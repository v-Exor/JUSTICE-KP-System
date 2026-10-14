"""Add canonical workflow ownership and update metadata to transcripts.

Revision ID: 20260822_0003
Revises: 20260815_0002
Create Date: 2026-08-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260822_0003"
down_revision = "20260815_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "transcripts" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("transcripts")}
    columns = [
        sa.Column("workflow_id", sa.Text(), nullable=True),
        sa.Column("case_id", sa.Text(), nullable=True),
        sa.Column("save_context", sa.Text(), nullable=False, server_default="standalone"),
        sa.Column("superseded_by_transcript_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    ]
    for column in columns:
        if column.name not in existing:
            op.add_column("transcripts", column)

    op.execute(
        "UPDATE transcripts SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
    )

    inspector = inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("transcripts")}
    if "ux_transcripts_workflow_id" not in indexes:
        op.create_index("ux_transcripts_workflow_id", "transcripts", ["workflow_id"], unique=True)
    if "ux_transcripts_case_id" not in indexes:
        op.create_index("ux_transcripts_case_id", "transcripts", ["case_id"], unique=True)
    if "ix_transcripts_superseded_by" not in indexes:
        op.create_index(
            "ix_transcripts_superseded_by",
            "transcripts",
            ["superseded_by_transcript_id"],
        )

    # The application model requires this for new rows.  It is made non-null
    # only after every historical row has received a conservative timestamp.
    with op.batch_alter_table("transcripts") as batch:
        batch.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)


def downgrade() -> None:
    # These fields identify canonical evidentiary records.  An automatic
    # downgrade intentionally preserves them and all historical data.
    pass
