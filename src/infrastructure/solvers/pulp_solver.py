from __future__ import annotations

import time as _time
import logging
from collections import defaultdict

import pulp

from src.domain.entities.schedule import Assignment
from src.domain.entities.teacher import TeacherType
from src.domain.exceptions import SolverError
from src.domain.ports.i_solver import ISolver, SchedulingProblem, ScheduleResult

logger = logging.getLogger(__name__)


class PuLPSolver(ISolver):
    """
    Optimized ISolver implementation using PuLP + CBC.
    Uses inverse indexing and dynamic constraint generation to support large datasets
    without memory crashes or O(N^4) loop overhead.
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

        # Pre-groupings for O(1) lookups and memory-efficient generation
        subject_map = {s.id: s for s in subjects}
        room_map = {r.id: r for r in rooms}
        teacher_map = {t.id: t for t in teachers}
        
        rooms_by_campus = defaultdict(list)
        for r in rooms:
            rooms_by_campus[r.campus_id].append(r)
            
        teachers_by_campus = defaultdict(list)
        for t in teachers:
            for cid in t.campus_ids:
                teachers_by_campus[cid].append(t)

        slots_by_day = defaultdict(list)
        for ts in timeslots:
            slots_by_day[ts.day].append(ts.slot_index)
        for day in slots_by_day:
            slots_by_day[day].sort()

        days = list({ts.day for ts in timeslots})
        procom_teachers = [t for t in teachers if t.teacher_type == TeacherType.PROCOM]

        # Aggregation dictionaries for fast constraint building
        vars_by_subject = defaultdict(list)
        vars_by_teacher_slot = defaultdict(list)
        vars_by_teacher_day = defaultdict(list)
        vars_by_room_slot = defaultdict(list)
        
        vars_by_teacher_campus_day = defaultdict(list)
        vars_by_teacher_campus_day_slot = defaultdict(list)
        vars_by_subject_day = defaultdict(list)

        X = {}

        import hashlib

        # ── Decision variables (O(Valid) instead of O(T*S*R*F)) ───────────────
        for subject in subjects:
            cid = subject.campus_id
            
            # Prune R8 & Reduce space: Only consider the 5 best-fit rooms to prevent Out of Memory
            valid_rooms = sorted(
                [r for r in rooms_by_campus[cid] if r.can_fit(subject.student_count)],
                key=lambda r: r.capacity
            )[:5]
            
            # Prune combinatorics: Limit to 5 "qualified" teachers per subject to prevent OOM
            all_cid_teachers = teachers_by_campus[cid]
            if not all_cid_teachers:
                continue
                
            hash_val = int(hashlib.md5(subject.id.encode()).hexdigest(), 16)
            start_idx = hash_val % len(all_cid_teachers)
            valid_teachers = [all_cid_teachers[(start_idx + i) % len(all_cid_teachers)] for i in range(min(5, len(all_cid_teachers)))]
            
            for teacher in valid_teachers:
                for ts in timeslots:
                    # Prune R9: Teacher availability
                    if teacher.availability.slots and teacher.is_restricted(ts.day, ts.slot_index):
                        continue
                    # Prune PROJEX: Extended hours only
                    if teacher.teacher_type == TeacherType.PROJEX and not ts.is_extended_hours:
                        continue
                        
                    for room in valid_rooms:
                        key = (teacher.id, subject.id, room.id, cid, ts.day, ts.slot_index)
                        var = pulp.LpVariable(f"X_{teacher.id}_{subject.id}_{room.id}_{ts.day}_{ts.slot_index}", cat="Binary")
                        X[key] = var
                        
                        vars_by_subject[subject.id].append(var)
                        vars_by_teacher_slot[(teacher.id, ts.day, ts.slot_index)].append(var)
                        vars_by_teacher_day[(teacher.id, ts.day)].append(var)
                        vars_by_room_slot[(room.id, ts.day, ts.slot_index)].append(var)
                        vars_by_teacher_campus_day[(teacher.id, cid, ts.day)].append(var)
                        vars_by_teacher_campus_day_slot[(teacher.id, cid, ts.day, ts.slot_index)].append(var)
                        vars_by_subject_day[(subject.id, ts.day)].append(var)

        # ── Soft-constraint penalty variables ─────────────────────────────────
        BZ = {}
        for subject in subjects:
            for day in days:
                key = (subject.id, day)
                BZ[key] = pulp.LpVariable(f"BZ_{subject.id}_{day}", cat="Binary")

        BY = {}
        for teacher in procom_teachers:
            for cid in teacher.campus_ids:
                for ts in timeslots:
                    key = (teacher.id, cid, ts.day, ts.slot_index)
                    BY[key] = pulp.LpVariable(f"BY_{teacher.id}_{cid}_{ts.day}_{ts.slot_index}", cat="Binary")

        # ── Objective function ────────────────────────────────────────────────
        gap_penalty = pulp.lpSum(BZ[(s.id, d)] * weights.penalizacion2 for s in subjects for d in days)
        transfer_penalty = pulp.lpSum(
            BY[(t.id, c, ts.day, ts.slot_index)] * weights.penalizacion1 
            for t in procom_teachers for c in t.campus_ids for ts in timeslots
        )
        prob += gap_penalty + transfer_penalty, "Minimize_Gaps_And_Transfers"

        # ── Hard Constraints ──────────────────────────────────────────────────
        
        # R6 — Intensity
        for subject in subjects:
            prob += pulp.lpSum(vars_by_subject[subject.id]) == subject.required_sessions, f"R6_{subject.id}"

        # R4 — No teacher double-booking
        for (tid, day, slot), var_list in vars_by_teacher_slot.items():
            if var_list:
                prob += pulp.lpSum(var_list) <= 1, f"R4_{tid}_{day}_{slot}"

        # R5 — Daily hour limit per teacher
        for (tid, day), var_list in vars_by_teacher_day.items():
            if var_list:
                limit = teacher_map[tid].max_hours_per_day
                prob += pulp.lpSum(var_list) <= limit, f"R5_{tid}_{day}"

        # R7 — Room not double-booked
        for (rid, day, slot), var_list in vars_by_room_slot.items():
            if var_list:
                prob += pulp.lpSum(var_list) <= 1, f"R7_{rid}_{day}_{slot}"

        # R8 (Capacity) and R9 (Availability) are completely pruned in O(1) during variable generation.

        # R10 — PROCOM travel time (cannot teach across campuses in consecutive slots)
        for teacher in procom_teachers:
            campus_list = teacher.campus_ids
            if len(campus_list) < 2:
                continue
            for day in days:
                day_slots = slots_by_day.get(day, [])
                for i, slot_t in enumerate(day_slots[:-1]):
                    slot_t1 = day_slots[i + 1]
                    for c1, c2 in [(campus_list[0], campus_list[1]), (campus_list[1], campus_list[0])]:
                        v1 = vars_by_teacher_campus_day_slot.get((teacher.id, c1, day, slot_t), [])
                        v2 = vars_by_teacher_campus_day_slot.get((teacher.id, c2, day, slot_t1), [])
                        if v1 and v2:
                            prob += pulp.lpSum(v1) + pulp.lpSum(v2) <= 1, f"R10_{teacher.id}_{c1}_{c2}_{day}_{slot_t}"

        # R13 — PROHES assigned exactly ½ × ntpphes distinct days per campus
        for teacher in teachers:
            if teacher.teacher_type != TeacherType.PROHES:
                continue
            target_days = max(1, teacher.ntpphes // 2)
            for campus_id in teacher.campus_ids:
                day_assigned = []
                for day in days:
                    day_var = pulp.LpVariable(f"PROHES_{teacher.id}_{campus_id}_{day}", cat="Binary")
                    day_assigned.append(day_var)
                    daily_vars = vars_by_teacher_campus_day.get((teacher.id, campus_id, day), [])
                    if daily_vars:
                        big_m = len(daily_vars)
                        prob += pulp.lpSum(daily_vars) <= big_m * day_var, f"R13_ub_{teacher.id}_{campus_id}_{day}"
                        prob += pulp.lpSum(daily_vars) >= day_var, f"R13_lb_{teacher.id}_{campus_id}_{day}"
                    else:
                        prob += day_var == 0, f"R13_zero_{teacher.id}_{campus_id}_{day}"
                        
                prob += pulp.lpSum(day_assigned) == target_days, f"R13_days_{teacher.id}_{campus_id}"

        # ── Soft-constraint linkage ───────────────────────────────────────────
        
        # BZ linkage (Gap/Bache) - approx gaps when sessions per day == 1
        for subject in subjects:
            for day in days:
                day_vars = vars_by_subject_day.get((subject.id, day), [])
                if day_vars:
                    prob += BZ[(subject.id, day)] >= 1 - pulp.lpSum(day_vars), f"BZ_{subject.id}_{day}"

        # BY linkage (PROCOM travel cross penalty)
        for teacher in procom_teachers:
            for cid in teacher.campus_ids:
                for ts in timeslots:
                    x_vars = vars_by_teacher_campus_day_slot.get((teacher.id, cid, ts.day, ts.slot_index), [])
                    if x_vars:
                        prob += BY[(teacher.id, cid, ts.day, ts.slot_index)] >= pulp.lpSum(x_vars), f"BY_{teacher.id}_{cid}_{ts.day}_{ts.slot_index}"

        # ── Solve ─────────────────────────────────────────────────────────────
        solver = pulp.PULP_CBC_CMD(
            timeLimit=p.time_limit_seconds,
            gapRel=self._gap_tolerance,
            threads=4,  # Reduced from 8 to 4 to prevent Out of Memory SIGKILL on 8GB machines
            msg=1,      # Show CBC stdout to monitor progress in Celery logs
            options=['heur=on', 'cuts=on'] # Force heuristics to find an early feasible solution
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
        for key, var in X.items():
            if var.varValue is not None and round(var.varValue) == 1:
                tid, sid, rid, cid, day, slot_idx = key
                subject = subject_map[sid]
                assignments.append(
                    Assignment(
                        teacher_id=tid,
                        subject_id=sid,
                        room_id=rid,
                        timeslot_id=f"{day}_{slot_idx}",
                        campus_id=cid,
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
