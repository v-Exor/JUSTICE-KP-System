import sys
import tempfile
import unittest
from datetime import datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import HTTPException, UploadFile  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from auth_schemas import UserCreateRequest  # noqa: E402
from auth_service import AuthContext, create_user, seed_roles_and_dev_admin  # noqa: E402
from database import Base  # noqa: E402
from main import (  # noqa: E402
    CANCELLED_REFERRAL_OUTCOME,
    WorkflowDraftCreateRequest,
    WorkflowDraftUpdateRequest,
    WorkflowFinalizeIntakeRequest,
    WorkflowFinalizeOutcomeRequest,
    WorkflowPhase2AnalysisRequest,
    WorkflowReferralActionRequest,
    complete_workflow_draft,
    create_workflow_draft,
    delete_workflow_draft,
    delete_transcript,
    finalize_workflow_intake,
    finalize_workflow_outcome,
    get_workflow_draft,
    get_paginated_finalized_workflow_cases,
    list_workflow_drafts,
    list_finalized_workflow_cases,
    process_phase3_pipeline,
    resolve_workflow_referral,
    run_workflow_phase2_analysis,
    update_workflow_draft,
    upload_audio,
)
from models import AuditLog, CaseInformation, Phase3OfficialDecision, Phase4FormPacket, Referral, Role, Transcript, User, WorkflowDraft  # noqa: E402
from schemas import CaseInformationPayload  # noqa: E402


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
    role = db.query(Role).filter(Role.name == user.role_name).first()
    return AuthContext(user=user, role=role, session=None, csrf_token="")


def case_info(**overrides):
    data = {
        "case_id": "KP-2026-DRAFT",
        "barangay_name": "Barangay Uno",
        "city_municipality": "Santa Cruz",
        "case_year": 2026,
        "case_type": "criminal",
        "dispute_category": "physical_injury",
        "complainant_residency": "same_barangay",
        "respondent_residency": "same_barangay",
        "debt_amount_php": 0,
        "maximum_penalty_years": 0,
        "fine_amount_php": 0,
        "government_party_involved": False,
        "already_filed_in_court": False,
        "has_vawc_or_child_abuse_indicators": False,
    }
    data.update(overrides)
    return CaseInformationPayload(**data)


class WorkflowDraftTests(unittest.TestCase):
    def test_draft_list_search_pagination_and_ownership(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            admin = make_context(db)
            secretary = make_context(db, username="secretary", role_name="barangay_secretary")
            other = make_context(db, username="other", role_name="barangay_secretary")
            created_at = datetime(2026, 9, 18, 12, 0, 0)
            updated_at = datetime(2026, 9, 19, 12, 0, 0)

            for index in range(12):
                db.add(
                    WorkflowDraft(
                        workflow_id=f"secretary-{index}",
                        owner_user_id=secretary.user.id,
                        status="active",
                        active_step=3 if index % 2 == 0 else 1,
                        max_unlocked_step=3 if index % 2 == 0 else 1,
                        case_id=f"KP-2026-{index:04d}",
                        payload_json={"caseInformation": {"case_id": f"KP-2026-{index:04d}"}},
                        created_at=created_at,
                        updated_at=updated_at,
                    )
                )
            db.add(
                WorkflowDraft(
                    workflow_id="other-draft",
                    owner_user_id=other.user.id,
                    status="active",
                    active_step=7,
                    max_unlocked_step=7,
                    case_id="KP-OTHER-0001",
                    payload_json={"caseInformation": {"case_id": "KP-OTHER-0001"}},
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
            db.commit()

            first_page = list_workflow_drafts("active", secretary, db, "", 1, 5)
            last_page = list_workflow_drafts("active", secretary, db, "", 3, 5)
            self.assertEqual(first_page["total"], 12)
            self.assertEqual(first_page["total_pages"], 3)
            self.assertEqual(len(first_page["items"]), 5)
            self.assertEqual(len(last_page["items"]), 2)
            self.assertEqual(
                [item["case_id"] for item in first_page["items"]],
                [f"KP-2026-{index:04d}" for index in range(5)],
            )
            self.assertEqual(
                [item["case_id"] for item in last_page["items"]],
                ["KP-2026-0010", "KP-2026-0011"],
            )
            self.assertTrue(all(item["owner"] is None for item in first_page["items"]))

            case_match = list_workflow_drafts("active", secretary, db, "0007", 1, 10)
            self.assertEqual([item["case_id"] for item in case_match["items"]], ["KP-2026-0007"])

            stage_match = list_workflow_drafts("active", secretary, db, "hearing", 1, 10)
            self.assertEqual(stage_match["total"], 6)
            self.assertTrue(all(item["current_stage"]["id"] == 2 for item in stage_match["items"]))

            admin_page = list_workflow_drafts("active", admin, db, "", 1, 50)
            self.assertEqual(admin_page["total"], 13)
            self.assertTrue(all(item["owner"] for item in admin_page["items"]))

            newest = last_page["items"][-1]
            delete_workflow_draft(newest["workflow_id"], secretary, db)
            recovered_page = list_workflow_drafts("active", secretary, db, "", 3, 5)
            self.assertEqual(recovered_page["total"], 11)
            self.assertEqual(recovered_page["page"], 3)
            self.assertEqual(len(recovered_page["items"]), 1)
        finally:
            db.close()

    def test_cases_pagination_filters_before_count_and_keeps_duplicate_case_ids(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            owner_context = make_context(db, username="secretary", role_name="barangay_secretary")
            other_context = make_context(db, username="viewer", role_name="viewer")
            updated_at = datetime(2026, 9, 18, 12, 0, 0)

            for index in range(12):
                case_id = "KP-DUPLICATE" if index < 2 else f"KP-2026-{index:04d}"
                is_referral = index % 2 == 1
                outcome = "Referral Packet Issued" if is_referral else "Amicable Settlement Reached"
                db.add(
                    WorkflowDraft(
                        workflow_id=f"owned-{index}",
                        owner_user_id=owner_context.user.id,
                        status="completed",
                        active_step=7,
                        max_unlocked_step=7,
                        case_id=case_id,
                        payload_json={
                            "finalizedAt": "2026-09-18T12:00:00",
                            "outcome": outcome,
                            "phase3ReferralRequired": is_referral,
                            "caseInformation": {
                                "case_id": case_id,
                                "dispute_category": "property",
                            },
                        },
                        updated_at=updated_at,
                    )
                )

            for index in range(3):
                db.add(
                    WorkflowDraft(
                        workflow_id=f"other-{index}",
                        owner_user_id=other_context.user.id,
                        status="completed",
                        active_step=7,
                        max_unlocked_step=7,
                        case_id=f"KP-OTHER-{index}",
                        payload_json={
                            "finalizedAt": "2026-09-18T12:00:00",
                            "outcome": "Amicable Settlement Reached",
                            "caseInformation": {"case_id": f"KP-OTHER-{index}"},
                        },
                        updated_at=updated_at,
                    )
                )
            db.commit()

            pages = [
                get_paginated_finalized_workflow_cases("", "", "", page, 5, owner_context, db)
                for page in (1, 2, 3)
            ]
            workflow_ids = [item["workflow_id"] for result in pages for item in result["items"]]
            self.assertEqual(len(workflow_ids), 12)
            self.assertEqual(len(set(workflow_ids)), 12)
            self.assertEqual(workflow_ids, [f"owned-{index}" for index in range(11, -1, -1)])
            self.assertEqual(pages[0]["total"], 12)
            self.assertEqual(pages[0]["total_pages"], 3)
            self.assertNotIn("other-0", workflow_ids)

            duplicates = get_paginated_finalized_workflow_cases(
                "duplicate", "", "", 1, 10, owner_context, db
            )
            self.assertEqual(duplicates["total"], 2)
            self.assertEqual([item["id"] for item in duplicates["items"]], ["KP-DUPLICATE"] * 2)
            self.assertTrue(all(item["duplicate_case_id"] for item in duplicates["items"]))

            referrals = get_paginated_finalized_workflow_cases(
                "", "Referral Packet Issued", "referral", 1, 10, owner_context, db
            )
            self.assertEqual(referrals["total"], 6)
            self.assertTrue(all(item["route"] == "referral" for item in referrals["items"]))

            recovered = get_paginated_finalized_workflow_cases(
                "", "", "", 99, 5, owner_context, db
            )
            self.assertEqual(recovered["page"], 3)
            self.assertEqual(len(recovered["items"]), 2)
        finally:
            db.close()

    def test_delete_workflow_draft_removes_only_selected_draft(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            first = create_workflow_draft(WorkflowDraftCreateRequest(), context, db)
            second = create_workflow_draft(WorkflowDraftCreateRequest(), context, db)
            transcript = Transcript(content="Saved independently", segments_json=[])
            case_record = CaseInformation(
                case_id=first["case_id"],
                barangay_name="Barangay Uno",
                city_municipality="Santa Cruz",
                case_year=2026,
                case_type="civil",
                dispute_category="property",
            )
            db.add_all([transcript, case_record])
            db.commit()
            transcript_id = transcript.id
            case_record_id = case_record.id
            linked_draft = db.query(WorkflowDraft).filter(WorkflowDraft.workflow_id == first["workflow_id"]).one()
            linked_draft.transcript_id = transcript_id
            db.commit()

            result = delete_workflow_draft(first["workflow_id"], context, db)

            self.assertEqual(result["workflow_id"], first["workflow_id"])
            self.assertIsNone(db.query(WorkflowDraft).filter(WorkflowDraft.workflow_id == first["workflow_id"]).first())
            self.assertIsNotNone(db.query(WorkflowDraft).filter(WorkflowDraft.workflow_id == second["workflow_id"]).first())
            self.assertIsNotNone(db.query(Transcript).filter(Transcript.id == transcript_id).first())
            self.assertIsNotNone(db.query(CaseInformation).filter(CaseInformation.id == case_record_id).first())
            with self.assertRaises(HTTPException) as raised:
                get_workflow_draft(first["workflow_id"], context, db)
            self.assertEqual(raised.exception.status_code, 404)
        finally:
            db.close()

    def test_delete_transcript_detaches_linked_draft(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            transcript = Transcript(content="Incorrect transcript", segments_json=[])
            db.add(transcript)
            db.commit()
            db.refresh(transcript)
            transcript_id = transcript.id
            created = create_workflow_draft(
                WorkflowDraftCreateRequest(payload={"transcriptId": transcript_id}),
                context,
                db,
            )
            draft = db.query(WorkflowDraft).filter(WorkflowDraft.workflow_id == created["workflow_id"]).first()
            draft.transcript_id = transcript_id
            db.commit()

            result = delete_transcript(transcript_id, context, db)
            db.refresh(draft)

            self.assertEqual(result["id"], transcript_id)
            self.assertIsNone(db.query(Transcript).filter(Transcript.id == transcript_id).first())
            self.assertIsNone(draft.transcript_id)
            self.assertIsNone(draft.payload_json["transcriptId"])
        finally:
            db.close()

    def test_new_drafts_receive_distinct_case_ids(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            first = create_workflow_draft(
                WorkflowDraftCreateRequest(payload={"caseInformation": {"case_id": "", "case_year": 2026}}),
                context,
                db,
            )
            second = create_workflow_draft(
                WorkflowDraftCreateRequest(payload={"caseInformation": {"case_id": "", "case_year": 2026}}),
                context,
                db,
            )

            self.assertEqual(first["payload"]["caseInformation"]["case_id"], "KP-2026-0001")
            self.assertEqual(second["payload"]["caseInformation"]["case_id"], "KP-2026-0002")
        finally:
            db.close()

    def test_create_update_restore_list_and_complete_draft(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            created = create_workflow_draft(
                WorkflowDraftCreateRequest(payload={"transcript": "Draft text"}),
                context,
                db,
            )

            self.assertEqual(created["active_step"], 1)
            self.assertEqual(created["revision"], 1)

            updated = update_workflow_draft(
                created["workflow_id"],
                WorkflowDraftUpdateRequest(
                    revision=1,
                    active_step=2,
                    max_unlocked_step=2,
                    payload={"transcript": "Updated text"},
                ),
                context,
                db,
            )

            self.assertEqual(updated["revision"], 2)
            self.assertEqual(updated["payload"]["transcript"], "Updated text")
            self.assertEqual(get_workflow_draft(created["workflow_id"], context, db)["active_step"], 2)
            self.assertEqual(len(list_workflow_drafts("active", context, db)["items"]), 1)

            completed = complete_workflow_draft(created["workflow_id"], context, db)
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(list_workflow_drafts("active", context, db)["items"], [])
        finally:
            db.close()

    def test_revision_conflict_returns_409(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            created = create_workflow_draft(WorkflowDraftCreateRequest(), context, db)
            update_workflow_draft(
                created["workflow_id"],
                WorkflowDraftUpdateRequest(revision=1, active_step=2, max_unlocked_step=2),
                context,
                db,
            )

            with self.assertRaises(HTTPException) as raised:
                update_workflow_draft(
                    created["workflow_id"],
                    WorkflowDraftUpdateRequest(revision=1, active_step=3, max_unlocked_step=3),
                    context,
                    db,
                )

            self.assertEqual(raised.exception.status_code, 409)
        finally:
            db.close()

    def test_draft_update_keeps_column_and_payload_case_identity_aligned(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            created = create_workflow_draft(
                WorkflowDraftCreateRequest(
                    payload={"caseInformation": {"case_id": "KP-2026-0018"}}
                ),
                context,
                db,
            )

            updated = update_workflow_draft(
                created["workflow_id"],
                WorkflowDraftUpdateRequest(
                    revision=created["revision"],
                    active_step=1,
                    max_unlocked_step=1,
                    payload={"caseInformation": {"case_id": "KP-2026-0018"}},
                ),
                context,
                db,
            )
            self.assertEqual(updated["case_id"], "KP-2026-0018")
            self.assertEqual(updated["payload"]["caseInformation"]["case_id"], "KP-2026-0018")

            with self.assertRaises(HTTPException) as raised:
                update_workflow_draft(
                    created["workflow_id"],
                    WorkflowDraftUpdateRequest(
                        revision=updated["revision"],
                        active_step=1,
                        max_unlocked_step=1,
                        case_id="KP-2026-0019",
                        payload={"caseInformation": {"case_id": "KP-2026-0018"}},
                    ),
                    context,
                    db,
                )
            self.assertEqual(raised.exception.status_code, 409)
        finally:
            db.close()

    def test_first_workflow_audio_is_saved_and_second_upload_is_rejected(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            created = create_workflow_draft(WorkflowDraftCreateRequest(), context, db)

            with tempfile.TemporaryDirectory() as upload_dir, patch("main.UPLOAD_DIR", Path(upload_dir)), patch(
                "main.convert_to_wav", side_effect=lambda path: path
            ), patch("main.wav_duration_seconds", return_value=12.5), patch("main.transcribe_audio", return_value=[]):
                result = upload_audio(
                    file=UploadFile(filename="first.wav", file=BytesIO(b"first audio")),
                    speaker_count=0,
                    recording_type="blotter_case",
                    workflow_id=created["workflow_id"],
                    db=db,
                    context=context,
                )

                saved = get_workflow_draft(created["workflow_id"], context, db)
                self.assertEqual(saved["payload"]["blotterAudioFilename"], result["playback_filename"])
                self.assertEqual(saved["payload"]["blotterDurationSeconds"], 12.5)

                with self.assertRaises(HTTPException) as raised:
                    upload_audio(
                        file=UploadFile(filename="replacement.mp3", file=BytesIO(b"replacement audio")),
                        speaker_count=0,
                        recording_type="blotter_case",
                        workflow_id=created["workflow_id"],
                        db=db,
                        context=context,
                    )

                self.assertEqual(raised.exception.status_code, 409)
                self.assertIn("already has an audio record", raised.exception.detail)
        finally:
            db.close()

    def test_draft_update_cannot_clear_or_replace_canonical_audio(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            created = create_workflow_draft(
                WorkflowDraftCreateRequest(
                    payload={"blotterAudioFilename": "original.wav", "blotterDurationSeconds": 9.0}
                ),
                context,
                db,
            )

            for invalid_filename in ("", "replacement.wav"):
                with self.assertRaises(HTTPException) as raised:
                    update_workflow_draft(
                        created["workflow_id"],
                        WorkflowDraftUpdateRequest(
                            revision=1,
                            active_step=1,
                            max_unlocked_step=1,
                            payload={"blotterAudioFilename": invalid_filename},
                        ),
                        context,
                        db,
                    )
                self.assertEqual(raised.exception.status_code, 409)
        finally:
            db.close()

    def test_current_user_draft_isolation(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            admin = make_context(db)
            secretary = make_context(db, username="secretary", role_name="barangay_secretary")
            draft = create_workflow_draft(WorkflowDraftCreateRequest(), secretary, db)

            self.assertEqual(len(list_workflow_drafts("active", secretary, db)["items"]), 1)
            self.assertEqual(len(list_workflow_drafts("active", admin, db)["items"]), 1)

            viewer = make_context(db, username="viewer1", role_name="viewer")
            self.assertEqual(list_workflow_drafts("active", viewer, db)["items"], [])
            with self.assertRaises(HTTPException):
                get_workflow_draft(draft["workflow_id"], viewer, db)
        finally:
            db.close()

    def test_phase2_analysis_persists_backend_decision_to_draft(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            draft = create_workflow_draft(WorkflowDraftCreateRequest(), context, db)

            with self.assertRaises(HTTPException) as unconfirmed:
                run_workflow_phase2_analysis(
                    draft["workflow_id"],
                    WorkflowPhase2AnalysisRequest(
                        revision=1,
                        transcript_text="Speaker 2: Sinaktan po ako at binantaan ng asawa ko.",
                        case_information=case_info(),
                    ),
                    context,
                    db,
                )
            self.assertEqual(unconfirmed.exception.status_code, 400)

            result = run_workflow_phase2_analysis(
                draft["workflow_id"],
                WorkflowPhase2AnalysisRequest(
                    revision=1,
                    transcript_text="Speaker 2: Sinaktan po ako at binantaan ng asawa ko.",
                    case_information=case_info(has_vawc_or_child_abuse_indicators=True),
                ),
                context,
                db,
            )

            self.assertEqual(result["analysis"].jurisdiction_decision, "refer_to_pnp_wcpc_or_authority")
            self.assertTrue(result["payload"]["phase2Analysis"]["detected_keywords"]["vawc_trigger"])
            self.assertEqual(result["payload"]["skippedPanelIds"], [3, 4, 5, 6])
            self.assertIsNotNone(result["case_analysis_id"])
        finally:
            db.close()

    def test_non_vawc_text_does_not_use_frontend_shortcut(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            draft = create_workflow_draft(WorkflowDraftCreateRequest(), context, db)

            result = run_workflow_phase2_analysis(
                draft["workflow_id"],
                WorkflowPhase2AnalysisRequest(
                    revision=1,
                    transcript_text="Speaker 2: May utang po siya sa akin na 5000 pesos.",
                    case_information=case_info(
                        case_type="civil",
                        dispute_category="debt",
                        has_vawc_or_child_abuse_indicators=False,
                    ),
                ),
                context,
                db,
            )

            self.assertEqual(result["analysis"].jurisdiction_decision, "within_kp")
            self.assertFalse(result["analysis"].detected_keywords["vawc_trigger"])
            self.assertEqual(result["payload"]["skippedPanelIds"], [])
        finally:
            db.close()

    def test_generate_forms_then_finalize_outcome_creates_case_record(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            draft = create_workflow_draft(WorkflowDraftCreateRequest(), context, db)
            analyzed = run_workflow_phase2_analysis(
                draft["workflow_id"],
                WorkflowPhase2AnalysisRequest(
                    revision=draft["revision"],
                    transcript_text="Speaker 1: May utang po siya. Speaker 2: Payag akong magbayad.",
                    case_information=case_info(case_id=draft["payload"]["caseInformation"]["case_id"], case_type="civil", dispute_category="debt"),
                ),
                context,
                db,
            )

            with tempfile.TemporaryDirectory() as directory, patch("main.GENERATED_FORMS_DIR", Path(directory)):
                generated = finalize_workflow_intake(
                    draft["workflow_id"],
                    WorkflowFinalizeIntakeRequest(revision=analyzed["revision"]),
                    context,
                    db,
                )
                retried = finalize_workflow_intake(
                    draft["workflow_id"],
                    WorkflowFinalizeIntakeRequest(revision=generated["revision"]),
                    context,
                    db,
                )
                regenerated = finalize_workflow_intake(
                    draft["workflow_id"],
                    WorkflowFinalizeIntakeRequest(
                        revision=retried["revision"],
                        regenerate=True,
                    ),
                    context,
                    db,
                )
                finalized = finalize_workflow_outcome(
                    draft["workflow_id"],
                    WorkflowFinalizeOutcomeRequest(
                        revision=regenerated["revision"],
                        outcome="Amicable Settlement Reached",
                    ),
                    context,
                    db,
                )

            self.assertEqual(generated["status"], "active")
            self.assertFalse(generated["payload"]["completed"])
            self.assertEqual(finalized["status"], "completed")
            self.assertEqual(finalized["active_step"], 7)
            self.assertEqual(generated["phase4_packet"]["id"], retried["phase4_packet"]["id"])
            self.assertNotEqual(regenerated["phase4_packet"]["id"], retried["phase4_packet"]["id"])
            self.assertEqual(finalized["payload"]["outcome"], "Amicable Settlement Reached")
            records = list_finalized_workflow_cases(context, db)
            self.assertEqual(records[0]["id"], analyzed["case_id"])
            self.assertEqual(records[0]["status"], "Amicable Settlement Reached")
            self.assertEqual(db.query(Phase4FormPacket).count(), 2)
        finally:
            db.close()

    def test_vawc_outcome_finalizes_as_protected_referral(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            draft = create_workflow_draft(WorkflowDraftCreateRequest(), context, db)
            analyzed = run_workflow_phase2_analysis(
                draft["workflow_id"],
                WorkflowPhase2AnalysisRequest(
                    revision=draft["revision"],
                    transcript_text="Complainant: Sinaktan at binantaan po ako ng asawa ko.",
                    case_information=case_info(
                        case_id=draft["payload"]["caseInformation"]["case_id"],
                        has_vawc_or_child_abuse_indicators=True,
                    ),
                ),
                context,
                db,
            )

            with tempfile.TemporaryDirectory() as directory, patch("main.GENERATED_FORMS_DIR", Path(directory)):
                generated = finalize_workflow_intake(
                    draft["workflow_id"],
                    WorkflowFinalizeIntakeRequest(revision=analyzed["revision"]),
                    context,
                    db,
                )
                finalized = finalize_workflow_outcome(
                    draft["workflow_id"],
                    WorkflowFinalizeOutcomeRequest(
                        revision=generated["revision"],
                        outcome="Referred to WCPD / PNP",
                    ),
                    context,
                    db,
                )

            self.assertEqual(finalized["payload"]["skippedPanelIds"], [3, 4, 5, 6])
            self.assertEqual(finalized["payload"]["caseRecordStatus"], "Referred - VAWC")
            record = list_finalized_workflow_cases(context, db)[0]
            self.assertEqual(record["route"], "vawc_referral")
            self.assertEqual(record["tone"], "red")
        finally:
            db.close()

    def test_within_kp_phase3_court_referral_finalizes_as_referral_record(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            draft = create_workflow_draft(WorkflowDraftCreateRequest(), context, db)
            transcript_text = (
                "Complainant: Sinabi ng kapitbahay ko na sasaktan niya ako "
                "kapag nakita niya ulit ang aking pamilya."
            )
            transcript = Transcript(content=transcript_text, raw_content=transcript_text, segments_json=[])
            db.add(transcript)
            db.commit()
            db.refresh(transcript)
            analyzed = run_workflow_phase2_analysis(
                draft["workflow_id"],
                WorkflowPhase2AnalysisRequest(
                    revision=draft["revision"],
                    transcript_id=transcript.id,
                    transcript_text=transcript_text,
                    case_information=case_info(
                        case_id=draft["payload"]["caseInformation"]["case_id"],
                        case_type="civil",
                        dispute_category="threat",
                        has_vawc_or_child_abuse_indicators=False,
                    ),
                ),
                context,
                db,
            )
            self.assertEqual(analyzed["analysis"].jurisdiction_decision, "within_kp")

            dashboard = process_phase3_pipeline(analyzed["case_id"], db)
            self.assertEqual(dashboard["phase3"]["final_recommended_action"], "Refer to Court")
            referral = db.query(Referral).filter(Referral.case_id == analyzed["case_id"]).one()

            resolved = resolve_workflow_referral(
                draft["workflow_id"],
                referral.id,
                WorkflowReferralActionRequest(
                    revision=analyzed["revision"],
                    action="complete_and_advance",
                ),
                context,
                db,
            )
            self.assertTrue(resolved["payload"]["phase3ReferralRequired"])
            self.assertEqual(resolved["payload"]["phase3ReferralId"], referral.id)
            self.assertEqual(resolved["payload"]["phase3ReferralStatus"], "completed")

            with tempfile.TemporaryDirectory() as directory, patch("main.GENERATED_FORMS_DIR", Path(directory)):
                generated = finalize_workflow_intake(
                    draft["workflow_id"],
                    WorkflowFinalizeIntakeRequest(revision=resolved["revision"]),
                    context,
                    db,
                )
                self.assertTrue(generated["payload"]["phase3ReferralRequired"])
                self.assertEqual(generated["payload"]["phase3RecommendedRoute"], "Refer to Court")

                with self.assertRaises(HTTPException) as wrong_destination:
                    finalize_workflow_outcome(
                        draft["workflow_id"],
                        WorkflowFinalizeOutcomeRequest(
                            revision=generated["revision"],
                            outcome="Referred to WCPD / PNP",
                        ),
                        context,
                        db,
                    )
                self.assertEqual(wrong_destination.exception.status_code, 400)
                self.assertEqual(
                    wrong_destination.exception.detail,
                    "Select a valid final outcome for this case route.",
                )

                finalized = finalize_workflow_outcome(
                    draft["workflow_id"],
                    WorkflowFinalizeOutcomeRequest(
                        revision=generated["revision"],
                        outcome="Referred to Court / Proper Authority",
                    ),
                    context,
                    db,
                )

            self.assertEqual(finalized["status"], "completed")
            self.assertTrue(finalized["payload"]["completed"])
            self.assertEqual(finalized["payload"]["phase3ReferralId"], referral.id)
            self.assertEqual(finalized["payload"]["phase3ReferralStatus"], "completed")
            records = list_finalized_workflow_cases(context, db)
            record = next(item for item in records if item["id"] == analyzed["case_id"])
            self.assertEqual(record["status"], "Referred to Court / Proper Authority")
            self.assertEqual(record["route"], "referral")
            self.assertEqual(
                db.query(AuditLog).filter(AuditLog.action == "workflow_outcome_finalized").count(),
                1,
            )
        finally:
            db.close()

    def test_referral_completion_saves_official_decision_and_advances_workflow(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            draft = create_workflow_draft(WorkflowDraftCreateRequest(), context, db)
            analyzed = run_workflow_phase2_analysis(
                draft["workflow_id"],
                WorkflowPhase2AnalysisRequest(
                    revision=draft["revision"],
                    transcript_text="Complainant: Sinaktan at binantaan po ako ng asawa ko.",
                    case_information=case_info(
                        case_id=draft["payload"]["caseInformation"]["case_id"],
                        has_vawc_or_child_abuse_indicators=True,
                    ),
                ),
                context,
                db,
            )
            process_phase3_pipeline(analyzed["case_id"], db)
            referral = db.query(Referral).filter(Referral.case_id == analyzed["case_id"]).one()
            self.assertEqual(referral.status, "pending")

            resolved = resolve_workflow_referral(
                draft["workflow_id"],
                referral.id,
                WorkflowReferralActionRequest(
                    revision=analyzed["revision"],
                    action="complete_and_advance",
                ),
                context,
                db,
            )

            self.assertEqual(resolved["status"], "active")
            self.assertEqual(resolved["active_step"], 7)
            self.assertEqual(resolved["max_unlocked_step"], 7)
            self.assertEqual(resolved["referral"]["status"], "completed")
            self.assertTrue(resolved["payload"]["symbolicConfirmed"])
            self.assertEqual(resolved["payload"]["referralResolution"]["status"], "completed")
            self.assertIn("Referral confirmed sent", resolved["official_decision"]["official_decision"])
            self.assertEqual(db.query(Phase3OfficialDecision).filter(Phase3OfficialDecision.case_id == analyzed["case_id"]).count(), 1)
            self.assertEqual(
                db.query(AuditLog).filter(AuditLog.action == "referral_confirmed_sent_and_workflow_advanced").count(),
                1,
            )

            with self.assertRaises(HTTPException) as stale:
                resolve_workflow_referral(
                    draft["workflow_id"],
                    referral.id,
                    WorkflowReferralActionRequest(
                        revision=analyzed["revision"],
                        action="complete_and_advance",
                    ),
                    context,
                    db,
                )
            self.assertEqual(stale.exception.status_code, 409)
        finally:
            db.close()

    def test_cancel_referral_record_advances_to_final_documentation(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            draft = create_workflow_draft(WorkflowDraftCreateRequest(), context, db)
            analyzed = run_workflow_phase2_analysis(
                draft["workflow_id"],
                WorkflowPhase2AnalysisRequest(
                    revision=draft["revision"],
                    transcript_text="Complainant: Sinaktan at binantaan po ako ng asawa ko.",
                    case_information=case_info(
                        case_id=draft["payload"]["caseInformation"]["case_id"],
                        has_vawc_or_child_abuse_indicators=True,
                    ),
                ),
                context,
                db,
            )
            process_phase3_pipeline(analyzed["case_id"], db)
            referral = db.query(Referral).filter(Referral.case_id == analyzed["case_id"]).one()
            self.assertEqual(referral.status, "pending")
            cancelled = resolve_workflow_referral(
                draft["workflow_id"],
                referral.id,
                WorkflowReferralActionRequest(
                    revision=analyzed["revision"],
                    action="cancel_referral",
                    reason="The referral entry was created in error and requires official review.",
                ),
                context,
                db,
            )

            self.assertEqual(cancelled["status"], "active")
            self.assertEqual(cancelled["active_step"], 7)
            self.assertEqual(cancelled["max_unlocked_step"], 7)
            self.assertEqual(cancelled["referral"]["status"], "cancelled")
            self.assertFalse(cancelled["payload"]["caseCancelled"])
            self.assertTrue(cancelled["payload"]["symbolicConfirmed"])
            self.assertEqual(cancelled["payload"]["referralResolution"]["status"], "cancelled")
            self.assertEqual(cancelled["payload"].get("outcome"), CANCELLED_REFERRAL_OUTCOME)
            self.assertIsNone(cancelled["official_decision"])
            self.assertEqual(
                db.query(Phase3OfficialDecision).filter(Phase3OfficialDecision.case_id == analyzed["case_id"]).count(),
                0,
            )
            self.assertEqual(len(list_workflow_drafts("active", context, db)["items"]), 1)
            self.assertEqual(
                db.query(AuditLog).filter(AuditLog.action == "referral_record_cancelled").count(),
                1,
            )

            with tempfile.TemporaryDirectory() as directory, patch("main.GENERATED_FORMS_DIR", Path(directory)):
                generated = finalize_workflow_intake(
                    draft["workflow_id"],
                    WorkflowFinalizeIntakeRequest(revision=cancelled["revision"]),
                    context,
                    db,
                )
                finalized = finalize_workflow_outcome(
                    draft["workflow_id"],
                    WorkflowFinalizeOutcomeRequest(
                        revision=generated["revision"],
                        outcome=CANCELLED_REFERRAL_OUTCOME,
                    ),
                    context,
                    db,
                )

            referrals = db.query(Referral).filter(Referral.case_id == analyzed["case_id"]).all()
            self.assertEqual([item.status for item in referrals], ["cancelled"])
            self.assertEqual(finalized["status"], "completed")
            self.assertEqual(finalized["payload"]["phase3ReferralStatus"], "cancelled")
            self.assertEqual(finalized["payload"]["outcome"], CANCELLED_REFERRAL_OUTCOME)
            record = next(item for item in list_finalized_workflow_cases(context, db) if item["id"] == analyzed["case_id"])
            self.assertEqual(record["status"], CANCELLED_REFERRAL_OUTCOME)
            self.assertEqual(record["route"], "vawc_referral")
        finally:
            db.close()

    def test_cancel_case_requires_reason_and_preserves_audited_terminal_record(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            context = make_context(db)
            draft = create_workflow_draft(WorkflowDraftCreateRequest(), context, db)
            analyzed = run_workflow_phase2_analysis(
                draft["workflow_id"],
                WorkflowPhase2AnalysisRequest(
                    revision=draft["revision"],
                    transcript_text="Complainant: Sinaktan at binantaan po ako ng asawa ko.",
                    case_information=case_info(
                        case_id=draft["payload"]["caseInformation"]["case_id"],
                        has_vawc_or_child_abuse_indicators=True,
                    ),
                ),
                context,
                db,
            )
            process_phase3_pipeline(analyzed["case_id"], db)
            referral = db.query(Referral).filter(Referral.case_id == analyzed["case_id"]).one()

            with self.assertRaises(HTTPException) as missing_reason:
                resolve_workflow_referral(
                    draft["workflow_id"],
                    referral.id,
                    WorkflowReferralActionRequest(
                        revision=analyzed["revision"],
                        action="cancel_case",
                        reason="short",
                    ),
                    context,
                    db,
                )
            self.assertEqual(missing_reason.exception.status_code, 400)

            cancelled = resolve_workflow_referral(
                draft["workflow_id"],
                referral.id,
                WorkflowReferralActionRequest(
                    revision=analyzed["revision"],
                    action="cancel_case",
                    reason="The complainant formally withdrew the case before referral dispatch.",
                ),
                context,
                db,
            )

            self.assertEqual(cancelled["status"], "cancelled")
            self.assertEqual(cancelled["referral"]["status"], "cancelled")
            self.assertTrue(cancelled["payload"]["caseCancelled"])
            self.assertEqual(cancelled["payload"]["caseRecordStatus"], "Cancelled")
            self.assertEqual(cancelled["payload"]["referralResolution"]["status"], "cancelled")
            self.assertEqual(list_workflow_drafts("active", context, db)["items"], [])
            records = list_finalized_workflow_cases(context, db)
            self.assertEqual(records[0]["status"], "Case Cancelled")
            self.assertEqual(records[0]["route"], "cancelled")
            self.assertEqual(
                db.query(AuditLog).filter(AuditLog.action == "workflow_case_cancelled_from_referral").count(),
                1,
            )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
