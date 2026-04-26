from __future__ import annotations

import collections
import logging
import time as _time

from ortools.sat.python import cp_model

from src.domain.entities.schedule import Assignment
from src.domain.entities.teacher import TeacherType
from src.domain.exceptions import SolverError
from src.domain.ports.i_solver import ISolver, SchedulingProblem, ScheduleResult

logger = logging.getLogger(__name__)


class OrToolsCPSolver(ISolver):
    """
    Production-ready ISolver implementation using Google OR-Tools CP-SAT.
    Replaces the PuLP/CBC implementation to resolve combinatorial explosions by:
    1. Using logical pruning to only instantiate valid Boolean variables.
    2. Exploiting the multithreaded architecture of CP-SAT.
    3. Correctly modeling constraints using integer/boolean math rather than
       heavy linear expressions.
    """

    def solve(self, problem: SchedulingProblem) -> ScheduleResult:
        t_start = _time.perf_counter()

        try:
            result = self._build_and_solve(problem)
        except Exception as exc:
            raise SolverError(f"ORTools solver failed unexpectedly: {exc}") from exc

        elapsed = _time.perf_counter() - t_start
        result.solve_time_seconds = elapsed
        return result

    def _build_and_solve(self, problem: SchedulingProblem) -> ScheduleResult:
        model = cp_model.CpModel()

        # Variable grouping maps (O(1) lookups for constraint building)
        by_subject = collections.defaultdict(list)
        by_teacher_slot = collections.defaultdict(list)
        by_room_slot = collections.defaultdict(list)
        by_teacher_day = collections.defaultdict(list)
        by_teacher_day_campus = collections.defaultdict(list)
        by_subject_day = collections.defaultdict(list)

        var_to_assignment = {}
        
        # We need slot indices per day to enforce contiguous constraints (R10)
        slots_by_day = collections.defaultdict(list)
        for ts in problem.timeslots:
            if ts.slot_index not in slots_by_day[ts.day]:
                slots_by_day[ts.day].append(ts.slot_index)
        for day in slots_by_day:
            slots_by_day[day].sort()

        # Pre-groupings to avoid O(T*S*R*TS) loop explosion and OOM
        teachers_by_campus = collections.defaultdict(list)
        for t in problem.teachers:
            for cid in t.campus_ids:
                teachers_by_campus[cid].append(t)
                
        rooms_by_campus = collections.defaultdict(list)
        for r in problem.rooms:
            rooms_by_campus[r.campus_id].append(r)

        # ── 1. Logical Filtering & Variable Generation ──────────────────────────
        for s in problem.subjects:
            valid_rooms = [r for r in rooms_by_campus.get(s.campus_id, []) if r.can_fit(s.student_count)]
            if not valid_rooms:
                continue
                
            # Filter valid teachers: Must belong to campus, and if eligible_teacher_ids is set, must be in it.
            campus_teachers = teachers_by_campus.get(s.campus_id, [])
            if s.eligible_teacher_ids:
                valid_teachers = [t for t in campus_teachers if t.id in s.eligible_teacher_ids]
            else:
                valid_teachers = campus_teachers

            for t in valid_teachers:
                for ts in problem.timeslots:
                    if t.is_restricted(ts.day, ts.slot_index):
                        continue
                    if t.teacher_type == TeacherType.PROJEX and not ts.is_extended_hours:
                        continue

                    for r in valid_rooms:
                        # Create the binary decision variable
                        name = f"x_{t.id}_{s.id}_{r.id}_{ts.day}_{ts.slot_index}"
                        var = model.NewBoolVar(name)

                        by_subject[s.id].append(var)
                        by_teacher_slot[(t.id, ts.day, ts.slot_index)].append(var)
                        by_room_slot[(r.id, ts.day, ts.slot_index)].append(var)
                        by_teacher_day[(t.id, ts.day)].append(var)
                        by_teacher_day_campus[(t.id, ts.day, r.campus_id)].append(var)
                        by_subject_day[(s.id, ts.day)].append(var)

                        var_to_assignment[var] = (
                            t.id,
                            s.id,
                            r.id,
                            f"{ts.day}_{ts.slot_index}",
                            s.campus_id,
                            s.group_id,
                        )

        # ── 2. Hard Constraints ───────────────────────────────────────────────

        # R6 — Intensity (Exact required sessions)
        for s in problem.subjects:
            model.Add(sum(by_subject[s.id]) == s.required_sessions)

        # R4 — No teacher double-booking per slot
        for vars_list in by_teacher_slot.values():
            if len(vars_list) > 1:
                model.AddAtMostOne(vars_list)

        # R7 — No room double-booking per slot
        for vars_list in by_room_slot.values():
            if len(vars_list) > 1:
                model.AddAtMostOne(vars_list)

        # R5 — Daily hour limit per teacher
        for t in problem.teachers:
            for day in range(6):
                day_vars = by_teacher_day.get((t.id, day), [])
                if day_vars:
                    model.Add(sum(day_vars) <= t.max_hours_per_day)

        # R10 — PROCOM travel time (cannot teach across campuses in contiguous slots)
        for t in problem.teachers:
            if t.teacher_type == TeacherType.PROCOM and len(t.campus_ids) >= 2:
                for day in range(6):
                    day_slots = slots_by_day.get(day, [])
                    for i in range(len(day_slots) - 1):
                        slot_t = day_slots[i]
                        slot_t1 = day_slots[i + 1]
                        
                        # Only consider actually contiguous slot indices
                        if slot_t1 != slot_t + 1:
                            continue

                        # Generate constraints for all pairs of DIFFERENT campuses
                        for c_a in t.campus_ids:
                            for c_b in t.campus_ids:
                                if c_a != c_b:
                                    # Use by_teacher_slot dictionary and filter by campus manually
                                    vars_a = [v for v in by_teacher_slot.get((t.id, day, slot_t), []) 
                                              if var_to_assignment[v].campus_id == c_a]
                                    vars_b = [v for v in by_teacher_slot.get((t.id, day, slot_t1), []) 
                                              if var_to_assignment[v].campus_id == c_b]
                                    
                                    if vars_a and vars_b:
                                        model.Add(sum(vars_a) + sum(vars_b) <= 1)

        # R13 — PROHES assigned exactly ½ × ntpphes distinct days per campus
        for t in problem.teachers:
            if t.teacher_type == TeacherType.PROHES:
                target_days = max(1, t.ntpphes // 2)
                for campus_id in t.campus_ids:
                    day_indicators = []
                    for day in range(6):
                        daily_campus_vars = by_teacher_day_campus.get((t.id, day, campus_id), [])
                        teaches_on_day = model.NewBoolVar(f"prohes_t{t.id}_c{campus_id}_d{day}")
                        
                        if daily_campus_vars:
                            model.AddMaxEquality(teaches_on_day, daily_campus_vars)
                        else:
                            model.Add(teaches_on_day == 0)
                            
                        day_indicators.append(teaches_on_day)
                    
                    model.Add(sum(day_indicators) == target_days)

        # ── 3. Soft Constraints & Objective ───────────────────────────────────
        penalties = []
        
        # Use a scaling factor since penalties are floats, CP-SAT requires ints
        SCALE = 100
        weight_gap = int(problem.penalty_weights.penalizacion2 * SCALE)
        weight_transfer = int(problem.penalty_weights.penalizacion1 * SCALE)

        # Subject gaps: Active if a subject has exactly 1 session on a particular day
        for s in problem.subjects:
            for day in range(6):
                day_vars = by_subject_day.get((s.id, day), [])
                if day_vars:
                    sessions = sum(day_vars)
                    is_gap = model.NewBoolVar(f"gap_s{s.id}_d{day}")
                    
                    model.Add(sessions == 1).OnlyEnforceIf(is_gap)
                    model.Add(sessions != 1).OnlyEnforceIf(is_gap.Not())
                    
                    penalties.append(is_gap * weight_gap)

        # PROCOM transfers: Penalize teaching in >1 campus on the same day
        for t in problem.teachers:
            if t.teacher_type == TeacherType.PROCOM:
                for day in range(6):
                    campus_indicators = []
                    for campus_id in t.campus_ids:
                        daily_campus_vars = by_teacher_day_campus.get((t.id, day, campus_id), [])
                        if daily_campus_vars:
                            teaches_in_c = model.NewBoolVar(f"trans_t{t.id}_c{campus_id}_d{day}")
                            model.AddMaxEquality(teaches_in_c, daily_campus_vars)
                            campus_indicators.append(teaches_in_c)
                    
                    if len(campus_indicators) > 1:
                        transfers = model.NewIntVar(0, len(campus_indicators) - 1, f"transfers_t{t.id}_d{day}")
                        model.Add(transfers >= sum(campus_indicators) - 1)
                        penalties.append(transfers * weight_transfer)

        if penalties:
            model.Minimize(sum(penalties))

        # ── 4. Solve ──────────────────────────────────────────────────────────
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = problem.time_limit_seconds
        solver.parameters.num_search_workers = 1  # 1 worker to survive 8GB RAM
        solver.parameters.log_search_progress = True
        
        logger.info("Starting CP-SAT solver. Time limit: %ds", problem.time_limit_seconds)
        logger.info("Model size: %d variables, %d constraints", len(model.Proto().variables), len(model.Proto().constraints))
        status = solver.Solve(model)
        
        status_name = solver.StatusName(status)
        logger.info("CP-SAT finished: status=%s", status_name)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            assignments = []
            for var, data in var_to_assignment.items():
                if solver.Value(var) == 1:
                    assignments.append(
                        Assignment(
                            teacher_id=data[0],
                            subject_id=data[1],
                            room_id=data[2],
                            timeslot_id=data[3],
                            campus_id=data[4],
                            group_id=data[5],
                        )
                    )
                    
            penalty_score = solver.ObjectiveValue() / SCALE if penalties else 0.0
            
            return ScheduleResult(
                assignments=assignments,
                penalty_score=penalty_score,
                solver_status=status_name.capitalize(),
                solve_time_seconds=0.0,  # Filled by caller
                solver_name="OR-Tools CP-SAT",
            )
        elif status == cp_model.INFEASIBLE:
            return ScheduleResult(
                assignments=[],
                penalty_score=0.0,
                solver_status="Infeasible",
                solve_time_seconds=0.0,
                solver_name="OR-Tools CP-SAT",
            )
        else:
            return ScheduleResult(
                assignments=[],
                penalty_score=0.0,
                solver_status=status_name.capitalize(),
                solve_time_seconds=0.0,
                solver_name="OR-Tools CP-SAT",
            )
