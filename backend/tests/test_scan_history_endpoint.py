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

    async def test_lists_and_retrieves_persisted_scans(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = ScanRepository(Path(temporary_directory) / "scans.db")
            record = repository.create_scan(
                {
                    "processing_status": "COMPLETED",
                    "extracted_fields": {"net_quantity": "500 g"},
                    "compliance_report": {"overall_status": "COMPLIANT", "compliance_score": 100, "violations": []},
                    "report_path": "data/reports/package.pdf",
                    "report_filename": "package.pdf",
                },
                "package.png",
            )
            with patch("backend.app.main.SCAN_REPOSITORY", repository):
                list_status, listed = await self._get("/scans")
                get_status, retrieved = await self._get(f"/scans/{record['scan_id']}")
                missing_status, missing = await self._get("/scans/not-found")

        self.assertEqual(list_status, 200)
        self.assertEqual(listed, [record])
        self.assertEqual(get_status, 200)
        self.assertEqual(retrieved, record)
        self.assertEqual(missing_status, 404)
        self.assertEqual(missing["detail"], "Scan history record not found.")


if __name__ == "__main__":
    unittest.main()
