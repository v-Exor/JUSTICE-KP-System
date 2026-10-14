"""Add raw and edited transcript audit fields to legacy databases.

Revision ID: 20260815_0002
Revises: 20260618_0001
Create Date: 2026-08-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260815_0002"
down_revision = "20260618_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "transcripts" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("transcripts")}
    columns = [
        sa.Column("raw_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("segments_json", sa.JSON(), nullable=True),
        sa.Column("raw_segments_json", sa.JSON(), nullable=True),
        sa.Column("corrections_json", sa.JSON(), nullable=True),
    ]
    for column in columns:
        if column.name not in existing:
            op.add_column("transcripts", column)


def downgrade() -> None:
    # These columns contain audit evidence and should not be removed
    # automatically by a downgrade.
    pass
