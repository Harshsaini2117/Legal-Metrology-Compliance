"""PDF compliance-report generation for completed SIH26034 scans."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from html import escape
from os import PathLike
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


_PROJECT_TITLE = "SIH26034 Legal Metrology Compliance Report"
_DISCLAIMER = (
    "Disclaimer: This report is an automated screening and assessment based on OCR-extracted label "
    "information and deterministic checks. It is not a final legal determination or legal advice."
)
_PREFERRED_FIELDS = (
    ("product_name", "Product Name"),
    ("mrp", "MRP"),
    ("net_quantity", "Net Quantity"),
    ("manufacturer", "Manufacturer"),
    ("manufacturer_address", "Manufacturer Address"),
    ("packer", "Packer"),
    ("packer_address", "Packer Address"),
    ("importer", "Importer"),
    ("importer_address", "Importer Address"),
    ("country_of_origin", "Country of Origin"),
    ("month_year", "Manufacture / Pack / Import Date"),
    ("size", "Size / Dimensions"),
)
_STATUS_COLORS = {
    "PASS": colors.HexColor("#1B5E20"),
    "FAIL": colors.HexColor("#B71C1C"),
    "NOT_APPLICABLE": colors.HexColor("#455A64"),
    "UNABLE_TO_VERIFY": colors.HexColor("#8A5A00"),
}


def generate_compliance_report(scan_result: Mapping[str, Any], output_path: str | PathLike[str]) -> Path:
    """Create a PDF summary from the existing ``scan_service.process_scan`` result.

    Args:
        scan_result: JSON-serializable result returned by ``process_scan``.
        output_path: Destination filename ending in ``.pdf``.

    Returns:
        The written PDF path.

    Raises:
        TypeError: If ``scan_result`` is not a mapping or ``output_path`` is not path-like.
        ValueError: If the destination is not a PDF file or names a directory.
        OSError: If its parent directory cannot be created or the report cannot be written.
    """
    if not isinstance(scan_result, Mapping):
        raise TypeError("scan_result must be a mapping returned by the scan pipeline.")
    if not isinstance(output_path, (str, PathLike)):
        raise TypeError("output_path must be a path-like PDF destination.")

    destination = Path(output_path)
    if destination.exists() and destination.is_dir():
        raise ValueError("output_path must identify a PDF file, not a directory.")
    if destination.suffix.lower() != ".pdf":
        raise ValueError("output_path must end with '.pdf'.")

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"Unable to create report directory: {destination.parent}") from exc

    try:
        _build_report(scan_result, destination)
    except OSError as exc:
        raise OSError(f"Unable to write compliance report: {destination}") from exc

    if not destination.is_file() or destination.stat().st_size == 0:
        raise OSError(f"Compliance report was not created: {destination}")
    return destination


def _build_report(scan_result: Mapping[str, Any], destination: Path) -> None:
    styles = _styles()
    fields = _mapping(scan_result.get("extracted_fields"))
    compliance = _mapping(scan_result.get("compliance_report"))
    document = SimpleDocTemplate(
        str(destination),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=_PROJECT_TITLE,
        author="SIH26034",
        pageCompression=0,
    )

    story: list[Any] = [Paragraph(_PROJECT_TITLE, styles["title"])]
    story.append(Spacer(1, 5 * mm))
    story.append(_summary_table(scan_result, compliance, styles))
    story.append(Spacer(1, 5 * mm))
    story.extend(_section("Extracted Fields", _fields_table(fields, styles), styles))
    story.extend(_section("Compliance Checks", _checks_table(compliance.get("checks"), styles), styles))
    story.extend(_section("Violations", _violations_table(compliance.get("violations"), styles), styles))
    story.extend(_section("OCR Evidence Summary", _ocr_evidence(scan_result.get("ocr_results"), styles), styles))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(_escape(_DISCLAIMER), styles["disclaimer"]))
    document.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle", parent=base["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#0D3559"), leading=24
        ),
        "heading": ParagraphStyle("ReportHeading", parent=base["Heading2"], textColor=colors.HexColor("#0D3559"), spaceBefore=10, spaceAfter=5),
        "body": ParagraphStyle("ReportBody", parent=base["BodyText"], fontSize=8.5, leading=11),
        "small": ParagraphStyle("ReportSmall", parent=base["BodyText"], fontSize=7.5, leading=9),
        "header": ParagraphStyle("ReportHeader", parent=base["BodyText"], fontSize=7.5, leading=9, textColor=colors.white),
        "disclaimer": ParagraphStyle("ReportDisclaimer", parent=base["BodyText"], fontSize=8, leading=10, textColor=colors.HexColor("#5A4A00")),
    }


def _summary_table(scan_result: Mapping[str, Any], compliance: Mapping[str, Any], styles: Mapping[str, ParagraphStyle]) -> Table:
    input_image = scan_result.get("input_image")
    filename = Path(str(input_image)).name if input_image else "Not available"
    verified_score = compliance.get("verified_compliance_score", compliance.get("compliance_score"))
    coverage = compliance.get("evidence_coverage")
    checks = _mappings(compliance.get("checks"))
    unresolved = compliance.get("unable_to_verify_checks")
    if not isinstance(unresolved, int):
        unresolved = sum(
            check.get("verification_status") == "UNABLE_TO_VERIFY" for check in checks
        )
    if coverage is None and checks:
        verified = sum(check.get("verification_status", "VERIFIED") == "VERIFIED" for check in checks)
        applicable = verified + unresolved
        coverage = round((verified / applicable) * 100) if applicable else None
    verified_score_text = f"{verified_score}%" if verified_score is not None else "Not available"
    coverage_text = f"{coverage}%" if coverage is not None else "Not available"
    status = _text(compliance.get("overall_status"), "UNABLE_TO_VERIFY")
    rows = [
        ["Scan Date / Time", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")],
        ["Input Image", filename],
        ["Overall Compliance Status", status],
        ["Verified Compliance", verified_score_text],
        ["Evidence Coverage", coverage_text],
    ]
    if compliance.get("review_required") or unresolved:
        rows.append(["Review Required", f"{unresolved} checks could not be verified"])
    return _table(rows, [42 * mm, 128 * mm], styles, header=None)


def _fields_table(fields: Mapping[str, Any], styles: Mapping[str, ParagraphStyle]) -> Table:
    preferred_names = {name for name, _ in _PREFERRED_FIELDS}
    rows = [(label, _display_value(fields.get(name))) for name, label in _PREFERRED_FIELDS if _has_value(fields.get(name))]
    rows.extend((_humanize(name), _display_value(value)) for name, value in fields.items() if name not in preferred_names and _has_value(value))
    if not rows:
        rows = [("Extracted Fields", "No normalized field values were available.")]
    return _table(rows, [58 * mm, 112 * mm], styles, header=None)


def _checks_table(raw_checks: Any, styles: Mapping[str, ParagraphStyle]) -> Table:
    rows = [["Rule / Check", "Status", "Explanation"]]
    for check in _mappings(raw_checks):
        status = _check_status(check)
        label = " - ".join(part for part in (_text(check.get("rule_id")), _humanize(_text(check.get("field")))) if part)
        rows.append([label or "Compliance check", status, _text(check.get("message"), "No explanation available.")])
    if len(rows) == 1:
        rows.append(["No compliance checks", "UNABLE_TO_VERIFY", "No rule-evaluation data was available."])
    return _table(rows, [48 * mm, 31 * mm, 91 * mm], styles, header=rows[0])


def _violations_table(raw_violations: Any, styles: Mapping[str, ParagraphStyle]) -> Table:
    rows = [["Rule / Check", "Explanation"]]
    for violation in _mappings(raw_violations):
        label = " - ".join(part for part in (_text(violation.get("rule_id")), _humanize(_text(violation.get("field")))) if part)
        rows.append([label or "Violation", _text(violation.get("message"), "No explanation available.")])
    if len(rows) == 1:
        rows.append(["No violations reported", "No failed compliance checks were reported in this assessment."])
    return _table(rows, [55 * mm, 115 * mm], styles, header=rows[0])


def _ocr_evidence(raw_results: Any, styles: Mapping[str, ParagraphStyle]) -> list[Any]:
    evidence = _mappings(raw_results)
    summary = [Paragraph(f"OCR detections recorded: <b>{len(evidence)}</b>", styles["body"])]
    if not evidence:
        summary.append(Paragraph("No OCR evidence was available in the scan result.", styles["body"]))
        return summary

    rows = [["Text", "Confidence"]]
    for item in evidence[:10]:
        confidence = item.get("confidence")
        confidence_text = f"{float(confidence):.2%}" if isinstance(confidence, (int, float)) else "Not available"
        rows.append([_text(item.get("text"), "[No text]"), confidence_text])
    summary.append(Spacer(1, 2 * mm))
    summary.append(_table(rows, [130 * mm, 40 * mm], styles, header=rows[0]))
    if len(evidence) > 10:
        summary.append(Paragraph(f"Only the first 10 of {len(evidence)} OCR detections are shown.", styles["small"]))
    return summary


def _section(title: str, content: Any, styles: Mapping[str, ParagraphStyle]) -> list[Any]:
    items = [Paragraph(title, styles["heading"])]
    if isinstance(content, list):
        items.extend(content)
    else:
        items.append(content)
    return items


def _table(rows: Sequence[Sequence[Any]], widths: list[float], styles: Mapping[str, ParagraphStyle], header: Sequence[Any] | None) -> Table:
    rendered_rows = [
        [Paragraph(_escape(str(value)), styles["header"] if header and row_index == 0 else styles["small"]) for value in row]
        for row_index, row in enumerate(rows)
    ]
    table = Table(rendered_rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C7D3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        commands.extend(
            [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0D3559")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
        )
    table.setStyle(TableStyle(commands))
    return table


def _page_footer(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#607D8B"))
    canvas.drawString(document.leftMargin, 11 * mm, "SIH26034 - Automated Legal Metrology Screening")
    canvas.drawRightString(A4[0] - document.rightMargin, 11 * mm, f"Page {document.page}")
    canvas.restoreState()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _check_status(check: Mapping[str, Any]) -> str:
    if check.get("verification_status") == "UNABLE_TO_VERIFY":
        return "UNABLE_TO_VERIFY"
    status = _text(check.get("status"), "UNABLE_TO_VERIFY")
    return status if status in _STATUS_COLORS else "UNABLE_TO_VERIFY"


def _text(value: Any, default: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _has_value(value: Any) -> bool:
    return value is not None and value != ""


def _display_value(value: Any) -> str:
    return str(value) if not isinstance(value, bool) else ("Yes" if value else "No")


def _humanize(value: str) -> str:
    return value.replace("_", " ").title() if value else ""


def _escape(value: str) -> str:
    return escape(value).replace("\n", "<br/>")
