"""Evidence-aware Legal Metrology declaration checks for packaged commodities.

This MVP evaluates only normalized text fields. It cannot determine label
placement, font size, image completeness, or category-specific exemptions.
Accordingly, missing OCR evidence is reported as ``UNABLE_TO_VERIFY`` rather
than as a legal violation.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable


STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"

_OFFICIAL_RULE_6_SOURCE = (
    "https://consumeraffairs.nic.in/sites/default/files/file-uploads/latestnews/"
    "2023.01.18%20advisory%20for%20outer%20gift%20package%20declarations.pdf"
)
_OFFICIAL_UNIT_SALE_PRICE_SOURCE = (
    "https://consumeraffairs.nic.in/sites/default/files/file-uploads/latestnews/230946.pdf"
)
_MONTH_YEAR_PATTERN = re.compile(
    r"^(?:0[1-9]|1[0-2])/(?:\d{2}|\d{4})$|^[A-Za-z]{3,9}\s+\d{2,4}$"
)
_NET_QUANTITY_PATTERN = re.compile(
    r"^(?:"
    r"\d+(?:\.\d+)?\s*(?:kg|g|mg|l|ml|cl|m|cm|mm|m2|cm2)"
    r"(?:\s*[xX]\s*\d+(?:\.\d+)?\s*(?:kg|g|mg|l|ml|pcs?|nos?|pairs?))?"
    r"|\d+(?:\.\d+)?\s*(?:pcs?|pieces?|nos?|units?|pairs?)"
    r"|\d+(?:\.\d+)?\s*N(?:\s*\(\s*\d+(?:\.\d+)?\s*"
    r"(?:pcs?|pieces?|nos?|units?|pairs?)\s*\))?"
    r")$",
    re.IGNORECASE,
)
_MRP_PATTERN = re.compile(r"^\d+(?:\.\d{1,2})?$")
_UNIT_SALE_PRICE_PATTERN = re.compile(r"(?:₹|rs\.?|inr)?\s*\d+(?:\.\d{1,2})?", re.IGNORECASE)
_UNIT_SALE_PRICE_PATTERN = re.compile(
    r"^\s*(?:â‚¹|₹|rs\.?|inr)\s*\d+(?:\.\d{1,2})?\s*"
    r"(?:/|\bper\b)\s*(g|kg|ml|l|cm|m|number)\s*$",
    re.IGNORECASE,
)
_MEASURED_QUANTITY_PATTERN = re.compile(
    r"^\d+(?:\.\d+)?\s*(?:kg|g|mg|l|ml|cl|m|cm|mm|m2|cm2)\b",
    re.IGNORECASE,
)
_COUNT_QUANTITY_PATTERN = re.compile(
    r"^(?:\d+(?:\.\d+)?\s*(?:pcs?|pieces?|nos?|units?|pairs?)|"
    r"\d+(?:\.\d+)?\s*N(?:\s*\(\s*\d+(?:\.\d+)?\s*"
    r"(?:pcs?|pieces?|nos?|units?|pairs?)\s*\))?)$",
    re.IGNORECASE,
)
_UNIT_SALE_PRICE_COMMENCEMENT = date(2022, 4, 1)
_MONTH_YEAR_VALUE_PATTERN = re.compile(r"^(0[1-9]|1[0-2])/(\d{2}|\d{4})$")
_NAMED_MONTH_YEAR_PATTERN = re.compile(r"^([A-Za-z]{3,9})\s+(\d{2}|\d{4})$")
_MONTH_NAMES = {
    name: number
    for number, name in enumerate(
        ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"),
        start=1,
    )
}
_MONTH_ABBREVIATIONS = {
    "jan": "january", "feb": "february", "mar": "march", "apr": "april",
    "jun": "june", "jul": "july", "aug": "august", "sep": "september",
    "sept": "september", "oct": "october", "nov": "november", "dec": "december",
}
_LEGAL_DATE_FIELDS = ("manufacture_date", "packing_date", "import_date")
_SEMANTIC_DATE_FIELDS = (*_LEGAL_DATE_FIELDS, "expiry_date", "best_before_date")
_MIN_DATE_YEAR = 2000
_MAX_DATE_YEAR = 2100
_CONSUMER_CONTACT_PATTERN = re.compile(
    r"\b(?:\+?\d[\d\s-]{7,}\d)\b|\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)


@dataclass(frozen=True)
class RuleDefinition:
    """Updateable legal metadata, deliberately separate from rule evaluators."""

    rule_id: str
    field: str
    title: str
    severity: str
    legal_basis: str
    source_url: str


@dataclass(frozen=True)
class ComplianceContext:
    """Facts about applicability that cannot safely be inferred from a value.

    Each value is deliberately tri-state: ``None`` means the scan did not
    contain reliable evidence to establish that fact.
    """

    imported: bool | None = None
    wholesale: bool | None = None
    unit_sale_price_applicable: bool | None = None
    size_relevant: bool | None = None


RULE_DEFINITIONS = (
    RuleDefinition("LMPC-R6-01", "product_name", "Common or generic name", "HIGH", "Rule 6", _OFFICIAL_RULE_6_SOURCE),
    RuleDefinition("LMPC-R6-02", "manufacturer_or_packer_or_importer", "Manufacturer, packer, or importer identification", "HIGH", "Rule 6", _OFFICIAL_RULE_6_SOURCE),
    RuleDefinition("LMPC-R6-03", "country_of_origin", "Country of origin for imported products", "HIGH", "Rule 6 (conditional for imports)", _OFFICIAL_RULE_6_SOURCE),
    RuleDefinition("LMPC-R6-04", "net_quantity", "Net quantity", "HIGH", "Rule 6", _OFFICIAL_RULE_6_SOURCE),
    RuleDefinition("LMPC-R6-05", "mrp", "Maximum Retail Price", "HIGH", "Rule 6", _OFFICIAL_RULE_6_SOURCE),
    RuleDefinition("LMPC-R6-06", "mrp_inclusive_of_taxes", "MRP inclusive of all taxes", "HIGH", "Rule 6", _OFFICIAL_RULE_6_SOURCE),
    RuleDefinition("LMPC-R6-07", "month_year", "Month and year of manufacture, pack, or import", "MEDIUM", "Rule 6", _OFFICIAL_RULE_6_SOURCE),
    RuleDefinition("LMPC-R6-08", "consumer_care", "Consumer care details", "MEDIUM", "Rule 6", _OFFICIAL_RULE_6_SOURCE),
    RuleDefinition("LMPC-R6-09", "unit_sale_price", "Unit sale price", "MEDIUM", "Rule 6(11), where applicable", _OFFICIAL_UNIT_SALE_PRICE_SOURCE),
    RuleDefinition("LMPC-R6-10", "size", "Relevant size or dimensions", "LOW", "Rule 6 (conditional where relevant)", _OFFICIAL_RULE_6_SOURCE),
)


def evaluate_compliance(
    declarations: Mapping[str, Any] | None,
    context: ComplianceContext | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate normalized declarations and return a predictable report.

    ``context`` holds tri-state applicability facts. Legacy context keys on
    ``declarations`` remain supported for callers that have not yet moved to
    the structured argument. A missing declaration only fails after its
    applicability is established.
    """
    data = declarations if isinstance(declarations, Mapping) else {}
    compliance_context = _resolve_context(data, context)
    evaluators: tuple[Callable[[Mapping[str, Any], RuleDefinition, ComplianceContext], dict[str, str]], ...] = (
        _check_product_name,
        _check_identification,
        _check_country_of_origin,
        _check_net_quantity,
        _check_mrp,
        _check_mrp_tax_inclusion,
        _check_month_year,
        _check_consumer_care,
        _check_unit_sale_price,
        _check_size,
    )

    checks = [
        evaluator(data, definition, compliance_context)
        for definition, evaluator in zip(RULE_DEFINITIONS, evaluators)
    ]
    violations = [check for check in checks if check["status"] == STATUS_FAIL]
    metrics = _verification_metrics(checks)

    if violations:
        overall_status = "NON_COMPLIANT"
    elif metrics["unable_to_verify_checks"]:
        overall_status = "UNABLE_TO_VERIFY"
    elif not metrics["total_applicable_checks"]:
        overall_status = STATUS_NOT_APPLICABLE
    else:
        overall_status = "COMPLIANT"

    return {
        "overall_status": overall_status,
        # Retained for existing consumers. It now explicitly means the score
        # among verified checks, never a percentage of legal compliance.
        "compliance_score": metrics["verified_compliance_score"],
        **metrics,
        "checks": checks,
        "violations": violations,
    }


def _verification_metrics(checks: list[Mapping[str, Any]]) -> dict[str, int | bool | None]:
    """Return unweighted, explainable verified-outcome and coverage metrics."""
    verified_checks = [check for check in checks if check["verification_status"] == "VERIFIED"]
    unable_to_verify_checks = [
        check for check in checks if check["verification_status"] == "UNABLE_TO_VERIFY"
    ]
    total_applicable_checks = len(verified_checks) + len(unable_to_verify_checks)
    passed_checks = sum(check["status"] == STATUS_PASS for check in verified_checks)
    failed_checks = sum(check["status"] == STATUS_FAIL for check in verified_checks)
    verified_compliance_score = (
        round((passed_checks / len(verified_checks)) * 100) if verified_checks else None
    )
    evidence_coverage = (
        round((len(verified_checks) / total_applicable_checks) * 100)
        if total_applicable_checks
        else None
    )
    return {
        "verified_compliance_score": verified_compliance_score,
        "evidence_coverage": evidence_coverage,
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "unable_to_verify_checks": len(unable_to_verify_checks),
        "total_applicable_checks": total_applicable_checks,
        "review_required": bool(unable_to_verify_checks),
    }


def _check_product_name(data: Mapping[str, Any], rule: RuleDefinition, _: ComplianceContext) -> dict[str, str]:
    return _presence_check(data.get("product_name"), rule, "Common or generic product name", _valid_text)


def _check_identification(data: Mapping[str, Any], rule: RuleDefinition, _: ComplianceContext) -> dict[str, str]:
    entities = ("manufacturer", "packer", "importer")
    detected = [entity for entity in entities if _has_value(data.get(entity))]
    if not detected:
        return _unable(rule, "Manufacturer, packer, or importer identification was not detected.")
    if any(not _valid_text(data[entity]) for entity in detected):
        return _fail(rule, "Detected manufacturer, packer, or importer identification is not usable.")
    if not any(_valid_text(data.get(f"{entity}_address")) for entity in detected):
        return _unable(rule, "An identifying name was detected, but its corresponding address was not detected.")
    return _pass(rule, "Manufacturer, packer, or importer name and address were detected.")


def _check_country_of_origin(data: Mapping[str, Any], rule: RuleDefinition, context: ComplianceContext) -> dict[str, str]:
    imported = context.imported
    value = data.get("country_of_origin")
    if imported is False:
        return _not_applicable(rule, "Country of origin is not required for a product identified as non-imported.")
    if imported is not True:
        return _unable(rule, "Whether the product is imported could not be determined from the normalized fields.")
    return _required_presence_check(value, rule, "Country of origin", _valid_text)


def _check_net_quantity(data: Mapping[str, Any], rule: RuleDefinition, _: ComplianceContext) -> dict[str, str]:
    return _presence_check(data.get("net_quantity"), rule, "Net quantity", _valid_net_quantity)


def _check_mrp(data: Mapping[str, Any], rule: RuleDefinition, _: ComplianceContext) -> dict[str, str]:
    return _presence_check(data.get("mrp"), rule, "MRP", _valid_mrp)


def _check_mrp_tax_inclusion(data: Mapping[str, Any], rule: RuleDefinition, _: ComplianceContext) -> dict[str, str]:
    evidence = data.get("mrp_inclusive_of_taxes")
    if evidence is True:
        return _pass(rule, "MRP is explicitly marked inclusive of all taxes.")
    if evidence is False:
        return _fail(rule, "MRP is explicitly marked as not inclusive of all taxes.")
    if isinstance(evidence, str) and re.search(
        r"(?:inclusive|incl\.?)\s+of\s+(?:all\s+)?tax", evidence, re.IGNORECASE
    ):
        return _pass(rule, "MRP text indicates inclusion of all taxes.")
    return _unable(rule, "Tax-inclusion wording was not available in the normalized OCR fields.")


def _check_month_year(data: Mapping[str, Any], rule: RuleDefinition, _: ComplianceContext) -> dict[str, str]:
    return _presence_check(
        _legal_month_year(data),
        rule,
        "Month and year of manufacture, packing, or import",
        _valid_month_year,
    )


def _check_consumer_care(data: Mapping[str, Any], rule: RuleDefinition, _: ComplianceContext) -> dict[str, str]:
    value = data.get("consumer_care")
    if not _has_value(value) or not _valid_consumer_care(value):
        return _unable(rule, "Usable consumer care contact details were not detected in the normalized OCR fields.")
    return _pass(rule, "Consumer care details were detected with a usable contact value.")


def _check_unit_sale_price(data: Mapping[str, Any], rule: RuleDefinition, context: ComplianceContext) -> dict[str, str]:
    applicable = _unit_sale_price_applicability(data, context)
    if applicable is False:
        return _not_applicable(rule, "Unit sale price is not applicable to the normalized quantity context.")
    if applicable is not True:
        return _unable(rule, "Unit-sale-price applicability is not available in the normalized fields.")
    value = data.get("unit_sale_price")
    if not _has_value(value):
        return _fail(rule, "Unit sale price is required for the normalized quantity context but was not detected.")
    if not _valid_unit_sale_price(value, data.get("net_quantity")):
        return _fail(rule, "Detected unit sale price has an invalid format.")
    return _pass(rule, "Unit sale price was detected with a usable format.")


def _unit_sale_price_applicability(data: Mapping[str, Any], context: ComplianceContext) -> bool | None:
    if context.wholesale is True:
        return False

    packaging_month = _month_year_as_date(_legal_month_year(data))
    if packaging_month is None:
        return None
    if packaging_month.year < _UNIT_SALE_PRICE_COMMENCEMENT.year:
        return False
    if packaging_month.year > _UNIT_SALE_PRICE_COMMENCEMENT.year:
        return context.unit_sale_price_applicable
    if packaging_month.month < _UNIT_SALE_PRICE_COMMENCEMENT.month:
        return False
    if packaging_month.month > _UNIT_SALE_PRICE_COMMENCEMENT.month:
        return context.unit_sale_price_applicable
    # A month-only declaration cannot establish whether an April 2022 package
    # was packed before the rule commenced on 1 April.
    return None


def _legal_month_year(data: Mapping[str, Any]) -> Any:
    """Return only a manufacture, packing, or import date for legal checks.

    Legacy payloads containing only ``month_year`` remain supported. Once a
    semantic date field is present, an expiry/best-before declaration cannot
    silently become the legal manufacture/packing/import date.
    """
    for field in _LEGAL_DATE_FIELDS:
        if field in data and data.get(field) is not None:
            return data.get(field)
    if any(field in data for field in _SEMANTIC_DATE_FIELDS):
        return None
    return data.get("month_year")


def _month_year_as_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    numeric = _MONTH_YEAR_VALUE_PATTERN.fullmatch(value.strip())
    if numeric:
        month, year = numeric.groups()
        resolved_year = int(year)
        if len(year) == 2:
            resolved_year += 2000
        return date(resolved_year, int(month), 1)
    named = _NAMED_MONTH_YEAR_PATTERN.fullmatch(value.strip())
    if not named:
        return None
    month_name, year = named.groups()
    month = _MONTH_NAMES.get(month_name.casefold())
    if month is None:
        full_name = _MONTH_ABBREVIATIONS.get(month_name.casefold())
        month = _MONTH_NAMES.get(full_name) if full_name else None
    if month is None:
        return None
    resolved_year = int(year)
    if len(year) == 2:
        resolved_year += 2000
    return date(resolved_year, month, 1)


def _check_size(data: Mapping[str, Any], rule: RuleDefinition, context: ComplianceContext) -> dict[str, str]:
    relevant = context.size_relevant
    if relevant is False:
        return _not_applicable(rule, "Size or dimensions are marked not relevant by upstream product context.")
    if relevant is not True and not _has_value(data.get("size")):
        return _unable(rule, "Size relevance could not be determined and no size declaration was detected.")
    return _required_presence_check(data.get("size"), rule, "Size or dimensions", _valid_text)


def _resolve_context(
    data: Mapping[str, Any], context: ComplianceContext | Mapping[str, Any] | None
) -> ComplianceContext:
    """Merge structured context with legacy inputs and direct importer evidence."""
    supplied = context if isinstance(context, Mapping) else {}

    def value(name: str, legacy_name: str) -> bool | None:
        candidate = (
            getattr(context, name)
            if isinstance(context, ComplianceContext)
            else supplied.get(name, supplied.get(legacy_name, data.get(legacy_name)))
        )
        return candidate if isinstance(candidate, bool) else None

    imported = value("imported", "is_imported")
    # An extracted importer declaration is explicit evidence of import status.
    if imported is None and _has_value(data.get("importer")):
        imported = True
    return ComplianceContext(
        imported=imported,
        wholesale=value("wholesale", "is_wholesale"),
        unit_sale_price_applicable=value("unit_sale_price_applicable", "unit_sale_price_applicable"),
        size_relevant=value("size_relevant", "size_relevant"),
    )


def _presence_check(
    value: Any,
    rule: RuleDefinition,
    label: str,
    validator: Callable[[Any], bool],
    *,
    conditional: bool = False,
) -> dict[str, str]:
    if not _has_value(value):
        qualifier = " when applicable" if conditional else ""
        return _unable(rule, f"{label}{qualifier} was not detected in the normalized OCR fields.")
    if not validator(value):
        return _fail(rule, f"Detected {label.lower()} has an invalid format.")
    return _pass(rule, f"{label} was detected with a usable format.")


def _required_presence_check(
    value: Any, rule: RuleDefinition, label: str, validator: Callable[[Any], bool]
) -> dict[str, str]:
    """Validate a declaration after context has established it is required."""
    if not _has_value(value):
        return _fail(rule, f"{label} is required by the established product context but was not detected.")
    if not validator(value):
        return _fail(rule, f"Detected {label.lower()} has an invalid format.")
    return _pass(rule, f"{label} was detected with a usable format.")


def _pass(rule: RuleDefinition, message: str) -> dict[str, str]:
    return _check(rule, STATUS_PASS, message, "EVIDENCE_DETECTED", "VERIFIED")


def _fail(rule: RuleDefinition, message: str) -> dict[str, str]:
    return _check(rule, STATUS_FAIL, message, "EVIDENCE_DETECTED", "VERIFIED")


def _unable(rule: RuleDefinition, message: str) -> dict[str, str]:
    return _check(rule, STATUS_NOT_APPLICABLE, message, "NOT_DETECTED", "UNABLE_TO_VERIFY")


def _not_applicable(rule: RuleDefinition, message: str) -> dict[str, str]:
    return _check(rule, STATUS_NOT_APPLICABLE, message, "NOT_REQUIRED", "NOT_APPLICABLE")


def _check(
    rule: RuleDefinition,
    status: str,
    message: str,
    evidence_status: str,
    verification_status: str,
) -> dict[str, str]:
    return {
        "rule_id": rule.rule_id,
        "field": rule.field,
        "status": status,
        "message": message,
        "severity": rule.severity,
        "evidence_status": evidence_status,
        "verification_status": verification_status,
    }


def _has_value(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_text(value: Any) -> bool:
    return _has_value(value) and bool(re.search(r"[A-Za-z0-9]", value))


def _valid_consumer_care(value: Any) -> bool:
    """Require a contact value, not merely a cue fragment or OCR residue."""
    return isinstance(value, str) and bool(_CONSUMER_CONTACT_PATTERN.search(value))


def _valid_net_quantity(value: Any) -> bool:
    return isinstance(value, str) and bool(_NET_QUANTITY_PATTERN.fullmatch(value.strip()))


def _valid_mrp(value: Any) -> bool:
    return isinstance(value, str) and bool(_MRP_PATTERN.fullmatch(value.replace(",", "").strip()))


def _valid_month_year(value: Any) -> bool:
    if not isinstance(value, str) or not _MONTH_YEAR_PATTERN.fullmatch(value.strip()):
        return False
    parsed = _month_year_as_date(value)
    return parsed is not None and _MIN_DATE_YEAR <= parsed.year <= _MAX_DATE_YEAR


def _valid_unit_sale_price(value: Any, net_quantity: Any) -> bool:
    if not isinstance(value, str):
        return False
    match = _UNIT_SALE_PRICE_PATTERN.fullmatch(value)
    if not match:
        return False
    expected_unit = _unit_sale_price_unit(net_quantity)
    return expected_unit is None or match.group(1).casefold() == expected_unit


def _unit_sale_price_unit(net_quantity: Any) -> str | None:
    if not isinstance(net_quantity, str):
        return None
    quantity = net_quantity.strip().casefold()
    if _COUNT_QUANTITY_PATTERN.fullmatch(quantity):
        return "number"
    unit_match = re.match(
        r"^\d+(?:\.\d+)?\s*(kg|g|mg|l|ml|cl|m|cm|mm|m2|cm2)\b",
        quantity,
    )
    if not unit_match:
        return None
    unit = unit_match.group(1)
    if unit in {"g", "mg"}:
        return "g"
    if unit == "kg":
        return "kg"
    if unit in {"ml", "cl"}:
        return "ml"
    if unit == "l":
        return "l"
    if unit in {"cm", "mm"}:
        return "cm"
    if unit == "m":
        return "m"
    return None
