"""Initial PostgreSQL production schema.

Revision ID: 20260618_0001
Revises:
Create Date: 2026-06-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from database import Base
import models  # noqa: F401


revision = "20260618_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            table.create(bind=bind)
    if "transcripts" in existing:
        transcript_columns = {column["name"] for column in inspector.get_columns("transcripts")}
        metric_columns = [
            sa.Column("asr_provider", sa.Text(), nullable=False, server_default=""),
            sa.Column("asr_confidence", sa.Float(), nullable=True),
            sa.Column("diarization_quality", sa.Float(), nullable=True),
            sa.Column("manual_correction_rate", sa.Float(), nullable=True),
            sa.Column("correction_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("original_word_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("edited_word_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("expected_speakers", sa.Integer(), nullable=True),
            sa.Column("detected_speakers", sa.Integer(), nullable=True),
            sa.Column("recording_type", sa.Text(), nullable=False, server_default=""),
            sa.Column("accuracy_metrics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        ]
        for column in metric_columns:
            if column.name not in transcript_columns:
                op.add_column("transcripts", column)


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in existing:
            table.drop(bind=bind)
