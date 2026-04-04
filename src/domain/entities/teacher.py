from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DomainError(Exception):
    """Base for all domain-level invariant violations."""


class TeacherType(str, Enum):
    REGULAR = "REGULAR"
    PROCOM = "PROCOM"    # Shared across campuses — penalises cross-campus travel
    PROJEX = "PROJEX"    # Extended-hours teacher — only assigned after normal schedule
    PROHES = "PROHES"    # Special-schedule teacher — exactly ½×ntpphes days per campus


@dataclass(frozen=True)
class TeacherAvailability:
    """Maps (day_index, slot_index) → available."""
    slots: frozenset[tuple[int, int]] = field(default_factory=frozenset)

    def is_available(self, day: int, slot: int) -> bool:
        return (day, slot) in self.slots

    @classmethod
    def always(cls) -> "TeacherAvailability":
        return cls(slots=frozenset())  # empty == unrestricted; checked via is_restricted


@dataclass
class Teacher:
    id: str
    name: str
    teacher_type: TeacherType
    campus_ids: list[str]            # Campuses where teacher can be assigned
    availability: TeacherAvailability
    max_hours_per_day: int = 6       # ntd from MM.lng DATA section
    ntpphes: int = 0                 # Only relevant for PROHES teachers

    def __post_init__(self) -> None:
        if not self.id:
            raise DomainError("Teacher id cannot be empty.")
        if not self.name:
            raise DomainError("Teacher name cannot be empty.")
        if self.max_hours_per_day < 1 or self.max_hours_per_day > 12:
            raise DomainError("max_hours_per_day must be between 1 and 12.")
        if self.teacher_type == TeacherType.PROCOM and len(self.campus_ids) < 2:
            raise DomainError("PROCOM teacher must be assigned to at least 2 campuses.")
        if self.teacher_type == TeacherType.PROHES and self.ntpphes < 1:
            raise DomainError("PROHES teacher must have ntpphes >= 1.")

    def is_restricted(self, day: int, slot: int) -> bool:
        """Return True if availability is explicitly defined and slot is NOT in it."""
        if not self.availability.slots:
            return False  # No restrictions defined → always available
        return not self.availability.is_available(day, slot)
