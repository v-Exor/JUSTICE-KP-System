import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from auth_schemas import UserCreateRequest  # noqa: E402
from auth_service import AuthContext, create_user, seed_roles_and_dev_admin  # noqa: E402
from database import Base  # noqa: E402
from main import (  # noqa: E402
    SaveTranscriptRequest,
    TranscriptSegment,
    WorkflowDraftCreateRequest,
    WorkflowPhase2AnalysisRequest,
    create_workflow_draft,
    delete_transcript,
    get_transcript,
    get_transcripts,
    run_workflow_phase2_analysis,
    save_transcript,
)
from models import PhraseCorrection, Role, Transcript, User, WorkflowDraft  # noqa: E402
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


def case_info(case_id):
    return CaseInformationPayload(
        case_id=case_id,
        barangay_name="Barangay Uno",
        city_municipality="Santa Cruz",
        case_year=2026,
        case_type="civil",
        dispute_category="debt",
        complainant_residency="same_barangay",
        respondent_residency="same_barangay",
        debt_amount_php=1000,
        maximum_penalty_years=0,
        fine_amount_php=0,
        government_party_involved=False,
        already_filed_in_court=False,
        has_vawc_or_child_abuse_indicators=False,
    )


class WorkflowTranscriptUpsertTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed_roles_and_dev_admin(self.db)
        self.context = make_context(self.db)
        self.temp_directory = tempfile.TemporaryDirectory()
        self.transcript_directory_patch = patch("main.TRANSCRIPT_DIR", Path(self.temp_directory.name))
        self.transcript_directory_patch.start()

    def tearDown(self):
        self.transcript_directory_patch.stop()
        self.temp_directory.cleanup()
        self.db.close()

    def create_draft(self, case_id):
        return create_workflow_draft(
            WorkflowDraftCreateRequest(payload={"caseInformation": {"case_id": case_id, "case_year": 2026}}),
            self.context,
            self.db,
        )

    def save_intake(self, draft, text="May utang po siya"):
        return save_transcript(
            SaveTranscriptRequest(
                content=f"Complainant: {text}",
                segments=[
                    TranscriptSegment(
                        speaker="Complainant",
                        start=0,
                        end=2,
                        text="May otang po siya",
                        confidence=0.72,
                    )
                ],
                edited_segments=[
                    TranscriptSegment(
                        speaker="Complainant",
                        start=0,
                        end=2,
                        text=text,
                        confidence=0.72,
                    )
                ],
                provider="local",
                recording_type="blotter_case",
                expected_speakers=2,
                asr_confidence=0.72,
                diarization_quality=0.8,
                workflow_id=draft["workflow_id"],
                case_id=draft["payload"]["caseInformation"]["case_id"],
                save_context="intake",
            ),
            self.db,
            self.context,
        )

    def test_hearing_replaces_edited_content_on_same_row_and_preserves_raw_evidence(self):
        draft = self.create_draft("KP-2026-1010")
        intake = self.save_intake(draft)
        original = self.db.query(Transcript).filter(Transcript.id == intake["id"]).one()
        original_created_at = original.created_at
        original_raw_content = original.raw_content
        original_raw_segments = list(original.raw_segments_json)

        hearing = save_transcript(
            SaveTranscriptRequest(
                content="Complainant: May bayad na po siya",
                # This represents a copied/edited hearing view and must not
                # replace the original ASR evidence.
                segments=[
                    TranscriptSegment(
                        speaker="Complainant",
                        start=10,
                        end=12,
                        text="This is not the intake raw transcript",
                        confidence=0.2,
                    )
                ],
                edited_segments=[
                    TranscriptSegment(
                        speaker="Complainant",
                        start=0,
                        end=2.5,
                        text="May bayad na po siya",
                        confidence=0.95,
                    )
                ],
                recording_type="blotter_hearing",
                expected_speakers=3,
                workflow_id=draft["workflow_id"],
                case_id="KP-2026-1010",
                transcript_id=intake["id"],
                save_context="hearing",
            ),
            self.db,
            self.context,
        )

        updated = self.db.query(Transcript).filter(Transcript.id == intake["id"]).one()
        stored_draft = self.db.query(WorkflowDraft).filter(WorkflowDraft.workflow_id == draft["workflow_id"]).one()
        self.assertEqual(hearing["operation"], "updated")
        self.assertEqual(hearing["id"], intake["id"])
        self.assertEqual(self.db.query(Transcript).count(), 1)
        self.assertEqual(updated.created_at, original_created_at)
        self.assertEqual(updated.raw_content, original_raw_content)
        self.assertEqual(updated.raw_segments_json, original_raw_segments)
        self.assertEqual(updated.content, "Complainant: May bayad na po siya")
        self.assertEqual(updated.segments_json[0]["text"], "May bayad na po siya")
        self.assertEqual(updated.asr_confidence, 0.72)
        self.assertEqual(updated.expected_speakers, 3)
        self.assertEqual(updated.save_context, "hearing")
        self.assertEqual(updated.corrections_json, [{"wrong": "otang", "corrected": "bayad na"}])
        self.assertEqual(stored_draft.transcript_id, intake["id"])
        self.assertEqual(stored_draft.payload_json["transcriptId"], intake["id"])
        self.assertEqual(stored_draft.payload_json["hearingTranscriptId"], intake["id"])
        self.assertEqual(get_transcripts(self.db)["items"][0]["case_id"], "KP-2026-1010")
        self.assertEqual(self.db.query(PhraseCorrection).count(), 1)

    def test_different_cases_never_share_a_transcript(self):
        first = self.create_draft("KP-2026-1011")
        second = self.create_draft("KP-2026-1012")
        first_saved = self.save_intake(first)
        second_saved = self.save_intake(second)

        self.assertNotEqual(first_saved["id"], second_saved["id"])
        self.assertEqual(self.db.query(Transcript).count(), 2)
        self.assertEqual(
            {row["case_id"] for row in get_transcripts(self.db)["items"]},
            {"KP-2026-1011", "KP-2026-1012"},
        )

    def test_same_exact_case_reuses_existing_canonical_transcript_for_same_owner(self):
        first = self.create_draft("KP-2026-1013")
        second = self.create_draft("KP-2026-1013")
        first_saved = self.save_intake(first)
        second_saved = self.save_intake(second, text="May utang po siyang bago")

        second_draft = self.db.query(WorkflowDraft).filter(WorkflowDraft.workflow_id == second["workflow_id"]).one()
        self.assertEqual(second_saved["id"], first_saved["id"])
        self.assertEqual(second_draft.transcript_id, first_saved["id"])
        self.assertEqual(self.db.query(Transcript).count(), 1)

    def test_cross_owner_case_id_collision_cannot_overwrite_transcript(self):
        first = self.create_draft("KP-2026-1014")
        first_saved = self.save_intake(first)
        secretary_context = make_context(self.db, "secretary", "barangay_secretary")
        second = create_workflow_draft(
            WorkflowDraftCreateRequest(payload={"caseInformation": {"case_id": "KP-2026-1014", "case_year": 2026}}),
            secretary_context,
            self.db,
        )

        with self.assertRaises(HTTPException) as raised:
            save_transcript(
                SaveTranscriptRequest(
                    content="Complainant: Attempted overwrite",
                    workflow_id=second["workflow_id"],
                    case_id="KP-2026-1014",
                    save_context="intake",
                ),
                self.db,
                secretary_context,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self.db.query(Transcript).count(), 1)
        self.assertEqual(self.db.query(Transcript).one().id, first_saved["id"])

    def test_workflow_only_intake_is_bound_when_phase2_assigns_case(self):
        draft_data = self.create_draft("KP-2026-TEMP")
        draft = self.db.query(WorkflowDraft).filter(WorkflowDraft.workflow_id == draft_data["workflow_id"]).one()
        draft.case_id = ""
        draft_payload = dict(draft.payload_json)
        draft_payload["caseInformation"] = {"case_id": "", "case_year": 2026}
        draft.payload_json = draft_payload
        self.db.commit()

        intake = save_transcript(
            SaveTranscriptRequest(
                content="Complainant: May utang po siya",
                segments=[TranscriptSegment(speaker="Complainant", start=0, end=2, text="May utang po siya")],
                workflow_id=draft.workflow_id,
                save_context="intake",
            ),
            self.db,
            self.context,
        )
        transcript = self.db.query(Transcript).filter(Transcript.id == intake["id"]).one()
        self.assertIsNone(transcript.case_id)

        analyzed = run_workflow_phase2_analysis(
            draft.workflow_id,
            WorkflowPhase2AnalysisRequest(
                revision=draft.revision,
                transcript_id=transcript.id,
                transcript_text=transcript.content,
                case_information=case_info("KP-2026-1015"),
            ),
            self.context,
            self.db,
        )

        self.db.refresh(transcript)
        self.assertEqual(analyzed["case_id"], "KP-2026-1015")
        self.assertEqual(transcript.workflow_id, draft.workflow_id)
        self.assertEqual(transcript.case_id, "KP-2026-1015")
        self.assertEqual(self.db.query(Transcript).count(), 1)

    def test_stale_hearing_id_is_not_merged_and_delete_clears_all_payload_links(self):
        first = self.create_draft("KP-2026-1016")
        second = self.create_draft("KP-2026-1017")
        first_saved = self.save_intake(first)
        second_saved = self.save_intake(second)
        first_draft = self.db.query(WorkflowDraft).filter(WorkflowDraft.workflow_id == first["workflow_id"]).one()
        first_payload = dict(first_draft.payload_json)
        first_payload["hearingTranscriptId"] = second_saved["id"]
        first_payload["hearingSavedAt"] = self.db.query(Transcript).filter(Transcript.id == second_saved["id"]).one().created_at.isoformat()
        first_draft.payload_json = first_payload
        self.db.commit()

        hearing = save_transcript(
            SaveTranscriptRequest(
                content="Complainant: Updated first case only",
                edited_segments=[TranscriptSegment(speaker="Complainant", start=0, end=2, text="Updated first case only")],
                workflow_id=first["workflow_id"],
                case_id="KP-2026-1016",
                transcript_id=first_saved["id"],
                save_context="hearing",
            ),
            self.db,
            self.context,
        )
        self.assertEqual(hearing["id"], first_saved["id"])
        self.assertEqual(self.db.query(Transcript).filter(Transcript.id == second_saved["id"]).one().case_id, "KP-2026-1017")
        self.assertEqual(get_transcripts(self.db)["total"], 2)

        delete_transcript(first_saved["id"], self.context, self.db)
        self.db.refresh(first_draft)
        self.assertIsNone(first_draft.transcript_id)
        self.assertIsNone(first_draft.payload_json["transcriptId"])
        self.assertIsNone(first_draft.payload_json["hearingTranscriptId"])
        self.assertFalse(first_draft.payload_json["hearingRecorded"])

    def test_transcript_list_searches_before_pagination_and_returns_lightweight_summaries(self):
        base_time = datetime(2026, 9, 20, 8, 0, 0)
        created: list[Transcript] = []
        for index in range(12):
            transcript = Transcript(
                case_id=f"KP-2026-{2000 + index}",
                content=f"Complainant: {'Needle' if index % 2 == 0 else 'Other'} statement {index}",
                raw_content=f"Raw statement {index}",
                segments_json=[{"speaker": "Complainant", "start": 0, "end": 1, "text": f"Statement {index}"}],
                corrections_json=[],
                save_context="standalone",
                asr_provider="local",
                recording_type="blotter_case",
                created_at=base_time + timedelta(minutes=index),
                updated_at=base_time + timedelta(minutes=index),
            )
            self.db.add(transcript)
            created.append(transcript)
        self.db.commit()

        result = get_transcripts(self.db, q="needle", page=2, page_size=3)

        self.assertEqual(result["total"], 6)
        self.assertEqual(result["total_pages"], 2)
        self.assertEqual(result["page"], 2)
        self.assertEqual(
            [item["id"] for item in result["items"]],
            [created[index].id for index in (6, 8, 10)],
        )
        self.assertNotIn("content", result["items"][0])
        self.assertNotIn("segments", result["items"][0])
        self.assertEqual(result["items"][0]["segment_count"], 1)

        detail = get_transcript(result["items"][0]["id"], self.db)
        self.assertIn("Needle", detail["content"])
        self.assertEqual(len(detail["segments"]), 1)

    def test_legacy_duplicate_is_hidden_from_list_and_id_detail(self):
        draft_data = self.create_draft("KP-2026-3001")
        saved = self.save_intake(draft_data)
        canonical = self.db.query(Transcript).filter(Transcript.id == saved["id"]).one()
        legacy_hearing = Transcript(
            content="Complainant: Legacy hearing content",
            raw_content="Complainant: Legacy hearing content",
            segments_json=[],
            raw_segments_json=[],
            corrections_json=[],
            save_context="standalone",
            created_at=canonical.created_at + timedelta(minutes=1),
            updated_at=canonical.updated_at + timedelta(minutes=1),
        )
        self.db.add(legacy_hearing)
        self.db.commit()

        draft = self.db.query(WorkflowDraft).filter(WorkflowDraft.workflow_id == draft_data["workflow_id"]).one()
        payload = dict(draft.payload_json)
        payload["hearingTranscriptId"] = legacy_hearing.id
        payload["hearingSavedAt"] = legacy_hearing.created_at.isoformat()
        draft.payload_json = payload
        self.db.commit()

        listing = get_transcripts(self.db)
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["id"], legacy_hearing.id)
        self.assertEqual(listing["items"][0]["case_id"], "KP-2026-3001")

        with self.assertRaises(HTTPException) as raised:
            get_transcript(canonical.id, self.db)
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
