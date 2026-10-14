from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from keyword_detector import detect_sensitive_keywords
from legal_ner import extract_legal_entities
from models import (
    AuditLog,
    CaseAnalysis,
    CaseInformation,
    EmotionAnalysis,
    ExtractedEntities,
    MediationEligibility,
    MediationSuggestion,
    Phase3CaseRoute,
    Phase5ComplianceReview,
    Phase5GroundTruth,
    Phase5ValidationCase,
    Transcript,
    XAITrace,
)
from phase3_services import (
    EmotionAnalysisService,
    MediationEligibilityService,
    MediationSuggestionService,
    SensitiveCaseRoutingService,
    get_phase2_bundle,
    serialize_model,
)
from phase5_services import Phase5ValidationService
from rule_engine import evaluate_jurisdiction
from schemas import CaseInformationPayload
from xai_trace import build_xai_trace


DEFAULT_KP_CASES_WORKBOOK = Path(__file__).resolve().parent.parent / "docs" / "KP_Cases" / "JusticeKP_Cases.xlsx"
BALANCED_DATASET_SHEET = "Balanced_Dataset"

SHEET_NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


@dataclass
class ImportStats:
    workbook_path: str
    total_rows: int
    imported: int
    skipped_existing: int
    by_case_type: dict[str, int]
    by_source_type: dict[str, int]
    by_label: dict[str, int]
    sample_case_ids: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "workbook_path": self.workbook_path,
            "total_rows": self.total_rows,
            "imported": self.imported,
            "skipped_existing": self.skipped_existing,
            "by_case_type": self.by_case_type,
            "by_source_type": self.by_source_type,
            "by_label": self.by_label,
            "sample_case_ids": self.sample_case_ids,
        }


def workbook_rows(workbook_path: Path = DEFAULT_KP_CASES_WORKBOOK, sheet_name: str = BALANCED_DATASET_SHEET) -> list[dict[str, str]]:
    if not workbook_path.exists():
        raise FileNotFoundError(f"KP cases workbook was not found: {workbook_path}")

    with zipfile.ZipFile(workbook_path) as archive:
        shared_strings = read_shared_strings(archive)
        sheet_path = sheet_xml_path(archive, sheet_name)
        rows = read_sheet_rows(archive, sheet_path, shared_strings)

    if not rows:
        return []
    headers = [str(item).strip() for item in rows[0]]
    records: list[dict[str, str]] = []
    for row in rows[1:]:
        padded = row + [""] * max(0, len(headers) - len(row))
        records.append({header: str(padded[index] or "").strip() for index, header in enumerate(headers)})
    return [item for item in records if item.get("case_id")]


def read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall("a:si", SHEET_NS):
        strings.append("".join(text.text or "" for text in item.findall(".//a:t", SHEET_NS)))
    return strings


def sheet_xml_path(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    relmap = {rel.attrib["Id"]: rel.attrib["Target"].lstrip("/") for rel in rels}
    for sheet in workbook.find("a:sheets", SHEET_NS) or []:
        if sheet.attrib.get("name") == sheet_name:
            rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            return relmap[rel_id]
    raise ValueError(f"Workbook sheet was not found: {sheet_name}")


def read_sheet_rows(archive: zipfile.ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(archive.read(sheet_path))
    rows: list[list[str]] = []
    for row in root.findall(".//a:sheetData/a:row", SHEET_NS):
        cells = {
            column_number(cell.attrib["r"]): cell_value(cell, shared_strings)
            for cell in row.findall("a:c", SHEET_NS)
        }
        if cells:
            rows.append([cells.get(index, "") for index in range(1, max(cells) + 1)])
    return rows


def column_number(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        return 0
    number = 0
    for char in match.group(1):
        number = number * 26 + ord(char) - 64
    return number


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value = cell.find("a:v", SHEET_NS)
    if cell_type == "s" and value is not None:
        return shared_strings[int(value.text or 0)]
    if cell_type == "inlineStr":
        inline = cell.find("a:is", SHEET_NS)
        if inline is not None:
            return "".join(text.text or "" for text in inline.findall(".//a:t", SHEET_NS))
    return value.text if value is not None and value.text is not None else ""


def workbook_summary(workbook_path: Path = DEFAULT_KP_CASES_WORKBOOK) -> dict[str, Any]:
    rows = workbook_rows(workbook_path)
    return ImportStats(
        workbook_path=str(workbook_path),
        total_rows=len(rows),
        imported=0,
        skipped_existing=0,
        by_case_type=dict(Counter(row.get("case_type", "") for row in rows)),
        by_source_type=dict(Counter(row.get("source_type", "") for row in rows)),
        by_label=dict(Counter(row.get("justice_kp_label", "") for row in rows)),
        sample_case_ids=[row["case_id"] for row in rows[:5]],
    ).as_dict()


def import_kp_cases_workbook(
    db: Session,
    workbook_path: Path = DEFAULT_KP_CASES_WORKBOOK,
    limit: int | None = None,
    skip_existing: bool = True,
    process_phase3: bool = True,
) -> dict[str, Any]:
    rows = workbook_rows(workbook_path)
    selected_rows = rows[:limit] if limit is not None else rows
    imported = 0
    skipped = 0
    sample_ids: list[str] = []

    for row in selected_rows:
        case_id = row["case_id"]
        existing = db.query(Phase5ValidationCase).filter(Phase5ValidationCase.case_id == case_id).first()
        if existing and skip_existing:
            skipped += 1
            continue

        if existing:
            raise ValueError(f"Case already exists in Phase 5 validation dataset: {case_id}")

        create_case_records(db, row)
        if process_phase3:
            process_phase3_outputs(db, case_id)
        create_phase5_records(db, row)
        Phase5ValidationService().sync_research_dataset(db, db.query(Phase5ValidationCase).filter(Phase5ValidationCase.case_id == case_id).first())
        db.commit()
        imported += 1
        if len(sample_ids) < 5:
            sample_ids.append(case_id)

    return ImportStats(
        workbook_path=str(workbook_path),
        total_rows=len(rows),
        imported=imported,
        skipped_existing=skipped,
        by_case_type=dict(Counter(row.get("case_type", "") for row in rows)),
        by_source_type=dict(Counter(row.get("source_type", "") for row in rows)),
        by_label=dict(Counter(row.get("justice_kp_label", "") for row in rows)),
        sample_case_ids=sample_ids,
    ).as_dict()


def create_case_records(db: Session, row: dict[str, str]) -> CaseAnalysis:
    transcript = Transcript(
        content=transcript_text(row),
        segments_json=[
            {"speaker": "Speaker 1", "start": 0, "end": 8, "text": row.get("original_nature", "")},
            {"speaker": "Speaker 2", "start": 8, "end": 16, "text": row.get("conversation_status", "")},
        ],
    )
    db.add(transcript)
    db.flush()

    payload = case_information_payload(row)
    keyword_result = detect_sensitive_keywords(transcript.content)
    extracted_entities = extract_legal_entities(transcript.content)
    rule_result = evaluate_jurisdiction(payload, keyword_result)
    xai_trace = build_xai_trace(rule_result, keyword_result)

    case_info = CaseInformation(
        transcript_id=transcript.id,
        sensitivity_level="sensitive" if expected_sensitive_case(row) else "normal",
        recording_consent_confirmed=False,
        hearing_consent_confirmed=False,
        **payload.model_dump(),
    )
    extracted = ExtractedEntities(transcript_id=transcript.id, entities_json=extracted_entities)
    trace = XAITrace(trace_json=xai_trace, trace_text="\n".join(xai_trace))
    db.add_all([case_info, extracted, trace])
    db.flush()

    analysis = CaseAnalysis(
        transcript_id=transcript.id,
        case_information_id=case_info.id,
        extracted_entities_id=extracted.id,
        xai_trace_id=trace.id,
        detected_keywords_json=keyword_result,
        rule_results_json=rule_result["rule_results"],
        jurisdiction_decision=rule_result["jurisdiction_decision"],
        exclusion_ground=rule_result["exclusion_ground"],
        confidence_level=rule_result["confidence_level"],
        missing_fields_json=rule_result["missing_fields"],
        recommended_next_action=rule_result["recommended_next_action"],
    )
    db.add(analysis)
    db.add(
        AuditLog(
            case_id=row["case_id"],
            action="kp_cases_workbook_case_imported",
            actor="dataset_importer",
            details_json=source_notes(row),
        )
    )
    db.flush()
    return analysis


def process_phase3_outputs(db: Session, case_id: str) -> None:
    bundle = get_phase2_bundle(db, case_id)
    route_model = SensitiveCaseRoutingService().save(db, bundle)
    route_data = serialize_model(route_model)
    eligibility_model = MediationEligibilityService().save(db, bundle, route_data)
    eligibility_data = serialize_model(eligibility_model)
    MediationSuggestionService().save(db, bundle, eligibility_data)
    EmotionAnalysisService().save(db, bundle)


def create_phase5_records(db: Session, row: dict[str, str]) -> Phase5ValidationCase:
    analysis = (
        db.query(CaseAnalysis)
        .join(CaseInformation, CaseAnalysis.case_information_id == CaseInformation.id)
        .filter(CaseInformation.case_id == row["case_id"])
        .order_by(CaseAnalysis.id.desc())
        .first()
    )
    if not analysis:
        raise ValueError(f"Imported case analysis was not found: {row['case_id']}")

    validation = Phase5ValidationCase(
        case_id=row["case_id"],
        analysis_id=analysis.id,
        audio_id=f"dataset-{row['case_id']}",
        dataset_split="validation",
        speaker_count=2,
        speaker_gender_mix="unspecified",
        audio_quality="not_applicable",
        notes=notes_text(row),
    )
    db.add(validation)
    db.flush()

    db.add(Phase5GroundTruth(validation_case_id=validation.id, **ground_truth_values(row)))
    compliance_values = {
        "consent_confirmed": False,
        "transcript_anonymized": True,
        "official_decision_saved": False,
        "generated_forms_reviewed": False,
        "audit_trail_complete": True,
        "sensitive_case_referred": expected_sensitive_case(row),
        "reviewer_name": "JusticeKP workbook",
        "notes": "Imported from docs/KP_Cases/JusticeKP_Cases.xlsx.",
    }
    db.add(
        Phase5ComplianceReview(
            validation_case_id=validation.id,
            compliance_score=Phase5ValidationService().compliance_score(compliance_values),
            **compliance_values,
        )
    )
    db.flush()
    return validation


def case_information_payload(row: dict[str, str]) -> CaseInformationPayload:
    label = row.get("justice_kp_label", "")
    case_type = row.get("case_type", "").lower()
    amount = parse_money(row.get("amount_or_penalty_reference", "")) or parse_money(row.get("conversation_status", ""))
    is_fine_over = case_type == "fine-over-5000"
    is_penalty_over = case_type == "penalty-over-1-year"
    is_government = case_type == "government-party"
    is_filed = case_type == "already-filed-in-court"
    is_review = label == "NON_KP_REVIEW"
    is_vawc_child = label == "REFER_VAWC_CHILD_PROTECTION"

    return CaseInformationPayload(
        case_id=row["case_id"],
        barangay_name="Dataset Barangay",
        city_municipality="Dataset City/Municipality",
        case_year=year_from_date(row.get("date_filed", "")) or 2025,
        case_type=system_case_type(row),
        dispute_category=system_dispute_category(row),
        complainant_residency="same_barangay",
        respondent_residency="same_barangay",
        debt_amount_php=amount if system_dispute_category(row) == "debt" else None,
        maximum_penalty_years=2 if is_penalty_over else 0,
        fine_amount_php=max(amount or 0, 5001) if is_fine_over else 0,
        government_party_involved=is_government,
        already_filed_in_court=is_filed,
        has_vawc_or_child_abuse_indicators=is_vawc_child,
        public_officer_involved=is_government,
        public_officer_official_function=is_government,
        penalty_lookup_required=is_review,
        real_property_involved=case_type == "boundary/property",
        real_property_barangay="Dataset Barangay" if case_type == "boundary/property" else "",
        incident_venue_basis="real_property_location" if case_type == "boundary/property" else "same_barangay",
        accused_under_detention=False,
        minor_or_incompetent_party=is_vawc_child and contains_child_signal(row),
    )


def system_case_type(row: dict[str, str]) -> str:
    original = row.get("original_dispute_category", "").lower()
    if original == "civil":
        return "civil"
    if original == "criminal":
        return "criminal"
    if row.get("case_type", "").lower() == "government-party":
        return "administrative"
    return "other"


def system_dispute_category(row: dict[str, str]) -> str:
    case_type = row.get("case_type", "").lower()
    if case_type == "debt":
        return "debt"
    if case_type == "boundary/property":
        return "boundary"
    if case_type == "nuisance":
        return "nuisance"
    if case_type == "physical injury":
        return "physical_injury"
    if case_type == "threats":
        return "threat"
    if case_type == "fine-over-5000":
        return "debt"
    return "other"


def transcript_text(row: dict[str, str]) -> str:
    parts = [
        f"Speaker 1: Reklamo: {row.get('original_nature', '')}.",
        f"Speaker 2: Tugon o kalagayan: {row.get('conversation_status', '')}.",
        f"Speaker 1: Aksyon: {row.get('action_taken', '')}.",
    ]
    return "\n".join(part for part in parts if part.strip())


def ground_truth_values(row: dict[str, str]) -> dict[str, Any]:
    label = row.get("justice_kp_label", "")
    case_type = row.get("case_type", "").lower()
    if label == "KP_COVERED_AMICABLE":
        jurisdiction = "within_kp"
        exclusion = "none"
        covered = True
        sensitive = False
        referral = "Proceed to Mediation"
        mediation = True
    elif label == "REFER_VAWC_CHILD_PROTECTION":
        jurisdiction = "refer_to_pnp_wcpc_or_authority"
        exclusion = "vawc"
        covered = False
        sensitive = True
        referral = "Refer to MSWDO" if contains_child_signal(row) else "Refer to PNP WCPD"
        mediation = False
    elif label == "NON_KP_REVIEW":
        jurisdiction = "ambiguous_manual_review"
        exclusion = "penalty_lookup_required"
        covered = False
        sensitive = False
        referral = "Manual Review"
        mediation = False
    else:
        jurisdiction = "outside_kp"
        covered = False
        sensitive = False
        mediation = False
        referral = "Refer to Court"
        exclusion = {
            "government-party": "government_party",
            "already-filed-in-court": "already_filed_in_court",
            "penalty-over-1-year": "penalty_over_1_year",
            "fine-over-5000": "fine_over_5000",
        }.get(case_type, "outside_kp")

    return {
        "expected_covered_under_kp": covered,
        "expected_jurisdiction_decision": jurisdiction,
        "expected_exclusion_ground": exclusion,
        "expected_sensitive_case": sensitive,
        "expected_referral_route": referral,
        "expected_mediation_eligible": mediation,
        "expected_form_ids": [],
        "expected_keywords": [],
        "expected_speaker_count": 2,
        "reference_transcript": transcript_text(row),
        "reviewer_name": "JusticeKP workbook",
    }


def expected_sensitive_case(row: dict[str, str]) -> bool:
    return row.get("justice_kp_label") == "REFER_VAWC_CHILD_PROTECTION"


def contains_child_signal(row: dict[str, str]) -> bool:
    text = " ".join(
        [
            row.get("case_type", ""),
            row.get("original_nature", ""),
            row.get("label_reason", ""),
            row.get("evidence_of_type", ""),
        ]
    ).lower()
    return any(term in text for term in ["child", "bata", "minor", "menor", "molestiya", "abuse"])


def parse_money(value: str) -> float | None:
    match = re.search(r"(?:p|php|₱)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", value or "", flags=re.I)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def year_from_date(value: str) -> int | None:
    match = re.search(r"\b(20[0-9]{2})\b", value or "")
    return int(match.group(1)) if match else None


def notes_text(row: dict[str, str]) -> str:
    return (
        f"Source type: {row.get('source_type', '')}; "
        f"label: {row.get('justice_kp_label', '')}; "
        f"eligibility: {row.get('kp_eligibility', '')}; "
        f"reason: {row.get('label_reason', '')}"
    )


def source_notes(row: dict[str, str]) -> dict[str, Any]:
    return {
        "source_file": row.get("source_file", ""),
        "source_type": row.get("source_type", ""),
        "source_pdf_case_id": row.get("source_pdf_case_id", ""),
        "justice_kp_label": row.get("justice_kp_label", ""),
        "kp_eligibility": row.get("kp_eligibility", ""),
        "recommended_system_action": row.get("recommended_system_action", ""),
        "synthetic_generation_note": row.get("synthetic_generation_note", ""),
    }
