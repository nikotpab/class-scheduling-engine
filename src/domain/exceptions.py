from __future__ import annotations


class DomainError(Exception):
    """Raised when a domain invariant is violated."""


class SolverError(Exception):
    """Raised when the solver encounters an unexpected failure."""


class InfeasibleProblemError(Exception):
    """Raised when the scheduling problem has no valid solution."""


class ScheduleNotFoundError(Exception):
    """Raised when a requested schedule does not exist."""


class JobNotFoundError(Exception):
    """Raised when a requested job does not exist."""
