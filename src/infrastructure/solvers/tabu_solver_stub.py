from __future__ import annotations

from src.domain.exceptions import SolverError
from src.domain.ports.i_solver import ISolver, ScheduleResult, SchedulingProblem


class TabuSearchSolverStub(ISolver):
    """
    Stub implementation of ISolver for Tabu Search metaheuristic.
    Satisfies the Strategy pattern — plug in a real implementation when ready.
    """

    def solve(self, problem: SchedulingProblem) -> ScheduleResult:
        raise SolverError(
            "TabuSearchSolver is not yet implemented. "
            "Use solver='pulp_cbc' in your request, or implement this class "
            "in src/infrastructure/solvers/tabu_solver.py."
        )
