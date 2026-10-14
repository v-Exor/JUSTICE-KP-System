import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import BackgroundTasks, HTTPException, Request, Response  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from auth_schemas import UserCreateRequest, UserStatusRequest, UserUpdateRequest  # noqa: E402
from auth_service import (  # noqa: E402
    AuthContext,
    create_user,
    hash_secret,
    password_hash,
    restore_csrf_token,
    seed_roles_and_dev_admin,
    update_user,
    update_user_status,
    verify_password,
)
from backup_service import BackupService  # noqa: E402
from database import Base, backfill_transcript_metrics  # noqa: E402
from main import (  # noqa: E402
    LearnTranscriptCorrectionsRequest,
    SaveTranscriptRequest,
    TranscriptSegment,
    assign_role_labels,
    cors_headers_for_request,
    get_learned_corrections,
    learn_transcript_corrections,
    save_transcript,
    shutdown_local_system,
    speaker_count_for_recording_type,
    transcript_accuracy_report,
)
from models import BackupRecord, PhraseCorrection, Role, Transcript, User, UserSession  # noqa: E402
from transcript_normalizer import normalize_transcript_text  # noqa: E402


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


class ProductionHardeningTests(unittest.TestCase):
    @staticmethod
    def make_auth_request(csrf_cookie: str = "") -> Request:
        headers = [(b"host", b"127.0.0.1:8000")]
        if csrf_cookie:
            headers.append((b"cookie", f"justice_kp_csrf={csrf_cookie}".encode("ascii")))
        return Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/api/auth/me",
                "raw_path": b"/api/auth/me",
                "query_string": b"",
                "headers": headers,
                "client": ("127.0.0.1", 51000),
                "server": ("127.0.0.1", 8000),
            }
        )

    @staticmethod
    def make_shutdown_request(client_host: str = "127.0.0.1", origin: str = "http://127.0.0.1:3000") -> Request:
        return Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/api/system/shutdown",
                "raw_path": b"/api/system/shutdown",
                "query_string": b"",
                "headers": [
                    (b"host", b"127.0.0.1:8000"),
                    (b"origin", origin.encode("ascii")),
                ],
                "client": (client_host, 51000),
                "server": ("127.0.0.1", 8000),
            }
        )

    def test_local_shutdown_is_disabled_in_production(self):
        with patch.dict("os.environ", {"APP_ENV": "production", "ALLOW_LOCAL_SHUTDOWN": "true"}):
            with self.assertRaises(HTTPException) as raised:
                shutdown_local_system(self.make_shutdown_request(), BackgroundTasks())
        self.assertEqual(raised.exception.status_code, 404)

    def test_security_errors_include_cors_headers_for_the_frontend(self):
        headers = cors_headers_for_request(self.make_shutdown_request())

        self.assertEqual(headers["Access-Control-Allow-Origin"], "http://127.0.0.1:3000")
        self.assertEqual(headers["Access-Control-Allow-Credentials"], "true")

    def test_local_shutdown_rejects_remote_clients(self):
        with patch.dict("os.environ", {"APP_ENV": "development", "ALLOW_LOCAL_SHUTDOWN": "true"}):
            with self.assertRaises(HTTPException) as raised:
                shutdown_local_system(self.make_shutdown_request(client_host="192.168.1.25"), BackgroundTasks())
        self.assertEqual(raised.exception.status_code, 403)

    def test_local_shutdown_schedules_helper_for_loopback(self):
        background_tasks = BackgroundTasks()
        with patch.dict("os.environ", {"APP_ENV": "development", "ALLOW_LOCAL_SHUTDOWN": "true"}):
            response = shutdown_local_system(self.make_shutdown_request(), background_tasks)
        self.assertIn("stopping", response["message"].lower())
        self.assertEqual(len(background_tasks.tasks), 1)

    def test_hearing_role_phrases_assign_the_three_supported_speakers(self):
        labeled = assign_role_labels(
            [
                {"speaker": "Speaker 1", "start": 0, "end": 2, "text": "Respondent/Inirereklamo po ako."},
                {"speaker": "Speaker 2", "start": 2, "end": 4, "text": "Ako ang Desk Officer at Kagawad."},
                {"speaker": "Speaker 3", "start": 4, "end": 6, "text": "Magrereklamo po ako tungkol sa utang."},
            ],
            "blotter_hearing",
        )

        self.assertEqual(
            [segment["speaker"] for segment in labeled],
            ["Respondent", "Barangay Secretary/Mediator", "Complainant"],
        )

    def test_blotter_role_phrases_only_use_the_two_supported_speakers(self):
        labeled = assign_role_labels(
            [
                {"speaker": "Speaker 1", "start": 0, "end": 2, "text": "Barangay Secretary po ako."},
                {"speaker": "Speaker 2", "start": 2, "end": 4, "text": "Magrereklamo po ako."},
                {"speaker": "Speaker 3", "start": 4, "end": 5, "text": "Opo."},
            ],
            "blotter_case",
        )

        labels = {segment["speaker"] for segment in labeled}
        self.assertEqual(labels, {"Barangay Secretary/Mediator", "Complainant"})
        self.assertFalse(any(label.startswith("Speaker ") for label in labels))

    def test_recording_type_enforces_two_or_three_speaker_mode(self):
        self.assertEqual(speaker_count_for_recording_type("blotter_case", 3), 2)
        self.assertEqual(speaker_count_for_recording_type("blotter_hearing", 2), 3)

    def test_password_hash_is_salted_and_verifiable(self):
        first = password_hash("StrongPassword123!")
        second = password_hash("StrongPassword123!")

        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("StrongPassword123!", first))
        self.assertFalse(verify_password("wrong", first))

    def test_session_restore_recovers_and_reuses_csrf_token(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            admin = db.query(User).filter(User.username == "admin").first()
            role = db.query(Role).filter(Role.name == "system_admin").first()
            session = UserSession(
                user_id=admin.id,
                session_token_hash=hash_secret("session-token"),
                csrf_token_hash=hash_secret("old-token"),
                expires_at=datetime.utcnow() + timedelta(hours=1),
            )
            db.add(session)
            db.commit()
            context = AuthContext(user=admin, role=role, session=session, csrf_token="")

            first_response = Response()
            recovered = restore_csrf_token(db, self.make_auth_request(), first_response, context)
            first_hash = context.session.csrf_token_hash

            self.assertTrue(recovered)
            self.assertEqual(first_hash, hash_secret(recovered))
            self.assertIn("justice_kp_csrf=", first_response.headers["set-cookie"])

            second_response = Response()
            reused = restore_csrf_token(
                db,
                self.make_auth_request(csrf_cookie=recovered),
                second_response,
                context,
            )

            self.assertEqual(reused, recovered)
            self.assertEqual(context.session.csrf_token_hash, first_hash)
        finally:
            db.close()

    def test_seed_roles_and_create_user(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            admin = db.query(User).filter(User.username == "admin").first()
            role = db.query(Role).filter(Role.name == "system_admin").first()
            context = AuthContext(user=admin, role=role, session=None, csrf_token="")
            created = create_user(
                db,
                UserCreateRequest(
                    username="secretary",
                    full_name="Barangay Secretary",
                    role_name="barangay_secretary",
                    password="Secretary123!",
                ),
                context,
            )

            self.assertEqual(created.username, "secretary")
            self.assertTrue(verify_password("Secretary123!", created.password_hash))
        finally:
            db.close()

    def test_only_active_user_cannot_be_deactivated(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            admin = db.query(User).filter(User.username == "admin").first()
            role = db.query(Role).filter(Role.name == "system_admin").first()
            context = AuthContext(user=admin, role=role, session=None, csrf_token="")

            with self.assertRaises(HTTPException) as raised:
                update_user_status(db, admin.id, UserStatusRequest(is_active=False), context)

            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(
                raised.exception.detail,
                "This account cannot be deactivated because it is the only active user account. "
                "Create or activate another account before deactivating it.",
            )
            db.refresh(admin)
            self.assertTrue(admin.is_active)
        finally:
            db.close()

    def test_only_active_system_admin_cannot_be_deactivated_through_general_update(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            admin = db.query(User).filter(User.username == "admin").first()
            role = db.query(Role).filter(Role.name == "system_admin").first()
            context = AuthContext(user=admin, role=role, session=None, csrf_token="")
            create_user(
                db,
                UserCreateRequest(
                    username="secretary",
                    full_name="Barangay Secretary",
                    role_name="barangay_secretary",
                    password="Secretary123!",
                ),
                context,
            )

            with self.assertRaises(HTTPException) as raised:
                update_user(db, admin.id, UserUpdateRequest(is_active=False), context)

            self.assertEqual(raised.exception.status_code, 409)
            self.assertIn("only active system administrator", raised.exception.detail)
            db.refresh(admin)
            self.assertTrue(admin.is_active)
        finally:
            db.close()

    def test_backup_run_and_verify(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            admin = db.query(User).filter(User.username == "admin").first()
            role = db.query(Role).filter(Role.name == "system_admin").first()
            context = AuthContext(user=admin, role=role, session=None, csrf_token="")
            with tempfile.TemporaryDirectory() as directory:
                import backup_service

                backup_service.BACKUP_DIR = Path(directory)
                result = BackupService().run_backup(db, context)
                verified = BackupService().verify_backup(db, result["backup_id"], context)

                self.assertEqual(verified["status"], "verified")
                self.assertTrue(any(Path(directory).glob("*.jkpbackup")))
        finally:
            db.close()

    def test_backup_retention_expires_old_files(self):
        db = make_session()
        try:
            seed_roles_and_dev_admin(db)
            admin = db.query(User).filter(User.username == "admin").first()
            role = db.query(Role).filter(Role.name == "system_admin").first()
            context = AuthContext(user=admin, role=role, session=None, csrf_token="")
            with tempfile.TemporaryDirectory() as directory:
                import backup_service

                old_count = backup_service.BACKUP_RETENTION_COUNT
                old_days = backup_service.BACKUP_RETENTION_DAYS
                backup_service.BACKUP_DIR = Path(directory)
                backup_service.BACKUP_RETENTION_COUNT = 1
                backup_service.BACKUP_RETENTION_DAYS = 90
                try:
                    first = BackupService().run_backup(db, context)
                    second = BackupService().run_backup(db, context)
                    first_record = db.query(BackupRecord).filter(BackupRecord.backup_id == first["backup_id"]).first()
                    second_record = db.query(BackupRecord).filter(BackupRecord.backup_id == second["backup_id"]).first()

                    self.assertEqual(first_record.status, "retention_expired")
                    self.assertEqual(second_record.status, "created")
                    self.assertFalse(Path(first_record.file_path).exists())
                    self.assertTrue(Path(second_record.file_path).exists())
                finally:
                    backup_service.BACKUP_RETENTION_COUNT = old_count
                    backup_service.BACKUP_RETENTION_DAYS = old_days
        finally:
            db.close()

    def test_transcript_accuracy_metrics_are_persisted_and_reported(self):
        db = make_session()
        try:
            response = save_transcript(
                SaveTranscriptRequest(
                    content="Speaker 1: Magandang araw po\nSpeaker 2: May utang po siya",
                    segments=[
                        TranscriptSegment(speaker="Speaker 1", start=0, end=1, text="Magandang araw", confidence=0.91),
                        TranscriptSegment(speaker="Speaker 2", start=1, end=2, text="May utang siya", confidence=0.83),
                    ],
                    provider="local",
                    recording_type="blotter_case",
                    expected_speakers=2,
                    asr_confidence=0.87,
                    diarization_quality=1.0,
                    accuracy_metrics={"detected_speakers": 2},
                ),
                db,
            )
            transcript = db.query(Transcript).filter(Transcript.id == response["id"]).first()
            report = transcript_accuracy_report(db)

            self.assertEqual(transcript.asr_provider, "local")
            self.assertEqual(transcript.expected_speakers, 2)
            self.assertEqual(transcript.detected_speakers, 2)
            self.assertGreater(transcript.manual_correction_rate, 0)
            self.assertEqual(report["transcript_count"], 1)
            self.assertEqual(report["average_asr_confidence"], 0.87)
            self.assertEqual(report["by_provider"][0]["provider"], "local")
        finally:
            db.close()

    def test_transcript_correction_autosave_learns_role_labeled_edits(self):
        db = make_session()
        try:
            response = learn_transcript_corrections(
                LearnTranscriptCorrectionsRequest(
                    content="Complainant: May utang po siya",
                    segments=[
                        TranscriptSegment(speaker="Complainant", start=0, end=2, text="May otang po siya"),
                    ],
                ),
                db,
            )
            correction = db.query(PhraseCorrection).first()

            self.assertEqual(response["learned_corrections"], 1)
            self.assertEqual(db.query(Transcript).count(), 0)
            self.assertEqual(correction.wrong_phrase, "otang")
            self.assertEqual(correction.correct_phrase, "utang")
        finally:
            db.close()

    def test_unsafe_common_and_reciprocal_corrections_are_not_auto_applied(self):
        db = make_session()
        try:
            db.add_all(
                [
                    PhraseCorrection(wrong_phrase="po", correct_phrase="Opo"),
                    PhraseCorrection(wrong_phrase="salamat", correct_phrase="maraming salamat"),
                    PhraseCorrection(wrong_phrase="utang", correct_phrase="otang"),
                    PhraseCorrection(wrong_phrase="otang", correct_phrase="utang"),
                ]
            )
            db.commit()

            learned = get_learned_corrections(db)

            self.assertNotIn("po", learned)
            self.assertNotIn("utang", learned)
            self.assertNotIn("otang", learned)
            self.assertEqual(learned["salamat"], "maraming salamat")
        finally:
            db.close()

    def test_saved_edit_preserves_raw_text_accuracy_and_future_correction(self):
        db = make_session()
        try:
            response = save_transcript(
                SaveTranscriptRequest(
                    content="Complainant: May utang po siya",
                    segments=[
                        TranscriptSegment(
                            speaker="Complainant",
                            start=0,
                            end=2,
                            text="May otang po siya",
                            confidence=0.72,
                        ),
                    ],
                    provider="local",
                    recording_type="blotter_case",
                    expected_speakers=2,
                    asr_confidence=0.72,
                    diarization_quality=0.5,
                ),
                db,
            )
            transcript = db.query(Transcript).filter(Transcript.id == response["id"]).first()
            learned = get_learned_corrections(db)

            self.assertEqual(transcript.raw_content, "Complainant: May otang po siya")
            self.assertEqual(transcript.content, "Complainant: May utang po siya")
            self.assertEqual(transcript.corrections_json, [{"wrong": "otang", "corrected": "utang"}])
            self.assertEqual(transcript.accuracy_metrics_json["word_error_rate"], 0.25)
            self.assertEqual(transcript.accuracy_metrics_json["raw_word_accuracy"], 0.75)
            self.assertEqual(transcript.accuracy_metrics_json["edited_word_accuracy"], 1.0)
            self.assertEqual(normalize_transcript_text("May otang po siya", learned), "May utang po siya")
        finally:
            db.close()

    def test_duplicate_phrase_edits_save_one_correction_and_the_transcript(self):
        db = make_session()
        try:
            response = save_transcript(
                SaveTranscriptRequest(
                    content="Complainant: Po, magsasalita ako\nComplainant: Po, naiintindihan ko",
                    segments=[
                        TranscriptSegment(
                            speaker="Complainant",
                            start=0,
                            end=2,
                            text="Opo, magsasalita ako",
                            confidence=0.81,
                        ),
                        TranscriptSegment(
                            speaker="Complainant",
                            start=2,
                            end=4,
                            text="Opo, naiintindihan ko",
                            confidence=0.84,
                        ),
                    ],
                    provider="local",
                    recording_type="blotter_case",
                    expected_speakers=2,
                ),
                db,
            )

            correction = db.query(PhraseCorrection).filter(PhraseCorrection.wrong_phrase == "Opo").one()
            transcript = db.query(Transcript).filter(Transcript.id == response["id"]).one()

            self.assertEqual(response["learned_corrections"], 1)
            self.assertEqual(db.query(PhraseCorrection).count(), 1)
            self.assertEqual(correction.correct_phrase, "Po")
            self.assertIn("Po, magsasalita ako", transcript.content)
            self.assertEqual(
                transcript.raw_content,
                "Complainant: Opo, magsasalita ako\n\nComplainant: Opo, naiintindihan ko",
            )
        finally:
            db.close()

    def test_explicit_edited_segments_preserve_reviewer_timing_and_confidence(self):
        db = make_session()
        try:
            response = save_transcript(
                SaveTranscriptRequest(
                    content="Complainant: Unang inayos\nComplainant: Idinagdag ng reviewer",
                    segments=[
                        TranscriptSegment(
                            speaker="Complainant",
                            start=1.25,
                            end=3.5,
                            text="Unang raw",
                            confidence=0.61,
                        ),
                    ],
                    edited_segments=[
                        TranscriptSegment(
                            speaker="Complainant",
                            start=1.25,
                            end=3.5,
                            text="Unang inayos",
                            confidence=0.61,
                        ),
                        TranscriptSegment(
                            speaker="Complainant",
                            start=3.5,
                            end=5.0,
                            text="Idinagdag ng reviewer",
                            confidence=0.95,
                        ),
                    ],
                    provider="local",
                    recording_type="blotter_case",
                ),
                db,
            )
            transcript = db.query(Transcript).filter(Transcript.id == response["id"]).one()

            self.assertEqual(len(transcript.raw_segments_json), 1)
            self.assertEqual(len(transcript.segments_json), 2)
            self.assertEqual(transcript.segments_json[1]["start"], 3.5)
            self.assertEqual(transcript.segments_json[1]["end"], 5.0)
            self.assertEqual(transcript.segments_json[1]["confidence"], 0.95)
        finally:
            db.close()

    def test_corrections_are_learned_when_reviewer_splits_transcript_lines(self):
        db = make_session()
        try:
            response = save_transcript(
                SaveTranscriptRequest(
                    content="Complainant: May utang po\nComplainant: siya",
                    segments=[
                        TranscriptSegment(
                            speaker="Complainant",
                            start=0,
                            end=2,
                            text="May otang po siya",
                        ),
                    ],
                ),
                db,
            )
            transcript = db.query(Transcript).filter(Transcript.id == response["id"]).first()

            self.assertIn({"wrong": "otang", "corrected": "utang"}, transcript.corrections_json)
        finally:
            db.close()

    def test_manual_only_transcript_has_zero_correction_rate(self):
        db = make_session()
        try:
            response = save_transcript(
                SaveTranscriptRequest(
                    content="Barangay Secretary: Manually entered blotter narrative.",
                    segments=[],
                    provider="manual",
                    recording_type="blotter_case",
                ),
                db,
            )
            transcript = db.query(Transcript).filter(Transcript.id == response["id"]).first()
            report = transcript_accuracy_report(db)

            self.assertEqual(transcript.original_word_count, 0)
            self.assertEqual(transcript.correction_count, 0)
            self.assertEqual(transcript.manual_correction_rate, 0.0)
            self.assertEqual(transcript.accuracy_metrics_json["raw_word_accuracy"], 0.0)
            self.assertEqual(transcript.accuracy_metrics_json["edited_word_accuracy"], 1.0)
            self.assertEqual(transcript.accuracy_metrics_json["word_error_rate"], 1.0)
            self.assertEqual(report["average_manual_correction_rate"], 0.0)
        finally:
            db.close()

    def test_legacy_transcript_comparison_metrics_are_backfilled(self):
        db = make_session()
        try:
            transcript = Transcript(
                content="Complainant: corrected words",
                raw_content="Complainant: original words",
                segments_json=[],
                raw_segments_json=[],
                corrections_json=[],
                accuracy_metrics_json={"asr_confidence": 0.75},
                original_word_count=10,
                edited_word_count=8,
                correction_count=2,
                detected_speakers=2,
            )
            db.add(transcript)
            db.commit()

            with db.get_bind().begin() as connection:
                updated = backfill_transcript_metrics(connection)
            db.expire_all()

            self.assertEqual(updated, 1)
            self.assertEqual(transcript.accuracy_metrics_json["asr_confidence"], 0.75)
            self.assertEqual(transcript.accuracy_metrics_json["raw_word_accuracy"], 0.75)
            self.assertEqual(transcript.accuracy_metrics_json["edited_word_accuracy"], 1.0)
            self.assertEqual(transcript.accuracy_metrics_json["word_error_rate"], 0.25)
            self.assertEqual(transcript.diarization_quality, 0.8)
            self.assertEqual(transcript.accuracy_metrics_json["diarization_quality"], 0.8)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
