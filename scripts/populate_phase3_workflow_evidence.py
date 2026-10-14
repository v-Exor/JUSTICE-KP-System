from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from database import SessionLocal  # noqa: E402
from models import (  # noqa: E402
    AuditLog,
    CaseAnalysis,
    CaseInformation,
    Evidence,
    Hearing,
    Phase3CaseRoute,
    Phase3OfficialDecision,
    Phase5ValidationCase,
    Referral,
    XAITrace,
)
from phase3_services import Phase3DashboardService  # noqa: E402


EVIDENCE_DIR = BACKEND / "evidence_uploads"
TARGET_BY_ROUTE = {
    "Proceed to Mediation": 8,
    "Manual Review": 6,
    "Refer to Court": 6,
    "Refer to MSWDO": 4,
    "Refer to PNP WCPD": 4,
}


def audit(db, case_id: str, action: str, details: dict[str, Any], actor: str = "validation_seed") -> None:
    db.add(
        AuditLog(
            case_id=case_id,
            action=action,
            actor=actor,
            details_json=details,
        )
    )


def latest_routes(db) -> list[tuple[Phase3CaseRoute, CaseInformation, CaseAnalysis]]:
    route_subquery = (
        db.query(Phase3CaseRoute.case_id, Phase3CaseRoute.recommended_route, Phase3CaseRoute.sensitive_category)
        .join(Phase5ValidationCase, Phase5ValidationCase.case_id == Phase3CaseRoute.case_id)
        .subquery()
    )
    rows: list[tuple[Phase3CaseRoute, CaseInformation, CaseAnalysis]] = []
    for route_name, limit in TARGET_BY_ROUTE.items():
        route_rows = (
            db.query(Phase3CaseRoute, CaseInformation, CaseAnalysis)
            .join(CaseInformation, CaseInformation.case_id == Phase3CaseRoute.case_id)
            .join(CaseAnalysis, CaseAnalysis.case_information_id == CaseInformation.id)
            .join(
                route_subquery,
                (route_subquery.c.case_id == Phase3CaseRoute.case_id)
                & (route_subquery.c.recommended_route == Phase3CaseRoute.recommended_route),
            )
            .filter(Phase3CaseRoute.recommended_route == route_name)
            .order_by(CaseInformation.dispute_category.asc(), Phase3CaseRoute.case_id.asc())
            .limit(limit)
            .all()
        )
        rows.extend(route_rows)
    return rows


def referral_payload(route: Phase3CaseRoute) -> dict[str, str]:
    mapping = {
        "Refer to PNP WCPD": (
            "VAWC",
            "PNP Women and Children Protection Desk",
            "Referral prepared because Phase 3 detected VAWC indicators.",
        ),
        "Refer to Court": (
            "Court",
            "Court or proper authority",
            "Referral prepared because Phase 3 marked the case outside KP or unsuitable for mediation.",
        ),
        "Refer to MSWDO": (
            "MSWDO",
            "Municipal Social Welfare and Development Office / PNP",
            "Referral prepared because Phase 3 detected child-abuse or minor-party indicators.",
        ),
        "Manual Review": (
            "Manual Review",
            "Barangay official manual review",
            "Manual review record prepared because the case requires official fact checking.",
        ),
    }
    referral_type, destination, fallback_reason = mapping.get(
        route.recommended_route,
        ("Manual Review", "Barangay official manual review", "Manual review required."),
    )
    return {
        "referral_type": referral_type,
        "destination": destination,
        "reason": route.reason or fallback_reason,
    }


def official_decision(route: Phase3CaseRoute) -> str:
    if route.recommended_route == "Proceed to Mediation":
        return "Proceed to Mediation"
    if route.recommended_route == "Manual Review":
        return "Manual Review Required"
    return route.recommended_route


def hearing_type_for(route: Phase3CaseRoute) -> str:
    if route.recommended_route == "Proceed to Mediation":
        return "mediation"
    if route.recommended_route == "Manual Review":
        return "initial"
    return "initial"


def evidence_note(case_info: CaseInformation, analysis: CaseAnalysis, route: Phase3CaseRoute) -> str:
    return (
        "Phase 3 validation workflow evidence note.\n"
        f"Case ID: {case_info.case_id}\n"
        f"Dispute category: {case_info.dispute_category or 'unspecified'}\n"
        f"Jurisdiction decision: {analysis.jurisdiction_decision}\n"
        f"Exclusion ground: {analysis.exclusion_ground}\n"
        f"Phase 3 route: {route.recommended_route}\n"
        f"Sensitive category: {route.sensitive_category}\n"
        f"Matched keywords: {', '.join(route.matched_keywords or []) or 'None'}\n"
        "Reviewer note: Representative documentation artifact used to test Phase 3 hearing, referral, "
        "evidence, and official-decision workflows for thesis validation.\n"
    )


def xai_reference(db, analysis: CaseAnalysis) -> list[str]:
    trace = db.query(XAITrace).filter(XAITrace.id == analysis.xai_trace_id).first()
    if not trace:
        return []
    if isinstance(trace.trace_json, list):
        return [str(item) for item in trace.trace_json]
    if trace.trace_text:
        return [line for line in trace.trace_text.splitlines() if line.strip()]
    return []


def ensure_evidence_file(case_id: str, note: str) -> Path:
    EVIDENCE_DIR.mkdir(exist_ok=True)
    file_path = EVIDENCE_DIR / f"{case_id}_phase3_validation_note.txt"
    if not file_path.exists():
        file_path.write_text(note, encoding="utf-8")
    return file_path


def populate() -> dict[str, Any]:
    db = SessionLocal()
    summary = {
        "selected_cases": 0,
        "hearings_created": 0,
        "referrals_created": 0,
        "evidence_created": 0,
        "official_decisions_created": 0,
        "selected_by_route": {},
    }
    try:
        selected = latest_routes(db)
        base_date = date.today() + timedelta(days=7)
        dashboard_service = Phase3DashboardService()

        for index, (route, case_info, analysis) in enumerate(selected):
            case_id = case_info.case_id
            summary["selected_cases"] += 1
            summary["selected_by_route"][route.recommended_route] = (
                summary["selected_by_route"].get(route.recommended_route, 0) + 1
            )

            note = evidence_note(case_info, analysis, route)
            evidence_file = ensure_evidence_file(case_id, note)
            if not db.query(Evidence).filter(Evidence.case_id == case_id).first():
                evidence = Evidence(
                    case_id=case_id,
                    file_name=evidence_file.name,
                    file_type="txt",
                    file_path=str(evidence_file),
                    ocr_text=note,
                    extracted_entities_json={
                        "source": "phase3_validation_seed",
                        "dispute_category": case_info.dispute_category,
                        "route": route.recommended_route,
                    },
                )
                db.add(evidence)
                db.flush()
                audit(db, case_id, "evidence_uploaded", {"evidence_id": evidence.id, "file_name": evidence.file_name})
                summary["evidence_created"] += 1

            if not db.query(Hearing).filter(Hearing.case_id == case_id).first():
                scheduled = base_date + timedelta(days=index)
                hearing = Hearing(
                    case_id=case_id,
                    hearing_type=hearing_type_for(route),
                    scheduled_date=scheduled.isoformat(),
                    scheduled_time="09:00",
                    location="Barangay Hall - Lupon Desk",
                    assigned_lupon_member=f"Lupon Reviewer {(index % 5) + 1}",
                    status="scheduled",
                    notes=(
                        "Representative Phase 3 workflow hearing record for validation. "
                        f"Route basis: {route.recommended_route}."
                    ),
                )
                db.add(hearing)
                db.flush()
                audit(db, case_id, "hearing_created", {"hearing_id": hearing.id, "type": hearing.hearing_type})
                summary["hearings_created"] += 1

            if route.recommended_route != "Proceed to Mediation":
                referral_info = referral_payload(route)
                existing_referral = (
                    db.query(Referral)
                    .filter(Referral.case_id == case_id, Referral.referral_type == referral_info["referral_type"])
                    .first()
                )
                if not existing_referral:
                    referral = Referral(
                        case_id=case_id,
                        referral_type=referral_info["referral_type"],
                        destination=referral_info["destination"],
                        reason=referral_info["reason"],
                        matched_keywords=route.matched_keywords or [],
                        xai_reference=xai_reference(db, analysis),
                        status="pending",
                    )
                    db.add(referral)
                    db.flush()
                    audit(
                        db,
                        case_id,
                        "referral_created",
                        {"referral_id": referral.id, "referral_type": referral.referral_type},
                    )
                    summary["referrals_created"] += 1

            if not db.query(Phase3OfficialDecision).filter(Phase3OfficialDecision.case_id == case_id).first():
                db.flush()
                dashboard = dashboard_service.build(db, case_id)
                decision = Phase3OfficialDecision(
                    case_id=case_id,
                    system_recommendation=dashboard["phase3"]["final_recommended_action"],
                    official_decision=official_decision(route),
                    official_notes=(
                        "Representative official decision record created for Phase 3 validation evidence. "
                        f"Decision follows route: {route.recommended_route}."
                    ),
                    approved_by="Validation Lupon Reviewer",
                    approved_at=datetime.utcnow(),
                )
                db.add(decision)
                db.flush()
                audit(
                    db,
                    case_id,
                    "official_decision_saved",
                    {"decision_id": decision.id, "official_decision": decision.official_decision},
                    actor="Validation Lupon Reviewer",
                )
                summary["official_decisions_created"] += 1

        db.commit()
        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    result = populate()
    for key, value in result.items():
        print(f"{key}: {value}")
