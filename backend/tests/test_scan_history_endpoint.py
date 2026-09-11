import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.main import app
from backend.app.services.scan_repository import ScanRepository


class ScanHistoryEndpointTests(unittest.IsolatedAsyncioTestCase):
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
        status = next(message["status"] for message in response if message["type"] == "http.response.start")
        body = b"".join(message.get("body", b"") for message in response if message["type"] == "http.response.body")
        return status, json.loads(body)

    async def test_lists_frontend_friendly_scan_summaries(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            reports_directory = Path(temporary_directory) / "reports"
            reports_directory.mkdir()
            report_path = reports_directory / "package.pdf"
            report_path.write_bytes(b"%PDF-1.4\n")
            repository = ScanRepository(Path(temporary_directory) / "scans.db")
            record = repository.create_scan(
                {
                    "processing_status": "COMPLETED",
                    "extracted_fields": {"net_quantity": "500 g"},
                    "compliance_report": {
                        "overall_status": "COMPLIANT",
                        "compliance_score": 100,
                        "violations": [{"rule_id": "LMPC-R6-05"}],
                    },
                    "report_path": str(report_path),
                    "report_filename": "package.pdf",
                },
                "package.png",
            )
            with (
                patch("backend.app.main.SCAN_REPOSITORY", repository),
                patch("backend.app.main.REPORT_DIR", reports_directory),
            ):
                list_status, listed = await self._get("/scans")

        self.assertEqual(list_status, 200)
        self.assertEqual(
            listed,
            [
                {
                    "scan_id": record["scan_id"],
                    "scan_timestamp": record["timestamp"],
                    "timestamp": record["timestamp"],
                    "original_filename": "package.png",
                    "processing_status": "COMPLETED",
                    "overall_status": "COMPLIANT",
                    "compliance_score": 100,
                    "violation_count": 1,
                    "report_available": True,
                    "report_filename": "package.pdf",
                    "report_url": f"/scans/{record['scan_id']}/report",
                }
            ],
        )
        self.assertNotIn("report_path", listed[0])

    async def test_returns_complete_persisted_scan_detail_without_filesystem_path(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = ScanRepository(Path(temporary_directory) / "scans.db")
            record = repository.create_scan(
                {
                    "processing_status": "COMPLETED",
                    "extracted_fields": {"net_quantity": "500 g"},
                    "compliance_report": {"overall_status": "COMPLIANT", "compliance_score": 100, "violations": []},
                },
                "package.png",
            )
            with patch("backend.app.main.SCAN_REPOSITORY", repository):
                get_status, retrieved = await self._get(f"/scans/{record['scan_id']}")

        self.assertEqual(get_status, 200)
        self.assertEqual(retrieved["scan_id"], record["scan_id"])
        self.assertEqual(retrieved["scan_timestamp"], record["timestamp"])
        self.assertEqual(retrieved["extracted_fields"], {"net_quantity": "500 g"})
        self.assertEqual(retrieved["compliance_report_summary"], record["compliance_report_summary"])
        self.assertEqual(retrieved["violations"], [])
        self.assertFalse(retrieved["report_available"])
        self.assertIsNone(retrieved["report_url"])
        self.assertNotIn("report_path", retrieved)

    async def test_returns_empty_history(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = ScanRepository(Path(temporary_directory) / "scans.db")
            with patch("backend.app.main.SCAN_REPOSITORY", repository):
                status, listed = await self._get("/scans")

        self.assertEqual(status, 200)
        self.assertEqual(listed, [])

    async def test_returns_404_for_unknown_scan_id(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = ScanRepository(Path(temporary_directory) / "scans.db")
            with patch("backend.app.main.SCAN_REPOSITORY", repository):
                missing_status, missing = await self._get("/scans/not-found")

        self.assertEqual(missing_status, 404)
        self.assertEqual(missing["detail"], "Scan history record not found.")


if __name__ == "__main__":
    unittest.main()
