import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from backend.app.services.ocr import extract_text


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
