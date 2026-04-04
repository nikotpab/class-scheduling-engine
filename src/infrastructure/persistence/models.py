from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.database import Base


class ScheduleJobORM(Base):
    """
    Persists schedule generation jobs and their results.
    The request_payload (JSONB) stores the full ScheduleGenerationRequest
    so the worker can reconstruct domain objects without a second API call.
    """
    __tablename__ = "schedule_jobs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    request_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_assignments: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    penalty_score: Mapped[float] = mapped_column(Float, default=0.0)
    solver_status: Mapped[str] = mapped_column(String(32), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    solver_name: Mapped[str] = mapped_column(String(64), default="")
    solve_time_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
