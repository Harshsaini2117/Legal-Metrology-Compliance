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


if __name__ == "__main__":
    unittest.main()
