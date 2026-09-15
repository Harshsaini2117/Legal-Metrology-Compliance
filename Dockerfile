FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OCR_BACKEND=tesseract \
    TESSERACT_CMD=/usr/bin/tesseract

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.production.txt backend/requirements.production.txt
RUN pip install --no-cache-dir -r backend/requirements.production.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
