import unittest

from backend.app.services.field_extractor import (
    FIELD_NAMES,
    derive_compliance_context,
    extract_fields,
    map_field_evidence,
)


class FieldExtractorTests(unittest.TestCase):
    def test_derives_only_explicit_compliance_context(self):
        ocr_results = [
            {"text": "Imported By: Global Trade LLP"},
            {"text": "For wholesale sale only"},
        ]
        fields = extract_fields(ocr_results)

        self.assertEqual(
            derive_compliance_context(ocr_results, fields),
            {
                "imported": True,
                "wholesale": True,
                "unit_sale_price_applicable": None,
                "size_relevant": None,
            },
        )

    def test_context_leaves_unspecified_applicability_unknown(self):
        ocr_results = [{"text": "Net Quantity: 100 g"}, {"text": "MFD: 06/2025"}]

        self.assertEqual(
            derive_compliance_context(ocr_results, extract_fields(ocr_results)),
            {
                "imported": None,
                "wholesale": None,
                "unit_sale_price_applicable": None,
                "size_relevant": None,
            },
        )

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
                "unit_sale_price": None,
                "net_quantity": "100 g",
                "manufacturer": "NatureFresh Foods Pvt. Ltd.",
                "manufacturer_address": "Plot 12, Sector 4, New Delhi - 110020, India",
                "importer": "Global Imports LLP",
                "importer_address": "Warehouse 7, Mumbai - 400001, India",
                "packer": "NatureFresh Packaging",
                "packer_address": "Unit 3, Noida - 201301, India",
                "month_year": "06/2025",
                "month_year_date_type": "import_date",
                "manufacture_date": None,
                "packing_date": None,
                "import_date": "06/2025",
                "expiry_date": None,
                "best_before_date": None,
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

        self.assertIn("1800-891-2646", fields["consumer_care"])

    def test_does_not_extract_generic_phone_without_consumer_care_cue(self):
        noisy_ocr = "fo tetal rparspee re b importa a toe dress trai l astreeig ionor al 1 +91-22-6727-6727"

        fields = extract_fields([{"text": noisy_ocr}])

        self.assertIsNone(fields["consumer_care"])

    def test_does_not_treat_manufacturer_phone_as_consumer_care(self):
        fields = extract_fields(
            [
                {"text": "Manufactured By: Example Foods Pvt. Ltd."},
                {"text": "Phone: +91 98765 43210"},
            ]
        )

        self.assertIsNone(fields["consumer_care"])

    def test_extracts_helpline_phone_with_explicit_consumer_contact_cue(self):
        fields = extract_fields(
            [
                {"text": "Helpline"},
                {"text": "1800-891-2646"},
            ]
        )

        self.assertEqual(fields["consumer_care"], "1800-891-2646")

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

    def test_links_standalone_tax_wording_to_the_adjacent_mrp_declaration(self):
        fields = extract_fields(
            [
                {"text": "MRP"},
                {"text": "Rs. 899"},
                {"text": "(Inclusive of All Taxes)"},
            ]
        )

        self.assertEqual(fields["mrp"], "899")
        self.assertEqual(fields["mrp_inclusive_of_taxes"], "Inclusive of All Taxes")

    def test_does_not_link_tax_wording_elsewhere_on_the_package_to_mrp(self):
        fields = extract_fields(
            [
                {"text": "MRP: Rs. 899"},
                {"text": "Net Quantity: 100 g"},
                {"text": "Manufactured by: Example Foods"},
                {"text": "Offer price inclusive of all taxes"},
            ]
        )

        self.assertEqual(fields["mrp"], "899")
        self.assertIsNone(fields["mrp_inclusive_of_taxes"])

    def test_does_not_treat_arbitrary_tax_wording_as_an_mrp_declaration(self):
        fields = extract_fields([{"text": "Offer price inclusive of all taxes"}])

        self.assertIsNone(fields["mrp"])
        self.assertIsNone(fields["mrp_inclusive_of_taxes"])

    def test_extracts_unit_sale_price_without_confusing_it_with_mrp(self):
        fields = extract_fields(
            [
                {"text": "MRP: Rs. 299/- (inclusive of all taxes)"},
                {"text": "Unit Sale Price: Rs. 2.99 per g"},
            ]
        )

        self.assertEqual(fields["mrp"], "299")
        self.assertEqual(fields["unit_sale_price"], "Rs. 2.99 per g")

    def test_extracts_net_quantity_without_losing_count_context(self):
        cases = (
            ("Net Contents: 2 N (1 Pair)", "2 N (1 Pair)"),
            ("Net Wt. 200 g", "200 g"),
            ("Net Weight: 200 g", "200 g"),
            ("Net Qty: 200 g", "200 g"),
            ("200 g", "200 g"),
            ("1 kg", "1 kg"),
            ("500 ml", "500 ml"),
            ("10 N", "10 N"),
            ("Contents: 10 pcs", "10 pcs"),
        )

        for text, expected_quantity in cases:
            with self.subTest(text=text):
                self.assertEqual(extract_fields([{"text": text}])["net_quantity"], expected_quantity)

    def test_does_not_treat_a_bare_number_as_net_quantity(self):
        self.assertIsNone(extract_fields([{"text": "123456789012"}])["net_quantity"])

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

    def test_extracts_manufacturer_with_multiline_address_until_next_declaration(self):
        fields = extract_fields(
            [
                {"text": "Manufactured By:"},
                {"text": "ABC Foods Pvt. Ltd."},
                {"text": "123 Industrial Area"},
                {"text": "Dehradun, Uttarakhand"},
                {"text": "India"},
                {"text": "MRP: Rs. 899"},
            ]
        )

        self.assertEqual(fields["manufacturer"], "ABC Foods Pvt. Ltd.")
        self.assertEqual(
            fields["manufacturer_address"],
            "123 Industrial Area Dehradun, Uttarakhand India",
        )

    def test_extracts_importer_and_packer_with_multiline_addresses(self):
        fields = extract_fields(
            [
                {"text": "Imported By:"},
                {"text": "XYZ India Pvt. Ltd."},
                {"text": "Mumbai, Maharashtra"},
                {"text": "India"},
                {"text": "Packed By:"},
                {"text": "Example Packaging Pvt. Ltd."},
                {"text": "Plot 7, Industrial Area"},
                {"text": "Noida, Uttar Pradesh"},
                {"text": "Net Weight: 200 g"},
            ]
        )

        self.assertEqual(fields["importer"], "XYZ India Pvt. Ltd.")
        self.assertEqual(fields["importer_address"], "Mumbai, Maharashtra India")
        self.assertEqual(fields["packer"], "Example Packaging Pvt. Ltd.")
        self.assertEqual(
            fields["packer_address"],
            "Plot 7, Industrial Area Noida, Uttar Pradesh",
        )

    def test_manufactured_and_packed_by_preserves_shared_legal_role_evidence(self):
        fields = extract_fields(
            [
                {"text": "Manufactured & Packed By:"},
                {"text": "ABC Foods Pvt. Ltd."},
                {"text": "123 Industrial Area, Dehradun"},
                {"text": "Consumer Care: 1800-000-0000"},
            ]
        )

        self.assertEqual(fields["manufacturer"], "ABC Foods Pvt. Ltd.")
        self.assertEqual(fields["packer"], "ABC Foods Pvt. Ltd.")
        self.assertEqual(fields["manufacturer_address"], "123 Industrial Area, Dehradun")
        self.assertEqual(fields["packer_address"], "123 Industrial Area, Dehradun")

    def test_does_not_assign_entity_noise_or_a_later_entity_address_to_manufacturer(self):
        fields = extract_fields(
            [
                {"text": "Manufactured By: ABC Foods Pvt. Ltd."},
                {"text": "Phone: +91 98765 43210"},
                {"text": "FSSAI License No. 10012345678901"},
                {"text": "8901234567890"},
                {"text": "Imported By: XYZ India Pvt. Ltd."},
                {"text": "Mumbai, Maharashtra"},
            ]
        )

        self.assertIsNone(fields["manufacturer_address"])
        self.assertEqual(fields["importer"], "XYZ India Pvt. Ltd.")
        self.assertEqual(fields["importer_address"], "Mumbai, Maharashtra")

    def test_extracts_country_of_origin_without_a_separator(self):
        for text in (
            "Made in Vietnam",
            "Country of Origin: Vietnam",
            "Country of Origin Vietnam",
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_fields([{"text": text}])["country_of_origin"], "Vietnam")

    def test_country_of_origin_stops_before_adjacent_declaration_text(self):
        cases = (
            ("Country of Origin: Vietnam - Imported and Marketed By Example Trade", "Vietnam"),
            ("Made in India (Packed for retail sale)", "India"),
            ("Country of Origin: Japan; Net Weight: 200 g", "Japan"),
        )

        for text, expected_country in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    extract_fields([{"text": text}])["country_of_origin"], expected_country
                )

    def test_extracts_typed_dates_without_using_expiry_as_month_year(self):
        cases = (
            ("Mfg. Date: 06 . 2025", "manufacture_date", "06/2025", "06/2025"),
            ("Manufacturing: 07/2024", "manufacture_date", "07/2024", "07/2024"),
            ("Pkdt: 08-2023", "packing_date", "08/2023", "08/2023"),
            ("Packed On: 09/2022", "packing_date", "09/2022", "09/2022"),
            ("Month & Year of Import :: 07 / 2018", "import_date", "07/2018", "07/2018"),
            ("Imported On: 10/2021", "import_date", "10/2021", "10/2021"),
            ("Expiry: 12-2026", "expiry_date", "12/2026", None),
            ("Exp: 11/2027", "expiry_date", "11/2027", None),
            ("Use By : Jan, 2027", "expiry_date", "Jan 2027", None),
            ("Best-Before: 12-2026", "best_before_date", "12/2026", None),
        )

        for text, date_field, expected_date, expected_month_year in cases:
            with self.subTest(text=text):
                fields = extract_fields([{"text": text}])
                self.assertEqual(fields[date_field], expected_date)
                self.assertEqual(fields["month_year"], expected_month_year)
                self.assertEqual(
                    fields["month_year_date_type"],
                    date_field if expected_month_year else None,
                )

    def test_rejects_implausible_date_years(self):
        for text in ("Mfg: 01/1899", "Expiry: 13/2201", "Pkdt: 15/2025"):
            with self.subTest(text=text):
                fields = extract_fields([{"text": text}])
                self.assertTrue(all(fields[field] is None for field in (
                    "manufacture_date", "packing_date", "import_date", "expiry_date", "best_before_date"
                )))

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

    def test_extracts_split_declarations_and_common_ocr_variations(self):
        fields = extract_fields(
            [
                {"text": "12 Market Road, Pune"},
                {"text": "Crunchy Snack Mix"},
                {"text": "Net Wt."},
                {"text": "200 9"},
                {"text": "M.R.P."},
                {"text": "Rs 99"},
                {"text": "Inclusive of all taxes"},
                {"text": "MFD"},
                {"text": "08 / 2026"},
                {"text": "Country of Origin"},
                {"text": "India"},
                {"text": "Size"},
                {"text": "10 x 20 cm"},
                {"text": "Manufactured By"},
                {"text": "Example Foods Pvt. Ltd."},
                {"text": "Plot 7, Industrial Area, Pune - 411001"},
                {"text": "Imported By: Example Imports LLP"},
                {"text": "Mumbai - 400001"},
                {"text": "Packed By"},
                {"text": "Example Packaging"},
                {"text": "Noida - 201301"},
                {"text": "Consumer Care"},
                {"text": "Call 1800-891-2646; care@example.com"},
            ]
        )

        self.assertEqual(fields["product_name"], "Crunchy Snack Mix")
        self.assertEqual(fields["net_quantity"], "200 g")
        self.assertEqual(fields["mrp"], "99")
        self.assertEqual(fields["mrp_inclusive_of_taxes"], "Inclusive of all taxes")
        self.assertEqual(fields["month_year"], "08/2026")
        self.assertEqual(fields["country_of_origin"], "India")
        self.assertEqual(fields["size"], "10 x 20 cm")
        self.assertEqual(fields["manufacturer"], "Example Foods Pvt. Ltd.")
        self.assertEqual(
            fields["manufacturer_address"],
            "Plot 7, Industrial Area, Pune - 411001",
        )
        self.assertEqual(fields["importer"], "Example Imports LLP")
        self.assertEqual(fields["importer_address"], "Mumbai - 400001")
        self.assertEqual(fields["packer"], "Example Packaging")
        self.assertEqual(fields["packer_address"], "Noida - 201301")
        self.assertEqual(
            fields["consumer_care"],
            "Call 1800-891-2646; care@example.com",
        )

    def test_extracts_standalone_compact_quantity_only_with_label_context(self):
        fields = extract_fields(
            [
                {"text": "Spiced Nut Mix"},
                {"text": "200g"},
                {"text": "MRP: 99"},
            ]
        )

        self.assertEqual(fields["product_name"], "Spiced Nut Mix")
        self.assertEqual(fields["net_quantity"], "200g")

    def test_does_not_select_an_uncontextualized_random_line_as_product_name(self):
        fields = extract_fields([{"text": "Warehouse 12"}])

        self.assertIsNone(fields["product_name"])

    def test_does_not_treat_ingredients_or_nutrition_ocr_as_product_name(self):
        fields = extract_fields(
            [
                {"text": "Ingredler : Roasted Jowar, Roasted Bajra, Maize", "confidence": 0.91},
                {"text": "Nutritional Information Energy 433 Kcal Protein 11.3 g", "confidence": 0.96},
                {"text": "Net Wt: 200 g", "confidence": 0.98},
            ]
        )

        self.assertIsNone(fields["product_name"])

    def test_does_not_treat_noisy_identifiers_or_low_confidence_text_as_product_name(self):
        fields = extract_fields(
            [
                {"text": "0899820121614", "confidence": 0.99},
                {"text": "FSSAI 1151306101945", "confidence": 0.95},
                {"text": "Cruncky Snack Mix", "confidence": 0.24},
                {"text": "MRP: 70", "confidence": 0.98},
            ]
        )

        self.assertIsNone(fields["product_name"])

    def test_accepts_high_confidence_top_label_product_name(self):
        fields = extract_fields(
            [
                {"text": "CRUNCHY SNACK MIX", "confidence": 0.96},
                {"text": "Net Quantity: 200 g", "confidence": 0.98},
            ]
        )

        self.assertEqual(fields["product_name"], "CRUNCHY SNACK MIX")

    def test_regression_real_label_uses_spatial_label_value_relationships(self):
        # This is regression coverage for an OCR layout, not a product-specific
        # extraction rule. The intentionally shuffled detections require
        # same-row ordering by their existing OCR bounding boxes.
        fields = extract_fields(
            [
                {"text": "70/-", "bounding_box": [[309, 290], [347, 290], [347, 304], [309, 304]]},
                {"text": "RAJKAMAL NAMKEENS PVT.LTD.", "bounding_box": [[160, 391], [351, 393], [350, 406], [160, 404]]},
                {"text": "DIET NAVRATAN MIX (200 g)", "bounding_box": [[39, 130], [363, 134], [363, 154], [39, 150]]},
                {"text": "MRP IN MUMBAI Rs.", "bounding_box": [[170, 285], [301, 288], [301, 302], [170, 299]]},
                {"text": "Net Wt :", "bounding_box": [[174, 229], [249, 232], [249, 246], [174, 244]]},
                {"text": "(Incl of All Taxes):", "bounding_box": [[192, 322], [282, 324], [282, 338], [191, 336]]},
                {"text": "Manufactured & Packed By:", "bounding_box": [[16, 394], [161, 393], [161, 406], [16, 407]]},
                {"text": "200 g", "bounding_box": [[255, 228], [300, 231], [299, 248], [254, 246]]},
            ]
        )

        self.assertEqual(fields["product_name"], "DIET NAVRATAN MIX")
        self.assertEqual(fields["net_quantity"], "200 g")
        self.assertEqual(fields["mrp"], "70")
        self.assertEqual(fields["mrp_inclusive_of_taxes"], "Incl of All Taxes")
        self.assertEqual(fields["manufacturer"], "RAJKAMAL NAMKEENS PVT.LTD.")
        self.assertEqual(fields["packer"], "RAJKAMAL NAMKEENS PVT.LTD.")

    def test_links_spatially_nearby_tax_text_but_not_a_neighboring_column(self):
        nearby = extract_fields([
            {"text": "MRP Rs. 120", "bounding_box": [[200, 100], [310, 100], [310, 114], [200, 114]]},
            {"text": "Nutrition Energy 420 kcal", "bounding_box": [[10, 118], [170, 118], [170, 132], [10, 132]]},
            {"text": "Protein 8 g", "bounding_box": [[10, 136], [95, 136], [95, 150], [10, 150]]},
            {"text": "Inclusive of all taxes", "bounding_box": [[205, 138], [335, 138], [335, 152], [205, 152]]},
        ])
        unrelated_column = extract_fields([
            {"text": "MRP Rs. 120", "bounding_box": [[200, 100], [310, 100], [310, 114], [200, 114]]},
            {"text": "Nutrition Energy 420 kcal", "bounding_box": [[10, 118], [170, 118], [170, 132], [10, 132]]},
            {"text": "Inclusive of all taxes", "bounding_box": [[10, 136], [140, 136], [140, 150], [10, 150]]},
        ])

        self.assertEqual(nearby["mrp_inclusive_of_taxes"], "Inclusive of all taxes")
        self.assertIsNone(unrelated_column["mrp_inclusive_of_taxes"])

    def test_consumer_care_requires_an_explicit_cue_even_for_small_text(self):
        small_care = extract_fields([{
            "text": "For consumer queries call 1800-891-2646",
            "confidence": 0.81,
            "bounding_box": [[10, 300], [190, 300], [190, 308], [10, 308]],
        }])
        manufacturer_phone = extract_fields([
            {"text": "Manufactured By: Example Foods"},
            {"text": "Phone: 9876543210"},
        ])
        unrelated_phone = extract_fields([{"text": "Delivery updates: 1800-891-2646"}])

        self.assertEqual(small_care["consumer_care"], "call 1800-891-2646")
        self.assertIsNone(manufacturer_phone["consumer_care"])
        self.assertIsNone(unrelated_phone["consumer_care"])

    def test_entity_address_stops_before_email_complaint_or_nutrition_prose(self):
        fields = extract_fields([
            {"text": "Imported By: Example Imports Pvt. Ltd."},
            {"text": "3rd Floor, Court House"},
            {"text": "Market Road, Mumbai - 400001"},
            {"text": "Email: care@example.com"},
            {"text": "For any questions or complaints please call us"},
            {"text": "Nutritional Information"},
        ])

        self.assertEqual(
            fields["importer_address"], "3rd Floor, Court House Market Road, Mumbai - 400001"
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

    def test_generalized_food_declarations_do_not_depend_on_brand_words(self):
        fields = extract_fields([
            {"text": "Product Name: Millet Breakfast Blend", "confidence": 0.93},
            {"text": "Maximum Retail Price: Rs. 180/- (inclusive of all taxes)"},
            {"text": "Net Contents: 500 GMS"},
            {"text": "Manufactured by: Sunrise Foods LLP"},
            {"text": "42 Grain Market, Jaipur - 302001"},
        ])

        self.assertEqual(fields["product_name"], "Millet Breakfast Blend")
        self.assertEqual(fields["mrp"], "180")
        self.assertEqual(fields["mrp_inclusive_of_taxes"], "inclusive of all taxes")
        self.assertEqual(fields["net_quantity"], "500 g")
        self.assertEqual(fields["manufacturer"], "Sunrise Foods LLP")
        self.assertEqual(fields["manufacturer_address"], "42 Grain Market, Jaipur - 302001")

    def test_generalized_cosmetic_and_household_declarations(self):
        cosmetic = extract_fields([
            {"text": "BOTANICAL FACE WASH 75", "confidence": 0.97},
            {"text": "M.R.P. Rs 245"},
            {"text": "Net Quantity: 75 ml"},
            {"text": "Manufactured By:"},
            {"text": "Herbal Care Industries"},
            {"text": "Building 8, Industrial Estate"},
            {"text": "Mysuru, Karnataka - 570018"},
        ])
        household = extract_fields([
            {"text": "Manufactured by: Clean Home Works"},
            {"text": "Unit 11, Service Road"},
            {"text": "Kochi, Kerala - 682021"},
            {"text": "Net Wt: 2 x 500 ml"},
        ])

        self.assertEqual(cosmetic["product_name"], "BOTANICAL FACE WASH 75")
        self.assertEqual(cosmetic["net_quantity"], "75 ml")
        self.assertEqual(cosmetic["manufacturer_address"], "Building 8, Industrial Estate Mysuru, Karnataka - 570018")
        self.assertEqual(household["net_quantity"], "2 x 500 ml")
        self.assertEqual(household["manufacturer_address"], "Unit 11, Service Road Kochi, Kerala - 682021")

    def test_generalized_garment_and_imported_declarations_keep_roles_distinct(self):
        garment = extract_fields([
            {"text": "Product Name: Trail Runner 4", "confidence": 0.91},
            {"text": "MRP: 3499"},
            {"text": "Size: UK 8 / EU 42"},
            {"text": "Imported By: Meridian Distribution Pvt. Ltd."},
            {"text": "15 Port Road, Chennai - 600001"},
        ])
        imported = extract_fields([
            {"text": "Importer: Northwind Trading Co."},
            {"text": "Country of Origin: Vietnam"},
            {"text": "Date of Import: Mar 2025"},
        ])

        self.assertEqual(garment["product_name"], "Trail Runner 4")
        self.assertEqual(garment["size"], "UK 8 / EU 42")
        self.assertEqual(garment["importer"], "Meridian Distribution Pvt. Ltd.")
        self.assertIsNone(garment["manufacturer"])
        self.assertEqual(imported["country_of_origin"], "Vietnam")
        self.assertEqual(imported["import_date"], "Mar 2025")
        self.assertEqual(imported["month_year_date_type"], "import_date")

    def test_supports_imported_from_unit_price_and_direct_multiline_address(self):
        fields = extract_fields([
            {"text": "Imported from: Thailand"},
            {"text": "Unit Sale Price: Rs 5 per kg"},
            {"text": "Manufacturer Address:"},
            {"text": "17 Lake View Avenue"},
            {"text": "Bhopal, Madhya Pradesh - 462016"},
            {"text": "GSTIN: 23ABCDE1234F1Z5"},
            {"text": "MRP: Rs 90"},
        ])

        self.assertEqual(fields["country_of_origin"], "Thailand")
        self.assertEqual(fields["unit_sale_price"], "Rs 5 per kg")
        self.assertEqual(fields["manufacturer_address"], "17 Lake View Avenue Bhopal, Madhya Pradesh - 462016")

    def test_rejects_identifiers_and_unrelated_prose_as_general_product_or_quantity_candidates(self):
        fields = extract_fields([
            {"text": "8901234567890", "confidence": 0.99},
            {"text": "GSTIN 27ABCDE1234F1Z5", "confidence": 0.99},
            {"text": "FSSAI Licence 10012345678901", "confidence": 0.99},
            {"text": "Call 9876543210 for delivery updates", "confidence": 0.99},
            {"text": "Ingredients: cereal, salt and spices", "confidence": 0.99},
            {"text": "Nutritional Information Energy 400 kcal", "confidence": 0.99},
        ])

        self.assertIsNone(fields["product_name"])
        self.assertIsNone(fields["net_quantity"])
        self.assertIsNone(fields["consumer_care"])

    def test_dense_food_layout_uses_spatial_order_and_fragmented_declarations(self):
        fields = extract_fields([
            {"text": "120/-", "confidence": 0.96, "bounding_box": [[265, 80], [310, 76], [312, 92], [267, 96]]},
            {"text": "Ingredients: grains, salt, spices", "confidence": 0.97, "bounding_box": [[10, 48], [250, 50], [250, 64], [10, 62]]},
            {"text": "By: Valley Food Works", "confidence": 0.94, "bounding_box": [[125, 130], [300, 128], [300, 144], [125, 146]]},
            {"text": "Net", "confidence": 0.96, "bounding_box": [[10, 103], [38, 104], [38, 118], [10, 117]]},
            {"text": "Nutrition Information Energy 410 kcal", "confidence": 0.93, "bounding_box": [[10, 65], [280, 68], [280, 82], [10, 79]]},
            {"text": "Country of", "confidence": 0.95, "bounding_box": [[10, 180], [95, 182], [95, 196], [10, 194]]},
            {"text": "MRP", "confidence": 0.97, "bounding_box": [[10, 80], [45, 81], [45, 95], [10, 94]]},
            {"text": "Wholegrain Snack Squares", "confidence": 0.98, "bounding_box": [[10, 20], [260, 15], [261, 35], [11, 40]]},
            {"text": "8901234567890", "confidence": 0.99, "bounding_box": [[320, 190], [430, 190], [430, 206], [320, 206]]},
            {"text": "Quantity: 200 g", "confidence": 0.96, "bounding_box": [[50, 101], [175, 103], [175, 118], [50, 116]]},
            {"text": "Manufactured", "confidence": 0.94, "bounding_box": [[10, 130], [112, 132], [112, 146], [10, 144]]},
            {"text": "18 Orchard Lane, Nashik - 422003", "confidence": 0.93, "bounding_box": [[10, 152], [280, 154], [280, 168], [10, 166]]},
            {"text": "Origin: India", "confidence": 0.95, "bounding_box": [[105, 180], [200, 182], [200, 196], [105, 194]]},
        ])

        self.assertEqual(fields["product_name"], "Wholegrain Snack Squares")
        self.assertEqual(fields["mrp"], "120")
        self.assertEqual(fields["net_quantity"], "200 g")
        self.assertEqual(fields["manufacturer"], "Valley Food Works")
        self.assertEqual(fields["manufacturer_address"], "18 Orchard Lane, Nashik - 422003")
        self.assertEqual(fields["country_of_origin"], "India")

    def test_fragmented_non_standard_panels_preserve_roles_and_date_semantics(self):
        fields = extract_fields([
            {"text": "Size", "confidence": 0.94, "bounding_box": [[300, 55], [340, 52], [342, 68], [302, 71]]},
            {"text": "Product Name:", "confidence": 0.97, "bounding_box": [[15, 20], [112, 18], [113, 34], [16, 36]]},
            {"text": "Date of", "confidence": 0.93, "bounding_box": [[15, 155], [78, 156], [78, 170], [15, 169]]},
            {"text": "Trail Sandal 6", "confidence": 0.97, "bounding_box": [[15, 42], [135, 44], [135, 60], [15, 58]]},
            {"text": "Origin: Vietnam", "confidence": 0.95, "bounding_box": [[120, 128], [230, 130], [230, 145], [120, 143]]},
            {"text": "Imported", "confidence": 0.95, "bounding_box": [[15, 78], [83, 80], [83, 95], [15, 93]]},
            {"text": "Import: 03/2025", "confidence": 0.94, "bounding_box": [[88, 155], [210, 156], [210, 171], [88, 170]]},
            {"text": "By: Coastal Supply Ltd.", "confidence": 0.95, "bounding_box": [[90, 80], [245, 82], [245, 97], [90, 95]]},
            {"text": "Country of", "confidence": 0.95, "bounding_box": [[15, 128], [105, 126], [106, 142], [16, 144]]},
            {"text": "UK 8 / EU 42", "confidence": 0.94, "bounding_box": [[350, 52], [450, 54], [450, 70], [350, 68]]},
            {"text": "Harbour Road, Goa - 403001", "confidence": 0.92, "bounding_box": [[15, 105], [240, 107], [240, 122], [15, 120]]},
        ])

        self.assertEqual(fields["product_name"], "Trail Sandal 6")
        self.assertEqual(fields["size"], "UK 8 / EU 42")
        self.assertEqual(fields["importer"], "Coastal Supply Ltd.")
        self.assertEqual(fields["importer_address"], "Harbour Road, Goa - 403001")
        self.assertEqual(fields["country_of_origin"], "Vietnam")
        self.assertEqual(fields["import_date"], "03/2025")
        self.assertIsNone(fields["manufacture_date"])

    def test_spatial_regions_keep_two_columns_and_fragmented_declarations_separate(self):
        fields = extract_fields([
            {"text": "Everyday Grain Bites", "confidence": 0.91, "bounding_box": [[12, 12], [210, 12], [210, 37], [12, 37]]},
            {"text": "A tasty choice", "confidence": 0.99, "bounding_box": [[12, 48], [145, 48], [145, 60], [12, 60]]},
            {"text": "Manufactured By: North Mill Foods", "confidence": 0.96, "bounding_box": [[10, 100], [210, 100], [210, 115], [10, 115]]},
            {"text": "14 River Road, Exampletown - 400001", "confidence": 0.95, "bounding_box": [[10, 121], [230, 121], [230, 136], [10, 136]]},
            {"text": "Nutrition Information", "confidence": 0.96, "bounding_box": [[270, 100], [410, 100], [410, 115], [270, 115]]},
            {"text": "Energy 400 kcal Protein 7 g", "confidence": 0.97, "bounding_box": [[270, 121], [460, 121], [460, 136], [270, 136]]},
            {"text": "FSSAI Licence 10000000000001", "confidence": 0.94, "bounding_box": [[10, 145], [230, 145], [230, 160], [10, 160]]},
        ])
        self.assertEqual(fields["product_name"], "Everyday Grain Bites")
        self.assertEqual(fields["manufacturer_address"], "14 River Road, Exampletown - 400001")

    def test_spatial_contact_requires_cued_block_and_never_uses_entity_phone(self):
        fields = extract_fields([
            {"text": "Manufactured By: Example Works", "bounding_box": [[10, 30], [210, 30], [210, 45], [10, 45]]},
            {"text": "Phone: 9876543210", "bounding_box": [[10, 52], [160, 52], [160, 67], [10, 67]]},
            {"text": "Consumer Care", "bounding_box": [[270, 30], [390, 30], [390, 45], [270, 45]]},
            {"text": "Call 1800-123-4567", "bounding_box": [[270, 52], [420, 52], [420, 67], [270, 67]]},
            {"text": "help@example.test", "bounding_box": [[270, 74], [405, 74], [405, 89], [270, 89]]},
        ])
        self.assertEqual(fields["consumer_care"], "Call 1800-123-4567 help@example.test")

    def test_spatial_mrp_tax_ownership_rejects_neighboring_column(self):
        same_panel = extract_fields([
            {"text": "MRP", "bounding_box": [[10, 30], [45, 30], [45, 45], [10, 45]]},
            {"text": "Rs 135", "bounding_box": [[55, 30], [110, 30], [110, 45], [55, 45]]},
            {"text": "(Incl. of all taxes)", "bounding_box": [[10, 53], [155, 53], [155, 68], [10, 68]]},
        ])
        other_panel = extract_fields([
            {"text": "MRP Rs 135", "bounding_box": [[10, 30], [110, 30], [110, 45], [10, 45]]},
            {"text": "(Incl. of all taxes)", "bounding_box": [[270, 53], [415, 53], [415, 68], [270, 68]]},
        ])
        self.assertEqual(same_panel["mrp"], "135")
        self.assertEqual(same_panel["mrp_inclusive_of_taxes"], "Incl. of all taxes")
        self.assertIsNone(other_panel["mrp_inclusive_of_taxes"])

    def test_spatial_analysis_falls_back_conservatively_without_complete_boxes(self):
        fields = extract_fields([
            {"text": "Product Name: Simple Item", "confidence": 0.9, "bounding_box": None},
            {"text": "MRP: 50", "confidence": 0.9, "bounding_box": [[10, 30], [75, 30], [75, 44], [10, 44]]},
            {"text": "Inclusive of all taxes", "confidence": 0.9, "bounding_box": None},
            {"text": "Nutrition Energy 400 kcal", "confidence": 0.9, "bounding_box": "invalid"},
        ])
        self.assertEqual(fields["product_name"], "Simple Item")
        self.assertEqual(fields["mrp"], "50")
        self.assertEqual(fields["mrp_inclusive_of_taxes"], "Inclusive of all taxes")

    def test_prefers_descriptive_spatial_product_name_over_standalone_brand_text(self):
        fields = extract_fields([
            {"text": "Brightmark", "confidence": 1.0, "bounding_box": [[10, 10], [150, 10], [150, 40], [10, 40]]},
            {"text": "Spiced Vegetable Crisps", "confidence": 1.0, "bounding_box": [[10, 52], [250, 52], [250, 68], [10, 68]]},
            {"text": "Net Quantity: 150 g", "confidence": 0.98, "bounding_box": [[10, 90], [190, 90], [190, 105], [10, 105]]},
        ])
        self.assertEqual(fields["product_name"], "Spiced Vegetable Crisps")

    def test_links_split_mrp_label_to_local_inclusive_tax_wording(self):
        fields = extract_fields([
            {"text": "MRP", "bounding_box": [[10, 10], [50, 10], [50, 25], [10, 25]]},
            {"text": "Rs. 50", "bounding_box": [[60, 10], [115, 10], [115, 25], [60, 25]]},
            {"text": "Incl. of all taxes", "bounding_box": [[10, 45], [155, 45], [155, 60], [10, 60]]},
            {"text": "MRP Rs. 100", "bounding_box": [[300, 10], [405, 10], [405, 25], [300, 25]]},
        ])
        self.assertEqual(fields["mrp"], "50")
        self.assertEqual(fields["mrp_inclusive_of_taxes"], "Incl. of all taxes")

    def test_stops_spatial_address_after_complete_postal_address(self):
        fields = extract_fields([
            {"text": "Manufactured By: Example Works", "bounding_box": [[10, 10], [230, 10], [230, 25], [10, 25]]},
            {"text": "12 Market Road, Exampletown - 400001", "bounding_box": [[10, 32], [260, 32], [260, 47], [10, 47]]},
            {"text": "uncertain", "bounding_box": [[10, 54], [80, 54], [80, 69], [10, 69]]},
            {"text": "Licence No. 10000000000001", "bounding_box": [[10, 76], [230, 76], [230, 91], [10, 91]]},
        ])
        self.assertEqual(fields["manufacturer_address"], "12 Market Road, Exampletown - 400001")


if __name__ == "__main__":
    unittest.main()
