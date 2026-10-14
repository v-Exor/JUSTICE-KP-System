from pathlib import Path
import json
import os

from sqlalchemy import JSON, bindparam, create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_PATH = Path(__file__).resolve().parent / "justicekp.db"
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DATABASE_PATH}"

if APP_ENV == "production":
    missing = [
        name
        for name in ["DATABASE_URL", "SESSION_SECRET", "BACKUP_ENCRYPTION_KEY", "ALLOWED_ORIGINS"]
        if not os.getenv(name)
    ]
    if missing:
        raise RuntimeError(f"Missing required production environment variable(s): {', '.join(missing)}")
    if not DATABASE_URL.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("APP_ENV=production requires PostgreSQL via DATABASE_URL.")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def comparison_metrics_from_counts(
    original_word_count: int | None,
    edited_word_count: int | None,
    correction_count: int | None,
) -> dict[str, float | int]:
    """Build raw-versus-edited metrics from the audit counts stored on a transcript."""
    original_count = max(int(original_word_count or 0), 0)
    edited_count = max(int(edited_word_count or 0), 0)
    corrections = max(int(correction_count or 0), 0)

    if original_count:
        word_error_rate = round(corrections / max(edited_count, 1), 4)
        raw_word_accuracy = round(max(0.0, 1.0 - word_error_rate), 4)
    elif edited_count:
        # A manual-only transcript has an edited reference but no ASR words
        # that could match it.
        word_error_rate = 1.0
        raw_word_accuracy = 0.0
    else:
        word_error_rate = 0.0
        raw_word_accuracy = 0.0

    return {
        "reference_word_count": edited_count,
        "word_error_rate": word_error_rate,
        "raw_word_accuracy": raw_word_accuracy,
        "edited_word_accuracy": 1.0 if edited_count else 0.0,
    }


def diarization_quality_from_counts(
    detected_speakers: int | None,
    expected_speakers: int | None,
) -> float:
    """Reproduce the conservative quality fallback used when warnings are unavailable."""
    detected_count = max(int(detected_speakers or 0), 0)
    expected_count = int(expected_speakers or 0)
    if not detected_count:
        return 0.0
    if expected_count in {2, 3}:
        if detected_count == expected_count:
            return 1.0
        return round(min(1.0, max(0.4, detected_count / expected_count)), 4)
    return 0.8


def backfill_transcript_metrics(connection) -> int:
    """Persist metrics missing from transcripts created by older releases."""
    inspector = inspect(connection)
    if "transcripts" not in inspector.get_table_names():
        return 0

    existing_columns = {column["name"] for column in inspector.get_columns("transcripts")}
    required_columns = {
        "accuracy_metrics_json",
        "original_word_count",
        "edited_word_count",
        "correction_count",
        "diarization_quality",
        "detected_speakers",
        "expected_speakers",
    }
    if not required_columns.issubset(existing_columns):
        return 0

    rows = connection.execute(
        text(
            "SELECT id, accuracy_metrics_json, original_word_count, "
            "edited_word_count, correction_count, diarization_quality, "
            "detected_speakers, expected_speakers FROM transcripts"
        )
    ).mappings()
    update_statement = text(
        "UPDATE transcripts SET accuracy_metrics_json = :metrics, "
        "diarization_quality = :diarization_quality WHERE id = :transcript_id"
    ).bindparams(bindparam("metrics", type_=JSON))
    updated_count = 0

    for row in rows:
        stored_metrics = row["accuracy_metrics_json"]
        if isinstance(stored_metrics, str):
            try:
                stored_metrics = json.loads(stored_metrics)
            except (TypeError, ValueError):
                stored_metrics = {}
        metrics = dict(stored_metrics or {})
        calculated = comparison_metrics_from_counts(
            row["original_word_count"],
            row["edited_word_count"],
            row["correction_count"],
        )
        changed = False
        for key, value in calculated.items():
            if metrics.get(key) is None:
                metrics[key] = value
                changed = True
        diarization_quality = row["diarization_quality"]
        if diarization_quality is None:
            diarization_quality = diarization_quality_from_counts(
                row["detected_speakers"],
                row["expected_speakers"],
            )
            changed = True
        if metrics.get("diarization_quality") is None:
            metrics["diarization_quality"] = float(diarization_quality)
            changed = True
        if not changed:
            continue
        connection.execute(
            update_statement,
            {
                "metrics": metrics,
                "diarization_quality": diarization_quality,
                "transcript_id": row["id"],
            },
        )
        updated_count += 1

    return updated_count


def add_column_if_missing(connection, inspector, table_name: str, column_name: str, definition: str) -> None:
    if table_name not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name not in existing:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))


def reconcile_duplicate_transcript_identities(connection) -> dict[str, list[dict[str, object]]]:
    """Make legacy transcript identities index-safe without deleting evidence.

    Old releases could save both an intake and hearing row with the same case or
    workflow identity.  Prefer the row explicitly linked by a workflow draft,
    detach the duplicated identity from the remaining rows, and only mark a row
    superseded when both rows belong to the same workflow.  This preserves
    genuinely separate historical workflows which reused a case ID.
    """
    inspector = inspect(connection)
    if "transcripts" not in inspector.get_table_names():
        return {"workflow_id": [], "case_id": []}
    columns = {column["name"] for column in inspector.get_columns("transcripts")}
    required = {"id", "workflow_id", "case_id", "superseded_by_transcript_id"}
    if not required.issubset(columns):
        return {"workflow_id": [], "case_id": []}

    linked_ids: set[int] = set()
    if "workflow_drafts" in inspector.get_table_names():
        draft_columns = {column["name"] for column in inspector.get_columns("workflow_drafts")}
        if "transcript_id" in draft_columns:
            linked_ids = {
                int(row[0])
                for row in connection.execute(
                    text("SELECT transcript_id FROM workflow_drafts WHERE transcript_id IS NOT NULL")
                )
            }

    reviews: dict[str, list[dict[str, object]]] = {"workflow_id": [], "case_id": []}
    for identity in ("workflow_id", "case_id"):
        duplicates = connection.execute(
            text(
                f"SELECT {identity} AS identity_value FROM transcripts "
                f"WHERE {identity} IS NOT NULL AND TRIM({identity}) <> '' "
                f"GROUP BY {identity} HAVING COUNT(*) > 1"
            )
        ).mappings()
        for duplicate in duplicates:
            value = duplicate["identity_value"]
            rows = list(
                connection.execute(
                    text(
                        f"SELECT id, workflow_id, case_id FROM transcripts "
                        f"WHERE {identity} = :identity_value ORDER BY id DESC"
                    ),
                    {"identity_value": value},
                ).mappings()
            )
            canonical = next((row for row in rows if int(row["id"]) in linked_ids), rows[0])
            detached_ids: list[int] = []
            superseded_ids: list[int] = []
            for row in rows:
                row_id = int(row["id"])
                if row_id == int(canonical["id"]):
                    continue
                same_workflow = bool(
                    row["workflow_id"]
                    and canonical["workflow_id"]
                    and row["workflow_id"] == canonical["workflow_id"]
                )
                updates = [f"{identity} = NULL"]
                parameters: dict[str, object] = {"row_id": row_id}
                if identity == "workflow_id" or same_workflow:
                    updates.append("superseded_by_transcript_id = COALESCE(superseded_by_transcript_id, :canonical_id)")
                    parameters["canonical_id"] = int(canonical["id"])
                    superseded_ids.append(row_id)
                connection.execute(
                    text(f"UPDATE transcripts SET {', '.join(updates)} WHERE id = :row_id"),
                    parameters,
                )
                detached_ids.append(row_id)
            reviews[identity].append(
                {
                    "value": value,
                    "canonical_id": int(canonical["id"]),
                    "detached_ids": detached_ids,
                    "superseded_ids": superseded_ids,
                }
            )
    return reviews


def repair_generated_form_paths(connection) -> int:
    """Relink generated PDFs after the application directory is moved."""
    inspector = inspect(connection)
    if "phase4_generated_forms" not in inspector.get_table_names():
        return 0
    generated_forms_dir = DATABASE_PATH.parent / "generated_forms"
    if not generated_forms_dir.is_dir():
        return 0

    repaired = 0
    rows = connection.execute(
        text("SELECT id, file_path FROM phase4_generated_forms WHERE file_path IS NOT NULL")
    ).mappings()
    for row in rows:
        stored_path = Path(str(row["file_path"] or ""))
        if stored_path.is_file() or not stored_path.name:
            continue
        candidate = generated_forms_dir / stored_path.name
        if not candidate.is_file():
            continue
        connection.execute(
            text("UPDATE phase4_generated_forms SET file_path = :file_path WHERE id = :form_id"),
            {"file_path": str(candidate.resolve()), "form_id": int(row["id"])},
        )
        repaired += 1
    return repaired


def repair_workflow_case_ids(connection) -> int:
    """Restore blank draft index IDs from that draft's own JSON payload.

    Older clients saved ``phase2CaseId`` into the indexed column.  Before
    Phase 2 that value is blank even though ``caseInformation.case_id`` is
    already assigned, which made the picker label and search index disagree.
    This repair never merges drafts and never changes a non-blank case ID.
    """
    inspector = inspect(connection)
    if "workflow_drafts" not in inspector.get_table_names():
        return 0

    repaired = 0
    rows = connection.execute(
        text("SELECT id, case_id, payload_json FROM workflow_drafts WHERE case_id = '' OR case_id IS NULL")
    ).mappings()
    for row in rows:
        payload = row["payload_json"] or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (TypeError, ValueError):
                continue
        case_information = payload.get("caseInformation") or {}
        payload_case_id = str(case_information.get("case_id") or "").strip()
        if not payload_case_id:
            continue
        connection.execute(
            text("UPDATE workflow_drafts SET case_id = :case_id WHERE id = :draft_id"),
            {"case_id": payload_case_id, "draft_id": int(row["id"])},
        )
        repaired += 1
    return repaired


def migrate_database() -> None:
    inspector = inspect(engine)
    if "transcripts" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("transcripts")}
    with engine.begin() as connection:
        if "segments_json" not in existing_columns:
            connection.execute(text("ALTER TABLE transcripts ADD COLUMN segments_json JSON"))
        if "created_at" not in existing_columns:
            connection.execute(text("ALTER TABLE transcripts ADD COLUMN created_at DATETIME"))
            connection.execute(
                text("UPDATE transcripts SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
            )
        add_column_if_missing(connection, inspector, "transcripts", "asr_provider", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "transcripts", "raw_content", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "transcripts", "raw_segments_json", "JSON")
        add_column_if_missing(connection, inspector, "transcripts", "corrections_json", "JSON")
        add_column_if_missing(connection, inspector, "transcripts", "asr_confidence", "FLOAT")
        add_column_if_missing(connection, inspector, "transcripts", "diarization_quality", "FLOAT")
        add_column_if_missing(connection, inspector, "transcripts", "manual_correction_rate", "FLOAT")
        add_column_if_missing(connection, inspector, "transcripts", "correction_count", "INTEGER DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "transcripts", "original_word_count", "INTEGER DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "transcripts", "edited_word_count", "INTEGER DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "transcripts", "expected_speakers", "INTEGER")
        add_column_if_missing(connection, inspector, "transcripts", "detected_speakers", "INTEGER")
        add_column_if_missing(connection, inspector, "transcripts", "recording_type", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "transcripts", "accuracy_metrics_json", "JSON DEFAULT '{}' NOT NULL")
        add_column_if_missing(connection, inspector, "transcripts", "workflow_id", "TEXT")
        add_column_if_missing(connection, inspector, "transcripts", "case_id", "TEXT")
        add_column_if_missing(connection, inspector, "transcripts", "save_context", "TEXT DEFAULT 'standalone' NOT NULL")
        add_column_if_missing(connection, inspector, "transcripts", "superseded_by_transcript_id", "INTEGER")
        add_column_if_missing(connection, inspector, "transcripts", "updated_at", "DATETIME")
        connection.execute(
            text("UPDATE transcripts SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)")
        )

        # Legacy duplicates must be reconciled before unique indexes are added;
        # otherwise an otherwise valid upgrade fails at application startup.
        reconcile_duplicate_transcript_identities(connection)

        transcript_index_records = inspect(connection).get_indexes("transcripts")
        transcript_indexes = {index["name"] for index in transcript_index_records}
        has_unique_workflow_index = any(
            index.get("unique") and index.get("column_names") == ["workflow_id"]
            for index in transcript_index_records
        )
        has_unique_case_index = any(
            index.get("unique") and index.get("column_names") == ["case_id"]
            for index in transcript_index_records
        )
        if not has_unique_workflow_index:
            connection.execute(
                text("CREATE UNIQUE INDEX ux_transcripts_workflow_id ON transcripts (workflow_id)")
            )
        if not has_unique_case_index:
            connection.execute(
                text("CREATE UNIQUE INDEX ux_transcripts_case_id ON transcripts (case_id)")
            )
        if "ix_transcripts_superseded_by" not in transcript_indexes:
            connection.execute(
                text("CREATE INDEX ix_transcripts_superseded_by ON transcripts (superseded_by_transcript_id)")
            )

        add_column_if_missing(connection, inspector, "case_information", "sensitivity_level", "TEXT DEFAULT 'normal' NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "recording_consent_confirmed", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "hearing_consent_confirmed", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "retention_until", "DATETIME")
        add_column_if_missing(connection, inspector, "workflow_drafts", "audio_filename", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "workflow_drafts", "audio_duration_seconds", "FLOAT")
        add_column_if_missing(connection, inspector, "workflow_drafts", "audio_upload_token", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "proceeding_origin", "TEXT DEFAULT 'new_complaint' NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "has_juridical_entity_party", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "public_officer_involved", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "public_officer_official_function", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "no_private_offended_party", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "offense_classification", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "penalty_lookup_required", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "real_property_involved", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "real_property_barangay", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "real_property_city_municipality", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "real_property_in_different_city_municipality", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "parties_in_different_city_municipality", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "parties_in_adjoining_barangays", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "mutual_agreement_to_kp", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "respondent_barangay", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "respondent_city_municipality", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "incident_venue_basis", "TEXT DEFAULT 'same_barangay' NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "workplace_or_school_dispute", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "workplace_or_school_barangay", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "workplace_or_school_city_municipality", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "accused_under_detention", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "liberty_or_habeas_issue", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "provisional_remedy_needed", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "statute_limitations_urgent", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "minor_or_incompetent_party", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "next_of_kin_assistant_name", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "next_of_kin_is_lawyer", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "indigenous_community_dispute", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "same_indigenous_community", "BOOLEAN DEFAULT 0 NOT NULL")
        add_column_if_missing(connection, inspector, "case_information", "indigenous_process_agreed", "BOOLEAN DEFAULT 0 NOT NULL")

        add_column_if_missing(connection, inspector, "audit_logs", "actor_user_id", "INTEGER")
        add_column_if_missing(connection, inspector, "audit_logs", "actor_role", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "audit_logs", "ip_address", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "audit_logs", "user_agent", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "audit_logs", "resource_type", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "audit_logs", "resource_id", "TEXT DEFAULT '' NOT NULL")
        add_column_if_missing(connection, inspector, "audit_logs", "risk_level", "TEXT DEFAULT 'low' NOT NULL")

        add_column_if_missing(connection, inspector, "workflow_drafts", "case_analysis_id", "INTEGER")
        repair_workflow_case_ids(connection)
        backfill_transcript_metrics(connection)
        repair_generated_form_paths(connection)
