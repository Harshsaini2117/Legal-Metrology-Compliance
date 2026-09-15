import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from backend.app.services.field_extractor import extract_fields
from backend.app.services.ocr import _run_tesseract_ocr, extract_text


class FakePaddleOcr:
    def ocr(self, image, cls):
        assert cls is True
        assert image.ndim == 3
        return [
            [
                (
                    [[10, 20], [110, 20], [110, 50], [10, 50]],
                    ("NET QUANTITY 500 g", 0.98),
                )
            ]
        ]


class RetryPaddleOcr:
    def __init__(self):
        self.calls = 0

    def ocr(self, image, cls):
        self.calls += 1
        if self.calls == 1:
            return [[([[1, 1], [10, 1], [10, 5], [1, 5]], ("x", 0.20))]]
        return [[
            ([[1, 1], [40, 1], [40, 5], [1, 5]], ("Net Quantity 100 g", 0.95)),
            ([[1, 10], [40, 10], [40, 14], [1, 14]], ("MRP Rs 99", 0.94)),
            ([[1, 20], [40, 20], [40, 24], [1, 24]], ("Manufactured By", 0.92)),
            ([[1, 30], [40, 30], [40, 34], [1, 34]], ("Acme Foods", 0.92)),
        ]]


class SmallTextRetryPaddleOcr:
    def __init__(self):
        self.calls = 0

    def ocr(self, image, cls):
        self.calls += 1
        if self.calls == 1:
            return [[
                ([[10, 10], [180, 10], [180, 24], [10, 24]], ("Imported By: Example Imports", 0.96)),
                ([[10, 35], [120, 35], [120, 49], [10, 49]], ("MRP Rs 99", 0.95)),
                ([[10, 60], [170, 60], [170, 74], [10, 74]], ("Net Quantity 100 g", 0.95)),
                ([[10, 85], [180, 85], [180, 99], [10, 99]], ("Manufactured By: Example Foods", 0.94)),
            ]]
        return [[
            ([[10, 10], [180, 10], [180, 24], [10, 24]], ("Imported By: Example Imports", 0.96)),
            ([[12, 28], [190, 28], [190, 42], [12, 42]], ("3rd Floor, Market Road", 0.84)),
            ([[12, 48], [245, 48], [245, 62], [12, 62]], ("For consumer queries call 1800-891-2646", 0.87)),
            ([[12, 68], [130, 68], [130, 82], [12, 82]], ("Freshness guaranteed", 0.94)),
        ]]


class ExtractTextTests(unittest.TestCase):
    def test_tesseract_groups_native_word_tokens_into_extractable_lines(self):
        data = {
            "text": ["MRP:", "Rs.", "99", "(Incl.", "of", "all", "taxes)"],
            "conf": ["94", "95", "96", "93", "94", "95", "96"],
            "left": [10, 55, 95, 10, 60, 85, 115],
            "top": [20, 20, 20, 45, 45, 45, 45],
            "width": [38, 30, 22, 48, 18, 22, 48],
            "height": [14, 14, 14, 14, 14, 14, 14],
            "block_num": [1, 1, 1, 1, 1, 1, 1],
            "par_num": [1, 1, 1, 1, 1, 1, 1],
            "line_num": [1, 1, 1, 2, 2, 2, 2],
        }
        fake_tesseract = SimpleNamespace(
            Output=SimpleNamespace(DICT=object()),
            image_to_data=lambda image, config, output_type: data,
            pytesseract=SimpleNamespace(tesseract_cmd=None),
        )

        with patch.dict("sys.modules", {"pytesseract": fake_tesseract}):
            results = _run_tesseract_ocr(np.full((80, 180, 3), 255, dtype=np.uint8))

        self.assertEqual([item["text"] for item in results], ["MRP: Rs. 99", "(Incl. of all taxes)"])
        self.assertEqual(results[0]["bounding_box"], [[10.0, 20.0], [117.0, 20.0], [117.0, 34.0], [10.0, 34.0]])
        fields = extract_fields(results)
        self.assertEqual(fields["mrp"], "99")
        self.assertEqual(fields["mrp_inclusive_of_taxes"], "Incl. of all taxes")

    def test_tesseract_uses_one_sparse_lower_panel_retry_for_declaration_poor_output(self):
        primary = [
            {"text": "Everyday goodness", "confidence": 0.95, "bounding_box": None},
            {"text": "Roasted snack", "confidence": 0.94, "bounding_box": None},
            {"text": "Fresh and crunchy", "confidence": 0.93, "bounding_box": None},
            {"text": "Great taste", "confidence": 0.92, "bounding_box": None},
        ]
        retry = [
            {
                "text": "MRP: Rs. 99 (Incl. of all taxes)",
                "confidence": 0.94,
                "bounding_box": [[15, 10], [210, 10], [210, 25], [15, 25]],
            },
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            image_path = Path(temporary_directory) / "label.png"
            self.assertTrue(cv2.imwrite(str(image_path), np.full((100, 200, 3), 255, dtype=np.uint8)))
            with (
                patch.dict("os.environ", {"OCR_BACKEND": "tesseract"}, clear=False),
                patch("backend.app.services.ocr._run_selected_ocr", side_effect=[primary, retry]) as runner,
            ):
                results = extract_text(image_path)

        self.assertEqual(runner.call_count, 2)
        self.assertEqual(runner.call_args_list[1].kwargs["tesseract_psm"], 11)
        self.assertIn("MRP: Rs. 99 (Incl. of all taxes)", [item["text"] for item in results])

    def test_returns_text_confidence_and_bounding_box(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            image_path = Path(temporary_directory) / "label.png"
            image = np.full((100, 300, 3), 255, dtype=np.uint8)
            self.assertTrue(cv2.imwrite(str(image_path), image))

            with patch("backend.app.services.ocr._get_ocr_engine", return_value=FakePaddleOcr()):
                result = extract_text(image_path)

        self.assertEqual(
            result,
            [
                {
                    "text": "NET QUANTITY 500 g",
                    "confidence": 0.98,
                    "bounding_box": [[10, 20], [110, 20], [110, 50], [10, 50]],
                }
            ],
        )

    def test_rejects_unreadable_image_before_initializing_ocr(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            invalid_path = Path(temporary_directory) / "invalid.png"
            invalid_path.write_text("not image data", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Unable to read input image"):
                extract_text(invalid_path)

    def test_uses_a_better_retry_pass_without_merging_noisy_detections(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            image_path = Path(temporary_directory) / "label.png"
            self.assertTrue(cv2.imwrite(str(image_path), np.full((80, 160, 3), 255, dtype=np.uint8)))
            engine = RetryPaddleOcr()

            with patch("backend.app.services.ocr._get_ocr_engine", return_value=engine):
                result = extract_text(image_path)

        self.assertEqual(engine.calls, 2)
        self.assertEqual([item["text"] for item in result], ["Net Quantity 100 g", "MRP Rs 99", "Manufactured By", "Acme Foods"])
        self.assertNotIn("x", [item["text"] for item in result])

    def test_adds_only_meaningful_small_text_retry_declarations(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            image_path = Path(temporary_directory) / "label.png"
            self.assertTrue(cv2.imwrite(str(image_path), np.full((80, 160, 3), 255, dtype=np.uint8)))
            engine = SmallTextRetryPaddleOcr()

            with patch("backend.app.services.ocr._get_ocr_engine", return_value=engine):
                result = extract_text(image_path)

        self.assertEqual(engine.calls, 2)
        texts = [item["text"] for item in result]
        self.assertEqual(texts.count("Imported By: Example Imports"), 1)
        self.assertIn("3rd Floor, Market Road", texts)
        self.assertIn("For consumer queries call 1800-891-2646", texts)
        self.assertNotIn("Freshness guaranteed", texts)


if __name__ == "__main__":
    unittest.main()
