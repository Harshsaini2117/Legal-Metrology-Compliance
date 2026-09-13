import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from backend.app.services.preprocessing import MAX_IMAGE_DIMENSION, MIN_OCR_DIMENSION, preprocess_image


class PreprocessImageTests(unittest.TestCase):
    def test_preprocesses_large_image_without_destroying_ocr_detail(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "source.png"
            output_path = root / "processed" / "document.png"

            image = np.full((1_200, 2_400, 3), 225, dtype=np.uint8)
            cv2.putText(
                image,
                "NET QUANTITY 500 g",
                (120, 600),
                cv2.FONT_HERSHEY_SIMPLEX,
                2,
                (25, 25, 25),
                4,
                cv2.LINE_AA,
            )
            self.assertTrue(cv2.imwrite(str(input_path), image))

            result = preprocess_image(input_path, output_path)
            processed = cv2.imread(str(output_path), cv2.IMREAD_UNCHANGED)

            self.assertEqual(result, output_path)
            self.assertTrue(output_path.is_file())
            self.assertEqual(processed.ndim, 3)
            self.assertEqual(processed.shape[2], 3)
            self.assertLessEqual(max(processed.shape), MAX_IMAGE_DIMENSION)
            self.assertGreater(len(np.unique(processed)), 2)

    def test_rejects_unreadable_image(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            invalid_path = Path(temporary_directory) / "not-an-image.png"
            invalid_path.write_text("not image data", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Unable to read input image"):
                preprocess_image(invalid_path, Path(temporary_directory) / "output.png")

    def test_upscales_small_colour_label_without_converting_it_to_binary(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "small-label.png"
            output_path = root / "processed.png"
            image = np.zeros((200, 300, 3), dtype=np.uint8)
            image[:, :, 1] = 140
            image[:, :, 2] = 220
            cv2.putText(image, "MRP 99", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
            self.assertTrue(cv2.imwrite(str(input_path), image))

            preprocess_image(input_path, output_path)
            processed = cv2.imread(str(output_path), cv2.IMREAD_COLOR)

            self.assertGreaterEqual(max(processed.shape[:2]), MIN_OCR_DIMENSION)
            self.assertEqual(processed.shape[2], 3)
            self.assertGreater(len(np.unique(processed.reshape(-1, 3), axis=0)), 8)


if __name__ == "__main__":
    unittest.main()
