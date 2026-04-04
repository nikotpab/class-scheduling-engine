from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.schedule import Schedule


class IScheduleRepository(ABC):
    """Port for persisting and retrieving Schedule aggregates."""

    @abstractmethod
    async def save(self, schedule: Schedule) -> Schedule: ...

    @abstractmethod
    async def find_by_id(self, schedule_id: str) -> Schedule | None: ...

    @abstractmethod
    async def find_by_job_id(self, job_id: str) -> Schedule | None: ...

    @abstractmethod
    async def list_all(self, limit: int = 50, offset: int = 0) -> list[Schedule]: ...

    @abstractmethod
    async def delete(self, schedule_id: str) -> bool: ...
