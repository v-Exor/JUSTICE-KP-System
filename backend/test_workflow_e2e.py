import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from database import Base  # noqa: E402
from main import build_case_analysis_response, process_phase3_case, save_case_analysis  # noqa: E402
from models import Evidence, Transcript  # noqa: E402
from phase4_schemas import Phase4GeneratePacketRequest  # noqa: E402
from phase4_services import Phase4FormService  # noqa: E402
from schemas import AnalyzeCaseRequest, CaseInformationPayload, SaveCaseAnalysisRequest  # noqa: E402


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def case_info(case_id: str, **overrides):
    data = {
        "case_id": case_id,
        "barangay_name": "Barangay Uno",
        "city_municipality": "Santa Cruz",
        "case_year": 2026,
        "case_type": "civil",
        "dispute_category": "debt",
        "complainant_residency": "same_barangay",
        "respondent_residency": "same_barangay",
        "debt_amount_php": 3000,
        "maximum_penalty_years": 0,
        "fine_amount_php": 0,
        "government_party_involved": False,
        "already_filed_in_court": False,
        "has_vawc_or_child_abuse_indicators": False,
    }
    data.update(overrides)
    return CaseInformationPayload(**data)


class WorkflowE2ETests(unittest.TestCase):
    def analyze_save_and_route(self, db, case_id: str, transcript_text: str, **case_overrides):
        transcript = Transcript(content=transcript_text, segments_json=[])
        db.add(transcript)
        db.commit()
        db.refresh(transcript)

        analysis = build_case_analysis_response(
            AnalyzeCaseRequest(
                transcript_id=transcript.id,
                case_information=case_info(case_id, **case_overrides),
            ),
            db,
        )
        saved = save_case_analysis(SaveCaseAnalysisRequest(**analysis.model_dump()), db)
        dashboard = process_phase3_case(case_id, db)
        return analysis, saved, dashboard

    def generate_official_packet(self, db, case_id: str):
        with tempfile.TemporaryDirectory() as directory:
            service = Phase4FormService(Path(directory))
            recommendation = service.recommendation(db, case_id)
            packet = service.generate_packet(
                db,
                case_id,
                Phase4GeneratePacketRequest(generated_by="E2E Tester"),
            )
            response = service.packet_response(db, packet)
            generated_paths = list(Path(directory).glob("*.pdf"))

        return recommendation, response, generated_paths

    def test_normal_kp_flow_generates_phase4_mediation_packet(self):
        db = make_session()
        try:
            analysis, _, dashboard = self.analyze_save_and_route(
                db,
                "KP-2026-E2E-NORMAL",
                "Speaker 1: May utang po siya na 3000 pesos. Speaker 2: Payag akong bayaran sa hulugan.",
            )
            self.assertEqual(analysis.jurisdiction_decision, "within_kp")
            self.assertEqual(dashboard["phase3"]["final_recommended_action"], "Awaiting Evidence")

            db.add(
                Evidence(
                    case_id="KP-2026-E2E-NORMAL",
                    file_name="promissory-note.pdf",
                    file_type="application/pdf",
                    file_path="/e2e/promissory-note.pdf",
                    ocr_text="Promissory note for 3000 pesos.",
                    extracted_entities_json={},
                )
            )
            db.commit()

            recommendation, packet, files = self.generate_official_packet(db, "KP-2026-E2E-NORMAL")
            self.assertEqual(recommendation["final_recommended_action"], "Proceed to Mediation")
            self.assertEqual(packet["source_phase3_action"], "Proceed to Mediation")
            self.assertEqual(packet["selected_forms"], ["kp-form-7", "kp-form-8", "kp-form-16"])
            self.assertEqual(packet["generated_form_count"], 3)
            self.assertEqual(len(files), 3)
        finally:
            db.close()

    def test_vawc_referral_flow_generates_only_backend_phase4_packet(self):
        db = make_session()
        try:
            analysis, _, dashboard = self.analyze_save_and_route(
                db,
                "KP-2026-E2E-VAWC",
                "Speaker 2: Sinaktan po ako at binantaan ng asawa ko.",
                case_type="criminal",
                dispute_category="physical_injury",
            )
            self.assertEqual(analysis.jurisdiction_decision, "refer_to_pnp_wcpc_or_authority")
            self.assertTrue(analysis.detected_keywords["vawc_trigger"])
            self.assertEqual(dashboard["phase3"]["final_recommended_action"], "Refer to PNP WCPD")

            recommendation, packet, files = self.generate_official_packet(db, "KP-2026-E2E-VAWC")
            self.assertEqual(recommendation["recommended_forms"][0]["form_id"], "kp-form-20-a")
            self.assertEqual(packet["source_phase3_action"], "Refer to PNP WCPD")
            self.assertEqual(packet["selected_forms"], ["kp-form-20-a"])
            self.assertEqual(packet["generated_form_count"], 1)
            self.assertEqual(len(files), 1)
        finally:
            db.close()

    def test_outside_kp_flow_generates_referral_packet(self):
        db = make_session()
        try:
            analysis, _, dashboard = self.analyze_save_and_route(
                db,
                "KP-2026-E2E-OUTSIDE",
                "Speaker 1: May reklamo po kami tungkol sa bayarin ng opisina.",
                government_party_involved=True,
            )
            self.assertEqual(analysis.jurisdiction_decision, "outside_kp")
            self.assertEqual(analysis.exclusion_ground, "government_party")
            self.assertEqual(dashboard["phase3"]["final_recommended_action"], "Refer to Court")

            recommendation, packet, files = self.generate_official_packet(db, "KP-2026-E2E-OUTSIDE")
            self.assertEqual([item["form_id"] for item in recommendation["recommended_forms"]], ["kp-form-20", "kp-form-20-a"])
            self.assertEqual(packet["source_phase3_action"], "Refer to Court")
            self.assertEqual(packet["selected_forms"], ["kp-form-20", "kp-form-20-a"])
            self.assertEqual(packet["generated_form_count"], 2)
            self.assertEqual(len(files), 2)
        finally:
            db.close()

    def test_manual_review_flow_generates_manual_review_packet(self):
        db = make_session()
        try:
            analysis, _, dashboard = self.analyze_save_and_route(
                db,
                "KP-2026-E2E-MANUAL",
                "Speaker 1: May reklamo po ako pero kailangan pang alamin ang posibleng parusa.",
                case_type="criminal",
                dispute_category="other",
                penalty_lookup_required=True,
            )
            self.assertEqual(analysis.jurisdiction_decision, "ambiguous_manual_review")
            self.assertEqual(analysis.exclusion_ground, "penalty_lookup_required")
            self.assertEqual(dashboard["phase3"]["final_recommended_action"], "Manual Review")

            recommendation, packet, files = self.generate_official_packet(db, "KP-2026-E2E-MANUAL")
            self.assertEqual([item["form_id"] for item in recommendation["recommended_forms"]], ["kp-form-7"])
            self.assertEqual(packet["source_phase3_action"], "Manual Review")
            self.assertEqual(packet["selected_forms"], ["kp-form-7"])
            self.assertEqual(packet["generated_form_count"], 1)
            self.assertEqual(len(files), 1)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
