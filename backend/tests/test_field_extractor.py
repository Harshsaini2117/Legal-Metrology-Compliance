import unittest

from backend.app.services.field_extractor import FIELD_NAMES, extract_fields, map_field_evidence


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
                "mrp_inclusive_of_taxes": "Inclusive of all taxes",
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
                "consumer_care": None,
            },
        )

    def test_handles_sample_style_net_quantity_and_missing_fields(self):
        fields = extract_fields(
            [{"text": "NET QUANTITY 500 g", "confidence": 0.98, "bounding_box": None}]
        )

        self.assertEqual(tuple(fields), FIELD_NAMES)
        self.assertEqual(fields["net_quantity"], "500 g")
        self.assertTrue(all(value is None for key, value in fields.items() if key != "net_quantity"))

    def test_extracts_real_sample_label_declarations_with_ocr_separator_noise(self):
        fields = extract_fields(
            [
                {"text": "Manufactured by: Payless India Franchising, LLC"},
                {"text": "Topeka, USA 66607"},
                {"text": "Imported & Marketed by : Reliance Clothing India Pvt. Ltd."},
                {"text": "3rd Floor,Court Houss,Lokmanya Tilak Marg Dhobi Talao"},
                {"text": "Mumbal: - 400002"},
                {"text": "Net Contents"},
                {"text": "2 N (1 Pair)"},
                {"text": "Product: WO4-FR-CCP-KARMEN"},
                {"text": "Month & Year of Import : : 07 / 2018"},
                {"text": "MRP: ₹899/- (inclusive of all taxes)"},
                {"text": "For consumer related queries, please contact:"},
                {"text": "Toll Free No. 1800 891 2646"},
                {"text": "Email: customercare@reliancebrands.com"},
            ]
        )

        self.assertEqual(fields["product_name"], "WO4-FR-CCP-KARMEN")
        self.assertEqual(fields["mrp"], "899")
        self.assertEqual(fields["mrp_inclusive_of_taxes"], "inclusive of all taxes")
        self.assertEqual(fields["net_quantity"], "2 N (1 Pair)")
        self.assertEqual(fields["manufacturer"], "Payless India Franchising, LLC")
        self.assertEqual(fields["manufacturer_address"], "Topeka, USA 66607")
        self.assertEqual(fields["importer"], "Reliance Clothing India Pvt. Ltd.")
        self.assertEqual(
            fields["importer_address"],
            "3rd Floor,Court Houss,Lokmanya Tilak Marg Dhobi Talao Mumbal: - 400002",
        )
        self.assertEqual(fields["month_year"], "07/2018")
        self.assertEqual(
            fields["consumer_care"],
            "Toll Free No. 1800 891 2646 Email: customercare@reliancebrands.com",
        )

    def test_extracts_consumer_care_from_noisy_ocr_phone_evidence(self):
        fields = extract_fields(
            [
                {"text": "C0nsumr c@re hclp desk"},
                {"text": "For asstnc call 1800-891-2646"},
            ]
        )

        self.assertEqual(fields["consumer_care"], "1800-891-2646")

    def test_extracts_consumer_care_from_noisy_indian_landline_ocr(self):
        noisy_ocr = "fo tetal rparspee re b importa a toe dress trai l astreeig ionor al 1 +91-22-6727-6727"

        fields = extract_fields([{"text": noisy_ocr}])

        self.assertEqual(fields["consumer_care"], "+91-22-6727-6727")

    def test_extracts_spaced_indian_consumer_care_phone_without_ocr_noise(self):
        fields = extract_fields(
            [{"text": "Consumer care desk: please call +91 22 6727 6727 for assistance"}]
        )

        self.assertEqual(
            fields["consumer_care"],
            "desk: please call +91 22 6727 6727 for assistance",
        )

    def test_extracts_parenthesized_pair_as_net_quantity(self):
        fields = extract_fields(
            [
                {"text": "Net Contents"},
                {"text": "2 N (1 Pair)"},
            ]
        )

        self.assertEqual(fields["net_quantity"], "2 N (1 Pair)")

    def test_extracts_mrp_variants_and_tax_inclusion(self):
        cases = (
            ("MRP:899/-", "899", None),
            ("MRP Rs. 899", "899", None),
            ("MRP ₹899", "899", None),
            (
                "MRP: 899/- (inclusive of all taxes)",
                "899",
                "inclusive of all taxes",
            ),
        )

        for text, expected_mrp, expected_tax in cases:
            with self.subTest(text=text):
                fields = extract_fields([{"text": text}])
                self.assertEqual(fields["mrp"], expected_mrp)
                self.assertEqual(fields["mrp_inclusive_of_taxes"], expected_tax)

    def test_extracts_net_quantity_without_losing_count_context(self):
        cases = (
            ("Net Contents: 2 N (1 Pair)", "2 N (1 Pair)"),
            ("Net Qty: 100 g", "100 g"),
            ("Net Quantity: 500 ml", "500 ml"),
            ("Contents: 10 pcs", "10 pcs"),
        )

        for text, expected_quantity in cases:
            with self.subTest(text=text):
                self.assertEqual(extract_fields([{"text": text}])["net_quantity"], expected_quantity)

    def test_extracts_common_entity_declaration_variants(self):
        fields = extract_fields(
            [
                {"text": "Mfd. By: Acme Foods Pvt. Ltd."},
                {"text": "12 Market Road, Pune"},
                {"text": "Import & Marketed By: Global Trade LLP"},
                {"text": "Mumbai, Maharashtra"},
                {"text": "Packed & Marketed By: Acme Packaging"},
                {"text": "Noida, Uttar Pradesh"},
            ]
        )

        self.assertEqual(fields["manufacturer"], "Acme Foods Pvt. Ltd.")
        self.assertEqual(fields["manufacturer_address"], "12 Market Road, Pune")
        self.assertEqual(fields["importer"], "Global Trade LLP")
        self.assertEqual(fields["importer_address"], "Mumbai, Maharashtra")
        self.assertEqual(fields["packer"], "Acme Packaging")
        self.assertEqual(fields["packer_address"], "Noida, Uttar Pradesh")

    def test_extracts_country_of_origin_without_a_separator(self):
        for text in (
            "Made in Vietnam",
            "Country of Origin: Vietnam",
            "Country of Origin Vietnam",
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_fields([{"text": text}])["country_of_origin"], "Vietnam")

    def test_extracts_dates_from_manufacture_and_best_before_declarations(self):
        cases = (
            ("Mfg. Date: 06 . 2025", "06/2025"),
            ("Month & Year of Import :: 07 / 2018", "07/2018"),
            ("Best-Before: 12-2026", "12/2026"),
            ("Use By : Jan, 2027", "Jan 2027"),
        )

        for text, expected_date in cases:
            with self.subTest(text=text):
                self.assertEqual(extract_fields([{"text": text}])["month_year"], expected_date)

    def test_preserves_consumer_care_phone_email_and_address(self):
        fields = extract_fields(
            [
                {"text": "Consumer Care: Call 1800-891-2646"},
                {"text": "Email: care@example.com"},
                {"text": "Acme Foods, 12 Market Road, Pune - 411001"},
            ]
        )

        self.assertEqual(
            fields["consumer_care"],
            "Call 1800-891-2646 Email: care@example.com Acme Foods, 12 Market Road, Pune - 411001",
        )

    def test_ignores_malformed_ocr_entries(self):
        self.assertEqual(extract_fields([{}, {"text": None}, "not an OCR result"]), {field: None for field in FIELD_NAMES})

    def test_maps_only_textually_supported_field_evidence(self):
        ocr_results = [
            {
                "text": "M.R.P.: Rs. 299/- (Inclusive of all taxes)",
                "confidence": 0.97,
                "bounding_box": [[1, 2], [30, 2], [30, 8], [1, 8]],
            },
            {
                "text": "Imported by: Example Imports Pvt. Ltd.",
                "confidence": 0.95,
                "bounding_box": [[1, 10], [50, 10], [50, 16], [1, 16]],
            },
            {
                "text": "Unit 2, Mumbai - 400001",
                "confidence": 0.94,
                "bounding_box": None,
            },
        ]
        fields = {
            "mrp": "299",
            "mrp_inclusive_of_taxes": "Inclusive of all taxes",
            "importer": "Example Imports Pvt. Ltd.",
            "importer_address": "Unit 2, Mumbai - 400001",
            "product_name": "Not present in OCR",
        }

        evidence = map_field_evidence(ocr_results, fields)

        self.assertEqual(
            evidence["mrp"],
            [{
                "source_ocr_text": ocr_results[0]["text"],
                "confidence": 0.97,
                "bounding_box": [[1, 2], [30, 2], [30, 8], [1, 8]],
            }],
        )
        self.assertEqual(evidence["mrp_inclusive_of_taxes"], evidence["mrp"])
        self.assertEqual(evidence["importer"], [{
            "source_ocr_text": ocr_results[1]["text"],
            "confidence": 0.95,
            "bounding_box": [[1, 10], [50, 10], [50, 16], [1, 16]],
        }])
        self.assertEqual(evidence["importer_address"], [{
            "source_ocr_text": ocr_results[2]["text"],
            "confidence": 0.94,
            "bounding_box": None,
        }])
        self.assertEqual(evidence["product_name"], [])


if __name__ == "__main__":
    unittest.main()
