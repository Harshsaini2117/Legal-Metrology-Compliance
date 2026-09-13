import tempfile
import unittest
from pathlib import Path

from backend.app.services.report_generator import generate_compliance_report


class ReportGeneratorTests(unittest.TestCase):
    def test_generates_readable_pdf_with_scan_content(self):
        scan_result = {
            "input_image": "data/raw/coffee-label.jpg",
            "extracted_fields": {
                "product_name": "Instant Coffee",
                "mrp": "149.00",
                "net_quantity": "100 g",
                "manufacturer": "Example Foods Pvt Ltd",
                "manufacturer_address": "Bengaluru, Karnataka",
                "month_year": "03/2026",
            },
            "compliance_report": {
                "overall_status": "NON_COMPLIANT",
                "compliance_score": 75,
                "verified_compliance_score": 50,
                "evidence_coverage": 75,
                "unable_to_verify_checks": 1,
                "review_required": True,
                "checks": [
                    {"rule_id": "LMPC-R6-04", "field": "net_quantity", "status": "PASS", "message": "Net quantity was detected."},
                    {"rule_id": "LMPC-R6-05", "field": "mrp", "status": "FAIL", "message": "Detected MRP has an invalid format."},
                    {"rule_id": "LMPC-R6-09", "field": "unit_sale_price", "status": "NOT_APPLICABLE", "verification_status": "NOT_APPLICABLE", "message": "Unit sale price is not applicable."},
                    {"rule_id": "LMPC-R6-10", "field": "size", "status": "NOT_APPLICABLE", "verification_status": "UNABLE_TO_VERIFY", "message": "Size relevance could not be determined."},
                ],
                "violations": [
                    {"rule_id": "LMPC-R6-05", "field": "mrp", "message": "Detected MRP has an invalid format."}
                ],
            },
            "ocr_results": [{"text": "NET QUANTITY 100 g", "confidence": 0.98}],
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "reports" / "coffee-report.pdf"
            result = generate_compliance_report(scan_result, output_path)
            contents = result.read_bytes()

        self.assertEqual(result, output_path)
        self.assertTrue(contents.startswith(b"%PDF-"))
        self.assertGreater(len(contents), 1_000)
        for expected in (
            b"SIH26034 Legal Metrology Compliance Report",
            b"NON_COMPLIANT",
            b"Verified Compliance",
            b"Evidence Coverage",
            b"Review Required",
            b"Instant Coffee",
            b"NOT_APPLICABLE",
            b"UNABLE_TO_VERIFY",
            b"Disclaimer",
        ):
            self.assertIn(expected, contents)

    def test_missing_optional_fields_do_not_prevent_generation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "minimal.pdf"
            result = generate_compliance_report({"input_image": "product.png"}, output_path)

            self.assertTrue(result.is_file())
            self.assertGreater(result.stat().st_size, 0)

    def test_rejects_invalid_inputs_and_output_paths(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            with self.assertRaisesRegex(TypeError, "scan_result"):
                generate_compliance_report([], directory / "report.pdf")
            with self.assertRaisesRegex(ValueError, "end with"):
                generate_compliance_report({}, directory / "report.txt")
            with self.assertRaisesRegex(ValueError, "not a directory"):
                generate_compliance_report({}, directory)


if __name__ == "__main__":
    unittest.main()
