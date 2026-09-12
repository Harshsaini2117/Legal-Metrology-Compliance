import unittest

from backend.app.services.rules_engine import (
    STATUS_FAIL,
    STATUS_NOT_APPLICABLE,
    STATUS_PASS,
    evaluate_compliance,
)


def check_by_rule(report, rule_id):
    return next(check for check in report["checks"] if check["rule_id"] == rule_id)


def compliant_declarations():
    return {
        "product_name": "Herbal Tea",
        "manufacturer": "NatureFresh Foods Pvt. Ltd.",
        "manufacturer_address": "New Delhi",
        "is_imported": True,
        "country_of_origin": "India",
        "net_quantity": "100 g",
        "mrp": "299.00",
        "mrp_inclusive_of_taxes": True,
        "month_year": "06/2025",
        "consumer_care": "1800-000-0000",
        "unit_sale_price_applicable": False,
        "size_relevant": False,
    }


class RulesEngineTests(unittest.TestCase):
    def assert_missing_declaration_is_unable_to_verify(self, declarations, rule_id):
        report = evaluate_compliance(declarations)
        check = check_by_rule(report, rule_id)

        self.assertEqual(check["status"], STATUS_NOT_APPLICABLE)
        self.assertEqual(check["verification_status"], "UNABLE_TO_VERIFY")
        self.assertNotIn(rule_id, {violation["rule_id"] for violation in report["violations"]})

    def test_missing_product_name_is_unable_to_verify_not_a_violation(self):
        declarations = compliant_declarations()
        declarations.pop("product_name")

        self.assert_missing_declaration_is_unable_to_verify(declarations, "LMPC-R6-01")

    def test_missing_manufacturer_packer_importer_is_unable_to_verify_not_a_violation(self):
        declarations = compliant_declarations()
        declarations.pop("manufacturer")
        declarations.pop("manufacturer_address")

        self.assert_missing_declaration_is_unable_to_verify(declarations, "LMPC-R6-02")

    def test_missing_country_of_origin_is_unable_to_verify_not_a_violation(self):
        declarations = compliant_declarations()
        declarations.pop("country_of_origin")

        self.assert_missing_declaration_is_unable_to_verify(declarations, "LMPC-R6-03")

    def test_missing_net_quantity_is_unable_to_verify_not_a_violation(self):
        declarations = compliant_declarations()
        declarations.pop("net_quantity")

        self.assert_missing_declaration_is_unable_to_verify(declarations, "LMPC-R6-04")

    def test_missing_mrp_is_unable_to_verify_not_a_violation(self):
        declarations = compliant_declarations()
        declarations.pop("mrp")

        self.assert_missing_declaration_is_unable_to_verify(declarations, "LMPC-R6-05")

    def test_missing_tax_inclusive_mrp_wording_is_unable_to_verify_not_a_violation(self):
        declarations = compliant_declarations()
        declarations.pop("mrp_inclusive_of_taxes")

        self.assert_missing_declaration_is_unable_to_verify(declarations, "LMPC-R6-06")

    def test_missing_month_year_is_unable_to_verify_not_a_violation(self):
        declarations = compliant_declarations()
        declarations.pop("month_year")

        self.assert_missing_declaration_is_unable_to_verify(declarations, "LMPC-R6-07")

    def test_missing_consumer_care_is_unable_to_verify_not_a_violation(self):
        declarations = compliant_declarations()
        declarations.pop("consumer_care")

        self.assert_missing_declaration_is_unable_to_verify(declarations, "LMPC-R6-08")

    def test_unit_sale_price_is_not_applicable_for_count_quantity(self):
        declarations = compliant_declarations()
        declarations.pop("unit_sale_price_applicable")
        declarations["net_quantity"] = "1 Pair"

        report = evaluate_compliance(declarations)
        check = check_by_rule(report, "LMPC-R6-09")

        self.assertEqual(check["status"], STATUS_NOT_APPLICABLE)
        self.assertEqual(check["verification_status"], "NOT_APPLICABLE")
        self.assertEqual(report["compliance_score"], 100)
        self.assertEqual(report["overall_status"], "COMPLIANT")

    def test_unit_sale_price_passes_when_measured_quantity_has_a_declaration(self):
        declarations = compliant_declarations()
        declarations.pop("unit_sale_price_applicable")
        declarations["unit_sale_price"] = "Rs. 299.00/kg"

        report = evaluate_compliance(declarations)

        self.assertEqual(check_by_rule(report, "LMPC-R6-09")["status"], STATUS_PASS)

    def test_unit_sale_price_fails_when_measured_quantity_is_missing_a_declaration(self):
        declarations = compliant_declarations()
        declarations.pop("unit_sale_price_applicable")

        report = evaluate_compliance(declarations)

        self.assertEqual(check_by_rule(report, "LMPC-R6-09")["status"], STATUS_FAIL)
        self.assertIn("LMPC-R6-09", {violation["rule_id"] for violation in report["violations"]})
        self.assertEqual(report["overall_status"], "NON_COMPLIANT")

    def test_unit_sale_price_is_unable_to_verify_without_quantity_or_context(self):
        declarations = compliant_declarations()
        declarations.pop("unit_sale_price_applicable")
        declarations.pop("net_quantity")

        report = evaluate_compliance(declarations)
        check = check_by_rule(report, "LMPC-R6-09")

        self.assertEqual(check["status"], STATUS_NOT_APPLICABLE)
        self.assertEqual(check["verification_status"], "UNABLE_TO_VERIFY")

    def test_reports_compliant_when_all_applicable_declarations_are_valid(self):
        report = evaluate_compliance(
            {
                "product_name": "Herbal Tea",
                "manufacturer": "NatureFresh Foods Pvt. Ltd.",
                "manufacturer_address": "New Delhi",
                "importer": "Global Imports LLP",
                "importer_address": "Mumbai",
                "country_of_origin": "India",
                "is_imported": True,
                "net_quantity": "100 g",
                "mrp": "299.00",
                "mrp_inclusive_of_taxes": True,
                "month_year": "06/2025",
                "consumer_care": "NatureFresh Care, New Delhi, 1800-000-0000",
                "unit_sale_price_applicable": True,
                "unit_sale_price": "Rs. 299.00/kg",
                "size_relevant": True,
                "size": "20 x 10 cm",
            }
        )

        self.assertEqual(report["overall_status"], "COMPLIANT")
        self.assertEqual(report["compliance_score"], 100)
        self.assertEqual(report["violations"], [])
        self.assertTrue(all(check["status"] == STATUS_PASS for check in report["checks"]))

    def test_reports_failures_for_detected_invalid_declarations(self):
        report = evaluate_compliance(
            {
                "product_name": "Herbal Tea",
                "manufacturer": "NatureFresh Foods Pvt. Ltd.",
                "net_quantity": "500",
                "mrp": "not shown",
                "mrp_inclusive_of_taxes": False,
                "month_year": "2025",
                "is_imported": False,
                "unit_sale_price_applicable": False,
                "size_relevant": False,
            }
        )

        self.assertEqual(report["overall_status"], "NON_COMPLIANT")
        self.assertEqual(check_by_rule(report, "LMPC-R6-04")["status"], STATUS_FAIL)
        self.assertEqual(check_by_rule(report, "LMPC-R6-05")["status"], STATUS_FAIL)
        self.assertEqual(check_by_rule(report, "LMPC-R6-06")["status"], STATUS_FAIL)
        self.assertEqual(check_by_rule(report, "LMPC-R6-07")["status"], STATUS_FAIL)
        self.assertEqual({item["rule_id"] for item in report["violations"]}, {"LMPC-R6-04", "LMPC-R6-05", "LMPC-R6-06", "LMPC-R6-07"})

    def test_missing_ocr_evidence_is_unable_to_verify_not_a_failure(self):
        report = evaluate_compliance({"product_name": "NET QUANTITY 500 g"})

        self.assertEqual(report["overall_status"], "UNABLE_TO_VERIFY")
        self.assertEqual(check_by_rule(report, "LMPC-R6-01")["status"], STATUS_PASS)
        net_quantity = check_by_rule(report, "LMPC-R6-04")
        self.assertEqual(net_quantity["status"], STATUS_NOT_APPLICABLE)
        self.assertEqual(net_quantity["evidence_status"], "NOT_DETECTED")
        self.assertEqual(net_quantity["verification_status"], "UNABLE_TO_VERIFY")
        self.assertEqual(report["violations"], [])

    def test_incomplete_checks_do_not_receive_a_full_compliance_score(self):
        report = evaluate_compliance(
            {
                "product_name": "Herbal Tea",
                "manufacturer": "NatureFresh Foods Pvt. Ltd.",
                "manufacturer_address": "New Delhi",
                "importer": "Global Imports LLP",
                "importer_address": "Mumbai",
                "country_of_origin": "India",
                "is_imported": True,
                "net_quantity": "100 g",
                "mrp": "299.00",
                "mrp_inclusive_of_taxes": "inclusive of all taxes",
                "month_year": "06/2025",
                "unit_sale_price_applicable": False,
                "size_relevant": False,
            }
        )

        self.assertEqual(check_by_rule(report, "LMPC-R6-05")["status"], STATUS_PASS)
        self.assertEqual(check_by_rule(report, "LMPC-R6-06")["status"], STATUS_PASS)
        self.assertEqual(check_by_rule(report, "LMPC-R6-08")["verification_status"], "UNABLE_TO_VERIFY")
        self.assertEqual(report["overall_status"], "UNABLE_TO_VERIFY")
        self.assertEqual(report["compliance_score"], 88)

    def test_accepts_pair_count_net_quantity_from_real_sample_label(self):
        report = evaluate_compliance(
            {
                "product_name": "WO4-FR-CCP-KARMEN",
                "manufacturer": "Payless India Franchising, LLC",
                "manufacturer_address": "Topeka, USA 66607",
                "importer": "Reliance Clothing India Pvt. Ltd.",
                "importer_address": "Mumbai - 400002",
                "country_of_origin": "Vietnam",
                "net_quantity": "1 Pair",
                "mrp": "899",
                "mrp_inclusive_of_taxes": "inclusive of all taxes",
                "month_year": "07/2018",
                "consumer_care": (
                    "Toll Free No. 1800 891 2646 "
                    "Email: customercare@reliancebrands.com"
                ),
            }
        )

        self.assertEqual(check_by_rule(report, "LMPC-R6-01")["status"], STATUS_PASS)
        self.assertEqual(check_by_rule(report, "LMPC-R6-02")["status"], STATUS_PASS)
        self.assertEqual(check_by_rule(report, "LMPC-R6-03")["status"], STATUS_PASS)
        self.assertEqual(check_by_rule(report, "LMPC-R6-04")["status"], STATUS_PASS)
        self.assertEqual(check_by_rule(report, "LMPC-R6-05")["status"], STATUS_PASS)
        self.assertEqual(check_by_rule(report, "LMPC-R6-06")["status"], STATUS_PASS)
        self.assertEqual(check_by_rule(report, "LMPC-R6-07")["status"], STATUS_PASS)
        self.assertEqual(check_by_rule(report, "LMPC-R6-08")["status"], STATUS_PASS)


if __name__ == "__main__":
    unittest.main()
