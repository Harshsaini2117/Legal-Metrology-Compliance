"""Deterministic extraction of product-label fields from OCR results."""

import re
from collections.abc import Iterable, Mapping
from typing import Any


FIELD_NAMES = (
    "product_name",
    "mrp",
    "mrp_inclusive_of_taxes",
    "net_quantity",
    "manufacturer",
    "manufacturer_address",
    "importer",
    "importer_address",
    "packer",
    "packer_address",
    "month_year",
    "country_of_origin",
    "size",
    "consumer_care",
)

_MRP_PATTERN = re.compile(
    r"\bM\s*\.?\s*R\s*\.?\s*P\s*\.?\s*[:\-]?\s*"
    r"(?:₹|Rs\.?|INR)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_MRP_TAX_INCLUSION_PATTERN = re.compile(
    r"\b(inclusive\s+of\s+(?:all\s+)?tax(?:es)?|incl\.?\s*(?:of\s+)?(?:all\s+)?tax(?:es)?)\b",
    re.IGNORECASE,
)
_NET_QUANTITY_LABEL_PATTERN = re.compile(
    r"\b(?:net\s*(?:quantity|qty|contents)|contents)\b\s*[:\-]?\s*(.*)$",
    re.IGNORECASE,
)
_NET_QUANTITY_VALUE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?\s*N\s*\(\s*\d+(?:\.\d+)?\s*"
    r"(?:pairs?|pcs?|pieces?|nos?|units?)\s*\)|"
    r"\d+(?:\.\d+)?\s*(?:kgs?|kg|gms?|grams?|g|ml|litres?|liters?|l|"
    r"pcs?|pieces?|nos?|units?|pairs?)(?:\s*[xX]\s*\d+(?:\.\d+)?\s*"
    r"(?:kg|g|ml|l|pcs?|nos?|pairs?))?)",
    re.IGNORECASE,
)
_MONTH_YEAR_PATTERN = re.compile(
    r"(?:month\s*(?:&|and)\s*year(?:\s+of\s+(?:import|manufacture|packing))?|"
    r"mfg\.?(?:\s*date)?|mfd\.?(?:\s*date)?|manufactured\s+on|packed\s+on|date\s+of\s+"
    r"(?:manufacture|packing|import)|best[\s-]*(?:before|by)|use[\s-]*by|"
    r"expiry|exp\.?)\s*(?:[:\-.]\s*)*"
    r"([A-Za-z]{3,9}\.?\s*[-/,.]?\s*\d{2,4}|\d{1,2}\s*[-/.\s]\s*\d{2,4})",
    re.IGNORECASE,
)
_COUNTRY_PATTERN = re.compile(
    r"\b(?:country\s+of\s+origin|made\s+in|product\s+of)\s*[:\-]?\s*"
    r"([A-Za-z][A-Za-z .-]{1,60})",
    re.IGNORECASE,
)
_PRODUCT_NAME_PATTERN = re.compile(r"\b(?:product(?:\s*name)?|name\s*of\s*product)\s*[:\-]\s*(.+)", re.IGNORECASE)
_SIZE_PATTERN = re.compile(r"\bsize\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9 .xX/-]{0,40})", re.IGNORECASE)
_CONSUMER_CARE_PATTERN = re.compile(
    r"^\s*(?:(?:for\s+)?(?:consumer|customer)(?:\s+related)?\s*(?:care|complaints?|queries?|service)"
    r"(?:\s*,?\s*please\s+contact)?"
    r"(?:\s*(?:details?|contact))?|for\s+(?:consumer|customer)\s+(?:queries?|complaints?)"
    r"\s*,?\s*please\s+contact)\s*[:\-]?\s*(.*)$",
    re.IGNORECASE,
)
_INDIAN_CONTACT_PATTERN = re.compile(
    r"(?<!\d)\+91(?:[\s-]*\d){10}(?!\d)|"
    r"(?<!\d)[6-9](?:[\s-]*\d){9}(?!\d)|"
    r"(?<!\d)1800(?:[\s-]*\d){7}(?!\d)"
)

_ENTITY_PATTERNS = {
    "manufacturer": re.compile(
        r"^\s*(?:manufactured(?:\s*(?:&|and)\s*marketed)?\s+by|"
        r"manufacture[dr]?\s+by|m(?:fg|fd|fr)\.?\s+by|"
        r"manufacturer(?:\s+(?:name|details))?)\s*[:\-]?\s*(.*)$",
        re.IGNORECASE,
    ),
    "importer": re.compile(
        r"^\s*(?:imported(?:\s*(?:&|and)\s*marketed)?\s+by|"
        r"import(?:\s*(?:&|and)\s*marketed)?\s+by|"
        r"importer(?:\s+(?:name|details))?)\s*[:\-]?\s*(.*)$",
        re.IGNORECASE,
    ),
    "packer": re.compile(
        r"^\s*(?:packed(?:\s*(?:&|and)\s*marketed)?\s+by|"
        r"pack(?:er|ing)\s+by|packer(?:\s+(?:name|details))?)\s*[:\-]?\s*(.*)$",
        re.IGNORECASE,
    ),
}
_DIRECT_ADDRESS_PATTERNS = {
    "manufacturer_address": re.compile(r"^\s*manufacturer(?:'s)?\s+address\s*[:\-]?\s*(.*)$", re.IGNORECASE),
    "importer_address": re.compile(r"^\s*importer(?:'s)?\s+address\s*[:\-]?\s*(.*)$", re.IGNORECASE),
    "packer_address": re.compile(r"^\s*packer(?:'s)?\s+address\s*[:\-]?\s*(.*)$", re.IGNORECASE),
}
_LABEL_TERMS = re.compile(
    r"\b(?:m\s*\.?\s*r\s*\.?\s*p\s*\.?|net\s*(?:quantity|qty|contents)|contents|"
    r"manufactured|manufacturer|mfg\.?|mfd\.?|imported|importer|packed\s+by|packer|"
    r"month\s*(?:&|and)\s*year|mfg\.?|mfd\.?|country\s+of\s+origin|"
    r"best[\s-]*(?:before|by)|use[\s-]*by|expiry|made\s+in|product\s+of|size|"
    r"product(?:\s*name)?|(?:consumer|customer)\b\s*"
    r"(?:care|complaints?|queries?|service))\b",
    re.IGNORECASE,
)


def extract_fields(ocr_results: Iterable[Mapping[str, Any]] | None) -> dict[str, str | None]:
    """Extract SIH26034 label fields from structured OCR output.

    The input is the list returned by ``ocr.extract_text``. Invalid or missing
    OCR entries are ignored so a partial label yields a complete, predictable
    dictionary with ``None`` for unavailable fields.
    """
    lines = _ocr_lines(ocr_results)
    text = "\n".join(lines)
    fields: dict[str, str | None] = {field: None for field in FIELD_NAMES}

    fields["product_name"] = _first_group(_PRODUCT_NAME_PATTERN, text) or _product_name_fallback(lines)
    fields["mrp"] = _normalize_mrp(_first_group(_MRP_PATTERN, text))
    fields["mrp_inclusive_of_taxes"] = _normalize_value(
        _first_group(_MRP_TAX_INCLUSION_PATTERN, text)
    )
    fields["net_quantity"] = _extract_net_quantity(lines)
    fields["month_year"] = _normalize_month_year(_first_group(_MONTH_YEAR_PATTERN, text))
    fields["country_of_origin"] = _normalize_value(_first_group(_COUNTRY_PATTERN, text))
    fields["size"] = _normalize_value(_first_group(_SIZE_PATTERN, text))
    fields["consumer_care"] = _extract_consumer_care(lines)

    for entity, pattern in _ENTITY_PATTERNS.items():
        name, address = _extract_entity(lines, pattern)
        fields[entity] = name
        fields[f"{entity}_address"] = address

    for field, pattern in _DIRECT_ADDRESS_PATTERNS.items():
        direct_address = _first_group(pattern, text)
        if direct_address:
            fields[field] = _normalize_value(direct_address)

    return fields


def map_field_evidence(
    ocr_results: Iterable[Mapping[str, Any]] | None,
    extracted_fields: Mapping[str, Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    """Return the OCR detections that deterministically support each field.

    Extraction intentionally normalizes OCR text (for example, ``GMS`` to
    ``g`` and date separators). This mapper links a value only when the
    normalized value and the detected text still have a direct textual match.
    It returns an empty list when no such link exists rather than inferring a
    location from nearby OCR detections.
    """
    fields = extracted_fields if isinstance(extracted_fields, Mapping) else {}
    detections = _ocr_detections(ocr_results)
    evidence: dict[str, list[dict[str, Any]]] = {field: [] for field in FIELD_NAMES}

    for field in FIELD_NAMES:
        value = fields.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        for detection in detections:
            if _evidence_matches(field, value, detection["text"]):
                evidence[field].append(
                    {
                        "source_ocr_text": detection["text"],
                        "confidence": detection.get("confidence"),
                        "bounding_box": detection.get("bounding_box"),
                    }
                )
    return evidence


def _extract_consumer_care(lines: list[str]) -> str | None:
    for index, line in enumerate(lines):
        match = _CONSUMER_CARE_PATTERN.match(line)
        if not match:
            continue

        section = [_normalize_value(match.group(1))]
        for following_line in lines[index + 1 :]:
            if _is_label_line(following_line):
                break
            section.append(following_line)
        return _normalize_value(" ".join(value for value in section if value))

    return _first_phone_number(lines)


def _extract_net_quantity(lines: list[str]) -> str | None:
    """Extract a quantity from a declaration line, retaining count context."""
    for index, line in enumerate(lines):
        match = _NET_QUANTITY_LABEL_PATTERN.search(line)
        if not match:
            continue

        candidates = [match.group(1)]
        if not match.group(1) and index + 1 < len(lines):
            candidates.append(lines[index + 1])
        for candidate in candidates:
            quantity = _first_group(_NET_QUANTITY_VALUE_PATTERN, candidate)
            if quantity:
                return _normalize_quantity(quantity)
    return None


def _first_phone_number(values: Iterable[str | None]) -> str | None:
    for value in values:
        if not value:
            continue
        match = _INDIAN_CONTACT_PATTERN.search(value)
        if match:
            return _normalize_value(match.group(0))
    return None


def _ocr_lines(ocr_results: Iterable[Mapping[str, Any]] | None) -> list[str]:
    if not ocr_results:
        return []

    lines = []
    for result in ocr_results:
        if not isinstance(result, Mapping):
            continue
        text = result.get("text")
        if isinstance(text, str):
            normalized = _normalize_value(text)
            if normalized:
                lines.append(normalized)
    return lines


def _ocr_detections(ocr_results: Iterable[Mapping[str, Any]] | None) -> list[Mapping[str, Any]]:
    if not ocr_results:
        return []
    return [
        result
        for result in ocr_results
        if isinstance(result, Mapping) and isinstance(result.get("text"), str) and result["text"].strip()
    ]


def _evidence_matches(field: str, value: str, detected_text: str) -> bool:
    """Require a textual value match, with narrow safeguards for MRP."""
    normalized_value = _match_text(value)
    normalized_detection = _match_text(detected_text)
    if not normalized_value or not normalized_detection:
        return False

    if field == "mrp" and not _MRP_PATTERN.search(detected_text):
        return False

    # A detected line can contain the label and value, or a multi-line field
    # (such as an address) can contain the detected line as one of its parts.
    return normalized_value in normalized_detection or (
        len(normalized_detection) >= 4 and normalized_detection in normalized_value
    )


def _match_text(value: str) -> str:
    """Normalize only OCR/extraction presentation differences for matching."""
    normalized = value.casefold()
    normalized = re.sub(r"\b(?:gms?|grams?)\b", "g", normalized)
    normalized = re.sub(r"\b(?:kgs?)\b", "kg", normalized)
    normalized = re.sub(r"\b(?:litres?|liters?)\b", "l", normalized)
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _extract_entity(lines: list[str], pattern: re.Pattern[str]) -> tuple[str | None, str | None]:
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue

        section = [_normalize_value(match.group(1))]
        for following_line in lines[index + 1 :]:
            if _is_label_line(following_line):
                break
            section.append(following_line)

        values = [value for value in section if value]
        if not values:
            return None, None

        name = values[0]
        address_parts = [re.sub(r"^address\s*[:\-]?\s*", "", value, flags=re.IGNORECASE) for value in values[1:]]
        address = _normalize_value(" ".join(address_parts))
        return name, address

    return None, None


def _is_label_line(line: str) -> bool:
    return any(pattern.match(line) for pattern in _ENTITY_PATTERNS.values()) or any(
        pattern.match(line) for pattern in _DIRECT_ADDRESS_PATTERNS.values()
    ) or bool(_LABEL_TERMS.search(line))


def _product_name_fallback(lines: list[str]) -> str | None:
    for line in lines:
        if not _LABEL_TERMS.search(line) and re.search(r"[A-Za-z]", line):
            return line
    return None


def _first_group(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def _normalize_value(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip(" :-\t")
    return normalized or None


def _normalize_mrp(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace(",", "")


def _normalize_quantity(value: str | None) -> str | None:
    value = _normalize_value(value)
    if not value:
        return None
    value = re.sub(r"\b(?:gms?|grams?)\b", "g", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:kgs?)\b", "kg", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:litres?|liters?)\b", "L", value, flags=re.IGNORECASE)
    return value


def _normalize_month_year(value: str | None) -> str | None:
    value = _normalize_value(value)
    if not value:
        return None

    value = re.sub(r"(?<=[A-Za-z]),\s*", " ", value)
    numeric = re.fullmatch(r"(\d{1,2})\s*[-/.\s]\s*(\d{2,4})", value)
    if numeric:
        return f"{numeric.group(1).zfill(2)}/{numeric.group(2)}"
    return value.title()
