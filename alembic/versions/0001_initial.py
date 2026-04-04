"""Initial schema — schedule_jobs table

Revision ID: 0001_initial
Revises: 
Create Date: 2026-04-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedule_jobs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("job_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("request_payload", JSONB, nullable=True),
        sa.Column("result_assignments", JSONB, nullable=True),
        sa.Column("penalty_score", sa.Float, server_default="0"),
        sa.Column("solver_status", sa.String(32), server_default=""),
        sa.Column("error_message", sa.Text, server_default=""),
        sa.Column("solver_name", sa.String(64), server_default=""),
        sa.Column("solve_time_seconds", sa.Float, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_schedule_jobs_job_id", "schedule_jobs", ["job_id"])
    op.create_index("ix_schedule_jobs_status", "schedule_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("schedule_jobs")
