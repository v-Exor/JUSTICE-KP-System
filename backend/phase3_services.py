from __future__ import annotations

import re
import shutil
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from legal_ner import apply_authoritative_case_entities

from models import (
    AuditLog,
    CaseAnalysis,
    CaseInformation,
    EmotionAnalysis,
    Evidence,
    ExtractedEntities,
    Hearing,
    MediationEligibility,
    MediationSuggestion,
    Phase3CaseRoute,
    Phase3OfficialDecision,
    Referral,
    Transcript,
    XAITrace,
)


VAWC_KEYWORDS = [
    "sinaktan",
    "binugbog",
    "pinagbubugbog",
    "sinuntok",
    "sinipa",
    "sinampal",
    "kinurot",
    "tinadyakan",
    "hinampas",
    "pinukpok",
    "sinakal",
    "tinulak",
    "kinaladkad",
    "pinaso",
    "pinahirapan",
    "binato",
    "pinalo",
    "hinataw",
    "sugatan",
    "nasaktan",
    "nasugatan",
    "dumugo",
    "nabalian",
    "napuruhan",
    "binantaan",
    "banta",
    "pananakit",
    "abuso",
    "bata",
    "asawa",
    "kinakasama",
]
THREAT_KEYWORDS = [
    "papatayin",
    "patayin",
    "papatayin kita",
    "susugurin",
    "sasaktan",
    "babalikan",
    "pagbabantaan",
]
SERIOUS_INJURY_KEYWORDS = ["nabalian", "napuruhan", "dumugo", "sugatan", "nasugatan"]
CHILD_ABUSE_KEYWORDS = ["bata", "menor", "minor de edad", "child abuse", "abuso sa bata"]
REFERRAL_KEYWORDS = ["pulis", "pnp", "korte", "court", "mswdo", "wcpd", "referral", "refer"]

AGGRESSIVE_TERMS = ["papatayin", "sasaktan", "murahin", "sigaw", "sinaktan", "banta"]
ANGRY_TERMS = ["galit", "inis", "sumigaw", "sigaw", "murahin"]
SAD_TERMS = ["takot", "umiiyak", "iyak", "natatakot", "nalungkot"]
COOPERATIVE_TERMS = ["payag", "ayos", "hulugan", "settle", "kasunduan", "pasensya"]

VALID_HEARING_STATUSES = {"scheduled", "completed", "missed", "cancelled"}
VALID_HEARING_TYPES = {"initial", "mediation", "follow_up", "final"}


@dataclass
class Phase2Bundle:
    analysis: CaseAnalysis
    case_info: CaseInformation
    transcript: Transcript | None
    xai_trace: list[str]


def find_keywords(text: str, keywords: list[str]) -> list[str]:
    normalized = text.lower()
    found: list[str] = []
    for keyword in keywords:
        pattern = re.compile(rf"(?<!\w){re.escape(keyword.lower())}(?!\w)")
        if pattern.search(normalized):
            found.append(keyword)
    return found


def normalize_jurisdiction(decision: str) -> str:
    if decision == "within_kp":
        return "within_kp"
    if decision in {"outside_kp", "refer_to_pnp_wcpc_or_authority"}:
        return "outside_kp"
    return "ambiguous"


def json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    return value


def serialize_model(model: Any) -> dict[str, Any]:
    return {
        column.name: json_safe(getattr(model, column.name))
        for column in model.__table__.columns
    }


def serialize_evidence_record(model: Evidence) -> dict[str, Any]:
    return {
        "id": model.id,
        "case_id": model.case_id,
        "file_name": model.file_name,
        "file_type": model.file_type,
        "download_url": f"/api/phase3/evidence/{model.id}/download",
        "evidence_text": model.ocr_text,
        "extracted_entities_json": json_safe(model.extracted_entities_json),
        "uploaded_at": json_safe(model.uploaded_at),
    }


def append_audit_log(db: Session, case_id: str, action: str, details: dict[str, Any], actor: str = "system") -> None:
    db.add(AuditLog(case_id=case_id, action=action, actor=actor, details_json=json_safe(details)))


def get_phase2_bundle(db: Session, case_id: str) -> Phase2Bundle:
    query = db.query(CaseAnalysis)
    if case_id.isdigit():
        analysis = query.filter(CaseAnalysis.id == int(case_id)).first()
    else:
        analysis = (
            query.join(CaseInformation, CaseAnalysis.case_information_id == CaseInformation.id)
            .filter(CaseInformation.case_id == case_id)
            .order_by(CaseAnalysis.created_at.desc())
            .first()
        )
    if not analysis:
        raise HTTPException(status_code=404, detail="Saved Phase 2 case analysis was not found.")

    case_info = db.query(CaseInformation).filter(CaseInformation.id == analysis.case_information_id).first()
    if not case_info:
        raise HTTPException(status_code=404, detail="Saved case information was not found.")

    transcript = None
    if analysis.transcript_id is not None:
        transcript = db.query(Transcript).filter(Transcript.id == analysis.transcript_id).first()

    trace = db.query(XAITrace).filter(XAITrace.id == analysis.xai_trace_id).first()
    return Phase2Bundle(
        analysis=analysis,
        case_info=case_info,
        transcript=transcript,
        xai_trace=trace.trace_json if trace else [],
    )


def transcript_text(bundle: Phase2Bundle) -> str:
    return bundle.transcript.content if bundle.transcript else ""


def upsert_latest(db: Session, model: type[Any], case_id: str, values: dict[str, Any]) -> Any:
    existing = db.query(model).filter(model.case_id == case_id).order_by(model.id.desc()).first()
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        return existing
    item = model(case_id=case_id, **values)
    db.add(item)
    db.flush()
    return item


class SensitiveCaseRoutingService:
    def evaluate(self, bundle: Phase2Bundle) -> dict[str, Any]:
        text = transcript_text(bundle)
        phase2_keywords = bundle.analysis.detected_keywords_json or {}
        detected = set(phase2_keywords.get("detected_keywords") or [])
        matched_vawc = sorted(set(find_keywords(text, VAWC_KEYWORDS)) | detected.intersection(VAWC_KEYWORDS))
        matched_threats = find_keywords(text, THREAT_KEYWORDS)
        matched_child = find_keywords(text, CHILD_ABUSE_KEYWORDS)
        matched_injury = find_keywords(text, SERIOUS_INJURY_KEYWORDS)
        matched_referral = find_keywords(text, REFERRAL_KEYWORDS)
        intake_sensitive = bool(getattr(bundle.case_info, "has_vawc_or_child_abuse_indicators", False))
        intake_minor = bool(getattr(bundle.case_info, "minor_or_incompetent_party", False))
        if intake_sensitive and "intake_sensitive_indicator" not in matched_vawc:
            matched_vawc.append("intake_sensitive_indicator")
        if intake_minor and "minor_or_incompetent_party" not in matched_child:
            matched_child.append("minor_or_incompetent_party")
        max_penalty = bundle.case_info.maximum_penalty_years or 0
        normalized_decision = normalize_jurisdiction(bundle.analysis.jurisdiction_decision)

        category = "None"
        route = "Proceed to Mediation"
        reason = "No Phase 3 blocking rule fired."
        blocking = False
        is_sensitive = False
        matched_keywords: list[str] = []

        if matched_child and (matched_vawc or "abuso" in matched_child):
            category = "Child Abuse"
            route = "Refer to MSWDO"
            reason = "Child abuse indicator detected in the transcript."
            matched_keywords = sorted(set(matched_child + matched_vawc))
            blocking = True
            is_sensitive = True
        elif matched_vawc:
            category = "VAWC"
            route = "Refer to PNP WCPD"
            reason = "VAWC-related keyword detected in the transcript or Phase 2 keyword output."
            matched_keywords = matched_vawc
            blocking = True
            is_sensitive = True
        elif matched_threats:
            category = "Threat"
            route = "Refer to Court"
            reason = "Threat-related keyword detected; barangay mediation should not proceed automatically."
            matched_keywords = matched_threats
            blocking = True
            is_sensitive = True
        elif matched_injury:
            category = "Serious Physical Injury"
            route = "Refer to Court"
            reason = "Serious physical injury indicator detected."
            matched_keywords = matched_injury
            blocking = True
            is_sensitive = True
        elif max_penalty > 1:
            category = "Outside KP"
            route = "Refer to Court"
            reason = "Maximum imposable penalty is greater than 1 year."
            blocking = True
        elif normalized_decision == "outside_kp":
            category = "Outside KP"
            route = "Refer to Court"
            reason = "Phase 2 jurisdiction result is outside KP."
            matched_keywords = matched_referral
            blocking = True
        elif normalized_decision == "ambiguous":
            route = "Manual Review"
            reason = "Phase 2 jurisdiction result is ambiguous and requires official review."
            blocking = True
        elif matched_referral:
            route = "Manual Review"
            reason = "Referral-related keyword detected."
            matched_keywords = matched_referral
            blocking = True

        confidence = "high" if is_sensitive or max_penalty > 1 or normalized_decision == "outside_kp" else "medium"
        if route == "Manual Review":
            confidence = "low"

        return {
            "case_id": bundle.case_info.case_id,
            "is_sensitive": is_sensitive,
            "sensitive_category": category,
            "recommended_route": route,
            "reason": reason,
            "matched_keywords": matched_keywords,
            "confidence_level": confidence,
            "blocking_mediation": blocking,
        }

    def save(self, db: Session, bundle: Phase2Bundle) -> Phase3CaseRoute:
        result = self.evaluate(bundle)
        route = upsert_latest(
            db,
            Phase3CaseRoute,
            bundle.case_info.case_id,
            {key: value for key, value in result.items() if key != "case_id"},
        )
        append_audit_log(db, bundle.case_info.case_id, "sensitive_routing_evaluated", result)
        db.commit()
        db.refresh(route)
        return route


class ReferralService:
    def create_from_route(self, db: Session, bundle: Phase2Bundle, route: dict[str, Any]) -> Referral | None:
        if route["recommended_route"] == "Proceed to Mediation":
            return None

        referral_type = {
            "Refer to PNP WCPD": "VAWC",
            "Refer to Court": "Court",
            "Refer to MSWDO": "MSWDO",
            "Manual Review": "Manual Review",
        }.get(route["recommended_route"], "Manual Review")
        destination = {
            "VAWC": "PNP Women and Children Protection Desk",
            "Court": "Court or proper authority",
            "MSWDO": "MSWDO/PNP",
            "Manual Review": "Barangay official manual review",
        }[referral_type]

        existing = (
            db.query(Referral)
            .filter(Referral.case_id == bundle.case_info.case_id, Referral.referral_type == referral_type)
            .order_by(Referral.id.desc())
            .first()
        )
        if existing and existing.status != "cancelled":
            return existing

        referral = Referral(
            case_id=bundle.case_info.case_id,
            referral_type=referral_type,
            destination=destination,
            reason=route["reason"],
            matched_keywords=route["matched_keywords"],
            xai_reference=bundle.xai_trace,
            status="pending",
        )
        db.add(referral)
        db.flush()
        append_audit_log(db, bundle.case_info.case_id, "referral_created", serialize_model(referral))
        return referral


class MediationEligibilityService:
    def evaluate(self, bundle: Phase2Bundle, route: dict[str, Any]) -> dict[str, Any]:
        decision = normalize_jurisdiction(bundle.analysis.jurisdiction_decision)
        if decision == "ambiguous":
            return {
                "case_id": bundle.case_info.case_id,
                "eligible_for_mediation": False,
                "reason": "Phase 2 jurisdiction is ambiguous.",
                "required_action": "Manual Review",
            }
        if decision == "outside_kp":
            return {
                "case_id": bundle.case_info.case_id,
                "eligible_for_mediation": False,
                "reason": "Case is outside KP jurisdiction.",
                "required_action": "Refer Case",
            }
        if route["blocking_mediation"]:
            return {
                "case_id": bundle.case_info.case_id,
                "eligible_for_mediation": False,
                "reason": route["reason"],
                "required_action": "Refer Case" if route["recommended_route"] != "Manual Review" else "Manual Review",
            }
        return {
            "case_id": bundle.case_info.case_id,
            "eligible_for_mediation": True,
            "reason": "Case is within KP jurisdiction and no sensitive-case blocking rule fired.",
            "required_action": "Generate Mediation Options",
        }

    def save(self, db: Session, bundle: Phase2Bundle, route: dict[str, Any]) -> MediationEligibility:
        result = self.evaluate(bundle, route)
        eligibility = upsert_latest(
            db,
            MediationEligibility,
            bundle.case_info.case_id,
            {key: value for key, value in result.items() if key != "case_id"},
        )
        append_audit_log(db, bundle.case_info.case_id, "mediation_eligibility_evaluated", result)
        db.commit()
        db.refresh(eligibility)
        return eligibility


class MediationSuggestionService:
    SUGGESTIONS = {
        "debt": [
            ("Installment payment plan", "Create a payment schedule divided into manageable dates.", ["amount per installment", "due dates", "missed-payment consequence"]),
            ("Partial immediate payment plus deadline", "Record an initial payment and a clear deadline for the balance.", ["initial payment", "final due date", "receipt acknowledgement"]),
            ("Written settlement agreement with witness", "Prepare a written agreement signed before barangay witnesses.", ["settlement amount", "witness names", "signature date"]),
        ],
        "boundary": [
            ("Joint boundary inspection", "Schedule a barangay-assisted inspection of the disputed boundary.", ["inspection date", "attendees", "sketch or photos"]),
            ("Barangay-assisted agreement", "Document mutually accepted boundary use terms.", ["agreed markers", "maintenance duty", "follow-up date"]),
            ("Written undertaking to respect boundaries", "Record a commitment not to disturb agreed boundary lines.", ["boundary markers", "non-interference terms", "witnesses"]),
        ],
        "family_dispute": [
            ("Cooling-off agreement", "Set a short cooling-off period before further dialogue.", ["duration", "communication limits", "support person"]),
            ("Family dialogue with Lupon guidance", "Hold a guided dialogue focused on specific conduct.", ["dialogue date", "ground rules", "follow-up"]),
            ("Behavioral commitment agreement", "Document commitments each party accepts.", ["commitments", "review date", "consequence for breach"]),
        ],
        "nuisance": [
            ("Time restriction agreement", "Set hours when the nuisance activity must stop.", ["restricted hours", "allowed exceptions", "monitoring period"]),
            ("Written neighbor conduct agreement", "Record expectations for neighbor conduct.", ["specific conduct", "reporting path", "review date"]),
            ("Monitoring period with follow-up hearing", "Set a monitoring window before a follow-up hearing.", ["monitoring dates", "barangay contact", "follow-up schedule"]),
        ],
        "property_damage": [
            ("Repair agreement", "Set repair work and completion deadline.", ["repair scope", "deadline", "proof of repair"]),
            ("Compensation agreement", "Agree on payment for verified damage.", ["amount", "payment date", "proof required"]),
            ("Replacement or service equivalent", "Allow replacement or equivalent service where appropriate.", ["replacement item", "service equivalent", "acceptance date"]),
        ],
        "physical_injury": [
            ("Apology and non-retaliation agreement", "Record apology and mutual commitment to avoid retaliation.", ["apology terms", "non-retaliation clause", "follow-up"]),
            ("Medical cost reimbursement", "Document verified minor medical costs for reimbursement.", ["verified amount", "payment deadline", "receipts"]),
            ("Peace bond or behavior commitment", "Set conduct commitments for peaceful interactions.", ["specific conduct", "duration", "monitoring"]),
        ],
        "online_defamation": [
            ("Remove or correct online content", "Identify the disputed content and record the agreed removal or correction.", ["content or post", "removal deadline", "correction statement"]),
            ("Written non-republication undertaking", "Record a commitment not to repost or repeat the disputed statement.", ["covered statements", "platforms", "compliance period"]),
            ("Clarification and monitoring agreement", "Document an agreed clarification and a short monitoring period.", ["clarification text", "publication method", "review date"]),
        ],
        "neighbor_altercation": [
            ("Mutual non-aggression agreement", "Set clear conduct boundaries for future neighbor interactions.", ["prohibited conduct", "contact limits", "monitoring period"]),
            ("Neighbor conduct agreement", "Document practical rules for peaceful day-to-day contact.", ["shared-area rules", "communication method", "barangay contact"]),
            ("Follow-up conference", "Schedule a review to confirm that both parties are complying.", ["follow-up date", "compliance concerns", "assigned official"]),
        ],
        "harassment_unjust_vexation": [
            ("No-contact or limited-contact agreement", "Set reasonable limits on unwanted contact between the parties.", ["contact limits", "allowed exceptions", "duration"]),
            ("Behavioral undertaking", "List the specific conduct that must stop and how concerns will be reported.", ["prohibited conduct", "reporting path", "review date"]),
            ("Barangay monitoring period", "Set a short period for monitoring compliance with the agreement.", ["monitoring dates", "barangay contact", "follow-up schedule"]),
        ],
        "business_defamation": [
            ("Correction or clarification agreement", "Record an agreed correction of the disputed business statement.", ["disputed statement", "correction wording", "delivery method"]),
            ("Non-repetition undertaking", "Document a commitment not to repeat unsupported statements about the business.", ["covered statements", "audience or channels", "compliance period"]),
            ("Documented business communication protocol", "Set a direct process for raising future business concerns.", ["contact persons", "communication channel", "response period"]),
        ],
        "other": [
            ("Guided dialogue", "Clarify each party's requested outcome before drafting terms.", ["issues list", "proposed terms", "review date"]),
            ("Written undertaking", "Record a focused undertaking tied to the complaint.", ["undertaking", "deadline", "witnesses"]),
            ("Follow-up conference", "Schedule a follow-up to confirm compliance.", ["follow-up date", "documents needed", "assigned official"]),
        ],
    }

    def generate(self, bundle: Phase2Bundle, eligibility: dict[str, Any]) -> dict[str, Any]:
        category = bundle.case_info.dispute_category or "other"
        if not eligibility["eligible_for_mediation"]:
            return {
                "case_id": bundle.case_info.case_id,
                "dispute_category": category,
                "suggestions": [],
                "xai_explanation": [
                    "No mediation suggestions generated because the case is not eligible for mediation.",
                    f"Required action = {eligibility['required_action']}",
                ],
            }

        templates = self.SUGGESTIONS.get(category, self.SUGGESTIONS["other"])
        suggestions = [
            {
                "title": title,
                "description": description,
                "recommended_terms": terms,
                "why_suggested": f"Suggestion generated because dispute_category = {category}.",
                "risk_level": "medium" if category == "physical_injury" else "low",
            }
            for title, description, terms in templates
        ]
        return {
            "case_id": bundle.case_info.case_id,
            "dispute_category": category,
            "suggestions": suggestions,
            "xai_explanation": [
                f"Suggestion generated because dispute_category = {category}",
                "Case is within KP jurisdiction",
                "No sensitive-case blocking rule fired",
            ],
        }

    def save(self, db: Session, bundle: Phase2Bundle, eligibility: dict[str, Any]) -> MediationSuggestion:
        result = self.generate(bundle, eligibility)
        suggestion = upsert_latest(
            db,
            MediationSuggestion,
            bundle.case_info.case_id,
            {
                "dispute_category": result["dispute_category"],
                "suggestions_json": result["suggestions"],
                "xai_explanation_json": result["xai_explanation"],
            },
        )
        append_audit_log(db, bundle.case_info.case_id, "mediation_suggestions_generated", result)
        db.commit()
        db.refresh(suggestion)
        return suggestion


class HearingService:
    def validate(self, db: Session, case_id: str, scheduled_date: str, status: str, hearing_type: str) -> None:
        get_phase2_bundle(db, case_id)
        if status not in VALID_HEARING_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid hearing status.")
        if hearing_type not in VALID_HEARING_TYPES:
            raise HTTPException(status_code=400, detail="Invalid hearing type.")
        try:
            parsed_date = date.fromisoformat(scheduled_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="scheduled_date must use YYYY-MM-DD format.") from exc
        if parsed_date < date.today():
            raise HTTPException(status_code=400, detail="scheduled_date cannot be in the past.")


class EvidenceFileService:
    def __init__(self, upload_dir: Path):
        self.upload_dir = upload_dir
        self.upload_dir.mkdir(exist_ok=True)

    def save_upload(self, case_id: str, file: UploadFile, manual_text: str | None = None) -> dict[str, Any]:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No evidence file was uploaded.")
        extension = Path(file.filename).suffix.lower()
        if extension not in {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".txt", ".doc", ".docx"}:
            raise HTTPException(status_code=400, detail="Unsupported evidence file type.")
        saved_path = self.upload_dir / f"{case_id}_{datetime.utcnow():%Y%m%d%H%M%S}_{uuid4().hex}{extension}"
        with saved_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "100"))
        if saved_path.stat().st_size > max_upload_mb * 1024 * 1024:
            saved_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Evidence file exceeds {max_upload_mb} MB limit.")

        return {
            "file_name": file.filename,
            "file_type": extension.lstrip(".") or "unknown",
            "file_path": str(saved_path),
            "evidence_text": (manual_text or "").strip(),
            "extracted_entities": {},
        }


class EmotionAnalysisService:
    def analyze(self, bundle: Phase2Bundle) -> dict[str, Any]:
        text = transcript_text(bundle)
        detected = (
            find_keywords(text, AGGRESSIVE_TERMS)
            + find_keywords(text, ANGRY_TERMS)
            + find_keywords(text, SAD_TERMS)
            + find_keywords(text, COOPERATIVE_TERMS)
        )
        aggressive = find_keywords(text, AGGRESSIVE_TERMS)
        angry = find_keywords(text, ANGRY_TERMS)
        sad = find_keywords(text, SAD_TERMS)
        cooperative = find_keywords(text, COOPERATIVE_TERMS)
        if aggressive:
            label = "aggressive"
            advice = "Recommend separate seating and close Lupon supervision."
            score = min(1.0, 0.65 + len(aggressive) * 0.08)
        elif angry:
            label = "angry"
            advice = "Recommend calm facilitation, turn-taking, and a cooling-off pause if needed."
            score = min(1.0, 0.45 + len(angry) * 0.08)
        elif sad:
            label = "sad"
            advice = "Recommend careful questioning and a support person if appropriate."
            score = min(1.0, 0.35 + len(sad) * 0.07)
        elif cooperative:
            label = "cooperative"
            advice = "Proceed with normal mediation."
            score = max(0.1, 0.25 - len(cooperative) * 0.03)
        else:
            label = "neutral"
            advice = "Proceed with standard procedure."
            score = 0.2
        return {
            "case_id": bundle.case_info.case_id,
            "emotion_label": label,
            "tension_score": round(score, 2),
            "detected_terms": sorted(set(detected)),
            "mediation_advice": advice,
        }

    def save(self, db: Session, bundle: Phase2Bundle) -> EmotionAnalysis:
        result = self.analyze(bundle)
        emotion = upsert_latest(
            db,
            EmotionAnalysis,
            bundle.case_info.case_id,
            {key: value for key, value in result.items() if key != "case_id"},
        )
        append_audit_log(db, bundle.case_info.case_id, "emotion_analysis_completed", result)
        db.commit()
        db.refresh(emotion)
        return emotion


class Phase3DashboardService:
    def final_action(
        self,
        route: dict[str, Any] | None,
        eligibility: dict[str, Any] | None,
        hearings: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> str:
        if route and route["recommended_route"] != "Proceed to Mediation":
            return route["recommended_route"]
        if eligibility and eligibility["required_action"] == "Manual Review":
            return "Manual Review Required"
        if hearings and all(item["status"] in {"completed", "cancelled", "missed"} for item in hearings):
            return "Schedule Hearing"
        if eligibility and eligibility["eligible_for_mediation"]:
            return "Proceed to Mediation" if evidence else "Awaiting Evidence"
        return "Manual Review Required"

    def build(self, db: Session, case_id: str) -> dict[str, Any]:
        bundle = get_phase2_bundle(db, case_id)
        canonical_case_id = bundle.case_info.case_id
        route = db.query(Phase3CaseRoute).filter(Phase3CaseRoute.case_id == canonical_case_id).order_by(Phase3CaseRoute.id.desc()).first()
        eligibility = db.query(MediationEligibility).filter(MediationEligibility.case_id == canonical_case_id).order_by(MediationEligibility.id.desc()).first()
        suggestions = db.query(MediationSuggestion).filter(MediationSuggestion.case_id == canonical_case_id).order_by(MediationSuggestion.id.desc()).first()
        referrals = db.query(Referral).filter(Referral.case_id == canonical_case_id).order_by(Referral.created_at.desc()).all()
        hearings = db.query(Hearing).filter(Hearing.case_id == canonical_case_id).order_by(Hearing.scheduled_date.asc(), Hearing.scheduled_time.asc()).all()
        evidence = db.query(Evidence).filter(Evidence.case_id == canonical_case_id).order_by(Evidence.uploaded_at.desc()).all()
        emotion = db.query(EmotionAnalysis).filter(EmotionAnalysis.case_id == canonical_case_id).order_by(EmotionAnalysis.id.desc()).first()
        official = db.query(Phase3OfficialDecision).filter(Phase3OfficialDecision.case_id == canonical_case_id).order_by(Phase3OfficialDecision.id.desc()).first()
        entities = db.query(ExtractedEntities).filter(ExtractedEntities.id == bundle.analysis.extracted_entities_id).first()

        route_data = serialize_model(route) if route else None
        eligibility_data = serialize_model(eligibility) if eligibility else None
        hearing_data = [serialize_model(item) for item in hearings]
        evidence_data = [serialize_evidence_record(item) for item in evidence]
        case_info = serialize_model(bundle.case_info)
        case_info.pop("id", None)
        case_info.pop("created_at", None)
        extracted_entities = apply_authoritative_case_entities(
            entities.entities_json if entities else {},
            bundle.case_info.barangay_name,
            bundle.case_info.created_at,
        )
        return {
            "case_id": canonical_case_id,
            "phase1": {
                "transcript_id": bundle.analysis.transcript_id,
                "transcript": bundle.transcript.content if bundle.transcript else "",
                "segments": bundle.transcript.segments_json if bundle.transcript else [],
            },
            "phase2": {
                "analysis_id": bundle.analysis.id,
                "case_information": case_info,
                "extracted_entities": extracted_entities,
                "detected_keywords": bundle.analysis.detected_keywords_json,
                "jurisdiction_decision": bundle.analysis.jurisdiction_decision,
                "normalized_jurisdiction_decision": normalize_jurisdiction(bundle.analysis.jurisdiction_decision),
                "exclusion_ground": bundle.analysis.exclusion_ground,
                "confidence_level": bundle.analysis.confidence_level,
                "missing_fields": bundle.analysis.missing_fields_json,
                "recommended_next_action": bundle.analysis.recommended_next_action,
                "xai_trace": bundle.xai_trace,
                "rule_results": bundle.analysis.rule_results_json,
            },
            "phase3": {
                "sensitive_routing": route_data,
                "mediation_eligibility": eligibility_data,
                "mediation_suggestions": serialize_model(suggestions) if suggestions else None,
                "referrals": [serialize_model(item) for item in referrals],
                "hearings": hearing_data,
                "evidence": evidence_data,
                "emotion_analysis": serialize_model(emotion) if emotion else None,
                "official_decision": serialize_model(official) if official else None,
                "final_recommended_action": self.final_action(route_data, eligibility_data, hearing_data, evidence_data),
                "disclaimer": "This system provides decision-support only. Barangay officials remain the final decision-makers.",
            },
        }
