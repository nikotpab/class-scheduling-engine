from __future__ import annotations

import asyncio
import logging

from src.infrastructure.messaging.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="src.infrastructure.messaging.tasks.solve_schedule_task",
    bind=True,
    max_retries=0,
)
def solve_schedule_task(self: object, *, job_id: str, payload: dict) -> dict:
    """
    Celery task: deserialises the request payload, runs the solver,
    persists the result, and broadcasts the completion event via WebSocket.

    Uses asyncio.run() because SQLAlchemy async sessions need an event loop.
    """
    try:
        return asyncio.run(_run_pipeline(job_id=job_id, payload=payload))
    except Exception as exc:
        logger.exception("Task failed for job_id=%s", job_id)
        asyncio.run(_mark_failed(job_id, str(exc)))
        raise


async def _run_pipeline(job_id: str, payload: dict) -> dict:
    from src.application.schemas.inputs import ScheduleGenerationRequest
    from src.application.use_cases.generate_schedule import _map_request_to_problem
    from src.domain.services.scheduling_service import SchedulingService
    from src.infrastructure.persistence.database import AsyncSessionFactory, engine
    from src.infrastructure.persistence.schedule_repository import SQLAlchemyScheduleRepository
    from src.infrastructure.solvers.solver_factory import get_solver
    from src.infrastructure.websockets.connection_manager import manager
    from src.domain.ports.i_event_publisher import DomainEvent, IEventPublisher
    from datetime import datetime, timezone

    class WebSocketPublisher(IEventPublisher):
        async def publish(self, event: DomainEvent) -> None:
            await manager.broadcast(
                event.job_id,
                {
                    "event": event.event_type,
                    "job_id": event.job_id,
                    **{k: str(v) for k, v in event.payload.items()},
                },
            )

    request = ScheduleGenerationRequest.model_validate(payload)
    problem = _map_request_to_problem(request)
    problem.time_limit_seconds = request.time_limit_seconds

    solver = get_solver(request.solver)

    try:
        async with AsyncSessionFactory() as session:
            repository = SQLAlchemyScheduleRepository(session)
            publisher = WebSocketPublisher()
            service = SchedulingService(
                solver=solver,
                repository=repository,
                publisher=publisher,
            )
            schedule = await service.generate(problem, job_id)

        return {
            "schedule_id": schedule.id,
            "status": schedule.status.value,
            "penalty_score": schedule.penalty_score,
        }
    finally:
        # Crucial for Celery + Asyncio: cleanup the engine pool so the next task 
        # (which will run in a new asyncio.run() loop) doesn't inherit stale locks.
        await engine.dispose()


async def _mark_failed(job_id: str, error: str) -> None:
    from src.infrastructure.persistence.database import AsyncSessionFactory
    from src.infrastructure.persistence.schedule_repository import SQLAlchemyScheduleRepository

    async with AsyncSessionFactory() as session:
        repo = SQLAlchemyScheduleRepository(session)
        schedule = await repo.find_by_job_id(job_id)
        if schedule:
            schedule.mark_failed(error)
            await repo.save(schedule)
