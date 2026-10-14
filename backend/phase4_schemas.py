from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ValidationStatus = Literal["ready", "needs_review"]


class Phase4GeneratePacketRequest(BaseModel):
    form_ids: list[str] = []
    generated_by: str = Field(default="Barangay Official", min_length=1)
    approved_by: str = ""
    field_overrides: dict[str, Any] = {}


class Phase4TemplateResponse(BaseModel):
    form_id: str
    form_number: str
    title: str
    purpose: str
    stage: str
    required_fields: list[str]
    when_used: list[str]
    source_template_url: str


class Phase4RecommendationResponse(BaseModel):
    case_id: str
    final_recommended_action: str
    recommended_forms: list[Phase4TemplateResponse]
    optional_forms: list[Phase4TemplateResponse]
    missing_fields: dict[str, list[str]]
    validation_status: ValidationStatus
    form_accuracy_pct: float


class Phase4GeneratedFormResponse(BaseModel):
    id: int
    packet_id: int
    case_id: str
    form_id: str
    title: str
    purpose: str
    download_url: str
    field_values: dict[str, Any]
    missing_fields: list[str]
    validation_status: ValidationStatus
    created_at: datetime


class Phase4PacketResponse(BaseModel):
    id: int
    case_id: str
    source_phase3_action: str
    selected_forms: list[str]
    generated_form_count: int
    missing_fields: dict[str, list[str]]
    validation_status: ValidationStatus
    form_accuracy_pct: float
    processing_time_min: float
    generated_by: str
    approved_by: str
    created_at: datetime
    approved_at: datetime | None
    generated_forms: list[Phase4GeneratedFormResponse]
