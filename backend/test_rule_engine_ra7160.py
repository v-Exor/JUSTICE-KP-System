import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rule_engine import evaluate_jurisdiction  # noqa: E402
from schemas import CaseInformationPayload  # noqa: E402
from xai_trace import build_xai_trace  # noqa: E402


def case_info(**overrides):
    values = {
        "case_id": "KP-2026-RA7160",
        "barangay_name": "Barangay Uno",
        "city_municipality": "Santa Cruz",
        "case_year": 2026,
        "case_type": "civil",
        "dispute_category": "debt",
        "complainant_residency": "same_barangay",
        "respondent_residency": "same_barangay",
        "maximum_penalty_years": 0,
        "fine_amount_php": 0,
    }
    values.update(overrides)
    return CaseInformationPayload(**values)


def fired_ids(result):
    return {rule["rule_id"] for rule in result["rule_results"] if rule["fired"]}


class RA7160RuleEngineTests(unittest.TestCase):
    def test_within_kp_uses_source_mapped_rule_ids(self):
        result = evaluate_jurisdiction(case_info(), {"detected_keywords": [], "vawc_trigger": False})

        self.assertEqual(result["jurisdiction_decision"], "within_kp")
        self.assertEqual(result["exclusion_ground"], "none")
        self.assertIn("KP-COVER-01", fired_ids(result))
        self.assertIn("KP-VENUE-01", fired_ids(result))
        self.assertIn("KP-DECISION-01", fired_ids(result))
        self.assertNotIn("R01", {rule["rule_id"] for rule in result["rule_results"]})

    def test_statutory_coverage_exceptions_are_traceable(self):
        scenarios = [
            ("has_juridical_entity_party", True, "KP-COVER-02", "juridical_entity_party"),
            ("government_party_involved", True, "KP-COVER-03", "government_party"),
            (
                "no_private_offended_party",
                True,
                "KP-COVER-06",
                "no_private_offended_party",
            ),
        ]

        for field, value, expected_rule, expected_ground in scenarios:
            with self.subTest(field=field):
                result = evaluate_jurisdiction(
                    case_info(**{field: value}),
                    {"detected_keywords": [], "vawc_trigger": False},
                )

                self.assertEqual(result["jurisdiction_decision"], "outside_kp")
                self.assertEqual(result["exclusion_ground"], expected_ground)
                self.assertIn(expected_rule, fired_ids(result))

    def test_penalty_fine_ceiling_uses_kp_cover_05(self):
        result = evaluate_jurisdiction(
            case_info(maximum_penalty_years=2),
            {"detected_keywords": [], "vawc_trigger": False},
        )

        self.assertEqual(result["jurisdiction_decision"], "outside_kp")
        self.assertEqual(result["exclusion_ground"], "penalty_over_1_year")
        self.assertIn("KP-COVER-05", fired_ids(result))

    def test_direct_court_exception_uses_trig_03(self):
        result = evaluate_jurisdiction(
            case_info(accused_under_detention=True),
            {"detected_keywords": [], "vawc_trigger": False},
        )

        self.assertEqual(result["jurisdiction_decision"], "outside_kp")
        self.assertEqual(result["exclusion_ground"], "direct_court_exception")
        self.assertIn("TRIG-03", fired_ids(result))

    def test_adjoining_barangay_with_mutual_agreement_is_not_auto_rejected(self):
        result = evaluate_jurisdiction(
            case_info(
                complainant_residency="different_municipality",
                respondent_residency="different_municipality",
                parties_in_different_city_municipality=True,
                parties_in_adjoining_barangays=True,
                mutual_agreement_to_kp=True,
            ),
            {"detected_keywords": [], "vawc_trigger": False},
        )

        self.assertEqual(result["jurisdiction_decision"], "within_kp")
        self.assertIn("KP-COVER-01", fired_ids(result))
        self.assertNotIn("KP-COVER-08", fired_ids(result))

    def test_vawc_xai_trace_uses_trig_01_and_authority(self):
        keyword_result = {"detected_keywords": ["sinaktan"], "vawc_trigger": True}
        result = evaluate_jurisdiction(case_info(), keyword_result)
        trace = build_xai_trace(result, keyword_result)

        self.assertEqual(result["jurisdiction_decision"], "refer_to_pnp_wcpc_or_authority")
        self.assertIn("TRIG-01", fired_ids(result))
        self.assertTrue(any("TRIG-01 Fired" in line and "sinaktan" in line for line in trace))
        self.assertTrue(any("R.A. 9262" in line for line in trace))


if __name__ == "__main__":
    unittest.main()
