import unittest

from backend.app.services.rules_engine import (
    STATUS_FAIL,
    STATUS_NOT_APPLICABLE,
    STATUS_PASS,
    evaluate_compliance,
)


def check_by_rule(report, rule_id):
    return next(check for check in report["checks"] if check["rule_id"] == rule_id)


class RulesEngineTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
