from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.application.schemas.inputs import ScheduleGenerationRequest
from src.application.schemas.outputs import JobSubmittedResponse, ScheduleJobResponse
from src.application.use_cases.generate_schedule import GenerateScheduleUseCase
from src.application.use_cases.get_schedule import GetScheduleUseCase
from src.api.dependencies import get_generate_use_case, get_query_use_case
from src.domain.exceptions import ScheduleNotFoundError
from src.infrastructure.persistence.schedule_repository import SQLAlchemyScheduleRepository
from src.api.dependencies import get_repository

router = APIRouter(prefix="/api/v1/schedules", tags=["Schedules"])


@router.post(
    "/generate",
    response_model=JobSubmittedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a schedule generation job",
    description=(
        "Validates all inputs via Pydantic, enqueues a background Celery task, "
        "and returns a job_id immediately. Connect to /ws/{job_id} for real-time updates."
    ),
)
async def generate_schedule(
    request: Request,
    body: ScheduleGenerationRequest,
    use_case: GenerateScheduleUseCase = Depends(get_generate_use_case),
) -> JobSubmittedResponse:
    base_url = str(request.base_url).rstrip("/")
    return await use_case.execute(body, base_url=base_url)


@router.get(
    "/{job_id}",
    response_model=ScheduleJobResponse,
    summary="Get schedule job status and result",
)
async def get_schedule(
    job_id: str,
    use_case: GetScheduleUseCase = Depends(get_query_use_case),
) -> ScheduleJobResponse:
    try:
        return await use_case.execute(job_id)
    except ScheduleNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/",
    response_model=list[ScheduleJobResponse],
    summary="List all schedule jobs",
)
async def list_schedules(
    limit: int = 20,
    offset: int = 0,
    repo: SQLAlchemyScheduleRepository = Depends(get_repository),
) -> list[ScheduleJobResponse]:
    from src.application.schemas.outputs import AssignmentOutput

    schedules = await repo.list_all(limit=limit, offset=offset)
    return [
        ScheduleJobResponse(
            job_id=s.job_id,
            schedule_id=s.id,
            status=s.status,
            penalty_score=s.penalty_score,
            solver_status=s.solver_status,
            error_message=s.error_message,
            assignments=[
                AssignmentOutput(
                    teacher_id=a.teacher_id,
                    subject_id=a.subject_id,
                    room_id=a.room_id,
                    timeslot_id=a.timeslot_id,
                    campus_id=a.campus_id,
                    group_id=a.group_id,
                )
                for a in s.assignments
            ],
        )
        for s in schedules
    ]


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a schedule job",
)
async def delete_schedule(
    job_id: str,
    repo: SQLAlchemyScheduleRepository = Depends(get_repository),
) -> None:
    from src.domain.exceptions import ScheduleNotFoundError

    schedule = await repo.find_by_job_id(job_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    await repo.delete(schedule.id)
