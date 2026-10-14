import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from database import Base  # noqa: E402
from models import (  # noqa: E402
    AuditLog,
    CaseAnalysis,
    CaseInformation,
    ExtractedEntities,
    KPResearchDataset,
    MediationEligibility,
    Phase3CaseRoute,
    Phase4FormPacket,
    Phase5ComplianceReview,
    Phase5EvaluationResult,
    Phase5GroundTruth,
    Phase5ValidationCase,
    Transcript,
    XAITrace,
)
from phase5_schemas import (  # noqa: E402
    Phase5ComplianceReviewRequest,
    Phase5ExperimentRunRequest,
    Phase5GroundTruthRequest,
    Phase5ImportCaseRequest,
)
from phase5_services import Phase5ValidationService  # noqa: E402


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed_case(db):
    transcript = Transcript(
        content="Speaker 1: May utang po siya. Speaker 2: Payag po ako sa hulugan.",
        segments_json=[
            {"speaker": "Speaker 1", "start": 0, "end": 2, "text": "May utang po siya."},
            {"speaker": "Speaker 2", "start": 2, "end": 4, "text": "Payag po ako sa hulugan."},
        ],
    )
    case_info = CaseInformation(
        transcript_id=1,
        case_id="KP-2026-P5",
        barangay_name="Brgy 1 Santa Cruz",
        city_municipality="Santa Cruz",
        case_year=2026,
        case_type="civil",
        dispute_category="debt",
        complainant_residency="same_barangay",
        respondent_residency="same_barangay",
        debt_amount_php=5000,
        maximum_penalty_years=0,
        fine_amount_php=0,
    )
    extracted = ExtractedEntities(
        transcript_id=1,
        entities_json={"speaker_roles": ["Speaker 1", "Speaker 2"]},
    )
    trace = XAITrace(trace_json=["R01 Fired", "R09 Fired"], trace_text="R01 Fired\nR09 Fired")
    db.add_all([transcript, case_info, extracted, trace])
    db.flush()
    analysis = CaseAnalysis(
        transcript_id=transcript.id,
        case_information_id=case_info.id,
        extracted_entities_id=extracted.id,
        xai_trace_id=trace.id,
        detected_keywords_json={"detected_keywords": [], "keyword_count": 0, "vawc_trigger": False},
        rule_results_json=[],
        jurisdiction_decision="within_kp",
        exclusion_ground="none",
        confidence_level="high",
        missing_fields_json=[],
        recommended_next_action="Proceed with Katarungang Pambarangay mediation and document the case analysis.",
    )
    db.add(analysis)
    db.flush()
    db.add(
        Phase3CaseRoute(
            case_id="KP-2026-P5",
            is_sensitive=False,
            sensitive_category="None",
            recommended_route="Proceed to Mediation",
            reason="No blocking rule fired.",
            matched_keywords=[],
            confidence_level="medium",
            blocking_mediation=False,
        )
    )
    db.add(
        MediationEligibility(
            case_id="KP-2026-P5",
            eligible_for_mediation=True,
            reason="Case is within KP jurisdiction.",
            required_action="Generate Mediation Options",
        )
    )
    db.add(
        Phase4FormPacket(
            case_id="KP-2026-P5",
            source_phase3_action="Proceed to Mediation",
            selected_forms_json=["kp-form-7"],
            generated_form_count=1,
            missing_fields_json={},
            validation_status="ready",
            form_accuracy_pct=100,
            processing_time_min=4.23,
            generated_by="tester",
            approved_by="Lupon Chair",
        )
    )
    db.add(AuditLog(case_id="KP-2026-P5", action="seeded", actor="tester", details_json={}))
    db.commit()


class Phase5ServiceTests(unittest.TestCase):
    def test_incomplete_ground_truth_stays_pending_and_can_be_removed_safely(self):
        db = make_session()
        try:
            seed_case(db)
            service = Phase5ValidationService()
            imported = service.import_case(
                db,
                "KP-2026-P5",
                Phase5ImportCaseRequest(audio_id="AUDIO-PENDING"),
            )

            self.assertEqual(imported["review_status"], "needs_ground_truth")
            self.assertFalse(imported["ground_truth_ready"])
            self.assertTrue(imported["can_delete"])
            self.assertIn("jurisdiction_decision", imported["ground_truth_missing_fields"])
            with self.assertRaises(HTTPException) as incomplete:
                service.evaluate_case(db, "KP-2026-P5")
            self.assertEqual(incomplete.exception.status_code, 400)
            self.assertEqual(service.evaluate_all(db), [])

            removed = service.delete_pending_case(db, "KP-2026-P5", actor="admin")

            self.assertEqual(removed["status"], "removed")
            self.assertEqual(db.query(Phase5ValidationCase).count(), 0)
            self.assertEqual(db.query(Phase5GroundTruth).count(), 0)
            self.assertEqual(db.query(Phase5ComplianceReview).count(), 0)
            self.assertEqual(db.query(Phase5EvaluationResult).count(), 0)
            self.assertEqual(db.query(KPResearchDataset).count(), 0)
            self.assertEqual(db.query(CaseAnalysis).count(), 1)
            self.assertEqual(db.query(Transcript).count(), 1)
            self.assertEqual(
                db.query(AuditLog).filter(AuditLog.action == "phase5_pending_case_removed").count(),
                1,
            )
        finally:
            db.close()

    def test_import_ground_truth_evaluate_and_metrics(self):
        db = make_session()
        try:
            seed_case(db)
            service = Phase5ValidationService()
            imported = service.import_case(
                db,
                "KP-2026-P5",
                Phase5ImportCaseRequest(
                    audio_id="AUDIO-P5",
                    speaker_gender_mix="mixed",
                    audio_quality="quiet",
                    manual_processing_time_min=45,
                ),
            )

            self.assertEqual(imported["case_id"], "KP-2026-P5")
            self.assertEqual(imported["system_outputs"]["jurisdiction_decision"], "within_kp")

            service.update_ground_truth(
                db,
                "KP-2026-P5",
                Phase5GroundTruthRequest(
                    expected_covered_under_kp=True,
                    expected_jurisdiction_decision="within_kp",
                    expected_exclusion_ground="none",
                    expected_sensitive_case=False,
                    expected_referral_route="Proceed to Mediation",
                    expected_mediation_eligible=True,
                    expected_form_ids=["kp-form-7"],
                    expected_speaker_count=2,
                    reviewer_name="researcher",
                ),
            )
            service.update_compliance(
                db,
                "KP-2026-P5",
                Phase5ComplianceReviewRequest(
                    consent_confirmed=True,
                    transcript_anonymized=True,
                    official_decision_saved=True,
                    generated_forms_reviewed=True,
                    audit_trail_complete=True,
                    sensitive_case_referred=True,
                    reviewer_name="researcher",
                ),
            )
            result = service.evaluate_case(db, "KP-2026-P5")
            metrics = service.metrics(db)

            self.assertTrue(result["overall_correct"])
            self.assertEqual(result["time_saved_min"], 40.77)
            self.assertEqual(result["compliance_score"], 100)
            self.assertEqual(metrics["case_count"], 1)
            self.assertEqual(metrics["overall_accuracy_pct"], 100)
            self.assertEqual(metrics["average_time_saved_pct"], 90.6)
            refreshed = service.validation_cases(db)[0]
            self.assertEqual(refreshed["review_status"], "evaluated")
            self.assertFalse(refreshed["can_delete"])
            with self.assertRaises(HTTPException) as protected_result:
                service.delete_pending_case(db, "KP-2026-P5")
            self.assertEqual(protected_result.exception.status_code, 409)
        finally:
            db.close()

    def test_csv_export_and_experiment_run(self):
        db = make_session()
        try:
            seed_case(db)
            service = Phase5ValidationService()
            service.import_case(db, "KP-2026-P5", Phase5ImportCaseRequest(manual_processing_time_min=45))
            service.update_ground_truth(
                db,
                "KP-2026-P5",
                Phase5GroundTruthRequest(
                    expected_covered_under_kp=True,
                    expected_jurisdiction_decision="within_kp",
                    expected_exclusion_ground="none",
                    expected_sensitive_case=False,
                    expected_referral_route="Proceed to Mediation",
                    expected_mediation_eligible=True,
                    expected_form_ids=["kp-form-7"],
                    expected_speaker_count=2,
                    reviewer_name="researcher",
                ),
            )
            service.evaluate_case(db, "KP-2026-P5")
            csv_text = service.csv_export(db)
            pdf_bytes = service.report_pdf(db)
            run = service.create_experiment_run(
                db,
                Phase5ExperimentRunRequest(name="Initial thesis validation", created_by="tester"),
            )

            self.assertIn("case_id,dispute_category", csv_text)
            self.assertIn("KP-2026-P5", csv_text)
            self.assertTrue(pdf_bytes.startswith(b"%PDF-1.4"))
            self.assertIn(b"%%EOF", pdf_bytes)
            self.assertEqual(run["case_count"], 1)
            self.assertEqual(run["metrics_json"]["jurisdiction_accuracy_pct"], 100)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
