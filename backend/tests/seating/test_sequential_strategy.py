"""Pure tests for SequentialSeatingStrategy — no DB, no HTTP. All data
synthetic.
"""

from datetime import date

import pytest

from app.domain import Exam, GenerationStatus, Student
from app.seating.models import RoomAllocation
from app.seating.strategies.sequential import SequentialSeatingStrategy

EXAM = Exam(
    id=1,
    course_id=1,
    exam_date=date(2024, 5, 30),
    time_slot="10:00-12:00",
    expected_student_count=80,
    day_label="Thursday",
)


def _students(count: int) -> list[Student]:
    return [Student(id=i, student_number=str(1000 + i), full_name=f"Student {i}") for i in range(1, count + 1)]


def test_basic_two_room_fifo_fill_matches_spec_example() -> None:
    strategy = SequentialSeatingStrategy()
    students = _students(80)
    room_allocations = [
        RoomAllocation(room_id=10, room_code="A", allocated_students=40, capacity=50),
        RoomAllocation(room_id=20, room_code="B", allocated_students=40, capacity=50),
    ]

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.status == GenerationStatus.SUCCESS
    assert result.registered_student_count == 80
    assert result.scheduled_student_count == 80
    assert result.available_capacity == 80
    assert result.assigned_student_count == 80
    assert result.unassigned_student_count == 0
    assert result.capacity_shortage is False

    room_a_assignments = [a for a in result.assignments if a.room_id == 10]
    room_b_assignments = [a for a in result.assignments if a.room_id == 20]
    assert len(room_a_assignments) == 40
    assert len(room_b_assignments) == 40
    # First 40 students (in given order) go to room A, next 40 to room B.
    assert {a.student_id for a in room_a_assignments} == {s.id for s in students[:40]}
    assert {a.student_id for a in room_b_assignments} == {s.id for s in students[40:]}
    # Seat numbers are a per-room ordinal starting at 1.
    assert sorted(a.seat_number for a in room_a_assignments) == list(range(1, 41))
    assert sorted(a.seat_number for a in room_b_assignments) == list(range(1, 41))


def test_registered_more_than_scheduled_leaves_students_unassigned() -> None:
    """Mismatch A: 100 registered, 80 scheduled -> 20 unassigned, never
    silently assigned beyond the schedule."""
    strategy = SequentialSeatingStrategy()
    students = _students(100)
    room_allocations = [RoomAllocation(room_id=10, room_code="A", allocated_students=80, capacity=100)]

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.status == GenerationStatus.PARTIAL
    assert result.assigned_student_count == 80
    assert result.unassigned_student_count == 20
    assert result.capacity_shortage is True
    assert len(result.unassigned_student_ids) == 20
    assert result.unassigned_student_ids == [s.id for s in students[80:]]
    assert any("registered" in w.lower() for w in result.warnings)


def test_registered_fewer_than_scheduled_leaves_capacity_unused() -> None:
    """Mismatch B: 60 registered, 80 scheduled -> assign only 60, no fake
    students, remaining scheduled seats simply unused."""
    strategy = SequentialSeatingStrategy()
    students = _students(60)
    room_allocations = [RoomAllocation(room_id=10, room_code="A", allocated_students=80, capacity=100)]

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.status == GenerationStatus.SUCCESS
    assert result.assigned_student_count == 60
    assert result.unassigned_student_count == 0
    assert result.capacity_shortage is False
    assert len(result.assignments) == 60
    assert any("unused" in w.lower() for w in result.warnings)


def test_allocation_exceeding_room_capacity_is_capped_not_overwritten_to_capacity_silently() -> None:
    """Mismatch C variant: a room's allocation exceeds its own physical
    capacity. The strategy must not seat more than `capacity` in that
    room, but if a later room can absorb the overflow, no one need go
    unassigned overall."""
    strategy = SequentialSeatingStrategy()
    students = _students(90)
    room_allocations = [
        RoomAllocation(room_id=10, room_code="A", allocated_students=50, capacity=40),  # over-allocated
        RoomAllocation(room_id=20, room_code="B", allocated_students=50, capacity=50),
    ]

    result = strategy.generate(EXAM, students, room_allocations)

    room_a_assignments = [a for a in result.assignments if a.room_id == 10]
    assert len(room_a_assignments) == 40  # never more than capacity
    assert max(a.seat_number for a in room_a_assignments) == 40
    # The 10 students who would have overflowed room A are seated in room B instead.
    assert result.unassigned_student_count == 0
    assert result.status == GenerationStatus.SUCCESS
    assert any("exceeds its" in w for w in result.warnings)


def test_true_physical_capacity_shortage_leaves_students_unassigned() -> None:
    """Mismatch C, no room to absorb overflow: total physical capacity is
    genuinely insufficient for everyone registered."""
    strategy = SequentialSeatingStrategy()
    students = _students(50)
    room_allocations = [RoomAllocation(room_id=10, room_code="A", allocated_students=50, capacity=30)]

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.available_capacity == 30
    assert result.assigned_student_count == 30
    assert result.unassigned_student_count == 20
    assert result.capacity_shortage is True
    assert result.status == GenerationStatus.PARTIAL


def test_no_rooms_scheduled_with_registered_students_fails() -> None:
    strategy = SequentialSeatingStrategy()
    students = _students(10)

    result = strategy.generate(EXAM, students, [])

    assert result.status == GenerationStatus.FAILED
    assert result.assigned_student_count == 0
    assert result.unassigned_student_count == 10
    assert result.capacity_shortage is True


def test_zero_registered_students_is_success_with_no_assignments() -> None:
    strategy = SequentialSeatingStrategy()
    room_allocations = [RoomAllocation(room_id=10, room_code="A", allocated_students=40, capacity=50)]

    result = strategy.generate(EXAM, [], room_allocations)

    assert result.status == GenerationStatus.SUCCESS
    assert result.assigned_student_count == 0
    assert result.unassigned_student_count == 0
    assert result.capacity_shortage is False


def test_duplicate_room_allocation_raises() -> None:
    strategy = SequentialSeatingStrategy()
    students = _students(5)
    room_allocations = [
        RoomAllocation(room_id=10, room_code="A", allocated_students=5, capacity=10),
        RoomAllocation(room_id=10, room_code="A", allocated_students=5, capacity=10),
    ]

    with pytest.raises(ValueError, match="Duplicate"):
        strategy.generate(EXAM, students, room_allocations)


def test_generation_never_mutates_the_input_student_list() -> None:
    strategy = SequentialSeatingStrategy()
    students = _students(10)
    original = list(students)
    room_allocations = [RoomAllocation(room_id=10, room_code="A", allocated_students=5, capacity=10)]

    strategy.generate(EXAM, students, room_allocations)

    assert students == original


def test_result_is_deterministic_across_repeated_runs() -> None:
    strategy = SequentialSeatingStrategy()
    students = _students(37)
    room_allocations = [
        RoomAllocation(room_id=10, room_code="A", allocated_students=20, capacity=20),
        RoomAllocation(room_id=20, room_code="B", allocated_students=20, capacity=20),
    ]

    first = strategy.generate(EXAM, students, room_allocations)
    second = strategy.generate(EXAM, students, room_allocations)

    assert first.assignments == second.assignments
    assert first.unassigned_student_ids == second.unassigned_student_ids
