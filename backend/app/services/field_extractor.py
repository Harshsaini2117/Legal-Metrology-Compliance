"""Deterministic extraction of product-label fields from OCR results."""

import re
from collections.abc import Iterable, Mapping
from typing import Any


FIELD_NAMES = (
    "product_name",
    "mrp",
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
)

_MRP_PATTERN = re.compile(
    r"\bM\s*\.?\s*R\s*\.?\s*P\s*\.?[^\d\n]{0,40}"
    r"(?:₹|Rs\.?|INR)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_NET_QUANTITY_PATTERN = re.compile(
    r"\bNET\s*(?:QUANTITY|QTY|CONTENTS)\s*[:\-]?\s*(?:[^\n]*?\(\s*)?"
    r"([0-9]+(?:\.\d+)?\s*(?:kgs?|kg|gms?|grams?|g|ml|litres?|liters?|l|"
    r"pcs?|pieces?|nos?|units?|pairs?)(?:\s*[xX]\s*[0-9]+(?:\.\d+)?\s*"
    r"(?:kg|g|ml|l|pcs?|nos?|pairs?))?)",
    re.IGNORECASE,
)
_MONTH_YEAR_PATTERN = re.compile(
    r"(?:month\s*(?:&|and)\s*year(?:\s+of\s+(?:import|manufacture|packing))?|"
    r"mfg\.?|mfd\.?|manufactured\s+on|packed\s+on)\s*(?:[:\-]\s*)*"
    r"([A-Za-z]{3,9}\.?\s*[-/,]?\s*\d{2,4}|\d{1,2}\s*[-/]\s*\d{2,4})",
    re.IGNORECASE,
)
_COUNTRY_PATTERN = re.compile(
    r"\b(?:country\s+of\s+origin|made\s+in|product\s+of)\s*[:\-]?\s*"
    r"([A-Za-z][A-Za-z .-]{1,60})",
    re.IGNORECASE,
)
_PRODUCT_NAME_PATTERN = re.compile(r"\b(?:product(?:\s*name)?|name\s*of\s*product)\s*[:\-]\s*(.+)", re.IGNORECASE)
_SIZE_PATTERN = re.compile(r"\bsize\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9 .xX/-]{0,40})", re.IGNORECASE)

_ENTITY_PATTERNS = {
    "manufacturer": re.compile(
        r"^\s*(?:manufactured(?:\s*&\s*marketed)?\s+by|manufacturer)\s*[:\-]?\s*(.*)$",
        re.IGNORECASE,
    ),
    "importer": re.compile(
        r"^\s*(?:imported(?:\s*&\s*marketed)?\s+by|importer)\s*[:\-]?\s*(.*)$",
        re.IGNORECASE,
    ),
    "packer": re.compile(
        r"^\s*(?:packed\s+by|packer)\s*[:\-]?\s*(.*)$",
        re.IGNORECASE,
    ),
}
_DIRECT_ADDRESS_PATTERNS = {
    "manufacturer_address": re.compile(r"^\s*manufacturer(?:'s)?\s+address\s*[:\-]?\s*(.*)$", re.IGNORECASE),
    "importer_address": re.compile(r"^\s*importer(?:'s)?\s+address\s*[:\-]?\s*(.*)$", re.IGNORECASE),
    "packer_address": re.compile(r"^\s*packer(?:'s)?\s+address\s*[:\-]?\s*(.*)$", re.IGNORECASE),
}
_LABEL_TERMS = re.compile(
    r"\b(?:m\s*\.?\s*r\s*\.?\s*p\s*\.?|net\s*(?:quantity|qty|contents)|"
    r"manufactured|manufacturer|imported|importer|packed\s+by|packer|"
    r"month\s*(?:&|and)\s*year|mfg\.?|mfd\.?|country\s+of\s+origin|"
    r"made\s+in|product\s+of|size|product(?:\s*name)?)\b",
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
    fields["net_quantity"] = _normalize_quantity(_first_group(_NET_QUANTITY_PATTERN, text))
    fields["month_year"] = _normalize_month_year(_first_group(_MONTH_YEAR_PATTERN, text))
    fields["country_of_origin"] = _normalize_value(_first_group(_COUNTRY_PATTERN, text))
    fields["size"] = _normalize_value(_first_group(_SIZE_PATTERN, text))

    for entity, pattern in _ENTITY_PATTERNS.items():
        name, address = _extract_entity(lines, pattern)
        fields[entity] = name
        fields[f"{entity}_address"] = address

    for field, pattern in _DIRECT_ADDRESS_PATTERNS.items():
        direct_address = _first_group(pattern, text)
        if direct_address:
            fields[field] = _normalize_value(direct_address)

    return fields


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

    numeric = re.fullmatch(r"(\d{1,2})\s*[-/]\s*(\d{2,4})", value)
    if numeric:
        return f"{numeric.group(1).zfill(2)}/{numeric.group(2)}"
    return value.title()
