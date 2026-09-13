"""Orchestrates the image-to-compliance scan pipeline."""

from pathlib import Path
from typing import Any, Union

from .field_extractor import derive_compliance_context, extract_fields, map_field_evidence
from .evidence_renderer import render_evidence_image
from .ocr import extract_text
from .preprocessing import preprocess_image
from .rules_engine import ComplianceContext, evaluate_compliance
from .scan_response import attach_evidence_to_checks


PathLike = Union[str, Path]
_PROCESSED_DIR = Path(__file__).resolve().parents[3] / "data" / "processed"


class ScanProcessingError(RuntimeError):
    """Identifies the pipeline stage that prevented a scan from completing."""

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        super().__init__(f"{stage.capitalize()} stage failed: {message}")


def process_scan(
    input_image: PathLike,
    processed_output_path: PathLike | None = None,
) -> dict[str, Any]:
    """Run preprocessing, OCR, field extraction, and compliance checks in order.

    Args:
        input_image: Uploaded source image to scan.
        processed_output_path: Optional destination for the preprocessed image.
            If omitted, a PNG is created under ``data/processed``.

    Returns:
        A JSON-serializable result containing the input path, processed-image
        path, original OCR evidence, normalized fields, and compliance report.

    Raises:
        ScanProcessingError: If any pipeline stage fails. The ``stage``
            attribute identifies ``preprocessing``, ``ocr``,
            ``field_extraction``, ``rules_evaluation``, or
            ``evidence_rendering``.
    """
    source = Path(input_image)
    destination = Path(processed_output_path) if processed_output_path else _default_output_path(source)

    try:
        processed_image = preprocess_image(source, destination)
    except Exception as exc:
        raise ScanProcessingError("preprocessing", str(exc)) from exc

    try:
        ocr_results = extract_text(processed_image)
    except Exception as exc:
        raise ScanProcessingError("ocr", str(exc)) from exc

    try:
        extracted_fields = extract_fields(ocr_results)
        field_evidence = map_field_evidence(ocr_results, extracted_fields)
        compliance_context = ComplianceContext(
            **derive_compliance_context(ocr_results, extracted_fields)
        )
    except Exception as exc:
        raise ScanProcessingError("field_extraction", str(exc)) from exc

    try:
        compliance_report = evaluate_compliance(extracted_fields, compliance_context)
    except Exception as exc:
        raise ScanProcessingError("rules_evaluation", str(exc)) from exc

    try:
        evidence_image = render_evidence_image(
            source,
            ocr_results,
            compliance_report,
            extracted_fields,
            coordinate_image_path=processed_image,
        )
    except Exception as exc:
        raise ScanProcessingError("evidence_rendering", str(exc)) from exc

    compliance_report = attach_evidence_to_checks(compliance_report, field_evidence)

    return {
        "input_image": str(source),
        "processed_image": str(processed_image),
        "ocr_results": ocr_results,
        "extracted_fields": extracted_fields,
        "compliance_context": {
            "imported": compliance_context.imported,
            "wholesale": compliance_context.wholesale,
            "unit_sale_price_applicable": compliance_context.unit_sale_price_applicable,
            "size_relevant": compliance_context.size_relevant,
        },
        "field_evidence": field_evidence,
        "compliance_report": compliance_report,
        "evidence_image_path": str(evidence_image),
        "processing_status": "COMPLETED",
    }


def _default_output_path(source: Path) -> Path:
    return _PROCESSED_DIR / f"{source.stem}_processed.png"
