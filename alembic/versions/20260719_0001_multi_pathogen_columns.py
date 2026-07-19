"""multi-pathogen analysis columns

Revision ID: 20260719_0001
Revises:
Create Date: 2026-07-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260719_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "analyses" not in tables:
        op.create_table(
            "analyses",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("current_stage", sa.String(length=64), nullable=True),
            sa.Column("progress", sa.Float(), nullable=False),
            sa.Column("sample_name", sa.String(length=200), nullable=False),
            sa.Column("organism", sa.String(length=128), nullable=False),
            sa.Column("selected_organism_id", sa.String(length=128), nullable=True),
            sa.Column("platform", sa.String(length=128), nullable=True),
            sa.Column("read_type", sa.String(length=32), nullable=False),
            sa.Column("file_format", sa.String(length=16), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("upload_id", sa.String(length=64), nullable=False),
            sa.Column("object_key", sa.String(length=512), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("result_schema_version", sa.String(length=16), nullable=True),
            sa.Column("remote_job_id", sa.String(length=128), nullable=True),
            sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("tool_run_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    else:
        existing = {col["name"] for col in inspector.get_columns("analyses")}
        additions = {
            "selected_organism_id": sa.Column("selected_organism_id", sa.String(128)),
            "result_schema_version": sa.Column("result_schema_version", sa.String(16)),
            "remote_job_id": sa.Column("remote_job_id", sa.String(128)),
            "attempt": sa.Column("attempt", sa.Integer(), server_default="1"),
            "tool_run_json": sa.Column("tool_run_json", sa.Text()),
        }
        for name, column in additions.items():
            if name not in existing:
                op.add_column("analyses", column)

    if "analysis_events" not in tables:
        op.create_table(
            "analysis_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("analysis_id", sa.String(36), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("stage", sa.String(64), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("level", sa.String(16), nullable=False),
            sa.Column("progress", sa.Float(), nullable=False),
            sa.Column("timestamp", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("analysis_id", "sequence", name="uq_analysis_sequence"),
        )

    if "uploads" not in tables:
        op.create_table(
            "uploads",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("filename", sa.String(512), nullable=False),
            sa.Column("content_type", sa.String(128), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("object_key", sa.String(512), nullable=False, unique=True),
            sa.Column("sample_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    # Keep downgrade non-destructive for shared hackathon DBs.
    pass
