from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ReferralStatus = Literal["pending", "completed", "cancelled"]
HearingStatus = Literal["scheduled", "completed", "missed", "cancelled"]
HearingType = Literal["initial", "mediation", "follow_up", "final"]


class ReferralCreateRequest(BaseModel):
    case_id: str
    referral_type: str
    destination: str
    reason: str
    matched_keywords: list[str] = []
    xai_reference: list[str] = []
    status: ReferralStatus = "pending"


class ReferralUpdateRequest(BaseModel):
    status: ReferralStatus | None = None
    reason: str | None = None


class HearingCreateRequest(BaseModel):
    case_id: str
    hearing_type: HearingType = "initial"
    scheduled_date: str
    scheduled_time: str
    location: str
    assigned_lupon_member: str
    status: HearingStatus = "scheduled"
    notes: str = ""


class HearingUpdateRequest(BaseModel):
    hearing_type: HearingType | None = None
    scheduled_date: str | None = None
    scheduled_time: str | None = None
    location: str | None = None
    assigned_lupon_member: str | None = None
    status: HearingStatus | None = None
    notes: str | None = None


class EvidenceUpdateRequest(BaseModel):
    evidence_text: str | None = None
    extracted_entities: dict[str, Any] | None = None


class OfficialDecisionRequest(BaseModel):
    official_decision: str = Field(min_length=1)
    official_notes: str = ""
    approved_by: str = Field(min_length=1)


class OfficialDecisionResponse(BaseModel):
    id: int
    case_id: str
    system_recommendation: str
    official_decision: str
    official_notes: str
    approved_by: str
    approved_at: datetime
