from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


CaseType = Literal["civil", "criminal", "administrative", "other"]
DisputeCategory = Literal[
    "debt",
    "boundary",
    "family_dispute",
    "physical_injury",
    "nuisance",
    "threat",
    "property_damage",
    "online_defamation",
    "neighbor_altercation",
    "harassment_unjust_vexation",
    "business_defamation",
    "other",
]
Residency = Literal["same_barangay", "adjacent_barangay", "different_municipality"]
ProceedingOrigin = Literal["new_complaint", "court_referred", "other"]
VenueBasis = Literal[
    "same_barangay",
    "respondent_barangay",
    "real_property_location",
    "workplace_or_school",
    "manual_review",
]
JurisdictionDecision = Literal[
    "within_kp",
    "outside_kp",
    "refer_to_pnp_wcpc_or_authority",
    "ambiguous_manual_review",
]
ConfidenceLevel = Literal["high", "medium", "low"]


class CaseInformationPayload(BaseModel):
    case_id: str = ""
    barangay_name: str = ""
    city_municipality: str = ""
    case_year: int | None = Field(default=None, ge=1900, le=2100)
    case_type: CaseType = "civil"
    dispute_category: DisputeCategory = "other"
    complainant_residency: Residency | None = None
    respondent_residency: Residency | None = None
    debt_amount_php: float | None = Field(default=None, ge=0)
    maximum_penalty_years: float | None = Field(default=0, ge=0)
    fine_amount_php: float | None = Field(default=0, ge=0)
    government_party_involved: bool = False
    already_filed_in_court: bool = False
    has_vawc_or_child_abuse_indicators: bool = False
    proceeding_origin: ProceedingOrigin = "new_complaint"
    has_juridical_entity_party: bool = False
    public_officer_involved: bool = False
    public_officer_official_function: bool = False
    no_private_offended_party: bool = False
    offense_classification: str = ""
    penalty_lookup_required: bool = False
    real_property_involved: bool = False
    real_property_barangay: str = ""
    real_property_city_municipality: str = ""
    real_property_in_different_city_municipality: bool = False
    parties_in_different_city_municipality: bool = False
    parties_in_adjoining_barangays: bool = False
    mutual_agreement_to_kp: bool = False
    respondent_barangay: str = ""
    respondent_city_municipality: str = ""
    incident_venue_basis: VenueBasis = "same_barangay"
    workplace_or_school_dispute: bool = False
    workplace_or_school_barangay: str = ""
    workplace_or_school_city_municipality: str = ""
    accused_under_detention: bool = False
    liberty_or_habeas_issue: bool = False
    provisional_remedy_needed: bool = False
    statute_limitations_urgent: bool = False
    minor_or_incompetent_party: bool = False
    next_of_kin_assistant_name: str = ""
    next_of_kin_is_lawyer: bool = False
    indigenous_community_dispute: bool = False
    same_indigenous_community: bool = False
    indigenous_process_agreed: bool = False


class AnalyzeCaseRequest(BaseModel):
    transcript_id: int | None = None
    transcript_text: str | None = None
    case_information: CaseInformationPayload

    @model_validator(mode="after")
    def require_transcript_source(self):
        if self.transcript_id is None and not (self.transcript_text and self.transcript_text.strip()):
            raise ValueError("transcript_id or transcript_text is required")
        return self


class AnalyzeCaseResponse(BaseModel):
    transcript_id: int | None = None
    case_information: CaseInformationPayload
    extracted_entities: dict[str, Any]
    detected_keywords: dict[str, Any]
    jurisdiction_decision: JurisdictionDecision
    exclusion_ground: str
    confidence_level: ConfidenceLevel
    missing_fields: list[str]
    recommended_next_action: str
    xai_trace: list[str]
    rule_results: list[dict[str, Any]]


class SaveCaseAnalysisRequest(AnalyzeCaseResponse):
    pass


class SaveCaseAnalysisResponse(BaseModel):
    message: str
    id: int
    created_at: datetime


class CaseAnalysisSummary(BaseModel):
    id: int
    transcript_id: int | None
    case_id: str
    barangay_name: str
    jurisdiction_decision: str
    exclusion_ground: str
    confidence_level: str
    recommended_next_action: str
    created_at: datetime
