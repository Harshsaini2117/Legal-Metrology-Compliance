"""Additive frontend-ready views over existing scan pipeline results."""

from collections.abc import Mapping, Sequence
from typing import Any


def build_summary(compliance_report: Any) -> dict[str, int | str | None]:
    """Summarize existing rule results without changing their decisions."""
    report = compliance_report if isinstance(compliance_report, Mapping) else {}
    checks = _mappings(report.get("checks"))
    violations = _mappings(report.get("violations"))
    return {
        "overall_status": report.get("overall_status"),
        "compliance_score": report.get("compliance_score"),
        "total_checks": len(checks),
        "passed_checks": sum(check.get("status") == "PASS" for check in checks),
        "failed_checks": sum(check.get("status") == "FAIL" for check in checks),
        "unable_to_verify_checks": sum(
            check.get("verification_status") == "UNABLE_TO_VERIFY" for check in checks
        ),
        "violation_count": len(violations),
    }


def normalize_evidence(ocr_results: Any, extracted_fields: Any, compliance_report: Any) -> list[dict[str, Any]]:
    """Expose OCR evidence with only deterministic field and rule links."""
    fields = extracted_fields if isinstance(extracted_fields, Mapping) else {}
    report = compliance_report if isinstance(compliance_report, Mapping) else {}
    checks = _mappings(report.get("checks"))
    evidence: list[dict[str, Any]] = []

    for detection in _mappings(ocr_results):
        text = detection.get("text")
        if not isinstance(text, str):
            continue
        item = {
            "detected_text": text,
            "confidence": detection.get("confidence"),
            "bounding_box": detection.get("bounding_box"),
        }
        related_field = _related_field(text, fields)
        if related_field:
            item["related_field"] = related_field
            related_checks = [check for check in checks if check.get("field") == related_field]
            if len(related_checks) == 1 and isinstance(related_checks[0].get("rule_id"), str):
                item["related_check"] = related_checks[0]["rule_id"]
        evidence.append(item)
    return evidence


def attach_evidence_to_checks(
    compliance_report: Any, field_evidence: Any
) -> dict[str, Any]:
    """Add available field OCR evidence to compliance checks without re-evaluating rules."""
    report = dict(compliance_report) if isinstance(compliance_report, Mapping) else {}
    evidence_by_field = field_evidence if isinstance(field_evidence, Mapping) else {}
    checks = []

    for check in _mappings(report.get("checks")):
        enriched_check = dict(check)
        evidence = _check_evidence(enriched_check.get("field"), evidence_by_field)
        if evidence:
            enriched_check["ocr_evidence"] = evidence
        checks.append(enriched_check)

    report["checks"] = checks
    return report


def _check_evidence(field: Any, evidence_by_field: Mapping[str, Any]) -> list[dict[str, Any]]:
    if field == "manufacturer_or_packer_or_importer":
        fields = (
            "manufacturer", "manufacturer_address", "packer", "packer_address",
            "importer", "importer_address",
        )
    elif isinstance(field, str):
        fields = (field,)
    else:
        return []

    evidence: list[dict[str, Any]] = []
    for field_name in fields:
        entries = evidence_by_field.get(field_name)
        if isinstance(entries, Sequence) and not isinstance(entries, (str, bytes)):
            evidence.extend(entry for entry in entries if isinstance(entry, Mapping))
    return evidence


def _related_field(detected_text: str, fields: Mapping[str, Any]) -> str | None:
    normalized_text = detected_text.casefold()
    matches = [
        field_name
        for field_name, value in fields.items()
        if isinstance(field_name, str)
        and isinstance(value, str)
        and value.strip()
        and value.casefold() in normalized_text
    ]
    return matches[0] if len(matches) == 1 else None


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]
