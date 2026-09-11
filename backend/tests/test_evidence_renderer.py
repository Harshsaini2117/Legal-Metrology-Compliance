import tempfile
import unittest
from pathlib import Path

from PIL import Image

from backend.app.services.evidence_renderer import render_evidence_image


class EvidenceRendererTests(unittest.TestCase):
    def _source_image(self, directory: str) -> Path:
        source = Path(directory) / "label.png"
        Image.new("RGB", (160, 90), "white").save(source)
        return source

    def test_renders_ocr_and_failed_rule_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._source_image(directory)
            destination = Path(directory) / "evidence" / "label_evidence.png"
            result = render_evidence_image(
                source,
                [
                    {"text": "NET QUANTITY 500 g", "bounding_box": [[10, 30], [130, 30], [130, 55], [10, 55]]},
                    {"text": "MRP 99", "bounding_box": [[10, 60], [100, 60], [100, 80], [10, 80]]},
                ],
                {"checks": [{"rule_id": "LMPC-R6-04", "field": "net_quantity", "status": "FAIL"}]},
                {"net_quantity": "500 g", "mrp": "99"},
                destination,
            )

            self.assertEqual(result, destination)
            self.assertTrue(destination.is_file())
            rendered = Image.open(destination).convert("RGB")
            self.assertEqual(rendered.getpixel((10, 30)), (198, 40, 40))
            self.assertEqual(rendered.getpixel((10, 60)), (22, 119, 200))

    def test_rejects_missing_images_and_malformed_boxes(self):
        with self.assertRaisesRegex(FileNotFoundError, "does not exist"):
            render_evidence_image("not-a-real-image.png", [], {}, {})

        with tempfile.TemporaryDirectory() as directory:
            source = self._source_image(directory)
            with self.assertRaisesRegex(ValueError, "malformed bounding_box"):
                render_evidence_image(
                    source,
                    [{"text": "bad", "bounding_box": [[1, 2], [3, 4]]}],
                    {},
                    {},
                )

    def test_scales_preprocessed_ocr_coordinates_to_the_original_image(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._source_image(directory)
            coordinate_image = Path(directory) / "processed.png"
            Image.new("RGB", (80, 45), "white").save(coordinate_image)
            destination = Path(directory) / "scaled.png"
            render_evidence_image(
                source,
                [{"text": "text", "bounding_box": [[5, 15], [30, 15], [30, 25], [5, 25]]}],
                {},
                {},
                destination,
                coordinate_image,
            )
            self.assertEqual(Image.open(destination).convert("RGB").getpixel((10, 30)), (22, 119, 200))


if __name__ == "__main__":
    unittest.main()
