import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from database import Base  # noqa: E402
from models import (  # noqa: E402
    AuditLog,
    CaseAnalysis,
    CaseInformation,
    ExtractedEntities,
    MediationEligibility,
    Phase3CaseRoute,
    Phase3OfficialDecision,
    Phase4FormPacket,
    Phase5ComplianceReview,
    Phase5GroundTruth,
    Phase5ValidationCase,
    Referral,
    Transcript,
    WorkflowDraft,
    XAITrace,
)
from phase5_schemas import Phase5ImportCaseRequest  # noqa: E402
from phase5_services import Phase5ValidationService  # noqa: E402


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed_finalized_workflow(db, *, status="completed", referral=True):
    case_id = "KP-2026-FINAL"
    transcript = Transcript(
        content="Complainant: Sinaktan po ako. Mediator: Itatala natin ang referral.",
        segments_json=[
            {"speaker": "Complainant", "start": 0, "end": 3, "text": "Sinaktan po ako."},
            {
                "speaker": "Barangay Secretary/Mediator",
                "start": 3,
                "end": 7,
                "text": "Itatala natin ang referral.",
            },
        ],
    )
    db.add(transcript)
    db.flush()
    case_info = CaseInformation(
        transcript_id=transcript.id,
        case_id=case_id,
        barangay_name="Barangay Uno",
        city_municipality="Santa Cruz",
        case_year=2026,
        case_type="civil",
        dispute_category="threat",
        complainant_residency="same_barangay",
        respondent_residency="same_barangay",
        debt_amount_php=0,
        maximum_penalty_years=0,
        fine_amount_php=0,
    )
    extracted = ExtractedEntities(
        transcript_id=transcript.id,
        entities_json={"speaker_roles": ["Complainant", "Barangay Secretary/Mediator"]},
    )
    trace = XAITrace(trace_json=["KP-COVER-01 Fired"], trace_text="KP-COVER-01 Fired")
    db.add_all([case_info, extracted, trace])
    db.flush()
    analysis = CaseAnalysis(
        transcript_id=transcript.id,
        case_information_id=case_info.id,
        extracted_entities_id=extracted.id,
        xai_trace_id=trace.id,
        detected_keywords_json={
            "detected_keywords": ["sinaktan"],
            "keyword_count": 1,
            "vawc_trigger": referral,
        },
        rule_results_json=[],
        jurisdiction_decision="outside_kp" if referral else "within_kp",
        exclusion_ground="sensitive referral" if referral else "none",
        confidence_level="high",
        missing_fields_json=[],
        recommended_next_action="Refer to Court" if referral else "Proceed to Mediation",
    )
    db.add(analysis)
    db.flush()

    route = "Refer to Court" if referral else "Proceed to Mediation"
    db.add(
        Phase3CaseRoute(
            case_id=case_id,
            is_sensitive=referral,
            sensitive_category="Threat" if referral else "None",
            recommended_route=route,
            reason="Test route",
            matched_keywords=["sinaktan"] if referral else [],
            confidence_level="high",
            blocking_mediation=referral,
        )
    )
    db.add(
        MediationEligibility(
            case_id=case_id,
            eligible_for_mediation=not referral,
            reason="Test eligibility",
            required_action=route,
        )
    )
    packet = Phase4FormPacket(
        case_id=case_id,
        source_phase3_action=route,
        selected_forms_json=["kp-form-20" if referral else "kp-form-7"],
        generated_form_count=1,
        missing_fields_json={},
        validation_status="ready",
        form_accuracy_pct=100,
        processing_time_min=2.5,
        generated_by="tester",
        approved_by="Barangay Secretary",
    )
    db.add(packet)
    db.flush()

    referral_record = None
    if referral:
        referral_record = Referral(
            case_id=case_id,
            referral_type="court",
            destination="Court or proper authority",
            reason="Threat indicator",
            matched_keywords=["sinaktan"],
            xai_reference=["KP-COVER-01 Fired"],
            status="completed",
        )
        db.add(referral_record)
        db.add(
            Phase3OfficialDecision(
                case_id=case_id,
                system_recommendation=route,
                official_decision="Referral confirmed sent to Court or proper authority",
                official_notes="Confirmed for testing.",
                approved_by="Barangay Secretary",
            )
        )
        db.flush()

    finalized = status == "completed"
    payload = {
        "caseInformation": {"case_id": case_id},
        "phase2Analysis": {
            "jurisdiction_decision": analysis.jurisdiction_decision,
            "detected_keywords": analysis.detected_keywords_json,
        },
        "completed": finalized,
        "outcome": "Referred to Court / Proper Authority" if referral else "Amicable Settlement Reached",
        "finalizedAt": "2026-08-15T10:00:00" if finalized else "",
        "phase4PacketId": packet.id,
        "phase3ReferralRequired": referral,
        "phase3RecommendedRoute": route,
        "referralResolution": (
            {
                "referralId": referral_record.id,
                "status": "completed",
                "destination": referral_record.destination,
            }
            if referral_record
            else None
        ),
    }
    draft = WorkflowDraft(
        workflow_id="workflow-finalized-test",
        owner_user_id=1,
        status=status,
        active_step=7 if finalized else 6,
        max_unlocked_step=7 if finalized else 6,
        case_id=case_id,
        transcript_id=transcript.id,
        case_analysis_id=analysis.id,
        payload_json=payload,
        revision=8,
    )
    db.add(draft)
    db.commit()
    return draft, analysis, packet, referral_record


class Phase5FinalizedWorkflowImportTests(unittest.TestCase):
    def test_lists_and_imports_exact_finalized_referral_workflow(self):
        db = make_session()
        try:
            draft, analysis, packet, _ = seed_finalized_workflow(db)
            service = Phase5ValidationService()

            candidates = service.finalized_workflow_candidates(db)
            self.assertEqual(len(candidates), 1)
            self.assertTrue(candidates[0]["eligible"])
            self.assertEqual(candidates[0]["workflow_id"], draft.workflow_id)
            self.assertEqual(candidates[0]["analysis_id"], analysis.id)
            self.assertTrue(candidates[0]["packet_ready"])
            self.assertTrue(candidates[0]["referral_ready"])
            self.assertTrue(candidates[0]["official_decision_ready"])

            imported = service.import_finalized_workflow(
                db,
                draft.workflow_id,
                Phase5ImportCaseRequest(
                    audio_id="FINAL-AUDIO-001",
                    dataset_split="validation",
                    speaker_gender_mix="mixed",
                    audio_quality="quiet",
                    manual_processing_time_min=15,
                ),
                actor="secretary",
            )

            validation = imported["validation_case"]
            self.assertEqual(validation["analysis_id"], analysis.id)
            self.assertEqual(validation["speaker_count"], 2)
            self.assertEqual(validation["system_processing_time_min"], packet.processing_time_min)
            self.assertTrue(imported["source_workflow"]["already_imported"])
            self.assertTrue(imported["source_workflow"]["eligible"])
            self.assertEqual(db.query(Phase5GroundTruth).count(), 1)
            self.assertEqual(db.query(Phase5ComplianceReview).count(), 1)
            audit = (
                db.query(AuditLog)
                .filter(AuditLog.action == "phase5_finalized_workflow_imported")
                .one()
            )
            self.assertEqual(audit.actor, "secretary")
            self.assertEqual(audit.details_json["workflow_id"], draft.workflow_id)
            self.assertEqual(audit.details_json["analysis_id"], analysis.id)
        finally:
            db.close()

    def test_active_workflow_is_not_importable(self):
        db = make_session()
        try:
            draft, _, _, _ = seed_finalized_workflow(db, status="active", referral=False)
            service = Phase5ValidationService()

            self.assertEqual(service.finalized_workflow_candidates(db), [])
            with self.assertRaises(HTTPException) as raised:
                service.import_finalized_workflow(db, draft.workflow_id, Phase5ImportCaseRequest())
            self.assertEqual(raised.exception.status_code, 409)
            self.assertIn("Workflow status is not completed.", raised.exception.detail["reasons"])
            self.assertEqual(db.query(Phase5ValidationCase).count(), 0)
        finally:
            db.close()

    def test_referral_and_packet_readiness_are_required(self):
        db = make_session()
        try:
            draft, _, packet, referral = seed_finalized_workflow(db)
            referral.status = "pending"
            packet.validation_status = "needs_review"
            db.query(Phase3OfficialDecision).delete()
            db.commit()

            source = Phase5ValidationService().workflow_import_readiness(db, draft)
            self.assertFalse(source["eligible"])
            self.assertFalse(source["packet_ready"])
            self.assertFalse(source["referral_ready"])
            self.assertFalse(source["official_decision_ready"])
            self.assertIn("The linked Phase 4 form packet is not ready.", source["ineligibility_reasons"])
            self.assertIn(
                "The required referral has not been verified as completed or officially cancelled.",
                source["ineligibility_reasons"],
            )
            self.assertIn(
                "The required official referral decision has not been saved.",
                source["ineligibility_reasons"],
            )
        finally:
            db.close()

    def test_officially_cancelled_referral_is_importable_after_finalization(self):
        db = make_session()
        try:
            draft, _, _, referral = seed_finalized_workflow(db)
            referral.status = "cancelled"
            payload = dict(draft.payload_json)
            payload["outcome"] = "Referral Cancelled - Case Closed After Official Review"
            payload["referralResolution"] = {
                "referralId": referral.id,
                "status": "cancelled",
                "destination": referral.destination,
                "cancellationReason": "The referral record was cancelled after official review.",
            }
            payload["phase3ReferralStatus"] = "cancelled"
            draft.payload_json = payload
            db.query(Phase3OfficialDecision).delete()
            db.commit()

            readiness = Phase5ValidationService().workflow_import_readiness(db, draft)

            self.assertTrue(readiness["eligible"])
            self.assertTrue(readiness["referral_ready"])
            self.assertTrue(readiness["official_decision_ready"])
            self.assertEqual(readiness["ineligibility_reasons"], [])
        finally:
            db.close()

    def test_rejects_stale_or_conflicting_analysis_provenance(self):
        db = make_session()
        try:
            draft, original, _, _ = seed_finalized_workflow(db, referral=False)
            copied = CaseAnalysis(
                transcript_id=original.transcript_id,
                case_information_id=original.case_information_id,
                extracted_entities_id=original.extracted_entities_id,
                xai_trace_id=original.xai_trace_id,
                detected_keywords_json=original.detected_keywords_json,
                rule_results_json=original.rule_results_json,
                jurisdiction_decision=original.jurisdiction_decision,
                exclusion_ground=original.exclusion_ground,
                confidence_level=original.confidence_level,
                missing_fields_json=original.missing_fields_json,
                recommended_next_action=original.recommended_next_action,
            )
            db.add(copied)
            db.flush()
            db.add(
                Phase5ValidationCase(
                    case_id=draft.case_id,
                    analysis_id=copied.id,
                    audio_id="existing-audio",
                    dataset_split="validation",
                    speaker_gender_mix="unspecified",
                    audio_quality="unspecified",
                    notes="",
                )
            )
            db.commit()

            readiness = Phase5ValidationService().workflow_import_readiness(db, draft)
            self.assertFalse(readiness["eligible"])
            self.assertTrue(
                any("newer Phase 2 analysis" in reason for reason in readiness["ineligibility_reasons"])
            )
            self.assertTrue(
                any("different Phase 2 analysis" in reason for reason in readiness["ineligibility_reasons"])
            )
        finally:
            db.close()

    def test_rejects_stale_phase4_packet_provenance(self):
        db = make_session()
        try:
            draft, _, packet, _ = seed_finalized_workflow(db, referral=False)
            db.add(
                Phase4FormPacket(
                    case_id=draft.case_id,
                    source_phase3_action="Proceed to Mediation",
                    selected_forms_json=["kp-form-7"],
                    generated_form_count=1,
                    missing_fields_json={},
                    validation_status="ready",
                    form_accuracy_pct=100,
                    processing_time_min=1.5,
                    generated_by="tester",
                    approved_by="Barangay Secretary",
                )
            )
            db.commit()

            readiness = Phase5ValidationService().workflow_import_readiness(db, draft)
            self.assertFalse(readiness["eligible"])
            self.assertFalse(readiness["packet_ready"])
            self.assertEqual(readiness["phase4_packet_id"], packet.id)
            self.assertTrue(
                any("newer Phase 4 form packet" in reason for reason in readiness["ineligibility_reasons"])
            )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
