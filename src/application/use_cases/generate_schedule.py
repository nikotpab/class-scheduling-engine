from __future__ import annotations

import uuid

from src.application.schemas.inputs import ScheduleGenerationRequest
from src.application.schemas.outputs import JobSubmittedResponse
from src.domain.entities.room import Room
from src.domain.entities.schedule import Schedule, ScheduleStatus
from src.domain.entities.subject import Subject
from src.domain.entities.teacher import Teacher, TeacherAvailability, TeacherType
from src.domain.entities.timeslot import Timeslot
from src.domain.ports.i_schedule_repository import IScheduleRepository
from src.domain.ports.i_solver import SchedulingProblem
from src.domain.value_objects.penalty_weights import PenaltyWeights

from datetime import time


def _parse_time(t: str) -> time:
    h, m = t.split(":")
    return time(int(h), int(m))


def _map_request_to_problem(request: ScheduleGenerationRequest) -> SchedulingProblem:
    teachers = [
        Teacher(
            id=t.id,
            name=t.name,
            teacher_type=TeacherType(t.teacher_type),
            campus_ids=t.campus_ids,
            availability=TeacherAvailability(
                slots=frozenset((s.day, s.slot_index) for s in t.availability_slots)
            ),
            max_hours_per_day=t.max_hours_per_day,
            ntpphes=t.ntpphes,
        )
        for t in request.teachers
    ]
    subjects = [
        Subject(
            id=s.id,
            name=s.name,
            group_id=s.group_id,
            required_sessions=s.required_sessions,
            campus_id=s.campus_id,
            student_count=s.student_count,
        )
        for s in request.subjects
    ]
    rooms = [
        Room(
            id=r.id,
            name=r.name,
            campus_id=r.campus_id,
            capacity=r.capacity,
            is_lab=r.is_lab,
        )
        for r in request.rooms
    ]
    timeslots = [
        Timeslot(
            day=ts.day,
            slot_index=ts.slot_index,
            start_time=_parse_time(ts.start_time),
            end_time=_parse_time(ts.end_time),
        )
        for ts in request.timeslots
    ]
    return SchedulingProblem(
        teachers=teachers,
        subjects=subjects,
        rooms=rooms,
        timeslots=timeslots,
        penalty_weights=PenaltyWeights(
            penalizacion1=request.penalty_weights.penalizacion1,
            penalizacion2=request.penalty_weights.penalizacion2,
        ),
        time_limit_seconds=request.time_limit_seconds,
    )


class GenerateScheduleUseCase:
    """
    Dispatches a scheduling job to the Celery task queue.
    Returns immediately with a job_id for polling or WebSocket tracking.
    """

    def __init__(self, repository: IScheduleRepository) -> None:
        self._repository = repository

    async def execute(
        self, request: ScheduleGenerationRequest, base_url: str = ""
    ) -> JobSubmittedResponse:
        from src.infrastructure.messaging.tasks import solve_schedule_task  # lazy import avoids circular

        job_id = str(uuid.uuid4())

        # Persist a PENDING placeholder so GET can find it immediately
        schedule = Schedule(job_id=job_id, status=ScheduleStatus.PENDING)
        await self._repository.save(schedule)

        # Dispatch async Celery task
        solve_schedule_task.apply_async(
            kwargs={"job_id": job_id, "payload": request.model_dump()},
            task_id=job_id,
        )

        return JobSubmittedResponse(
            job_id=job_id,
            ws_url=f"{base_url}/ws/{job_id}",
        )
