from __future__ import annotations

from dataclasses import dataclass

from src.domain.entities.teacher import DomainError


@dataclass(frozen=True)
class PenaltyWeights:
    """
    Immutable value object representing the soft-constraint penalty coefficients
    from the MM.lng DATA section:
        penalizacion1 = cost per inter-campus transfer (PROCOM teachers, BZ variable)
        penalizacion2 = cost per gap/bache in a teacher's daily schedule (BY variable)
    """
    penalizacion1: float = 2.0
    penalizacion2: float = 1.0

    def __post_init__(self) -> None:
        if self.penalizacion1 < 0:
            raise DomainError("penalizacion1 must be >= 0.")
        if self.penalizacion2 < 0:
            raise DomainError("penalizacion2 must be >= 0.")
