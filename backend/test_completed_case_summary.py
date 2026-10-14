import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from auth_schemas import UserCreateRequest  # noqa: E402
from auth_service import AuthContext, create_user, seed_roles_and_dev_admin  # noqa: E402
from database import Base  # noqa: E402
from main import completed_case_summary  # noqa: E402
from models import (  # noqa: E402
    CaseAnalysis,
    CaseInformation,
    ExtractedEntities,
    Phase3CaseRoute,
    Phase4FormPacket,
    Role,
    Transcript,
    User,
    WorkflowDraft,
    XAITrace,
)


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def make_context(db, username="admin", role_name="system_admin"):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        admin = db.query(User).filter(User.username == "admin").first()
        admin_role = db.query(Role).filter(Role.name == "system_admin").first()
        user = create_user(
            db,
            UserCreateRequest(
                username=username,
                full_name=username.title(),
                role_name=role_name,
                password="StrongPassword123!",
            ),
            AuthContext(user=admin, role=admin_role, session=None, csrf_token=""),
        )
    role = db.query(Role).filter(Role.name == user.role_name).one()
    return AuthContext(user=user, role=role, session=None, csrf_token="")


def add_analysis(db, case_id, decision, transcript_text, sensitive=False, created_at=None, recording_type="blotter_case", segments=None):
    transcript = Transcript(
        content=transcript_text,
        raw_content=transcript_text,
        recording_type=recording_type,
        save_context="hearing" if recording_type == "blotter_hearing" else "intake",
        segments_json=segments,
    )
    db.add(transcript)
    db.flush()
    case_info = CaseInformation(
        transcript_id=transcript.id,
        case_id=case_id,
        barangay_name="Barangay Uno",
        city_municipality="Santa Cruz",
        case_type="civil",
        dispute_category="family_dispute" if sensitive else "debt",
        complainant_residency="same_barangay",
        respondent_residency="same_barangay",
        has_vawc_or_child_abuse_indicators=sensitive,
        next_of_kin_assistant_name="Protected Person" if sensitive else "",
    )
    entities = ExtractedEntities(transcript_id=transcript.id, entities_json={"people": ["Protected Person"]})
    trace = XAITrace(trace_json=[f"Exact trace for {decision}"], trace_text=f"Exact trace for {decision}")
    db.add_all([case_info, entities, trace])
    db.flush()
    analysis = CaseAnalysis(
        transcript_id=transcript.id,
        case_information_id=case_info.id,
        extracted_entities_id=entities.id,
        xai_trace_id=trace.id,
        detected_keywords_json={"vawc_trigger": sensitive, "detected_keywords": ["protected"] if sensitive else []},
        rule_results_json=[{"decision": decision}],
        jurisdiction_decision=decision,
        exclusion_ground="sensitive referral" if sensitive else "none",
        confidence_level="high",
        missing_fields_json=[],
        recommended_next_action="Refer to PNP WCPD" if sensitive else "Proceed to Mediation",
        created_at=created_at or datetime.utcnow(),
    )
    db.add(analysis)
    db.flush()
    return analysis


class CompletedCaseSummaryTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed_roles_and_dev_admin(self.db)

    def tearDown(self):
        self.db.close()

    def add_completed_workflow(self, owner, workflow_id, analysis, packet_id=None, payload_overrides=None):
        now = datetime.utcnow()
        payload = {
            "outcome": "Amicable Settlement Reached",
            "caseRecordStatus": "Amicable Settlement Reached",
            "finalizedAt": now.isoformat(),
            "phase4PacketId": packet_id,
        }
        payload.update(payload_overrides or {})
        workflow = WorkflowDraft(
            workflow_id=workflow_id,
            owner_user_id=owner.user.id,
            status="completed",
            active_step=7,
            max_unlocked_step=7,
            case_id=self.db.query(CaseInformation).filter(CaseInformation.id == analysis.case_information_id).one().case_id,
            transcript_id=analysis.transcript_id,
            case_analysis_id=analysis.id,
            payload_json=payload,
            created_at=analysis.created_at - timedelta(minutes=1),
            updated_at=now,
        )
        self.db.add(workflow)
        self.db.commit()
        return workflow

    def test_uses_workflows_exact_analysis_and_packet_ids(self):
        admin = make_context(self.db)
        case_id = "KP-2026-EXACT"
        add_analysis(self.db, case_id, "outside_kp", "Older transcript", created_at=datetime.utcnow() - timedelta(hours=2))
        exact = add_analysis(self.db, case_id, "within_kp", "Exact transcript", created_at=datetime.utcnow() - timedelta(hours=1))
        chosen_packet = Phase4FormPacket(
            case_id=case_id,
            source_phase3_action="Proceed to Mediation",
            selected_forms_json=["kp-form-16"],
            generated_form_count=0,
            missing_fields_json={},
            validation_status="ready",
            form_accuracy_pct=100,
            processing_time_min=0.1,
            generated_by="Secretary",
        )
        newer_packet = Phase4FormPacket(
            case_id=case_id,
            source_phase3_action="Refer to Court",
            selected_forms_json=["kp-form-20"],
            generated_form_count=0,
            missing_fields_json={},
            validation_status="ready",
            form_accuracy_pct=100,
            processing_time_min=0.1,
            generated_by="Secretary",
        )
        self.db.add_all([chosen_packet, newer_packet])
        self.db.flush()
        self.add_completed_workflow(admin, "workflow-exact", exact, chosen_packet.id)

        result = completed_case_summary("workflow-exact", admin, self.db)

        self.assertEqual(result["workflow"]["case_analysis_id"], exact.id)
        self.assertEqual(result["phase2_analysis"]["jurisdiction_decision"], "within_kp")
        self.assertEqual(result["transcript"]["content"], "Exact transcript")
        self.assertEqual(result["phase4_packet"]["id"], chosen_packet.id)
        self.assertNotEqual(result["phase4_packet"]["id"], newer_packet.id)

    def test_phase3_summary_uses_finalized_workflow_record_snapshot(self):
        admin = make_context(self.db)
        case_id = "KP-2026-DUPLICATE-SUMMARY"
        first_analysis = add_analysis(
            self.db,
            case_id,
            "within_kp",
            "First workflow transcript",
            created_at=datetime.utcnow() - timedelta(hours=2),
        )
        second_analysis = add_analysis(
            self.db,
            case_id,
            "outside_kp",
            "Second workflow transcript",
            created_at=datetime.utcnow() - timedelta(hours=1),
        )
        first_route = Phase3CaseRoute(
            case_id=case_id,
            is_sensitive=False,
            sensitive_category="None",
            recommended_route="Proceed to Mediation",
            reason="First exact route",
            matched_keywords=[],
            confidence_level="high",
            blocking_mediation=False,
        )
        second_route = Phase3CaseRoute(
            case_id=case_id,
            is_sensitive=False,
            sensitive_category="Outside KP",
            recommended_route="Refer to Court",
            reason="Second exact route",
            matched_keywords=[],
            confidence_level="high",
            blocking_mediation=True,
        )
        self.db.add_all([first_route, second_route])
        self.db.flush()
        first_workflow = self.add_completed_workflow(
            admin,
            "workflow-duplicate-summary-one",
            first_analysis,
            payload_overrides={"phase3RecordIds": {"sensitive_routing": first_route.id}},
        )
        second_workflow = self.add_completed_workflow(
            admin,
            "workflow-duplicate-summary-two",
            second_analysis,
            payload_overrides={"phase3RecordIds": {"sensitive_routing": second_route.id}},
        )

        first_summary = completed_case_summary(first_workflow.workflow_id, admin, self.db)
        second_summary = completed_case_summary(second_workflow.workflow_id, admin, self.db)

        self.assertEqual(
            first_summary["phase3_routing"]["sensitive_routing"]["id"],
            first_route.id,
        )
        self.assertEqual(
            second_summary["phase3_routing"]["sensitive_routing"]["id"],
            second_route.id,
        )
        self.assertEqual(first_summary["phase3_routing"]["recommended_route"], "Proceed to Mediation")
        self.assertEqual(second_summary["phase3_routing"]["recommended_route"], "Refer to Court")

    def test_sensitive_case_is_redacted_for_role_without_sensitive_access(self):
        viewer = make_context(self.db, "caseviewer", "viewer")
        analysis = add_analysis(self.db, "KP-2026-PROTECTED", "outside_kp", "Protected complainant narrative", sensitive=True)
        self.db.add(
            Phase3CaseRoute(
                case_id="KP-2026-PROTECTED",
                is_sensitive=True,
                sensitive_category="VAWC",
                recommended_route="Refer to PNP WCPD",
                reason="Protected reason",
                matched_keywords=["protected"],
                confidence_level="high",
                blocking_mediation=True,
            )
        )
        self.db.flush()
        self.add_completed_workflow(viewer, "workflow-protected", analysis)

        result = completed_case_summary("workflow-protected", viewer, self.db)

        self.assertTrue(result["privacy"]["is_sensitive"])
        self.assertTrue(result["privacy"]["redacted"])
        self.assertEqual(result["transcript"]["content"], "")
        self.assertIsNone(result["case_information"]["complainant_residency"])
        self.assertIsNone(result["case_information"]["next_of_kin_assistant_name"])
        self.assertEqual(result["phase3_routing"]["sensitive_routing"]["matched_keywords"], [])
        self.assertEqual(result["phase3_routing"]["sensitive_routing"]["reason"], "Protected")
        self.assertEqual(result["jurisdiction"]["exclusion_ground"], "Protected")
        self.assertFalse(result["actions"]["can_download_transcript_pdf"])
        self.assertFalse(result["actions"]["can_download_forms"])

    def test_non_admin_cannot_read_another_owners_record(self):
        owner = make_context(self.db, "owner", "barangay_secretary")
        other = make_context(self.db, "other", "viewer")
        analysis = add_analysis(self.db, "KP-2026-PRIVATE", "within_kp", "Owner transcript")
        self.add_completed_workflow(owner, "workflow-owned", analysis)

        with self.assertRaises(HTTPException) as raised:
            completed_case_summary("workflow-owned", other, self.db)

        self.assertEqual(raised.exception.status_code, 404)

    def test_hearing_summary_declares_all_three_participant_roles(self):
        admin = make_context(self.db)
        analysis = add_analysis(
            self.db,
            "KP-2026-HEARING",
            "within_kp",
            "Barangay Secretary/Mediator: Hearing opened.\nComplainant: I confirm my complaint.",
            recording_type="blotter_hearing",
            segments=[
                {"speaker": "Barangay Secretary/Mediator", "start": 0, "end": 2, "text": "Hearing opened."},
                {"speaker": "Complainant", "start": 2, "end": 4, "text": "I confirm my complaint."},
            ],
        )
        self.add_completed_workflow(admin, "workflow-hearing", analysis)

        result = completed_case_summary("workflow-hearing", admin, self.db)

        self.assertEqual(result["transcript"]["recording_type"], "blotter_hearing")
        self.assertEqual(
            result["transcript"]["participant_roles"],
            ["Barangay Secretary/Mediator", "Complainant", "Respondent"],
        )
        respondent = result["transcript"]["participant_transcripts"][2]
        self.assertEqual(respondent["role"], "Respondent")
        self.assertEqual(respondent["segment_count"], 0)

    def test_blotter_recording_summary_uses_two_participant_roles(self):
        admin = make_context(self.db)
        analysis = add_analysis(
            self.db,
            "KP-2026-BLOTTER",
            "within_kp",
            "Barangay Secretary/Mediator: State your concern.\nComplainant: My statement.",
            recording_type="blotter_case",
        )
        self.add_completed_workflow(admin, "workflow-blotter", analysis)

        result = completed_case_summary("workflow-blotter", admin, self.db)

        self.assertEqual(result["transcript"]["recording_type"], "blotter_case")
        self.assertEqual(
            result["transcript"]["participant_roles"],
            ["Barangay Secretary/Mediator", "Complainant"],
        )


if __name__ == "__main__":
    unittest.main()
