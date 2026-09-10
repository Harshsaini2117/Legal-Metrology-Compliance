"""Evidence-aware Legal Metrology declaration checks for packaged commodities.

This MVP evaluates only normalized text fields. It cannot determine label
placement, font size, image completeness, or category-specific exemptions.
Accordingly, missing OCR evidence is reported as ``UNABLE_TO_VERIFY`` rather
than as a legal violation.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable


STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"

_OFFICIAL_RULE_6_SOURCE = (
    "https://consumeraffairs.nic.in/sites/default/files/file-uploads/latestnews/"
    "2023.01.18%20advisory%20for%20outer%20gift%20package%20declarations.pdf"
)
_OFFICIAL_UNIT_SALE_PRICE_SOURCE = (
    "https://consumeraffairs.nic.in/sites/default/files/file-uploads/latestnews/LM_FAQs.pdf"
)
_MONTH_YEAR_PATTERN = re.compile(
    r"^(?:0[1-9]|1[0-2])/(?:\d{2}|\d{4})$|^[A-Za-z]{3,9}\s+\d{2,4}$"
)
_NET_QUANTITY_PATTERN = re.compile(
    r"^\d+(?:\.\d+)?\s*(?:kg|g|mg|l|ml|cl|m|cm|mm|m2|cm2|pcs?|pieces?|nos?|units?)"
    r"(?:\s*[xX]\s*\d+(?:\.\d+)?\s*(?:kg|g|mg|l|ml|pcs?|nos?))?$",
    re.IGNORECASE,
)
_MRP_PATTERN = re.compile(r"^\d+(?:\.\d{1,2})?$")
_UNIT_SALE_PRICE_PATTERN = re.compile(r"(?:₹|rs\.?|inr)?\s*\d+(?:\.\d{1,2})?", re.IGNORECASE)


@dataclass(frozen=True)
class RuleDefinition:
    """Updateable legal metadata, deliberately separate from rule evaluators."""

    rule_id: str
    field: str
    title: str
    severity: str
    legal_basis: str
    source_url: str


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


def evaluate_compliance(declarations: Mapping[str, Any] | None) -> dict[str, Any]:
    """Evaluate normalized declarations and return a predictable report.

    Optional context keys let an upstream workflow state facts it knows but OCR
    alone cannot establish: ``is_imported``, ``mrp_inclusive_of_taxes``,
    ``unit_sale_price_applicable``, and ``size_relevant``. A present but invalid
    declaration fails; an absent declaration remains unable to verify.
    """
    data = declarations if isinstance(declarations, Mapping) else {}
    evaluators: tuple[Callable[[Mapping[str, Any], RuleDefinition], dict[str, str]], ...] = (
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

    checks = [evaluator(data, definition) for definition, evaluator in zip(RULE_DEFINITIONS, evaluators)]
    violations = [check for check in checks if check["status"] == STATUS_FAIL]
    verifiable_checks = [check for check in checks if check["status"] != STATUS_NOT_APPLICABLE]
    passed = sum(check["status"] == STATUS_PASS for check in verifiable_checks)
    score = round((passed / len(verifiable_checks)) * 100) if verifiable_checks else None

    if violations:
        overall_status = "NON_COMPLIANT"
    elif any(check["verification_status"] == "UNABLE_TO_VERIFY" for check in checks):
        overall_status = "UNABLE_TO_VERIFY"
    else:
        overall_status = "COMPLIANT"

    return {
        "overall_status": overall_status,
        "compliance_score": score,
        "checks": checks,
        "violations": violations,
    }


def _check_product_name(data: Mapping[str, Any], rule: RuleDefinition) -> dict[str, str]:
    return _presence_check(data.get("product_name"), rule, "Common or generic product name", _valid_text)


def _check_identification(data: Mapping[str, Any], rule: RuleDefinition) -> dict[str, str]:
    entities = ("manufacturer", "packer", "importer")
    detected = [entity for entity in entities if _has_value(data.get(entity))]
    if not detected:
        return _unable(rule, "Manufacturer, packer, or importer identification was not detected.")
    if any(not _valid_text(data[entity]) for entity in detected):
        return _fail(rule, "Detected manufacturer, packer, or importer identification is not usable.")
    if not any(_valid_text(data.get(f"{entity}_address")) for entity in detected):
        return _unable(rule, "An identifying name was detected, but its corresponding address was not detected.")
    return _pass(rule, "Manufacturer, packer, or importer name and address were detected.")


def _check_country_of_origin(data: Mapping[str, Any], rule: RuleDefinition) -> dict[str, str]:
    imported = data.get("is_imported") is True or _has_value(data.get("importer"))
    explicitly_not_imported = data.get("is_imported") is False
    value = data.get("country_of_origin")
    if explicitly_not_imported:
        return _not_applicable(rule, "Country of origin is not required for a product identified as non-imported.")
    if not imported:
        return _unable(rule, "Whether the product is imported could not be determined from the normalized fields.")
    return _presence_check(value, rule, "Country of origin", _valid_text, conditional=True)


def _check_net_quantity(data: Mapping[str, Any], rule: RuleDefinition) -> dict[str, str]:
    return _presence_check(data.get("net_quantity"), rule, "Net quantity", _valid_net_quantity)


def _check_mrp(data: Mapping[str, Any], rule: RuleDefinition) -> dict[str, str]:
    return _presence_check(data.get("mrp"), rule, "MRP", _valid_mrp)


def _check_mrp_tax_inclusion(data: Mapping[str, Any], rule: RuleDefinition) -> dict[str, str]:
    evidence = data.get("mrp_inclusive_of_taxes")
    if evidence is True:
        return _pass(rule, "MRP is explicitly marked inclusive of all taxes.")
    if evidence is False:
        return _fail(rule, "MRP is explicitly marked as not inclusive of all taxes.")
    if isinstance(data.get("mrp"), str) and re.search(r"inclusive\s+of\s+all\s+tax", data["mrp"], re.IGNORECASE):
        return _pass(rule, "MRP text indicates inclusion of all taxes.")
    return _unable(rule, "Tax-inclusion wording was not available in the normalized OCR fields.")


def _check_month_year(data: Mapping[str, Any], rule: RuleDefinition) -> dict[str, str]:
    return _presence_check(data.get("month_year"), rule, "Month and year declaration", _valid_month_year)


def _check_consumer_care(data: Mapping[str, Any], rule: RuleDefinition) -> dict[str, str]:
    if "consumer_care" not in data:
        return _unable(rule, "Consumer care details are not extracted by the current field schema.")
    return _presence_check(data.get("consumer_care"), rule, "Consumer care details", _valid_text)


def _check_unit_sale_price(data: Mapping[str, Any], rule: RuleDefinition) -> dict[str, str]:
    applicable = data.get("unit_sale_price_applicable")
    if applicable is False:
        return _not_applicable(rule, "Unit sale price is marked not applicable by upstream product context.")
    if applicable is not True:
        return _unable(rule, "Unit-sale-price applicability is not available in the normalized fields.")
    return _presence_check(data.get("unit_sale_price"), rule, "Unit sale price", _valid_unit_sale_price, conditional=True)


def _check_size(data: Mapping[str, Any], rule: RuleDefinition) -> dict[str, str]:
    relevant = data.get("size_relevant")
    if relevant is False:
        return _not_applicable(rule, "Size or dimensions are marked not relevant by upstream product context.")
    if relevant is not True and not _has_value(data.get("size")):
        return _unable(rule, "Size relevance could not be determined and no size declaration was detected.")
    return _presence_check(data.get("size"), rule, "Size or dimensions", _valid_text, conditional=True)


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


def _valid_net_quantity(value: Any) -> bool:
    return isinstance(value, str) and bool(_NET_QUANTITY_PATTERN.fullmatch(value.strip()))


def _valid_mrp(value: Any) -> bool:
    return isinstance(value, str) and bool(_MRP_PATTERN.fullmatch(value.replace(",", "").strip()))


def _valid_month_year(value: Any) -> bool:
    return isinstance(value, str) and bool(_MONTH_YEAR_PATTERN.fullmatch(value.strip()))


def _valid_unit_sale_price(value: Any) -> bool:
    return isinstance(value, str) and bool(_UNIT_SALE_PRICE_PATTERN.search(value))
