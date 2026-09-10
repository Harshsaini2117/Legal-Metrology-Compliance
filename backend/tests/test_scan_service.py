import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.services.scan_service import ScanProcessingError, process_scan


class ScanServiceTests(unittest.TestCase):
    def test_orchestrates_existing_services_and_preserves_ocr_evidence(self):
        input_image = Path("data/raw/product.jpg")
        processed_image = Path("data/processed/product_processed.png")
        ocr_results = [
            {
                "text": "NET QUANTITY 500 g",
                "confidence": 0.98,
                "bounding_box": [[10, 20], [200, 20], [200, 50], [10, 50]],
            }
        ]
        fields = {"product_name": None, "net_quantity": "500 g", "mrp": None}
        report = {"overall_status": "UNABLE_TO_VERIFY", "compliance_score": None, "checks": [], "violations": []}

        with (
            patch("backend.app.services.scan_service.preprocess_image", return_value=processed_image) as preprocess,
            patch("backend.app.services.scan_service.extract_text", return_value=ocr_results) as ocr,
            patch("backend.app.services.scan_service.extract_fields", return_value=fields) as extractor,
            patch("backend.app.services.scan_service.evaluate_compliance", return_value=report) as rules,
        ):
            result = process_scan(input_image, processed_image)

        preprocess.assert_called_once_with(input_image, processed_image)
        ocr.assert_called_once_with(processed_image)
        extractor.assert_called_once_with(ocr_results)
        rules.assert_called_once_with(fields)
        self.assertEqual(result["input_image"], str(input_image))
        self.assertEqual(result["processed_image"], str(processed_image))
        self.assertEqual(result["ocr_results"], ocr_results)
        self.assertEqual(result["extracted_fields"], fields)
        self.assertEqual(result["compliance_report"], report)
        self.assertEqual(result["processing_status"], "COMPLETED")

    def test_wraps_stage_failures_with_the_stage_name(self):
        with patch(
            "backend.app.services.scan_service.preprocess_image",
            side_effect=ValueError("Unable to read input image: data/raw/bad.png"),
        ) as preprocess:
            with self.assertRaises(ScanProcessingError) as context:
                process_scan("data/raw/bad.png", "data/processed/bad.png")

        self.assertEqual(context.exception.stage, "preprocessing")
        self.assertIn("Preprocessing stage failed", str(context.exception))
        self.assertIn("Unable to read input image", str(context.exception))
        preprocess.assert_called_once()


if __name__ == "__main__":
    unittest.main()
