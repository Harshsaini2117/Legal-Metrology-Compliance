from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile


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