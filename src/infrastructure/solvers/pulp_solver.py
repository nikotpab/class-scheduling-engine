from __future__ import annotations

import time as _time
import logging
from itertools import product

import pulp

from src.domain.entities.schedule import Assignment
from src.domain.entities.teacher import TeacherType
from src.domain.exceptions import SolverError
from src.domain.ports.i_solver import ISolver, SchedulingProblem, ScheduleResult

logger = logging.getLogger(__name__)


class PuLPSolver(ISolver):
    """
    Concrete ISolver implementation using PuLP + CBC.

    Implements the Esquivel Tovar (2014) mathematical model translated from MM.lng:

    Decision variable:
        X[teacher_id, subject_id, room_id, campus_id, day, slot_index] ∈ {0, 1}

    Penalty variables (soft constraints):
        BZ[subject_id, group_id, day]  — gap/bache indicator (penalizacion2)
        BY[teacher_id, campus_id, day, slot_index] — PROCOM transfer indicator (penalizacion1)

    Hard constraints:
        R1  — Full coverage: each subject-group gets exactly required_sessions assignments
        R4  — No teacher double-booking: teacher teaches ≤ 1 class per (day, slot)
        R5  — Daily hour limit per teacher (ntd = max_hours_per_day)
        R6  — Intensity fulfilled: Σ assignments == required_sessions per subject
        R7  — Room not double-booked: room ≤ 1 assignment per (day, slot)
        R8  — Room capacity respected
        R9  — Teacher availability windows
        R10 — PROCOM travel: cannot teach campus_1 at slot t AND campus_2 at slot t+1
        R13 — PROHES: assigned exactly ½ × ntpphes distinct days
        PROJEX — Extended-hours teacher only assigned to is_extended_hours slots
    """

    def __init__(self, gap_tolerance: float = 0.05) -> None:
        self._gap_tolerance = gap_tolerance

    def solve(self, problem: SchedulingProblem) -> ScheduleResult:
        t_start = _time.perf_counter()

        try:
            result = self._build_and_solve(problem)
        except Exception as exc:
            raise SolverError(f"PuLP solver failed unexpectedly: {exc}") from exc

        elapsed = _time.perf_counter() - t_start
        result.solve_time_seconds = elapsed
        return result

    # ── Private ──────────────────────────────────────────────────────────────

    def _build_and_solve(self, p: SchedulingProblem) -> ScheduleResult:
        prob = pulp.LpProblem("ClassSchedulingEngine", pulp.LpMinimize)

        teachers = p.teachers
        subjects = p.subjects
        rooms = p.rooms
        timeslots = p.timeslots
        weights = p.penalty_weights

        # Index helpers
        teacher_map = {t.id: t for t in teachers}
        room_map = {r.id: r for r in rooms}
        ts_map = {(ts.day, ts.slot_index): ts for ts in timeslots}

        # Unique sorted slot_indices per day for ordering
        slots_by_day: dict[int, list[int]] = {}
        for ts in timeslots:
            slots_by_day.setdefault(ts.day, []).append(ts.slot_index)
        for day in slots_by_day:
            slots_by_day[day].sort()

        days = list({ts.day for ts in timeslots})

        # ── Decision variables ────────────────────────────────────────────────
        # X[tid, sid, rid, cid, day, slot] ∈ {0, 1}
        X: dict[tuple, pulp.LpVariable] = {}
        for teacher in teachers:
            for subject in subjects:
                for room in rooms:
                    for ts in timeslots:
                        # Prune: room must be on same campus as subject
                        if room.campus_id != subject.campus_id:
                            continue
                        # Prune: teacher must be allowed on that campus
                        if room.campus_id not in teacher.campus_ids:
                            continue
                        # Prune: PROJEX teachers only in extended-hours slots
                        if teacher.teacher_type == TeacherType.PROJEX and not ts.is_extended_hours:
                            continue
                        key = (teacher.id, subject.id, room.id, room.campus_id, ts.day, ts.slot_index)
                        var_name = f"X_{teacher.id}_{subject.id}_{room.id}_{ts.day}_{ts.slot_index}"
                        X[key] = pulp.LpVariable(var_name, cat="Binary")

        # ── Soft-constraint penalty variables ─────────────────────────────────

        # BZ[subject_id, day] = 1 if subject has an isolated single-period gap
        BZ: dict[tuple, pulp.LpVariable] = {}
        for subject in subjects:
            for day in days:
                key = (subject.id, day)
                BZ[key] = pulp.LpVariable(f"BZ_{subject.id}_{day}", cat="Binary")

        # BY[teacher_id, campus_id, day, slot] = 1 if PROCOM teacher crosses campuses
        BY: dict[tuple, pulp.LpVariable] = {}
        procom_teachers = [t for t in teachers if t.teacher_type == TeacherType.PROCOM]
        for teacher in procom_teachers:
            for campus_id in teacher.campus_ids:
                for ts in timeslots:
                    key = (teacher.id, campus_id, ts.day, ts.slot_index)
                    BY[key] = pulp.LpVariable(
                        f"BY_{teacher.id}_{campus_id}_{ts.day}_{ts.slot_index}",
                        cat="Binary",
                    )

        # ── Objective function ────────────────────────────────────────────────
        # MIN = Σ BZ × penalizacion2  +  Σ BY × penalizacion1
        gap_penalty = pulp.lpSum(
            BZ[(subj.id, day)] * weights.penalizacion2
            for subj in subjects
            for day in days
        )
        transfer_penalty = pulp.lpSum(
            BY[(t.id, camp, ts.day, ts.slot_index)] * weights.penalizacion1
            for t in procom_teachers
            for camp in t.campus_ids
            for ts in timeslots
            if (t.id, camp, ts.day, ts.slot_index) in BY
        )
        prob += gap_penalty + transfer_penalty, "Minimize_Gaps_And_Transfers"

        # ── Hard Constraints ──────────────────────────────────────────────────

        # R6 — Intensity: each subject must get exactly required_sessions assignments
        for subject in subjects:
            vars_for_subject = [
                v for k, v in X.items() if k[1] == subject.id
            ]
            if vars_for_subject:
                prob += (
                    pulp.lpSum(vars_for_subject) == subject.required_sessions,
                    f"R6_intensity_{subject.id}",
                )

        # R4 — No teacher double-booking per (day, slot)
        for teacher in teachers:
            for ts in timeslots:
                vars_teacher_slot = [
                    v for k, v in X.items()
                    if k[0] == teacher.id and k[4] == ts.day and k[5] == ts.slot_index
                ]
                if vars_teacher_slot:
                    prob += (
                        pulp.lpSum(vars_teacher_slot) <= 1,
                        f"R4_no_conflict_{teacher.id}_{ts.day}_{ts.slot_index}",
                    )

        # R5 — Daily hour limit per teacher
        for teacher in teachers:
            for day in days:
                vars_teacher_day = [
                    v for k, v in X.items()
                    if k[0] == teacher.id and k[4] == day
                ]
                if vars_teacher_day:
                    prob += (
                        pulp.lpSum(vars_teacher_day) <= teacher.max_hours_per_day,
                        f"R5_daily_limit_{teacher.id}_{day}",
                    )

        # R7 — Room not double-booked per (day, slot)
        for room in rooms:
            for ts in timeslots:
                vars_room_slot = [
                    v for k, v in X.items()
                    if k[2] == room.id and k[4] == ts.day and k[5] == ts.slot_index
                ]
                if vars_room_slot:
                    prob += (
                        pulp.lpSum(vars_room_slot) <= 1,
                        f"R7_room_conflict_{room.id}_{ts.day}_{ts.slot_index}",
                    )

        # R8 — Room capacity
        for subject in subjects:
            room_vars = [
                (k, v) for k, v in X.items()
                if k[1] == subject.id
            ]
            for key, var in room_vars:
                room = room_map[key[2]]
                if not room.can_fit(subject.student_count):
                    prob += (var == 0, f"R8_capacity_{key}")

        # R9 — Teacher availability
        for teacher in teachers:
            if not teacher.availability.slots:
                continue  # No restrictions
            for ts in timeslots:
                if teacher.is_restricted(ts.day, ts.slot_index):
                    constrained = [
                        v for k, v in X.items()
                        if k[0] == teacher.id and k[4] == ts.day and k[5] == ts.slot_index
                    ]
                    if constrained:
                        prob += (
                            pulp.lpSum(constrained) == 0,
                            f"R9_availability_{teacher.id}_{ts.day}_{ts.slot_index}",
                        )

        # R10 — PROCOM travel time: cannot teach campus_1 at slot t AND campus_2 at t+1
        # (Restriction 10/11/12 from MM.lng)
        for teacher in procom_teachers:
            campus_list = teacher.campus_ids
            for day in days:
                day_slots = slots_by_day.get(day, [])
                for i, slot_t in enumerate(day_slots[:-1]):
                    slot_t1 = day_slots[i + 1]
                    for c1, c2 in [(campus_list[0], campus_list[1]), (campus_list[1], campus_list[0])]:
                        vars_campus1_t = [
                            v for k, v in X.items()
                            if k[0] == teacher.id and k[3] == c1
                            and k[4] == day and k[5] == slot_t
                        ]
                        vars_campus2_t1 = [
                            v for k, v in X.items()
                            if k[0] == teacher.id and k[3] == c2
                            and k[4] == day and k[5] == slot_t1
                        ]
                        if vars_campus1_t and vars_campus2_t1:
                            prob += (
                                pulp.lpSum(vars_campus1_t) + pulp.lpSum(vars_campus2_t1) <= 1,
                                f"R10_procom_{teacher.id}_{c1}_to_{c2}_{day}_{slot_t}",
                            )

        # R13 — PROHES: assigned exactly ½ × ntpphes distinct days per campus
        for teacher in teachers:
            if teacher.teacher_type != TeacherType.PROHES:
                continue
            target_days = max(1, teacher.ntpphes // 2)
            for campus_id in teacher.campus_ids:
                # Binary: was teacher assigned on this campus on this day?
                day_assigned: dict[int, pulp.LpVariable] = {}
                for day in days:
                    day_var = pulp.LpVariable(
                        f"PROHES_{teacher.id}_{campus_id}_{day}", cat="Binary"
                    )
                    day_assigned[day] = day_var
                    daily_vars = [
                        v for k, v in X.items()
                        if k[0] == teacher.id and k[3] == campus_id and k[4] == day
                    ]
                    if daily_vars:
                        # day_var == 1 iff any assignment on that day
                        big_m = len(daily_vars)
                        prob += (
                            pulp.lpSum(daily_vars) <= big_m * day_var,
                            f"R13_link_ub_{teacher.id}_{campus_id}_{day}",
                        )
                        prob += (
                            pulp.lpSum(daily_vars) >= day_var,
                            f"R13_link_lb_{teacher.id}_{campus_id}_{day}",
                        )
                prob += (
                    pulp.lpSum(day_assigned.values()) == target_days,
                    f"R13_prohes_days_{teacher.id}_{campus_id}",
                )

        # ── Soft-constraint linkage ───────────────────────────────────────────

        # BZ linkage: BZ[subject, day] = 1 if subject is assigned on that day
        # in an isolated slot (gap detection heuristic via ≤ 1 session that day)
        for subject in subjects:
            for day in days:
                day_vars = [
                    v for k, v in X.items()
                    if k[1] == subject.id and k[4] == day
                ]
                if day_vars:
                    # A "bache" occurs when subject is assigned just 1 period that day
                    # We approximate: BZ ≥ 1 when Σ day_vars == 1
                    # Exact formulation: BZ = 1 - floor(Σ/total_per_day)
                    # Simplified: if total sessions per day ≤ 1 → penalty applies
                    n = len(day_vars)
                    prob += (
                        BZ[(subject.id, day)] >= 1 - pulp.lpSum(day_vars),
                        f"BZ_lower_{subject.id}_{day}",
                    )

        # BY linkage: BY[teacher, campus, day, slot] ≥ X[teacher, campus, day, slot]
        for teacher in procom_teachers:
            for campus_id in teacher.campus_ids:
                for ts in timeslots:
                    by_key = (teacher.id, campus_id, ts.day, ts.slot_index)
                    if by_key not in BY:
                        continue
                    x_vars = [
                        v for k, v in X.items()
                        if k[0] == teacher.id and k[3] == campus_id
                        and k[4] == ts.day and k[5] == ts.slot_index
                    ]
                    if x_vars:
                        prob += (
                            BY[by_key] >= pulp.lpSum(x_vars),
                            f"BY_link_{teacher.id}_{campus_id}_{ts.day}_{ts.slot_index}",
                        )

        # ── Solve ─────────────────────────────────────────────────────────────
        solver = pulp.PULP_CBC_CMD(
            timeLimit=p.time_limit_seconds,
            gapRel=self._gap_tolerance,
            msg=0,  # Suppress CBC stdout — logs go through structlog
        )
        prob.solve(solver)

        status_str = pulp.LpStatus[prob.status]
        logger.info("CBC finished: status=%s objective=%.4f", status_str, pulp.value(prob.objective) or 0)

        if prob.status == pulp.constants.LpStatusInfeasible:
            return ScheduleResult(
                assignments=[],
                penalty_score=0.0,
                solver_status="Infeasible",
                solve_time_seconds=0.0,
                solver_name="PuLP/CBC",
            )

        # ── Extract solution ──────────────────────────────────────────────────
        assignments: list[Assignment] = []
        subject_map = {s.id: s for s in subjects}

        for key, var in X.items():
            if var.varValue is not None and round(var.varValue) == 1:
                teacher_id, subject_id, room_id, campus_id, day, slot_idx = key
                subject = subject_map[subject_id]
                timeslot_id = f"{day}_{slot_idx}"
                assignments.append(
                    Assignment(
                        teacher_id=teacher_id,
                        subject_id=subject_id,
                        room_id=room_id,
                        timeslot_id=timeslot_id,
                        campus_id=campus_id,
                        group_id=subject.group_id,
                    )
                )

        penalty = pulp.value(prob.objective) or 0.0

        return ScheduleResult(
            assignments=assignments,
            penalty_score=float(penalty),
            solver_status=status_str,
            solve_time_seconds=0.0,  # filled by caller
            solver_name="PuLP/CBC",
        )
