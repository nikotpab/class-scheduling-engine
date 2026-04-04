from __future__ import annotations

from src.application.schemas.outputs import AssignmentOutput, ScheduleJobResponse
from src.domain.exceptions import ScheduleNotFoundError
from src.domain.ports.i_schedule_repository import IScheduleRepository


class GetScheduleUseCase:
    """Query a schedule result by job_id."""

    def __init__(self, repository: IScheduleRepository) -> None:
        self._repository = repository

    async def execute(self, job_id: str) -> ScheduleJobResponse:
        schedule = await self._repository.find_by_job_id(job_id)
        if schedule is None:
            raise ScheduleNotFoundError(f"No schedule found for job_id={job_id}")

        return ScheduleJobResponse(
            job_id=schedule.job_id,
            schedule_id=schedule.id,
            status=schedule.status,
            penalty_score=schedule.penalty_score,
            solver_status=schedule.solver_status,
            error_message=schedule.error_message,
            assignments=[
                AssignmentOutput(
                    teacher_id=a.teacher_id,
                    subject_id=a.subject_id,
                    room_id=a.room_id,
                    timeslot_id=a.timeslot_id,
                    campus_id=a.campus_id,
                    group_id=a.group_id,
                )
                for a in schedule.assignments
            ],
        )
