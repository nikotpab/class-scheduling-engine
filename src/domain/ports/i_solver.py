from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.domain.entities.room import Room
from src.domain.entities.schedule import Assignment
from src.domain.entities.subject import Subject
from src.domain.entities.teacher import Teacher
from src.domain.entities.timeslot import Timeslot
from src.domain.value_objects.penalty_weights import PenaltyWeights


@dataclass
class SchedulingProblem:
    """Input value object passed to any ISolver implementation."""
    teachers: list[Teacher]
    subjects: list[Subject]
    rooms: list[Room]
    timeslots: list[Timeslot]
    penalty_weights: PenaltyWeights
    time_limit_seconds: int = 300
    gap_tolerance: float = 0.05
    extra_params: dict[str, object] = field(default_factory=dict)


@dataclass
class ScheduleResult:
    """Output value object returned by any ISolver implementation."""
    assignments: list[Assignment]
    penalty_score: float
    solver_status: str    # "Optimal" | "Feasible" | "Infeasible" | "Error"
    solve_time_seconds: float
    solver_name: str


class ISolver(ABC):
    """
    Strategy port — defines the contract for all schedule solver implementations.
    Concrete implementations live in src/infrastructure/solvers/.
    """

    @abstractmethod
    def solve(self, problem: SchedulingProblem) -> ScheduleResult:
        """
        Solve the scheduling problem and return a result.
        Raises SolverError on unexpected failure.
        """
