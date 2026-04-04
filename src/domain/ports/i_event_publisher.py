from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    job_id: str
    payload: dict[str, object]
    occurred_at: datetime


class IEventPublisher(ABC):
    """Port for publishing domain events (WebSocket broadcasts, webhooks, etc.)."""

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None: ...
