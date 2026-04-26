from __future__ import annotations

import time as _time
import logging
from collections import defaultdict

from ortools.sat.python import cp_model

from src.domain.entities.schedule import Assignment
from src.domain.entities.teacher import TeacherType
from src.domain.exceptions import SolverError
from src.domain.ports.i_solver import ISolver, SchedulingProblem, ScheduleResult

logger = logging.getLogger(__name__)


class OrToolsCPSolver(ISolver):
    """
    Constraint Programming solver using Google OR-Tools CP-SAT.
    Orders of magnitude faster than MILP for Timetabling problems.
    """

    def solve(self, problem: SchedulingProblem) -> ScheduleResult:
        t_start = _time.perf_counter()

        model = cp_model.CpModel()

        teachers = problem.teachers
        subjects = problem.subjects
        rooms = problem.rooms
        timeslots = problem.timeslots
        weights = problem.penalty_weights

        subject_map = {s.id: s for s in subjects}
        teacher_map = {t.id: t for t in teachers}
        room_map = {r.id: r for r in rooms}

        days = sorted(list({ts.day for ts in timeslots}))
        procom_teachers = [t for t in teachers if t.teacher_type == TeacherType.PROCOM]

        # X[(t_id, s_id, r_id, day, slot)] -> Boolean Variable
        X = {}
        
        # Aggregation tools
        vars_by_subject = defaultdict(list)
        vars_by_teacher_slot = defaultdict(list)
        vars_by_room_slot = defaultdict(list)
        vars_by_teacher_day = defaultdict(list)
        vars_by_teacher_campus_day_slot = defaultdict(list)
        vars_by_teacher_campus_day = defaultdict(list)
        vars_by_subject_day = defaultdict(list)

        logger.info("Building CP-SAT Model...")

        for subject in subjects:
            valid_teachers = [t for t in teachers if t.id in subject.eligible_teacher_ids]
            valid_rooms = [r for r in rooms if r.campus_id == subject.campus_id and r.can_fit(subject.student_count)]
            
            for teacher in valid_teachers:
                for ts in timeslots:
                    if teacher.availability.slots and teacher.is_restricted(ts.day, ts.slot_index):
                        continue
                    if teacher.teacher_type == TeacherType.PROJEX and not ts.is_extended_hours:
                        continue
                    
                    for room in valid_rooms:
                        # Boolean variable for this exact assignment
                        var = model.NewBoolVar(f"X_{teacher.id}_{subject.id}_{room.id}_{ts.day}_{ts.slot_index}")
                        key = (teacher.id, subject.id, room.id, ts.day, ts.slot_index)
                        X[key] = var
                        
                        vars_by_subject[subject.id].append(var)
                        vars_by_teacher_slot[(teacher.id, ts.day, ts.slot_index)].append(var)
                        vars_by_room_slot[(room.id, ts.day, ts.slot_index)].append(var)
                        vars_by_teacher_day[(teacher.id, ts.day)].append(var)
                        vars_by_teacher_campus_day_slot[(teacher.id, subject.campus_id, ts.day, ts.slot_index)].append(var)
                        vars_by_teacher_campus_day[(teacher.id, subject.campus_id, ts.day)].append(var)
                        vars_by_subject_day[(subject.id, ts.day)].append(var)

        # ── HARD CONSTRAINTS ─────────────────────────────────────────────────

        # R6: Exactly required_sessions per subject
        for subject in subjects:
            if vars_by_subject[subject.id]:
                model.Add(sum(vars_by_subject[subject.id]) == subject.required_sessions)
            elif subject.required_sessions > 0:
                # Subject cannot be scheduled (no valid teachers/rooms)
                model.AddBoolOr([]) # Force infeasible

        # R4: Teacher cannot be in two places at once
        for var_list in vars_by_teacher_slot.values():
            if len(var_list) > 1:
                model.AddAtMostOne(var_list)

        # R7: Room cannot host two classes at once
        for var_list in vars_by_room_slot.values():
            if len(var_list) > 1:
                model.AddAtMostOne(var_list)

        # R5: Teacher daily hour limit
        for (tid, day), var_list in vars_by_teacher_day.items():
            if var_list:
                model.Add(sum(var_list) <= teacher_map[tid].max_hours_per_day)

        # R10: PROCOM teacher travel (cannot teach in C1 at t, and C2 at t+1)
        slots_by_day = defaultdict(list)
        for ts in timeslots:
            slots_by_day[ts.day].append(ts.slot_index)
        for day in slots_by_day:
            slots_by_day[day].sort()

        for teacher in procom_teachers:
            if len(teacher.campus_ids) < 2: continue
            for day in days:
                day_slots = slots_by_day.get(day, [])
                for i in range(len(day_slots) - 1):
                    t_now = day_slots[i]
                    t_next = day_slots[i+1]
                    c1, c2 = teacher.campus_ids[0], teacher.campus_ids[1]
                    
                    v_c1_now = vars_by_teacher_campus_day_slot.get((teacher.id, c1, day, t_now), [])
                    v_c2_next = vars_by_teacher_campus_day_slot.get((teacher.id, c2, day, t_next), [])
                    if v_c1_now and v_c2_next:
                        # (A => Not B) is equivalent to A + B <= 1
                        for a in v_c1_now:
                            for b in v_c2_next:
                                model.AddImplication(a, b.Not())
                                
                    v_c2_now = vars_by_teacher_campus_day_slot.get((teacher.id, c2, day, t_now), [])
                    v_c1_next = vars_by_teacher_campus_day_slot.get((teacher.id, c1, day, t_next), [])
                    if v_c2_now and v_c1_next:
                        for a in v_c2_now:
                            for b in v_c1_next:
                                model.AddImplication(a, b.Not())

        # R13: PROHES exactly 1/2 ntpphes distinct days
        for teacher in teachers:
            if teacher.teacher_type != TeacherType.PROHES:
                continue
            target_days = max(1, teacher.ntpphes // 2)
            for campus_id in teacher.campus_ids:
                days_assigned = []
                for day in days:
                    daily_vars = vars_by_teacher_campus_day.get((teacher.id, campus_id, day), [])
                    day_is_active = model.NewBoolVar(f"PROHES_day_{teacher.id}_{campus_id}_{day}")
                    if daily_vars:
                        # day_is_active is True if sum(daily_vars) > 0
                        model.Add(sum(daily_vars) > 0).OnlyEnforceIf(day_is_active)
                        model.Add(sum(daily_vars) == 0).OnlyEnforceIf(day_is_active.Not())
                    else:
                        model.Add(day_is_active == 0)
                    days_assigned.append(day_is_active)
                model.Add(sum(days_assigned) == target_days)

        # ── OBJECTIVE ────────────────────────────────────────────────────────
        # For CP, we want to maximize preferences or minimize penalties.
        # In this scale, finding ANY feasible solution is priority #1.
        # We will add simple soft constraints.
        
        penalty_terms = []

        # Gap Penalty (approximated): penalize if a subject is only scheduled once per day
        for subject in subjects:
            for day in days:
                day_vars = vars_by_subject_day.get((subject.id, day), [])
                if len(day_vars) > 1:
                    is_gap = model.NewBoolVar(f"Gap_{subject.id}_{day}")
                    model.Add(sum(day_vars) == 1).OnlyEnforceIf(is_gap)
                    model.Add(sum(day_vars) != 1).OnlyEnforceIf(is_gap.Not())
                    penalty_terms.append(is_gap * int(weights.penalizacion2))

        # Travel Penalty: PROCOM teaching in a campus
        for teacher in procom_teachers:
            for cid in teacher.campus_ids:
                for ts in timeslots:
                    slot_vars = vars_by_teacher_campus_day_slot.get((teacher.id, cid, ts.day, ts.slot_index), [])
                    if slot_vars:
                        is_active = model.NewBoolVar(f"Trv_{teacher.id}_{cid}_{ts.day}_{ts.slot_index}")
                        model.Add(sum(slot_vars) > 0).OnlyEnforceIf(is_active)
                        model.Add(sum(slot_vars) == 0).OnlyEnforceIf(is_active.Not())
                        penalty_terms.append(is_active * int(weights.penalizacion1))

        if penalty_terms:
            model.Minimize(sum(penalty_terms))

        # ── SOLVE ────────────────────────────────────────────────────────────
        logger.info("CP-SAT Model built. Solving with aggressive configuration...")
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = problem.time_limit_seconds
        
        # Maximize CPU usage for speed
        solver.parameters.num_search_workers = 8  # Use all Mac cores
        
        # Aggressive heuristic settings for instant feasibility
        solver.parameters.cp_model_presolve = True
        solver.parameters.relative_gap_limit = 0.20  # Accept 20% gap like we did in CBC
        solver.parameters.log_search_progress = True
        
        status = solver.Solve(model)
        
        solve_time = _time.perf_counter() - t_start
        status_name = solver.StatusName(status)
        logger.info("CP-SAT finished: status=%s time=%.2fs", status_name, solve_time)

        if status == cp_model.INFEASIBLE:
            return ScheduleResult(
                assignments=[],
                penalty_score=0.0,
                solver_status="Infeasible",
                solve_time_seconds=solve_time,
                solver_name="OR-Tools CP-SAT",
            )

        # ── EXTRACT ──────────────────────────────────────────────────────────
        assignments = []
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for key, var in X.items():
                if solver.Value(var):
                    tid, sid, rid, day, slot_idx = key
                    subject = subject_map[sid]
                    assignments.append(
                        Assignment(
                            teacher_id=tid,
                            subject_id=sid,
                            room_id=rid,
                            timeslot_id=f"{day}_{slot_idx}",
                            campus_id=subject.campus_id,
                            group_id=subject.group_id,
                        )
                    )

        return ScheduleResult(
            assignments=assignments,
            penalty_score=solver.ObjectiveValue() if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else 0.0,
            solver_status=status_name,
            solve_time_seconds=solve_time,
            solver_name="OR-Tools CP-SAT",
        )
