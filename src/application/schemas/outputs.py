from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from src.domain.entities.schedule import ScheduleStatus


class AssignmentOutput(BaseModel):
    teacher_id: str
    subject_id: str
    room_id: str
    timeslot_id: str
    campus_id: str
    group_id: str


class ScheduleJobResponse(BaseModel):
    job_id: str
    schedule_id: str | None = None
    status: ScheduleStatus
    penalty_score: float = 0.0
    solver_status: str = ""
    error_message: str = ""
    assignments: list[AssignmentOutput] = []
    created_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class JobSubmittedResponse(BaseModel):
    job_id: str
    message: str = "Schedule generation job queued successfully."
    ws_url: str


class PenaltyWeightsResponse(BaseModel):
    penalizacion1: float
    penalizacion2: float
