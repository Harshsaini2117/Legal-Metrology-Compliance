import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.main import app
from backend.app.services.scan_repository import ScanRepository


class ScanReportEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def _get(self, path: str):
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
        response = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            response.append(message)

        await app(scope, receive, send)
        start = next(message for message in response if message["type"] == "http.response.start")
        body = b"".join(message.get("body", b"") for message in response if message["type"] == "http.response.body")
        headers = dict(start["headers"])
        return start["status"], headers, body

    @staticmethod
    def _scan_result(report_path: Path | None = None) -> dict:
        result = {
            "processing_status": "COMPLETED",
            "extracted_fields": {},
            "compliance_report": {"violations": []},
        }
        if report_path is not None:
            result["report_path"] = str(report_path)
            result["report_filename"] = report_path.name
        return result

    async def test_downloads_persisted_pdf_report(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            reports_directory = Path(temporary_directory) / "reports"
            reports_directory.mkdir()
            report_path = reports_directory / "package_compliance_report.pdf"
            report_contents = b"%PDF-1.4\nreport contents\n"
            report_path.write_bytes(report_contents)
            repository = ScanRepository(Path(temporary_directory) / "scans.db")
            record = repository.create_scan(self._scan_result(report_path), "package.png")

            with (
                patch("backend.app.main.SCAN_REPOSITORY", repository),
                patch("backend.app.main.REPORT_DIR", reports_directory),
            ):
                status, headers, body = await self._get(f"/scans/{record['scan_id']}/report")

        self.assertEqual(status, 200)
        self.assertEqual(body, report_contents)
        self.assertEqual(headers[b"content-type"], b"application/pdf")
        self.assertIn(b"package_compliance_report.pdf", headers[b"content-disposition"])

    async def test_returns_404_for_unknown_scan(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = ScanRepository(Path(temporary_directory) / "scans.db")
            with patch("backend.app.main.SCAN_REPOSITORY", repository):
                status, _, _ = await self._get("/scans/unknown/report")

        self.assertEqual(status, 404)

    async def test_returns_404_when_scan_has_no_report(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = ScanRepository(Path(temporary_directory) / "scans.db")
            record = repository.create_scan(self._scan_result(), "package.png")
            with patch("backend.app.main.SCAN_REPOSITORY", repository):
                status, _, _ = await self._get(f"/scans/{record['scan_id']}/report")

        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
