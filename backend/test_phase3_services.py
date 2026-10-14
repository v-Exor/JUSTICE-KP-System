from io import BytesIO
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase3_services import (  # noqa: E402
    EvidenceFileService,
    HearingService,
    MediationEligibilityService,
    MediationSuggestionService,
    Phase2Bundle,
    SensitiveCaseRoutingService,
    EmotionAnalysisService,
)
from schemas import CaseInformationPayload  # noqa: E402


def make_bundle(
    *,
    case_id="KP-2026-TEST",
    transcript="Speaker 2: May utang po siya sa akin.",
    dispute_category="debt",
    jurisdiction_decision="within_kp",
    penalty_years=0,
    detected_keywords=None,
):
    return Phase2Bundle(
        analysis=SimpleNamespace(
            id=1,
            transcript_id=1,
            jurisdiction_decision=jurisdiction_decision,
            exclusion_ground="none",
            confidence_level="high",
            missing_fields_json=[],
            recommended_next_action="Proceed",
            detected_keywords_json=detected_keywords or {"detected_keywords": [], "keyword_count": 0, "vawc_trigger": False},
            rule_results_json=[],
            xai_trace_id=1,
        ),
        case_info=SimpleNamespace(
            case_id=case_id,
            dispute_category=dispute_category,
            maximum_penalty_years=penalty_years,
        ),
        transcript=SimpleNamespace(content=transcript, segments_json=[]),
        xai_trace=["R01 fired"],
    )


class Phase3ServiceTests(unittest.TestCase):
    def test_vawc_keyword_blocks_mediation(self):
        bundle = make_bundle(transcript="Speaker 2: Sinaktan po ako ng asawa ko.")
        route = SensitiveCaseRoutingService().evaluate(bundle)
        eligibility = MediationEligibilityService().evaluate(bundle, route)

        self.assertTrue(route["is_sensitive"])
        self.assertTrue(route["blocking_mediation"])
        self.assertEqual(route["recommended_route"], "Refer to PNP WCPD")
        self.assertFalse(eligibility["eligible_for_mediation"])

    def test_outside_kp_blocks_mediation(self):
        bundle = make_bundle(jurisdiction_decision="outside_kp")
        route = SensitiveCaseRoutingService().evaluate(bundle)
        eligibility = MediationEligibilityService().evaluate(bundle, route)

        self.assertEqual(route["sensitive_category"], "Outside KP")
        self.assertFalse(eligibility["eligible_for_mediation"])

    def test_penalty_over_one_year_blocks_mediation(self):
        bundle = make_bundle(penalty_years=2)
        route = SensitiveCaseRoutingService().evaluate(bundle)

        self.assertTrue(route["blocking_mediation"])
        self.assertEqual(route["recommended_route"], "Refer to Court")

    def test_ambiguous_case_goes_to_manual_review(self):
        bundle = make_bundle(jurisdiction_decision="ambiguous_manual_review")
        route = SensitiveCaseRoutingService().evaluate(bundle)
        eligibility = MediationEligibilityService().evaluate(bundle, route)

        self.assertEqual(route["recommended_route"], "Manual Review")
        self.assertEqual(eligibility["required_action"], "Manual Review")

    def test_within_kp_debt_case_generates_three_suggestions(self):
        bundle = make_bundle(dispute_category="debt")
        route = SensitiveCaseRoutingService().evaluate(bundle)
        eligibility = MediationEligibilityService().evaluate(bundle, route)
        suggestions = MediationSuggestionService().generate(bundle, eligibility)

        self.assertTrue(eligibility["eligible_for_mediation"])
        self.assertEqual(len(suggestions["suggestions"]), 3)
        self.assertIn("Installment payment plan", suggestions["suggestions"][0]["title"])

    def test_additional_dispute_categories_are_valid_and_have_specific_suggestions(self):
        expected_titles = {
            "online_defamation": "Remove or correct online content",
            "neighbor_altercation": "Mutual non-aggression agreement",
            "harassment_unjust_vexation": "No-contact or limited-contact agreement",
            "business_defamation": "Correction or clarification agreement",
        }

        for category, expected_title in expected_titles.items():
            with self.subTest(category=category):
                case_information = CaseInformationPayload(dispute_category=category)
                bundle = make_bundle(dispute_category=case_information.dispute_category)
                route = SensitiveCaseRoutingService().evaluate(bundle)
                eligibility = MediationEligibilityService().evaluate(bundle, route)
                suggestions = MediationSuggestionService().generate(bundle, eligibility)

                self.assertTrue(eligibility["eligible_for_mediation"])
                self.assertEqual(len(suggestions["suggestions"]), 3)
                self.assertEqual(suggestions["suggestions"][0]["title"], expected_title)

    def test_emotion_analysis_detects_aggressive_terms(self):
        bundle = make_bundle(transcript="Speaker 2: Papatayin kita kung babalik ka.")
        emotion = EmotionAnalysisService().analyze(bundle)

        self.assertEqual(emotion["emotion_label"], "aggressive")
        self.assertIn("papatayin", emotion["detected_terms"])

    def test_evidence_upload_preserves_manual_notes_without_text_extraction(self):
        service = EvidenceFileService(Path(__file__).resolve().parent / "tmp_test_evidence")
        upload = SimpleNamespace(filename="receipt.txt", file=BytesIO(b"sample evidence file"))
        saved = service.save_upload("KP-2026-TEST", upload, "Receipt was reviewed by the lupon member.")

        self.assertEqual(saved["file_name"], "receipt.txt")
        self.assertEqual(saved["evidence_text"], "Receipt was reviewed by the lupon member.")
        self.assertEqual(saved["extracted_entities"], {})

    def test_hearing_schedule_cannot_be_in_past(self):
        with patch("phase3_services.get_phase2_bundle", return_value=True):
            with self.assertRaises(Exception) as raised:
                HearingService().validate(None, "KP-2026-TEST", "2020-01-01", "scheduled", "initial")

        self.assertIn("scheduled_date cannot be in the past", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
