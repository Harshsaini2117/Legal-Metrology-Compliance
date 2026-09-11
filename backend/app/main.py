from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from .services.scan_service import ScanProcessingError, process_scan


app = FastAPI(
    title="SIH26034 Compliance API",
    description="Packaged Commodity Legal Metrology Compliance System",
    version="0.2.0",
)


UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

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


@app.post("/scan")
async def scan_product_image(file: UploadFile | None = File(default=None)):
    """Store one product image and run the existing scan-service pipeline."""
    if file is None:
        raise HTTPException(status_code=400, detail="A product image file is required.")

    saved_image = await _save_image(file)

    try:
        return process_scan(saved_image)
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
