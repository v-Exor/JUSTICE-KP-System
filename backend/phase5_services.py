from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from io import StringIO
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import (
    AuditLog,
    CaseAnalysis,
    CaseInformation,
    KPResearchDataset,
    Phase4FormPacket,
    Phase3CaseRoute,
    Phase3OfficialDecision,
    Phase5ComplianceReview,
    Phase5EvaluationResult,
    Phase5ExperimentRun,
    Phase5GroundTruth,
    Phase5ValidationCase,
    Referral,
    Transcript,
    WorkflowDraft,
)
from phase3_services import Phase3DashboardService, get_phase2_bundle, normalize_jurisdiction, serialize_model
from phase5_schemas import (
    Phase5ComplianceReviewRequest,
    Phase5ExperimentRunRequest,
    Phase5GroundTruthRequest,
    Phase5ImportCaseRequest,
)


@dataclass
class Phase5SystemSnapshot:
    case_id: str
    case_information: dict[str, Any]
    jurisdiction_decision: str
    normalized_jurisdiction_decision: str
    exclusion_ground: str
    sensitive_case: bool
    referral_route: str
    mediation_eligible: bool | None
    generated_form_ids: list[str]
    recommended_form_ids: list[str]
    detected_keywords: list[str]
    detected_speaker_count: int | None
    xai_trace_length: int
    form_accuracy_pct: float | None
    phase4_processing_time_min: float | None
    final_recommended_action: str
    compliance_signals: dict[str, bool]


def serialize_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def serialize_record(model: Any) -> dict[str, Any]:
    return {
        column.name: serialize_value(getattr(model, column.name))
        for column in model.__table__.columns
    }


def latest_for_case(db: Session, model: type[Any], case_id: str) -> Any | None:
    return db.query(model).filter(model.case_id == case_id).order_by(model.id.desc()).first()


def percent(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round((numerator / denominator) * 100, 2)


def average(values: list[float | None]) -> float | None:
    actual = [value for value in values if value is not None]
    if not actual:
        return None
    return round(sum(actual) / len(actual), 2)


def bool_accuracy(values: list[bool | None]) -> float | None:
    actual = [value for value in values if value is not None]
    if not actual:
        return None
    return percent(sum(1 for value in actual if value), len(actual))


class Phase5ValidationService:
    def finalized_workflow_candidates(
        self,
        db: Session,
        *,
        include_ineligible: bool = False,
    ) -> list[dict[str, Any]]:
        """List finalized workflow drafts that can be imported into Phase 5.

        ``include_ineligible`` is intended for diagnostics and tests. The normal API
        contract only exposes records that pass every readiness check.
        """
        drafts = (
            db.query(WorkflowDraft)
            .filter(WorkflowDraft.status.in_(["completed", "cancelled"]))
            .order_by(WorkflowDraft.updated_at.desc(), WorkflowDraft.id.desc())
            .all()
        )
        candidates = [self.workflow_import_readiness(db, draft) for draft in drafts]
        if include_ineligible:
            return candidates
        return [candidate for candidate in candidates if candidate["eligible"]]

    def workflow_import_readiness(self, db: Session, draft: WorkflowDraft) -> dict[str, Any]:
        payload = dict(draft.payload_json or {})
        case_information = payload.get("caseInformation")
        if not isinstance(case_information, dict):
            case_information = {}
        case_id = str(draft.case_id or case_information.get("case_id") or "").strip()
        outcome = str(payload.get("outcome") or "").strip()
        finalized_at_value = payload.get("finalizedAt")
        finalized_at = str(finalized_at_value).strip() if finalized_at_value else None
        analysis_id = draft.case_analysis_id
        reasons: list[str] = []

        if draft.status != "completed":
            reasons.append("Workflow status is not completed.")
        if payload.get("completed") is not True:
            reasons.append("Workflow payload is not marked completed.")
        if not finalized_at:
            reasons.append("Workflow has no finalized timestamp.")
        if not outcome:
            reasons.append("Workflow has no final outcome.")
        if not case_id:
            reasons.append("Workflow has no case ID.")

        analysis = None
        if not isinstance(analysis_id, int) or isinstance(analysis_id, bool):
            reasons.append("Workflow has no linked Phase 2 analysis.")
        else:
            analysis = db.query(CaseAnalysis).filter(CaseAnalysis.id == analysis_id).first()
            if analysis is None:
                reasons.append("The linked Phase 2 analysis no longer exists.")

        if analysis is not None and case_id:
            analysis_case = (
                db.query(CaseInformation)
                .filter(CaseInformation.id == analysis.case_information_id)
                .first()
            )
            if analysis_case is None or analysis_case.case_id != case_id:
                reasons.append("The linked Phase 2 analysis belongs to a different case.")
            latest_analysis = (
                db.query(CaseAnalysis)
                .join(CaseInformation, CaseInformation.id == CaseAnalysis.case_information_id)
                .filter(CaseInformation.case_id == case_id)
                .order_by(CaseAnalysis.created_at.desc(), CaseAnalysis.id.desc())
                .first()
            )
            if latest_analysis is not None and latest_analysis.id != analysis.id:
                reasons.append(
                    "A newer Phase 2 analysis exists; finalize that workflow revision before importing."
                )

        packet_id_value = payload.get("phase4PacketId")
        packet_id = (
            packet_id_value
            if isinstance(packet_id_value, int) and not isinstance(packet_id_value, bool)
            else None
        )
        packet = None
        if packet_id is not None and case_id:
            packet = (
                db.query(Phase4FormPacket)
                .filter(Phase4FormPacket.id == packet_id, Phase4FormPacket.case_id == case_id)
                .first()
            )
        packet_ready = bool(
            packet
            and packet.validation_status == "ready"
            and packet.generated_form_count > 0
        )
        if packet_id is None:
            reasons.append("Workflow has no linked Phase 4 form packet.")
        elif packet is None:
            reasons.append("The linked Phase 4 form packet does not belong to this case.")
        elif not packet_ready:
            reasons.append("The linked Phase 4 form packet is not ready.")
        elif latest_for_case(db, Phase4FormPacket, case_id).id != packet.id:
            packet_ready = False
            reasons.append(
                "A newer Phase 4 form packet exists; finalize that workflow revision before importing."
            )

        route_record = latest_for_case(db, Phase3CaseRoute, case_id) if case_id else None
        phase2_payload = payload.get("phase2Analysis")
        if not isinstance(phase2_payload, dict):
            phase2_payload = {}
        detected = phase2_payload.get("detected_keywords")
        if not isinstance(detected, dict):
            detected = {}
        jurisdiction = str(phase2_payload.get("jurisdiction_decision") or "").strip().lower()
        route = str(
            (route_record.recommended_route if route_record else "")
            or payload.get("phase3RecommendedRoute")
            or outcome
        ).strip()
        referral_required = bool(
            payload.get("phase3ReferralRequired")
            or detected.get("vawc_trigger")
            or (jurisdiction and jurisdiction != "within_kp")
            or (route_record and route_record.recommended_route != "Proceed to Mediation")
        )

        resolution = payload.get("referralResolution")
        if not isinstance(resolution, dict):
            resolution = {}
        referral_id_value = resolution.get("referralId")
        referral_id = (
            referral_id_value
            if isinstance(referral_id_value, int) and not isinstance(referral_id_value, bool)
            else None
        )
        referral = None
        if referral_id is not None and case_id:
            referral = (
                db.query(Referral)
                .filter(Referral.id == referral_id, Referral.case_id == case_id)
                .first()
            )
        resolution_status = str(resolution.get("status") or "").strip().lower()
        referral_ready = bool(
            not referral_required
            or (
                resolution_status in {"completed", "cancelled"}
                and referral is not None
                and referral.status == resolution_status
            )
        )
        official_decision = latest_for_case(db, Phase3OfficialDecision, case_id) if case_id else None
        # A verified cancellation resolution, including its required reason and
        # audit trail, is itself the official administrative action. It does not
        # require a contradictory "referral sent" decision record.
        cancelled_resolution_ready = bool(
            resolution_status == "cancelled"
            and referral_ready
            and str(resolution.get("cancellationReason") or "").strip()
        )
        official_decision_ready = bool(
            not referral_required or official_decision is not None or cancelled_resolution_ready
        )
        if referral_required and not referral_ready:
            reasons.append("The required referral has not been verified as completed or officially cancelled.")
        if referral_required and not official_decision_ready:
            reasons.append("The required official referral decision has not been saved.")

        existing = (
            db.query(Phase5ValidationCase)
            .filter(Phase5ValidationCase.case_id == case_id)
            .first()
            if case_id
            else None
        )
        already_imported = existing is not None
        if existing is not None and analysis_id is not None and existing.analysis_id != analysis_id:
            reasons.append(
                "This case is already in Phase 5 with a different Phase 2 analysis."
            )

        return {
            "workflow_id": draft.workflow_id,
            "case_id": case_id,
            "analysis_id": analysis_id,
            "revision": draft.revision,
            "status": draft.status,
            "outcome": outcome,
            "finalized_at": finalized_at,
            "route": route,
            "phase4_packet_id": packet_id,
            "packet_ready": packet_ready,
            "referral_required": referral_required,
            "referral_ready": referral_ready,
            "official_decision_ready": official_decision_ready,
            "already_imported": already_imported,
            "eligible": not reasons,
            "ineligibility_reasons": reasons,
        }

    def import_finalized_workflow(
        self,
        db: Session,
        workflow_id: str,
        payload: Phase5ImportCaseRequest,
        *,
        actor: str = "researcher",
    ) -> dict[str, Any]:
        draft = db.query(WorkflowDraft).filter(WorkflowDraft.workflow_id == workflow_id).first()
        if draft is None:
            raise HTTPException(status_code=404, detail="Workflow draft was not found.")

        source = self.workflow_import_readiness(db, draft)
        if not source["eligible"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Workflow is not ready for Phase 5 validation.",
                    "reasons": source["ineligibility_reasons"],
                },
            )

        analysis = db.query(CaseAnalysis).filter(CaseAnalysis.id == source["analysis_id"]).one()
        case_info = db.query(CaseInformation).filter(CaseInformation.id == analysis.case_information_id).one()
        transcript = (
            db.query(Transcript).filter(Transcript.id == analysis.transcript_id).first()
            if analysis.transcript_id is not None
            else None
        )
        packet = (
            db.query(Phase4FormPacket)
            .filter(Phase4FormPacket.id == source["phase4_packet_id"])
            .one()
        )
        existing = (
            db.query(Phase5ValidationCase)
            .filter(Phase5ValidationCase.case_id == source["case_id"])
            .first()
        )
        system_time = payload.system_processing_time_min
        if system_time is None:
            system_time = packet.processing_time_min
        values = {
            "analysis_id": analysis.id,
            "audio_id": payload.audio_id.strip() or f"audio-{source['case_id']}",
            "dataset_split": payload.dataset_split,
            "speaker_count": payload.speaker_count or self.detected_speaker_count(transcript),
            "speaker_gender_mix": payload.speaker_gender_mix,
            "audio_quality": payload.audio_quality,
            "manual_processing_time_min": payload.manual_processing_time_min,
            "system_processing_time_min": system_time,
            "notes": payload.notes,
        }
        if existing is not None:
            for key, value in values.items():
                setattr(existing, key, value)
            validation = existing
        else:
            validation = Phase5ValidationCase(case_id=case_info.case_id, **values)
            db.add(validation)
            db.flush()

        self.ground_truth_for_case(db, validation)
        self.compliance_for_case(db, validation)
        self.sync_research_dataset(db, validation)
        db.add(
            AuditLog(
                case_id=case_info.case_id,
                action="phase5_finalized_workflow_imported",
                actor=actor.strip() or "researcher",
                details_json={
                    "validation_case_id": validation.id,
                    "dataset_split": validation.dataset_split,
                    "workflow_id": draft.workflow_id,
                    "workflow_revision": draft.revision,
                    "analysis_id": analysis.id,
                    "phase4_packet_id": packet.id,
                    "outcome": source["outcome"],
                    "finalized_at": source["finalized_at"],
                },
            )
        )
        db.commit()
        db.refresh(validation)
        return {
            "validation_case": self.validation_case_response(db, validation),
            "source_workflow": self.workflow_import_readiness(db, draft),
        }

    def validation_cases(self, db: Session) -> list[dict[str, Any]]:
        cases = db.query(Phase5ValidationCase).order_by(Phase5ValidationCase.imported_at.desc()).all()
        return [self.validation_case_response(db, item) for item in cases]

    def get_validation_case(self, db: Session, case_id: str) -> Phase5ValidationCase:
        validation = db.query(Phase5ValidationCase).filter(Phase5ValidationCase.case_id == case_id).first()
        if not validation:
            raise HTTPException(status_code=404, detail="Phase 5 validation case was not found.")
        return validation

    def ground_truth_missing_fields(self, ground_truth: Phase5GroundTruth | None) -> list[str]:
        if ground_truth is None:
            return [
                "covered_under_kp",
                "jurisdiction_decision",
                "exclusion_ground",
                "sensitive_case",
                "referral_route",
                "mediation_eligible",
                "reviewer",
            ]
        missing: list[str] = []
        if ground_truth.expected_covered_under_kp is None:
            missing.append("covered_under_kp")
        if not ground_truth.expected_jurisdiction_decision.strip():
            missing.append("jurisdiction_decision")
        if not ground_truth.expected_exclusion_ground.strip():
            missing.append("exclusion_ground")
        if ground_truth.expected_sensitive_case is None:
            missing.append("sensitive_case")
        if not ground_truth.expected_referral_route.strip():
            missing.append("referral_route")
        if ground_truth.expected_mediation_eligible is None:
            missing.append("mediation_eligible")
        if not ground_truth.reviewer_name.strip():
            missing.append("reviewer")
        return missing

    def delete_pending_case(self, db: Session, case_id: str, actor: str = "researcher") -> dict[str, Any]:
        validation = self.get_validation_case(db, case_id)
        decisive_results = (
            db.query(Phase5EvaluationResult)
            .filter(
                Phase5EvaluationResult.validation_case_id == validation.id,
                Phase5EvaluationResult.overall_correct.isnot(None),
            )
            .count()
        )
        if decisive_results:
            raise HTTPException(
                status_code=409,
                detail="Evaluated validation cases cannot be removed. Keep completed results for reproducible research and error analysis.",
            )

        evaluation_count = (
            db.query(Phase5EvaluationResult)
            .filter(Phase5EvaluationResult.validation_case_id == validation.id)
            .count()
        )
        audio_id = validation.audio_id
        validation_id = validation.id
        db.query(Phase5EvaluationResult).filter(Phase5EvaluationResult.validation_case_id == validation_id).delete(synchronize_session=False)
        db.query(Phase5GroundTruth).filter(Phase5GroundTruth.validation_case_id == validation_id).delete(synchronize_session=False)
        db.query(Phase5ComplianceReview).filter(Phase5ComplianceReview.validation_case_id == validation_id).delete(synchronize_session=False)
        db.delete(validation)

        if audio_id:
            used_elsewhere = (
                db.query(Phase5ValidationCase)
                .filter(Phase5ValidationCase.audio_id == audio_id, Phase5ValidationCase.id != validation_id)
                .count()
            )
            if not used_elsewhere:
                db.query(KPResearchDataset).filter(KPResearchDataset.audio_id == audio_id).delete(synchronize_session=False)

        db.add(
            AuditLog(
                case_id=case_id,
                action="phase5_pending_case_removed",
                actor=actor,
                details_json={
                    "validation_case_id": validation_id,
                    "removed_inconclusive_evaluations": evaluation_count,
                    "source_case_preserved": True,
                },
            )
        )
        db.commit()
        return {
            "case_id": case_id,
            "status": "removed",
            "message": "Pending validation entry removed. The finalized workflow, case record, transcript, and forms were preserved.",
        }

    def import_case(self, db: Session, case_id: str, payload: Phase5ImportCaseRequest) -> dict[str, Any]:
        bundle = get_phase2_bundle(db, case_id)
        canonical_case_id = bundle.case_info.case_id
        existing = db.query(Phase5ValidationCase).filter(Phase5ValidationCase.case_id == canonical_case_id).first()
        latest_packet = latest_for_case(db, Phase4FormPacket, canonical_case_id)
        system_time = payload.system_processing_time_min
        if system_time is None and latest_packet:
            system_time = latest_packet.processing_time_min

        values = {
            "analysis_id": bundle.analysis.id,
            "audio_id": payload.audio_id.strip() or f"audio-{canonical_case_id}",
            "dataset_split": payload.dataset_split,
            "speaker_count": payload.speaker_count or self.detected_speaker_count(bundle.transcript),
            "speaker_gender_mix": payload.speaker_gender_mix,
            "audio_quality": payload.audio_quality,
            "manual_processing_time_min": payload.manual_processing_time_min,
            "system_processing_time_min": system_time,
            "notes": payload.notes,
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
            validation = existing
        else:
            validation = Phase5ValidationCase(case_id=canonical_case_id, **values)
            db.add(validation)
            db.flush()
            db.add(Phase5GroundTruth(validation_case_id=validation.id))
            db.add(Phase5ComplianceReview(validation_case_id=validation.id))

        self.sync_research_dataset(db, validation)
        db.add(
            AuditLog(
                case_id=canonical_case_id,
                action="phase5_case_imported",
                actor="researcher",
                details_json={"validation_case_id": validation.id, "dataset_split": validation.dataset_split},
            )
        )
        db.commit()
        db.refresh(validation)
        return self.validation_case_response(db, validation)

    def update_ground_truth(self, db: Session, case_id: str, payload: Phase5GroundTruthRequest) -> dict[str, Any]:
        validation = self.get_validation_case(db, case_id)
        ground_truth = self.ground_truth_for_case(db, validation)
        for key, value in payload.model_dump().items():
            setattr(ground_truth, key, value)
        db.add(
            AuditLog(
                case_id=validation.case_id,
                action="phase5_ground_truth_updated",
                actor=payload.reviewer_name or "researcher",
                details_json=payload.model_dump(),
            )
        )
        db.commit()
        db.refresh(ground_truth)
        return serialize_record(ground_truth)

    def update_compliance(self, db: Session, case_id: str, payload: Phase5ComplianceReviewRequest) -> dict[str, Any]:
        validation = self.get_validation_case(db, case_id)
        review = self.compliance_for_case(db, validation)
        data = payload.model_dump()
        for key, value in data.items():
            setattr(review, key, value)
        review.compliance_score = self.compliance_score(data)
        db.add(
            AuditLog(
                case_id=validation.case_id,
                action="phase5_compliance_review_updated",
                actor=payload.reviewer_name or "researcher",
                details_json={**data, "compliance_score": review.compliance_score},
            )
        )
        db.commit()
        db.refresh(review)
        return serialize_record(review)

    def evaluate_case(self, db: Session, case_id: str) -> dict[str, Any]:
        validation = self.get_validation_case(db, case_id)
        ground_truth = self.ground_truth_for_case(db, validation)
        missing_ground_truth = self.ground_truth_missing_fields(ground_truth)
        if missing_ground_truth:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Complete and save the required ground-truth fields before evaluation.",
                    "missing_fields": missing_ground_truth,
                },
            )
        compliance = self.compliance_for_case(db, validation)
        snapshot = self.system_snapshot(db, validation.case_id)
        errors: list[str] = []

        jurisdiction_correct = self.compare_text(
            ground_truth.expected_jurisdiction_decision,
            snapshot.jurisdiction_decision,
            "jurisdiction_decision",
            errors,
        )
        exclusion_correct = self.compare_text(
            ground_truth.expected_exclusion_ground,
            snapshot.exclusion_ground,
            "exclusion_ground",
            errors,
        )
        sensitive_case_correct = self.compare_bool(
            ground_truth.expected_sensitive_case,
            snapshot.sensitive_case,
            "sensitive_case",
            errors,
        )
        referral_correct = self.compare_text(
            ground_truth.expected_referral_route,
            snapshot.referral_route,
            "referral_route",
            errors,
        )
        mediation_correct = self.compare_bool(
            ground_truth.expected_mediation_eligible,
            snapshot.mediation_eligible,
            "mediation_eligible",
            errors,
        )
        speaker_count_correct = self.compare_int(
            ground_truth.expected_speaker_count,
            snapshot.detected_speaker_count,
            "speaker_count",
            errors,
        )
        forms_correct = self.compare_forms(
            ground_truth.expected_form_ids,
            snapshot.generated_form_ids,
            snapshot.recommended_form_ids,
            errors,
        )
        keyword_precision, keyword_recall = self.keyword_metrics(
            ground_truth.expected_keywords,
            snapshot.detected_keywords,
        )

        manual_time = validation.manual_processing_time_min
        system_time = validation.system_processing_time_min or snapshot.phase4_processing_time_min
        time_saved_min = None
        time_saved_pct = None
        if manual_time is not None and system_time is not None:
            time_saved_min = round(manual_time - system_time, 4)
            time_saved_pct = round((time_saved_min / manual_time) * 100, 2) if manual_time > 0 else None

        comparable = [
            jurisdiction_correct,
            exclusion_correct,
            sensitive_case_correct,
            referral_correct,
            mediation_correct,
            forms_correct,
            speaker_count_correct,
        ]
        actual_comparisons = [item for item in comparable if item is not None]
        overall_correct = all(actual_comparisons) if actual_comparisons else None
        metrics = {
            "case_id": validation.case_id,
            "jurisdiction_decision": {
                "expected": ground_truth.expected_jurisdiction_decision,
                "actual": snapshot.jurisdiction_decision,
                "correct": jurisdiction_correct,
            },
            "exclusion_ground": {
                "expected": ground_truth.expected_exclusion_ground,
                "actual": snapshot.exclusion_ground,
                "correct": exclusion_correct,
            },
            "sensitive_case": {
                "expected": ground_truth.expected_sensitive_case,
                "actual": snapshot.sensitive_case,
                "correct": sensitive_case_correct,
            },
            "referral_route": {
                "expected": ground_truth.expected_referral_route,
                "actual": snapshot.referral_route,
                "correct": referral_correct,
            },
            "mediation_eligible": {
                "expected": ground_truth.expected_mediation_eligible,
                "actual": snapshot.mediation_eligible,
                "correct": mediation_correct,
            },
            "form_ids": {
                "expected": ground_truth.expected_form_ids or [],
                "actual_generated": snapshot.generated_form_ids,
                "actual_recommended": snapshot.recommended_form_ids,
                "correct": forms_correct,
            },
            "keywords": {
                "expected": ground_truth.expected_keywords or [],
                "actual": snapshot.detected_keywords,
                "precision": keyword_precision,
                "recall": keyword_recall,
            },
            "processing_time": {
                "manual_min": manual_time,
                "system_min": system_time,
                "saved_min": time_saved_min,
                "saved_pct": time_saved_pct,
            },
            "xai_trace_length": snapshot.xai_trace_length,
            "compliance_signals": snapshot.compliance_signals,
        }

        result = Phase5EvaluationResult(
            validation_case_id=validation.id,
            jurisdiction_correct=jurisdiction_correct,
            exclusion_correct=exclusion_correct,
            sensitive_case_correct=sensitive_case_correct,
            referral_correct=referral_correct,
            mediation_correct=mediation_correct,
            forms_correct=forms_correct,
            speaker_count_correct=speaker_count_correct,
            overall_correct=overall_correct,
            keyword_precision=keyword_precision,
            keyword_recall=keyword_recall,
            form_accuracy_pct=snapshot.form_accuracy_pct,
            compliance_score=compliance.compliance_score,
            system_processing_time_min=system_time,
            manual_processing_time_min=manual_time,
            time_saved_min=time_saved_min,
            time_saved_pct=time_saved_pct,
            metrics_json=metrics,
            errors_json=errors,
        )
        db.add(result)
        db.add(
            AuditLog(
                case_id=validation.case_id,
                action="phase5_case_evaluated",
                actor=ground_truth.reviewer_name or "researcher",
                details_json={"overall_correct": overall_correct, "errors": errors},
            )
        )
        self.sync_research_dataset(db, validation)
        db.commit()
        db.refresh(result)
        return serialize_record(result)

    def evaluate_all(self, db: Session) -> list[dict[str, Any]]:
        cases = db.query(Phase5ValidationCase).order_by(Phase5ValidationCase.imported_at.asc()).all()
        ready_cases = []
        for item in cases:
            ground_truth = db.query(Phase5GroundTruth).filter(Phase5GroundTruth.validation_case_id == item.id).first()
            if not self.ground_truth_missing_fields(ground_truth):
                ready_cases.append(item)
        return [self.evaluate_case(db, item.case_id) for item in ready_cases]

    def metrics(self, db: Session) -> dict[str, Any]:
        cases = db.query(Phase5ValidationCase).all()
        latest_results = [self.latest_evaluation(db, case) for case in cases]
        # Legacy builds allowed an evaluation with no completed ground truth,
        # producing overall_correct=None. Such rows are inconclusive and must
        # not inflate the evaluated-case count or aggregate research metrics.
        results = [
            result
            for result in latest_results
            if result is not None and result.overall_correct is not None
        ]
        ground_truth_count = db.query(Phase5GroundTruth).count()
        metrics = {
            "case_count": len(cases),
            "evaluated_count": len(results),
            "ground_truth_count": ground_truth_count,
            "overall_accuracy_pct": bool_accuracy([item.overall_correct for item in results]),
            "jurisdiction_accuracy_pct": bool_accuracy([item.jurisdiction_correct for item in results]),
            "sensitive_accuracy_pct": bool_accuracy([item.sensitive_case_correct for item in results]),
            "referral_accuracy_pct": bool_accuracy([item.referral_correct for item in results]),
            "mediation_accuracy_pct": bool_accuracy([item.mediation_correct for item in results]),
            "forms_accuracy_pct": bool_accuracy([item.forms_correct for item in results]),
            "speaker_count_accuracy_pct": bool_accuracy([item.speaker_count_correct for item in results]),
            "average_keyword_precision_pct": average([item.keyword_precision for item in results]),
            "average_keyword_recall_pct": average([item.keyword_recall for item in results]),
            "average_form_accuracy_pct": average([item.form_accuracy_pct for item in results]),
            "average_compliance_score_pct": average([item.compliance_score for item in results]),
            "average_manual_time_min": average([item.manual_processing_time_min for item in results]),
            "average_system_time_min": average([item.system_processing_time_min for item in results]),
            "average_time_saved_min": average([item.time_saved_min for item in results]),
            "average_time_saved_pct": average([item.time_saved_pct for item in results]),
            "by_dispute_category": self.group_accuracy(db, cases, results, "dispute_category"),
            "by_speaker_gender_mix": self.group_accuracy(db, cases, results, "speaker_gender_mix"),
            "error_cases": [
                {
                    "case_id": self.case_for_result(db, result).case_id,
                    "errors": result.errors_json,
                    "evaluated_at": result.evaluated_at.isoformat(),
                }
                for result in results
                if result.errors_json
            ],
        }
        return metrics

    def create_experiment_run(self, db: Session, payload: Phase5ExperimentRunRequest) -> dict[str, Any]:
        metrics = self.metrics(db)
        run = Phase5ExperimentRun(
            name=payload.name,
            case_count=metrics["case_count"],
            metrics_json=metrics,
            created_by=payload.created_by,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return serialize_record(run)

    def experiment_runs(self, db: Session) -> list[dict[str, Any]]:
        runs = db.query(Phase5ExperimentRun).order_by(Phase5ExperimentRun.created_at.desc()).all()
        return [serialize_record(run) for run in runs]

    def csv_export(self, db: Session, anonymized: bool = False) -> str:
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "case_id",
                "dispute_category",
                "speaker_gender_mix",
                "audio_quality",
                "expected_jurisdiction",
                "actual_jurisdiction",
                "jurisdiction_correct",
                "expected_exclusion",
                "actual_exclusion",
                "sensitive_correct",
                "referral_correct",
                "mediation_correct",
                "forms_correct",
                "overall_correct",
                "keyword_precision",
                "keyword_recall",
                "form_accuracy_pct",
                "compliance_score",
                "manual_time_min",
                "system_time_min",
                "time_saved_min",
                "time_saved_pct",
                "errors",
            ]
        )
        for validation in db.query(Phase5ValidationCase).order_by(Phase5ValidationCase.case_id.asc()).all():
            ground_truth = self.ground_truth_for_case(db, validation)
            snapshot = self.system_snapshot(db, validation.case_id)
            result = self.latest_evaluation(db, validation)
            writer.writerow(
                [
                    self.anonymized_case_id(validation.case_id) if anonymized else validation.case_id,
                    snapshot.case_information.get("dispute_category", ""),
                    validation.speaker_gender_mix,
                    validation.audio_quality,
                    ground_truth.expected_jurisdiction_decision,
                    snapshot.jurisdiction_decision,
                    result.jurisdiction_correct if result else "",
                    ground_truth.expected_exclusion_ground,
                    snapshot.exclusion_ground,
                    result.sensitive_case_correct if result else "",
                    result.referral_correct if result else "",
                    result.mediation_correct if result else "",
                    result.forms_correct if result else "",
                    result.overall_correct if result else "",
                    result.keyword_precision if result else "",
                    result.keyword_recall if result else "",
                    result.form_accuracy_pct if result else "",
                    result.compliance_score if result else "",
                    result.manual_processing_time_min if result else validation.manual_processing_time_min,
                    result.system_processing_time_min if result else validation.system_processing_time_min,
                    result.time_saved_min if result else "",
                    result.time_saved_pct if result else "",
                    " | ".join(result.errors_json) if result else "",
                ]
            )
        return output.getvalue()

    def report_text(self, db: Session, anonymized: bool = False) -> str:
        metrics = self.metrics(db)
        lines = [
            "JUSTICE-KP Phase 5 Validation Report" + (" (Anonymized)" if anonymized else ""),
            "",
            f"Cases imported: {metrics['case_count']}",
            f"Cases evaluated: {metrics['evaluated_count']}",
            f"Overall accuracy: {self.display_metric(metrics['overall_accuracy_pct'])}",
            f"Jurisdiction accuracy: {self.display_metric(metrics['jurisdiction_accuracy_pct'])}",
            f"Sensitive-case accuracy: {self.display_metric(metrics['sensitive_accuracy_pct'])}",
            f"Referral accuracy: {self.display_metric(metrics['referral_accuracy_pct'])}",
            f"Mediation accuracy: {self.display_metric(metrics['mediation_accuracy_pct'])}",
            f"Form recommendation accuracy: {self.display_metric(metrics['forms_accuracy_pct'])}",
            f"Average form completion: {self.display_metric(metrics['average_form_accuracy_pct'])}",
            f"Average compliance score: {self.display_metric(metrics['average_compliance_score_pct'])}",
            f"Average manual time: {metrics['average_manual_time_min'] or 'N/A'} min",
            f"Average system time: {metrics['average_system_time_min'] or 'N/A'} min",
            f"Average time saved: {metrics['average_time_saved_min'] or 'N/A'} min",
            f"Average time saved percent: {self.display_metric(metrics['average_time_saved_pct'])}",
            "",
            "Error Cases:",
        ]
        if not metrics["error_cases"]:
            lines.append("None")
        for item in metrics["error_cases"]:
            case_id = self.anonymized_case_id(item["case_id"]) if anonymized else item["case_id"]
            lines.append(f"- {case_id}: {'; '.join(item['errors'])}")
        return "\n".join(lines)

    def report_pdf(self, db: Session, anonymized: bool = False) -> bytes:
        rows = self.report_text(db, anonymized=anonymized).splitlines()
        return self.render_pdf(rows)

    def validation_case_response(self, db: Session, validation: Phase5ValidationCase) -> dict[str, Any]:
        snapshot = self.system_snapshot(db, validation.case_id)
        ground_truth = db.query(Phase5GroundTruth).filter(Phase5GroundTruth.validation_case_id == validation.id).first()
        latest = self.latest_evaluation(db, validation)
        latest_decisive = (
            db.query(Phase5EvaluationResult)
            .filter(
                Phase5EvaluationResult.validation_case_id == validation.id,
                Phase5EvaluationResult.overall_correct.isnot(None),
            )
            .order_by(Phase5EvaluationResult.evaluated_at.desc(), Phase5EvaluationResult.id.desc())
            .first()
        )
        displayed_evaluation = latest_decisive or latest
        compliance = db.query(Phase5ComplianceReview).filter(Phase5ComplianceReview.validation_case_id == validation.id).first()
        missing_ground_truth = self.ground_truth_missing_fields(ground_truth)
        ground_truth_ready = not missing_ground_truth
        has_decisive_evaluation = latest_decisive is not None
        review_status = (
            "evaluated"
            if has_decisive_evaluation
            else "ready_for_evaluation"
            if ground_truth_ready
            else "needs_ground_truth"
        )
        return {
            **serialize_record(validation),
            "case_information": snapshot.case_information,
            "system_outputs": {
                "jurisdiction_decision": snapshot.jurisdiction_decision,
                "normalized_jurisdiction_decision": snapshot.normalized_jurisdiction_decision,
                "exclusion_ground": snapshot.exclusion_ground,
                "sensitive_case": snapshot.sensitive_case,
                "referral_route": snapshot.referral_route,
                "mediation_eligible": snapshot.mediation_eligible,
                "generated_form_ids": snapshot.generated_form_ids,
                "recommended_form_ids": snapshot.recommended_form_ids,
                "detected_keywords": snapshot.detected_keywords,
                "detected_speaker_count": snapshot.detected_speaker_count,
                "xai_trace_length": snapshot.xai_trace_length,
                "form_accuracy_pct": snapshot.form_accuracy_pct,
                "final_recommended_action": snapshot.final_recommended_action,
            },
            "ground_truth": serialize_record(ground_truth) if ground_truth else None,
            "latest_evaluation": serialize_record(displayed_evaluation) if displayed_evaluation else None,
            "compliance_review": serialize_record(compliance) if compliance else None,
            "review_status": review_status,
            "ground_truth_ready": ground_truth_ready,
            "ground_truth_missing_fields": missing_ground_truth,
            "can_delete": not has_decisive_evaluation,
        }

    def system_snapshot(self, db: Session, case_id: str) -> Phase5SystemSnapshot:
        dashboard = Phase3DashboardService().build(db, case_id)
        canonical_case_id = dashboard["case_id"]
        phase2 = dashboard["phase2"]
        phase3 = dashboard["phase3"]
        latest_packet = latest_for_case(db, Phase4FormPacket, canonical_case_id)
        generated_form_ids = latest_packet.selected_forms_json if latest_packet else []
        recommended_form_ids = []
        if latest_packet:
            recommended_form_ids = latest_packet.selected_forms_json
        detected_keywords = phase2.get("detected_keywords", {}).get("detected_keywords") or []
        route = phase3.get("sensitive_routing") or {}
        eligibility = phase3.get("mediation_eligibility") or {}
        referrals = phase3.get("referrals") or []
        official_decision = phase3.get("official_decision")
        evidence = phase3.get("evidence") or []
        transcript_segments = dashboard["phase1"].get("segments") or []
        detected_speaker_count = self.detected_speaker_count_from_segments(transcript_segments)
        if detected_speaker_count is None and dashboard["phase1"].get("transcript"):
            detected_speaker_count = len(set(re.findall(r"Speaker\s+\d+", dashboard["phase1"]["transcript"])))

        return Phase5SystemSnapshot(
            case_id=canonical_case_id,
            case_information=phase2.get("case_information", {}),
            jurisdiction_decision=phase2.get("jurisdiction_decision", ""),
            normalized_jurisdiction_decision=phase2.get("normalized_jurisdiction_decision", ""),
            exclusion_ground=phase2.get("exclusion_ground", ""),
            sensitive_case=bool(route.get("is_sensitive") or phase2.get("detected_keywords", {}).get("vawc_trigger")),
            referral_route=route.get("recommended_route") or phase3.get("final_recommended_action", ""),
            mediation_eligible=eligibility.get("eligible_for_mediation") if eligibility else None,
            generated_form_ids=generated_form_ids,
            recommended_form_ids=recommended_form_ids,
            detected_keywords=detected_keywords,
            detected_speaker_count=detected_speaker_count,
            xai_trace_length=len(phase2.get("xai_trace") or []),
            form_accuracy_pct=latest_packet.form_accuracy_pct if latest_packet else None,
            phase4_processing_time_min=latest_packet.processing_time_min if latest_packet else None,
            final_recommended_action=phase3.get("final_recommended_action", ""),
            compliance_signals={
                "official_decision_saved": bool(official_decision),
                "generated_forms_reviewed": bool(latest_packet and latest_packet.approved_by),
                "audit_trail_complete": db.query(AuditLog).filter(AuditLog.case_id == canonical_case_id).count() > 0,
                "sensitive_case_referred": bool((not route.get("is_sensitive")) or referrals),
                "evidence_present": bool(evidence),
            },
        )

    def detected_speaker_count(self, transcript: Transcript | None) -> int | None:
        if not transcript:
            return None
        return self.detected_speaker_count_from_segments(transcript.segments_json or [])

    def detected_speaker_count_from_segments(self, segments: list[dict[str, Any]]) -> int | None:
        speakers = {str(item.get("speaker", "")).strip() for item in segments if item.get("speaker")}
        return len(speakers) or None

    def ground_truth_for_case(self, db: Session, validation: Phase5ValidationCase) -> Phase5GroundTruth:
        ground_truth = db.query(Phase5GroundTruth).filter(Phase5GroundTruth.validation_case_id == validation.id).first()
        if ground_truth:
            return ground_truth
        ground_truth = Phase5GroundTruth(validation_case_id=validation.id)
        db.add(ground_truth)
        db.flush()
        return ground_truth

    def compliance_for_case(self, db: Session, validation: Phase5ValidationCase) -> Phase5ComplianceReview:
        review = db.query(Phase5ComplianceReview).filter(Phase5ComplianceReview.validation_case_id == validation.id).first()
        if review:
            return review
        review = Phase5ComplianceReview(validation_case_id=validation.id)
        db.add(review)
        db.flush()
        return review

    def latest_evaluation(self, db: Session, validation: Phase5ValidationCase) -> Phase5EvaluationResult | None:
        return (
            db.query(Phase5EvaluationResult)
            .filter(Phase5EvaluationResult.validation_case_id == validation.id)
            .order_by(Phase5EvaluationResult.evaluated_at.desc(), Phase5EvaluationResult.id.desc())
            .first()
        )

    def case_for_result(self, db: Session, result: Phase5EvaluationResult) -> Phase5ValidationCase:
        return db.query(Phase5ValidationCase).filter(Phase5ValidationCase.id == result.validation_case_id).first()

    def compare_text(self, expected: str, actual: str, label: str, errors: list[str]) -> bool | None:
        if not expected:
            return None
        correct = expected.strip().lower() == (actual or "").strip().lower()
        if not correct:
            errors.append(f"{label}: expected {expected}, got {actual or 'None'}")
        return correct

    def compare_bool(self, expected: bool | None, actual: bool | None, label: str, errors: list[str]) -> bool | None:
        if expected is None or actual is None:
            return None
        correct = expected == actual
        if not correct:
            errors.append(f"{label}: expected {expected}, got {actual}")
        return correct

    def compare_int(self, expected: int | None, actual: int | None, label: str, errors: list[str]) -> bool | None:
        if expected is None or actual is None:
            return None
        correct = expected == actual
        if not correct:
            errors.append(f"{label}: expected {expected}, got {actual}")
        return correct

    def compare_forms(
        self,
        expected_ids: list[str] | None,
        generated_ids: list[str],
        recommended_ids: list[str],
        errors: list[str],
    ) -> bool | None:
        expected = set(expected_ids or [])
        if not expected:
            return None
        actual = set(generated_ids or recommended_ids)
        correct = expected == actual
        if not correct:
            errors.append(f"form_ids: expected {sorted(expected)}, got {sorted(actual)}")
        return correct

    def keyword_metrics(self, expected_keywords: list[str] | None, actual_keywords: list[str]) -> tuple[float | None, float | None]:
        expected = {item.lower() for item in expected_keywords or [] if item}
        actual = {item.lower() for item in actual_keywords or [] if item}
        if not expected:
            return None, None
        true_positive = len(expected.intersection(actual))
        precision_value = percent(true_positive, len(actual)) if actual else 0.0
        recall_value = percent(true_positive, len(expected))
        return precision_value, recall_value

    def compliance_score(self, values: dict[str, Any]) -> float:
        flags = [
            bool(values.get("consent_confirmed")),
            bool(values.get("transcript_anonymized")),
            bool(values.get("official_decision_saved")),
            bool(values.get("generated_forms_reviewed")),
            bool(values.get("audit_trail_complete")),
            bool(values.get("sensitive_case_referred")),
        ]
        return percent(sum(1 for item in flags if item), len(flags)) or 0.0

    def group_accuracy(
        self,
        db: Session,
        cases: list[Phase5ValidationCase],
        results: list[Phase5EvaluationResult],
        key: str,
    ) -> list[dict[str, Any]]:
        result_map = {result.validation_case_id: result for result in results}
        groups: dict[str, list[Phase5EvaluationResult]] = {}
        for validation in cases:
            if key == "dispute_category":
                try:
                    snapshot = self.system_snapshot(db, validation.case_id)
                    group_key = str(snapshot.case_information.get("dispute_category") or "unknown")
                except HTTPException:
                    group_key = "unknown"
            else:
                group_key = str(getattr(validation, key) or "unknown")
            result = result_map.get(validation.id)
            if result:
                groups.setdefault(group_key, []).append(result)
            else:
                groups.setdefault(group_key, [])
        return [
            {
                "group": group_key,
                "case_count": len(items),
                "overall_accuracy_pct": bool_accuracy([item.overall_correct for item in items]),
                "jurisdiction_accuracy_pct": bool_accuracy([item.jurisdiction_correct for item in items]),
            }
            for group_key, items in sorted(groups.items())
        ]

    def sync_research_dataset(self, db: Session, validation: Phase5ValidationCase) -> None:
        try:
            bundle = get_phase2_bundle(db, validation.case_id)
            snapshot = self.system_snapshot(db, validation.case_id)
        except HTTPException:
            return
        case_info = bundle.case_info
        audio_id = validation.audio_id or f"audio-{validation.case_id}"
        existing = db.query(KPResearchDataset).filter(KPResearchDataset.audio_id == audio_id).first()
        values = {
            "barangay_name": case_info.barangay_name,
            "city_municipality": case_info.city_municipality,
            "case_year": case_info.case_year,
            "case_type": case_info.case_type,
            "dispute_category": case_info.dispute_category,
            "complainant_residency": case_info.complainant_residency,
            "respondent_residency": case_info.respondent_residency,
            "debt_amount_php": case_info.debt_amount_php,
            "penalty_years_max": case_info.maximum_penalty_years,
            "vawc_trigger": bool(bundle.analysis.detected_keywords_json.get("vawc_trigger")),
            "speaker_count": validation.speaker_count or snapshot.detected_speaker_count,
            "emotion_tension": (Phase3DashboardService().build(db, validation.case_id)["phase3"].get("emotion_analysis") or {}).get("tension_score"),
            "covered_under_kp": normalize_jurisdiction(bundle.analysis.jurisdiction_decision) == "within_kp",
            "kp_exclusion_ground": bundle.analysis.exclusion_ground,
            "jurisdiction_decision": bundle.analysis.jurisdiction_decision,
            "processing_time_min": validation.system_processing_time_min or snapshot.phase4_processing_time_min,
            "form_accuracy_pct": snapshot.form_accuracy_pct,
            "xai_trace_length": snapshot.xai_trace_length,
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            db.add(KPResearchDataset(audio_id=audio_id, **values))

    def display_metric(self, value: float | None) -> str:
        return "N/A" if value is None else f"{value}%"

    def anonymized_case_id(self, case_id: str) -> str:
        digest = hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:10].upper()
        return f"CASE-{digest}"

    def render_pdf(self, rows: list[str]) -> bytes:
        lines: list[str] = []
        for row in rows:
            lines.extend(self.wrap_line(row, 88) or [""])
        content = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
        for line in lines[:52]:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content.append(f"({escaped}) Tj")
            content.append("T*")
        content.append("ET")
        stream = "\n".join(content).encode("latin-1", errors="replace")
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


# Imported late to avoid keeping a rarely used dependency at module top during
# tests that do not exercise text fallback speaker detection.
import re  # noqa: E402
