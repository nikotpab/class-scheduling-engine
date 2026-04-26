from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Sub-schemas ──────────────────────────────────────────────────────────────

class AvailabilitySlotInput(BaseModel):
    day: Annotated[int, Field(ge=0, le=5, description="0=Monday … 5=Saturday")]
    slot_index: Annotated[int, Field(ge=0, description="Integer slot index")]


class TeacherInput(BaseModel):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    teacher_type: Literal["REGULAR", "PROCOM", "PROJEX", "PROHES"] = "REGULAR"
    campus_ids: Annotated[list[str], Field(min_length=1, max_length=10)]
    availability_slots: list[AvailabilitySlotInput] = Field(
        default_factory=list,
        description="Explicit available (day, slot_index) pairs. Empty = always available.",
    )
    max_hours_per_day: Annotated[int, Field(ge=1, le=12)] = 6
    ntpphes: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def validate_procom_campuses(self) -> "TeacherInput":
        if self.teacher_type == "PROCOM" and len(self.campus_ids) < 2:
            raise ValueError("PROCOM teachers must list at least 2 campus_ids.")
        if self.teacher_type == "PROHES" and self.ntpphes < 1:
            raise ValueError("PROHES teachers must have ntpphes >= 1.")
        return self


class SubjectInput(BaseModel):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    group_id: Annotated[str, Field(min_length=1, max_length=64)]
    required_sessions: Annotated[int, Field(ge=1, le=30)]
    campus_id: Annotated[str, Field(min_length=1, max_length=64)]
    student_count: Annotated[int, Field(ge=0)] = 0
    eligible_teacher_ids: list[str] = Field(default_factory=list)


class RoomInput(BaseModel):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    campus_id: Annotated[str, Field(min_length=1, max_length=64)]
    capacity: Annotated[int, Field(ge=1, le=500)]
    is_lab: bool = False


class TimeslotInput(BaseModel):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    day: Annotated[int, Field(ge=0, le=5)]
    slot_index: Annotated[int, Field(ge=0)]
    start_time: Annotated[str, Field(pattern=r"^\d{2}:\d{2}$")]
    end_time: Annotated[str, Field(pattern=r"^\d{2}:\d{2}$")]

    @field_validator("end_time", mode="after")
    @classmethod
    def end_after_start(cls, v: str, info: object) -> str:
        return v   # Full cross-field validation delegated to domain entity


class PenaltyWeightsInput(BaseModel):
    penalizacion1: Annotated[float, Field(ge=0.0, le=100.0)] = 2.0
    penalizacion2: Annotated[float, Field(ge=0.0, le=100.0)] = 1.0


# ── Top-level request ────────────────────────────────────────────────────────

class ScheduleGenerationRequest(BaseModel):
    """
    Full validated payload for a schedule generation request.
    Pydantic v2 enforces all constraints before data reaches the solver,
    preventing parameter-injection attacks on CBC command-line arguments.
    """
    teachers: Annotated[list[TeacherInput], Field(min_length=1, max_length=10000)]
    subjects: Annotated[list[SubjectInput], Field(min_length=1, max_length=10000)]
    rooms: Annotated[list[RoomInput], Field(min_length=1, max_length=10000)]
    timeslots: Annotated[list[TimeslotInput], Field(min_length=1, max_length=10000)]
    penalty_weights: PenaltyWeightsInput = Field(default_factory=PenaltyWeightsInput)
    solver: Literal["pulp_cbc", "tabu_search", "ortools_cpsat"] = "pulp_cbc"
    time_limit_seconds: Annotated[int, Field(ge=10, le=3600)] = 300

    @model_validator(mode="after")
    def validate_referential_integrity(self) -> "ScheduleGenerationRequest":
        campus_ids = {r.campus_id for r in self.rooms}
        for subj in self.subjects:
            if subj.campus_id not in campus_ids:
                raise ValueError(
                    f"Subject '{subj.id}' references unknown campus '{subj.campus_id}'."
                )
        return self


class PenaltyWeightsUpdateRequest(BaseModel):
    penalizacion1: Annotated[float, Field(ge=0.0, le=100.0)]
    penalizacion2: Annotated[float, Field(ge=0.0, le=100.0)]
