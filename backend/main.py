import shutil
import subprocess
import hashlib
from datetime import datetime
from difflib import SequenceMatcher
import os
from pathlib import Path
import re
from typing import Any, List, Literal
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from auth_schemas import (
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    UserCreateRequest,
    UserPasswordRequest,
    UserResponse,
    UserStatusRequest,
    UserUpdateRequest,
)
from auth_service import (
    AuthContext,
    authenticate_request,
    create_user,
    login,
    logout,
    restore_csrf_token,
    seed_roles_and_dev_admin,
    serialize_user,
    update_user,
    update_user_password,
    update_user_status,
    user_payload,
)
from audio_utils import convert_to_wav, wav_duration_seconds
from backup_service import BackupService
from completed_transcript_pdf import CompletedTranscriptPdfService
from database import Base, SessionLocal, comparison_metrics_from_counts, engine, migrate_database
from diarization import diarize_audio, has_diarization_token
from keyword_detector import detect_sensitive_keywords
from kp_cases_importer import import_kp_cases_workbook, workbook_summary
from legal_ner import MANILA_TIMEZONE, apply_authoritative_case_entities, extract_legal_entities
from merge import merge_transcript_and_speakers
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
    Phase4FormPacket,
    Phase4GeneratedForm,
    Phase5ValidationCase,
    PhraseCorrection,
    Referral,
    Transcript,
    User,
    WorkflowDraft,
    XAITrace,
)
from phase3_schemas import (
    EvidenceUpdateRequest,
    HearingCreateRequest,
    HearingUpdateRequest,
    OfficialDecisionRequest,
    ReferralCreateRequest,
    ReferralUpdateRequest,
)
from phase3_services import (
    EvidenceFileService,
    EmotionAnalysisService,
    HearingService,
    MediationEligibilityService,
    MediationSuggestionService,
    Phase3DashboardService,
    ReferralService,
    SensitiveCaseRoutingService,
    append_audit_log,
    get_phase2_bundle,
    serialize_evidence_record,
    serialize_model,
)
from phase4_schemas import (
    Phase4GeneratePacketRequest,
    Phase4PacketResponse,
    Phase4RecommendationResponse,
    Phase4TemplateResponse,
)
from phase4_services import Phase4FormService
from phase5_schemas import (
    Phase5ComplianceReviewRequest,
    Phase5EvaluationResponse,
    Phase5ExperimentRunRequest,
    Phase5ExperimentRunResponse,
    Phase5FinalizedWorkflowImportResponse,
    Phase5GroundTruthRequest,
    Phase5ImportCaseRequest,
    Phase5ImportableWorkflowResponse,
    Phase5MetricsResponse,
    Phase5ValidationCaseResponse,
)
from phase5_services import Phase5ValidationService
from rule_engine import evaluate_jurisdiction
from schemas import (
    AnalyzeCaseRequest,
    AnalyzeCaseResponse,
    CaseAnalysisSummary,
    SaveCaseAnalysisRequest,
    SaveCaseAnalysisResponse,
)
from transcript_normalizer import normalize_segments
from transcribe import transcribe_audio
from xai_trace import build_xai_trace


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
TRANSCRIPT_DIR = BASE_DIR / "transcripts"
EVIDENCE_DIR = BASE_DIR / "evidence_uploads"
GENERATED_FORMS_DIR = BASE_DIR / "generated_forms"
CONSENT_DIR = BASE_DIR / "consent_uploads"
KP_FORMS_DIR = BASE_DIR.parent / "docs" / "KP_Updated_Forms"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))

UPLOAD_DIR.mkdir(exist_ok=True)
TRANSCRIPT_DIR.mkdir(exist_ok=True)
EVIDENCE_DIR.mkdir(exist_ok=True)
GENERATED_FORMS_DIR.mkdir(exist_ok=True)
CONSENT_DIR.mkdir(exist_ok=True)


def kp_form_id(file_path: Path) -> str:
    return file_path.stem.lower().replace(" ", "-")


def safe_upload_name(filename: str) -> str:
    name = Path(filename).name.strip()
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:140] or "upload.bin"


def get_kp_form_files() -> list[Path]:
    if not KP_FORMS_DIR.exists():
        return []
    def sort_key(path: Path) -> tuple[int, str]:
        match = re.search(r"KP FORM (\d+)(?:-([A-Z]))?", path.stem, flags=re.IGNORECASE)
        if not match:
            return (999, path.stem)
        return (int(match.group(1)), match.group(2) or "")

    return sorted(KP_FORMS_DIR.glob("KP FORM *.pdf"), key=sort_key)

if os.getenv("APP_ENV", "development").strip().lower() != "production":
    Base.metadata.create_all(bind=engine)
    migrate_database()
with SessionLocal() as seed_db:
    seed_roles_and_dev_admin(seed_db)

app = FastAPI(title="JUSTICE-KP Production API", version="6.0.0")


def configured_origins() -> list[str]:
    configured = os.getenv("ALLOWED_ORIGINS", "")
    if configured.strip():
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


def cors_headers_for_request(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin", "")
    if origin and origin in configured_origins():
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }
    return {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Document-ID", "X-Document-SHA256", "X-Generated-At"],
)


PROTECTED_PREFIXES = (
    "/api",
    "/upload",
    "/save-transcript",
    "/transcript-corrections",
    "/transcripts",
    "/analyze-case",
    "/save-case-analysis",
    "/case-analyses",
    "/case-analysis",
)
PUBLIC_PATHS = {"/", "/api/auth/login", "/api/system/shutdown"}


def permission_for_request(method: str, path: str) -> str | None:
    if path.startswith("/api/admin/users"):
        return "users.manage"
    if path.startswith("/api/admin/backups"):
        return "backup.manage"
    if path.startswith("/api/dashboard"):
        return "case.read"
    if path.startswith("/api/management/cases") or path.startswith("/api/cases"):
        return "case.read"
    if path.startswith("/api/workflow"):
        return "case.write" if method != "GET" else "case.read"
    if path.startswith("/api/phase5"):
        return "phase5.evaluate" if method != "GET" else "reports.export"
    if path.startswith("/api/phase4/generated-forms") or path.startswith("/api/kp-forms"):
        return "forms.download"
    if path.startswith("/api/phase3/evidence/") and path.endswith("/download"):
        return "evidence.download"
    if path.startswith("/api/phase4"):
        return "phase4.generate" if method != "GET" else "case.read"
    if path.startswith("/api/phase3"):
        return "phase3.decide" if method != "GET" else "case.read"
    if path.startswith("/api/phase2") or path == "/analyze-case":
        return "phase2.analyze"
    if path == "/save-case-analysis":
        return "case.write"
    if path in {"/upload", "/save-transcript", "/transcript-corrections/learn"}:
        return "transcript.write"
    if path == "/transcripts" or path.startswith("/transcripts/"):
        return "transcript.read" if method == "GET" else "transcript.write"
    if path.startswith("/case-analysis") or path == "/case-analyses":
        return "case.read"
    return None


@app.middleware("http")
async def production_security_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    protected = path in PUBLIC_PATHS or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)
    if protected and path not in PUBLIC_PATHS:
        db = SessionLocal()
        try:
            require_csrf = request.method in {"POST", "PUT", "PATCH", "DELETE"}
            try:
                context = authenticate_request(db, request, require_csrf=require_csrf)
                permission = permission_for_request(request.method, path)
                if permission and permission not in context.permissions:
                    raise HTTPException(status_code=403, detail="You do not have permission for this action.")
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=cors_headers_for_request(request),
                )
        finally:
            db.close()

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "microphone=(self)"
    return response


class TranscriptSegment(BaseModel):
    speaker: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    confidence: float | None = Field(default=None, ge=0, le=1)


class SaveTranscriptRequest(BaseModel):
    content: str = Field(min_length=1)
    segments: List[TranscriptSegment] = Field(default_factory=list)
    edited_segments: List[TranscriptSegment] = Field(default_factory=list)
    provider: str = ""
    recording_type: str = ""
    expected_speakers: int | None = None
    asr_confidence: float | None = Field(default=None, ge=0, le=1)
    diarization_quality: float | None = Field(default=None, ge=0, le=1)
    accuracy_metrics: dict[str, Any] = Field(default_factory=dict)
    workflow_id: str = ""
    case_id: str = ""
    transcript_id: int | None = Field(default=None, ge=1)
    save_context: Literal["intake", "hearing", "standalone"] = "standalone"


class LearnTranscriptCorrectionsRequest(BaseModel):
    content: str = Field(min_length=1)
    segments: List[TranscriptSegment] = Field(default_factory=list)


class WorkflowDraftCreateRequest(BaseModel):
    active_step: int = Field(default=1, ge=1, le=8)
    max_unlocked_step: int = Field(default=1, ge=1, le=8)
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkflowDraftUpdateRequest(BaseModel):
    revision: int = Field(ge=1)
    active_step: int = Field(ge=1, le=8)
    max_unlocked_step: int = Field(ge=1, le=8)
    status: str = Field(default="active")
    case_id: str = ""
    transcript_id: int | None = None
    case_analysis_id: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkflowPhase2AnalysisRequest(AnalyzeCaseRequest):
    revision: int | None = Field(default=None, ge=1)


class WorkflowFinalizeIntakeRequest(BaseModel):
    revision: int | None = Field(default=None, ge=1)
    generated_by: str = Field(default="Barangay Official", min_length=1)
    approved_by: str = ""
    field_overrides: dict[str, Any] = Field(default_factory=dict)
    regenerate: bool = False


class WorkflowFinalizeOutcomeRequest(BaseModel):
    revision: int | None = Field(default=None, ge=1)
    outcome: str = Field(min_length=1, max_length=160)


class WorkflowReferralActionRequest(BaseModel):
    revision: int | None = Field(default=None, ge=1)
    action: Literal["complete_and_advance", "cancel_referral", "cancel_case"]
    reason: str = Field(default="", max_length=1000)


ROLE_KEYWORDS = {
    "barangay_secretary": (
        ("desk officer", 14),
        ("barangay secretary", 14),
        ("kagawad", 14),
        ("secretary", 8),
        ("mediator", 12),
        ("tagapamagitan", 12),
        ("lupon member", 12),
        ("lupon", 8),
        ("punong barangay", 12),
        ("kapitan", 10),
        ("chairman", 10),
    ),
    "complainant": (
        ("magrereklamo po ako", 18),
        ("magrereklamo ako", 16),
        ("ako po ang nagrereklamo", 18),
        ("ako ang nagrereklamo", 16),
        ("ako po si complainant", 18),
        ("complainant", 12),
        ("nagrereklamo", 10),
        ("magrereklamo", 10),
        ("reklamante", 12),
    ),
    "respondent": (
        ("respondent inirereklamo", 20),
        ("respondent nirereklamo", 18),
        ("ako po ang inirereklamo", 18),
        ("ako ang inirereklamo", 16),
        ("ako po ang respondent", 18),
        ("ako ang respondent", 16),
        ("respondent", 12),
        ("inirereklamo", 14),
        ("nirereklamo", 12),
        ("iniirereklamo", 12),
        ("sinusumbong", 10),
    ),
}


ROLE_LABELS = {
    "barangay_secretary": "Barangay Secretary/Mediator",
    "complainant": "Complainant",
    "respondent": "Respondent",
}

UNSAFE_GLOBAL_CORRECTION_TOKENS = {
    "ako",
    "ang",
    "at",
    "ay",
    "ito",
    "mga",
    "na",
    "naman",
    "nang",
    "ng",
    "opo",
    "po",
    "sa",
    "si",
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_auth_context(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    return authenticate_request(db, request, require_csrf=False)


def get_learned_corrections(db: Session) -> dict[str, str]:
    corrections = db.query(PhraseCorrection).all()
    reciprocal_pairs = {
        (correction.wrong_phrase.casefold(), correction.correct_phrase.casefold())
        for correction in corrections
        if correction.wrong_phrase and correction.correct_phrase
    }
    return {
        correction.wrong_phrase: correction.correct_phrase
        for correction in corrections
        if correction.wrong_phrase and correction.correct_phrase
        and not (
            len(correction.wrong_phrase.split()) == 1
            and len(correction.correct_phrase.split()) == 1
            and (
                correction.wrong_phrase.casefold() in UNSAFE_GLOBAL_CORRECTION_TOKENS
                or correction.correct_phrase.casefold() in UNSAFE_GLOBAL_CORRECTION_TOKENS
            )
        )
        and (correction.correct_phrase.casefold(), correction.wrong_phrase.casefold()) not in reciprocal_pairs
    }


def parse_edited_transcript(content: str) -> List[TranscriptSegment]:
    edited_segments: List[TranscriptSegment] = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = re.match(r"^([^:]{1,80})\s*:\s*(.+)$", line)
        if match:
            speaker = re.sub(r"\s+", " ", match.group(1).strip())
            edited_segments.append(
                TranscriptSegment(
                    speaker=speaker.title() if re.match(r"^speaker\s+\d+$", speaker, flags=re.IGNORECASE) else speaker,
                    start=0,
                    end=0,
                    text=match.group(2).strip(),
                )
            )
        elif edited_segments:
            edited_segments[-1].text = f"{edited_segments[-1].text} {line}".strip()

    return edited_segments


def format_transcript_segments(segments: List[TranscriptSegment]) -> str:
    # Keep each speaker turn visually distinct in both stored raw transcripts
    # and any client that renders the plain text with preserved whitespace.
    return "\n\n".join(f"{segment.speaker}: {segment.text}" for segment in segments)


def clean_correction_token(token: str) -> str:
    return token.strip(" \t\r\n.,!?;:\"'()[]{}")


def transcript_words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower(), flags=re.UNICODE)


def segment_words(segments: List[TranscriptSegment]) -> list[str]:
    words: list[str] = []
    for segment in segments:
        words.extend(transcript_words(segment.text))
    return words


def correction_summary(
    original_segments: List[TranscriptSegment],
    edited_segments: List[TranscriptSegment],
    edited_content: str,
) -> dict[str, Any]:
    original_words = segment_words(original_segments)
    edited_words = segment_words(edited_segments) if edited_segments else transcript_words(edited_content)
    if not original_words:
        comparison_metrics = comparison_metrics_from_counts(0, len(edited_words), 0)
        return {
            "original_word_count": 0,
            "edited_word_count": len(edited_words),
            "correction_count": 0,
            "manual_correction_rate": 0.0,
            **comparison_metrics,
        }

    matcher = SequenceMatcher(None, original_words, edited_words)
    correction_count = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            correction_count += max(i2 - i1, j2 - j1)
    denominator = max(len(original_words), 1)
    reference_denominator = max(len(edited_words), 1)
    word_error_rate = correction_count / reference_denominator
    return {
        "original_word_count": len(original_words),
        "edited_word_count": len(edited_words),
        "reference_word_count": len(edited_words),
        "correction_count": correction_count,
        "manual_correction_rate": round(min(correction_count / denominator, 1.0), 4),
        # The explicitly saved, human-edited transcript is the reference for
        # these agreement metrics. This is not an independent ASR benchmark.
        "word_error_rate": round(word_error_rate, 4),
        "raw_word_accuracy": round(max(0.0, 1.0 - word_error_rate), 4),
        "edited_word_accuracy": 1.0 if edited_words else None,
    }


def normalized_correction_rate(transcript: Transcript) -> float | None:
    if transcript.original_word_count <= 0:
        return 0.0
    if transcript.manual_correction_rate is None:
        return None
    return round(min(max(float(transcript.manual_correction_rate), 0.0), 1.0), 4)


def correction_records(corrections: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"wrong": wrong, "corrected": corrected} for wrong, corrected in corrections]


def average_segment_confidence(segments: list[dict] | List[TranscriptSegment]) -> float | None:
    confidences = []
    for segment in segments:
        value = segment.get("confidence") if isinstance(segment, dict) else segment.confidence
        if value is not None:
            confidences.append(float(value))
    if not confidences:
        return None
    return round(sum(confidences) / len(confidences), 4)


def transcript_quality_metrics(
    segments: list[dict],
    expected_speakers: int | None,
    warnings: list[str],
) -> dict[str, Any]:
    detected_speakers = len({str(segment.get("speaker") or "") for segment in segments if segment.get("speaker")})
    confidence = average_segment_confidence(segments)
    warning_text = " ".join(warnings).lower()
    if not segments:
        diarization_quality = 0.0
    elif "speaker diarization failed" in warning_text or "speaker 1 fallback" in warning_text:
        diarization_quality = 0.25
    elif expected_speakers in {2, 3}:
        diarization_quality = 1.0 if detected_speakers == expected_speakers else max(0.4, detected_speakers / expected_speakers)
    else:
        diarization_quality = 0.8 if detected_speakers else 0.0
    return {
        "asr_confidence": confidence,
        "diarization_quality": round(diarization_quality, 4),
        "detected_speakers": detected_speakers,
    }


def append_recording_quality_warnings(
    segments: list[dict],
    expected_speakers: int | None,
    duration_seconds: float | None,
    warnings: list[str],
) -> None:
    if expected_speakers not in {2, 3}:
        return

    word_count = sum(len(str(segment.get("text") or "").split()) for segment in segments)
    speech_seconds = round(
        sum(max(0.0, float(segment.get("end") or 0) - float(segment.get("start") or 0)) for segment in segments),
        2,
    )
    minimum_words = expected_speakers * 4
    minimum_speech_seconds = expected_speakers * 3
    if (duration_seconds is not None and duration_seconds < 15) or word_count < minimum_words or speech_seconds < minimum_speech_seconds:
        warnings.append(
            "Not enough distinct speech for reliable speaker separation. "
            f"The recording contains about {word_count} recognized words across {speech_seconds:.1f} seconds of speech. "
            f"For {expected_speakers} speakers, record at least 20 seconds and let each person speak separately for 5-10 seconds."
        )


def speaker_count_for_recording_type(recording_type: str, speaker_count: int) -> int:
    normalized = recording_type.strip().lower().replace("-", "_")
    if normalized in {"blotter_case", "case", "blotter"}:
        return 2
    if normalized in {"blotter_hearing", "hearing", "mediation"}:
        return 3
    if speaker_count in {2, 3}:
        return speaker_count
    return 3


def role_order_for_recording_type(recording_type: str) -> list[str]:
    expected_count = speaker_count_for_recording_type(recording_type, 0)
    if expected_count == 2:
        return ["barangay_secretary", "complainant"]
    return ["barangay_secretary", "complainant", "respondent"]


def role_label_for_recording_type(role: str | None, recording_type: str, fallback: str) -> str:
    return ROLE_LABELS.get(role or "", fallback)


def score_role_text(text: str, role: str) -> int:
    normalized = re.sub(r"[^\w]+", " ", text.casefold()).strip()
    padded_text = f" {normalized} "
    score = 0
    for phrase, weight in ROLE_KEYWORDS[role]:
        normalized_phrase = re.sub(r"[^\w]+", " ", phrase.casefold()).strip()
        score += padded_text.count(f" {normalized_phrase} ") * weight
    return score


def assign_role_labels(segments: list[dict], recording_type: str) -> list[dict]:
    if not segments:
        return []

    role_order = role_order_for_recording_type(recording_type)
    speaker_text: dict[str, str] = {}
    for segment in segments:
        speaker = str(segment.get("speaker") or "Speaker 1")
        speaker_text[speaker] = f"{speaker_text.get(speaker, '')} {segment.get('text', '')}".strip()

    speaker_order = list(speaker_text.keys())
    assignments: dict[str, str] = {}
    assigned_roles: set[str] = set()

    scored = []
    for speaker, text in speaker_text.items():
        for role in role_order:
            score = score_role_text(text, role)
            if score:
                scored.append((score, speaker, role))

    speaker_rank = {speaker: index for index, speaker in enumerate(speaker_order)}
    role_rank = {role: index for index, role in enumerate(role_order)}
    for _score, speaker, role in sorted(
        scored,
        key=lambda item: (-item[0], speaker_rank[item[1]], role_rank[item[2]]),
    ):
        if speaker in assignments or role in assigned_roles:
            continue
        assignments[speaker] = role
        assigned_roles.add(role)

    remaining_roles = [role for role in role_order if role not in assigned_roles]
    for speaker in speaker_order:
        if speaker not in assignments and remaining_roles:
            assignments[speaker] = remaining_roles.pop(0)

    # Diarization services can occasionally split one voice into an extra raw
    # speaker. Never leak that as "Speaker N" into a supported 2/3-person
    # workflow: collapse it to the best permitted role (or deterministic order
    # when the text contains no role phrase).
    for speaker in speaker_order:
        if speaker in assignments:
            continue
        role_scores = [(score_role_text(speaker_text[speaker], role), role) for role in role_order]
        best_score, best_role = max(
            role_scores,
            key=lambda item: (item[0], -role_rank[item[1]]),
        )
        assignments[speaker] = best_role if best_score else role_order[speaker_rank[speaker] % len(role_order)]

    return [
        {
            **segment,
            "speaker": role_label_for_recording_type(
                assignments.get(str(segment.get("speaker") or "")),
                recording_type,
                str(segment.get("speaker") or "Speaker 1"),
            ),
        }
        for segment in segments
    ]


def extract_phrase_corrections(
    original_segments: List[TranscriptSegment],
    edited_segments: List[TranscriptSegment],
) -> list[tuple[str, str]]:
    learned: list[tuple[str, str]] = []

    def learn_from_words(original_words: list[str], edited_words: list[str]) -> None:
        original_words = [word for word in original_words if word]
        edited_words = [word for word in edited_words if word]

        matcher = SequenceMatcher(None, original_words, edited_words)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "replace":
                continue

            wrong_phrase = " ".join(original_words[i1:i2]).strip()
            correct_phrase = " ".join(edited_words[j1:j2]).strip()
            wrong_word_count = len(wrong_phrase.split())
            correct_word_count = len(correct_phrase.split())

            if (
                not wrong_phrase
                or not correct_phrase
                or wrong_phrase.lower() == correct_phrase.lower()
                or wrong_word_count > 6
                or correct_word_count > 8
                or len(wrong_phrase) > 80
                or len(correct_phrase) > 100
            ):
                continue

            learned.append((wrong_phrase, correct_phrase))

    if len(original_segments) == len(edited_segments):
        for original, edited in zip(original_segments, edited_segments):
            if original.speaker.lower() != edited.speaker.lower():
                continue
            learn_from_words(
                [clean_correction_token(word) for word in original.text.split()],
                [clean_correction_token(word) for word in edited.text.split()],
            )

    # If the reviewer split or joined transcript lines, compare the complete
    # spoken text as a fallback. Speaker labels are excluded from this diff.
    if not learned and original_segments and edited_segments:
        learn_from_words(segment_words(original_segments), segment_words(edited_segments))

    return learned


def unique_phrase_corrections(corrections: list[tuple[str, str]]) -> list[tuple[str, str]]:
    unique: dict[str, tuple[str, str]] = {}
    ambiguous: set[str] = set()

    for wrong_phrase, correct_phrase in corrections:
        wrong_phrase = wrong_phrase.strip()
        correct_phrase = correct_phrase.strip()
        key = wrong_phrase.casefold()
        if not key or not correct_phrase:
            continue

        previous = unique.get(key)
        if previous and previous[1].casefold() != correct_phrase.casefold():
            # A single incorrect phrase mapping to two different reviewer edits
            # is unsafe to learn automatically.
            ambiguous.add(key)
            continue
        unique.setdefault(key, (wrong_phrase, correct_phrase))

    return [correction for key, correction in unique.items() if key not in ambiguous]


def save_phrase_corrections(
    db: Session,
    corrections: list[tuple[str, str]],
    *,
    commit: bool = True,
) -> int:
    saved_count = 0

    # SessionLocal uses autoflush=False. Deduplicating first prevents two
    # pending inserts for the same unique wrong_phrase in a single save.
    for wrong_phrase, correct_phrase in unique_phrase_corrections(corrections):
        existing = (
            db.query(PhraseCorrection)
            .filter(func.lower(PhraseCorrection.wrong_phrase) == wrong_phrase.lower())
            .first()
        )

        reciprocal = (
            db.query(PhraseCorrection)
            .filter(
                func.lower(PhraseCorrection.wrong_phrase) == correct_phrase.lower(),
                func.lower(PhraseCorrection.correct_phrase) == wrong_phrase.lower(),
            )
            .first()
        )
        if reciprocal:
            # Do not learn A -> B when B -> A already exists. Applying both
            # mappings would make future transcript normalization oscillate.
            continue

        if existing:
            if existing.correct_phrase != correct_phrase:
                existing.correct_phrase = correct_phrase
            existing.usage_count += 1
        else:
            db.add(
                PhraseCorrection(
                    wrong_phrase=wrong_phrase,
                    correct_phrase=correct_phrase,
                )
            )
        saved_count += 1

    if saved_count and commit:
        db.commit()

    return saved_count


def pct(part: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round((part / total) * 100, 1)


def month_label(value: datetime) -> str:
    return value.strftime("%b")


def format_activity_time(value: datetime | None) -> str:
    if not value:
        return "Just now"
    delta = datetime.utcnow() - value
    minutes = max(0, int(delta.total_seconds() // 60))
    if minutes < 1:
        return "Just now"
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def dashboard_summary(db: Session, context: AuthContext | None = None) -> dict:
    analysis_query = db.query(CaseAnalysis)
    if isinstance(context, AuthContext):
        draft_query = db.query(WorkflowDraft).filter(WorkflowDraft.case_analysis_id.is_not(None))
        if "users.manage" not in context.permissions:
            draft_query = draft_query.filter(WorkflowDraft.owner_user_id == context.user.id)
        authorized_analysis_ids = {
            draft.case_analysis_id
            for draft in draft_query.all()
            if draft.case_analysis_id is not None
            and (
                "sensitive_case.read" in context.permissions
                or not _workflow_is_sensitive(db, draft)
            )
        }
        analysis_query = analysis_query.filter(CaseAnalysis.id.in_(authorized_analysis_ids))
    analyses = analysis_query.order_by(CaseAnalysis.created_at.asc()).all()
    case_info_by_id = {
        item.id: item
        for item in db.query(CaseInformation).all()
    }
    case_ids = [
        case_info_by_id[analysis.case_information_id].case_id
        for analysis in analyses
        if analysis.case_information_id in case_info_by_id
    ]
    total_cases = len(analyses)
    within_kp = sum(1 for item in analyses if item.jurisdiction_decision == "within_kp")
    referred_cases = sum(
        1
        for item in analyses
        if item.jurisdiction_decision in {"outside_kp", "refer_to_pnp_wcpc_or_authority"}
        or item.exclusion_ground not in {"", "none", "within_kp"}
    )
    official_decisions = (
        db.query(Phase3OfficialDecision)
        .filter(Phase3OfficialDecision.case_id.in_(case_ids))
        .all()
        if case_ids
        else []
    )
    decided_case_ids = {item.case_id for item in official_decisions}
    resolved_case_ids = decided_case_ids.intersection(case_ids)
    pending_cases = len(set(case_ids) - decided_case_ids)
    generated_form_count = int(
        db.query(func.coalesce(func.sum(Phase4FormPacket.generated_form_count), 0))
        .filter(Phase4FormPacket.case_id.in_(case_ids))
        .scalar()
        or 0
    ) if case_ids else 0
    eligibility_query = db.query(MediationEligibility).filter(MediationEligibility.case_id.in_(case_ids))
    eligibility_count = eligibility_query.count() if case_ids else 0
    eligible_count = eligibility_query.filter(MediationEligibility.eligible_for_mediation.is_(True)).count() if case_ids else 0

    decision_dates = {item.case_id: item.created_at for item in official_decisions}
    processing_days: list[float] = []
    for analysis in analyses:
        case_info = case_info_by_id.get(analysis.case_information_id)
        if not case_info:
            continue
        decided_at = decision_dates.get(case_info.case_id)
        if decided_at:
            processing_days.append(max(0, (decided_at - analysis.created_at).total_seconds() / 86400))

    settled_count = sum(
        1
        for item in official_decisions
        if any(word in item.official_decision.lower() for word in ("settlement", "settled", "mediation", "mediate"))
    )
    referral_records = db.query(Referral).filter(Referral.case_id.in_(case_ids)).count() if case_ids else 0

    recent_months = []
    now = datetime.utcnow()
    for offset in range(5, -1, -1):
        year = now.year
        month = now.month - offset
        while month <= 0:
            month += 12
            year -= 1
        count = sum(1 for item in analyses if item.created_at.year == year and item.created_at.month == month)
        recent_months.append({"label": datetime(year, month, 1).strftime("%b"), "count": count})

    category_counts: dict[str, int] = {}
    for analysis in analyses:
        case_info = case_info_by_id.get(analysis.case_information_id)
        if not case_info:
            continue
        label = case_info.dispute_category.replace("_", " ").title()
        category_counts[label] = category_counts.get(label, 0) + 1
    category_breakdown = [
        {"label": label, "count": count, "percentage": pct(count, total_cases) or 0}
        for label, count in sorted(category_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    ]

    heatmap = []
    daily_counts: list[int] = []
    for offset in range(34, -1, -1):
        target = now.date()
        target = target.fromordinal(target.toordinal() - offset)
        count = sum(1 for item in analyses if item.created_at.date() == target)
        daily_counts.append(count)
    max_daily = max(daily_counts) if daily_counts else 0
    for count in daily_counts:
        level = 1 if max_daily == 0 else max(1, min(5, int(round((count / max_daily) * 4)) + 1))
        heatmap.append(level)

    recent_routings = []
    routes = (
        db.query(Phase3CaseRoute)
        .filter(Phase3CaseRoute.case_id.in_(case_ids))
        .order_by(Phase3CaseRoute.created_at.desc())
        .limit(3)
        .all()
        if case_ids
        else []
    )
    for route in routes:
        recent_routings.append(
            {
                "case_id": route.case_id,
                "text": route.reason,
                "status": route.recommended_route,
                "tone": "red" if route.blocking_mediation else "green",
            }
        )

    system_logs = []
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.case_id.in_(case_ids))
        .order_by(AuditLog.created_at.desc())
        .limit(4)
        .all()
        if case_ids
        else []
    )
    for log in logs:
        action = log.action.replace("_", " ").title()
        label = f"{action} for {log.case_id}" if log.case_id else action
        system_logs.append({"label": label, "time": format_activity_time(log.created_at)})

    return {
        "metrics": {
            "resolution_rate_pct": pct(len(resolved_case_ids), total_cases),
            "average_processing_days": round(sum(processing_days) / len(processing_days), 1) if processing_days else None,
            "settlement_ratio": f"{settled_count}:{max(referral_records, 1)}" if settled_count else "0:0",
            "mediation_success_pct": pct(eligible_count, eligibility_count),
            "total_cases": total_cases,
            "pending_cases": pending_cases,
            "referred_cases": referred_cases,
            "generated_forms": generated_form_count,
        },
        "monthly_trend": recent_months,
        "settlement_referral_trend": {
            "settled": settled_count,
            "referred": referral_records,
        },
        "category_breakdown": category_breakdown,
        "kp_distribution": {
            "covered": within_kp,
            "referred": max(total_cases - within_kp, 0),
            "covered_pct": pct(within_kp, total_cases),
        },
        "activity_heatmap": heatmap,
        "recent_routings": recent_routings,
        "system_logs": system_logs,
        "generated_at": datetime.utcnow(),
    }


WORKFLOW_STAGE_DEFINITIONS = (
    (1, "Intake & Case Assessment", "Intake", (1, 2)),
    (2, "Summons & Hearing", "Hearing", (3, 4)),
    (3, "Analysis & Routing", "Review", (5, 6)),
    (4, "Resolution & Forms", "Outcome", (7,)),
)


def workflow_stage_details(active_step: int) -> dict[str, Any]:
    safe_step = min(7, max(1, active_step or 1))
    stage = next(
        (item for item in WORKFLOW_STAGE_DEFINITIONS if safe_step in item[3]),
        WORKFLOW_STAGE_DEFINITIONS[0],
    )
    return {
        "id": stage[0],
        "label": stage[1],
        "short_label": stage[2],
    }


def serialize_workflow_draft(draft: WorkflowDraft, owner: User | None = None) -> dict[str, Any]:
    payload = dict(draft.payload_json or {})
    if draft.audio_filename:
        payload["blotterAudioFilename"] = draft.audio_filename
        payload["blotterDurationSeconds"] = draft.audio_duration_seconds or 0
    return {
        "workflow_id": draft.workflow_id,
        "owner_user_id": draft.owner_user_id,
        "status": draft.status,
        "active_step": draft.active_step,
        "max_unlocked_step": draft.max_unlocked_step,
        "case_id": draft.case_id,
        "transcript_id": draft.transcript_id,
        "case_analysis_id": draft.case_analysis_id,
        "payload": payload,
        "revision": draft.revision,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
        "current_stage": workflow_stage_details(draft.active_step),
        "completion_percentage": 100 if draft.status == "completed" else round(min(7, max(1, draft.active_step)) / 7 * 100),
        "owner": (
            {
                "id": owner.id,
                "username": owner.username,
                "full_name": owner.full_name,
            }
            if owner
            else None
        ),
    }


def next_workflow_case_id(db: Session, year: int | None = None) -> str:
    case_year = year or datetime.utcnow().year
    pattern = re.compile(rf"^KP-{case_year}-(\d+)$", re.IGNORECASE)
    existing_ids = [row[0] for row in db.query(CaseInformation.case_id).all() if row[0]]
    for draft in db.query(WorkflowDraft).all():
        case_info = (draft.payload_json or {}).get("caseInformation") or {}
        if case_info.get("case_id"):
            existing_ids.append(str(case_info["case_id"]))

    sequence = max(
        (int(match.group(1)) for case_id in existing_ids if (match := pattern.match(case_id))),
        default=0,
    ) + 1
    return f"KP-{case_year}-{sequence:04d}"


def get_owned_workflow_draft(db: Session, workflow_id: str, context: AuthContext) -> WorkflowDraft:
    draft = db.query(WorkflowDraft).filter(WorkflowDraft.workflow_id == workflow_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Workflow draft was not found.")
    if draft.owner_user_id != context.user.id and "users.manage" not in context.permissions:
        raise HTTPException(status_code=404, detail="Workflow draft was not found.")
    return draft


def is_finalized_workflow(draft: WorkflowDraft) -> bool:
    payload = dict(draft.payload_json or {})
    return draft.status in {"completed", "cancelled"} and bool(
        payload.get("finalizedAt") and payload.get("outcome")
    )


def ensure_workflow_is_mutable(draft: WorkflowDraft) -> None:
    if is_finalized_workflow(draft):
        raise HTTPException(
            status_code=409,
            detail=(
                "This completed case is an immutable record. Its transcript can only be changed "
                "through a separately authorized retention action."
            ),
        )


def ensure_case_is_mutable(db: Session, case_id: str) -> None:
    for draft in db.query(WorkflowDraft).filter(WorkflowDraft.case_id == case_id).all():
        if is_finalized_workflow(draft):
            raise HTTPException(
                status_code=409,
                detail="This completed case is an immutable record and cannot receive new operational changes.",
            )


def ensure_workflow_revision(draft: WorkflowDraft, revision: int | None) -> None:
    if revision is not None and revision != draft.revision:
        raise HTTPException(status_code=409, detail="Workflow draft changed. Refresh before saving again.")


def analysis_to_payload(analysis: AnalyzeCaseResponse) -> dict[str, Any]:
    return analysis.model_dump(mode="json")


def skipped_panels_for_analysis(analysis: AnalyzeCaseResponse) -> list[int]:
    if analysis.detected_keywords.get("vawc_trigger"):
        return [3, 4, 5, 6]
    return [] if analysis.jurisdiction_decision == "within_kp" else [3, 4]


def workflow_has_vawc_trigger(payload: dict[str, Any]) -> bool:
    analysis = payload.get("phase2Analysis") or {}
    detected = analysis.get("detected_keywords") or {}
    case_information = payload.get("caseInformation") or {}
    return bool(
        detected.get("vawc_trigger")
        or case_information.get("has_vawc_or_child_abuse_indicators")
    )


def workflow_requires_referral(payload: dict[str, Any]) -> bool:
    analysis = payload.get("phase2Analysis") or {}
    decision = str(analysis.get("jurisdiction_decision") or "").strip().lower()
    return (
        workflow_has_vawc_trigger(payload)
        or bool(decision and decision != "within_kp")
        or bool(payload.get("phase3ReferralRequired"))
    )


def completed_workflow_referral(
    db: Session,
    draft: WorkflowDraft,
    payload: dict[str, Any],
) -> Referral | None:
    resolution = payload.get("referralResolution") or {}
    if not isinstance(resolution, dict) or resolution.get("status") != "completed":
        return None

    referral_id = resolution.get("referralId")
    if not isinstance(referral_id, int) or isinstance(referral_id, bool):
        return None

    return (
        db.query(Referral)
        .filter(
            Referral.id == referral_id,
            Referral.case_id == draft.case_id,
            Referral.status == "completed",
        )
        .first()
    )


CANCELLED_REFERRAL_OUTCOME = "Referral Cancelled - Case Closed After Official Review"


def cancelled_workflow_referral(
    db: Session,
    draft: WorkflowDraft,
    payload: dict[str, Any],
) -> Referral | None:
    resolution = payload.get("referralResolution") or {}
    if not isinstance(resolution, dict) or resolution.get("status") != "cancelled":
        return None

    referral_id = resolution.get("referralId")
    if not isinstance(referral_id, int) or isinstance(referral_id, bool):
        return None

    return (
        db.query(Referral)
        .filter(
            Referral.id == referral_id,
            Referral.case_id == draft.case_id,
            Referral.status == "cancelled",
        )
        .first()
    )


def referral_outcome_label(referral: Referral) -> str:
    referral_type = referral.referral_type.strip().lower()
    if referral_type == "vawc":
        return "Referred to WCPD / PNP"
    if referral_type == "mswdo":
        return "Referred to MSWDO / PNP"
    if referral_type == "court":
        return "Referred to Court / Proper Authority"
    return "Referred for Manual Review"


def launch_local_shutdown(backend_process_id: int) -> None:
    shutdown_script = BASE_DIR.parent / "scripts" / "stop_local_dev.ps1"
    if not shutdown_script.is_file():
        return
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(shutdown_script),
            "-BackendProcessId",
            str(backend_process_id),
        ],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
    )


@app.post("/api/system/shutdown")
def shutdown_local_system(request: Request, background_tasks: BackgroundTasks):
    app_environment = os.getenv("APP_ENV", "development").strip().lower()
    shutdown_enabled = os.getenv("ALLOW_LOCAL_SHUTDOWN", "false").strip().lower() == "true"
    if app_environment == "production" or not shutdown_enabled:
        raise HTTPException(status_code=404, detail="Local shutdown is not available in this environment.")

    loopback_hosts = {"127.0.0.1", "::1", "localhost"}
    client_host = request.client.host if request.client else ""
    request_host = (request.url.hostname or "").lower()
    if client_host not in loopback_hosts or request_host not in loopback_hosts:
        raise HTTPException(status_code=403, detail="Shutdown is restricted to this computer.")

    origin = request.headers.get("origin", "").rstrip("/").lower()
    allowed_origins = {"http://127.0.0.1:3000", "http://localhost:3000"}
    if origin and origin not in allowed_origins:
        raise HTTPException(status_code=403, detail="The shutdown request origin is not allowed.")

    background_tasks.add_task(launch_local_shutdown, os.getpid())
    return {"message": "JUSTICE-KP local frontend and backend are stopping."}


@app.get("/")
def root():
    return {"message": "JUSTICE-KP production backend is running"}


@app.post("/api/auth/login", response_model=LoginResponse)
def auth_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    return login(db, request, response, payload)


@app.post("/api/auth/logout")
def auth_logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    context = authenticate_request(db, request, require_csrf=False)
    return logout(db, request, response, context)


@app.get("/api/auth/me", response_model=CurrentUserResponse)
def auth_me(
    request: Request,
    response: Response,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    csrf_token = restore_csrf_token(db, request, response, context)
    return user_payload(db, context.user, csrf_token)


@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return dashboard_summary(db, context)


@app.post("/api/workflow/drafts")
def create_workflow_draft(
    payload: WorkflowDraftCreateRequest,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    payload_json = dict(payload.payload or {})
    case_information = dict(payload_json.get("caseInformation") or {})
    if not str(case_information.get("case_id") or "").strip():
        case_year = case_information.get("case_year")
        case_information["case_id"] = next_workflow_case_id(
            db,
            int(case_year) if isinstance(case_year, (int, float)) else None,
        )
        payload_json["caseInformation"] = case_information

    draft = WorkflowDraft(
        workflow_id=uuid4().hex,
        owner_user_id=context.user.id,
        status="active",
        active_step=payload.active_step,
        max_unlocked_step=payload.max_unlocked_step,
        case_id=str(case_information.get("case_id") or "").strip(),
        payload_json=payload_json,
        revision=1,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return serialize_workflow_draft(draft)


@app.get("/api/workflow/drafts")
def list_workflow_drafts(
    status: str = "active",
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    q: str = "",
    page: int = 1,
    page_size: int = 10,
):
    if page < 1:
        raise HTTPException(status_code=422, detail="Page must be at least 1.")
    if page_size < 1 or page_size > 50:
        raise HTTPException(status_code=422, detail="Page size must be between 1 and 50.")
    if len(q) > 200:
        raise HTTPException(status_code=422, detail="Search must be 200 characters or fewer.")

    query = db.query(WorkflowDraft).filter(WorkflowDraft.status == status)
    can_manage_users = "users.manage" in context.permissions
    if not can_manage_users:
        query = query.filter(WorkflowDraft.owner_user_id == context.user.id)
    if "sensitive_case.read" not in context.permissions:
        visible_draft_ids = [
            draft.id
            for draft in query.all()
            if not _workflow_is_sensitive(db, draft)
        ]
        query = query.filter(WorkflowDraft.id.in_(visible_draft_ids))

    normalized_query = _normalize_case_filter(q)
    if normalized_query:
        matching_steps: set[int] = set()
        for stage_id, label, short_label, panel_ids in WORKFLOW_STAGE_DEFINITIONS:
            searchable_stage = " ".join(
                (
                    f"stage {stage_id}",
                    label.lower(),
                    short_label.lower(),
                )
            )
            if normalized_query in searchable_stage:
                matching_steps.update(panel_ids)
        filters = [func.lower(WorkflowDraft.case_id).contains(normalized_query)]
        if matching_steps:
            filters.append(WorkflowDraft.active_step.in_(matching_steps))
        query = query.filter(or_(*filters))

    total = query.count()
    total_pages = (total + page_size - 1) // page_size
    valid_page = min(page, total_pages) if total_pages else 1
    # Draft navigation is a stable creation timeline: the first draft stays on
    # page 1 and newer drafts are appended to the right.  updated_at must not
    # participate here, otherwise saving an older case silently moves it to the
    # first page and makes the picker appear to point at a different workflow.
    drafts = (
        query.order_by(WorkflowDraft.created_at.asc(), WorkflowDraft.id.asc())
        .offset((valid_page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    owners: dict[int, User] = {}
    if can_manage_users and drafts:
        owner_ids = {draft.owner_user_id for draft in drafts}
        owners = {
            owner.id: owner
            for owner in db.query(User).filter(User.id.in_(owner_ids)).all()
        }
    return {
        "items": [serialize_workflow_draft(draft, owners.get(draft.owner_user_id)) for draft in drafts],
        "page": valid_page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _normalize_case_filter(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _workflow_is_sensitive(db: Session, draft: WorkflowDraft) -> bool:
    payload = dict(draft.payload_json or {})
    if workflow_has_vawc_trigger(payload):
        return True
    if draft.case_analysis_id is None:
        return False
    analysis = db.query(CaseAnalysis).filter(CaseAnalysis.id == draft.case_analysis_id).first()
    if analysis is None:
        return False
    case_information = (
        db.query(CaseInformation)
        .filter(CaseInformation.id == analysis.case_information_id)
        .first()
    )
    if bool(
        (analysis.detected_keywords_json or {}).get("vawc_trigger")
        or (case_information and case_information.has_vawc_or_child_abuse_indicators)
    ):
        return True
    case_id = draft.case_id or (case_information.case_id if case_information else "")
    if not case_id:
        return False
    route_query = db.query(Phase3CaseRoute).filter(Phase3CaseRoute.case_id == case_id)
    if analysis.created_at:
        route_query = route_query.filter(Phase3CaseRoute.created_at >= analysis.created_at)
    if draft.updated_at:
        route_query = route_query.filter(Phase3CaseRoute.created_at <= draft.updated_at)
    route = route_query.order_by(Phase3CaseRoute.id.desc()).first()
    return bool(route and route.is_sensitive)


def _case_id_is_sensitive(db: Session, case_id: str) -> bool:
    """Return the conservative sensitivity classification for a case identity.

    Historical databases may contain more than one workflow with the same case
    ID. Treat the identity as protected when any linked workflow, intake,
    analysis, or Phase 3 route is sensitive so a less-sensitive duplicate can
    never be used to bypass protected-record access.
    """
    normalized_case_id = case_id.strip()
    if not normalized_case_id:
        return False
    drafts = db.query(WorkflowDraft).filter(WorkflowDraft.case_id == normalized_case_id).all()
    if any(_workflow_is_sensitive(db, draft) for draft in drafts):
        return True
    case_information = (
        db.query(CaseInformation)
        .filter(CaseInformation.case_id == normalized_case_id)
        .all()
    )
    if any(
        item.has_vawc_or_child_abuse_indicators
        or str(item.sensitivity_level or "").strip().lower() not in {"", "normal", "standard"}
        for item in case_information
    ):
        return True
    information_ids = [item.id for item in case_information]
    if information_ids:
        analyses = db.query(CaseAnalysis).filter(CaseAnalysis.case_information_id.in_(information_ids)).all()
        if any((analysis.detected_keywords_json or {}).get("vawc_trigger") for analysis in analyses):
            return True
    return bool(
        db.query(Phase3CaseRoute)
        .filter(Phase3CaseRoute.case_id == normalized_case_id, Phase3CaseRoute.is_sensitive.is_(True))
        .first()
    )


def ensure_case_read_access(
    db: Session,
    case_id: str,
    context: Any,
    *,
    audit_resource_type: str | None = None,
    audit_resource_id: str | None = None,
) -> bool:
    """Enforce row-level ownership and sensitive-case access for direct APIs."""
    if not isinstance(context, AuthContext):
        return _case_id_is_sensitive(db, case_id)
    drafts = db.query(WorkflowDraft).filter(WorkflowDraft.case_id == case_id).all()
    if (
        drafts
        and "users.manage" not in context.permissions
        and not any(draft.owner_user_id == context.user.id for draft in drafts)
    ):
        raise HTTPException(status_code=404, detail="Case record was not found.")
    is_sensitive = _case_id_is_sensitive(db, case_id)
    if is_sensitive and "sensitive_case.read" not in context.permissions:
        raise HTTPException(status_code=404, detail="Case record was not found.")
    if is_sensitive and audit_resource_type:
        db.add(
            AuditLog(
                case_id=case_id,
                action="sensitive_case_record_accessed",
                actor=context.user.username,
                actor_user_id=context.user.id,
                actor_role=context.role.name,
                resource_type=audit_resource_type,
                resource_id=audit_resource_id or case_id,
                risk_level="moderate",
                details_json={"case_id": case_id, "redacted": False},
            )
        )
        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="The sensitive record was not released because access could not be audited.",
            ) from exc
    return is_sensitive


def _authorized_finalized_case_records(
    context: AuthContext,
    db: Session,
) -> list[dict[str, Any]]:
    query = db.query(WorkflowDraft).filter(WorkflowDraft.status.in_(["completed", "cancelled"]))
    if "users.manage" not in context.permissions:
        query = query.filter(WorkflowDraft.owner_user_id == context.user.id)

    records: list[dict[str, Any]] = []
    for draft in query.order_by(WorkflowDraft.updated_at.desc(), WorkflowDraft.id.desc()).all():
        payload = dict(draft.payload_json or {})
        if not payload.get("finalizedAt") or not payload.get("outcome"):
            continue
        case_information = dict(payload.get("caseInformation") or {})
        case_id = draft.case_id or str(case_information.get("case_id") or "")
        if not case_id:
            continue
        is_vawc = workflow_has_vawc_trigger(payload)
        is_sensitive = _workflow_is_sensitive(db, draft)
        if draft.case_analysis_id is not None:
            linked_analysis = (
                db.query(CaseAnalysis)
                .filter(CaseAnalysis.id == draft.case_analysis_id)
                .first()
            )
            if linked_analysis is not None:
                linked_case_information = (
                    db.query(CaseInformation)
                    .filter(CaseInformation.id == linked_analysis.case_information_id)
                    .first()
                )
                is_vawc = bool(
                    is_vawc
                    or (linked_analysis.detected_keywords_json or {}).get("vawc_trigger")
                    or (
                        linked_case_information
                        and linked_case_information.has_vawc_or_child_abuse_indicators
                    )
                )
                linked_sensitive_route = (
                    db.query(Phase3CaseRoute)
                    .filter(
                        Phase3CaseRoute.case_id == case_id,
                        Phase3CaseRoute.created_at >= linked_analysis.created_at,
                        Phase3CaseRoute.created_at <= draft.updated_at,
                    )
                    .order_by(Phase3CaseRoute.id.desc())
                    .first()
                )
                is_sensitive = bool(is_sensitive or is_vawc or (linked_sensitive_route and linked_sensitive_route.is_sensitive))
        # Apply authorization before search, filtering, and totals.  A caller
        # without protected-case access cannot infer hidden records from counts.
        if is_sensitive and "sensitive_case.read" not in context.permissions:
            continue
        outcome = str(payload.get("outcome") or payload.get("caseRecordStatus") or "Finalized")
        is_cancelled = draft.status == "cancelled" or bool(payload.get("caseCancelled"))
        tone = "red" if is_cancelled or is_sensitive else "green" if outcome == "Amicable Settlement Reached" else "amber"
        records.append(
            {
                "id": case_id,
                "parties": "Protected complainant referral" if is_sensitive else "Complainant and Respondent",
                "type": str(case_information.get("dispute_category") or case_information.get("case_type") or "Case").replace("_", " ").title(),
                "dateFiled": payload.get("finalizedAt") or draft.updated_at,
                "status": outcome,
                "tone": tone,
                "route": "cancelled" if is_cancelled else "vawc_referral" if is_vawc else "referral" if workflow_requires_referral(payload) else "mediation",
                "is_sensitive": is_sensitive,
                "privacy_label": "Sensitive / protected" if is_sensitive else "Standard access",
                "workflow_id": draft.workflow_id,
                "phase4_packet_id": payload.get("phase4PacketId"),
            }
        )
    case_id_counts: dict[str, int] = {}
    for record in records:
        normalized_id = str(record["id"]).casefold()
        case_id_counts[normalized_id] = case_id_counts.get(normalized_id, 0) + 1
    for record in records:
        record["duplicate_case_id"] = case_id_counts[str(record["id"]).casefold()] > 1
    return records


def list_finalized_workflow_cases(
    context: AuthContext,
    db: Session,
) -> list[dict[str, Any]]:
    """Return authorized finalized records for internal callers and legacy tests."""
    return _authorized_finalized_case_records(context, db)


@app.get("/api/cases")
def get_paginated_finalized_workflow_cases(
    q: str = Query(default="", max_length=200),
    status: str = Query(default="", max_length=200),
    route: str = Query(default="", max_length=50),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    records = _authorized_finalized_case_records(context, db)
    normalized_query = _normalize_case_filter(q)
    normalized_status = _normalize_case_filter(status)
    normalized_route = _normalize_case_filter(route).replace(" ", "_")

    filtered_records: list[dict[str, Any]] = []
    for record in records:
        if normalized_status and _normalize_case_filter(str(record["status"])) != normalized_status:
            continue
        if normalized_route and _normalize_case_filter(str(record["route"])).replace(" ", "_") != normalized_route:
            continue
        if normalized_query:
            searchable_values = (
                record["id"],
                record["parties"],
                record["type"],
                record["status"],
                record["route"],
                str(record["route"]).replace("_", " "),
                record["dateFiled"],
            )
            if not any(normalized_query in _normalize_case_filter(str(value or "")) for value in searchable_values):
                continue
        filtered_records.append(record)

    total = len(filtered_records)
    total_pages = (total + page_size - 1) // page_size
    valid_page = min(page, total_pages) if total_pages else 1
    start = (valid_page - 1) * page_size
    return {
        "items": filtered_records[start:start + page_size],
        "page": valid_page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _completed_case_workflow(
    workflow_id: str,
    context: AuthContext,
    db: Session,
) -> WorkflowDraft:
    draft = get_owned_workflow_draft(db, workflow_id, context)
    payload = dict(draft.payload_json or {})
    if draft.status not in {"completed", "cancelled"} or not (
        payload.get("finalizedAt") and payload.get("outcome")
    ):
        raise HTTPException(status_code=404, detail="Completed case record was not found.")
    if draft.case_analysis_id is None:
        raise HTTPException(status_code=409, detail="The completed workflow has no linked case analysis.")
    return draft


def _record_in_workflow_window(record: Any, draft: WorkflowDraft, analysis: CaseAnalysis) -> bool:
    created_at = getattr(record, "created_at", None) or getattr(record, "uploaded_at", None)
    if not created_at:
        return True
    start = analysis.created_at or draft.created_at
    end = draft.updated_at
    return (not start or created_at >= start) and (not end or created_at <= end)


def workflow_phase3_record_ids(
    db: Session,
    draft: WorkflowDraft,
    analysis: CaseAnalysis,
    *,
    end_at: datetime | None = None,
) -> dict[str, Any]:
    """Snapshot the exact Phase 3 rows used by a workflow at finalization."""
    case_id = draft.case_id
    start = analysis.created_at or draft.created_at
    end = end_at or draft.updated_at

    def records_for(model: type[Any], order_column: Any) -> list[Any]:
        records = db.query(model).filter(model.case_id == case_id).order_by(order_column).all()
        return [
            record
            for record in records
            if (
                not (created_at := getattr(record, "created_at", None) or getattr(record, "uploaded_at", None))
                or ((not start or created_at >= start) and (not end or created_at <= end))
            )
        ]

    routes = records_for(Phase3CaseRoute, Phase3CaseRoute.id.desc())
    eligibility = records_for(MediationEligibility, MediationEligibility.id.desc())
    suggestions = records_for(MediationSuggestion, MediationSuggestion.id.desc())
    referrals = records_for(Referral, Referral.id.desc())
    hearings = records_for(Hearing, Hearing.id.asc())
    evidence = records_for(Evidence, Evidence.id.desc())
    emotions = records_for(EmotionAnalysis, EmotionAnalysis.id.desc())
    decisions = records_for(Phase3OfficialDecision, Phase3OfficialDecision.id.desc())
    return {
        "sensitive_routing": routes[0].id if routes else None,
        "mediation_eligibility": eligibility[0].id if eligibility else None,
        "mediation_suggestions": suggestions[0].id if suggestions else None,
        "referrals": [record.id for record in referrals],
        "hearings": [record.id for record in hearings],
        "evidence": [record.id for record in evidence],
        "emotion_analysis": emotions[0].id if emotions else None,
        "official_decision": decisions[0].id if decisions else None,
    }


def _redact_case_information(case_information: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(case_information)
    for field in (
        "complainant_residency",
        "respondent_residency",
        "next_of_kin_assistant_name",
        "real_property_barangay",
        "real_property_city_municipality",
        "respondent_barangay",
        "respondent_city_municipality",
        "workplace_or_school_barangay",
        "workplace_or_school_city_municipality",
    ):
        if field in redacted:
            redacted[field] = None
    return redacted


def completed_transcript_record(
    transcript: Transcript,
    payload: dict[str, Any],
    transcript_access: bool,
) -> dict[str, Any]:
    raw_recording_type = str(
        transcript.recording_type
        or ("blotter_hearing" if payload.get("hearingRecorded") else payload.get("recordingType"))
        or "blotter_case"
    ).strip().lower().replace("-", "_")
    recording_type = (
        "blotter_hearing"
        if raw_recording_type in {"blotter_hearing", "hearing", "mediation"}
        or transcript.save_context == "hearing"
        else "blotter_case"
    )
    participant_roles = [ROLE_LABELS[role] for role in role_order_for_recording_type(recording_type)]

    stored_segments = [dict(item) for item in (transcript.segments_json or []) if isinstance(item, dict)]
    if not stored_segments and transcript.content:
        stored_segments = [item.model_dump() for item in parse_edited_transcript(transcript.content)]

    known_labels = {label.casefold(): label for label in participant_roles}
    aliases = {
        "barangay secretary": ROLE_LABELS["barangay_secretary"],
        "barangay secretary/mediator": ROLE_LABELS["barangay_secretary"],
        "secretary": ROLE_LABELS["barangay_secretary"],
        "mediator": ROLE_LABELS["barangay_secretary"],
        "complainant": ROLE_LABELS["complainant"],
        "respondent": ROLE_LABELS["respondent"],
    }
    canonical_segments: list[dict[str, Any]] = []
    all_known = bool(stored_segments)
    for item in stored_segments:
        speaker = str(item.get("speaker") or "").strip()
        canonical = known_labels.get(speaker.casefold()) or aliases.get(speaker.casefold())
        if canonical not in participant_roles:
            all_known = False
        canonical_segments.append({**item, "speaker": canonical or speaker or "Speaker 1"})
    if canonical_segments and not all_known:
        canonical_segments = assign_role_labels(canonical_segments, recording_type)

    participant_transcripts = []
    for role in participant_roles:
        role_segments = [item for item in canonical_segments if item.get("speaker") == role]
        participant_transcripts.append(
            {
                "role": role,
                "segment_count": len(role_segments),
                "text": "\n".join(str(item.get("text") or "").strip() for item in role_segments).strip()
                if transcript_access
                else "",
            }
        )

    normalized_content = "\n\n".join(
        f"{item.get('speaker')}: {str(item.get('text') or '').strip()}"
        for item in canonical_segments
        if str(item.get("text") or "").strip()
    ) or transcript.content

    return {
        "id": transcript.id,
        "workflow_id": transcript.workflow_id,
        "case_id": transcript.case_id,
        "save_context": transcript.save_context,
        "content": normalized_content if transcript_access else "",
        "segments": canonical_segments if transcript_access else [],
        "recording_type": recording_type,
        "recording_type_label": "Blotter Hearing" if recording_type == "blotter_hearing" else "Blotter Recording",
        "participant_roles": participant_roles,
        "participant_transcripts": participant_transcripts,
        "asr_provider": transcript.asr_provider,
        "asr_confidence": transcript.asr_confidence,
        "diarization_quality": transcript.diarization_quality,
        "manual_correction_rate": normalized_correction_rate(transcript),
        "expected_speakers": len(participant_roles),
        "stored_expected_speakers": transcript.expected_speakers,
        "detected_speakers": transcript.detected_speakers,
        "created_at": transcript.created_at,
        "updated_at": transcript.updated_at or transcript.created_at,
        "redacted": not transcript_access,
    }


def completed_case_summary(
    workflow_id: str,
    context: AuthContext,
    db: Session,
) -> dict[str, Any]:
    """Build the immutable record view from the workflow's exact linked IDs."""
    draft = _completed_case_workflow(workflow_id, context, db)
    payload = dict(draft.payload_json or {})
    analysis = (
        db.query(CaseAnalysis)
        .filter(CaseAnalysis.id == draft.case_analysis_id)
        .first()
    )
    if analysis is None:
        raise HTTPException(status_code=409, detail="The workflow's linked case analysis was not found.")

    case_information = (
        db.query(CaseInformation)
        .filter(CaseInformation.id == analysis.case_information_id)
        .first()
    )
    if case_information is None:
        raise HTTPException(status_code=409, detail="The workflow's linked case information was not found.")

    if draft.case_id and case_information.case_id.casefold() != draft.case_id.casefold():
        raise HTTPException(
            status_code=409,
            detail="The completed workflow's case information belongs to a different case ID.",
        )
    if (
        draft.transcript_id is not None
        and analysis.transcript_id is not None
        and draft.transcript_id != analysis.transcript_id
    ):
        raise HTTPException(
            status_code=409,
            detail="The completed workflow and its analysis do not reference the same transcript.",
        )

    transcript = None
    if analysis.transcript_id is not None:
        transcript = db.query(Transcript).filter(Transcript.id == analysis.transcript_id).first()
    xai_trace = db.query(XAITrace).filter(XAITrace.id == analysis.xai_trace_id).first()
    case_id = draft.case_id or case_information.case_id

    phase3_record_ids = payload.get("phase3RecordIds")
    if not isinstance(phase3_record_ids, dict):
        phase3_record_ids = {}

    def scoped_records(model: type[Any], order_column: Any, record_key: str) -> list[Any]:
        if record_key in phase3_record_ids:
            stored_value = phase3_record_ids.get(record_key)
            stored_ids = stored_value if isinstance(stored_value, list) else [stored_value]
            exact_ids = [
                value
                for value in stored_ids
                if isinstance(value, int) and not isinstance(value, bool)
            ]
            if not exact_ids:
                return []
            return (
                db.query(model)
                .filter(model.case_id == case_id, model.id.in_(exact_ids))
                .order_by(order_column)
                .all()
            )
        records = (
            db.query(model)
            .filter(model.case_id == case_id)
            .order_by(order_column)
            .all()
        )
        return [item for item in records if _record_in_workflow_window(item, draft, analysis)]

    routes = scoped_records(Phase3CaseRoute, Phase3CaseRoute.id.desc(), "sensitive_routing")
    eligibility_records = scoped_records(MediationEligibility, MediationEligibility.id.desc(), "mediation_eligibility")
    suggestions_records = scoped_records(MediationSuggestion, MediationSuggestion.id.desc(), "mediation_suggestions")
    referrals = scoped_records(Referral, Referral.id.desc(), "referrals")
    hearings = scoped_records(Hearing, Hearing.id.asc(), "hearings")
    evidence = scoped_records(Evidence, Evidence.id.desc(), "evidence")
    emotions = scoped_records(EmotionAnalysis, EmotionAnalysis.id.desc(), "emotion_analysis")
    official_decisions = scoped_records(Phase3OfficialDecision, Phase3OfficialDecision.id.desc(), "official_decision")

    phase4_packet = None
    packet_id = payload.get("phase4PacketId")
    if isinstance(packet_id, int) and not isinstance(packet_id, bool):
        phase4_packet = (
            db.query(Phase4FormPacket)
            .filter(Phase4FormPacket.id == packet_id, Phase4FormPacket.case_id == case_id)
            .first()
        )

    generated_forms: list[Phase4GeneratedForm] = []
    if phase4_packet is not None:
        generated_forms = (
            db.query(Phase4GeneratedForm)
            .filter(Phase4GeneratedForm.packet_id == phase4_packet.id)
            .order_by(Phase4GeneratedForm.id.asc())
            .all()
        )

    route = routes[0] if routes else None
    keyword_result = dict(analysis.detected_keywords_json or {})
    is_sensitive = bool(
        case_information.has_vawc_or_child_abuse_indicators
        or keyword_result.get("vawc_trigger")
        or (route and route.is_sensitive)
    )
    sensitive_access = (not is_sensitive) or "sensitive_case.read" in context.permissions
    transcript_access = sensitive_access and "transcript.read" in context.permissions
    evidence_access = sensitive_access and "evidence.read" in context.permissions
    evidence_download = evidence_access and "evidence.download" in context.permissions
    forms_download = sensitive_access and "forms.download" in context.permissions

    case_information_data = serialize_model(case_information)
    case_information_data.pop("id", None)
    if not sensitive_access:
        case_information_data = _redact_case_information(case_information_data)

    def referral_data(item: Referral) -> dict[str, Any]:
        data = serialize_model(item)
        if not sensitive_access:
            data.update({"reason": "Protected", "matched_keywords": [], "xai_reference": {}})
        return data

    def hearing_data(item: Hearing) -> dict[str, Any]:
        data = serialize_model(item)
        if not sensitive_access:
            data.update(
                {
                    "location": "Protected",
                    "assigned_lupon_member": "Protected",
                    "notes": "Protected",
                }
            )
        return data

    def evidence_data(item: Evidence) -> dict[str, Any]:
        data = {
            "id": item.id,
            "case_id": item.case_id,
            "file_name": item.file_name if evidence_access else f"Protected evidence #{item.id}",
            "file_type": item.file_type,
            "evidence_text": item.ocr_text if evidence_access else "",
            "extracted_entities_json": item.extracted_entities_json if evidence_access else {},
            "uploaded_at": item.uploaded_at,
            "download_url": f"/api/phase3/evidence/{item.id}/download" if evidence_download else None,
        }
        return data

    audit_records = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case_id)
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        .all()
    )
    audit_history = []
    for item in audit_records:
        details = dict(item.details_json or {})
        details_workflow_id = str(details.get("workflow_id") or "")
        if details_workflow_id and details_workflow_id != draft.workflow_id:
            continue
        if not details_workflow_id and not _record_in_workflow_window(item, draft, analysis):
            continue
        audit_history.append(
            {
                "id": item.id,
                "action": item.action,
                "actor": item.actor,
                "actor_role": item.actor_role,
                "risk_level": item.risk_level,
                "details": details if sensitive_access else {},
                "created_at": item.created_at,
            }
        )

    route_data = serialize_model(route) if route else None
    if route_data and not sensitive_access:
        route_data.update({"reason": "Protected", "matched_keywords": []})

    eligibility_data = serialize_model(eligibility_records[0]) if eligibility_records else None
    if eligibility_data and not sensitive_access:
        eligibility_data["reason"] = "Protected"

    official_data = serialize_model(official_decisions[0]) if official_decisions else None
    if official_data and not sensitive_access:
        official_data.update(
            {
                "official_decision": "Protected referral decision",
                "official_notes": "Protected",
                "approved_by": "Protected",
            }
        )

    packet_data = None
    if phase4_packet is not None:
        packet_data = serialize_model(phase4_packet)
        packet_data["generated_forms"] = [
            {
                "id": form.id,
                "form_id": form.form_id,
                "title": form.title,
                "purpose": form.purpose,
                "validation_status": form.validation_status,
                "missing_fields": form.missing_fields_json,
                "created_at": form.created_at,
                "download_url": (
                    f"/api/phase4/generated-forms/{form.id}/download" if forms_download else None
                ),
            }
            for form in generated_forms
        ]

    transcript_data = (
        completed_transcript_record(transcript, payload, transcript_access)
        if transcript is not None
        else None
    )

    return {
        "workflow": {
            "workflow_id": draft.workflow_id,
            "case_id": case_id,
            "case_analysis_id": analysis.id,
            "transcript_id": analysis.transcript_id,
            "status": draft.status,
            "revision": draft.revision,
            "created_at": draft.created_at,
            "updated_at": draft.updated_at,
        },
        "privacy": {
            "is_sensitive": is_sensitive,
            "sensitivity_category": route.sensitive_category if route else ("Protected case" if is_sensitive else "None"),
            "redacted": is_sensitive and not sensitive_access,
            "notice": (
                "Protected complainant information is redacted for your role."
                if is_sensitive and not sensitive_access
                else "Sensitive-case access is authorized for this record."
                if is_sensitive
                else "Standard case access rules apply."
            ),
        },
        "final_outcome": {
            "outcome": payload.get("outcome"),
            "record_status": payload.get("caseRecordStatus") or draft.status,
            "finalized_at": payload.get("finalizedAt"),
            "cancelled": bool(payload.get("caseCancelled") or draft.status == "cancelled"),
            "cancellation_reason": payload.get("cancellationReason") if sensitive_access else None,
            "cancelled_at": payload.get("cancelledAt"),
            "cancelled_by": payload.get("cancelledBy") if sensitive_access else None,
        },
        "case_information": case_information_data,
        "transcript": transcript_data,
        "phase2_analysis": {
            "analysis_id": analysis.id,
            "detected_keywords": keyword_result if sensitive_access else {"vawc_trigger": bool(keyword_result.get("vawc_trigger"))},
            "rule_results": analysis.rule_results_json if sensitive_access else [],
            "jurisdiction_decision": analysis.jurisdiction_decision,
            "exclusion_ground": analysis.exclusion_ground if sensitive_access else "Protected",
            "confidence_level": analysis.confidence_level,
            "missing_fields": analysis.missing_fields_json if sensitive_access else [],
            "recommended_next_action": analysis.recommended_next_action if sensitive_access else "Protected referral",
            "created_at": analysis.created_at,
        },
        "jurisdiction": {
            "decision": analysis.jurisdiction_decision,
            "exclusion_ground": analysis.exclusion_ground if sensitive_access else "Protected",
            "confidence_level": analysis.confidence_level,
        },
        "xai_reasoning": {
            "trace": xai_trace.trace_json if xai_trace and sensitive_access else [],
            "explanation": xai_trace.trace_text if xai_trace and sensitive_access else "",
        },
        "phase3_routing": {
            "sensitive_routing": route_data,
            "mediation_eligibility": eligibility_data,
            "mediation_suggestions": (
                serialize_model(suggestions_records[0]) if suggestions_records and sensitive_access else None
            ),
            "emotion_analysis": serialize_model(emotions[0]) if emotions and sensitive_access else None,
            "recommended_route": (
                payload.get("phase3RecommendedRoute") or (route.recommended_route if route else "")
            ) if sensitive_access else "Protected referral",
        },
        "referral_resolution": {
            "workflow_resolution": payload.get("referralResolution") if sensitive_access else None,
            "referrals": [referral_data(item) for item in referrals],
        },
        "hearings": [hearing_data(item) for item in hearings],
        "evidence": [evidence_data(item) for item in evidence],
        "official_decision": official_data,
        "phase4_packet": packet_data,
        "audit_history": audit_history,
        "actions": {
            "can_view_transcript": transcript_access and transcript is not None,
            "can_print_transcript": transcript_access and transcript is not None,
            "can_download_transcript_pdf": (
                transcript_access and transcript is not None and "reports.export" in context.permissions
            ),
            "can_view_evidence": evidence_access,
            "can_download_evidence": evidence_download,
            "can_download_forms": forms_download,
            "can_print_summary": True,
        },
    }


@app.get("/api/management/cases/{workflow_id}")
def get_completed_case_summary(
    workflow_id: str,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    summary = completed_case_summary(workflow_id, context, db)
    if summary["privacy"]["is_sensitive"]:
        db.add(
            AuditLog(
                case_id=summary["workflow"]["case_id"],
                action="sensitive_case_record_accessed",
                actor=context.user.username,
                actor_user_id=context.user.id,
                actor_role=context.role.name,
                ip_address=request.client.host if request.client else "",
                user_agent=request.headers.get("user-agent", "")[:500],
                resource_type="completed_case_summary",
                resource_id=workflow_id,
                risk_level="moderate",
                details_json={
                    "workflow_id": workflow_id,
                    "redacted": summary["privacy"]["redacted"],
                },
            )
        )
        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="The sensitive record was not released because access could not be audited.",
            ) from exc
    return summary


@app.get("/api/management/cases/{workflow_id}/transcript.pdf")
def download_completed_transcript_pdf(
    workflow_id: str,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if "transcript.read" not in context.permissions or "reports.export" not in context.permissions:
        raise HTTPException(status_code=403, detail="You do not have permission to export transcript PDFs.")

    summary = completed_case_summary(workflow_id, context, db)
    transcript = summary.get("transcript")
    if not transcript:
        raise HTTPException(status_code=409, detail="The completed case has no linked final transcript.")
    if transcript.get("redacted") or not summary["actions"]["can_download_transcript_pdf"]:
        raise HTTPException(status_code=403, detail="You do not have permission to export this transcript.")

    try:
        artifact = CompletedTranscriptPdfService().build(
            summary,
            generated_by=context.user.full_name or context.user.username,
            generated_by_username=context.user.username,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    audit = AuditLog(
        case_id=summary["workflow"]["case_id"],
        action="completed_transcript_pdf_generated_downloaded",
        actor=context.user.username,
        actor_user_id=context.user.id,
        actor_role=context.role.name,
        ip_address=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", "")[:500],
        resource_type="completed_transcript_pdf",
        resource_id=artifact.document_id,
        risk_level="moderate" if summary["privacy"]["is_sensitive"] else "low",
        details_json={
            "workflow_id": workflow_id,
            "case_id": summary["workflow"]["case_id"],
            "transcript_id": transcript["id"],
            "transcript_scope": artifact.scope,
            "document_id": artifact.document_id,
            "filename": artifact.filename,
            "sha256": artifact.sha256,
            "byte_length": len(artifact.content),
            "page_count": artifact.page_count,
            "generated_at": artifact.generated_at.isoformat(),
            "generated_by": context.user.username,
        },
    )
    db.add(audit)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="The PDF was not released because its audit record could not be saved.",
        ) from exc

    return Response(
        content=artifact.content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "Cache-Control": "private, no-store, max-age=0",
            "X-Document-ID": artifact.document_id,
            "X-Document-SHA256": artifact.sha256,
            "X-Generated-At": artifact.generated_at.isoformat(),
        },
    )


@app.get("/api/workflow/drafts/{workflow_id}")
def get_workflow_draft(
    workflow_id: str,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return serialize_workflow_draft(get_owned_workflow_draft(db, workflow_id, context))


@app.delete("/api/workflow/drafts/{workflow_id}")
def delete_workflow_draft(
    workflow_id: str,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    draft = get_owned_workflow_draft(db, workflow_id, context)
    ensure_workflow_is_mutable(draft)
    db.delete(draft)
    db.commit()
    return {
        "workflow_id": workflow_id,
        "message": "Workflow draft deleted.",
    }


@app.patch("/api/workflow/drafts/{workflow_id}")
def update_workflow_draft(
    workflow_id: str,
    payload: WorkflowDraftUpdateRequest,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    draft = get_owned_workflow_draft(db, workflow_id, context)
    ensure_workflow_is_mutable(draft)
    ensure_workflow_revision(draft, payload.revision)

    existing_payload = dict(draft.payload_json or {})
    canonical_audio_filename = draft.audio_filename or str(existing_payload.get("blotterAudioFilename") or "").strip()
    incoming_payload = dict(payload.payload or {})
    incoming_audio_filename = str(incoming_payload.get("blotterAudioFilename") or "").strip()
    if canonical_audio_filename and incoming_audio_filename != canonical_audio_filename:
        raise HTTPException(
            status_code=409,
            detail="This workflow already has an audio record. Its recording cannot be removed or replaced.",
        )
    if canonical_audio_filename:
        incoming_payload["blotterAudioFilename"] = canonical_audio_filename
        incoming_payload["blotterDurationSeconds"] = (
            draft.audio_duration_seconds
            if draft.audio_duration_seconds is not None
            else existing_payload.get("blotterDurationSeconds", 0)
        )

    incoming_case_information = dict(incoming_payload.get("caseInformation") or {})
    payload_case_id = str(incoming_case_information.get("case_id") or "").strip()
    requested_case_id = str(payload.case_id or "").strip()
    if requested_case_id and payload_case_id and requested_case_id != payload_case_id:
        raise HTTPException(
            status_code=409,
            detail="The workflow case ID does not match the case information in this draft.",
        )
    canonical_case_id = requested_case_id or payload_case_id or draft.case_id
    incoming_case_information["case_id"] = canonical_case_id
    incoming_payload["caseInformation"] = incoming_case_information

    draft.active_step = payload.active_step
    draft.max_unlocked_step = payload.max_unlocked_step
    draft.status = payload.status
    draft.case_id = canonical_case_id
    draft.transcript_id = payload.transcript_id
    draft.case_analysis_id = payload.case_analysis_id
    draft.payload_json = incoming_payload
    draft.revision += 1
    draft.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(draft)
    return serialize_workflow_draft(draft)


@app.post("/api/workflow/drafts/{workflow_id}/complete")
def complete_workflow_draft(
    workflow_id: str,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    draft = get_owned_workflow_draft(db, workflow_id, context)
    ensure_workflow_is_mutable(draft)
    draft.status = "completed"
    draft.active_step = 7
    draft.max_unlocked_step = 7
    draft.revision += 1
    draft.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(draft)
    return serialize_workflow_draft(draft)


@app.post("/api/workflow/drafts/{workflow_id}/phase2-analysis")
def run_workflow_phase2_analysis(
    workflow_id: str,
    payload: WorkflowPhase2AnalysisRequest,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    draft = get_owned_workflow_draft(db, workflow_id, context)
    ensure_workflow_is_mutable(draft)
    ensure_workflow_revision(draft, payload.revision)

    keyword_preview = detect_sensitive_keywords(payload.transcript_text or "")
    if (
        keyword_preview.get("vawc_trigger")
        and not payload.case_information.has_vawc_or_child_abuse_indicators
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "VAWC or child-abuse trigger words were detected. "
                "An authorized official must confirm the protected-case indicator before routing."
            ),
        )

    requested_case_id = payload.case_information.case_id.strip() or workflow_case_id(draft)
    if not requested_case_id:
        requested_case_id = next_workflow_case_id(db, payload.case_information.case_year)
    existing_case_id = workflow_case_id(draft)
    if existing_case_id and requested_case_id.casefold() != existing_case_id.casefold():
        if draft.case_analysis_id is not None:
            raise HTTPException(
                status_code=409,
                detail="The case ID cannot change after the backend decision has been saved.",
            )
        conflicting_draft = (
            db.query(WorkflowDraft)
            .filter(
                WorkflowDraft.case_id == requested_case_id,
                WorkflowDraft.workflow_id != draft.workflow_id,
            )
            .first()
        )
        if conflicting_draft:
            raise HTTPException(
                status_code=409,
                detail="This case ID is already assigned to another workflow. Resume that workflow instead.",
            )
        draft.case_id = requested_case_id
        draft_payload = dict(draft.payload_json or {})
        draft_case_information = dict(draft_payload.get("caseInformation") or {})
        draft_case_information["case_id"] = requested_case_id
        draft_payload["caseInformation"] = draft_case_information
        draft.payload_json = draft_payload

    canonical_transcript = None
    if draft.transcript_id is not None:
        if payload.transcript_id is not None and payload.transcript_id != draft.transcript_id:
            raise HTTPException(
                status_code=409,
                detail="The selected transcript is not the canonical transcript for this workflow.",
            )
        canonical_transcript = (
            db.query(Transcript)
            .filter(
                Transcript.id == draft.transcript_id,
                Transcript.superseded_by_transcript_id.is_(None),
            )
            .first()
        )
        if not canonical_transcript:
            raise HTTPException(status_code=409, detail="The workflow transcript is no longer available.")
    elif payload.transcript_text and payload.transcript_text.strip():
        # Backward-compatible recovery for older clients: direct Phase 2 text
        # is first persisted through the same canonical workflow upsert. This
        # prevents an untracked analysis or a second Saved Transcript row.
        saved = save_transcript(
            SaveTranscriptRequest(
                content=payload.transcript_text.strip(),
                workflow_id=draft.workflow_id,
                case_id=requested_case_id,
                save_context="intake",
            ),
            db,
            context,
        )
        draft = get_owned_workflow_draft(db, workflow_id, context)
        canonical_transcript = db.query(Transcript).filter(Transcript.id == saved["id"]).first()
    else:
        raise HTTPException(
            status_code=409,
            detail="Save the canonical intake transcript for this workflow before running Phase 2.",
        )

    if not canonical_transcript:
        raise HTTPException(status_code=409, detail="The workflow transcript is no longer available.")
    if canonical_transcript.workflow_id and canonical_transcript.workflow_id != draft.workflow_id:
        owning_draft = (
            db.query(WorkflowDraft)
            .filter(WorkflowDraft.workflow_id == canonical_transcript.workflow_id)
            .first()
        )
        if (
            "users.manage" not in context.permissions
            and (not owning_draft or owning_draft.owner_user_id != context.user.id)
        ):
            raise HTTPException(status_code=409, detail="The workflow transcript belongs to another case owner.")
    if canonical_transcript.case_id and canonical_transcript.case_id.casefold() != requested_case_id.casefold():
        raise HTTPException(status_code=409, detail="The workflow transcript belongs to a different case.")

    existing_case_transcript = (
        db.query(Transcript)
        .filter(
            Transcript.case_id == requested_case_id,
            Transcript.id != canonical_transcript.id,
            Transcript.superseded_by_transcript_id.is_(None),
        )
        .first()
    )
    if existing_case_transcript:
        # Never guess which of two evidentiary transcripts should win. The
        # existing workflow must be resumed instead of silently overwriting it.
        raise HTTPException(
            status_code=409,
            detail="This case already has a canonical transcript. Resume its existing workflow.",
        )

    canonical_transcript.workflow_id = canonical_transcript.workflow_id or draft.workflow_id
    canonical_transcript.case_id = requested_case_id
    canonical_metrics = dict(canonical_transcript.accuracy_metrics_json or {})
    canonical_metrics.update({"workflow_id": draft.workflow_id, "case_id": requested_case_id})
    canonical_transcript.accuracy_metrics_json = canonical_metrics
    canonical_transcript.updated_at = datetime.utcnow()
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This case already has a canonical transcript. Resume its existing workflow.",
        ) from exc

    analysis_case_information = payload.case_information.model_copy(
        update={"case_id": requested_case_id}
    )
    analysis_payload = AnalyzeCaseRequest(
        transcript_id=canonical_transcript.id,
        transcript_text=canonical_transcript.content,
        case_information=analysis_case_information,
    )
    analysis = build_case_analysis_response(analysis_payload, db)
    saved_analysis = create_case_analysis_record(analysis, db)
    saved_case_id = analysis.case_information.case_id
    current_payload = dict(draft.payload_json or {})
    current_payload.update(
        {
            "phase2Analysis": analysis_to_payload(analysis),
            "caseInformation": analysis.case_information.model_dump(mode="json"),
            "phase2CaseId": saved_case_id,
            "phase2AnalysisId": saved_analysis.id,
            "analysisConfirmed": True,
            "phase3Processed": False,
            "phase3ReferralRequired": False,
            "phase3RecommendedRoute": "",
            "phase3ReferralId": None,
            "phase3ReferralStatus": "",
            "referralResolution": None,
            "officialDecision": "",
            "symbolicConfirmed": False,
            "skippedPanelIds": skipped_panels_for_analysis(analysis),
        }
    )

    draft.payload_json = current_payload
    draft.case_id = saved_case_id
    draft.case_analysis_id = saved_analysis.id
    draft.transcript_id = analysis.transcript_id
    draft.active_step = 2
    draft.max_unlocked_step = max(draft.max_unlocked_step, 2)
    draft.revision += 1
    draft.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(draft)

    response = serialize_workflow_draft(draft)
    response["analysis"] = analysis
    return response


def process_phase3_pipeline(case_id: str, db: Session) -> dict[str, Any]:
    ensure_case_is_mutable(db, case_id)
    bundle = get_phase2_bundle(db, case_id)

    route_service = SensitiveCaseRoutingService()
    eligibility_service = MediationEligibilityService()
    suggestion_service = MediationSuggestionService()
    emotion_service = EmotionAnalysisService()
    referral_service = ReferralService()

    route_model = route_service.save(db, bundle)
    route_data = serialize_model(route_model)
    referral = referral_service.create_from_route(db, bundle, route_data)
    if referral:
        db.commit()
        db.refresh(referral)

    eligibility_model = eligibility_service.save(db, bundle, route_data)
    eligibility_data = serialize_model(eligibility_model)
    suggestion_service.save(db, bundle, eligibility_data)
    emotion_service.save(db, bundle)

    return Phase3DashboardService().build(db, bundle.case_info.case_id)


@app.post("/api/workflow/drafts/{workflow_id}/generate-forms")
@app.post("/api/workflow/drafts/{workflow_id}/finalize-intake")
def finalize_workflow_intake(
    workflow_id: str,
    payload: WorkflowFinalizeIntakeRequest,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    draft = get_owned_workflow_draft(db, workflow_id, context)
    ensure_workflow_is_mutable(draft)
    ensure_workflow_revision(draft, payload.revision)
    if not draft.case_id or not draft.case_analysis_id:
        raise HTTPException(status_code=400, detail="Run the requirements and XAI decision before generating KP forms.")

    current_payload = dict(draft.payload_json or {})
    # Phase 3 has already created the routing/referral records before Stage 4.
    # Re-running it here can silently create a replacement referral after an
    # official cancelled the original record, so Stage 4 only reads that result.
    dashboard = (
        Phase3DashboardService().build(db, draft.case_id)
        if current_payload.get("phase3Processed")
        else process_phase3_pipeline(draft.case_id, db)
    )
    service = Phase4FormService(GENERATED_FORMS_DIR)
    existing_packet_id = current_payload.get("phase4PacketId")
    packet = None
    if isinstance(existing_packet_id, int) and not payload.regenerate:
        packet = (
            db.query(Phase4FormPacket)
            .filter(Phase4FormPacket.id == existing_packet_id, Phase4FormPacket.case_id == draft.case_id)
            .first()
        )

    if packet is None:
        recommendation = service.recommendation(db, draft.case_id)
        form_ids = [item["form_id"] for item in recommendation["recommended_forms"]]
        packet = service.generate_packet(
            db,
            draft.case_id,
            Phase4GeneratePacketRequest(
                form_ids=form_ids,
                generated_by=payload.generated_by,
                approved_by=payload.approved_by,
                field_overrides=payload.field_overrides,
            ),
        )

    packet_response = service.packet_response(db, packet)
    phase3 = dashboard["phase3"]
    sensitive_route = phase3.get("sensitive_routing") or {}
    referrals = phase3.get("referrals") or []
    latest_referral = referrals[0] if referrals else None
    phase3_recommended_route = str(
        sensitive_route.get("recommended_route")
        or phase3.get("final_recommended_action")
        or ""
    )
    phase3_referral_required = bool(
        latest_referral
        and phase3_recommended_route
        and phase3_recommended_route != "Proceed to Mediation"
    )
    current_payload.update(
        {
            "completed": False,
            "phase3Processed": True,
            "phase3ReferralRequired": phase3_referral_required,
            "phase3RecommendedRoute": phase3_recommended_route,
            "phase3ReferralId": latest_referral.get("id") if latest_referral else None,
            "phase3ReferralStatus": latest_referral.get("status") if latest_referral else "",
            "phase4PacketId": packet.id,
            "generatedFormIds": [item["id"] for item in packet_response["generated_forms"]],
        }
    )
    draft.payload_json = current_payload
    draft.status = "active"
    draft.active_step = 7
    draft.max_unlocked_step = 7
    draft.revision += 1
    draft.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(draft)

    response = serialize_workflow_draft(draft)
    response["phase3"] = dashboard
    response["phase4_packet"] = packet_response
    return response


@app.post("/api/workflow/drafts/{workflow_id}/finalize-outcome")
def finalize_workflow_outcome(
    workflow_id: str,
    payload: WorkflowFinalizeOutcomeRequest,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    draft = get_owned_workflow_draft(db, workflow_id, context)
    ensure_workflow_is_mutable(draft)
    ensure_workflow_revision(draft, payload.revision)
    current_payload = dict(draft.payload_json or {})
    packet_id = current_payload.get("phase4PacketId")
    if not isinstance(packet_id, int):
        raise HTTPException(status_code=400, detail="Generate the required KP forms before finalizing the case.")

    packet = (
        db.query(Phase4FormPacket)
        .filter(Phase4FormPacket.id == packet_id, Phase4FormPacket.case_id == draft.case_id)
        .first()
    )
    if packet is None:
        raise HTTPException(status_code=400, detail="The generated KP form packet could not be found.")

    outcome = payload.outcome.strip()
    is_vawc = workflow_has_vawc_trigger(current_payload)
    referral_resolution = current_payload.get("referralResolution") or {}
    resolved_referral = completed_workflow_referral(db, draft, current_payload)
    cancelled_referral = cancelled_workflow_referral(db, draft, current_payload)
    if (
        isinstance(referral_resolution, dict)
        and referral_resolution.get("status") == "completed"
        and resolved_referral is None
    ):
        raise HTTPException(
            status_code=400,
            detail="The completed referral could not be verified for this workflow case.",
        )
    if (
        isinstance(referral_resolution, dict)
        and referral_resolution.get("status") == "cancelled"
        and cancelled_referral is None
    ):
        raise HTTPException(
            status_code=400,
            detail="The cancelled referral could not be verified for this workflow case.",
        )
    phase2_analysis = current_payload.get("phase2Analysis") or {}
    phase2_decision = str(phase2_analysis.get("jurisdiction_decision") or "").strip().lower()
    phase3_route = (
        db.query(Phase3CaseRoute)
        .filter(Phase3CaseRoute.case_id == draft.case_id)
        .order_by(Phase3CaseRoute.id.desc())
        .first()
    )
    phase3_route_requires_referral = bool(
        phase3_route and phase3_route.recommended_route != "Proceed to Mediation"
    )
    is_referral = (
        is_vawc
        or bool(phase2_decision and phase2_decision != "within_kp")
        or phase3_route_requires_referral
        or resolved_referral is not None
        or cancelled_referral is not None
    )
    normal_outcomes = {
        "Amicable Settlement Reached",
        "No Settlement - Certificate to File Action",
        "Repudiated Settlement",
    }
    referral_outcomes = {
        "Referred to WCPD / PNP",
        "Referred to MSWDO / PNP",
        "Emergency Protection Assistance Initiated",
        "Referred to Court / Proper Authority",
        "Referred for Manual Review",
        "Referral Packet Issued",
    }
    if cancelled_referral is not None:
        allowed = {CANCELLED_REFERRAL_OUTCOME}
    elif resolved_referral is not None:
        allowed = {referral_outcome_label(resolved_referral)}
    else:
        allowed = referral_outcomes if is_referral else normal_outcomes
    if outcome not in allowed:
        raise HTTPException(status_code=400, detail="Select a valid final outcome for this case route.")

    finalized_at = datetime.utcnow()
    final_referral = resolved_referral if resolved_referral is not None else cancelled_referral
    linked_analysis = db.query(CaseAnalysis).filter(CaseAnalysis.id == draft.case_analysis_id).first()
    if linked_analysis is None:
        raise HTTPException(status_code=409, detail="The workflow's linked case analysis was not found.")
    current_payload.update(
        {
            "completed": True,
            "outcome": outcome,
            "finalizedAt": finalized_at.isoformat(),
            "caseRecordStatus": (
                CANCELLED_REFERRAL_OUTCOME
                if cancelled_referral is not None
                else "Referred - VAWC" if is_vawc else outcome
            ),
            "phase3ReferralRequired": is_referral,
            "phase3RecommendedRoute": current_payload.get("phase3RecommendedRoute") or (
                referral_outcome_label(resolved_referral) if resolved_referral is not None else ""
            ),
            "phase3ReferralId": (
                final_referral.id
                if final_referral is not None
                else current_payload.get("phase3ReferralId")
            ),
            "phase3ReferralStatus": (
                final_referral.status
                if final_referral is not None
                else current_payload.get("phase3ReferralStatus", "")
            ),
            "phase3RecordIds": workflow_phase3_record_ids(
                db,
                draft,
                linked_analysis,
                end_at=finalized_at,
            ),
        }
    )
    draft.payload_json = current_payload
    draft.status = "completed"
    draft.active_step = 7
    draft.max_unlocked_step = 7
    draft.revision += 1
    draft.updated_at = finalized_at

    if is_referral and cancelled_referral is None:
        referral = resolved_referral
        if referral is None:
            referral = (
                db.query(Referral)
                .filter(Referral.case_id == draft.case_id)
                .order_by(Referral.id.desc())
                .first()
            )
        if referral:
            referral.status = "completed"
            referral.updated_at = finalized_at

    append_audit_log(
        db,
        draft.case_id,
        "workflow_outcome_finalized",
        {
            "workflow_id": draft.workflow_id,
            "outcome": outcome,
            "phase4_packet_id": packet.id,
            "protected_vawc_route": is_vawc,
            "referral_route": is_referral,
            "cancelled_referral": cancelled_referral is not None,
        },
        actor=context.user.username,
    )
    db.commit()
    db.refresh(draft)

    response = serialize_workflow_draft(draft)
    response["phase4_packet"] = Phase4FormService(GENERATED_FORMS_DIR).packet_response(db, packet)
    return response


@app.post("/api/workflow/drafts/{workflow_id}/referrals/{referral_id}/resolve")
def resolve_workflow_referral(
    workflow_id: str,
    referral_id: int,
    payload: WorkflowReferralActionRequest,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    draft = get_owned_workflow_draft(db, workflow_id, context)
    ensure_workflow_revision(draft, payload.revision)

    if payload.action == "cancel_case" and "case.cancel" not in context.permissions:
        raise HTTPException(status_code=403, detail="You do not have permission to cancel a case.")
    if payload.action in {"complete_and_advance", "cancel_referral"} and "phase3.decide" not in context.permissions:
        raise HTTPException(status_code=403, detail="You do not have permission to update a referral decision.")
    if draft.status == "completed":
        raise HTTPException(status_code=409, detail="This case has already been finalized.")
    if draft.status == "cancelled":
        raise HTTPException(status_code=409, detail="This case has already been cancelled.")

    referral = (
        db.query(Referral)
        .filter(Referral.id == referral_id, Referral.case_id == draft.case_id)
        .first()
    )
    if not referral:
        raise HTTPException(status_code=404, detail="The referral does not belong to this workflow case.")

    cancellation_reason = payload.reason.strip()
    if payload.action in {"cancel_referral", "cancel_case"} and len(cancellation_reason) < 10:
        raise HTTPException(status_code=400, detail="Enter a clear cancellation reason of at least 10 characters.")
    if payload.action == "complete_and_advance" and referral.status != "pending":
        raise HTTPException(status_code=409, detail=f"This referral is already {referral.status}.")
    if payload.action == "cancel_referral" and referral.status != "pending":
        raise HTTPException(status_code=409, detail=f"This referral is already {referral.status}.")

    dashboard = Phase3DashboardService().build(db, draft.case_id)
    system_recommendation = dashboard["phase3"]["final_recommended_action"]
    acted_at = datetime.utcnow()
    acted_by = context.user.full_name or context.user.username
    current_payload = dict(draft.payload_json or {})
    official_decision: Phase3OfficialDecision | None = None
    official_decision_text = ""

    try:
        if payload.action == "complete_and_advance":
            official_decision_text = f"Referral confirmed sent to {referral.destination}"
            official_notes = cancellation_reason or (
                "The barangay official confirmed that the referral was issued through the local/manual referral process."
            )
            referral.status = "completed"
            referral.updated_at = acted_at
            outcome = referral_outcome_label(referral)
            current_payload.update(
                {
                    "caseCancelled": False,
                    "completed": False,
                    "officialDecision": official_decision_text,
                    "outcome": outcome,
                    "phase3Processed": True,
                    "phase3ReferralRequired": True,
                    "phase3RecommendedRoute": system_recommendation,
                    "phase3ReferralId": referral.id,
                    "phase3ReferralStatus": "completed",
                    "symbolicConfirmed": True,
                    "referralResolution": {
                        "referralId": referral.id,
                        "status": "completed",
                        "destination": referral.destination,
                        "officialDecision": official_decision_text,
                        "resolvedAt": acted_at.isoformat(),
                        "resolvedBy": acted_by,
                    },
                }
            )
            draft.status = "active"
            draft.active_step = 7
            draft.max_unlocked_step = max(draft.max_unlocked_step, 7)
            audit_action = "referral_confirmed_sent_and_workflow_advanced"
            message = "Referral recorded as sent and completed. The workflow advanced to Outcome & Forms."
        elif payload.action == "cancel_referral":
            official_notes = cancellation_reason
            referral.status = "cancelled"
            referral.updated_at = acted_at
            current_payload.update(
                {
                    "caseCancelled": False,
                    "completed": False,
                    "phase3Processed": True,
                    "phase3ReferralRequired": True,
                    "phase3RecommendedRoute": system_recommendation,
                    "phase3ReferralId": referral.id,
                    "phase3ReferralStatus": "cancelled",
                    "symbolicConfirmed": True,
                    "outcome": CANCELLED_REFERRAL_OUTCOME,
                    "referralResolution": {
                        "referralId": referral.id,
                        "status": "cancelled",
                        "destination": referral.destination,
                        "resolvedAt": acted_at.isoformat(),
                        "resolvedBy": acted_by,
                        "cancellationReason": cancellation_reason,
                    },
                }
            )
            draft.status = "active"
            draft.active_step = 7
            draft.max_unlocked_step = max(draft.max_unlocked_step, 7)
            audit_action = "referral_record_cancelled"
            message = "Referral record cancelled. Continue to Outcome & Forms to document and finalize the case; ordinary mediation remains blocked."
        else:
            official_decision_text = "Case Cancelled by Barangay Official"
            official_notes = cancellation_reason
            for case_referral in db.query(Referral).filter(Referral.case_id == draft.case_id).all():
                case_referral.status = "cancelled"
                case_referral.updated_at = acted_at
            current_payload.update(
                {
                    "caseCancelled": True,
                    "cancellationReason": cancellation_reason,
                    "cancelledAt": acted_at.isoformat(),
                    "cancelledBy": acted_by,
                    "caseRecordStatus": "Cancelled",
                    "completed": False,
                    "finalizedAt": acted_at.isoformat(),
                    "officialDecision": official_decision_text,
                    "outcome": "Case Cancelled",
                    "phase3ReferralRequired": True,
                    "phase3RecommendedRoute": system_recommendation,
                    "phase3ReferralId": referral.id,
                    "phase3ReferralStatus": "cancelled",
                    "symbolicConfirmed": False,
                    "referralResolution": {
                        "referralId": referral.id,
                        "status": "cancelled",
                        "destination": referral.destination,
                        "officialDecision": official_decision_text,
                        "resolvedAt": acted_at.isoformat(),
                        "resolvedBy": acted_by,
                        "cancellationReason": cancellation_reason,
                    },
                }
            )
            draft.status = "cancelled"
            audit_action = "workflow_case_cancelled_from_referral"
            message = "The referral and case were cancelled. The workflow is now closed."

        if payload.action != "cancel_referral":
            official_decision = Phase3OfficialDecision(
                case_id=draft.case_id,
                system_recommendation=system_recommendation,
                official_decision=official_decision_text,
                official_notes=official_notes,
                approved_by=acted_by,
                approved_at=acted_at,
                created_at=acted_at,
            )
            db.add(official_decision)

        if payload.action == "cancel_case" and draft.case_analysis_id is not None:
            linked_analysis = db.query(CaseAnalysis).filter(
                CaseAnalysis.id == draft.case_analysis_id
            ).first()
            if linked_analysis is None:
                raise HTTPException(
                    status_code=409,
                    detail="The workflow's linked case analysis was not found.",
                )
            # The query in the snapshot helper flushes the newly-added official
            # decision first, so the terminal record captures its exact ID.
            current_payload["phase3RecordIds"] = workflow_phase3_record_ids(
                db,
                draft,
                linked_analysis,
                end_at=acted_at,
            )

        draft.payload_json = current_payload
        draft.revision += 1
        draft.updated_at = acted_at
        append_audit_log(
            db,
            draft.case_id,
            audit_action,
            {
                "workflow_id": draft.workflow_id,
                "referral_id": referral.id,
                "referral_status": referral.status,
                "destination": referral.destination,
                "official_decision": official_decision_text or None,
                "reason": official_notes,
            },
            actor=context.user.username,
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="The referral action could not be saved atomically.") from exc

    db.refresh(draft)
    db.refresh(referral)
    if official_decision is not None:
        db.refresh(official_decision)
    response = serialize_workflow_draft(draft)
    response.update(
        {
            "message": message,
            "referral": serialize_model(referral),
            "official_decision": serialize_model(official_decision) if official_decision is not None else None,
        }
    )
    return response


@app.post("/api/workflow/consent-files")
async def upload_workflow_consent_file(
    file: UploadFile = File(...),
    party_type: str = Form("general"),
    context: AuthContext = Depends(get_auth_context),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No consent file was uploaded.")

    extension = Path(file.filename).suffix.lower()
    if extension not in {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx"}:
        raise HTTPException(status_code=400, detail="Unsupported consent file format.")

    original_name = safe_upload_name(file.filename)
    consent_id = uuid4().hex
    saved_path = CONSENT_DIR / f"{datetime.utcnow():%Y%m%d%H%M%S}_{consent_id}_{original_name}"

    with saved_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    size_bytes = saved_path.stat().st_size
    if size_bytes > MAX_UPLOAD_MB * 1024 * 1024:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Uploaded consent file exceeds {MAX_UPLOAD_MB} MB limit.")

    return {
        "id": consent_id,
        "file_name": original_name,
        "party_type": party_type,
        "size_bytes": size_bytes,
        "uploaded_by": context.user.username,
        "uploaded_at": datetime.utcnow(),
    }


@app.get("/api/admin/users", response_model=list[UserResponse])
def list_admin_users(
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if "users.manage" not in context.permissions:
        raise HTTPException(status_code=403, detail="You do not have permission for this action.")
    return [serialize_user(user) for user in db.query(User).order_by(User.username.asc()).all()]


@app.post("/api/admin/users", response_model=UserResponse)
def create_admin_user(
    payload: UserCreateRequest,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return serialize_user(create_user(db, payload, context))


@app.patch("/api/admin/users/{user_id}", response_model=UserResponse)
def update_admin_user(
    user_id: int,
    payload: UserUpdateRequest,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return serialize_user(update_user(db, user_id, payload, context))


@app.patch("/api/admin/users/{user_id}/password", response_model=UserResponse)
def update_admin_user_password(
    user_id: int,
    payload: UserPasswordRequest,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return serialize_user(update_user_password(db, user_id, payload, context))


@app.patch("/api/admin/users/{user_id}/status", response_model=UserResponse)
def update_admin_user_status(
    user_id: int,
    payload: UserStatusRequest,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return serialize_user(update_user_status(db, user_id, payload, context))


@app.post("/api/admin/backups/run")
def run_admin_backup(
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return BackupService().run_backup(db, context)


@app.get("/api/admin/backups")
def list_admin_backups(
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return BackupService().list_backups(db, context)


@app.post("/api/admin/backups/enforce-retention")
def enforce_backup_retention(
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return BackupService().enforce_retention(db, context)


@app.get("/api/admin/backups/{backup_id}/download")
def download_admin_backup(
    backup_id: str,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    record = BackupService().backup_file(db, backup_id, context)
    return FileResponse(
        path=record.file_path,
        media_type="application/octet-stream",
        filename=f"{record.backup_id}.jkpbackup",
    )


@app.post("/api/admin/backups/{backup_id}/verify")
def verify_admin_backup(
    backup_id: str,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return BackupService().verify_backup(db, backup_id, context)


@app.post("/api/admin/backups/{backup_id}/restore")
def restore_admin_backup(
    backup_id: str,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return BackupService().restore_backup(db, backup_id, context)


@app.get("/api/kp-forms")
def list_kp_forms():
    return [
        {
            "form_id": kp_form_id(file_path),
            "title": file_path.stem.title().replace("Kp", "KP"),
            "file_name": file_path.name,
            "download_url": f"/api/kp-forms/{kp_form_id(file_path)}/download",
        }
        for file_path in get_kp_form_files()
    ]


@app.get("/api/kp-forms/{form_id}/download")
def download_kp_form(form_id: str, disposition: str = Query("attachment", pattern="^(attachment|inline)$")):
    for file_path in get_kp_form_files():
        if kp_form_id(file_path) == form_id:
            return FileResponse(
                path=file_path,
                media_type="application/pdf",
                filename=file_path.name,
                content_disposition_type=disposition,
            )
    raise HTTPException(status_code=404, detail="KP form template was not found.")


@app.get("/api/phase4/form-templates", response_model=list[Phase4TemplateResponse])
def list_phase4_form_templates():
    return Phase4FormService(GENERATED_FORMS_DIR).registry()


@app.get("/api/phase4/recommendations/{case_id}", response_model=Phase4RecommendationResponse)
def get_phase4_recommendations(
    case_id: str,
    db: Session = Depends(get_db),
    context: AuthContext | None = Depends(get_auth_context),
):
    ensure_case_read_access(
        db,
        case_id,
        context,
        audit_resource_type="phase4_recommendations",
        audit_resource_id=case_id,
    )
    return Phase4FormService(GENERATED_FORMS_DIR).recommendation(db, case_id)


@app.post("/api/phase4/generate-packet/{case_id}", response_model=Phase4PacketResponse)
def generate_phase4_packet(
    case_id: str,
    payload: Phase4GeneratePacketRequest,
    db: Session = Depends(get_db),
):
    ensure_case_is_mutable(db, case_id)
    service = Phase4FormService(GENERATED_FORMS_DIR)
    packet = service.generate_packet(db, case_id, payload)
    return service.packet_response(db, packet)


@app.get("/api/phase4/packets/{case_id}", response_model=list[Phase4PacketResponse])
def get_phase4_packets(
    case_id: str,
    db: Session = Depends(get_db),
    context: AuthContext | None = Depends(get_auth_context),
):
    ensure_case_read_access(db, case_id, context, audit_resource_type="phase4_packets")
    service = Phase4FormService(GENERATED_FORMS_DIR)
    return [service.packet_response(db, packet) for packet in service.packets_for_case(db, case_id)]


@app.get("/api/phase4/generated-forms/{generated_form_id}/download")
def download_generated_phase4_form(
    generated_form_id: int,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    service = Phase4FormService(GENERATED_FORMS_DIR)
    form = service.generated_form_file(db, generated_form_id)
    is_sensitive = ensure_case_read_access(db, form.case_id, context)
    linked_workflow = next(
        (
            draft
            for draft in db.query(WorkflowDraft).order_by(WorkflowDraft.updated_at.desc()).all()
            if (draft.payload_json or {}).get("phase4PacketId") == form.packet_id
        ),
        None,
    )
    if linked_workflow is not None:
        if linked_workflow.owner_user_id != context.user.id and "users.manage" not in context.permissions:
            raise HTTPException(status_code=404, detail="Generated KP form was not found.")

    template_path = service.blank_template_file(form.form_id)
    document_bytes = template_path.read_bytes()
    db.add(
        AuditLog(
            case_id=form.case_id,
            action="generated_form_pdf_downloaded",
            actor=context.user.username,
            actor_user_id=context.user.id,
            actor_role=context.role.name,
            ip_address=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent", "")[:500],
            resource_type="phase4_generated_form",
            resource_id=str(form.id),
            risk_level="moderate" if is_sensitive else "low",
            details_json={
                "workflow_id": linked_workflow.workflow_id if linked_workflow else None,
                "packet_id": form.packet_id,
                "generated_form_id": form.id,
                "form_id": form.form_id,
                "sha256": hashlib.sha256(document_bytes).hexdigest(),
                "byte_length": len(document_bytes),
            },
        )
    )
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="The PDF was not released because its audit record could not be saved.",
        ) from exc
    return FileResponse(
        # Older stored packets may still contain the discontinued attachment.
        path=template_path,
        media_type="application/pdf",
        filename=f"{form.case_id}_{form.form_id}.pdf",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/phase5/dataset", response_model=list[Phase5ValidationCaseResponse])
def get_phase5_dataset(db: Session = Depends(get_db)):
    return Phase5ValidationService().validation_cases(db)


@app.delete("/api/phase5/dataset/{case_id}")
def delete_pending_phase5_case(
    case_id: str,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return Phase5ValidationService().delete_pending_case(
        db,
        case_id,
        actor=context.user.username,
    )


@app.get(
    "/api/phase5/importable-workflows",
    response_model=list[Phase5ImportableWorkflowResponse],
)
def get_importable_phase5_workflows(db: Session = Depends(get_db)):
    return Phase5ValidationService().finalized_workflow_candidates(db)


@app.post(
    "/api/phase5/import-workflow/{workflow_id}",
    response_model=Phase5FinalizedWorkflowImportResponse,
)
def import_finalized_phase5_workflow(
    workflow_id: str,
    payload: Phase5ImportCaseRequest,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return Phase5ValidationService().import_finalized_workflow(
        db,
        workflow_id,
        payload,
        actor=context.user.username,
    )


@app.get("/api/phase5/kp-cases-workbook/summary")
def get_kp_cases_workbook_summary():
    return workbook_summary()


@app.post("/api/phase5/import-kp-cases-workbook")
def import_kp_cases_workbook_endpoint(
    limit: int | None = None,
    skip_existing: bool = True,
    db: Session = Depends(get_db),
):
    if limit is not None and limit < 1:
        raise HTTPException(status_code=400, detail="limit must be greater than zero.")
    return import_kp_cases_workbook(db, limit=limit, skip_existing=skip_existing)


@app.post("/api/phase5/import-case/{case_id}", response_model=Phase5ValidationCaseResponse)
def import_phase5_case(
    case_id: str,
    payload: Phase5ImportCaseRequest,
    db: Session = Depends(get_db),
):
    return Phase5ValidationService().import_case(db, case_id, payload)


@app.patch("/api/phase5/ground-truth/{case_id}")
def update_phase5_ground_truth(
    case_id: str,
    payload: Phase5GroundTruthRequest,
    db: Session = Depends(get_db),
):
    return Phase5ValidationService().update_ground_truth(db, case_id, payload)


@app.patch("/api/phase5/compliance/{case_id}")
def update_phase5_compliance(
    case_id: str,
    payload: Phase5ComplianceReviewRequest,
    db: Session = Depends(get_db),
):
    return Phase5ValidationService().update_compliance(db, case_id, payload)


@app.post("/api/phase5/evaluate/{case_id}", response_model=Phase5EvaluationResponse)
def evaluate_phase5_case(case_id: str, db: Session = Depends(get_db)):
    return Phase5ValidationService().evaluate_case(db, case_id)


@app.post("/api/phase5/evaluate-all", response_model=list[Phase5EvaluationResponse])
def evaluate_all_phase5_cases(db: Session = Depends(get_db)):
    return Phase5ValidationService().evaluate_all(db)


@app.get("/api/phase5/metrics", response_model=Phase5MetricsResponse)
def get_phase5_metrics(db: Session = Depends(get_db)):
    return Phase5ValidationService().metrics(db)


@app.post("/api/phase5/experiment-runs", response_model=Phase5ExperimentRunResponse)
def create_phase5_experiment_run(
    payload: Phase5ExperimentRunRequest,
    db: Session = Depends(get_db),
):
    return Phase5ValidationService().create_experiment_run(db, payload)


@app.get("/api/phase5/experiment-runs", response_model=list[Phase5ExperimentRunResponse])
def get_phase5_experiment_runs(db: Session = Depends(get_db)):
    return Phase5ValidationService().experiment_runs(db)


@app.get("/api/phase5/export/csv")
def export_phase5_csv(db: Session = Depends(get_db)):
    return Response(
        content=Phase5ValidationService().csv_export(db),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=justice-kp-phase5-validation.csv"},
    )


@app.get("/api/phase5/export/anonymized.csv")
def export_phase5_anonymized_csv(db: Session = Depends(get_db)):
    return Response(
        content=Phase5ValidationService().csv_export(db, anonymized=True),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=justice-kp-phase5-validation-anonymized.csv"},
    )


@app.get("/api/phase5/export/report", response_class=PlainTextResponse)
def export_phase5_report(db: Session = Depends(get_db)):
    return Phase5ValidationService().report_text(db)


@app.get("/api/phase5/export/report.pdf")
def export_phase5_pdf_report(db: Session = Depends(get_db)):
    return Response(
        content=Phase5ValidationService().report_pdf(db),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=justice-kp-phase5-validation-report.pdf"},
    )


@app.get("/api/phase5/export/anonymized-report.pdf")
def export_phase5_anonymized_pdf_report(db: Session = Depends(get_db)):
    return Response(
        content=Phase5ValidationService().report_pdf(db, anonymized=True),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=justice-kp-phase5-validation-report-anonymized.pdf"},
    )


@app.get("/api/audio/{filename}")
def stream_uploaded_audio(
    filename: str,
    context: AuthContext = Depends(get_auth_context),
):
    del context
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=404, detail="Audio recording was not found.")

    audio_path = UPLOAD_DIR / safe_name
    if not audio_path.is_file():
        raise HTTPException(status_code=404, detail="Audio recording was not found.")

    media_types = {
        ".m4a": "audio/mp4",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
        ".webm": "audio/webm",
    }
    return FileResponse(
        audio_path,
        media_type=media_types.get(audio_path.suffix.lower(), "application/octet-stream"),
        headers={"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"},
    )


@app.post("/upload")
def upload_audio(
    file: UploadFile = File(...),
    speaker_count: int = Form(0),
    recording_type: str = Form("blotter_hearing"),
    workflow_id: str = Form(""),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No audio file was uploaded.")

    extension = Path(file.filename).suffix.lower() or ".webm"
    if extension not in {".webm", ".wav", ".mp3", ".m4a", ".ogg"}:
        raise HTTPException(status_code=400, detail="Unsupported audio format.")

    canonical_workflow_id = workflow_id.strip()
    upload_token = ""
    if canonical_workflow_id:
        draft = locked_owned_workflow_draft(db, canonical_workflow_id, context)
        draft_payload = dict(draft.payload_json or {})
        existing_audio = draft.audio_filename or str(draft_payload.get("blotterAudioFilename") or "").strip()
        if existing_audio:
            raise HTTPException(
                status_code=409,
                detail="This workflow already has an audio record. Start Recording and Upload Audio are permanently disabled for this draft.",
            )
        if draft.audio_upload_token:
            raise HTTPException(
                status_code=409,
                detail="An audio record is already being processed for this workflow.",
            )

        # Reserve this workflow before performing the slower ASR work. The
        # conditional update also prevents two browser tabs from both winning.
        upload_token = uuid4().hex
        reserved = (
            db.query(WorkflowDraft)
            .filter(
                WorkflowDraft.id == draft.id,
                WorkflowDraft.audio_filename == "",
                WorkflowDraft.audio_upload_token == "",
            )
            .update({WorkflowDraft.audio_upload_token: upload_token}, synchronize_session=False)
        )
        if reserved != 1:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="An audio record already exists or is being processed for this workflow.",
            )
        db.commit()

    saved_path = UPLOAD_DIR / f"{datetime.utcnow():%Y%m%d%H%M%S}_{uuid4().hex}{extension}"
    processing_path = str(saved_path)
    try:
        with saved_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        if saved_path.stat().st_size > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"Uploaded audio exceeds {MAX_UPLOAD_MB} MB limit.")

        warnings = []
        learned_corrections = get_learned_corrections(db)
        expected_speakers = speaker_count_for_recording_type(recording_type, speaker_count)

        try:
            processing_path = convert_to_wav(str(saved_path))
        except Exception as exc:
            processing_path = str(saved_path)
            warnings.append(f"Audio cleanup failed, using original upload. Detail: {exc}")
        processing_file = Path(processing_path)
        audio_duration_seconds = wav_duration_seconds(processing_path)
        playback_filename = (
            processing_file.name
            if processing_file.is_file() and processing_file.parent.resolve() == UPLOAD_DIR.resolve()
            else saved_path.name
        )

        try:
            transcription_segments = transcribe_audio(processing_path)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Speech-to-text failed. Check that FFmpeg is installed and that "
                    f"the uploaded audio is valid. Technical detail: {exc}"
                ),
            ) from exc

        if not transcription_segments:
            labeled = []
            metrics = {"asr_confidence": None, "diarization_quality": 0.0, "detected_speakers": 0}
            warnings.append(
                "No speech was detected. The audio record was retained; add transcript segments manually if needed."
            )
        else:
            try:
                if expected_speakers and not has_diarization_token():
                    warnings.append("No Hugging Face token was loaded, so speaker detection used Speaker 1 fallback.")
                diarization_segments = diarize_audio(
                    processing_path,
                    max_speakers=3,
                    speaker_count=expected_speakers,
                )
            except Exception as exc:
                # ASR is the most important Phase 1 path. If pyannote is not configured
                # or FFmpeg/torchcodec fails locally, still return an editable transcript.
                warnings.append(f"Speaker diarization failed, using Speaker 1 fallback. Detail: {exc}")
                diarization_segments = [{"speaker": "Speaker 1", "start": 0.0, "end": 999999.0}]

            merged = normalize_segments(
                merge_transcript_and_speakers(transcription_segments, diarization_segments),
                learned_corrections=learned_corrections,
            )
            labeled = assign_role_labels(merged, recording_type)
            append_recording_quality_warnings(labeled, expected_speakers, audio_duration_seconds, warnings)
            metrics = transcript_quality_metrics(labeled, expected_speakers, warnings)
            if expected_speakers in {2, 3} and metrics["detected_speakers"] == 1:
                warnings.append(
                    "Only one speaker was detected. Use the editable transcript to correct speaker roles if needed."
                )
                metrics = transcript_quality_metrics(labeled, expected_speakers, warnings)

        if canonical_workflow_id:
            draft = locked_owned_workflow_draft(db, canonical_workflow_id, context)
            if draft.audio_upload_token != upload_token:
                raise HTTPException(status_code=409, detail="The workflow audio reservation expired. Refresh the draft.")
            draft_payload = dict(draft.payload_json or {})
            draft.audio_filename = playback_filename
            draft.audio_duration_seconds = audio_duration_seconds
            draft.audio_upload_token = ""
            draft_payload["blotterAudioFilename"] = playback_filename
            draft_payload["blotterDurationSeconds"] = audio_duration_seconds or 0
            draft.payload_json = draft_payload
            draft.updated_at = datetime.utcnow()
            db.commit()

        return {
            "filename": saved_path.name,
            "playback_filename": playback_filename,
            "audio_duration_seconds": audio_duration_seconds,
            "provider": "local",
            "recording_type": recording_type,
            "expected_speakers": expected_speakers,
            "transcript": labeled,
            "asr_confidence": metrics["asr_confidence"],
            "diarization_quality": metrics["diarization_quality"],
            "detected_speakers": metrics["detected_speakers"],
            "accuracy_metrics": metrics,
            "warnings": warnings,
        }
    except Exception:
        saved_path.unlink(missing_ok=True)
        converted_path = Path(processing_path)
        if converted_path != saved_path and converted_path.parent.resolve() == UPLOAD_DIR.resolve():
            converted_path.unlink(missing_ok=True)
        if canonical_workflow_id and upload_token:
            db.rollback()
            reserved_draft = db.query(WorkflowDraft).filter(WorkflowDraft.workflow_id == canonical_workflow_id).first()
            if reserved_draft and reserved_draft.audio_upload_token == upload_token:
                reserved_draft.audio_upload_token = ""
                db.commit()
        raise


@app.post("/transcript-corrections/learn")
def learn_transcript_corrections(payload: LearnTranscriptCorrectionsRequest, db: Session = Depends(get_db)):
    edited_segments = parse_edited_transcript(payload.content)
    corrections = extract_phrase_corrections(payload.segments, edited_segments)
    learned_count = save_phrase_corrections(db, corrections)
    return {
        "message": "Transcript corrections learned.",
        "learned_corrections": learned_count,
    }


def transcript_segments_from_json(value: Any) -> List[TranscriptSegment]:
    parsed: List[TranscriptSegment] = []
    if not isinstance(value, list):
        return parsed
    for item in value:
        try:
            parsed.append(TranscriptSegment.model_validate(item))
        except (TypeError, ValueError):
            # A malformed historical segment must not destroy the otherwise
            # valid raw evidentiary transcript.  It remains stored unchanged.
            continue
    return parsed


def workflow_case_id(draft: WorkflowDraft) -> str:
    payload = dict(draft.payload_json or {})
    case_information = dict(payload.get("caseInformation") or {})
    return (draft.case_id or str(case_information.get("case_id") or "")).strip()


def locked_owned_workflow_draft(
    db: Session,
    workflow_id: str,
    context: AuthContext,
) -> WorkflowDraft:
    draft = (
        db.query(WorkflowDraft)
        .filter(WorkflowDraft.workflow_id == workflow_id)
        .with_for_update()
        .first()
    )
    if not draft:
        raise HTTPException(status_code=404, detail="Workflow draft was not found.")
    if draft.owner_user_id != context.user.id and "users.manage" not in context.permissions:
        raise HTTPException(status_code=404, detail="Workflow draft was not found.")
    ensure_workflow_is_mutable(draft)
    return draft


def canonical_transcript_for_draft(
    db: Session,
    draft: WorkflowDraft,
    case_id: str,
    context: AuthContext,
) -> Transcript | None:
    # First reuse a record already carrying an explicit canonical identity.
    transcript = (
        db.query(Transcript)
        .filter(
            Transcript.workflow_id == draft.workflow_id,
            Transcript.superseded_by_transcript_id.is_(None),
        )
        .first()
    )
    if not transcript and case_id:
        transcript = (
            db.query(Transcript)
            .filter(
                Transcript.case_id == case_id,
                Transcript.superseded_by_transcript_id.is_(None),
            )
            .first()
        )
        if transcript and transcript.workflow_id != draft.workflow_id:
            owner_draft = (
                db.query(WorkflowDraft)
                .filter(
                    (WorkflowDraft.workflow_id == transcript.workflow_id)
                    | (WorkflowDraft.transcript_id == transcript.id)
                )
                .order_by(WorkflowDraft.updated_at.desc())
                .first()
            )
            if (
                "users.manage" not in context.permissions
                and (not owner_draft or owner_draft.owner_user_id != context.user.id)
            ):
                raise HTTPException(
                    status_code=409,
                    detail="This case ID is already assigned to another workflow.",
                )

    # An exact case may be resumed through another draft.  Reuse its canonical
    # transcript, but never expose another user's draft through this lookup.
    if not transcript and case_id:
        same_case_query = db.query(WorkflowDraft).filter(
            WorkflowDraft.case_id == case_id,
            WorkflowDraft.workflow_id != draft.workflow_id,
            WorkflowDraft.transcript_id.is_not(None),
        )
        if "users.manage" not in context.permissions:
            same_case_query = same_case_query.filter(WorkflowDraft.owner_user_id == context.user.id)
        same_case_draft = same_case_query.order_by(WorkflowDraft.updated_at.desc()).first()
        if same_case_draft:
            transcript = (
                db.query(Transcript)
                .filter(
                    Transcript.id == same_case_draft.transcript_id,
                    Transcript.superseded_by_transcript_id.is_(None),
                )
                .first()
            )

    if transcript:
        return transcript

    # Legacy drafts predate workflow_id/case_id on Transcript.  Their
    # authoritative relationship is WorkflowDraft.transcript_id.  Do not use
    # payload.hearingTranscriptId: deleted SQLite IDs could historically be
    # reused by a different case.
    if not draft.transcript_id:
        return None
    candidate = db.query(Transcript).filter(Transcript.id == draft.transcript_id).first()
    if not candidate or candidate.superseded_by_transcript_id is not None:
        return None

    conflicting_draft = (
        db.query(WorkflowDraft)
        .filter(
            WorkflowDraft.transcript_id == candidate.id,
            WorkflowDraft.workflow_id != draft.workflow_id,
        )
        .first()
    )
    if conflicting_draft and workflow_case_id(conflicting_draft).casefold() != case_id.casefold():
        # The numeric ID was reused after a legacy delete.  Treat the link as
        # stale rather than overwriting the other case's transcript.
        return None
    if candidate.workflow_id and candidate.workflow_id != draft.workflow_id:
        if not case_id or (candidate.case_id or "").casefold() != case_id.casefold():
            return None
    if candidate.case_id and case_id and candidate.case_id.casefold() != case_id.casefold():
        return None
    return candidate


def supersede_legacy_hearing_transcript(
    db: Session,
    draft: WorkflowDraft,
    canonical: Transcript,
) -> int | None:
    draft_payload = dict(draft.payload_json or {})
    hearing_id = draft_payload.get("hearingTranscriptId")
    if not isinstance(hearing_id, int) or isinstance(hearing_id, bool) or hearing_id == canonical.id:
        return None

    legacy = db.query(Transcript).filter(Transcript.id == hearing_id).first()
    if not legacy:
        return None
    other_owner = (
        db.query(WorkflowDraft)
        .filter(
            WorkflowDraft.transcript_id == hearing_id,
            WorkflowDraft.workflow_id != draft.workflow_id,
        )
        .first()
    )
    if other_owner:
        # This is a stale reused ID, not a duplicate belonging to this case.
        return None
    if legacy.workflow_id and legacy.workflow_id != draft.workflow_id:
        return None
    if legacy.case_id and canonical.case_id and legacy.case_id != canonical.case_id:
        return None

    legacy.superseded_by_transcript_id = canonical.id
    legacy.updated_at = datetime.utcnow()
    return legacy.id


@app.post("/save-transcript")
def save_transcript(
    payload: SaveTranscriptRequest,
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    request_workflow_id = payload.workflow_id.strip()
    request_case_id = payload.case_id.strip()
    auth_context = context if isinstance(context, AuthContext) else None
    if payload.save_context != "standalone" and not request_workflow_id:
        raise HTTPException(
            status_code=400,
            detail="workflow_id is required when saving an intake or hearing transcript.",
        )

    draft: WorkflowDraft | None = None
    canonical_case_id = ""
    transcript: Transcript | None = None
    if request_workflow_id:
        if not auth_context:
            raise HTTPException(status_code=401, detail="Authentication is required for a workflow transcript.")
        draft = locked_owned_workflow_draft(db, request_workflow_id, auth_context)
        canonical_case_id = workflow_case_id(draft)
        if request_case_id and canonical_case_id and request_case_id.casefold() != canonical_case_id.casefold():
            raise HTTPException(
                status_code=409,
                detail="The transcript case ID does not match the selected workflow.",
            )
        canonical_case_id = canonical_case_id or request_case_id
        transcript = canonical_transcript_for_draft(db, draft, canonical_case_id, auth_context)

    operation = "updated" if transcript else "created"
    if transcript is None:
        transcript = Transcript(
            workflow_id=request_workflow_id or None,
            case_id=canonical_case_id or None,
            save_context=payload.save_context,
            content=payload.content,
            raw_content="",
            segments_json=[],
            raw_segments_json=[],
            corrections_json=[],
            accuracy_metrics_json={},
        )
        db.add(transcript)
        try:
            # Detect the unique workflow/case invariant before learning phrase
            # corrections so a failed concurrent insert leaves no side effect.
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="This case transcript changed while it was being saved. Refresh and try again.",
            ) from exc
    else:
        if not transcript.workflow_id:
            transcript.workflow_id = request_workflow_id or None
        if not transcript.case_id:
            transcript.case_id = canonical_case_id or None

    has_explicit_edited_segments = bool(payload.edited_segments)
    edited_segments = (
        [segment.model_copy(deep=True) for segment in payload.edited_segments]
        if has_explicit_edited_segments
        else parse_edited_transcript(payload.content)
    )

    preserve_raw = operation == "updated" and payload.save_context == "hearing"
    canonical_raw_segments = (
        transcript_segments_from_json(transcript.raw_segments_json)
        if preserve_raw and transcript.raw_segments_json
        else [segment.model_copy(deep=True) for segment in payload.segments]
    )
    if not has_explicit_edited_segments and edited_segments and len(edited_segments) == len(canonical_raw_segments):
        for edited_segment, original_segment in zip(edited_segments, canonical_raw_segments):
            edited_segment.start = original_segment.start
            edited_segment.end = original_segment.end
            edited_segment.confidence = original_segment.confidence

    correction_metrics = correction_summary(canonical_raw_segments, edited_segments, payload.content)
    stored_segments = edited_segments if edited_segments else payload.segments
    corrections = unique_phrase_corrections(extract_phrase_corrections(canonical_raw_segments, edited_segments))
    # Keep learned corrections and the transcript in one database transaction.
    learned_count = save_phrase_corrections(db, corrections, commit=False)

    detected_speakers = len({segment.speaker for segment in stored_segments if segment.speaker})
    asr_confidence = payload.asr_confidence
    if asr_confidence is None:
        asr_confidence = average_segment_confidence(canonical_raw_segments)
    if preserve_raw and asr_confidence is None:
        asr_confidence = transcript.asr_confidence
    provider = payload.provider or (transcript.asr_provider if preserve_raw else "")
    diarization_quality = (
        payload.diarization_quality
        if payload.diarization_quality is not None
        else transcript.diarization_quality if preserve_raw else None
    )
    expected_speakers = (
        payload.expected_speakers
        if payload.expected_speakers is not None
        else transcript.expected_speakers if preserve_raw else None
    )
    existing_accuracy_metrics = dict(transcript.accuracy_metrics_json or {}) if preserve_raw else {}
    accuracy_metrics = {
        **existing_accuracy_metrics,
        **payload.accuracy_metrics,
        **correction_metrics,
        "asr_provider": provider,
        "asr_confidence": asr_confidence,
        "diarization_quality": diarization_quality,
        "expected_speakers": expected_speakers,
        "detected_speakers": detected_speakers,
        "recording_type": payload.recording_type,
        "workflow_id": request_workflow_id or None,
        "case_id": canonical_case_id or None,
        "latest_save_context": payload.save_context,
    }

    transcript.content = payload.content
    if not preserve_raw or not transcript.raw_content:
        transcript.raw_content = (
            format_transcript_segments(canonical_raw_segments)
            if canonical_raw_segments
            else payload.content
        )
        transcript.raw_segments_json = [segment.model_dump() for segment in canonical_raw_segments]
    transcript.segments_json = [segment.model_dump() for segment in stored_segments]
    # The transcript row describes raw-versus-current-edited accuracy only.
    # Historical learned mappings remain in PhraseCorrection for future ASR.
    transcript.corrections_json = correction_records(corrections)
    transcript.asr_provider = provider
    transcript.asr_confidence = asr_confidence
    transcript.diarization_quality = diarization_quality
    transcript.manual_correction_rate = correction_metrics["manual_correction_rate"]
    transcript.correction_count = correction_metrics["correction_count"]
    transcript.original_word_count = correction_metrics["original_word_count"]
    transcript.edited_word_count = correction_metrics["edited_word_count"]
    transcript.expected_speakers = expected_speakers
    transcript.detected_speakers = detected_speakers
    transcript.recording_type = payload.recording_type or transcript.recording_type
    transcript.save_context = payload.save_context
    transcript.accuracy_metrics_json = accuracy_metrics
    transcript.updated_at = datetime.utcnow()

    superseded_id = None
    if draft:
        superseded_id = supersede_legacy_hearing_transcript(db, draft, transcript)
        draft.transcript_id = transcript.id
        draft.case_id = canonical_case_id
        draft_payload = dict(draft.payload_json or {})
        draft_payload["transcriptId"] = transcript.id
        if payload.save_context == "hearing":
            draft_payload["hearingTranscriptId"] = transcript.id
            draft_payload["hearingRecorded"] = True
            draft_payload["hearingSavedAt"] = transcript.updated_at.isoformat()
        elif payload.save_context == "intake":
            draft_payload["hearingTranscriptId"] = None
            draft_payload["hearingRecorded"] = False
            draft_payload["hearingSavedAt"] = ""
        if superseded_id:
            superseded_ids = {
                item
                for item in draft_payload.get("supersededTranscriptIds", [])
                if isinstance(item, int) and not isinstance(item, bool)
            }
            superseded_ids.add(superseded_id)
            draft_payload["supersededTranscriptIds"] = sorted(superseded_ids)
        draft.payload_json = draft_payload

        append_audit_log(
            db,
            canonical_case_id,
            f"workflow_transcript_{operation}",
            {
                "transcript_id": transcript.id,
                "workflow_id": draft.workflow_id,
                "save_context": payload.save_context,
                "superseded_transcript_id": superseded_id,
            },
            actor=auth_context.user.username if auth_context else "system",
        )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This case already has a canonical transcript. Refresh and try again.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="The transcript could not be saved to the database. No partial transcript was stored.",
        ) from exc
    db.refresh(transcript)

    text_path = TRANSCRIPT_DIR / f"transcript_{transcript.id}.txt"
    sidecar_warning = ""
    try:
        text_path.write_text(payload.content, encoding="utf-8")
    except OSError:
        # The database is the source of truth; an optional text export failure
        # must not make a successful database save look unsuccessful.
        sidecar_warning = "The transcript was saved, but its optional text-file copy could not be written."

    return {
        "message": "Transcript saved successfully." if operation == "created" else "Transcript updated successfully.",
        "id": transcript.id,
        "operation": operation,
        "workflow_id": request_workflow_id or None,
        "case_id": canonical_case_id or None,
        "save_context": payload.save_context,
        "workflow_revision": draft.revision if draft else None,
        "created_at": transcript.created_at,
        "updated_at": transcript.updated_at,
        "learned_corrections": learned_count,
        "accuracy_metrics": accuracy_metrics,
        "warning": sidecar_warning,
    }


def parsed_client_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None)
    except ValueError:
        return None


def canonical_transcript_listing(
    db: Session,
) -> list[tuple[Transcript, dict[str, Any]]]:
    """Return one visible record per exact workflow case without deleting history.

    Legacy Stage 2 saves inserted a second row and kept its ID only in
    payload.hearingTranscriptId.  We collapse only IDs connected by the same
    WorkflowDraft/case.  A timestamp/ownership check prevents a deleted ID
    later reused by another case from being merged into the wrong transcript.
    """

    research_transcript_ids = {
        transcript_id
        for (transcript_id,) in (
            db.query(CaseAnalysis.transcript_id)
            .join(Phase5ValidationCase, Phase5ValidationCase.analysis_id == CaseAnalysis.id)
            .filter(CaseAnalysis.transcript_id.isnot(None))
            .all()
        )
        if transcript_id is not None
    }
    transcripts = (
        db.query(Transcript)
        .filter(Transcript.superseded_by_transcript_id.is_(None))
        .all()
    )
    drafts = db.query(WorkflowDraft).all()
    workflow_transcript_ids: set[int] = set()
    for draft in drafts:
        if isinstance(draft.transcript_id, int) and not isinstance(draft.transcript_id, bool):
            workflow_transcript_ids.add(draft.transcript_id)
        draft_payload = dict(draft.payload_json or {})
        for key in ("transcriptId", "hearingTranscriptId", "canonicalTranscriptId"):
            value = draft_payload.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                workflow_transcript_ids.add(value)
    # Workbook imports are validation/research evidence, not operational saved
    # transcripts. An operational workflow later imported into Phase 5 keeps
    # its explicit identity or draft reference and remains visible.
    by_id = {
        item.id: item
        for item in transcripts
        if not (
            item.id in research_transcript_ids
            and not item.workflow_id
            and not item.case_id
            and item.id not in workflow_transcript_ids
        )
    }
    authoritative_owner = {
        draft.transcript_id: draft.workflow_id
        for draft in drafts
        if isinstance(draft.transcript_id, int) and not isinstance(draft.transcript_id, bool)
    }

    grouped_ids: dict[str, set[int]] = {}
    metadata_by_id: dict[int, dict[str, Any]] = {}
    for draft in drafts:
        case_id = workflow_case_id(draft)
        # A case ID is not globally unique in historical data. Collapse only
        # transcript rows belonging to this exact workflow so two old records
        # sharing a displayed case ID remain independently navigable.
        group_key = f"workflow:{draft.workflow_id}"
        ids = grouped_ids.setdefault(group_key, set())
        canonical_id = draft.transcript_id
        if isinstance(canonical_id, int) and canonical_id in by_id:
            ids.add(canonical_id)
            metadata_by_id[canonical_id] = {
                "workflow_id": draft.workflow_id,
                "case_id": case_id or None,
                "save_context": by_id[canonical_id].save_context or "intake",
            }

        draft_payload = dict(draft.payload_json or {})
        hearing_id = draft_payload.get("hearingTranscriptId")
        if (
            isinstance(hearing_id, int)
            and not isinstance(hearing_id, bool)
            and hearing_id != canonical_id
            and hearing_id in by_id
            and authoritative_owner.get(hearing_id) in {None, draft.workflow_id}
        ):
            hearing_saved_at = parsed_client_datetime(draft_payload.get("hearingSavedAt"))
            hearing_created_at = by_id[hearing_id].created_at
            same_historical_save = bool(
                hearing_saved_at
                and hearing_created_at
                and abs((hearing_created_at - hearing_saved_at).total_seconds()) <= 600
            )
            explicit_identity_match = bool(
                by_id[hearing_id].workflow_id == draft.workflow_id
                or (case_id and by_id[hearing_id].case_id == case_id)
            )
            if same_historical_save or explicit_identity_match:
                ids.add(hearing_id)
                metadata_by_id[hearing_id] = {
                    "workflow_id": draft.workflow_id,
                    "case_id": case_id or None,
                    "save_context": "hearing",
                }

    visible_ids = set(by_id)
    for ids in grouped_ids.values():
        present = [by_id[transcript_id] for transcript_id in ids if transcript_id in by_id]
        if len(present) < 2:
            continue
        selected = max(
            present,
            key=lambda item: (item.updated_at or item.created_at or datetime.min, item.id),
        )
        visible_ids.difference_update(item.id for item in present if item.id != selected.id)

    visible = [by_id[item_id] for item_id in visible_ids]
    # Transcript navigation is chronological by record number: the earliest
    # remaining canonical ID appears first and pagination continues upward.
    visible.sort(key=lambda item: item.id)
    result: list[tuple[Transcript, dict[str, Any]]] = []
    for transcript in visible:
        metadata = metadata_by_id.get(transcript.id, {})
        result.append(
            (
                transcript,
                {
                    "workflow_id": transcript.workflow_id or metadata.get("workflow_id"),
                    "case_id": transcript.case_id or metadata.get("case_id"),
                    "save_context": (
                        metadata.get("save_context")
                        if not transcript.workflow_id and not transcript.case_id and metadata
                        else transcript.save_context
                    ) or "standalone",
                },
            )
        )
    return result


def _transcript_workflow(
    db: Session,
    transcript: Transcript,
    metadata: dict[str, Any],
) -> WorkflowDraft | None:
    workflow_id = str(metadata.get("workflow_id") or transcript.workflow_id or "").strip()
    if workflow_id:
        draft = db.query(WorkflowDraft).filter(WorkflowDraft.workflow_id == workflow_id).first()
        if draft is not None:
            return draft
    draft = (
        db.query(WorkflowDraft)
        .filter(WorkflowDraft.transcript_id == transcript.id)
        .order_by(WorkflowDraft.updated_at.desc(), WorkflowDraft.id.desc())
        .first()
    )
    if draft is not None:
        return draft
    case_id = str(metadata.get("case_id") or transcript.case_id or "").strip()
    if not case_id:
        return None
    return (
        db.query(WorkflowDraft)
        .filter(WorkflowDraft.case_id == case_id)
        .order_by(WorkflowDraft.updated_at.desc(), WorkflowDraft.id.desc())
        .first()
    )


def _can_access_transcript(
    db: Session,
    transcript: Transcript,
    metadata: dict[str, Any],
    context: Any,
) -> bool:
    # Internal callers and legacy unit tests intentionally omit an HTTP auth
    # context.  Requests always receive an AuthContext from middleware.
    if not isinstance(context, AuthContext):
        return True
    draft = _transcript_workflow(db, transcript, metadata)
    if draft is None:
        return True
    if draft.owner_user_id != context.user.id and "users.manage" not in context.permissions:
        return False
    if _workflow_is_sensitive(db, draft) and "sensitive_case.read" not in context.permissions:
        return False
    return True


def serialize_transcript_summary(
    transcript: Transcript,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": transcript.id,
        "workflow_id": metadata["workflow_id"],
        "case_id": metadata["case_id"],
        "save_context": metadata["save_context"],
        "asr_provider": transcript.asr_provider,
        "asr_confidence": transcript.asr_confidence,
        "diarization_quality": transcript.diarization_quality,
        "manual_correction_rate": normalized_correction_rate(transcript),
        "recording_type": transcript.recording_type,
        "expected_speakers": transcript.expected_speakers,
        "detected_speakers": transcript.detected_speakers,
        "segment_count": len(transcript.segments_json or []),
        "correction_count": len(transcript.corrections_json or []),
        "created_at": transcript.created_at,
        "updated_at": transcript.updated_at or transcript.created_at,
    }


def serialize_transcript_detail(
    transcript: Transcript,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    accuracy_metrics = dict(transcript.accuracy_metrics_json or {})
    calculated_metrics = comparison_metrics_from_counts(
        transcript.original_word_count,
        transcript.edited_word_count,
        transcript.correction_count,
    )
    for key, value in calculated_metrics.items():
        if accuracy_metrics.get(key) is None:
            accuracy_metrics[key] = value
    return {
        **serialize_transcript_summary(transcript, metadata),
        "content": transcript.content,
        "raw_content": transcript.raw_content or transcript.content,
        "segments": transcript.segments_json or [],
        "raw_segments": transcript.raw_segments_json or [],
        "corrections": transcript.corrections_json or [],
        "accuracy_metrics": accuracy_metrics,
    }


def transcript_matches_search(
    transcript: Transcript,
    metadata: dict[str, Any],
    normalized_query: str,
) -> bool:
    if not normalized_query:
        return True
    searchable_values = (
        transcript.id,
        f"Transcript {transcript.id}",
        metadata["workflow_id"],
        metadata["case_id"],
        metadata["save_context"],
        transcript.content,
        transcript.raw_content,
        transcript.asr_provider,
        transcript.recording_type,
    )
    return any(
        normalized_query in _normalize_case_filter(str(value or ""))
        for value in searchable_values
    )


@app.get("/transcripts")
def get_transcripts(
    db: Session = Depends(get_db),
    q: str = "",
    page: int = 1,
    page_size: int = 10,
    context: AuthContext | None = Depends(get_auth_context),
):
    if page < 1:
        raise HTTPException(status_code=422, detail="Page must be at least 1.")
    if page_size < 1 or page_size > 50:
        raise HTTPException(status_code=422, detail="Page size must be between 1 and 50.")
    if len(q) > 200:
        raise HTTPException(status_code=422, detail="Search must be 200 characters or fewer.")

    transcripts = [
        (item, metadata)
        for item, metadata in canonical_transcript_listing(db)
        if _can_access_transcript(db, item, metadata, context)
    ]
    normalized_query = _normalize_case_filter(q)
    filtered = [
        (item, metadata)
        for item, metadata in transcripts
        if transcript_matches_search(item, metadata, normalized_query)
    ]
    total = len(filtered)
    total_pages = (total + page_size - 1) // page_size
    valid_page = min(page, total_pages) if total_pages else 1
    start = (valid_page - 1) * page_size
    return {
        "items": [
            serialize_transcript_summary(item, metadata)
            for item, metadata in filtered[start:start + page_size]
        ],
        "page": valid_page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


@app.delete("/transcripts/{transcript_id}")
def delete_transcript(
    transcript_id: int,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    transcript = db.query(Transcript).filter(Transcript.id == transcript_id).first()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript was not found.")
    metadata = {
        "workflow_id": transcript.workflow_id,
        "case_id": transcript.case_id,
        "save_context": transcript.save_context,
    }
    if not _can_access_transcript(db, transcript, metadata, context):
        raise HTTPException(status_code=404, detail="Transcript was not found.")

    linked_analysis_ids = {
        row[0]
        for row in db.query(CaseAnalysis.id).filter(CaseAnalysis.transcript_id == transcript_id).all()
    }
    protected_workflow = None
    for draft in db.query(WorkflowDraft).filter(WorkflowDraft.status.in_(["completed", "cancelled"])).all():
        payload = dict(draft.payload_json or {})
        payload_transcript_ids = {
            value
            for key in ("transcriptId", "hearingTranscriptId", "canonicalTranscriptId")
            if isinstance((value := payload.get(key)), int) and not isinstance(value, bool)
        }
        if not is_finalized_workflow(draft):
            continue
        if (
            draft.transcript_id == transcript_id
            or draft.case_analysis_id in linked_analysis_ids
            or transcript_id in payload_transcript_ids
        ):
            protected_workflow = draft
            break
    if protected_workflow is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "This transcript belongs to a completed case and is protected from ordinary deletion. "
                "Use an authorized retention action when one is approved and available."
            ),
        )

    case_information_count = db.query(CaseInformation).filter(CaseInformation.transcript_id == transcript_id).update(
        {CaseInformation.transcript_id: None}, synchronize_session=False
    )
    analysis_count = db.query(CaseAnalysis).filter(CaseAnalysis.transcript_id == transcript_id).update(
        {CaseAnalysis.transcript_id: None}, synchronize_session=False
    )
    entity_count = db.query(ExtractedEntities).filter(ExtractedEntities.transcript_id == transcript_id).update(
        {ExtractedEntities.transcript_id: None}, synchronize_session=False
    )

    linked_drafts: list[WorkflowDraft] = []
    for draft in db.query(WorkflowDraft).all():
        draft_payload = dict(draft.payload_json or {})
        changed = False
        if draft.transcript_id == transcript_id:
            draft.transcript_id = None
            changed = True
        for key in ["transcriptId", "hearingTranscriptId", "canonicalTranscriptId"]:
            if draft_payload.get(key) == transcript_id:
                draft_payload[key] = None
                changed = True
        if draft_payload.get("hearingTranscriptId") is None and (
            draft_payload.get("hearingRecorded") or draft_payload.get("hearingSavedAt")
        ):
            draft_payload["hearingRecorded"] = False
            draft_payload["hearingSavedAt"] = ""
            changed = True
        superseded_ids = draft_payload.get("supersededTranscriptIds")
        if isinstance(superseded_ids, list) and transcript_id in superseded_ids:
            draft_payload["supersededTranscriptIds"] = [item for item in superseded_ids if item != transcript_id]
            changed = True
        if not changed:
            continue
        linked_drafts.append(draft)
        draft.payload_json = draft_payload
        draft.revision += 1
        draft.updated_at = datetime.utcnow()

    db.delete(transcript)
    db.commit()
    (TRANSCRIPT_DIR / f"transcript_{transcript_id}.txt").unlink(missing_ok=True)

    return {
        "message": f"Transcript #{transcript_id} deleted.",
        "id": transcript_id,
        "detached_references": case_information_count + analysis_count + entity_count + len(linked_drafts),
    }


@app.get("/transcripts/accuracy-report")
def transcript_accuracy_report(
    db: Session = Depends(get_db),
    context: AuthContext | None = Depends(get_auth_context),
):
    transcripts = [
        item
        for item, metadata in canonical_transcript_listing(db)
        if _can_access_transcript(db, item, metadata, context)
    ]

    def average(values: list[float | None]) -> float | None:
        present = [float(value) for value in values if value is not None]
        return round(sum(present) / len(present), 4) if present else None

    provider_groups: dict[str, list[Transcript]] = {}
    for transcript in transcripts:
        provider_groups.setdefault(transcript.asr_provider or "unknown", []).append(transcript)

    return {
        "transcript_count": len(transcripts),
        "average_asr_confidence": average([item.asr_confidence for item in transcripts]),
        "average_diarization_quality": average([item.diarization_quality for item in transcripts]),
        "average_manual_correction_rate": average([normalized_correction_rate(item) for item in transcripts]),
        "by_provider": [
            {
                "provider": provider,
                "transcript_count": len(items),
                "average_asr_confidence": average([item.asr_confidence for item in items]),
                "average_diarization_quality": average([item.diarization_quality for item in items]),
                "average_manual_correction_rate": average([normalized_correction_rate(item) for item in items]),
            }
            for provider, items in sorted(provider_groups.items())
        ],
    }


@app.get("/transcripts/{transcript_id}")
def get_transcript(
    transcript_id: int,
    db: Session = Depends(get_db),
    context: AuthContext | None = Depends(get_auth_context),
):
    for transcript, metadata in canonical_transcript_listing(db):
        if transcript.id == transcript_id and _can_access_transcript(db, transcript, metadata, context):
            return serialize_transcript_detail(transcript, metadata)
    raise HTTPException(status_code=404, detail="Canonical transcript was not found.")


def get_transcript_text(
    db: Session,
    transcript_id: int | None,
    transcript_text: str | None,
) -> tuple[int | None, str]:
    if transcript_text and transcript_text.strip():
        return transcript_id, transcript_text.strip()

    if transcript_id is None:
        raise HTTPException(status_code=400, detail="transcript_id or transcript_text is required.")

    transcript = db.query(Transcript).filter(Transcript.id == transcript_id).first()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript was not found.")

    return transcript.id, transcript.content


def build_case_analysis_response(
    payload: AnalyzeCaseRequest,
    db: Session,
) -> AnalyzeCaseResponse:
    transcript_id, transcript_text = get_transcript_text(
        db,
        payload.transcript_id,
        payload.transcript_text,
    )
    keyword_result = detect_sensitive_keywords(transcript_text)
    extracted_entities = apply_authoritative_case_entities(
        extract_legal_entities(transcript_text),
        payload.case_information.barangay_name,
        datetime.now(MANILA_TIMEZONE),
    )
    rule_result = evaluate_jurisdiction(payload.case_information, keyword_result)
    xai_trace = build_xai_trace(rule_result, keyword_result)

    return AnalyzeCaseResponse(
        transcript_id=transcript_id,
        case_information=payload.case_information,
        extracted_entities=extracted_entities,
        detected_keywords=keyword_result,
        jurisdiction_decision=rule_result["jurisdiction_decision"],
        exclusion_ground=rule_result["exclusion_ground"],
        confidence_level=rule_result["confidence_level"],
        missing_fields=rule_result["missing_fields"],
        recommended_next_action=rule_result["recommended_next_action"],
        xai_trace=xai_trace,
        rule_results=rule_result["rule_results"],
    )


def determine_sensitivity(payload: AnalyzeCaseResponse) -> str:
    if (
        payload.case_information.has_vawc_or_child_abuse_indicators
        or payload.detected_keywords.get("vawc_trigger")
        or payload.jurisdiction_decision == "refer_to_pnp_wcpc_or_authority"
        or payload.exclusion_ground in {"vawc", "child_abuse"}
    ):
        return "sensitive"
    return "normal"


def create_case_analysis_record(payload: AnalyzeCaseResponse, db: Session) -> CaseAnalysis:
    if payload.transcript_id is not None:
        transcript = db.query(Transcript).filter(Transcript.id == payload.transcript_id).first()
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript was not found.")

    case_info = CaseInformation(
        transcript_id=payload.transcript_id,
        sensitivity_level=determine_sensitivity(payload),
        recording_consent_confirmed=True,
        **payload.case_information.model_dump(),
    )
    extracted = ExtractedEntities(
        transcript_id=payload.transcript_id,
        entities_json=payload.extracted_entities,
    )
    trace = XAITrace(
        trace_json=payload.xai_trace,
        trace_text="\n".join(payload.xai_trace),
    )
    db.add_all([case_info, extracted, trace])
    db.flush()
    extracted.entities_json = apply_authoritative_case_entities(
        payload.extracted_entities,
        case_info.barangay_name,
        case_info.created_at,
    )

    analysis = CaseAnalysis(
        transcript_id=payload.transcript_id,
        case_information_id=case_info.id,
        extracted_entities_id=extracted.id,
        xai_trace_id=trace.id,
        detected_keywords_json=payload.detected_keywords,
        rule_results_json=payload.rule_results,
        jurisdiction_decision=payload.jurisdiction_decision,
        exclusion_ground=payload.exclusion_ground,
        confidence_level=payload.confidence_level,
        missing_fields_json=payload.missing_fields,
        recommended_next_action=payload.recommended_next_action,
    )
    db.add(analysis)
    db.flush()
    return analysis


@app.post("/analyze-case", response_model=AnalyzeCaseResponse)
def analyze_case(payload: AnalyzeCaseRequest, db: Session = Depends(get_db)):
    return build_case_analysis_response(payload, db)


@app.post("/save-case-analysis", response_model=SaveCaseAnalysisResponse)
def save_case_analysis(payload: SaveCaseAnalysisRequest, db: Session = Depends(get_db)):
    analysis = create_case_analysis_record(payload, db)
    db.commit()
    db.refresh(analysis)

    return {
        "message": "Case analysis saved successfully.",
        "id": analysis.id,
        "created_at": analysis.created_at,
    }


@app.get("/case-analyses", response_model=list[CaseAnalysisSummary])
def get_case_analyses(db: Session = Depends(get_db)):
    analyses = db.query(CaseAnalysis).order_by(CaseAnalysis.created_at.desc()).all()
    summaries = []
    for analysis in analyses:
        case_info = (
            db.query(CaseInformation)
            .filter(CaseInformation.id == analysis.case_information_id)
            .first()
        )
        summaries.append(
            {
                "id": analysis.id,
                "transcript_id": analysis.transcript_id,
                "case_id": case_info.case_id if case_info else "",
                "barangay_name": case_info.barangay_name if case_info else "",
                "jurisdiction_decision": analysis.jurisdiction_decision,
                "exclusion_ground": analysis.exclusion_ground,
                "confidence_level": analysis.confidence_level,
                "recommended_next_action": analysis.recommended_next_action,
                "created_at": analysis.created_at,
            }
        )
    return summaries


@app.get("/case-analysis/{analysis_id}")
def get_case_analysis(analysis_id: int, db: Session = Depends(get_db)):
    analysis = db.query(CaseAnalysis).filter(CaseAnalysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Case analysis was not found.")

    case_info = (
        db.query(CaseInformation)
        .filter(CaseInformation.id == analysis.case_information_id)
        .first()
    )
    extracted = (
        db.query(ExtractedEntities)
        .filter(ExtractedEntities.id == analysis.extracted_entities_id)
        .first()
    )
    trace = db.query(XAITrace).filter(XAITrace.id == analysis.xai_trace_id).first()

    return {
        "id": analysis.id,
        "transcript_id": analysis.transcript_id,
        "case_information": {
            column.name: getattr(case_info, column.name)
            for column in CaseInformation.__table__.columns
            if case_info and column.name not in {"id", "created_at"}
        },
        "extracted_entities": apply_authoritative_case_entities(
            extracted.entities_json if extracted else {},
            case_info.barangay_name,
            case_info.created_at,
        ) if case_info else {},
        "detected_keywords": analysis.detected_keywords_json,
        "jurisdiction_decision": analysis.jurisdiction_decision,
        "exclusion_ground": analysis.exclusion_ground,
        "confidence_level": analysis.confidence_level,
        "missing_fields": analysis.missing_fields_json,
        "recommended_next_action": analysis.recommended_next_action,
        "xai_trace": trace.trace_json if trace else [],
        "rule_results": analysis.rule_results_json,
        "created_at": analysis.created_at,
    }


@app.post("/api/phase3/process-case/{case_id}")
def process_phase3_case(case_id: str, db: Session = Depends(get_db)):
    return process_phase3_pipeline(case_id, db)


@app.get("/api/phase3/dashboard/{case_id}")
def get_phase3_dashboard(
    case_id: str,
    db: Session = Depends(get_db),
    context: AuthContext | None = Depends(get_auth_context),
):
    ensure_case_read_access(db, case_id, context, audit_resource_type="phase3_dashboard")
    return Phase3DashboardService().build(db, case_id)


@app.post("/api/phase3/sensitive-routing/{case_id}")
def run_sensitive_routing(case_id: str, db: Session = Depends(get_db)):
    ensure_case_is_mutable(db, case_id)
    bundle = get_phase2_bundle(db, case_id)
    route = SensitiveCaseRoutingService().save(db, bundle)
    return serialize_model(route)


@app.get("/api/phase3/sensitive-routing/{case_id}")
def get_sensitive_routing(
    case_id: str,
    db: Session = Depends(get_db),
    context: AuthContext | None = Depends(get_auth_context),
):
    ensure_case_read_access(db, case_id, context, audit_resource_type="phase3_sensitive_routing")
    bundle = get_phase2_bundle(db, case_id)
    route = (
        db.query(Phase3CaseRoute)
        .filter(Phase3CaseRoute.case_id == bundle.case_info.case_id)
        .order_by(Phase3CaseRoute.id.desc())
        .first()
    )
    if not route:
        raise HTTPException(status_code=404, detail="Sensitive routing result was not found.")
    return serialize_model(route)


@app.post("/api/phase3/referrals")
def create_referral(payload: ReferralCreateRequest, db: Session = Depends(get_db)):
    ensure_case_is_mutable(db, payload.case_id)
    get_phase2_bundle(db, payload.case_id)
    referral = Referral(
        case_id=payload.case_id,
        referral_type=payload.referral_type,
        destination=payload.destination,
        reason=payload.reason,
        matched_keywords=payload.matched_keywords,
        xai_reference=payload.xai_reference,
        status=payload.status,
    )
    db.add(referral)
    db.flush()
    append_audit_log(db, payload.case_id, "referral_created", serialize_model(referral), actor="official")
    db.commit()
    db.refresh(referral)
    return serialize_model(referral)


@app.get("/api/phase3/referrals/{case_id}")
def get_referrals(
    case_id: str,
    db: Session = Depends(get_db),
    context: AuthContext | None = Depends(get_auth_context),
):
    ensure_case_read_access(db, case_id, context, audit_resource_type="phase3_referrals")
    bundle = get_phase2_bundle(db, case_id)
    referrals = (
        db.query(Referral)
        .filter(Referral.case_id == bundle.case_info.case_id)
        .order_by(Referral.created_at.desc())
        .all()
    )
    return [serialize_model(item) for item in referrals]


@app.patch("/api/phase3/referrals/{referral_id}")
def update_referral(referral_id: int, payload: ReferralUpdateRequest, db: Session = Depends(get_db)):
    referral = db.query(Referral).filter(Referral.id == referral_id).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Referral was not found.")
    ensure_case_is_mutable(db, referral.case_id)
    if payload.status is not None:
        referral.status = payload.status
    if payload.reason is not None:
        referral.reason = payload.reason
    append_audit_log(db, referral.case_id, "referral_updated", serialize_model(referral), actor="official")
    db.commit()
    db.refresh(referral)
    return serialize_model(referral)


@app.post("/api/phase3/mediation-eligibility/{case_id}")
def run_mediation_eligibility(case_id: str, db: Session = Depends(get_db)):
    ensure_case_is_mutable(db, case_id)
    bundle = get_phase2_bundle(db, case_id)
    route = SensitiveCaseRoutingService().evaluate(bundle)
    route_model = (
        db.query(Phase3CaseRoute)
        .filter(Phase3CaseRoute.case_id == bundle.case_info.case_id)
        .order_by(Phase3CaseRoute.id.desc())
        .first()
    )
    if route_model:
        route = serialize_model(route_model)
    eligibility = MediationEligibilityService().save(db, bundle, route)
    return serialize_model(eligibility)


@app.get("/api/phase3/mediation-eligibility/{case_id}")
def get_mediation_eligibility(
    case_id: str,
    db: Session = Depends(get_db),
    context: AuthContext | None = Depends(get_auth_context),
):
    ensure_case_read_access(db, case_id, context, audit_resource_type="phase3_mediation_eligibility")
    bundle = get_phase2_bundle(db, case_id)
    eligibility = (
        db.query(MediationEligibility)
        .filter(MediationEligibility.case_id == bundle.case_info.case_id)
        .order_by(MediationEligibility.id.desc())
        .first()
    )
    if not eligibility:
        raise HTTPException(status_code=404, detail="Mediation eligibility result was not found.")
    return serialize_model(eligibility)


@app.post("/api/phase3/mediation-suggestions/{case_id}")
def run_mediation_suggestions(case_id: str, db: Session = Depends(get_db)):
    ensure_case_is_mutable(db, case_id)
    bundle = get_phase2_bundle(db, case_id)
    route = SensitiveCaseRoutingService().evaluate(bundle)
    eligibility = MediationEligibilityService().evaluate(bundle, route)
    eligibility_model = (
        db.query(MediationEligibility)
        .filter(MediationEligibility.case_id == bundle.case_info.case_id)
        .order_by(MediationEligibility.id.desc())
        .first()
    )
    if eligibility_model:
        eligibility = serialize_model(eligibility_model)
    suggestions = MediationSuggestionService().save(db, bundle, eligibility)
    return serialize_model(suggestions)


@app.get("/api/phase3/mediation-suggestions/{case_id}")
def get_mediation_suggestions(
    case_id: str,
    db: Session = Depends(get_db),
    context: AuthContext | None = Depends(get_auth_context),
):
    ensure_case_read_access(db, case_id, context, audit_resource_type="phase3_mediation_suggestions")
    bundle = get_phase2_bundle(db, case_id)
    suggestions = (
        db.query(MediationSuggestion)
        .filter(MediationSuggestion.case_id == bundle.case_info.case_id)
        .order_by(MediationSuggestion.id.desc())
        .first()
    )
    if not suggestions:
        raise HTTPException(status_code=404, detail="Mediation suggestions were not found.")
    return serialize_model(suggestions)


@app.post("/api/phase3/hearings")
def create_hearing(payload: HearingCreateRequest, db: Session = Depends(get_db)):
    ensure_case_is_mutable(db, payload.case_id)
    HearingService().validate(db, payload.case_id, payload.scheduled_date, payload.status, payload.hearing_type)
    hearing = Hearing(**payload.model_dump())
    db.add(hearing)
    db.flush()
    append_audit_log(db, payload.case_id, "hearing_created", serialize_model(hearing), actor="official")
    db.commit()
    db.refresh(hearing)
    return serialize_model(hearing)


@app.get("/api/phase3/hearings/{case_id}")
def get_hearings(
    case_id: str,
    db: Session = Depends(get_db),
    context: AuthContext | None = Depends(get_auth_context),
):
    ensure_case_read_access(db, case_id, context, audit_resource_type="phase3_hearings")
    bundle = get_phase2_bundle(db, case_id)
    hearings = (
        db.query(Hearing)
        .filter(Hearing.case_id == bundle.case_info.case_id)
        .order_by(Hearing.scheduled_date.asc(), Hearing.scheduled_time.asc())
        .all()
    )
    return [serialize_model(item) for item in hearings]


@app.patch("/api/phase3/hearings/{hearing_id}")
def update_hearing(hearing_id: int, payload: HearingUpdateRequest, db: Session = Depends(get_db)):
    hearing = db.query(Hearing).filter(Hearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing was not found.")
    ensure_case_is_mutable(db, hearing.case_id)
    next_date = payload.scheduled_date or hearing.scheduled_date
    next_status = payload.status or hearing.status
    next_type = payload.hearing_type or hearing.hearing_type
    HearingService().validate(db, hearing.case_id, next_date, next_status, next_type)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(hearing, key, value)
    append_audit_log(db, hearing.case_id, "hearing_updated", serialize_model(hearing), actor="official")
    db.commit()
    db.refresh(hearing)
    return serialize_model(hearing)


@app.post("/api/phase3/evidence/upload/{case_id}")
async def upload_evidence(
    case_id: str,
    file: UploadFile = File(...),
    evidence_text: str = Form(""),
    db: Session = Depends(get_db),
):
    ensure_case_is_mutable(db, case_id)
    bundle = get_phase2_bundle(db, case_id)
    evidence_service = EvidenceFileService(EVIDENCE_DIR)
    saved = evidence_service.save_upload(bundle.case_info.case_id, file, evidence_text)
    evidence = Evidence(
        case_id=bundle.case_info.case_id,
        file_name=saved["file_name"],
        file_type=saved["file_type"],
        file_path=saved["file_path"],
        ocr_text=saved["evidence_text"],
        extracted_entities_json=saved["extracted_entities"],
    )
    db.add(evidence)
    db.flush()
    append_audit_log(db, bundle.case_info.case_id, "evidence_uploaded", serialize_model(evidence), actor="official")
    db.commit()
    db.refresh(evidence)
    return serialize_evidence_record(evidence)


@app.get("/api/phase3/evidence/{case_id}")
def get_evidence(
    case_id: str,
    db: Session = Depends(get_db),
    context: AuthContext | None = Depends(get_auth_context),
):
    ensure_case_read_access(db, case_id, context, audit_resource_type="phase3_evidence")
    bundle = get_phase2_bundle(db, case_id)
    evidence = (
        db.query(Evidence)
        .filter(Evidence.case_id == bundle.case_info.case_id)
        .order_by(Evidence.uploaded_at.desc())
        .all()
    )
    return [serialize_evidence_record(item) for item in evidence]


@app.get("/api/phase3/evidence/{evidence_id}/download")
def download_evidence(
    evidence_id: int,
    db: Session = Depends(get_db),
    context: AuthContext | None = Depends(get_auth_context),
):
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence was not found.")
    is_sensitive = ensure_case_read_access(db, evidence.case_id, context)
    file_path = Path(evidence.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Evidence file was not found.")
    if isinstance(context, AuthContext) and is_sensitive:
        db.add(
            AuditLog(
                case_id=evidence.case_id,
                action="sensitive_case_evidence_downloaded",
                actor=context.user.username,
                actor_user_id=context.user.id,
                actor_role=context.role.name,
                resource_type="evidence",
                resource_id=str(evidence.id),
                risk_level="moderate",
                details_json={"evidence_id": evidence.id, "file_name": evidence.file_name},
            )
        )
        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="The evidence was not released because access could not be audited.",
            ) from exc
    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        filename=evidence.file_name,
    )


@app.patch("/api/phase3/evidence/{evidence_id}")
def update_evidence(evidence_id: int, payload: EvidenceUpdateRequest, db: Session = Depends(get_db)):
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence was not found.")
    ensure_case_is_mutable(db, evidence.case_id)
    if payload.evidence_text is not None:
        evidence.ocr_text = payload.evidence_text
    if payload.extracted_entities is not None:
        evidence.extracted_entities_json = payload.extracted_entities
    append_audit_log(db, evidence.case_id, "evidence_updated", serialize_model(evidence), actor="official")
    db.commit()
    db.refresh(evidence)
    return serialize_evidence_record(evidence)


@app.post("/api/phase3/emotion-analysis/{case_id}")
def run_emotion_analysis(case_id: str, db: Session = Depends(get_db)):
    ensure_case_is_mutable(db, case_id)
    bundle = get_phase2_bundle(db, case_id)
    emotion = EmotionAnalysisService().save(db, bundle)
    return serialize_model(emotion)


@app.get("/api/phase3/emotion-analysis/{case_id}")
def get_emotion_analysis(
    case_id: str,
    db: Session = Depends(get_db),
    context: AuthContext | None = Depends(get_auth_context),
):
    ensure_case_read_access(db, case_id, context, audit_resource_type="phase3_emotion_analysis")
    bundle = get_phase2_bundle(db, case_id)
    emotion = (
        db.query(EmotionAnalysis)
        .filter(EmotionAnalysis.case_id == bundle.case_info.case_id)
        .order_by(EmotionAnalysis.id.desc())
        .first()
    )
    if not emotion:
        raise HTTPException(status_code=404, detail="Emotion analysis result was not found.")
    return serialize_model(emotion)


@app.post("/api/phase3/official-decision/{case_id}")
def save_official_decision(case_id: str, payload: OfficialDecisionRequest, db: Session = Depends(get_db)):
    ensure_case_is_mutable(db, case_id)
    dashboard = Phase3DashboardService().build(db, case_id)
    canonical_case_id = dashboard["case_id"]
    decision = Phase3OfficialDecision(
        case_id=canonical_case_id,
        system_recommendation=dashboard["phase3"]["final_recommended_action"],
        official_decision=payload.official_decision,
        official_notes=payload.official_notes,
        approved_by=payload.approved_by,
    )
    db.add(decision)
    db.flush()
    append_audit_log(db, canonical_case_id, "official_decision_saved", serialize_model(decision), actor=payload.approved_by)
    db.commit()
    db.refresh(decision)
    return serialize_model(decision)
