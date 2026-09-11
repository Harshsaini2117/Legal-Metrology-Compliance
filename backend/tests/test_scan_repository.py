import tempfile
import unittest
from pathlib import Path

from backend.app.services.scan_repository import ScanRepository


class ScanRepositoryTests(unittest.TestCase):
    def test_persists_completed_scan_across_repository_instances(self):
        scan_result = {
            "input_image": "data/raw/tea.png",
            "processing_status": "COMPLETED",
            "extracted_fields": {"product_name": "Tea", "net_quantity": "100 g"},
            "compliance_report": {
                "overall_status": "NON_COMPLIANT",
                "compliance_score": 80,
                "violations": [{"rule_id": "LMPC-R6-05", "message": "MRP is invalid."}],
            },
            "report_path": "data/reports/tea_compliance_report.pdf",
            "report_filename": "tea_compliance_report.pdf",
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "history" / "scans.db"
            record = ScanRepository(database_path).create_scan(scan_result, "tea-label.png")
            reloaded = ScanRepository(database_path).get_scan(record["scan_id"])

        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["scan_id"], record["scan_id"])
        self.assertEqual(reloaded["original_filename"], "tea-label.png")
        self.assertEqual(reloaded["processing_status"], "COMPLETED")
        self.assertEqual(reloaded["extracted_fields"], scan_result["extracted_fields"])
        self.assertEqual(
            reloaded["compliance_report_summary"],
            {"overall_status": "NON_COMPLIANT", "compliance_score": 80},
        )
        self.assertEqual(reloaded["violations"], scan_result["compliance_report"]["violations"])
        self.assertEqual(reloaded["report_path"], scan_result["report_path"])
        self.assertEqual(reloaded["report_filename"], scan_result["report_filename"])

    def test_lists_most_recent_records(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = ScanRepository(Path(temporary_directory) / "scans.db")
            first = repository.create_scan({}, "first.png")
            second = repository.create_scan({}, "second.png")
            records = repository.list_recent(limit=1)

        self.assertEqual(records, [second])
        self.assertNotEqual(first["scan_id"], second["scan_id"])


if __name__ == "__main__":
    unittest.main()
