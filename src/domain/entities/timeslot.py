from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from src.domain.entities.teacher import DomainError

# Operational windows per README
_WEEKDAY_START = time(7, 0)
_WEEKDAY_END = time(22, 0)
_SATURDAY_START = time(7, 0)
_SATURDAY_END = time(13, 0)
_LUNCH_START = time(12, 0)
_LUNCH_END = time(13, 0)

# Day indices: 0=Monday … 4=Friday, 5=Saturday
_SATURDAY_INDEX = 5


@dataclass(frozen=True)
class Timeslot:
    day: int            # 0–5  (Mon–Sat)
    slot_index: int     # Integer index used in LP constraint math (t in MM.lng)
    start_time: time
    end_time: time

    def __post_init__(self) -> None:
        if self.day < 0 or self.day > 5:
            raise DomainError(f"day must be 0–5 (Mon–Sat), got {self.day}.")
        if self.start_time >= self.end_time:
            raise DomainError("start_time must be before end_time.")
        self._validate_operational_window()
        self._validate_lunch_block()

    def _validate_operational_window(self) -> None:
        if self.day == _SATURDAY_INDEX:
            if self.start_time < _SATURDAY_START or self.end_time > _SATURDAY_END:
                raise DomainError(
                    f"Saturday timeslot {self} is outside 07:00–13:00 window."
                )
        else:
            if self.start_time < _WEEKDAY_START or self.end_time > _WEEKDAY_END:
                raise DomainError(
                    f"Weekday timeslot {self} is outside 07:00–22:00 window."
                )

    def _validate_lunch_block(self) -> None:
        overlaps_lunch = self.start_time < _LUNCH_END and self.end_time > _LUNCH_START
        if overlaps_lunch:
            raise DomainError(
                f"Timeslot {self} overlaps the mandatory lunch block (12:00–13:00)."
            )

    @property
    def is_extended_hours(self) -> bool:
        """Slot after 18:00 — relevant for PROJEX teacher filtering."""
        return self.start_time >= time(18, 0)

    @property
    def day_name(self) -> str:
        names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        return names[self.day]
