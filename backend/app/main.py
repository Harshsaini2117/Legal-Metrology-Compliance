from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from .runtime import configure_paddle_runtime

configure_paddle_runtime()

from .services.report_generator import generate_compliance_report
from .services.scan_repository import ScanRepository
from .services.scan_response import build_summary, normalize_evidence
from .services.scan_service import ScanProcessingError, process_scan


app = FastAPI(
    title="SIH26034 Compliance API",
    description="Packaged Commodity Legal Metrology Compliance System",
    version="0.2.0",
)


UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR = Path(__file__).resolve().parents[2] / "data" / "reports"
SCAN_REPOSITORY = ScanRepository(Path(__file__).resolve().parents[2] / "data" / "scans.db")

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "project": "SIH26034",
        "service": "compliance-api",
    }


@app.post("/scan/upload")
async def upload_product_image(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only JPEG, PNG, and WEBP images are allowed.",
        )

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Image size must be 10 MB or less.",
        )

    extension = Path(file.filename or "").suffix.lower()

    if not extension:
        extension = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }[file.content_type]

    stored_filename = f"{uuid4().hex}{extension}"
    output_path = UPLOAD_DIR / stored_filename

    output_path.write_bytes(contents)

    return {
        "status": "uploaded",
        "original_filename": file.filename,
        "stored_filename": stored_filename,
        "content_type": file.content_type,
        "size_bytes": len(contents),
        "message": "Product image uploaded successfully.",
    }


@app.get("/scans")
def list_scans(limit: int = Query(default=20, ge=1, le=100)):
    """Return recent completed scans, newest first."""
    return [_scan_history_summary(scan) for scan in SCAN_REPOSITORY.list_recent(limit)]


@app.get("/scans/{scan_id}")
def get_scan(scan_id: str):
    """Return a single persisted completed scan."""
    scan = SCAN_REPOSITORY.get_scan(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan history record not found.")
    return _scan_history_detail(scan)


@app.get("/scans/{scan_id}/report")
def download_scan_report(scan_id: str):
    """Download the PDF report associated with a persisted scan."""
    scan = SCAN_REPOSITORY.get_scan(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan history record not found.")

    resolved_report = _resolve_report_path(scan.get("report_path"))
    if resolved_report is None:
        raise HTTPException(status_code=404, detail="PDF report not found for this scan.")

    filename = Path(str(scan.get("report_filename") or resolved_report.name)).name
    return FileResponse(resolved_report, media_type="application/pdf", filename=filename)


def _scan_history_summary(scan: dict) -> dict:
    """Build the compact scan-history item consumed by the frontend."""
    compliance_summary = scan.get("compliance_report_summary")
    if not isinstance(compliance_summary, dict):
        compliance_summary = {}
    violations = scan.get("violations")
    report_url = _report_download_url(scan)

    return {
        "scan_id": scan.get("scan_id"),
        "scan_timestamp": scan.get("timestamp"),
        "timestamp": scan.get("timestamp"),
        "original_filename": scan.get("original_filename"),
        "processing_status": scan.get("processing_status"),
        "overall_status": compliance_summary.get("overall_status"),
        "compliance_score": compliance_summary.get("compliance_score"),
        "violation_count": len(violations) if isinstance(violations, list) else 0,
        "report_available": report_url is not None,
        "report_filename": scan.get("report_filename") if report_url else None,
        "report_url": report_url,
    }


def _scan_history_detail(scan: dict) -> dict:
    """Return all persisted scan data plus frontend-friendly summary fields."""
    detail = dict(scan)
    detail.update(_scan_history_summary(scan))
    detail.pop("report_path", None)
    return detail


def _report_download_url(scan: dict) -> str | None:
    if _resolve_report_path(scan.get("report_path")) is None:
        return None
    scan_id = scan.get("scan_id")
    return f"/scans/{scan_id}/report" if isinstance(scan_id, str) and scan_id else None


def _resolve_report_path(report_path: object) -> Path | None:
    """Return an existing report only when it remains inside ``REPORT_DIR``."""
    if not isinstance(report_path, str) or not report_path:
        return None
    try:
        resolved_report = Path(report_path).resolve(strict=True)
        resolved_report.relative_to(REPORT_DIR.resolve())
    except (OSError, ValueError):
        return None
    if not resolved_report.is_file() or resolved_report.suffix.lower() != ".pdf":
        return None
    return resolved_report


@app.post("/scan")
async def scan_product_image(file: UploadFile | None = File(default=None)):
    """Store one product image and run the existing scan-service pipeline."""
    if file is None:
        raise HTTPException(status_code=400, detail="A product image file is required.")

    saved_image = await _save_image(file)

    try:
        scan_result = process_scan(saved_image)
    except ScanProcessingError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Scan processing failed.",
                "stage": exc.stage,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"message": "Scan processing failed.", "stage": "unknown"},
        ) from exc

    scan_result["scan_id"] = uuid4().hex
    scan_result["summary"] = build_summary(scan_result.get("compliance_report"))
    scan_result["evidence"] = normalize_evidence(
        scan_result.get("ocr_results"),
        scan_result.get("extracted_fields"),
        scan_result.get("compliance_report"),
    )

    report_path = REPORT_DIR / f"{saved_image.stem}_compliance_report.pdf"
    try:
        generated_report = generate_compliance_report(scan_result, report_path)
    except Exception as exc:
        scan_result["report_generation_error"] = (
            f"Compliance report could not be generated: {exc}"
        )
    else:
        scan_result["report_path"] = str(generated_report)
        scan_result["report_filename"] = generated_report.name

    try:
        persisted_scan = SCAN_REPOSITORY.create_scan(
            scan_result, file.filename, scan_id=scan_result["scan_id"]
        )
    except Exception as exc:
        scan_result["persistence_error"] = f"Scan history could not be saved: {exc}"
    else:
        scan_result["scan_timestamp"] = persisted_scan["timestamp"]

    return scan_result


async def _save_image(file: UploadFile) -> Path:
    """Validate and store an upload without trusting its client-provided name."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only JPEG, PNG, and WEBP images are allowed.",
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded image is empty.")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Image size must be 10 MB or less.",
        )

    try:
        image = Image.open(BytesIO(contents))
        image_format = image.format
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is not a valid image.",
        ) from exc

    expected_format = {
        "image/jpeg": "JPEG",
        "image/png": "PNG",
        "image/webp": "WEBP",
    }[file.content_type]
    if image_format != expected_format:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file does not match its image content type.",
        )

    extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }[file.content_type]
    output_path = UPLOAD_DIR / f"{uuid4().hex}{extension}"
    output_path.write_bytes(contents)
    return output_path
