"""Pure tests for SequentialSeatingStrategy — no DB, no HTTP. All data
synthetic.
"""

from datetime import date

import pytest

from app.domain import Exam, GenerationStatus, Student
from app.seating.models import RoomAllocation
from app.seating.strategies.sequential import SequentialSeatingStrategy
from app.seating.topology import RectangularRoomTopology
from app.seating.topology_provider import RoomTopologyProvider

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


class _FixedTopologyProvider(RoomTopologyProvider):
    """Minimal test double: returns one pre-built topology per room_id,
    regardless of the room_code/capacity it's asked with. Only used by
    the Milestone 10 blocked-seat tests below — every other test in this
    file constructs SequentialSeatingStrategy() with no topology_provider
    at all, exercising sequential's original, unchanged "no topology
    needed" fallback path."""

    def __init__(self, topologies_by_room_id: dict[int, RectangularRoomTopology]) -> None:
        self._topologies = topologies_by_room_id

    def get_topology(self, room_id: int, room_code: str, capacity: int):
        return self._topologies[room_id]


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


# --- Precise shortage semantics: scheduled_allocation_shortage vs. --------
# --- physical_capacity_shortage must be independently correct, not --------
# --- just "some students ended up unassigned" (that's capacity_shortage). -


def test_scheduled_allocation_shortage_without_physical_capacity_shortage() -> None:
    """registered > scheduled allocation, but physical capacity would have
    been sufficient — the schedule under-allocated, the rooms themselves
    did not run out of physical space."""
    strategy = SequentialSeatingStrategy()
    students = _students(100)
    room_allocations = [RoomAllocation(room_id=10, room_code="A", allocated_students=80, capacity=120)]

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.scheduled_student_count == 80
    assert result.total_physical_capacity == 120
    assert result.scheduled_allocation_shortage is True
    assert result.physical_capacity_shortage is False
    # Still true that someone actually went unassigned this generation —
    # a distinct, broader fact from *why*.
    assert result.capacity_shortage is True
    assert result.unassigned_student_count == 20


def test_physical_capacity_shortage_without_scheduled_allocation_shortage() -> None:
    """registered <= scheduled allocation, but the rooms physically
    assigned cannot hold that many seats regardless of what was scheduled."""
    strategy = SequentialSeatingStrategy()
    students = _students(100)
    room_allocations = [RoomAllocation(room_id=10, room_code="A", allocated_students=120, capacity=80)]

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.scheduled_student_count == 120
    assert result.total_physical_capacity == 80
    assert result.scheduled_allocation_shortage is False
    assert result.physical_capacity_shortage is True
    assert result.capacity_shortage is True
    assert result.unassigned_student_count == 20


def test_both_shortages_simultaneously() -> None:
    """registered exceeds both the scheduled allocation and the rooms'
    total physical capacity — both flags must be true independently."""
    strategy = SequentialSeatingStrategy()
    students = _students(150)
    room_allocations = [RoomAllocation(room_id=10, room_code="A", allocated_students=80, capacity=100)]

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.scheduled_allocation_shortage is True
    assert result.physical_capacity_shortage is True
    assert result.capacity_shortage is True
    # The algorithm only ever fills up to the capped, scheduled amount —
    # physical capacity (100) here is not even the binding constraint.
    assert result.assigned_student_count == 80
    assert result.unassigned_student_count == 70


def test_neither_shortage_when_registered_fits_within_both() -> None:
    """registered <= scheduled allocation and <= physical capacity: no
    shortage of either kind, and no one goes unassigned."""
    strategy = SequentialSeatingStrategy()
    students = _students(60)
    room_allocations = [RoomAllocation(room_id=10, room_code="A", allocated_students=80, capacity=100)]

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.scheduled_allocation_shortage is False
    assert result.physical_capacity_shortage is False
    assert result.capacity_shortage is False
    assert result.unassigned_student_count == 0
    assert result.status == GenerationStatus.SUCCESS


# --- Milestone 10: usable seats / blocked seats ----------------------------


def test_normal_rectangular_room_with_topology_produces_the_same_result_as_without_one() -> None:
    """A room with a configured topology but zero blocked seats must
    produce byte-identical assignments to the pre-Milestone-10,
    topology-less path — usable_capacity == physical_capacity when
    nothing is blocked, so nothing about the fill changes."""
    topology = RectangularRoomTopology(room_id=10, rows=4, columns=5)  # 20 seats, none blocked
    provider = _FixedTopologyProvider({10: topology})
    room_allocations = [RoomAllocation(room_id=10, room_code="500", allocated_students=20, capacity=20)]
    students = _students(20)

    with_topology = SequentialSeatingStrategy(topology_provider=provider).generate(EXAM, students, room_allocations)
    without_topology = SequentialSeatingStrategy().generate(EXAM, students, room_allocations)

    assert with_topology.assignments == without_topology.assignments
    assert with_topology.total_usable_capacity == with_topology.total_physical_capacity == 20


def test_blocked_seats_are_skipped_and_never_assigned() -> None:
    topology = RectangularRoomTopology(room_id=10, rows=4, columns=5, blocked_seat_numbers={7, 17})
    provider = _FixedTopologyProvider({10: topology})
    room_allocations = [RoomAllocation(room_id=10, room_code="500", allocated_students=20, capacity=20)]
    students = _students(18)

    result = SequentialSeatingStrategy(topology_provider=provider).generate(EXAM, students, room_allocations)

    assert result.total_physical_capacity == 20
    assert result.total_usable_capacity == 18
    assert result.assigned_student_count == 18
    assert result.unassigned_student_count == 0
    assigned_seat_numbers = {a.seat_number for a in result.assignments}
    assert 7 not in assigned_seat_numbers
    assert 17 not in assigned_seat_numbers
    assert assigned_seat_numbers == {1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 19, 20}


def test_insufficient_usable_seats_leaves_exact_overflow_unassigned() -> None:
    topology = RectangularRoomTopology(room_id=10, rows=4, columns=5, blocked_seat_numbers={7, 17})
    provider = _FixedTopologyProvider({10: topology})
    room_allocations = [RoomAllocation(room_id=10, room_code="500", allocated_students=20, capacity=20)]
    students = _students(20)  # 2 more than the 18 usable seats

    result = SequentialSeatingStrategy(topology_provider=provider).generate(EXAM, students, room_allocations)

    assert result.assigned_student_count == 18
    assert result.unassigned_student_count == 2
    assert result.status == GenerationStatus.PARTIAL
    # Physical capacity is unaffected by blocking — 20 registered does not
    # exceed 20 physical seats, so this must NOT be a physical shortage.
    assert result.physical_capacity_shortage is False
    assert result.usable_capacity_shortage is True
    assert result.capacity_shortage is True
    assert any("blocked seat" in w.lower() for w in result.warnings)


def test_blocked_seat_result_is_deterministic() -> None:
    topology = RectangularRoomTopology(room_id=10, rows=4, columns=5, blocked_seat_numbers={7, 17})
    provider = _FixedTopologyProvider({10: topology})
    room_allocations = [RoomAllocation(room_id=10, room_code="500", allocated_students=20, capacity=20)]
    students = _students(18)
    strategy = SequentialSeatingStrategy(topology_provider=provider)

    first = strategy.generate(EXAM, students, room_allocations)
    second = strategy.generate(EXAM, students, room_allocations)

    assert first.assignments == second.assignments


# --- Milestone 10: capacity semantics (physical vs. usable) ---------------


def test_capacity_physical_20_usable_20_registered_18() -> None:
    topology = RectangularRoomTopology(room_id=10, rows=4, columns=5)  # no blocking
    provider = _FixedTopologyProvider({10: topology})
    room_allocations = [RoomAllocation(room_id=10, room_code="500", allocated_students=20, capacity=20)]
    result = SequentialSeatingStrategy(topology_provider=provider).generate(EXAM, _students(18), room_allocations)

    assert result.total_physical_capacity == 20
    assert result.total_usable_capacity == 20
    assert result.assigned_student_count == 18
    assert result.unassigned_student_count == 0
    assert result.scheduled_allocation_shortage is False
    assert result.physical_capacity_shortage is False
    assert result.usable_capacity_shortage is False


def test_capacity_physical_20_usable_18_registered_18() -> None:
    topology = RectangularRoomTopology(room_id=10, rows=4, columns=5, blocked_seat_numbers={7, 17})
    provider = _FixedTopologyProvider({10: topology})
    room_allocations = [RoomAllocation(room_id=10, room_code="500", allocated_students=20, capacity=20)]
    result = SequentialSeatingStrategy(topology_provider=provider).generate(EXAM, _students(18), room_allocations)

    assert result.total_physical_capacity == 20
    assert result.total_usable_capacity == 18
    assert result.assigned_student_count == 18
    assert result.unassigned_student_count == 0
    assert result.scheduled_allocation_shortage is False
    assert result.physical_capacity_shortage is False
    assert result.usable_capacity_shortage is False  # exactly enough usable seats


def test_capacity_physical_20_usable_18_registered_20() -> None:
    topology = RectangularRoomTopology(room_id=10, rows=4, columns=5, blocked_seat_numbers={7, 17})
    provider = _FixedTopologyProvider({10: topology})
    room_allocations = [RoomAllocation(room_id=10, room_code="500", allocated_students=20, capacity=20)]
    result = SequentialSeatingStrategy(topology_provider=provider).generate(EXAM, _students(20), room_allocations)

    assert result.total_physical_capacity == 20
    assert result.total_usable_capacity == 18
    assert result.assigned_student_count == 18
    assert result.unassigned_student_count == 2
    assert result.scheduled_allocation_shortage is False
    assert result.physical_capacity_shortage is False  # 20 registered does not exceed 20 physical
    assert result.usable_capacity_shortage is True  # but does exceed 18 usable


def test_capacity_physical_20_usable_18_registered_21() -> None:
    topology = RectangularRoomTopology(room_id=10, rows=4, columns=5, blocked_seat_numbers={7, 17})
    provider = _FixedTopologyProvider({10: topology})
    room_allocations = [RoomAllocation(room_id=10, room_code="500", allocated_students=20, capacity=20)]
    result = SequentialSeatingStrategy(topology_provider=provider).generate(EXAM, _students(21), room_allocations)

    assert result.total_physical_capacity == 20
    assert result.total_usable_capacity == 18
    assert result.assigned_student_count == 18
    assert result.unassigned_student_count == 3
    assert result.scheduled_allocation_shortage is True  # 21 registered exceeds the scheduled 20 too
    assert result.physical_capacity_shortage is True  # 21 registered exceeds 20 physical
    assert result.usable_capacity_shortage is True  # and exceeds 18 usable too
