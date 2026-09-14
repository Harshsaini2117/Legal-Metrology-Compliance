import unittest

from backend.app.services.rules_engine import (
    STATUS_FAIL,
    STATUS_NOT_APPLICABLE,
    STATUS_PASS,
    _verification_metrics,
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

    def test_imported_product_missing_country_of_origin_is_a_failure(self):
        declarations = compliant_declarations()
        declarations.pop("country_of_origin")

        report = evaluate_compliance(declarations)
        check = check_by_rule(report, "LMPC-R6-03")

        self.assertEqual(check["status"], STATUS_FAIL)
        self.assertIn("LMPC-R6-03", {violation["rule_id"] for violation in report["violations"]})

    def test_domestic_product_missing_country_of_origin_is_not_applicable(self):
        declarations = compliant_declarations()
        declarations["is_imported"] = False
        declarations.pop("country_of_origin")

        check = check_by_rule(evaluate_compliance(declarations), "LMPC-R6-03")

        self.assertEqual(check["status"], STATUS_NOT_APPLICABLE)
        self.assertEqual(check["verification_status"], "NOT_APPLICABLE")

    def test_unknown_import_status_missing_country_of_origin_is_unable_to_verify(self):
        declarations = compliant_declarations()
        declarations.pop("is_imported")
        declarations.pop("country_of_origin")

        check = check_by_rule(evaluate_compliance(declarations), "LMPC-R6-03")

        self.assertEqual(check["status"], STATUS_NOT_APPLICABLE)
        self.assertEqual(check["verification_status"], "UNABLE_TO_VERIFY")

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

    def test_accepts_abbreviated_tax_inclusion_wording(self):
        declarations = compliant_declarations()
        declarations["mrp_inclusive_of_taxes"] = "Incl. of all taxes"

        self.assertEqual(check_by_rule(evaluate_compliance(declarations), "LMPC-R6-06")["status"], STATUS_PASS)

    def test_missing_month_year_is_unable_to_verify_not_a_violation(self):
        declarations = compliant_declarations()
        declarations.pop("month_year")

        self.assert_missing_declaration_is_unable_to_verify(declarations, "LMPC-R6-07")

    def test_expiry_only_date_does_not_satisfy_manufacture_packing_import_requirement(self):
        declarations = compliant_declarations()
        declarations.pop("month_year")
        declarations["manufacture_date"] = None
        declarations["packing_date"] = None
        declarations["import_date"] = None
        declarations["expiry_date"] = "12/2026"
        declarations["best_before_date"] = None

        check = check_by_rule(evaluate_compliance(declarations), "LMPC-R6-07")

        self.assertEqual(check["status"], STATUS_NOT_APPLICABLE)
        self.assertEqual(check["verification_status"], "UNABLE_TO_VERIFY")

    def test_best_before_only_date_does_not_satisfy_manufacture_packing_import_requirement(self):
        declarations = compliant_declarations()
        declarations.pop("month_year")
        declarations["manufacture_date"] = None
        declarations["packing_date"] = None
        declarations["import_date"] = None
        declarations["expiry_date"] = None
        declarations["best_before_date"] = "12/2026"

        check = check_by_rule(evaluate_compliance(declarations), "LMPC-R6-07")

        self.assertEqual(check["status"], STATUS_NOT_APPLICABLE)
        self.assertEqual(check["verification_status"], "UNABLE_TO_VERIFY")

    def test_typed_import_date_satisfies_manufacture_packing_import_requirement(self):
        declarations = compliant_declarations()
        declarations.pop("month_year")
        declarations["import_date"] = "06/2025"
        declarations["expiry_date"] = "12/2026"

        check = check_by_rule(evaluate_compliance(declarations), "LMPC-R6-07")

        self.assertEqual(check["status"], STATUS_PASS)

    def test_missing_consumer_care_is_unable_to_verify_not_a_violation(self):
        declarations = compliant_declarations()
        declarations.pop("consumer_care")

        self.assert_missing_declaration_is_unable_to_verify(declarations, "LMPC-R6-08")

    def test_empty_or_cue_only_consumer_care_is_unable_to_verify(self):
        for value in (None, "", " / Feedback"):
            with self.subTest(value=value):
                declarations = compliant_declarations()
                declarations["consumer_care"] = value
                self.assert_missing_declaration_is_unable_to_verify(declarations, "LMPC-R6-08")

    def test_unit_sale_price_is_required_for_post_commencement_count_quantity(self):
        declarations = compliant_declarations()
        declarations["unit_sale_price_applicable"] = True
        declarations["net_quantity"] = "2 N (1 Pair)"

        report = evaluate_compliance(declarations)
        check = check_by_rule(report, "LMPC-R6-09")

        self.assertEqual(check["status"], STATUS_FAIL)
        self.assertEqual(check["verification_status"], "VERIFIED")
        self.assertIn("LMPC-R6-09", {violation["rule_id"] for violation in report["violations"]})

    def test_accepts_recognized_measured_and_count_net_quantity_formats(self):
        for quantity in ("2 N (1 Pair)", "1 Pair", "100 g"):
            with self.subTest(quantity=quantity):
                declarations = compliant_declarations()
                declarations["net_quantity"] = quantity

                report = evaluate_compliance(declarations)

                self.assertEqual(check_by_rule(report, "LMPC-R6-04")["status"], STATUS_PASS)

    def test_rejects_plain_number_as_invalid_net_quantity(self):
        declarations = compliant_declarations()
        declarations["net_quantity"] = "500"

        report = evaluate_compliance(declarations)

        self.assertEqual(check_by_rule(report, "LMPC-R6-04")["status"], STATUS_FAIL)

    def test_unit_sale_price_passes_when_measured_quantity_has_a_declaration(self):
        declarations = compliant_declarations()
        declarations["unit_sale_price_applicable"] = True
        declarations["unit_sale_price"] = "Rs. 2.99 per g"

        report = evaluate_compliance(declarations)

        self.assertEqual(check_by_rule(report, "LMPC-R6-09")["status"], STATUS_PASS)

    def test_unit_sale_price_fails_when_measured_quantity_is_missing_a_declaration(self):
        declarations = compliant_declarations()
        declarations["unit_sale_price_applicable"] = True

        report = evaluate_compliance(declarations)

        self.assertEqual(check_by_rule(report, "LMPC-R6-09")["status"], STATUS_FAIL)
        self.assertIn("LMPC-R6-09", {violation["rule_id"] for violation in report["violations"]})
        self.assertEqual(report["overall_status"], "NON_COMPLIANT")

    def test_post_commencement_unit_sale_price_is_unable_to_verify_when_applicability_is_unknown(self):
        declarations = compliant_declarations()
        declarations.pop("unit_sale_price_applicable")

        check = check_by_rule(evaluate_compliance(declarations), "LMPC-R6-09")

        self.assertEqual(check["status"], STATUS_NOT_APPLICABLE)
        self.assertEqual(check["verification_status"], "UNABLE_TO_VERIFY")

    def test_present_valid_unit_sale_price_is_verified_when_applicability_is_unknown(self):
        declarations = compliant_declarations()
        declarations.pop("unit_sale_price_applicable")
        declarations["unit_sale_price"] = "Rs. 0.33 per g"

        check = check_by_rule(evaluate_compliance(declarations), "LMPC-R6-09")

        self.assertEqual(check["status"], STATUS_PASS)
        self.assertEqual(check["verification_status"], "VERIFIED")

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
                "unit_sale_price": "Rs. 2.99 per g",
                "size_relevant": True,
                "size": "20 x 10 cm",
            }
        )

        self.assertEqual(report["overall_status"], "COMPLIANT")
        self.assertEqual(report["compliance_score"], 100)
        self.assertEqual(report["verified_compliance_score"], 100)
        self.assertEqual(report["evidence_coverage"], 100)
        self.assertFalse(report["review_required"])
        self.assertEqual(report["violations"], [])
        self.assertTrue(all(check["status"] == STATUS_PASS for check in report["checks"]))

    def test_unit_sale_price_is_not_applicable_before_rule_commencement(self):
        declarations = compliant_declarations()
        declarations.pop("unit_sale_price_applicable")
        declarations["month_year"] = "03/2022"

        report = evaluate_compliance(declarations)
        check = check_by_rule(report, "LMPC-R6-09")

        self.assertEqual(check["status"], STATUS_NOT_APPLICABLE)
        self.assertEqual(check["verification_status"], "NOT_APPLICABLE")

    def test_unit_sale_price_is_not_applicable_for_wholesale_package_context(self):
        declarations = compliant_declarations()
        declarations.pop("unit_sale_price_applicable")
        declarations["is_wholesale"] = True
        declarations["unit_sale_price"] = "Rs. 2.99 per g"

        report = evaluate_compliance(declarations)
        check = check_by_rule(report, "LMPC-R6-09")

        self.assertEqual(check["status"], STATUS_NOT_APPLICABLE)
        self.assertEqual(check["verification_status"], "NOT_APPLICABLE")

    def test_missing_size_is_unable_to_verify_when_size_relevance_is_unknown(self):
        declarations = compliant_declarations()
        declarations.pop("size_relevant")

        check = check_by_rule(evaluate_compliance(declarations), "LMPC-R6-10")

        self.assertEqual(check["status"], STATUS_NOT_APPLICABLE)
        self.assertEqual(check["verification_status"], "UNABLE_TO_VERIFY")

    def test_unit_sale_price_is_unable_to_verify_for_commencement_month(self):
        declarations = compliant_declarations()
        declarations.pop("unit_sale_price_applicable")
        declarations["month_year"] = "04/2022"

        report = evaluate_compliance(declarations)
        check = check_by_rule(report, "LMPC-R6-09")

        self.assertEqual(check["status"], STATUS_NOT_APPLICABLE)
        self.assertEqual(check["verification_status"], "UNABLE_TO_VERIFY")

    def test_expiry_and_best_before_do_not_affect_unit_sale_price_applicability(self):
        declarations = compliant_declarations()
        declarations.pop("month_year")
        declarations.pop("unit_sale_price_applicable")
        declarations["manufacture_date"] = None
        declarations["packing_date"] = None
        declarations["import_date"] = None
        declarations["expiry_date"] = "12/2026"
        declarations["best_before_date"] = "11/2026"

        check = check_by_rule(evaluate_compliance(declarations), "LMPC-R6-09")

        self.assertEqual(check["status"], STATUS_NOT_APPLICABLE)
        self.assertEqual(check["verification_status"], "UNABLE_TO_VERIFY")

    def test_unit_sale_price_requires_the_quantity_specific_unit(self):
        declarations = compliant_declarations()
        declarations["unit_sale_price_applicable"] = True
        declarations["unit_sale_price"] = "Rs. 299.00 per kg"

        report = evaluate_compliance(declarations)

        self.assertEqual(check_by_rule(report, "LMPC-R6-09")["status"], STATUS_FAIL)

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

    def test_unresolved_checks_are_coverage_not_verified_compliance(self):
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
        self.assertEqual(report["compliance_score"], 100)
        self.assertEqual(report["verified_compliance_score"], 100)
        self.assertEqual(report["evidence_coverage"], 88)
        self.assertEqual(report["unable_to_verify_checks"], 1)
        self.assertTrue(report["review_required"])

    def test_confirmed_failure_remains_visible_when_other_checks_are_unresolved(self):
        declarations = compliant_declarations()
        declarations["mrp"] = "invalid"
        declarations.pop("consumer_care")

        report = evaluate_compliance(declarations)

        self.assertEqual(report["overall_status"], "NON_COMPLIANT")
        self.assertEqual(report["failed_checks"], 1)
        self.assertEqual(report["unable_to_verify_checks"], 1)
        self.assertTrue(report["review_required"])
        self.assertIn("LMPC-R6-05", {item["rule_id"] for item in report["violations"]})

    def test_verified_pass_and_fail_is_confirmed_non_compliance(self):
        declarations = compliant_declarations()
        declarations["mrp"] = "invalid"

        report = evaluate_compliance(declarations)

        self.assertEqual(report["overall_status"], "NON_COMPLIANT")
        self.assertEqual(report["passed_checks"], 7)
        self.assertEqual(report["failed_checks"], 1)
        self.assertEqual(report["verified_compliance_score"], 88)
        self.assertEqual(report["evidence_coverage"], 100)
        self.assertFalse(report["review_required"])

    def test_not_applicable_checks_are_excluded_from_metrics(self):
        metrics = _verification_metrics(
            [
                {"status": STATUS_PASS, "verification_status": "VERIFIED"},
                {"status": STATUS_NOT_APPLICABLE, "verification_status": "NOT_APPLICABLE"},
            ]
        )

        self.assertEqual(metrics["verified_compliance_score"], 100)
        self.assertEqual(metrics["evidence_coverage"], 100)
        self.assertEqual(metrics["total_applicable_checks"], 1)

    def test_all_not_applicable_checks_produce_no_misleading_percentage(self):
        metrics = _verification_metrics(
            [{"status": STATUS_NOT_APPLICABLE, "verification_status": "NOT_APPLICABLE"}]
        )

        self.assertIsNone(metrics["verified_compliance_score"])
        self.assertIsNone(metrics["evidence_coverage"])
        self.assertEqual(metrics["total_applicable_checks"], 0)
        self.assertFalse(metrics["review_required"])

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
