from __future__ import annotations

import pytest
from datetime import time

from src.domain.entities.teacher import Teacher, TeacherAvailability, TeacherType, DomainError
from src.domain.entities.subject import Subject
from src.domain.entities.room import Room
from src.domain.entities.timeslot import Timeslot
from src.domain.value_objects.penalty_weights import PenaltyWeights


class TestTeacherInvariants:
    def test_valid_regular_teacher(self) -> None:
        t = Teacher(
            id="T1", name="Docente A", teacher_type=TeacherType.REGULAR,
            campus_ids=["C1"], availability=TeacherAvailability(),
        )
        assert t.id == "T1"

    def test_procom_requires_two_campuses(self) -> None:
        with pytest.raises(DomainError, match="PROCOM"):
            Teacher(
                id="T2", name="PROCOM Teacher", teacher_type=TeacherType.PROCOM,
                campus_ids=["C1"], availability=TeacherAvailability(),
            )

    def test_prohes_requires_ntpphes(self) -> None:
        with pytest.raises(DomainError, match="PROHES"):
            Teacher(
                id="T3", name="PROHES Teacher", teacher_type=TeacherType.PROHES,
                campus_ids=["C1"], availability=TeacherAvailability(), ntpphes=0,
            )

    def test_max_hours_bounds(self) -> None:
        with pytest.raises(DomainError, match="max_hours_per_day"):
            Teacher(
                id="T4", name="Bad Teacher", teacher_type=TeacherType.REGULAR,
                campus_ids=["C1"], availability=TeacherAvailability(), max_hours_per_day=13,
            )

    def test_availability_restriction(self) -> None:
        avail = TeacherAvailability(slots=frozenset([(0, 1), (0, 2)]))
        t = Teacher(
            id="T5", name="Available Teacher", teacher_type=TeacherType.REGULAR,
            campus_ids=["C1"], availability=avail,
        )
        assert not t.is_restricted(0, 1)
        assert t.is_restricted(0, 3)


class TestTimeslotInvariants:
    def test_valid_weekday_slot(self) -> None:
        ts = Timeslot(day=0, slot_index=1, start_time=time(7, 0), end_time=time(9, 0))
        assert ts.day_name == "Monday"
        assert not ts.is_extended_hours

    def test_extended_hours_detection(self) -> None:
        ts = Timeslot(day=1, slot_index=5, start_time=time(18, 0), end_time=time(20, 0))
        assert ts.is_extended_hours

    def test_lunch_block_raises(self) -> None:
        with pytest.raises(DomainError, match="lunch block"):
            Timeslot(day=0, slot_index=3, start_time=time(12, 0), end_time=time(13, 0))

    def test_saturday_window_enforced(self) -> None:
        with pytest.raises(DomainError, match="Saturday"):
            Timeslot(day=5, slot_index=6, start_time=time(13, 0), end_time=time(15, 0))

    def test_start_before_end(self) -> None:
        with pytest.raises(DomainError):
            Timeslot(day=0, slot_index=0, start_time=time(10, 0), end_time=time(9, 0))


class TestPenaltyWeightsInvariants:
    def test_defaults(self) -> None:
        pw = PenaltyWeights()
        assert pw.penalizacion1 == 2.0
        assert pw.penalizacion2 == 1.0

    def test_negative_raises(self) -> None:
        with pytest.raises(DomainError):
            PenaltyWeights(penalizacion1=-1.0)

    def test_custom_values(self) -> None:
        pw = PenaltyWeights(penalizacion1=5.0, penalizacion2=3.0)
        assert pw.penalizacion1 == 5.0


class TestRoomInvariants:
    def test_valid_room(self) -> None:
        r = Room(id="R1", name="Aula 101", campus_id="C1", capacity=40)
        assert r.can_fit(30)
        assert not r.can_fit(41)

    def test_zero_capacity_raises(self) -> None:
        with pytest.raises(DomainError):
            Room(id="R2", name="Empty", campus_id="C1", capacity=0)
