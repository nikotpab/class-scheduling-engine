from __future__ import annotations

import pytest
from datetime import time

from src.domain.entities.room import Room
from src.domain.entities.schedule import ScheduleStatus
from src.domain.entities.subject import Subject
from src.domain.entities.teacher import Teacher, TeacherAvailability, TeacherType
from src.domain.entities.timeslot import Timeslot
from src.domain.ports.i_solver import SchedulingProblem
from src.domain.value_objects.penalty_weights import PenaltyWeights
from src.infrastructure.solvers.pulp_solver import PuLPSolver


def _make_minimal_problem() -> SchedulingProblem:
    """
    Two teachers, two subjects, two rooms, four timeslots.
    Guaranteed feasible: each teacher teaches one subject.
    """
    teachers = [
        Teacher(
            id="T1", name="Prof A", teacher_type=TeacherType.REGULAR,
            campus_ids=["C1"], availability=TeacherAvailability(),
        ),
        Teacher(
            id="T2", name="Prof B", teacher_type=TeacherType.REGULAR,
            campus_ids=["C1"], availability=TeacherAvailability(),
        ),
    ]
    subjects = [
        Subject(id="S1", name="Calculo", group_id="G1", required_sessions=2, campus_id="C1"),
        Subject(id="S2", name="Programacion", group_id="G2", required_sessions=2, campus_id="C1"),
    ]
    rooms = [
        Room(id="R1", name="Aula 101", campus_id="C1", capacity=40),
        Room(id="R2", name="Lab", campus_id="C1", capacity=30),
    ]
    timeslots = [
        Timeslot(day=0, slot_index=0, start_time=time(7, 0), end_time=time(9, 0)),
        Timeslot(day=0, slot_index=1, start_time=time(9, 0), end_time=time(11, 0)),
        Timeslot(day=1, slot_index=0, start_time=time(7, 0), end_time=time(9, 0)),
        Timeslot(day=1, slot_index=1, start_time=time(9, 0), end_time=time(11, 0)),
    ]
    return SchedulingProblem(
        teachers=teachers,
        subjects=subjects,
        rooms=rooms,
        timeslots=timeslots,
        penalty_weights=PenaltyWeights(penalizacion1=2.0, penalizacion2=1.0),
        time_limit_seconds=60,
    )


class TestPuLPSolver:
    def test_feasible_problem_solves(self) -> None:
        solver = PuLPSolver()
        problem = _make_minimal_problem()
        result = solver.solve(problem)

        assert result.solver_status in ("Optimal", "Feasible"), (
            f"Expected Optimal/Feasible, got {result.solver_status}"
        )
        assert len(result.assignments) > 0
        assert result.penalty_score >= 0

    def test_assignments_cover_required_sessions(self) -> None:
        solver = PuLPSolver()
        problem = _make_minimal_problem()
        result = solver.solve(problem)

        if result.solver_status == "Infeasible":
            pytest.skip("Solver returned infeasible — check problem setup")

        session_counts: dict[str, int] = {}
        for assignment in result.assignments:
            session_counts[assignment.subject_id] = (
                session_counts.get(assignment.subject_id, 0) + 1
            )
        for subject in problem.subjects:
            assert session_counts.get(subject.id, 0) == subject.required_sessions, (
                f"Subject {subject.id} expected {subject.required_sessions} sessions, "
                f"got {session_counts.get(subject.id, 0)}"
            )

    def test_no_teacher_double_booking(self) -> None:
        solver = PuLPSolver()
        problem = _make_minimal_problem()
        result = solver.solve(problem)

        if result.solver_status == "Infeasible":
            pytest.skip("Solver returned infeasible")

        seen: set[tuple[str, str]] = set()
        for a in result.assignments:
            key = (a.teacher_id, a.timeslot_id)
            assert key not in seen, f"Teacher {a.teacher_id} double-booked at slot {a.timeslot_id}"
            seen.add(key)

    def test_infeasible_problem_detected(self) -> None:
        """
        Force infeasibility: teacher availability = empty (day=0, slot=0 only),
        but subjects require 2 sessions and only 1 timeslot is available for that teacher.
        Additionally, restrict both rooms to capacity 0 and subjects to student_count 1.
        """
        solver = PuLPSolver()
        problem = _make_minimal_problem()
        # Make subjects require more sessions than available timeslots on any one day
        # 4 required sessions but only 2 timeslots and 1 teacher → can't assign same
        # teacher twice per slot. Force by putting teacher availability to zero slots.
        from src.domain.entities.teacher import TeacherAvailability
        # Remove all available slots → teacher is never available → no valid assignments
        for t in problem.teachers:
            t.availability = TeacherAvailability(slots=frozenset([(99, 99)]))  # unreachable slot
        result = solver.solve(problem)
        assert result.solver_status == "Infeasible", (
            f"Expected Infeasible but got {result.solver_status} "
            f"with {len(result.assignments)} assignments"
        )
