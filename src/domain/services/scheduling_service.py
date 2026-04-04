from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from src.domain.entities.schedule import Schedule, ScheduleStatus
from src.domain.exceptions import SolverError
from src.domain.ports.i_event_publisher import DomainEvent, IEventPublisher
from src.domain.ports.i_schedule_repository import IScheduleRepository
from src.domain.ports.i_solver import ISolver, SchedulingProblem

logger = logging.getLogger(__name__)


class SchedulingService:
    """
    Domain Service — orchestrates the scheduling workflow.
    Pure business logic: no I/O, no framework dependencies.
    """

    def __init__(
        self,
        solver: ISolver,
        repository: IScheduleRepository,
        publisher: IEventPublisher,
    ) -> None:
        self._solver = solver
        self._repository = repository
        self._publisher = publisher

    async def generate(self, problem: SchedulingProblem, job_id: str) -> Schedule:
        """
        Run the full scheduling pipeline:
        1. Create a pending Schedule aggregate.
        2. Persist it (status = RUNNING).
        3. Invoke the solver.
        4. Persist the result.
        5. Publish a domain event for real-time notification.
        """
        schedule = Schedule(
            id=str(uuid.uuid4()),
            job_id=job_id,
            status=ScheduleStatus.PENDING,
        )
        schedule.mark_running()
        await self._repository.save(schedule)

        try:
            logger.info("Solver starting for job_id=%s", job_id)
            result = self._solver.solve(problem)

            if result.solver_status == "Infeasible":
                schedule.mark_infeasible()
            else:
                schedule.mark_complete(
                    assignments=result.assignments,
                    penalty_score=result.penalty_score,
                    solver_status=result.solver_status,
                )
            logger.info(
                "Solver finished job_id=%s status=%s score=%.2f time=%.1fs",
                job_id,
                result.solver_status,
                result.penalty_score,
                result.solve_time_seconds,
            )

        except SolverError as exc:
            logger.exception("Solver error for job_id=%s", job_id)
            schedule.mark_failed(str(exc))

        await self._repository.save(schedule)

        event = DomainEvent(
            event_type="schedule.completed",
            job_id=job_id,
            payload={
                "schedule_id": schedule.id,
                "status": schedule.status.value,
                "penalty_score": schedule.penalty_score,
            },
            occurred_at=datetime.now(timezone.utc),
        )
        await self._publisher.publish(event)

        return schedule
