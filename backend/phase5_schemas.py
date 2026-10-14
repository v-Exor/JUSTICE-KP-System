from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Phase5ImportCaseRequest(BaseModel):
    audio_id: str = ""
    dataset_split: str = "validation"
    speaker_count: int | None = None
    speaker_gender_mix: str = "unspecified"
    audio_quality: str = "unspecified"
    manual_processing_time_min: float | None = Field(default=None, ge=0)
    system_processing_time_min: float | None = Field(default=None, ge=0)
    notes: str = ""


class Phase5ImportableWorkflowResponse(BaseModel):
    workflow_id: str
    case_id: str
    analysis_id: int | None
    revision: int
    status: str
    outcome: str
    finalized_at: str | None
    route: str
    phase4_packet_id: int | None
    packet_ready: bool
    referral_required: bool
    referral_ready: bool
    official_decision_ready: bool
    already_imported: bool
    eligible: bool
    ineligibility_reasons: list[str]


class Phase5GroundTruthRequest(BaseModel):
    expected_covered_under_kp: bool | None = None
    expected_jurisdiction_decision: str = ""
    expected_exclusion_ground: str = ""
    expected_sensitive_case: bool | None = None
    expected_referral_route: str = ""
    expected_mediation_eligible: bool | None = None
    expected_form_ids: list[str] = []
    expected_keywords: list[str] = []
    expected_speaker_count: int | None = None
    reference_transcript: str = ""
    reviewer_name: str = ""


class Phase5ComplianceReviewRequest(BaseModel):
    consent_confirmed: bool = False
    transcript_anonymized: bool = False
    official_decision_saved: bool = False
    generated_forms_reviewed: bool = False
    audit_trail_complete: bool = False
    sensitive_case_referred: bool = False
    reviewer_name: str = ""
    notes: str = ""


class Phase5ExperimentRunRequest(BaseModel):
    name: str = Field(min_length=1)
    created_by: str = "researcher"


class Phase5ValidationCaseResponse(BaseModel):
    id: int
    case_id: str
    analysis_id: int
    audio_id: str | None
    dataset_split: str
    speaker_count: int | None
    speaker_gender_mix: str
    audio_quality: str
    manual_processing_time_min: float | None
    system_processing_time_min: float | None
    notes: str
    imported_at: datetime
    updated_at: datetime
    case_information: dict[str, Any]
    system_outputs: dict[str, Any]
    ground_truth: dict[str, Any] | None = None
    latest_evaluation: dict[str, Any] | None = None
    compliance_review: dict[str, Any] | None = None
    review_status: str
    ground_truth_ready: bool
    ground_truth_missing_fields: list[str]
    can_delete: bool


class Phase5FinalizedWorkflowImportResponse(BaseModel):
    validation_case: Phase5ValidationCaseResponse
    source_workflow: Phase5ImportableWorkflowResponse


class Phase5EvaluationResponse(BaseModel):
    id: int
    validation_case_id: int
    jurisdiction_correct: bool | None
    exclusion_correct: bool | None
    sensitive_case_correct: bool | None
    referral_correct: bool | None
    mediation_correct: bool | None
    forms_correct: bool | None
    speaker_count_correct: bool | None
    overall_correct: bool | None
    keyword_precision: float | None
    keyword_recall: float | None
    form_accuracy_pct: float | None
    compliance_score: float | None
    system_processing_time_min: float | None
    manual_processing_time_min: float | None
    time_saved_min: float | None
    time_saved_pct: float | None
    metrics_json: dict[str, Any]
    errors_json: list[str]
    evaluated_at: datetime


class Phase5MetricsResponse(BaseModel):
    case_count: int
    evaluated_count: int
    ground_truth_count: int
    overall_accuracy_pct: float | None
    jurisdiction_accuracy_pct: float | None
    sensitive_accuracy_pct: float | None
    referral_accuracy_pct: float | None
    mediation_accuracy_pct: float | None
    forms_accuracy_pct: float | None
    speaker_count_accuracy_pct: float | None
    average_keyword_precision_pct: float | None
    average_keyword_recall_pct: float | None
    average_form_accuracy_pct: float | None
    average_compliance_score_pct: float | None
    average_manual_time_min: float | None
    average_system_time_min: float | None
    average_time_saved_min: float | None
    average_time_saved_pct: float | None
    by_dispute_category: list[dict[str, Any]]
    by_speaker_gender_mix: list[dict[str, Any]]
    error_cases: list[dict[str, Any]]


class Phase5ExperimentRunResponse(BaseModel):
    id: int
    name: str
    case_count: int
    metrics_json: dict[str, Any]
    created_by: str
    created_at: datetime
