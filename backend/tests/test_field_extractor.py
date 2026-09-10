import unittest

from backend.app.services.field_extractor import FIELD_NAMES, extract_fields


class FieldExtractorTests(unittest.TestCase):
    def test_extracts_normalized_fields_from_product_label_ocr(self):
        ocr_results = [
            {"text": "NATUREFRESH HERBAL TEA", "confidence": 0.99, "bounding_box": None},
            {"text": "Net Qty: 100 GMS", "confidence": 0.98, "bounding_box": None},
            {"text": "M.R.P.: Rs. 299/- (Inclusive of all taxes)", "confidence": 0.97, "bounding_box": None},
            {"text": "Manufactured & Marketed by:", "confidence": 0.96, "bounding_box": None},
            {"text": "NatureFresh Foods Pvt. Ltd.", "confidence": 0.96, "bounding_box": None},
            {"text": "Plot 12, Sector 4, New Delhi - 110020, India", "confidence": 0.95, "bounding_box": None},
            {"text": "Imported & Marketed by: Global Imports LLP", "confidence": 0.94, "bounding_box": None},
            {"text": "Warehouse 7, Mumbai - 400001, India", "confidence": 0.94, "bounding_box": None},
            {"text": "Packed by: NatureFresh Packaging", "confidence": 0.93, "bounding_box": None},
            {"text": "Unit 3, Noida - 201301, India", "confidence": 0.93, "bounding_box": None},
            {"text": "Month & Year of Import: 06-2025", "confidence": 0.92, "bounding_box": None},
            {"text": "Made in India", "confidence": 0.92, "bounding_box": None},
            {"text": "Size: 250 ml", "confidence": 0.91, "bounding_box": None},
        ]

        self.assertEqual(
            extract_fields(ocr_results),
            {
                "product_name": "NATUREFRESH HERBAL TEA",
                "mrp": "299",
                "net_quantity": "100 g",
                "manufacturer": "NatureFresh Foods Pvt. Ltd.",
                "manufacturer_address": "Plot 12, Sector 4, New Delhi - 110020, India",
                "importer": "Global Imports LLP",
                "importer_address": "Warehouse 7, Mumbai - 400001, India",
                "packer": "NatureFresh Packaging",
                "packer_address": "Unit 3, Noida - 201301, India",
                "month_year": "06/2025",
                "country_of_origin": "India",
                "size": "250 ml",
            },
        )

    def test_handles_sample_style_net_quantity_and_missing_fields(self):
        fields = extract_fields(
            [{"text": "NET QUANTITY 500 g", "confidence": 0.98, "bounding_box": None}]
        )

        self.assertEqual(tuple(fields), FIELD_NAMES)
        self.assertEqual(fields["net_quantity"], "500 g")
        self.assertTrue(all(value is None for key, value in fields.items() if key != "net_quantity"))

    def test_ignores_malformed_ocr_entries(self):
        self.assertEqual(extract_fields([{}, {"text": None}, "not an OCR result"]), {field: None for field in FIELD_NAMES})


if __name__ == "__main__":
    unittest.main()
