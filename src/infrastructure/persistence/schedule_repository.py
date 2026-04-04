from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.schedule import Assignment, Schedule, ScheduleStatus
from src.domain.ports.i_schedule_repository import IScheduleRepository
from src.infrastructure.persistence.models import ScheduleJobORM


class SQLAlchemyScheduleRepository(IScheduleRepository):
    """Implements IScheduleRepository using async SQLAlchemy + PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, schedule: Schedule) -> Schedule:
        existing = await self._session.get(ScheduleJobORM, schedule.id)
        if existing:
            existing.status = schedule.status.value
            existing.penalty_score = schedule.penalty_score
            existing.solver_status = schedule.solver_status
            existing.error_message = schedule.error_message
            existing.result_assignments = [
                {
                    "teacher_id": a.teacher_id,
                    "subject_id": a.subject_id,
                    "room_id": a.room_id,
                    "timeslot_id": a.timeslot_id,
                    "campus_id": a.campus_id,
                    "group_id": a.group_id,
                }
                for a in schedule.assignments
            ]
            if schedule.status in (
                ScheduleStatus.OPTIMAL,
                ScheduleStatus.FEASIBLE,
                ScheduleStatus.INFEASIBLE,
                ScheduleStatus.FAILED,
            ):
                existing.completed_at = datetime.now(timezone.utc)
        else:
            orm = ScheduleJobORM(
                id=schedule.id,
                job_id=schedule.job_id,
                status=schedule.status.value,
                penalty_score=schedule.penalty_score,
                solver_status=schedule.solver_status,
                error_message=schedule.error_message,
                result_assignments=[],
            )
            self._session.add(orm)

        await self._session.commit()
        return schedule

    async def find_by_id(self, schedule_id: str) -> Schedule | None:
        orm = await self._session.get(ScheduleJobORM, schedule_id)
        if orm is None:
            return None
        return self._to_domain(orm)

    async def find_by_job_id(self, job_id: str) -> Schedule | None:
        stmt = select(ScheduleJobORM).where(ScheduleJobORM.job_id == job_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return self._to_domain(orm)

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[Schedule]:
        stmt = (
            select(ScheduleJobORM)
            .order_by(ScheduleJobORM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(orm) for orm in result.scalars().all()]

    async def delete(self, schedule_id: str) -> bool:
        orm = await self._session.get(ScheduleJobORM, schedule_id)
        if orm is None:
            return False
        await self._session.delete(orm)
        await self._session.commit()
        return True

    @staticmethod
    def _to_domain(orm: ScheduleJobORM) -> Schedule:
        assignments = [
            Assignment(
                teacher_id=a["teacher_id"],
                subject_id=a["subject_id"],
                room_id=a["room_id"],
                timeslot_id=a["timeslot_id"],
                campus_id=a["campus_id"],
                group_id=a["group_id"],
            )
            for a in (orm.result_assignments or [])
        ]
        return Schedule(
            id=orm.id,
            job_id=orm.job_id,
            status=ScheduleStatus(orm.status),
            assignments=assignments,
            penalty_score=orm.penalty_score or 0.0,
            solver_status=orm.solver_status or "",
            error_message=orm.error_message or "",
        )
