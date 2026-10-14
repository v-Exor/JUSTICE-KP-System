from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from time import perf_counter
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import (
    AuditLog,
    ExtractedEntities,
    Phase4FormPacket,
    Phase4GeneratedForm,
)
from phase3_services import Phase3DashboardService, get_phase2_bundle, serialize_model


@dataclass(frozen=True)
class FormTemplate:
    form_id: str
    form_number: str
    title: str
    purpose: str
    stage: str
    required_fields: list[str]
    when_used: list[str]


BASE_REQUIRED_FIELDS = [
    "case_id",
    "barangay_name",
    "city_municipality",
    "case_year",
    "dispute_category",
    "parties",
    "final_recommended_action",
]

FORM_REGISTRY: list[FormTemplate] = [
    FormTemplate("kp-form-7", "7", "KP Form 7", "Initial complaint and case record packet.", "Complaint", BASE_REQUIRED_FIELDS + ["transcript_summary"], ["Proceed to Mediation", "Schedule Hearing", "Manual Review Required"]),
    FormTemplate("kp-form-8", "8", "KP Form 8", "Notice of hearing or mediation schedule.", "Notice", BASE_REQUIRED_FIELDS + ["hearing_schedule"], ["Proceed to Mediation", "Schedule Hearing", "Awaiting Evidence"]),
    FormTemplate("kp-form-9", "9", "KP Form 9", "Notice for respondent or party appearance.", "Notice", BASE_REQUIRED_FIELDS + ["hearing_schedule"], ["Proceed to Mediation", "Schedule Hearing"]),
    FormTemplate("kp-form-10", "10", "KP Form 10", "Pangkat constitution notice.", "Pangkat", BASE_REQUIRED_FIELDS + ["hearing_schedule"], ["Proceed to Mediation"]),
    FormTemplate("kp-form-11", "11", "KP Form 11", "Pangkat proceeding record.", "Pangkat", BASE_REQUIRED_FIELDS + ["xai_trace_summary"], ["Proceed to Mediation"]),
    FormTemplate("kp-form-12", "12", "KP Form 12", "Conciliation hearing notice.", "Notice", BASE_REQUIRED_FIELDS + ["hearing_schedule"], ["Proceed to Mediation"]),
    FormTemplate("kp-form-13", "13", "KP Form 13", "Pangkat hearing documentation.", "Pangkat", BASE_REQUIRED_FIELDS + ["mediation_terms"], ["Proceed to Mediation"]),
    FormTemplate("kp-form-14", "14", "KP Form 14", "Pangkat action record.", "Pangkat", BASE_REQUIRED_FIELDS + ["mediation_terms"], ["Proceed to Mediation"]),
    FormTemplate("kp-form-15", "15", "KP Form 15", "Pangkat proceeding summary.", "Pangkat", BASE_REQUIRED_FIELDS + ["xai_trace_summary"], ["Proceed to Mediation"]),
    FormTemplate("kp-form-16", "16", "KP Form 16", "Kasunduang Pag-aayos or amicable settlement.", "Settlement", BASE_REQUIRED_FIELDS + ["mediation_terms", "official_decision"], ["Settlement/Final Output", "Proceed to Mediation"]),
    FormTemplate("kp-form-17", "17", "KP Form 17", "Settlement follow-through record.", "Settlement", BASE_REQUIRED_FIELDS + ["mediation_terms", "official_decision"], ["Settlement/Final Output"]),
    FormTemplate("kp-form-18", "18", "KP Form 18", "Settlement action and compliance record.", "Settlement", BASE_REQUIRED_FIELDS + ["official_decision"], ["Settlement/Final Output"]),
    FormTemplate("kp-form-19", "19", "KP Form 19", "Post-mediation documentation.", "Settlement", BASE_REQUIRED_FIELDS + ["official_decision"], ["Settlement/Final Output"]),
    FormTemplate("kp-form-20", "20", "KP Form 20", "Certification to file action or unresolved case certification.", "Certification", BASE_REQUIRED_FIELDS + ["referral_reason", "xai_trace_summary"], ["Refer to Court", "Manual Review Required"]),
    FormTemplate("kp-form-20-a", "20-A", "KP Form 20-A", "Supplemental certification for referred or unresolved action.", "Certification", BASE_REQUIRED_FIELDS + ["referral_reason", "xai_trace_summary"], ["Refer to Court", "Refer to PNP WCPD", "Refer to MSWDO"]),
    FormTemplate("kp-form-20-b", "20-B", "KP Form 20-B", "Supplemental certification for subsequent action.", "Certification", BASE_REQUIRED_FIELDS + ["referral_reason", "official_decision"], ["Refer to Court", "Manual Review Required"]),
    FormTemplate("kp-form-21", "21", "KP Form 21", "Execution or post-settlement case form.", "Execution", BASE_REQUIRED_FIELDS + ["official_decision"], ["Settlement/Final Output"]),
    FormTemplate("kp-form-22", "22", "KP Form 22", "Execution follow-through documentation.", "Execution", BASE_REQUIRED_FIELDS + ["official_decision"], ["Settlement/Final Output"]),
    FormTemplate("kp-form-23", "23", "KP Form 23", "Compliance documentation.", "Execution", BASE_REQUIRED_FIELDS + ["official_decision"], ["Settlement/Final Output"]),
    FormTemplate("kp-form-24", "24", "KP Form 24", "Execution-stage case documentation.", "Execution", BASE_REQUIRED_FIELDS + ["official_decision"], ["Settlement/Final Output"]),
    FormTemplate("kp-form-25", "25", "KP Form 25", "Final execution or compliance documentation.", "Execution", BASE_REQUIRED_FIELDS + ["official_decision"], ["Settlement/Final Output"]),
]


class Phase4FormService:
    def __init__(self, output_dir: Path, template_dir: Path | None = None):
        self.output_dir = output_dir
        self.template_dir = template_dir or Path(__file__).resolve().parent.parent / "docs" / "KP_Updated_Forms"
        self.output_dir.mkdir(exist_ok=True)

    def registry(self) -> list[dict[str, Any]]:
        return [self.template_to_dict(template) for template in FORM_REGISTRY]

    def template_to_dict(self, template: FormTemplate) -> dict[str, Any]:
        return {
            "form_id": template.form_id,
            "form_number": template.form_number,
            "title": template.title,
            "purpose": template.purpose,
            "stage": template.stage,
            "required_fields": template.required_fields,
            "when_used": template.when_used,
            "source_template_url": f"/api/kp-forms/{template.form_id}/download",
        }

    def template_map(self) -> dict[str, FormTemplate]:
        return {template.form_id: template for template in FORM_REGISTRY}

    def dashboard(self, db: Session, case_id: str) -> dict[str, Any]:
        return Phase3DashboardService().build(db, case_id)

    def final_action_key(self, dashboard: dict[str, Any]) -> str:
        action = dashboard["phase3"]["final_recommended_action"]
        official = dashboard["phase3"].get("official_decision")
        if official and "settlement" in str(official.get("official_decision", "")).lower():
            return "Settlement/Final Output"
        return action

    def recommended_templates(self, dashboard: dict[str, Any]) -> tuple[list[FormTemplate], list[FormTemplate]]:
        action = self.final_action_key(dashboard)
        if action == "Proceed to Mediation":
            recommended_ids = ["kp-form-7", "kp-form-8", "kp-form-16"]
            optional_ids = ["kp-form-9", "kp-form-10", "kp-form-12"]
        elif action == "Awaiting Evidence":
            recommended_ids = ["kp-form-7"]
            optional_ids = ["kp-form-8", "kp-form-9"]
        elif action == "Schedule Hearing":
            recommended_ids = ["kp-form-7", "kp-form-8", "kp-form-9"]
            optional_ids = ["kp-form-12"]
        elif action == "Refer to PNP WCPD":
            recommended_ids = ["kp-form-20-a"]
            optional_ids = ["kp-form-20-b"]
        elif action == "Refer to MSWDO":
            recommended_ids = ["kp-form-20-a"]
            optional_ids = ["kp-form-20-b"]
        elif action == "Refer to Court":
            recommended_ids = ["kp-form-20", "kp-form-20-a"]
            optional_ids = ["kp-form-20-b"]
        elif action == "Manual Review Required":
            recommended_ids = ["kp-form-7", "kp-form-20"]
            optional_ids = ["kp-form-20-b"]
        elif action == "Settlement/Final Output":
            recommended_ids = ["kp-form-16", "kp-form-17", "kp-form-21"]
            optional_ids = ["kp-form-18", "kp-form-19", "kp-form-22", "kp-form-23", "kp-form-24", "kp-form-25"]
        else:
            recommended_ids = ["kp-form-7"]
            optional_ids = ["kp-form-20"]

        templates = self.template_map()
        return (
            [templates[form_id] for form_id in recommended_ids if form_id in templates],
            [templates[form_id] for form_id in optional_ids if form_id in templates],
        )

    def extracted_entities(self, db: Session, case_id: str) -> dict[str, Any]:
        bundle = get_phase2_bundle(db, case_id)
        extracted = db.query(ExtractedEntities).filter(ExtractedEntities.id == bundle.analysis.extracted_entities_id).first()
        return extracted.entities_json if extracted else {}

    def build_field_values(
        self,
        db: Session,
        dashboard: dict[str, Any],
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        case_info = dashboard["phase2"]["case_information"]
        phase3 = dashboard["phase3"]
        entities = self.extracted_entities(db, dashboard["case_id"])
        hearings = phase3.get("hearings") or []
        referrals = phase3.get("referrals") or []
        suggestions = (phase3.get("mediation_suggestions") or {}).get("suggestions_json") or []
        official = phase3.get("official_decision") or {}
        xai_trace = dashboard["phase2"].get("xai_trace") or []
        transcript = dashboard["phase1"].get("transcript") or ""
        parties = entities.get("speaker_roles") or []

        latest_hearing = hearings[-1] if hearings else {}
        referral = referrals[0] if referrals else {}
        mediation_terms = [
            f"{item.get('title')}: {', '.join(item.get('recommended_terms') or [])}"
            for item in suggestions
        ]

        values = {
            **case_info,
            "case_id": dashboard["case_id"],
            "parties": ", ".join(parties),
            "transcript_summary": transcript[:700],
            "final_recommended_action": phase3["final_recommended_action"],
            "hearing_schedule": self.format_hearing(latest_hearing),
            "mediation_terms": "; ".join(mediation_terms),
            "referral_reason": referral.get("reason", ""),
            "referral_destination": referral.get("destination", ""),
            "official_decision": official.get("official_decision", ""),
            "approved_by": official.get("approved_by", ""),
            "emotion_tension": (phase3.get("emotion_analysis") or {}).get("tension_score", ""),
            "xai_trace_summary": " | ".join(xai_trace[:5]),
            "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        }
        values.update(overrides or {})
        return values

    def format_hearing(self, hearing: dict[str, Any]) -> str:
        if not hearing:
            return ""
        return f"{hearing.get('scheduled_date', '')} {hearing.get('scheduled_time', '')} at {hearing.get('location', '')}".strip()

    def missing_fields(self, template: FormTemplate, values: dict[str, Any]) -> list[str]:
        return [field for field in template.required_fields if not values.get(field)]

    def validation_summary(self, templates: list[FormTemplate], values: dict[str, Any]) -> tuple[dict[str, list[str]], str, float]:
        missing = {template.form_id: self.missing_fields(template, values) for template in templates}
        total_required = sum(len(template.required_fields) for template in templates)
        total_missing = sum(len(items) for items in missing.values())
        accuracy = 100.0 if total_required == 0 else round(((total_required - total_missing) / total_required) * 100, 2)
        status = "ready" if total_missing == 0 else "needs_review"
        return missing, status, accuracy

    def recommendation(self, db: Session, case_id: str) -> dict[str, Any]:
        dashboard = self.dashboard(db, case_id)
        recommended, optional = self.recommended_templates(dashboard)
        values = self.build_field_values(db, dashboard)
        missing, status, accuracy = self.validation_summary(recommended, values)
        return {
            "case_id": dashboard["case_id"],
            "final_recommended_action": dashboard["phase3"]["final_recommended_action"],
            "recommended_forms": [self.template_to_dict(template) for template in recommended],
            "optional_forms": [self.template_to_dict(template) for template in optional],
            "missing_fields": missing,
            "validation_status": status,
            "form_accuracy_pct": accuracy,
        }

    def generate_packet(self, db: Session, case_id: str, payload: Any) -> Phase4FormPacket:
        started = perf_counter()
        dashboard = self.dashboard(db, case_id)
        recommended, _ = self.recommended_templates(dashboard)
        templates_by_id = self.template_map()
        requested_ids = payload.form_ids or [template.form_id for template in recommended]
        selected = [templates_by_id[form_id] for form_id in requested_ids if form_id in templates_by_id]
        if not selected:
            raise HTTPException(status_code=400, detail="No valid KP form IDs were selected.")
        for template in selected:
            self.blank_template_file(template.form_id)

        values = self.build_field_values(db, dashboard, payload.field_overrides)
        missing, status, accuracy = self.validation_summary(selected, values)
        processing_time_min = round((perf_counter() - started) / 60, 4)
        approved_by = payload.approved_by.strip()

        packet = Phase4FormPacket(
            case_id=dashboard["case_id"],
            source_phase3_action=dashboard["phase3"]["final_recommended_action"],
            selected_forms_json=[template.form_id for template in selected],
            generated_form_count=len(selected),
            missing_fields_json=missing,
            validation_status=status,
            form_accuracy_pct=accuracy,
            processing_time_min=processing_time_min,
            generated_by=payload.generated_by,
            approved_by=approved_by,
            approved_at=datetime.utcnow() if approved_by else None,
        )
        created_files: list[Path] = []
        try:
            db.add(packet)
            db.flush()

            for template in selected:
                form_missing = missing[template.form_id]
                file_path = self.write_pdf(dashboard["case_id"], packet.id, template, values, form_missing)
                created_files.append(file_path)
                db.add(
                    Phase4GeneratedForm(
                        packet_id=packet.id,
                        case_id=dashboard["case_id"],
                        form_id=template.form_id,
                        title=template.title,
                        purpose=template.purpose,
                        file_path=str(file_path),
                        field_values_json=values,
                        missing_fields_json=form_missing,
                        validation_status="ready" if not form_missing else "needs_review",
                    )
                )

            db.add(
                AuditLog(
                    case_id=dashboard["case_id"],
                    action="phase4_packet_generated",
                    actor=payload.generated_by,
                    details_json={
                        "packet_id": packet.id,
                        "selected_forms": packet.selected_forms_json,
                        "validation_status": status,
                        "form_accuracy_pct": accuracy,
                        "processing_time_min": processing_time_min,
                    },
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            for file_path in created_files:
                try:
                    file_path.unlink(missing_ok=True)
                except OSError:
                    # The database rollback is authoritative. A later integrity
                    # sweep can remove a file held open by the operating system.
                    pass
            raise
        db.refresh(packet)
        return packet

    def packets_for_case(self, db: Session, case_id: str) -> list[Phase4FormPacket]:
        dashboard = self.dashboard(db, case_id)
        return (
            db.query(Phase4FormPacket)
            .filter(Phase4FormPacket.case_id == dashboard["case_id"])
            .order_by(Phase4FormPacket.created_at.desc())
            .all()
        )

    def packet_response(self, db: Session, packet: Phase4FormPacket) -> dict[str, Any]:
        forms = (
            db.query(Phase4GeneratedForm)
            .filter(Phase4GeneratedForm.packet_id == packet.id)
            .order_by(Phase4GeneratedForm.id.asc())
            .all()
        )
        return {
            "id": packet.id,
            "case_id": packet.case_id,
            "source_phase3_action": packet.source_phase3_action,
            "selected_forms": packet.selected_forms_json,
            "generated_form_count": packet.generated_form_count,
            "missing_fields": packet.missing_fields_json,
            "validation_status": packet.validation_status,
            "form_accuracy_pct": packet.form_accuracy_pct,
            "processing_time_min": packet.processing_time_min,
            "generated_by": packet.generated_by,
            "approved_by": packet.approved_by,
            "created_at": packet.created_at,
            "approved_at": packet.approved_at,
            "generated_forms": [self.generated_form_response(form) for form in forms],
        }

    def generated_form_response(self, form: Phase4GeneratedForm) -> dict[str, Any]:
        return {
            "id": form.id,
            "packet_id": form.packet_id,
            "case_id": form.case_id,
            "form_id": form.form_id,
            "title": form.title,
            "purpose": form.purpose,
            "download_url": f"/api/phase4/generated-forms/{form.id}/download",
            "field_values": form.field_values_json,
            "missing_fields": form.missing_fields_json,
            "validation_status": form.validation_status,
            "created_at": form.created_at,
        }

    def generated_form_file(self, db: Session, generated_form_id: int) -> Phase4GeneratedForm:
        form = db.query(Phase4GeneratedForm).filter(Phase4GeneratedForm.id == generated_form_id).first()
        if not form:
            raise HTTPException(status_code=404, detail="Generated KP form was not found.")
        packet = (
            db.query(Phase4FormPacket)
            .filter(
                Phase4FormPacket.id == form.packet_id,
                Phase4FormPacket.case_id == form.case_id,
            )
            .first()
        )
        if packet is None:
            raise HTTPException(status_code=404, detail="Generated KP form is not linked to a valid packet.")
        if not Path(form.file_path).exists():
            raise HTTPException(status_code=404, detail="Generated KP form file was not found.")
        return form

    def write_pdf(
        self,
        case_id: str,
        packet_id: int,
        template: FormTemplate,
        values: dict[str, Any],
        missing: list[str],
    ) -> Path:
        file_path = self.output_dir / f"{case_id}_{packet_id}_{template.form_id}.pdf"
        # Preserve every original page for printing and manual completion.
        # Case data stays in the packet record, not in an appended PDF page.
        file_path.write_bytes(self.blank_template_file(template.form_id).read_bytes())
        return file_path

    def blank_template_file(self, form_id: str) -> Path:
        template = self.template_map().get(form_id)
        if template is None:
            raise HTTPException(status_code=404, detail="KP form template was not found.")
        source = self.official_template_path(template)
        if not source.is_file():
            raise HTTPException(status_code=404, detail=f"Original {template.title} PDF was not found.")
        return source

    def official_template_path(self, template: FormTemplate) -> Path:
        return self.template_dir / f"KP FORM {template.form_number}.pdf"

    def form_attachment_rows(
        self,
        case_id: str,
        template: FormTemplate,
        values: dict[str, Any],
        missing: list[str],
    ) -> list[str]:
        rows = [
            "JUSTICE-KP 2.0 Filled Data Attachment",
            template.title,
            template.purpose,
            f"Official Template: KP FORM {template.form_number}.pdf",
            "",
            f"Case ID: {case_id}",
            f"Barangay: {values.get('barangay_name', '')}",
            f"City/Municipality: {values.get('city_municipality', '')}",
            f"Case Year: {values.get('case_year', '')}",
            f"Dispute Category: {values.get('dispute_category', '')}",
            f"Parties: {values.get('parties', '')}",
            f"Final Recommended Action: {values.get('final_recommended_action', '')}",
            f"Hearing Schedule: {values.get('hearing_schedule', '')}",
            f"Referral Reason: {values.get('referral_reason', '')}",
            f"Mediation Terms: {values.get('mediation_terms', '')}",
            f"Official Decision: {values.get('official_decision', '')}",
            f"XAI Trace: {values.get('xai_trace_summary', '')}",
            "",
            f"Validation Status: {'Ready' if not missing else 'Needs Review'}",
            f"Missing Fields: {', '.join(missing) if missing else 'None'}",
            "",
            "Review and sign using the official barangay process before release.",
        ]
        return rows

    def append_attachment_page(self, source_pdf: bytes, rows: list[str]) -> bytes:
        text = source_pdf.decode("latin-1", errors="ignore")
        root_match = re.search(r"/Root\s+(\d+)\s+0\s+R", text)
        if not root_match:
            raise ValueError("PDF root object not found.")
        root_ref = int(root_match.group(1))

        root_body = self.object_body(text, root_ref)
        pages_match = re.search(r"/Pages\s+(\d+)\s+0\s+R", root_body)
        if not pages_match:
            raise ValueError("PDF pages object not found.")
        pages_ref = int(pages_match.group(1))

        pages_body = self.object_body(text, pages_ref)
        kids_match = re.search(r"/Kids\s*\[(.*?)\]", pages_body, flags=re.S)
        count_match = re.search(r"/Count\s+(\d+)", pages_body)
        if not kids_match or not count_match:
            raise ValueError("PDF pages object is not a simple page tree.")

        object_numbers = [int(value) for value in re.findall(r"(\d+)\s+0\s+obj", text)]
        if not object_numbers:
            raise ValueError("PDF objects not found.")
        next_object = max(object_numbers) + 1
        page_ref = next_object
        font_ref = next_object + 1
        content_ref = next_object + 2
        next_size = content_ref + 1

        content_stream = self.render_text_stream(rows)
        updated_kids = f"/Kids [{kids_match.group(1).strip()} {page_ref} 0 R]"
        updated_count = f"/Count {int(count_match.group(1)) + 1}"
        updated_pages_body = re.sub(r"/Kids\s*\[.*?\]", updated_kids, pages_body, flags=re.S)
        updated_pages_body = re.sub(r"/Count\s+\d+", updated_count, updated_pages_body, count=1)

        objects = [
            (pages_ref, updated_pages_body.encode("latin-1", errors="replace")),
            (
                page_ref,
                (
                    f"<< /Type /Page /Parent {pages_ref} 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 {font_ref} 0 R >> >> "
                    f"/Contents {content_ref} 0 R >>"
                ).encode("ascii"),
            ),
            (font_ref, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
            (
                content_ref,
                b"<< /Length "
                + str(len(content_stream)).encode("ascii")
                + b" >>\nstream\n"
                + content_stream
                + b"\nendstream",
            ),
        ]

        previous_xref = self.previous_xref_offset(text)
        output = bytearray(source_pdf.rstrip() + b"\n")
        offsets: list[tuple[int, int]] = []
        for object_id, body in objects:
            offsets.append((object_id, len(output)))
            output.extend(f"{object_id} 0 obj\n".encode("ascii"))
            output.extend(body)
            output.extend(b"\nendobj\n")

        xref_offset = len(output)
        output.extend(b"xref\n")
        for object_id, offset in offsets:
            output.extend(f"{object_id} 1\n".encode("ascii"))
            output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        output.extend(
            (
                f"trailer\n<< /Size {next_size} /Root {root_ref} 0 R /Prev {previous_xref} >>\n"
                f"startxref\n{xref_offset}\n%%EOF\n"
            ).encode("ascii")
        )
        return bytes(output)

    def render_pdf(self, rows: list[str]) -> bytes:
        lines = []
        for row in rows:
            lines.extend(self.wrap_line(row, 88) or [""])
        stream = self.render_text_stream(lines[:52])
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        ]
        pdf = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, obj in enumerate(objects, start=1):
            offsets.append(len(pdf))
            pdf.extend(f"{index} 0 obj\n".encode("ascii"))
            pdf.extend(obj)
            pdf.extend(b"\nendobj\n")
        xref = len(pdf)
        pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        pdf.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
        )
        return bytes(pdf)

    def render_text_stream(self, rows: list[str]) -> bytes:
        lines = []
        for row in rows:
            lines.extend(self.wrap_line(row, 88) or [""])
        content = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
        for line in lines[:52]:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content.append(f"({escaped}) Tj")
            content.append("T*")
        content.append("ET")
        return "\n".join(content).encode("latin-1", errors="replace")

    def object_body(self, pdf_text: str, object_id: int) -> str:
        match = re.search(rf"{object_id}\s+0\s+obj(.*?)endobj", pdf_text, flags=re.S)
        if not match:
            raise ValueError(f"PDF object {object_id} was not found.")
        return match.group(1).strip()

    def previous_xref_offset(self, pdf_text: str) -> int:
        start = pdf_text.rfind("startxref")
        if start < 0:
            raise ValueError("PDF startxref was not found.")
        match = re.search(r"startxref\s+(\d+)", pdf_text[start:])
        if not match:
            raise ValueError("PDF xref offset was not found.")
        return int(match.group(1))

    def wrap_line(self, text: str, width: int) -> list[str]:
        if len(text) <= width:
            return [text]
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) > width and current:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines
