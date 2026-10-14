from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from database import SessionLocal  # noqa: E402
from models import Phase4FormPacket, Phase5EvaluationResult, Phase5ValidationCase  # noqa: E402
from phase4_schemas import Phase4GeneratePacketRequest  # noqa: E402
from phase4_services import Phase4FormService  # noqa: E402
from phase5_services import Phase5ValidationService  # noqa: E402


GENERATED_FORMS_DIR = BACKEND / "generated_forms"


def default_overrides(case_id: str) -> dict[str, Any]:
    return {
        "parties": "Complainant and respondent listed in the barangay case intake record",
        "transcript_summary": "Transcript or intake summary is available in the saved validation case record.",
        "hearing_schedule": "Validation review schedule to be finalized by the Lupon before official release.",
        "mediation_terms": "Terms to be reviewed and finalized by the Lupon before release.",
        "referral_reason": "Referral or manual review reason is documented in the Phase 3 routing record.",
        "official_decision": "Official decision recorded for Phase 4 validation review.",
        "xai_trace_summary": f"Rule-trace summary available in JUSTICE-KP case record {case_id}.",
    }


def generate_packets(limit: int | None = None, reevaluate: bool = True) -> dict[str, Any]:
    db = SessionLocal()
    service = Phase4FormService(GENERATED_FORMS_DIR)
    validation_service = Phase5ValidationService()
    summary = {
        "validation_cases": 0,
        "already_had_packets": 0,
        "already_ready_packets": 0,
        "correction_packets_created": 0,
        "packets_created": 0,
        "forms_created": 0,
        "evaluations_refreshed": 0,
        "errors": [],
    }
    try:
        query = db.query(Phase5ValidationCase).order_by(Phase5ValidationCase.case_id.asc())
        if limit is not None:
            query = query.limit(limit)
        cases = query.all()
        summary["validation_cases"] = len(cases)

        for validation in cases:
            existing = (
                db.query(Phase4FormPacket)
                .filter(Phase4FormPacket.case_id == validation.case_id)
                .order_by(Phase4FormPacket.created_at.desc(), Phase4FormPacket.id.desc())
                .first()
            )
            if existing:
                summary["already_had_packets"] += 1
                if existing.validation_status == "ready":
                    summary["already_ready_packets"] += 1
                    packet_created = False
                else:
                    payload = Phase4GeneratePacketRequest(
                        generated_by="Validation Lupon Reviewer",
                        approved_by="Validation Lupon Reviewer",
                        field_overrides=default_overrides(validation.case_id),
                    )
                    try:
                        packet = service.generate_packet(db, validation.case_id, payload)
                        packet_created = True
                        summary["correction_packets_created"] += 1
                        summary["forms_created"] += packet.generated_form_count
                    except Exception as exc:
                        db.rollback()
                        summary["errors"].append({"case_id": validation.case_id, "error": str(exc)})
                        continue
            else:
                payload = Phase4GeneratePacketRequest(
                    generated_by="Validation Lupon Reviewer",
                    approved_by="Validation Lupon Reviewer",
                    field_overrides=default_overrides(validation.case_id),
                )
                try:
                    packet = service.generate_packet(db, validation.case_id, payload)
                    packet_created = True
                    summary["packets_created"] += 1
                    summary["forms_created"] += packet.generated_form_count
                except Exception as exc:  # keep moving so one malformed case does not stop the batch
                    db.rollback()
                    summary["errors"].append({"case_id": validation.case_id, "error": str(exc)})
                    continue

            latest_result = (
                db.query(Phase5EvaluationResult)
                .filter(Phase5EvaluationResult.validation_case_id == validation.id)
                .order_by(Phase5EvaluationResult.evaluated_at.desc(), Phase5EvaluationResult.id.desc())
                .first()
            )
            latest_has_phase4 = bool(latest_result and latest_result.form_accuracy_pct is not None)
            if reevaluate and (packet_created or not latest_has_phase4):
                try:
                    validation_service.evaluate_case(db, validation.case_id)
                    summary["evaluations_refreshed"] += 1
                except Exception as exc:
                    db.rollback()
                    summary["errors"].append({"case_id": validation.case_id, "evaluation_error": str(exc)})

        summary["evaluation_results_total"] = db.query(Phase5EvaluationResult).count()
        return summary
    finally:
        db.close()


if __name__ == "__main__":
    result = generate_packets()
    for key, value in result.items():
        print(f"{key}: {value}")
