from __future__ import annotations

from src.domain.ports.i_solver import ISolver
from src.infrastructure.config.settings import settings
from src.infrastructure.solvers.pulp_solver import PuLPSolver
from src.infrastructure.solvers.tabu_solver_stub import TabuSearchSolverStub
from src.infrastructure.solvers.ortools_solver import OrToolsCPSolver


def get_solver(solver_name: str | None = None) -> ISolver:
    """
    Factory function — returns the appropriate ISolver instance.
    Defaults to the configured DEFAULT_SOLVER in settings.
    """
    name = (solver_name or settings.DEFAULT_SOLVER).lower()

    if name == "pulp_cbc":
        return PuLPSolver(gap_tolerance=settings.SOLVER_GAP_TOLERANCE)
    elif name == "tabu_search":
        return TabuSearchSolverStub()
    elif name == "ortools_cpsat":
        return OrToolsCPSolver()
    else:
        raise ValueError(
            f"Unknown solver '{name}'. Available: 'pulp_cbc', 'tabu_search', 'ortools_cpsat'."
        )
