"""Deterministic extraction of product-label fields from OCR results."""

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .spatial_analysis import SpatialLayout


FIELD_NAMES = (
    "product_name",
    "mrp",
    "mrp_inclusive_of_taxes",
    "unit_sale_price",
    "net_quantity",
    "manufacturer",
    "manufacturer_address",
    "importer",
    "importer_address",
    "packer",
    "packer_address",
    # ``month_year`` is retained for callers that consume the applicable
    # Legal Metrology manufacture/packing/import date. The typed fields retain
    # the OCR-declared date semantics.
    "month_year",
    "month_year_date_type",
    "manufacture_date",
    "packing_date",
    "import_date",
    "expiry_date",
    "best_before_date",
    "country_of_origin",
    "size",
    "consumer_care",
)

_MRP_PATTERN = re.compile(
    r"\b(?:M\s*\.?\s*R\s*\.?\s*P\s*\.?|maximum\s+retail\s+price)\s*[:\-]?\s*"
    r"(?:₹|Rs\.?|INR)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_MRP_LABEL_PATTERN = re.compile(
    r"\b(?:M\s*\.?\s*R\s*\.?\s*P\s*\.?|maximum\s+retail\s+price)\s*[:\-]?\s*(.*)$",
    re.IGNORECASE,
)
_MRP_VALUE_PATTERN = re.compile(
    r"(?:₹|â‚¹|Rs\.?|INR)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_MRP_TAX_INCLUSION_PATTERN = re.compile(
    r"\b(inclusive\s+of\s+(?:all\s+)?tax(?:es)?|incl\.?\s*(?:of\s+)?(?:all\s+)?tax(?:es)?)\b",
    re.IGNORECASE,
)
_UNIT_SALE_PRICE_PATTERN = re.compile(
    r"((?:â‚¹|₹|Rs\.?|INR)\s*\d+(?:\.\d{1,2})?\s*"
    r"(?:/|\bper\b)\s*(?:\d+(?:\.\d+)?\s*)?"
    r"(?:g|kg|ml|l|litres?|liters?|cm|m|number|unit|piece|pc)\b)",
    re.IGNORECASE,
)
_NET_QUANTITY_LABEL_PATTERN = re.compile(
    r"\b(?:net\s*(?:quantity|qty|contents|weight|wt\.?)|contents)"
    r"(?:\b|(?=[:\-\s]|$))\s*[:\-]?\s*(.*)$",
    re.IGNORECASE,
)
_NET_QUANTITY_VALUE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?\s*N(?:\s*\(\s*\d+(?:\.\d+)?\s*"
    r"(?:pairs?|pcs?|pieces?|nos?|units?)\s*\))?|"
    r"\d+(?:\.\d+)?\s*[xX]\s*\d+(?:\.\d+)?\s*"
    r"(?:kg|g|ml|l|pcs?|pieces?|nos?|units?|pairs?)|"
    r"\d+(?:\.\d+)?\s*(?:kgs?|kg|gms?|grams?|g|ml|litres?|liters?|l|"
    r"pcs?|pieces?|nos?|units?|pairs?)(?:\s*[xX]\s*\d+(?:\.\d+)?\s*"
    r"(?:kg|g|ml|l|pcs?|nos?|pairs?))?)",
    re.IGNORECASE,
)
_DATE_VALUE_PATTERN = re.compile(
    r"([A-Za-z]{3,9}\.?\s*[-/,.]?\s*\d{2,4}"
    r"|\d{1,2}\s*[-/.\s]\s*\d{1,2}\s*[-/.\s]\s*\d{2,4}"
    r"|\d{1,2}\s*[-/.\s]\s*\d{2,4})",
    re.IGNORECASE,
)
_DATE_TYPE_PATTERNS = (
    (
        "manufacture_date",
        re.compile(
            r"\b(?:month\s*(?:&|and)\s*year\s+of\s+manufacture|date\s+of\s+manufacture|"
            r"mfg\.?(?:\s*date)?|mfd\.?(?:\s*date)?|manufactur(?:e|ed|ing)(?:\s+(?:date|on))?)\b"
            r"\s*[:\-.]?\s*(.*)$",
            re.IGNORECASE,
        ),
    ),
    (
        "packing_date",
        re.compile(
            r"\b(?:month\s*(?:&|and)\s*year\s+of\s+packing|date\s+of\s+packing|"
            r"pkd\.?t?\.?(?:\s*date)?|packed(?:\s+(?:date|on))?|packing(?:\s+date)?)\b"
            r"\s*[:\-.]?\s*(.*)$",
            re.IGNORECASE,
        ),
    ),
    (
        "import_date",
        re.compile(
            r"\b(?:month\s*(?:&|and)\s*year\s+of\s+import|date\s+of\s+import|"
            r"import(?:ed)?(?:\s+(?:date|on))?)\b\s*[:\-.]?\s*(.*)$",
            re.IGNORECASE,
        ),
    ),
    (
        "expiry_date",
        re.compile(r"\b(?:expiry|exp\.?|use[\s-]*by)\b\s*[:\-.]?\s*(.*)$", re.IGNORECASE),
    ),
    (
        "best_before_date",
        re.compile(r"\bbest[\s-]*(?:before|by)\b\s*[:\-.]?\s*(.*)$", re.IGNORECASE),
    ),
)
_DATE_FIELDS = tuple(field for field, _ in _DATE_TYPE_PATTERNS)
_LEGAL_DATE_FIELDS = ("manufacture_date", "packing_date", "import_date")
_MIN_DATE_YEAR = 2000
_MAX_DATE_YEAR = 2100
_COUNTRY_PATTERN = re.compile(
    r"\b(?:country\s+of\s+origin|made\s+in|product\s+of|imported\s+from)\s*[:\-]?\s*"
    r"([A-Za-z][A-Za-z .-]{1,60})",
    re.IGNORECASE,
)
_COUNTRY_LABEL_PATTERN = re.compile(
    r"\b(?:country\s+of\s+origin|made\s+in|product\s+of|imported\s+from)\b\s*[:\-]?\s*(.*)$",
    re.IGNORECASE,
)
_COUNTRY_VALUE_TERMINATOR = re.compile(
    r"\s*(?:\(|[|;]|\s[-–—]\s)|\s+\b(?:manufactured|imported|marketed|"
    r"packed|distributed|for\s+(?:retail|domestic)|mrp|net\s+(?:quantity|qty|weight|wt\.?))\b",
    re.IGNORECASE,
)
_PRODUCT_NAME_PATTERN = re.compile(
    r"\b(?:product(?:\s*name)?|name\s*of\s*product)\b\s*[:\-]?\s*(.*)$",
    re.IGNORECASE,
)
_SIZE_PATTERN = re.compile(r"\b(?:size|dimensions?)\b\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9 .xX/-]{0,40})", re.IGNORECASE)
_SIZE_LABEL_PATTERN = re.compile(r"\b(?:size|dimensions?)\b\s*[:\-]?\s*(.*)$", re.IGNORECASE)
_CONSUMER_CARE_PATTERN = re.compile(
    r"^\s*(?:(?:for\s+)?(?:consumer|customer)(?:\s+related)?\s*(?:care|complaints?|queries?|service)"
    r"(?:\s*,?\s*please\s+contact)?"
    r"(?:\s*(?:details?|contact))?|for\s+(?:consumer|customer)\s+(?:queries?|complaints?)"
    r"\s*,?\s*(?:please\s+)?(?:contact|call|write\s+to)|helpline|toll\s*free|contact\s+us|"
    r"c[ou0]nsum(?:[ea@])?r\s+c[ae@]re|customer\s+support)\s*[:\-]?\s*(.*)$",
    re.IGNORECASE,
)
_INDIAN_CONTACT_PATTERN = re.compile(
    r"(?<!\d)\+91(?:[\s-]*\d){10}(?!\d)|"
    r"(?<!\d)[6-9](?:[\s-]*\d){9}(?!\d)|"
    r"(?<!\d)1800(?:[\s-]*\d){7}(?!\d)"
)
_PRODUCT_MIN_CONFIDENCE = 0.55
_PRODUCT_NEGATIVE_PATTERN = re.compile(
    r"\b(?:ingred\w*|nutrition(?:al)?|nutritional|energy|calories?|protein|"
    r"carbohydrate|sugar|sodium|total\s+fat|serving|fssai|licen[cs]e|"
    r"barcode|ean|upc|gstin|batch|b\.?no|lot\s*(?:no|number)|pincode|pin\s*code|"
    r"customer\s*(?:care|service)|consumer\s*(?:care|complaint))\b",
    re.IGNORECASE,
)
_IDENTIFIER_ONLY_PATTERN = re.compile(r"^[^A-Za-z]*[0-9][0-9\s-]{5,}[^A-Za-z]*$")
_ADDRESS_POSTAL_CODE_PATTERN = re.compile(r"\b\d{6}\b")
_DOMESTIC_PRODUCT_PATTERN = re.compile(
    r"\b(?:domestic\s+product|for\s+domestic\s+(?:sale|market))\b", re.IGNORECASE
)
_WHOLESALE_PATTERN = re.compile(
    r"\b(?:wholesale\s+(?:package|pack)|for\s+wholesale(?:\s+sale)?|not\s+for\s+retail\s+sale)\b",
    re.IGNORECASE,
)
_RETAIL_PATTERN = re.compile(
    r"\b(?:retail\s+(?:package|pack)|for\s+retail\s+sale)\b", re.IGNORECASE
)

_ENTITY_PATTERNS = {
    "manufacturer": re.compile(
        r"^\s*(?:manufactured(?:\s*(?:&|and)\s*(?:marketed|packed))?\s+by|"
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
        r"manufactured\s*(?:&|and)\s*packed\s+by|"
        r"pack(?:er|ing)\s+by|packer(?:\s+(?:name|details))?)\s*[:\-]?\s*(.*)$",
        re.IGNORECASE,
    ),
}
_DIRECT_ADDRESS_PATTERNS = {
    "manufacturer_address": re.compile(r"^\s*manufacturer(?:'s)?\s+address\s*[:\-]?\s*(.*)$", re.IGNORECASE),
    "importer_address": re.compile(r"^\s*importer(?:'s)?\s+address\s*[:\-]?\s*(.*)$", re.IGNORECASE),
    "packer_address": re.compile(r"^\s*packer(?:'s)?\s+address\s*[:\-]?\s*(.*)$", re.IGNORECASE),
}
_ENTITY_ADDRESS_EXCLUDED_PATTERN = re.compile(
    r"^\s*(?:phone|tel(?:ephone)?|mobile|contact|email|e-mail|fssai|licen[cs]e|lic\.?\s*no|"
    r"barcode|ean|upc|gstin|ingredients?|nutritional?\s+information|"
    r"(?:for\s+)?(?:any\s+)?(?:consumer|customer)?\s*(?:questions?|complaints?|queries?|feedback))\b",
    re.IGNORECASE,
)
_ENTITY_ADDRESS_BOUNDARY_PATTERN = re.compile(
    r"^\s*(?:date\s+of\s+(?:manufacture|packing|import)|"
    r"(?:manufacture|manufacturing|packing|import)\s+date|batch|lot)\b",
    re.IGNORECASE,
)
_LABEL_TERMS = re.compile(
    r"\b(?:m\s*\.?\s*r\s*\.?\s*p\s*\.?|net\s*(?:quantity|qty|contents|weight|wt\.?)|contents|"
    r"manufactured|manufacturer|mfg\.?|mfd\.?|imported|importer|packed\s+by|packer|"
    r"month\s*(?:&|and)\s*year|mfg\.?|mfd\.?|country\s+of\s+origin|"
    r"best[\s-]*(?:before|by)|use[\s-]*by|expiry|made\s+in|product\s+of|imported\s+from|size|"
    r"product(?:\s*name)?|(?:consumer|customer)\b\s*"
    r"(?:care|complaints?|queries?|service))\b",
    re.IGNORECASE,
)
_DECLARATION_FRAGMENT_PATTERN = re.compile(
    r"^\s*(?:m\s*\.?\s*r\s*\.?\s*p\s*\.?|maximum\s+retail|retail\s+price|"
    r"net|quantity|net\s+quantity|net\s+contents|net\s+weight|manufactured|packed|"
    r"imported|country\s+of|date\s+of|consumer|customer|product(?:\s+name)?|"
    r"name\s+of\s+product|size|dimensions?)\s*[:\-]?\s*$",
    re.IGNORECASE,
)


def extract_fields(ocr_results: Iterable[Mapping[str, Any]] | None) -> dict[str, str | None]:
    """Extract SIH26034 label fields from structured OCR output.

    The input is the list returned by ``ocr.extract_text``. Invalid or missing
    OCR entries are ignored so a partial label yields a complete, predictable
    dictionary with ``None`` for unavailable fields.
    """
    ocr_entries = list(ocr_results or [])
    layout = SpatialLayout(ocr_entries)
    lines = layout.reading_lines()
    confidence_by_line = _line_confidences(ocr_entries)
    text = "\n".join(lines)
    fields: dict[str, str | None] = {field: None for field in FIELD_NAMES}

    fields["product_name"] = _extract_product_name(lines, confidence_by_line, layout)
    fields["mrp"] = _extract_mrp(lines)
    fields["mrp_inclusive_of_taxes"] = _extract_mrp_tax_inclusion(ocr_entries, lines, layout)
    fields["unit_sale_price"] = _normalize_value(
        _first_group(_UNIT_SALE_PRICE_PATTERN, text)
    )
    fields["net_quantity"] = _extract_net_quantity(lines)
    typed_dates = _extract_typed_dates(lines)
    fields.update(typed_dates)
    for date_type in _LEGAL_DATE_FIELDS:
        if typed_dates[date_type]:
            fields["month_year"] = typed_dates[date_type]
            fields["month_year_date_type"] = date_type
            break
    fields["country_of_origin"] = _extract_country_of_origin(lines)
    fields["size"] = _extract_size(lines)
    fields["consumer_care"] = _extract_consumer_care(lines, layout)

    for entity, pattern in _ENTITY_PATTERNS.items():
        name, address = _extract_entity_spatial(layout, pattern)
        if name is None:
            name, address = _extract_entity(lines, pattern)
        fields[entity] = name
        fields[f"{entity}_address"] = address

    for field, pattern in _DIRECT_ADDRESS_PATTERNS.items():
        direct_address = _extract_direct_address_spatial(layout, pattern) or _extract_direct_address(lines, pattern)
        if direct_address:
            fields[field] = _normalize_value(direct_address)

    return fields


def derive_compliance_context(
    ocr_results: Iterable[Mapping[str, Any]] | None,
    extracted_fields: Mapping[str, Any] | None,
) -> dict[str, bool | None]:
    """Derive only explicit applicability facts from OCR evidence.

    This deliberately does not infer retail status or unit-sale-price
    applicability from quantity, a date, a product name, or a missing field.
    The returned shape is kept separate from extracted declarations so callers
    can distinguish OCR values from applicability evidence.
    """
    fields = extracted_fields if isinstance(extracted_fields, Mapping) else {}
    text = "\n".join(_ocr_lines(ocr_results))
    imported: bool | None = True if _has_extracted_value(fields.get("importer")) else None
    if imported is None and _DOMESTIC_PRODUCT_PATTERN.search(text):
        imported = False

    wholesale: bool | None = None
    if _WHOLESALE_PATTERN.search(text):
        wholesale = True
    elif _RETAIL_PATTERN.search(text):
        wholesale = False

    return {
        "imported": imported,
        "wholesale": wholesale,
        "unit_sale_price_applicable": None,
        "size_relevant": True if _has_extracted_value(fields.get("size")) else None,
    }


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


def _extract_consumer_care(lines: list[str], layout: SpatialLayout | None = None) -> str | None:
    # Geometry takes precedence when it is available: never let a support
    # heading in one column consume a phone/value from another column.
    if layout and layout.has_geometry:
        for detection in layout.detections:
            match = _CONSUMER_CARE_PATTERN.match(detection.text)
            if not match:
                continue
            values = [_normalize_value(match.group(1))]
            for following in layout.below_in_region(detection):
                if _is_label_line(following.text) or "entity" in following.cues or "nutrition" in following.cues or "identifier" in following.cues:
                    break
                values.append(following.text)
            value = _normalize_value(" ".join(part for part in values if part))
            if value:
                return value
    for index, line in enumerate(lines):
        match, consumed = _declaration_match(lines, index, _CONSUMER_CARE_PATTERN, anchored=True)
        if not match:
            continue

        section = [_normalize_value(match.group(1))]
        for following_line in lines[index + consumed + 1 :]:
            if _is_label_line(following_line):
                break
            section.append(following_line)
        return _normalize_value(" ".join(value for value in section if value))

    # A phone number without a consumer/contact cue may belong to a
    # manufacturer, importer, licence record, or unrelated OCR content.
    return None


def _extract_net_quantity(lines: list[str]) -> str | None:
    """Extract a quantity from a declaration line, retaining count context."""
    for index, line in enumerate(lines):
        match, consumed = _declaration_match(lines, index, _NET_QUANTITY_LABEL_PATTERN)
        if not match:
            continue

        candidates = [match.group(1)]
        if not match.group(1) and index + consumed + 1 < len(lines):
            candidates.append(lines[index + consumed + 1])
        for candidate in candidates:
            quantity = _quantity_from_text(candidate, allow_ocr_g=True)
            if quantity:
                return quantity

    # A standalone quantity is useful only when it is the complete OCR line;
    # this avoids treating a date, MRP, or address fragment as net quantity.
    for line in lines:
        quantity = _quantity_from_text(line)
        if quantity and _NET_QUANTITY_VALUE_PATTERN.fullmatch(line):
            return quantity
    return None


def _quantity_from_text(value: str, *, allow_ocr_g: bool = False) -> str | None:
    quantity = _first_group(_NET_QUANTITY_VALUE_PATTERN, value)
    if quantity:
        return _normalize_quantity(quantity)
    if allow_ocr_g:
        match = re.search(r"\b(\d+(?:\.\d+)?)\s+9\b", value)
        if match:
            return f"{match.group(1)} g"
    return None


def _extract_mrp(lines: list[str]) -> str | None:
    for index, line in enumerate(lines):
        match, consumed = _declaration_match(lines, index, _MRP_LABEL_PATTERN)
        if not match:
            continue
        candidates = [match.group(1)]
        if not _first_group(_MRP_VALUE_PATTERN, match.group(1)):
            candidates.extend(lines[index + consumed + 1 : index + consumed + 3])
        for candidate in candidates:
            value = _first_group(_MRP_VALUE_PATTERN, candidate)
            if value:
                return _normalize_mrp(value)
    return None


def _extract_mrp_tax_inclusion(
    ocr_results: Iterable[Mapping[str, Any]], lines: list[str], layout: SpatialLayout | None = None
) -> str | None:
    """Return tax wording only when it belongs to a detected MRP declaration.

    OCR commonly splits an MRP declaration across a label, value, and tax line.
    The small declaration window below accepts that layout, but stops at another
    declaration label and does not scan the rest of the package for tax text.
    """
    spatial_tax = _spatial_mrp_tax_inclusion(ocr_results, layout)
    if spatial_tax:
        return spatial_tax
    if _has_positioned_mrp_and_tax(ocr_results):
        return None

    for index, line in enumerate(lines):
        match, consumed = _declaration_match(lines, index, _MRP_LABEL_PATTERN)
        if not match:
            continue

        declaration_lines = [match.group(0)]
        for following_line in lines[index + consumed + 1 : index + consumed + 3]:
            if _is_label_line(following_line):
                break
            declaration_lines.append(following_line)

        # A bare MRP label is not enough: this must be the declaration from
        # which an MRP value can actually be extracted.
        if not any(_first_group(_MRP_VALUE_PATTERN, candidate) for candidate in declaration_lines):
            continue

        for candidate_index, candidate in enumerate(declaration_lines):
            tax_wording = _first_group(_MRP_TAX_INCLUSION_PATTERN, candidate)
            if not tax_wording:
                continue
            if candidate_index == 0 or _is_standalone_tax_inclusion(candidate):
                return _normalize_value(tax_wording)
    return None


def _spatial_mrp_tax_inclusion(
    ocr_results: Iterable[Mapping[str, Any]], layout: SpatialLayout | None = None
) -> str | None:
    """Link tax wording only to an MRP panel that is visibly adjacent to it."""
    if layout and layout.has_geometry:
        # An OCR engine often separates the MRP heading and its numeric value.
        # The heading is still the local declaration anchor; geometry continues
        # to prevent a tax phrase in another panel from being claimed.
        mrps = [item for item in layout.detections if _MRP_LABEL_PATTERN.search(item.text)]
        for tax in layout.detections:
            tax_text = _first_group(_MRP_TAX_INCLUSION_PATTERN, tax.text)
            if tax_text and any(layout.related(mrp, tax) for mrp in mrps):
                return _normalize_value(tax_text)
        return None
    detections = _ocr_detections(ocr_results)
    mrp_detections = [
        detection for detection in detections
        if _MRP_PATTERN.search(detection["text"]) and _box_bounds(detection.get("bounding_box"))
    ]
    for tax_detection in detections:
        tax_text = _first_group(_MRP_TAX_INCLUSION_PATTERN, tax_detection["text"])
        if not tax_text or not _box_bounds(tax_detection.get("bounding_box")):
            continue
        if any(_same_mrp_declaration_region(mrp, tax_detection) for mrp in mrp_detections):
            return _normalize_value(tax_text)
    return None


def _has_positioned_mrp_and_tax(ocr_results: Iterable[Mapping[str, Any]]) -> bool:
    detections = _ocr_detections(ocr_results)
    return any(
        _MRP_PATTERN.search(detection["text"]) and _box_bounds(detection.get("bounding_box"))
        for detection in detections
    ) and any(
        _MRP_TAX_INCLUSION_PATTERN.search(detection["text"]) and _box_bounds(detection.get("bounding_box"))
        for detection in detections
    )


def _same_mrp_declaration_region(mrp: Mapping[str, Any], tax: Mapping[str, Any]) -> bool:
    mrp_box = _box_bounds(mrp.get("bounding_box"))
    tax_box = _box_bounds(tax.get("bounding_box"))
    if mrp_box is None or tax_box is None:
        return False
    mrp_left, mrp_top, mrp_right, mrp_bottom = mrp_box
    tax_left, tax_top, tax_right, tax_bottom = tax_box
    overlap = max(0.0, min(mrp_right, tax_right) - max(mrp_left, tax_left))
    min_width = min(mrp_right - mrp_left, tax_right - tax_left)
    if min_width <= 0 or overlap < min_width * 0.5:
        return False
    vertical_gap = max(0.0, tax_top - mrp_bottom, mrp_top - tax_bottom)
    row_height = max(mrp_bottom - mrp_top, tax_bottom - tax_top, 1.0)
    return vertical_gap <= row_height * 3


def _is_standalone_tax_inclusion(value: str) -> bool:
    """Allow a split tax line only when it contains no unrelated declaration."""
    remainder = _MRP_TAX_INCLUSION_PATTERN.sub("", value, count=1)
    return not re.search(r"[A-Za-z0-9]", remainder)


def _extract_typed_dates(lines: list[str]) -> dict[str, str | None]:
    """Extract dates only when their declaration label establishes a type."""
    dates = {field: None for field in _DATE_FIELDS}
    for field, pattern in _DATE_TYPE_PATTERNS:
        for index, line in enumerate(lines):
            match, consumed = _declaration_match(lines, index, pattern)
            if not match:
                continue
            candidates = [match.group(1)]
            if not match.group(1) and index + consumed + 1 < len(lines):
                candidates.append(lines[index + consumed + 1])
            for candidate in candidates:
                value = _first_group(_DATE_VALUE_PATTERN, candidate)
                normalized = _normalize_month_year(value)
                if normalized:
                    dates[field] = normalized
                    break
            if dates[field]:
                break
    return dates


def _extract_country_of_origin(lines: list[str]) -> str | None:
    for index, line in enumerate(lines):
        match, consumed = _declaration_match(lines, index, _COUNTRY_LABEL_PATTERN)
        if not match:
            continue
        value = _country_value(match.group(1))
        if not value and index + consumed + 1 < len(lines):
            value = _country_value(lines[index + consumed + 1])
        if value:
            return value
    return _country_value(_first_group(_COUNTRY_PATTERN, "\n".join(lines)))


def _country_value(value: str | None) -> str | None:
    """Keep only the declared country before adjacent label description text."""
    normalized = _normalize_value(value)
    if not normalized:
        return None
    country = _normalize_value(_COUNTRY_VALUE_TERMINATOR.split(normalized, maxsplit=1)[0])
    if country and re.fullmatch(r"[A-Za-z][A-Za-z .-]{1,60}", country):
        return country
    return None


def _extract_size(lines: list[str]) -> str | None:
    for index, line in enumerate(lines):
        match, consumed = _declaration_match(lines, index, _SIZE_LABEL_PATTERN)
        if not match:
            continue
        value = _normalize_value(match.group(1))
        if not value and index + consumed + 1 < len(lines):
            value = _normalize_value(lines[index + consumed + 1])
        if value and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .xX/-]{0,40}", value):
            return value
    return None


def _declaration_candidates(lines: list[str], index: int) -> list[tuple[str, int]]:
    """Return an OCR line and one safe continuation for a split label.

    Only a short, known declaration fragment may consume the immediately next
    spatially ordered detection. This bridges fragmented OCR without broadly
    merging text from separate package panels.
    """
    line = lines[index]
    candidates = [(line, 0)]
    if _DECLARATION_FRAGMENT_PATTERN.match(line) and index + 1 < len(lines):
        continuation = _normalize_value(lines[index + 1])
        if continuation:
            candidates.append((f"{line} {continuation}", 1))
    return candidates


def _declaration_match(
    lines: list[str], index: int, pattern: re.Pattern[str], *, anchored: bool = False
) -> tuple[re.Match[str] | None, int]:
    for candidate, consumed in _declaration_candidates(lines, index):
        match = pattern.match(candidate) if anchored else pattern.search(candidate)
        if match:
            return match, consumed
    return None, 0


def _extract_labeled_line_value(lines: list[str], pattern: re.Pattern[str]) -> str | None:
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue
        value = _normalize_value(match.group(1))
        if value:
            return value
        if index + 1 < len(lines):
            return _normalize_value(lines[index + 1])
    return None


def _extract_direct_address(lines: list[str], pattern: re.Pattern[str]) -> str | None:
    """Read a labelled address and adjacent lines without crossing a declaration."""
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue
        parts = [_normalize_value(match.group(1))]
        for following_line in lines[index + 1 :]:
            if _is_entity_address_boundary(following_line) or _is_entity_address_noise(following_line):
                break
            parts.append(_normalize_value(following_line))
            if _ADDRESS_POSTAL_CODE_PATTERN.search(following_line):
                break
        return _normalize_value(" ".join(part for part in parts if part))
    return None


def _extract_direct_address_spatial(layout: SpatialLayout, pattern: re.Pattern[str]) -> str | None:
    """Read only the visually connected address panel of an address label."""
    if not layout.has_geometry:
        return None
    for detection in layout.detections:
        match = pattern.match(detection.text)
        if not match:
            continue
        parts = [_normalize_value(match.group(1))]
        for following in layout.below_in_region(detection):
            if _is_entity_address_boundary(following.text) or _is_entity_address_noise(following.text):
                break
            if following.cues & {"nutrition", "identifier", "contact", "pricing"}:
                break
            parts.append(following.text)
            if _ADDRESS_POSTAL_CODE_PATTERN.search(following.text):
                break
        return _normalize_value(" ".join(part for part in parts if part))
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

    detections: list[tuple[str, int, tuple[float, float] | None]] = []
    for index, result in enumerate(ocr_results):
        if not isinstance(result, Mapping):
            continue
        text = result.get("text")
        if isinstance(text, str):
            normalized = _normalize_value(text)
            if normalized:
                detections.append((normalized, index, _box_origin(result.get("bounding_box"))))

    if not detections or not all(origin is not None for _, _, origin in detections):
        return [text for text, _, _ in detections]
    return _spatially_ordered_lines(detections)


def _line_confidences(ocr_results: Iterable[Mapping[str, Any]] | None) -> dict[str, float | None]:
    """Return the strongest reported confidence for each normalized OCR line."""
    confidences: dict[str, float | None] = {}
    if not ocr_results:
        return confidences
    for result in ocr_results:
        if not isinstance(result, Mapping) or not isinstance(result.get("text"), str):
            continue
        text = _normalize_value(result["text"])
        if not text:
            continue
        confidence = result.get("confidence")
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            existing = confidences.get(text)
            confidences[text] = max(float(confidence), existing) if existing is not None else float(confidence)
        else:
            confidences.setdefault(text, None)
    return confidences


def _box_origin(bounding_box: Any) -> tuple[float, float] | None:
    if not isinstance(bounding_box, (list, tuple)) or not bounding_box:
        return None
    points = [
        point
        for point in bounding_box
        if isinstance(point, (list, tuple))
        and len(point) >= 2
        and isinstance(point[0], (int, float))
        and isinstance(point[1], (int, float))
    ]
    if not points:
        return None
    return min(float(point[0]) for point in points), sum(float(point[1]) for point in points) / len(points)


def _box_bounds(bounding_box: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(bounding_box, (list, tuple)):
        return None
    points = [
        point for point in bounding_box
        if isinstance(point, (list, tuple))
        and len(point) >= 2
        and isinstance(point[0], (int, float))
        and isinstance(point[1], (int, float))
    ]
    if not points:
        return None
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _spatially_ordered_lines(
    detections: list[tuple[str, int, tuple[float, float] | None]]
) -> list[str]:
    """Order OCR detections by nearby visual rows, then left-to-right."""
    positioned = sorted(
        ((text, index, origin) for text, index, origin in detections if origin is not None),
        key=lambda item: (item[2][1], item[2][0], item[1]),
    )
    rows: list[list[tuple[str, int, tuple[float, float]]]] = []
    for text, index, origin in positioned:
        if not rows or abs(origin[1] - rows[-1][0][2][1]) > 8:
            rows.append([(text, index, origin)])
        else:
            rows[-1].append((text, index, origin))

    return [
        text
        for row in rows
        for text, _, _ in sorted(row, key=lambda item: (item[2][0], item[1]))
    ]


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

    if field == "mrp":
        # MRP values are sometimes split across OCR detections,
        # e.g. "MRP IN MUMBAI Rs." followed by "70/-".
        # Accept the numeric value itself when it is a standalone
        # OCR detection.
        if re.fullmatch(r"\d+(?:\.\d{1,2})?", normalized_detection):
            return normalized_value == normalized_detection

        if not _MRP_PATTERN.search(detected_text):
            return False

    return normalized_value in normalized_detection or (
        len(normalized_detection) >= 4
        and normalized_detection in normalized_value
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
        match, consumed = _declaration_match(lines, index, pattern, anchored=True)
        if not match:
            continue

        name = _normalize_value(match.group(1))
        address_parts: list[str] = []
        for following_line in lines[index + consumed + 1 :]:
            if _is_entity_address_boundary(following_line) or _is_entity_address_noise(following_line):
                break
            value = _normalize_value(following_line)
            if not value:
                continue
            if name is None:
                name = value
                continue
            address_parts.append(
                re.sub(r"^address\s*[:\-]?\s*", "", value, flags=re.IGNORECASE)
            )
            if _ADDRESS_POSTAL_CODE_PATTERN.search(value):
                break

        if name is None:
            return None, None
        address = _normalize_value(" ".join(address_parts))
        return name, address

    return None, None


def _extract_entity_spatial(layout: SpatialLayout, pattern: re.Pattern[str]) -> tuple[str | None, str | None]:
    """Extract an entity and address from its own geometry-derived region."""
    if not layout.has_geometry:
        return None, None
    for detection in layout.detections:
        match = pattern.match(detection.text)
        if not match:
            continue
        name = _normalize_value(match.group(1))
        address_parts: list[str] = []
        for following in layout.below_in_region(detection):
            # Semantic panel starts are hard boundaries even when OCR rows are
            # physically touching, avoiding address/nutrition contamination.
            if _is_entity_address_boundary(following.text) or _is_entity_address_noise(following.text):
                break
            if following.cues & {"nutrition", "identifier", "contact", "pricing"}:
                break
            value = _normalize_value(following.text)
            if not value:
                continue
            if name is None:
                name = value
            else:
                address_parts.append(re.sub(r"^address\s*[:\-]?\s*", "", value, flags=re.IGNORECASE))
                if _ADDRESS_POSTAL_CODE_PATTERN.search(value):
                    break
        if name:
            return name, _normalize_value(" ".join(address_parts))
    return None, None


def _is_label_line(line: str) -> bool:
    return any(pattern.match(line) for pattern in _ENTITY_PATTERNS.values()) or any(
        pattern.match(line) for pattern in _DIRECT_ADDRESS_PATTERNS.values()
    ) or bool(_LABEL_TERMS.search(line))


def _is_entity_address_boundary(line: str) -> bool:
    """Return whether a line starts a new declaration, not an address line."""
    return (
        _is_label_line(line)
        or bool(_DECLARATION_FRAGMENT_PATTERN.match(line))
        or bool(_ENTITY_ADDRESS_BOUNDARY_PATTERN.match(line))
    )


def _is_entity_address_noise(line: str) -> bool:
    """Reject identifiers and contact details that cannot establish an address."""
    return bool(
        _ENTITY_ADDRESS_EXCLUDED_PATTERN.match(line)
        or _INDIAN_CONTACT_PATTERN.search(line)
        or _IDENTIFIER_ONLY_PATTERN.fullmatch(line)
    )


def _extract_product_name(
    lines: list[str], confidence_by_line: Mapping[str, float | None], layout: SpatialLayout | None = None
) -> str | None:
    for index, line in enumerate(lines):
        match, consumed = _declaration_match(lines, index, _PRODUCT_NAME_PATTERN)
        if not match:
            continue
        value = _product_candidate_value(match.group(1))
        confidence = confidence_by_line.get(line)
        if not value and index + consumed + 1 < len(lines):
            value = _product_candidate_value(lines[index + consumed + 1])
            confidence = confidence_by_line.get(lines[index + consumed + 1])
        if value and _looks_like_product_name(value, confidence):
            return value

    # Explicit labels retain their existing semantics.  For unlabeled titles,
    # use visual prominence rather than flattening columns into OCR order.
    if layout and layout.has_geometry:
        candidates: list[tuple[float, int, str]] = []
        positioned = [item for item in layout.detections if item.bounds]
        min_top = min((item.bounds[1] for item in positioned), default=0.0)  # type: ignore[index]
        max_height = max((item.bounds[3] - item.bounds[1] for item in positioned), default=1.0)  # type: ignore[index]
        for item in positioned:
            value = _product_candidate_value(item.text)
            if not value or not _looks_like_product_name(value, item.confidence):
                continue
            left, top, right, bottom = item.bounds  # type: ignore[misc]
            score = min(item.confidence, 1.0) if item.confidence is not None else 0.35
            score += min(0.35, (bottom - top) / max_height * 0.35)
            score += max(0.0, 0.25 - ((top - min_top) / max(layout.line_height * 12, 1)) * 0.25)
            if len(layout.in_region(item)) <= 3:
                score += 0.12
            # A generic product declaration is normally descriptive, while a
            # standalone word is more likely to be a brand or marketing mark.
            # This is deliberately a preference, not an exclusion.
            if len(re.findall(r"[A-Za-z]{2,}", value)) >= 2:
                score += 0.55
            else:
                score -= 0.10
            if item.cues:
                score -= 0.8
            candidates.append((score, -item.index, value))
        if candidates:
            score, _, value = max(candidates)
            if score >= 0.9:
                return value

    declaration_indexes = [index for index, line in enumerate(lines) if _is_label_line(line)]
    first_declaration = declaration_indexes[0] if declaration_indexes else None
    candidates: list[tuple[float, int, str]] = []
    for index, line in enumerate(lines):
        value = _product_candidate_value(line)
        confidence = confidence_by_line.get(line)
        if not value or not _looks_like_product_name(value, confidence):
            continue
        score = 1.0 if first_declaration is not None and index < first_declaration else 0.0
        score += min(confidence, 1.0) if confidence is not None else 0.35
        if len(re.findall(r"[A-Za-z]{2,}", value)) >= 2:
            score += 0.25
        if value.isupper():
            score += 0.1
        candidates.append((score, index, value))
    if not candidates:
        return None
    score, _, value = max(candidates, key=lambda candidate: (candidate[0], -candidate[1]))
    return value if score >= 1.15 else None


def _product_candidate_value(value: str) -> str | None:
    """Remove an explicit trailing quantity from an otherwise textual title."""
    normalized = _normalize_value(value)
    if not normalized:
        return None
    match = re.fullmatch(r"(.+?)\s*\(\s*([^)]+)\s*\)", normalized)
    if match and _quantity_from_text(match.group(2)):
        return _normalize_value(match.group(1))
    return normalized


def _looks_like_product_name(value: str, confidence: float | None = None) -> bool:
    """Reject common non-product OCR lines before using an unlabeled fallback."""
    if confidence is not None and confidence < _PRODUCT_MIN_CONFIDENCE:
        return False
    if _is_label_line(value) or _quantity_from_text(value) or _MRP_PATTERN.search(value):
        return False
    if _INDIAN_CONTACT_PATTERN.search(value) or "@" in value:
        return False
    if _PRODUCT_NEGATIVE_PATTERN.search(value) or _IDENTIFIER_ONLY_PATTERN.fullmatch(value):
        return False
    if re.search(r"\b(?:address|road|street|sector|plot|pincode|pin|india)\b", value, re.IGNORECASE):
        return False
    words = re.findall(r"[A-Za-z]{2,}", value)
    if len(words) < 2:
        return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9 .&'/-]{5,60}", value) and re.search(r"[A-Za-z]", value))
    if re.search(r"\d", value) and not re.fullmatch(r"[A-Za-z][A-Za-z0-9 .&'/-]{2,60}", value):
        return False
    return len(value) <= 80


def _first_group(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def _normalize_value(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip(" :-\t")
    return normalized or None


def _has_extracted_value(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


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

    # Full date: DD-MM-YY / DD-MM-YYYY -> MM/YY or MM/YYYY
    full_date = re.fullmatch(
        r"(\d{1,2})\s*[-/.\s]\s*(\d{1,2})\s*[-/.\s]\s*(\d{2,4})",
        value,
    )
    if full_date:
        day, month, year = full_date.groups()
        if not _plausible_date_parts(day, month, year):
            return None
        return f"{month.zfill(2)}/{year}"

    # Month-Year: MM-YY / MM-YYYY
    numeric = re.fullmatch(
        r"(\d{1,2})\s*[-/.\s]\s*(\d{2,4})",
        value,
    )
    if numeric:
        month, year = numeric.groups()
        if not _plausible_date_parts(None, month, year):
            return None
        return f"{month.zfill(2)}/{year}"

    named = re.fullmatch(r"([A-Za-z]{3,9})\s+(\d{2,4})", value)
    if not named:
        return None
    month_name, year = named.groups()
    if month_name.casefold() not in {
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    } or not _plausible_date_parts(None, "1", year):
        return None
    return f"{month_name.title()} {year}"


def _plausible_date_parts(day: str | None, month: str, year: str) -> bool:
    """Reject OCR-like years and impossible calendar values before extraction."""
    resolved_year = int(year) + 2000 if len(year) == 2 else int(year)
    if not _MIN_DATE_YEAR <= resolved_year <= _MAX_DATE_YEAR:
        return False
    try:
        month_value = int(month)
    except ValueError:
        return False
    if not 1 <= month_value <= 12:
        return False
    if day is not None:
        try:
            day_value = int(day)
        except ValueError:
            return False
        if not 1 <= day_value <= 31:
            return False
    return True
