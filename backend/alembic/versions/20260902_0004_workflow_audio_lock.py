"""Add canonical workflow audio locking fields.

Revision ID: 20260902_0004
Revises: 20260822_0003
Create Date: 2026-09-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260902_0004"
down_revision = "20260822_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "workflow_drafts" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("workflow_drafts")}
    columns = [
        sa.Column("audio_filename", sa.Text(), nullable=False, server_default=""),
        sa.Column("audio_duration_seconds", sa.Float(), nullable=True),
        sa.Column("audio_upload_token", sa.Text(), nullable=False, server_default=""),
    ]
    for column in columns:
        if column.name not in existing:
            op.add_column("workflow_drafts", column)


def downgrade() -> None:
    # Canonical audio ownership is evidence metadata and should not be removed
    # automatically by a downgrade.
    pass
