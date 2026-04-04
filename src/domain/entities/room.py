from __future__ import annotations

from dataclasses import dataclass

from src.domain.entities.teacher import DomainError


@dataclass
class Room:
    id: str
    name: str
    campus_id: str
    capacity: int
    is_lab: bool = False

    def __post_init__(self) -> None:
        if not self.id:
            raise DomainError("Room id cannot be empty.")
        if self.capacity < 1:
            raise DomainError("Room capacity must be >= 1.")

    def can_fit(self, student_count: int) -> bool:
        return self.capacity >= student_count
