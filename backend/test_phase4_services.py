import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from database import Base  # noqa: E402
from models import CaseAnalysis, CaseInformation, ExtractedEntities, Transcript, XAITrace  # noqa: E402
from phase4_services import FORM_REGISTRY, Phase4FormService  # noqa: E402


class Phase4ServiceTests(unittest.TestCase):
    def test_registry_contains_official_kp_form_templates(self):
        service = Phase4FormService(Path(__file__).resolve().parent / "generated_forms_test")
        registry = service.registry()

        self.assertGreaterEqual(len(registry), 20)
        self.assertEqual(service.template_dir.name, "KP_Updated_Forms")
        self.assertIn("kp-form-16", {item["form_id"] for item in registry})
        self.assertIn("required_fields", registry[0])

    def test_form_selection_uses_phase3_final_action(self):
        service = Phase4FormService(Path(__file__).resolve().parent / "generated_forms_test")
        dashboard = {"phase3": {"final_recommended_action": "Refer to Court", "official_decision": None}}
        recommended, optional = service.recommended_templates(dashboard)

        self.assertEqual([item.form_id for item in recommended], ["kp-form-20", "kp-form-20-a"])
        self.assertEqual([item.form_id for item in optional], ["kp-form-20-b"])

    def test_validation_tracks_missing_fields_and_accuracy(self):
        service = Phase4FormService(Path(__file__).resolve().parent / "generated_forms_test")
        template = next(item for item in FORM_REGISTRY if item.form_id == "kp-form-7")
        values = {field: "ok" for field in template.required_fields}
        values["parties"] = ""
        missing, status, accuracy = service.validation_summary([template], values)

        self.assertEqual(missing["kp-form-7"], ["parties"])
        self.assertEqual(status, "needs_review")
        self.assertLess(accuracy, 100)

    def test_generated_pdf_is_valid_pdf_bytes(self):
        service = Phase4FormService(Path(__file__).resolve().parent / "generated_forms_test")
        content = service.render_pdf(["JUSTICE-KP", "KP Form 7", "Case ID: KP-2026-TEST"])

        self.assertTrue(content.startswith(b"%PDF-1.4"))
        self.assertIn(b"%%EOF", content)

    def test_all_generated_pdfs_preserve_the_original_blank_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            service = Phase4FormService(Path(directory))
            for template in FORM_REGISTRY:
                with self.subTest(form_id=template.form_id):
                    original = service.official_template_path(template).read_bytes()
                    output_path = service.write_pdf(
                        "KP-2026-TEMPLATE", 1, template,
                        {"transcript_summary": "Private case information"}, [],
                    )
                    self.assertEqual(output_path.read_bytes(), original)

    def test_missing_template_does_not_generate_a_substitute_attachment(self):
        with tempfile.TemporaryDirectory() as directory:
            service = Phase4FormService(Path(directory), template_dir=Path(directory))
            with self.assertRaises(HTTPException) as raised:
                service.write_pdf("KP-2026-MISSING", 1, FORM_REGISTRY[0], {}, [])
            self.assertEqual(raised.exception.status_code, 404)
            self.assertEqual(list(Path(directory).glob("*.pdf")), [])

    def test_generate_packet_persists_forms_and_pdf(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            transcript = Transcript(content="Speaker 1: May utang po siya at payag sa hulugan.", segments_json=[])
            case_info = CaseInformation(
                transcript_id=1,
                case_id="KP-2026-P4",
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
            extracted = ExtractedEntities(transcript_id=1, entities_json={"speaker_roles": ["Speaker 1", "Speaker 2"]})
            trace = XAITrace(trace_json=["R01 Fired"], trace_text="R01 Fired")
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
            db.commit()

            with tempfile.TemporaryDirectory() as directory:
                service = Phase4FormService(Path(directory))
                packet = service.generate_packet(
                    db,
                    "KP-2026-P4",
                    SimpleNamespace(form_ids=["kp-form-7"], generated_by="tester", approved_by="", field_overrides={}),
                )
                response = service.packet_response(db, packet)

                self.assertEqual(response["generated_form_count"], 1)
                self.assertEqual(response["generated_forms"][0]["form_id"], "kp-form-7")
                self.assertTrue(Path(response["generated_forms"][0]["download_url"]).name.endswith("download"))
                self.assertTrue(any(Path(directory).glob("*.pdf")))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
