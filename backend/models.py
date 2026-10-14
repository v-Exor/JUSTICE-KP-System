from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, JSON, Column, DateTime, Integer, Text

from database import Base


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True, index=True)
    # Workflow transcripts are canonical per workflow/case.  Legacy and
    # research-only transcripts remain valid with these values left NULL.
    workflow_id = Column(Text, nullable=True, unique=True, index=True)
    case_id = Column(Text, nullable=True, unique=True, index=True)
    save_context = Column(Text, default="standalone", nullable=False)
    superseded_by_transcript_id = Column(Integer, nullable=True, index=True)
    content = Column(Text, nullable=False)
    raw_content = Column(Text, default="", nullable=False)
    segments_json = Column(JSON, nullable=True)
    raw_segments_json = Column(JSON, nullable=True)
    corrections_json = Column(JSON, nullable=True)
    asr_provider = Column(Text, default="", nullable=False)
    asr_confidence = Column(Float, nullable=True)
    diarization_quality = Column(Float, nullable=True)
    manual_correction_rate = Column(Float, nullable=True)
    correction_count = Column(Integer, default=0, nullable=False)
    original_word_count = Column(Integer, default=0, nullable=False)
    edited_word_count = Column(Integer, default=0, nullable=False)
    expected_speakers = Column(Integer, nullable=True)
    detected_speakers = Column(Integer, nullable=True)
    recording_type = Column(Text, default="", nullable=False)
    accuracy_metrics_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PhraseCorrection(Base):
    __tablename__ = "phrase_corrections"

    id = Column(Integer, primary_key=True, index=True)
    wrong_phrase = Column(Text, nullable=False, unique=True)
    correct_phrase = Column(Text, nullable=False)
    usage_count = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class CaseInformation(Base):
    __tablename__ = "case_information"

    id = Column(Integer, primary_key=True, index=True)
    transcript_id = Column(Integer, ForeignKey("transcripts.id"), nullable=True, index=True)
    case_id = Column(Text, nullable=False)
    barangay_name = Column(Text, nullable=False)
    city_municipality = Column(Text, nullable=False)
    case_year = Column(Integer, nullable=True)
    case_type = Column(Text, nullable=False)
    dispute_category = Column(Text, nullable=False)
    complainant_residency = Column(Text, nullable=True)
    respondent_residency = Column(Text, nullable=True)
    debt_amount_php = Column(Float, nullable=True)
    maximum_penalty_years = Column(Float, nullable=True)
    fine_amount_php = Column(Float, nullable=True)
    government_party_involved = Column(Boolean, default=False, nullable=False)
    already_filed_in_court = Column(Boolean, default=False, nullable=False)
    has_vawc_or_child_abuse_indicators = Column(Boolean, default=False, nullable=False)
    proceeding_origin = Column(Text, default="new_complaint", nullable=False)
    has_juridical_entity_party = Column(Boolean, default=False, nullable=False)
    public_officer_involved = Column(Boolean, default=False, nullable=False)
    public_officer_official_function = Column(Boolean, default=False, nullable=False)
    no_private_offended_party = Column(Boolean, default=False, nullable=False)
    offense_classification = Column(Text, default="", nullable=False)
    penalty_lookup_required = Column(Boolean, default=False, nullable=False)
    real_property_involved = Column(Boolean, default=False, nullable=False)
    real_property_barangay = Column(Text, default="", nullable=False)
    real_property_city_municipality = Column(Text, default="", nullable=False)
    real_property_in_different_city_municipality = Column(Boolean, default=False, nullable=False)
    parties_in_different_city_municipality = Column(Boolean, default=False, nullable=False)
    parties_in_adjoining_barangays = Column(Boolean, default=False, nullable=False)
    mutual_agreement_to_kp = Column(Boolean, default=False, nullable=False)
    respondent_barangay = Column(Text, default="", nullable=False)
    respondent_city_municipality = Column(Text, default="", nullable=False)
    incident_venue_basis = Column(Text, default="same_barangay", nullable=False)
    workplace_or_school_dispute = Column(Boolean, default=False, nullable=False)
    workplace_or_school_barangay = Column(Text, default="", nullable=False)
    workplace_or_school_city_municipality = Column(Text, default="", nullable=False)
    accused_under_detention = Column(Boolean, default=False, nullable=False)
    liberty_or_habeas_issue = Column(Boolean, default=False, nullable=False)
    provisional_remedy_needed = Column(Boolean, default=False, nullable=False)
    statute_limitations_urgent = Column(Boolean, default=False, nullable=False)
    minor_or_incompetent_party = Column(Boolean, default=False, nullable=False)
    next_of_kin_assistant_name = Column(Text, default="", nullable=False)
    next_of_kin_is_lawyer = Column(Boolean, default=False, nullable=False)
    indigenous_community_dispute = Column(Boolean, default=False, nullable=False)
    same_indigenous_community = Column(Boolean, default=False, nullable=False)
    indigenous_process_agreed = Column(Boolean, default=False, nullable=False)
    sensitivity_level = Column(Text, default="normal", nullable=False)
    recording_consent_confirmed = Column(Boolean, default=False, nullable=False)
    hearing_consent_confirmed = Column(Boolean, default=False, nullable=False)
    retention_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ExtractedEntities(Base):
    __tablename__ = "extracted_entities"

    id = Column(Integer, primary_key=True, index=True)
    transcript_id = Column(Integer, ForeignKey("transcripts.id"), nullable=True, index=True)
    entities_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class XAITrace(Base):
    __tablename__ = "xai_traces"

    id = Column(Integer, primary_key=True, index=True)
    trace_json = Column(JSON, nullable=False)
    trace_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CaseAnalysis(Base):
    __tablename__ = "case_analyses"

    id = Column(Integer, primary_key=True, index=True)
    transcript_id = Column(Integer, ForeignKey("transcripts.id"), nullable=True, index=True)
    case_information_id = Column(Integer, ForeignKey("case_information.id"), nullable=False)
    extracted_entities_id = Column(Integer, ForeignKey("extracted_entities.id"), nullable=False)
    xai_trace_id = Column(Integer, ForeignKey("xai_traces.id"), nullable=False)
    detected_keywords_json = Column(JSON, nullable=False)
    rule_results_json = Column(JSON, nullable=False)
    jurisdiction_decision = Column(Text, nullable=False)
    exclusion_ground = Column(Text, nullable=False)
    confidence_level = Column(Text, nullable=False)
    missing_fields_json = Column(JSON, nullable=False)
    recommended_next_action = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WorkflowDraft(Base):
    __tablename__ = "workflow_drafts"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Text, nullable=False, unique=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(Text, default="active", nullable=False, index=True)
    active_step = Column(Integer, default=1, nullable=False)
    max_unlocked_step = Column(Integer, default=1, nullable=False)
    case_id = Column(Text, default="", nullable=False, index=True)
    transcript_id = Column(Integer, ForeignKey("transcripts.id"), nullable=True, index=True)
    case_analysis_id = Column(Integer, ForeignKey("case_analyses.id"), nullable=True, index=True)
    audio_filename = Column(Text, default="", nullable=False)
    audio_duration_seconds = Column(Float, nullable=True)
    audio_upload_token = Column(Text, default="", nullable=False)
    payload_json = Column(JSON, nullable=False)
    revision = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class KPResearchDataset(Base):
    __tablename__ = "kp_research_dataset"

    audio_id = Column(Text, primary_key=True, index=True)
    barangay_name = Column(Text, nullable=False)
    city_municipality = Column(Text, nullable=False)
    case_year = Column(Integer, nullable=True)
    case_type = Column(Text, nullable=False)
    dispute_category = Column(Text, nullable=False)
    complainant_residency = Column(Text, nullable=True)
    respondent_residency = Column(Text, nullable=True)
    debt_amount_php = Column(Float, nullable=True)
    penalty_years_max = Column(Float, nullable=True)
    vawc_trigger = Column(Boolean, default=False, nullable=False)
    speaker_count = Column(Integer, nullable=True)
    emotion_tension = Column(Float, nullable=True)
    covered_under_kp = Column(Boolean, default=False, nullable=False)
    kp_exclusion_ground = Column(Text, nullable=False)
    jurisdiction_decision = Column(Text, nullable=False)
    processing_time_min = Column(Float, nullable=True)
    form_accuracy_pct = Column(Float, nullable=True)
    xai_trace_length = Column(Integer, nullable=True)


class Phase3CaseRoute(Base):
    __tablename__ = "phase3_case_routes"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Text, nullable=False, index=True)
    is_sensitive = Column(Boolean, default=False, nullable=False)
    sensitive_category = Column(Text, nullable=False)
    recommended_route = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    matched_keywords = Column(JSON, nullable=False)
    confidence_level = Column(Text, nullable=False)
    blocking_mediation = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Text, nullable=False, index=True)
    referral_type = Column(Text, nullable=False)
    destination = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    matched_keywords = Column(JSON, nullable=False)
    xai_reference = Column(JSON, nullable=False)
    status = Column(Text, default="pending", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class MediationEligibility(Base):
    __tablename__ = "mediation_eligibility"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Text, nullable=False, index=True)
    eligible_for_mediation = Column(Boolean, default=False, nullable=False)
    reason = Column(Text, nullable=False)
    required_action = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MediationSuggestion(Base):
    __tablename__ = "mediation_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Text, nullable=False, index=True)
    dispute_category = Column(Text, nullable=False)
    suggestions_json = Column(JSON, nullable=False)
    xai_explanation_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Hearing(Base):
    __tablename__ = "hearings"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Text, nullable=False, index=True)
    hearing_type = Column(Text, nullable=False)
    scheduled_date = Column(Text, nullable=False)
    scheduled_time = Column(Text, nullable=False)
    location = Column(Text, nullable=False)
    assigned_lupon_member = Column(Text, nullable=False)
    status = Column(Text, default="scheduled", nullable=False)
    notes = Column(Text, default="", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Text, nullable=False, index=True)
    file_name = Column(Text, nullable=False)
    file_type = Column(Text, nullable=False)
    file_path = Column(Text, nullable=False)
    ocr_text = Column(Text, default="", nullable=False)
    extracted_entities_json = Column(JSON, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EmotionAnalysis(Base):
    __tablename__ = "emotion_analysis"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Text, nullable=False, index=True)
    emotion_label = Column(Text, nullable=False)
    tension_score = Column(Float, default=0, nullable=False)
    detected_terms = Column(JSON, nullable=False)
    mediation_advice = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Text, nullable=False, index=True)
    action = Column(Text, nullable=False)
    actor = Column(Text, default="system", nullable=False)
    actor_user_id = Column(Integer, nullable=True, index=True)
    actor_role = Column(Text, default="", nullable=False)
    ip_address = Column(Text, default="", nullable=False)
    user_agent = Column(Text, default="", nullable=False)
    resource_type = Column(Text, default="", nullable=False)
    resource_id = Column(Text, default="", nullable=False)
    risk_level = Column(Text, default="low", nullable=False)
    details_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False, unique=True, index=True)
    display_name = Column(Text, nullable=False)
    permissions_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(Text, nullable=False, unique=True, index=True)
    full_name = Column(Text, nullable=False)
    role_name = Column(Text, ForeignKey("roles.name"), nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login_at = Column(DateTime, nullable=True)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_token_hash = Column(Text, nullable=False, unique=True, index=True)
    csrf_token_hash = Column(Text, nullable=False)
    ip_address = Column(Text, default="", nullable=False)
    user_agent = Column(Text, default="", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(Text, nullable=False, index=True)
    ip_address = Column(Text, default="", nullable=False)
    user_agent = Column(Text, default="", nullable=False)
    success = Column(Boolean, default=False, nullable=False)
    reason = Column(Text, default="", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(Text, nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class BackupRecord(Base):
    __tablename__ = "backup_records"

    id = Column(Integer, primary_key=True, index=True)
    backup_id = Column(Text, nullable=False, unique=True, index=True)
    file_path = Column(Text, nullable=False)
    backup_type = Column(Text, default="manual", nullable=False)
    manifest_json = Column(JSON, nullable=False)
    checksum = Column(Text, nullable=False)
    status = Column(Text, default="created", nullable=False)
    created_by = Column(Text, default="system", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    verified_at = Column(DateTime, nullable=True)


class Phase3OfficialDecision(Base):
    __tablename__ = "phase3_official_decisions"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Text, nullable=False, index=True)
    system_recommendation = Column(Text, nullable=False)
    official_decision = Column(Text, nullable=False)
    official_notes = Column(Text, default="", nullable=False)
    approved_by = Column(Text, nullable=False)
    approved_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Phase4FormPacket(Base):
    __tablename__ = "phase4_form_packets"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Text, nullable=False, index=True)
    source_phase3_action = Column(Text, nullable=False)
    selected_forms_json = Column(JSON, nullable=False)
    generated_form_count = Column(Integer, default=0, nullable=False)
    missing_fields_json = Column(JSON, nullable=False)
    validation_status = Column(Text, nullable=False)
    form_accuracy_pct = Column(Float, default=0, nullable=False)
    processing_time_min = Column(Float, default=0, nullable=False)
    generated_by = Column(Text, nullable=False)
    approved_by = Column(Text, default="", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    approved_at = Column(DateTime, nullable=True)


class Phase4GeneratedForm(Base):
    __tablename__ = "phase4_generated_forms"

    id = Column(Integer, primary_key=True, index=True)
    packet_id = Column(Integer, ForeignKey("phase4_form_packets.id"), nullable=False, index=True)
    case_id = Column(Text, nullable=False, index=True)
    form_id = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    purpose = Column(Text, nullable=False)
    file_path = Column(Text, nullable=False)
    field_values_json = Column(JSON, nullable=False)
    missing_fields_json = Column(JSON, nullable=False)
    validation_status = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Phase5ValidationCase(Base):
    __tablename__ = "phase5_validation_cases"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Text, nullable=False, unique=True, index=True)
    analysis_id = Column(Integer, ForeignKey("case_analyses.id"), nullable=False, index=True)
    audio_id = Column(Text, nullable=True, index=True)
    dataset_split = Column(Text, default="validation", nullable=False)
    speaker_count = Column(Integer, nullable=True)
    speaker_gender_mix = Column(Text, default="unspecified", nullable=False)
    audio_quality = Column(Text, default="unspecified", nullable=False)
    manual_processing_time_min = Column(Float, nullable=True)
    system_processing_time_min = Column(Float, nullable=True)
    notes = Column(Text, default="", nullable=False)
    imported_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Phase5GroundTruth(Base):
    __tablename__ = "phase5_ground_truth"

    id = Column(Integer, primary_key=True, index=True)
    validation_case_id = Column(Integer, ForeignKey("phase5_validation_cases.id"), nullable=False, unique=True, index=True)
    expected_covered_under_kp = Column(Boolean, nullable=True)
    expected_jurisdiction_decision = Column(Text, default="", nullable=False)
    expected_exclusion_ground = Column(Text, default="", nullable=False)
    expected_sensitive_case = Column(Boolean, nullable=True)
    expected_referral_route = Column(Text, default="", nullable=False)
    expected_mediation_eligible = Column(Boolean, nullable=True)
    expected_form_ids = Column(JSON, default=list, nullable=False)
    expected_keywords = Column(JSON, default=list, nullable=False)
    expected_speaker_count = Column(Integer, nullable=True)
    reference_transcript = Column(Text, default="", nullable=False)
    reviewer_name = Column(Text, default="", nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Phase5EvaluationResult(Base):
    __tablename__ = "phase5_evaluation_results"

    id = Column(Integer, primary_key=True, index=True)
    validation_case_id = Column(Integer, ForeignKey("phase5_validation_cases.id"), nullable=False, index=True)
    jurisdiction_correct = Column(Boolean, nullable=True)
    exclusion_correct = Column(Boolean, nullable=True)
    sensitive_case_correct = Column(Boolean, nullable=True)
    referral_correct = Column(Boolean, nullable=True)
    mediation_correct = Column(Boolean, nullable=True)
    forms_correct = Column(Boolean, nullable=True)
    speaker_count_correct = Column(Boolean, nullable=True)
    overall_correct = Column(Boolean, nullable=True)
    keyword_precision = Column(Float, nullable=True)
    keyword_recall = Column(Float, nullable=True)
    form_accuracy_pct = Column(Float, nullable=True)
    compliance_score = Column(Float, nullable=True)
    system_processing_time_min = Column(Float, nullable=True)
    manual_processing_time_min = Column(Float, nullable=True)
    time_saved_min = Column(Float, nullable=True)
    time_saved_pct = Column(Float, nullable=True)
    metrics_json = Column(JSON, nullable=False)
    errors_json = Column(JSON, nullable=False)
    evaluated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Phase5ComplianceReview(Base):
    __tablename__ = "phase5_compliance_reviews"

    id = Column(Integer, primary_key=True, index=True)
    validation_case_id = Column(Integer, ForeignKey("phase5_validation_cases.id"), nullable=False, unique=True, index=True)
    consent_confirmed = Column(Boolean, default=False, nullable=False)
    transcript_anonymized = Column(Boolean, default=False, nullable=False)
    official_decision_saved = Column(Boolean, default=False, nullable=False)
    generated_forms_reviewed = Column(Boolean, default=False, nullable=False)
    audit_trail_complete = Column(Boolean, default=False, nullable=False)
    sensitive_case_referred = Column(Boolean, default=False, nullable=False)
    reviewer_name = Column(Text, default="", nullable=False)
    notes = Column(Text, default="", nullable=False)
    compliance_score = Column(Float, default=0, nullable=False)
    reviewed_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Phase5ExperimentRun(Base):
    __tablename__ = "phase5_experiment_runs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)
    case_count = Column(Integer, default=0, nullable=False)
    metrics_json = Column(JSON, nullable=False)
    created_by = Column(Text, default="researcher", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
