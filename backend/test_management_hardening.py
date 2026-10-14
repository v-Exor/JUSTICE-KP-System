import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from starlette.requests import Request  # noqa: E402

from auth_service import seed_roles_and_dev_admin  # noqa: E402
from database import reconcile_duplicate_transcript_identities  # noqa: E402
from main import (  # noqa: E402
    download_evidence,
    get_completed_case_summary,
    get_paginated_finalized_workflow_cases,
    get_phase3_dashboard,
    get_transcript,
    get_transcripts,
    process_phase3_pipeline,
    update_evidence,
)
from models import (  # noqa: E402
    AuditLog,
    CaseInformation,
    Evidence,
    Phase4GeneratedForm,
    Phase5ValidationCase,
    Transcript,
    WorkflowDraft,
)
from phase3_schemas import EvidenceUpdateRequest  # noqa: E402
from phase4_services import Phase4FormService  # noqa: E402
from test_completed_case_summary import add_analysis, make_context, make_session  # noqa: E402


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
            "headers": [(b"user-agent", b"JUSTICE-KP hardening test")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
        }
    )


class ManagementHardeningTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        seed_roles_and_dev_admin(self.db)

    def tearDown(self):
        self.db.close()

    def add_completed_workflow(self, owner, workflow_id, analysis):
        now = datetime.utcnow()
        case_information = self.db.query(CaseInformation).filter(
            CaseInformation.id == analysis.case_information_id
        ).one()
        case_id = case_information.case_id
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
                "outcome": "Referred to WCPD / PNP",
                "caseRecordStatus": "Referred to WCPD / PNP",
                "finalizedAt": now.isoformat(),
                "caseInformation": {
                    "case_id": case_id,
                    "has_vawc_or_child_abuse_indicators": bool(
                        case_information.has_vawc_or_child_abuse_indicators
                    ),
                },
            },
            created_at=analysis.created_at - timedelta(minutes=1),
            updated_at=now,
        )
        self.db.add(workflow)
        self.db.commit()
        return workflow

    def test_sensitive_records_are_removed_before_search_and_total_counts(self):
        viewer = make_context(self.db, "secureviewer", "viewer")
        analysis = add_analysis(
            self.db,
            "KP-2026-SECURE",
            "outside_kp",
            "Protected complainant narrative",
            sensitive=True,
        )
        workflow = self.add_completed_workflow(viewer, "workflow-secure", analysis)

        listing = get_paginated_finalized_workflow_cases(
            "secure", "", "", 1, 10, viewer, self.db
        )

        self.assertEqual(listing["items"], [])
        self.assertEqual(listing["total"], 0)
        self.assertEqual(listing["total_pages"], 0)
        transcript_listing = get_transcripts(self.db, context=viewer)
        self.assertEqual(transcript_listing["items"], [])
        self.assertEqual(transcript_listing["total"], 0)
        with self.assertRaises(HTTPException) as hidden_detail:
            get_transcript(analysis.transcript_id, self.db, viewer)
        self.assertEqual(hidden_detail.exception.status_code, 404)

        # Exact, owner-known access remains useful but is fully redacted and audited.
        summary = get_completed_case_summary(
            workflow.workflow_id,
            request_for(f"/api/management/cases/{workflow.workflow_id}"),
            viewer,
            self.db,
        )
        self.assertTrue(summary["privacy"]["redacted"])
        self.assertEqual(summary["phase2_analysis"]["rule_results"], [])
        self.assertEqual(summary["xai_reasoning"]["trace"], [])
        audit = self.db.query(AuditLog).filter(
            AuditLog.action == "sensitive_case_record_accessed"
        ).one()
        self.assertTrue(audit.details_json["redacted"])
        with self.assertRaises(HTTPException) as immutable:
            process_phase3_pipeline(workflow.case_id, self.db)
        self.assertEqual(immutable.exception.status_code, 409)

    def test_generated_form_with_missing_packet_is_not_downloadable(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "orphan.pdf"
            file_path.write_bytes(b"%PDF-1.4\n%%EOF")
            form = Phase4GeneratedForm(
                packet_id=999,
                case_id="KP-ORPHAN",
                form_id="kp-form-7",
                title="KP Form 7",
                purpose="Test",
                file_path=str(file_path),
                field_values_json={},
                missing_fields_json=[],
                validation_status="ready",
            )
            self.db.add(form)
            self.db.commit()

            with self.assertRaises(HTTPException) as orphan:
                Phase4FormService(Path(directory)).generated_form_file(self.db, form.id)
            self.assertEqual(orphan.exception.status_code, 404)

    def test_research_import_transcript_is_excluded_from_operational_search(self):
        viewer = make_context(self.db, "researchviewer", "viewer")
        research_analysis = add_analysis(
            self.db,
            "RESEARCH-ONLY-001",
            "within_kp",
            "Needle research transcript",
        )
        self.db.add(
            Phase5ValidationCase(
                case_id="RESEARCH-ONLY-001",
                analysis_id=research_analysis.id,
                dataset_split="validation",
                notes="Imported research artifact",
            )
        )
        operational = Transcript(
            case_id="KP-2026-OPERATIONAL",
            content="Needle operational transcript",
            raw_content="Needle operational transcript",
            segments_json=[],
            corrections_json=[],
        )
        self.db.add(operational)
        self.db.commit()

        listing = get_transcripts(self.db, q="needle", context=viewer)

        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["id"], operational.id)
        with self.assertRaises(HTTPException) as hidden_detail:
            get_transcript(research_analysis.transcript_id, self.db, viewer)
        self.assertEqual(hidden_detail.exception.status_code, 404)

    def test_duplicate_historical_case_ids_keep_separate_workflow_transcripts(self):
        owner = make_context(self.db, "historyowner", "barangay_secretary")
        first = Transcript(
            workflow_id="history-workflow-one",
            case_id="KP-HISTORICAL-DUP",
            content="First historical workflow",
            raw_content="First historical workflow",
            segments_json=[],
            corrections_json=[],
        )
        second = Transcript(
            workflow_id="history-workflow-two",
            case_id=None,
            content="Second historical workflow",
            raw_content="Second historical workflow",
            segments_json=[],
            corrections_json=[],
        )
        self.db.add_all([first, second])
        self.db.flush()
        now = datetime.utcnow()
        self.db.add_all(
            [
                WorkflowDraft(
                    workflow_id=first.workflow_id,
                    owner_user_id=owner.user.id,
                    status="active",
                    active_step=2,
                    max_unlocked_step=2,
                    case_id="KP-HISTORICAL-DUP",
                    transcript_id=first.id,
                    payload_json={"caseInformation": {"case_id": "KP-HISTORICAL-DUP"}},
                    updated_at=now - timedelta(minutes=1),
                ),
                WorkflowDraft(
                    workflow_id=second.workflow_id,
                    owner_user_id=owner.user.id,
                    status="active",
                    active_step=2,
                    max_unlocked_step=2,
                    case_id="KP-HISTORICAL-DUP",
                    transcript_id=second.id,
                    payload_json={"caseInformation": {"case_id": "KP-HISTORICAL-DUP"}},
                    updated_at=now,
                ),
            ]
        )
        self.db.commit()

        listing = get_transcripts(self.db, q="historical", context=owner)

        self.assertEqual(listing["total"], 2)
        self.assertEqual(
            {item["workflow_id"] for item in listing["items"]},
            {"history-workflow-one", "history-workflow-two"},
        )
        self.assertTrue(all(item["case_id"] == "KP-HISTORICAL-DUP" for item in listing["items"]))

    def test_completed_evidence_is_readable_but_not_editable(self):
        owner = make_context(self.db, "evidenceowner", "barangay_secretary")
        analysis = add_analysis(
            self.db,
            "KP-2026-EVIDENCE",
            "within_kp",
            "Completed evidence transcript",
        )
        self.add_completed_workflow(owner, "workflow-evidence", analysis)
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "evidence.txt"
            evidence_path.write_text("original evidence", encoding="utf-8")
            evidence = Evidence(
                case_id="KP-2026-EVIDENCE",
                file_name="evidence.txt",
                file_type="txt",
                file_path=str(evidence_path),
                ocr_text="original evidence",
                extracted_entities_json={},
            )
            self.db.add(evidence)
            self.db.commit()

            with self.assertRaises(HTTPException) as immutable:
                update_evidence(
                    evidence.id,
                    EvidenceUpdateRequest(evidence_text="changed evidence"),
                    self.db,
                )
            self.assertEqual(immutable.exception.status_code, 409)
            response = download_evidence(evidence.id, self.db, owner)
            self.assertEqual(Path(response.path).resolve(), evidence_path.resolve())

    def test_direct_phase3_read_hides_sensitive_case_without_permission(self):
        viewer = make_context(self.db, "phase3viewer", "viewer")
        analysis = add_analysis(
            self.db,
            "KP-2026-DIRECT-PROTECTED",
            "outside_kp",
            "Protected direct dashboard narrative",
            sensitive=True,
        )
        self.add_completed_workflow(viewer, "workflow-direct-protected", analysis)

        with self.assertRaises(HTTPException) as hidden:
            get_phase3_dashboard("KP-2026-DIRECT-PROTECTED", self.db, viewer)
        self.assertEqual(hidden.exception.status_code, 404)

        admin = make_context(self.db)
        dashboard = get_phase3_dashboard("KP-2026-DIRECT-PROTECTED", self.db, admin)
        self.assertEqual(dashboard["case_id"], "KP-2026-DIRECT-PROTECTED")
        audited = self.db.query(AuditLog).filter(
            AuditLog.action == "sensitive_case_record_accessed",
            AuditLog.resource_type == "phase3_dashboard",
        ).one()
        self.assertEqual(audited.resource_id, "KP-2026-DIRECT-PROTECTED")


class DuplicateTranscriptMigrationTests(unittest.TestCase):
    def test_duplicate_identity_reconciliation_prefers_workflow_link_and_preserves_other_workflows(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE transcripts (id INTEGER PRIMARY KEY, workflow_id TEXT, case_id TEXT, superseded_by_transcript_id INTEGER)"
            ))
            connection.execute(text(
                "CREATE TABLE workflow_drafts (id INTEGER PRIMARY KEY, transcript_id INTEGER)"
            ))
            connection.execute(text(
                "INSERT INTO transcripts (id, workflow_id, case_id) VALUES "
                "(1, 'wf-one', 'KP-DUP'), (2, 'wf-one', 'KP-DUP'), (3, 'wf-three', 'KP-DUP')"
            ))
            connection.execute(text("INSERT INTO workflow_drafts (id, transcript_id) VALUES (1, 2), (2, 3)"))

            review = reconcile_duplicate_transcript_identities(connection)
            rows = list(connection.execute(text(
                "SELECT id, workflow_id, case_id, superseded_by_transcript_id FROM transcripts ORDER BY id"
            )).mappings())

        self.assertEqual(review["workflow_id"][0]["canonical_id"], 2)
        self.assertEqual(rows[0]["superseded_by_transcript_id"], 2)
        self.assertIsNone(rows[0]["workflow_id"])
        self.assertIsNone(rows[1]["case_id"])
        self.assertEqual(rows[2]["case_id"], "KP-DUP")
        self.assertIsNone(rows[2]["superseded_by_transcript_id"])


if __name__ == "__main__":
    unittest.main()
