"""Backfill raw-versus-edited metrics on legacy transcripts.

Revision ID: 20260920_0005
Revises: 20260902_0004
Create Date: 2026-09-20
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260920_0005"
down_revision = "20260902_0004"
branch_labels = None
depends_on = None


def _comparison_metrics(original_count: int, edited_count: int, correction_count: int) -> dict:
    original_count = max(int(original_count or 0), 0)
    edited_count = max(int(edited_count or 0), 0)
    correction_count = max(int(correction_count or 0), 0)
    if original_count:
        word_error_rate = round(correction_count / max(edited_count, 1), 4)
        raw_word_accuracy = round(max(0.0, 1.0 - word_error_rate), 4)
    elif edited_count:
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


def _diarization_quality(detected_speakers: int, expected_speakers: int) -> float:
    detected_count = max(int(detected_speakers or 0), 0)
    expected_count = int(expected_speakers or 0)
    if not detected_count:
        return 0.0
    if expected_count in {2, 3}:
        if detected_count == expected_count:
            return 1.0
        return round(min(1.0, max(0.4, detected_count / expected_count)), 4)
    return 0.8


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "transcripts" not in inspector.get_table_names():
        return

    rows = bind.execute(
        sa.text(
            "SELECT id, accuracy_metrics_json, original_word_count, "
            "edited_word_count, correction_count, diarization_quality, "
            "detected_speakers, expected_speakers FROM transcripts"
        )
    ).mappings()
    update_statement = sa.text(
        "UPDATE transcripts SET accuracy_metrics_json = :metrics, "
        "diarization_quality = :diarization_quality WHERE id = :transcript_id"
    ).bindparams(sa.bindparam("metrics", type_=sa.JSON()))

    for row in rows:
        stored_metrics = row["accuracy_metrics_json"]
        if isinstance(stored_metrics, str):
            try:
                stored_metrics = json.loads(stored_metrics)
            except (TypeError, ValueError):
                stored_metrics = {}
        metrics = dict(stored_metrics or {})
        changed = False
        for key, value in _comparison_metrics(
            row["original_word_count"],
            row["edited_word_count"],
            row["correction_count"],
        ).items():
            if metrics.get(key) is None:
                metrics[key] = value
                changed = True
        diarization_quality = row["diarization_quality"]
        if diarization_quality is None:
            diarization_quality = _diarization_quality(
                row["detected_speakers"],
                row["expected_speakers"],
            )
            changed = True
        if metrics.get("diarization_quality") is None:
            metrics["diarization_quality"] = float(diarization_quality)
            changed = True
        if changed:
            bind.execute(
                update_statement,
                {
                    "metrics": metrics,
                    "diarization_quality": diarization_quality,
                    "transcript_id": row["id"],
                },
            )


def downgrade() -> None:
    # Comparison metrics are derived audit metadata and remain valid when an
    # application downgrade occurs, so they are intentionally preserved.
    pass
