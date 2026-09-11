import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.main import app
from backend.app.services.scan_repository import ScanRepository
from backend.app.services.scan_service import ScanProcessingError


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N"
    "70a4AAAAAElFTkSuQmCC"
)


class ScanEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def _post_scan(self, filename: str | None = None, content: bytes = b"", content_type: str = "image/png"):
        boundary = "scan-test-boundary"
        body = b""
        if filename is not None:
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode() + content + f"\r\n--{boundary}--\r\n".encode()

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/scan",
            "raw_path": b"/scan",
            "query_string": b"",
            "headers": [
                (b"content-type", f"multipart/form-data; boundary={boundary}".encode()),
                (b"content-length", str(len(body)).encode()),
            ],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
        response = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            response.append(message)

        await app(scope, receive, send)
        status = next(message["status"] for message in response if message["type"] == "http.response.start")
        response_body = b"".join(
            message.get("body", b"") for message in response if message["type"] == "http.response.body"
        )
        return status, json.loads(response_body)

    async def test_scan_stores_image_and_returns_scan_service_result(self):
        scan_result = {
            "input_image": "data/raw/generated.png",
            "processed_image": "data/processed/generated_processed.png",
            "ocr_results": [{"text": "NET QUANTITY 500 g", "confidence": 0.99}],
            "extracted_fields": {"net_quantity": "500 g"},
            "compliance_report": {"overall_status": "COMPLIANT", "checks": []},
            "processing_status": "COMPLETED",
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            upload_dir = Path(temporary_directory)
            report_dir = Path(temporary_directory) / "reports"
            generated_report = report_dir / "generated_compliance_report.pdf"
            repository = ScanRepository(Path(temporary_directory) / "scans.db")
            with (
                patch("backend.app.main.UPLOAD_DIR", upload_dir),
                patch("backend.app.main.REPORT_DIR", report_dir),
                patch("backend.app.main.SCAN_REPOSITORY", repository),
                patch("backend.app.main.process_scan", return_value=scan_result) as process_scan,
                patch(
                    "backend.app.main.generate_compliance_report", return_value=generated_report
                ) as generate_report,
            ):
                status, response = await self._post_scan("product.png", PNG_BYTES)

            self.assertEqual(status, 200)
            self.assertEqual(response["input_image"], scan_result["input_image"])
            self.assertEqual(response["processed_image"], scan_result["processed_image"])
            self.assertEqual(response["ocr_results"], scan_result["ocr_results"])
            self.assertEqual(response["extracted_fields"], scan_result["extracted_fields"])
            self.assertEqual(response["compliance_report"], scan_result["compliance_report"])
            self.assertEqual(response["processing_status"], scan_result["processing_status"])
            self.assertEqual(response["report_path"], str(generated_report))
            self.assertEqual(response["report_filename"], generated_report.name)
            self.assertIn("scan_id", response)
            self.assertIn("scan_timestamp", response)
            saved_files = list(upload_dir.glob("*.png"))
            self.assertEqual(len(saved_files), 1)
            self.assertEqual(saved_files[0].read_bytes(), PNG_BYTES)
            process_scan.assert_called_once_with(saved_files[0])
            generate_report.assert_called_once_with(
                scan_result,
                report_dir / f"{saved_files[0].stem}_compliance_report.pdf",
            )
            persisted = repository.get_scan(response["scan_id"])
            self.assertEqual(persisted["original_filename"], "product.png")
            self.assertEqual(persisted["report_filename"], generated_report.name)

    async def test_scan_returns_result_when_report_generation_fails(self):
        scan_result = {
            "input_image": "data/raw/generated.png",
            "processed_image": "data/processed/generated_processed.png",
            "ocr_results": [],
            "extracted_fields": {"net_quantity": "500 g"},
            "compliance_report": {"overall_status": "UNABLE_TO_VERIFY", "checks": []},
            "processing_status": "COMPLETED",
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            with (
                patch("backend.app.main.UPLOAD_DIR", Path(temporary_directory)),
                patch("backend.app.main.REPORT_DIR", Path(temporary_directory) / "reports"),
                patch("backend.app.main.SCAN_REPOSITORY", ScanRepository(Path(temporary_directory) / "scans.db")),
                patch("backend.app.main.process_scan", return_value=scan_result),
                patch(
                    "backend.app.main.generate_compliance_report",
                    side_effect=OSError("disk unavailable"),
                ),
            ):
                status, response = await self._post_scan("product.png", PNG_BYTES)

        self.assertEqual(status, 200)
        self.assertEqual(response["input_image"], scan_result["input_image"])
        self.assertEqual(response["compliance_report"], scan_result["compliance_report"])
        self.assertEqual(response["processing_status"], "COMPLETED")
        self.assertNotIn("report_path", response)
        self.assertIn("Compliance report could not be generated: disk unavailable", response["report_generation_error"])

    async def test_scan_rejects_non_image_upload(self):
        status, response = await self._post_scan("not-an-image.png", b"not an image")

        self.assertEqual(status, 400)
        self.assertEqual(response["detail"], "The uploaded file is not a valid image.")

    async def test_scan_rejects_unsupported_file_type(self):
        status, response = await self._post_scan(
            "product.pdf", b"%PDF-1.7", "application/pdf"
        )

        self.assertEqual(status, 400)
        self.assertEqual(response["detail"], "Only JPEG, PNG, and WEBP images are allowed.")

    async def test_scan_requires_a_file(self):
        status, response = await self._post_scan()

        self.assertEqual(status, 400)
        self.assertEqual(response["detail"], "A product image file is required.")

    async def test_scan_reports_pipeline_stage_failure(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with (
                patch("backend.app.main.UPLOAD_DIR", Path(temporary_directory)),
                patch(
                    "backend.app.main.process_scan",
                    side_effect=ScanProcessingError("ocr", "unavailable"),
                ),
            ):
                status, response = await self._post_scan("product.png", PNG_BYTES)

        self.assertEqual(status, 500)
        self.assertEqual(
            response["detail"],
            {"message": "Scan processing failed.", "stage": "ocr"},
        )


if __name__ == "__main__":
    unittest.main()
