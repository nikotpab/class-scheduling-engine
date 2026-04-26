from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.entities.teacher import DomainError


@dataclass
class Subject:
    id: str
    name: str
    group_id: str              # Academic group that takes this subject
    required_sessions: int     # Total weekly periods (intensity = iag in MM.lng)
    campus_id: str             # Primary campus for this subject
    student_count: int = 0    # For room-capacity matching
    eligible_teacher_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.id:
            raise DomainError("Subject id cannot be empty.")
        if self.required_sessions < 1:
            raise DomainError("required_sessions must be >= 1.")
        if self.student_count < 0:
            raise DomainError("student_count cannot be negative.")
