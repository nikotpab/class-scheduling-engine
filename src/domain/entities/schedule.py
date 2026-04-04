from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class ScheduleStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    FAILED = "FAILED"


@dataclass
class Assignment:
    """A single scheduled class — the atomic result unit."""
    teacher_id: str
    subject_id: str
    room_id: str
    timeslot_id: str
    campus_id: str
    group_id: str


@dataclass
class Schedule:
    """Aggregate root — the complete generated timetable."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    status: ScheduleStatus = ScheduleStatus.PENDING
    assignments: list[Assignment] = field(default_factory=list)
    penalty_score: float = 0.0
    solver_status: str = ""
    error_message: str = ""

    def mark_running(self) -> None:
        self.status = ScheduleStatus.RUNNING

    def mark_complete(
        self,
        assignments: list[Assignment],
        penalty_score: float,
        solver_status: str,
    ) -> None:
        self.assignments = assignments
        self.penalty_score = penalty_score
        self.solver_status = solver_status
        self.status = (
            ScheduleStatus.OPTIMAL
            if solver_status == "Optimal"
            else ScheduleStatus.FEASIBLE
        )

    def mark_infeasible(self) -> None:
        self.status = ScheduleStatus.INFEASIBLE
        self.solver_status = "Infeasible"

    def mark_failed(self, error: str) -> None:
        self.status = ScheduleStatus.FAILED
        self.error_message = error
