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
        Run the full scheduling workflow:
        1. Fetch the pending Schedule aggregate.
        2. Persist it (status = RUNNING).
        3. Partition the problem by Campus.
        4. Invoke the solver sequentially per partition.
        5. Merge results and Persist.
        """
        schedule = await self._repository.find_by_job_id(job_id)
        if not schedule:
            schedule = Schedule(
                id=str(uuid.uuid4()),
                job_id=job_id,
                status=ScheduleStatus.PENDING,
            )
            
        schedule.mark_running()
        await self._repository.save(schedule)

        try:
            logger.info("Solver starting for job_id=%s with Divide and Conquer strategy", job_id)
            
            all_assignments = []
            total_penalty = 0.0
            overall_status = "Optimal"
            total_time = 0.0
            
            # Partition subjects by Campus ID
            campuses = list({s.campus_id for s in problem.subjects})
            
            from copy import deepcopy
            current_problem = deepcopy(problem)
            
            for campus in campuses:
                logger.info("Solving partition for campus: %s", campus)
                
                # Filter only subjects and rooms for this campus
                campus_subjects = [s for s in current_problem.subjects if s.campus_id == campus]
                if not campus_subjects:
                    continue
                    
                campus_rooms = [r for r in current_problem.rooms if r.campus_id == campus]
                
                partition = SchedulingProblem(
                    teachers=current_problem.teachers,
                    subjects=campus_subjects,
                    rooms=campus_rooms,
                    timeslots=current_problem.timeslots,
                    penalty_weights=current_problem.penalty_weights,
                    time_limit_seconds=current_problem.time_limit_seconds // len(campuses),
                )
                
                result = self._solver.solve(partition)
                
                if result.solver_status == "Infeasible":
                    overall_status = "Infeasible"
                    break
                    
                all_assignments.extend(result.assignments)
                total_penalty += result.penalty_score
                total_time += result.solve_time_seconds
                if "Feasible" in result.solver_status:
                    overall_status = "Feasible"
                    
                # Update availability for the next iteration (subtract used timeslots for teachers)
                teacher_used_slots = {}
                for a in result.assignments:
                    # Parse timeslot_id like '1_0' -> day=1, slot=0
                    day, slot = map(int, a.timeslot_id.split('_'))
                    teacher_used_slots.setdefault(a.teacher_id, set()).add((day, slot))
                    
                for t in current_problem.teachers:
                    if t.id in teacher_used_slots:
                        current_avail = set(t.availability.slots) if t.availability.slots else set(
                            (ts.day, ts.slot_index) for ts in current_problem.timeslots
                        )
                        new_avail = frozenset(current_avail - teacher_used_slots[t.id])
                        # Mutate the teacher's availability for the next partition
                        t.availability.slots = new_avail

            if overall_status == "Infeasible":
                schedule.mark_infeasible()
            else:
                schedule.mark_complete(
                    assignments=all_assignments,
                    penalty_score=total_penalty,
                    solver_status=overall_status,
                )
            logger.info(
                "Divide and Conquer finished job_id=%s status=%s score=%.2f time=%.1fs",
                job_id,
                overall_status,
                total_penalty,
                total_time,
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
