import hashlib
import sys
import unittest
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import HTTPException  # noqa: E402
from pypdf import PdfReader  # noqa: E402
from starlette.requests import Request  # noqa: E402

from completed_transcript_pdf import CompletedTranscriptPdfService  # noqa: E402
from main import (  # noqa: E402
    completed_case_summary,
    delete_transcript,
    delete_workflow_draft,
    download_completed_transcript_pdf,
)
from models import AuditLog, Transcript  # noqa: E402
from test_completed_case_summary import (  # noqa: E402
    add_analysis,
    make_context,
    make_session,
)
from auth_service import seed_roles_and_dev_admin  # noqa: E402


def request_for(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": [(b"user-agent", b"JUSTICE-KP PDF test")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
        }
    )


class CompletedTranscriptPdfTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed_roles_and_dev_admin(self.db)

    def tearDown(self):
        self.db.close()

    def add_completed_workflow(self, owner, workflow_id, analysis):
        from models import CaseInformation, WorkflowDraft

        case_id = (
            self.db.query(CaseInformation)
            .filter(CaseInformation.id == analysis.case_information_id)
            .one()
            .case_id
        )
        finalized_at = datetime(2026, 9, 19, 8, 30, tzinfo=timezone.utc)
        workflow = WorkflowDraft(
            workflow_id=workflow_id,
            owner_user_id=owner.user.id,
            status="completed",
            active_step=7,
            max_unlocked_step=7,
            case_id=case_id,
            transcript_id=analysis.transcript_id,
            case_analysis_id=analysis.id,
            payload_json={
                "outcome": "Amicable Settlement Reached",
                "caseRecordStatus": "Amicable Settlement Reached",
                "finalizedAt": finalized_at.isoformat(),
            },
            created_at=analysis.created_at,
            updated_at=finalized_at.replace(tzinfo=None),
        )
        self.db.add(workflow)
        self.db.commit()
        return workflow

    def test_long_unicode_transcript_is_multipage_a4_and_not_truncated(self):
        admin = make_context(self.db)
        segments = []
        for index in range(180):
            marker = " FINAL-UNICODE-MARKER" if index == 179 else ""
            segments.append(
                {
                    "speaker": "Complainant" if index % 2 else "Barangay Secretary/Mediator",
                    "start": index * 3.25,
                    "end": (index + 1) * 3.25,
                    "text": f"Pahayag {index + 1}: Buong salaysay, may ñ at ₱ simbolo.{marker}",
                }
            )
        transcript_text = "\n".join(f"{item['speaker']}: {item['text']}" for item in segments)
        analysis = add_analysis(
            self.db,
            "KP-2026-LONG-PDF",
            "within_kp",
            transcript_text,
            segments=segments,
        )
        self.add_completed_workflow(admin, "workflow-long-pdf", analysis)
        summary = completed_case_summary("workflow-long-pdf", admin, self.db)

        artifact = CompletedTranscriptPdfService().build(
            summary,
            generated_by="System Administrator",
            generated_by_username="admin",
            generated_at=datetime(2026, 9, 19, 9, 0, tzinfo=timezone.utc),
            document_id="fixed-document-id",
        )
        reader = PdfReader(BytesIO(artifact.content))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

        self.assertGreater(len(reader.pages), 2)
        self.assertEqual(artifact.page_count, len(reader.pages))
        self.assertAlmostEqual(float(reader.pages[0].mediabox.width), 595.28, places=1)
        self.assertAlmostEqual(float(reader.pages[0].mediabox.height), 841.89, places=1)
        self.assertIn("FINAL-UNICODE-MARKER", extracted)
        self.assertIn("Pahayag 1", extracted)
        self.assertIn("₱", extracted)
        self.assertIn("Complainant", extracted)
        self.assertIn("Page 1", extracted)
        self.assertIn("Decision-support disclaimer", extracted)
        self.assertEqual(reader.metadata.author, "System Administrator")
        self.assertEqual(hashlib.sha256(artifact.content).hexdigest(), artifact.sha256)

    def test_download_records_hash_and_generation_metadata_in_audit(self):
        admin = make_context(self.db)
        analysis = add_analysis(
            self.db,
            "KP-2026-AUDITED-PDF",
            "within_kp",
            "Complainant: Kumpleto ang pinal na salaysay.",
        )
        workflow = self.add_completed_workflow(admin, "workflow-audited-pdf", analysis)
        request = request_for(f"/api/management/cases/{workflow.workflow_id}/transcript.pdf")

        response = download_completed_transcript_pdf(workflow.workflow_id, request, admin, self.db)

        self.assertEqual(response.media_type, "application/pdf")
        self.assertTrue(response.body.startswith(b"%PDF-"))
        self.assertEqual(hashlib.sha256(response.body).hexdigest(), response.headers["x-document-sha256"])
        self.assertEqual(response.headers["cache-control"], "private, no-store, max-age=0")
        audit = (
            self.db.query(AuditLog)
            .filter(AuditLog.action == "completed_transcript_pdf_generated_downloaded")
            .one()
        )
        self.assertEqual(audit.actor, admin.user.username)
        self.assertEqual(audit.actor_user_id, admin.user.id)
        self.assertEqual(audit.resource_id, response.headers["x-document-id"])
        self.assertEqual(audit.details_json["sha256"], response.headers["x-document-sha256"])
        self.assertEqual(audit.details_json["transcript_scope"], "latest_final_reviewer_approved_transcript")
        self.assertGreaterEqual(audit.details_json["page_count"], 1)

    def test_export_requires_report_permission_in_addition_to_transcript_access(self):
        member = make_context(self.db, "member", "lupon_member")
        analysis = add_analysis(self.db, "KP-2026-NO-EXPORT", "within_kp", "Complainant: Salaysay")
        workflow = self.add_completed_workflow(member, "workflow-no-export", analysis)
        summary = completed_case_summary(workflow.workflow_id, member, self.db)

        self.assertTrue(summary["actions"]["can_view_transcript"])
        self.assertFalse(summary["actions"]["can_download_transcript_pdf"])
        with self.assertRaises(HTTPException) as raised:
            download_completed_transcript_pdf(
                workflow.workflow_id,
                request_for(f"/api/management/cases/{workflow.workflow_id}/transcript.pdf"),
                member,
                self.db,
            )
        self.assertEqual(raised.exception.status_code, 403)

    def test_completed_transcript_and_workflow_are_protected_from_ordinary_deletion(self):
        admin = make_context(self.db)
        analysis = add_analysis(self.db, "KP-2026-RETAINED", "within_kp", "Complainant: Preserve this.")
        workflow = self.add_completed_workflow(admin, "workflow-retained", analysis)

        with self.assertRaises(HTTPException) as transcript_error:
            delete_transcript(analysis.transcript_id, admin, self.db)
        self.assertEqual(transcript_error.exception.status_code, 409)
        self.assertIsNotNone(self.db.query(Transcript).filter(Transcript.id == analysis.transcript_id).first())

        with self.assertRaises(HTTPException) as workflow_error:
            delete_workflow_draft(workflow.workflow_id, admin, self.db)
        self.assertEqual(workflow_error.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
