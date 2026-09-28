"""Pure tests for ConstraintSeatingStrategy — no DB, no HTTP. All data
synthetic. Mirrors tests/seating/test_sequential_strategy.py's style and
covers the Phase 7 spec's numbered test list (registration, determinism,
hard/soft handling, unassignment, duplicate prevention, room boundaries).
"""

from datetime import date

from app.domain import Exam, GenerationStatus, Student
from app.seating import get_strategy
from app.seating.constraints import ConstraintSet, SeparateCoursesConstraint, StudentsNotAdjacentConstraint
from app.seating.models import RoomAllocation
from app.seating.strategies.constraint import ConstraintSeatingStrategy
from app.seating.strategies.sequential import SequentialSeatingStrategy
from app.seating.topology import RectangularRoomTopology
from app.seating.topology_provider import RoomTopologyProvider, StaticRoomTopologyProvider

EXAM = Exam(
    id=1,
    course_id=1,
    exam_date=date(2024, 5, 30),
    time_slot="10:00-12:00",
    expected_student_count=10,
    day_label="Thursday",
)


def _students(count: int, start: int = 1) -> list[Student]:
    return [
        Student(id=i, student_number=str(1000 + i), full_name=f"Student {i}") for i in range(start, start + count)
    ]


def _provider(**layouts: tuple[int, int]) -> StaticRoomTopologyProvider:
    return StaticRoomTopologyProvider(layouts)


class _FixedTopologyProvider(RoomTopologyProvider):
    """Minimal test double for the Milestone 10 blocked-seat tests below —
    StaticRoomTopologyProvider has no way to configure blocked seats, so
    these tests build a RectangularRoomTopology directly instead."""

    def __init__(self, topologies_by_room_id: dict[int, RectangularRoomTopology]) -> None:
        self._topologies = topologies_by_room_id

    def get_topology(self, room_id: int, room_code: str, capacity: int):
        return self._topologies[room_id]


# --- Test 1: strategy registration -----------------------------------


def test_constraint_strategy_is_registered_and_resolvable_by_name() -> None:
    strategy = get_strategy("constraint")
    assert isinstance(strategy, ConstraintSeatingStrategy)
    assert strategy.name == "constraint"


def test_sequential_strategy_registration_is_unaffected() -> None:
    strategy = get_strategy("sequential")
    assert isinstance(strategy, SequentialSeatingStrategy)
    assert strategy.name == "sequential"


# --- Test 2: deterministic output -------------------------------------


def test_result_is_deterministic_across_repeated_runs() -> None:
    provider = _provider(A=(2, 5))
    strategy = ConstraintSeatingStrategy(topology_provider=provider, constraint_set=ConstraintSet())
    students = _students(10)
    room_allocations = [RoomAllocation(room_id=1, room_code="A", allocated_students=10, capacity=10)]

    first = strategy.generate(EXAM, students, room_allocations)
    second = strategy.generate(EXAM, students, room_allocations)

    assert first.assignments == second.assignments
    assert first.unassigned_student_ids == second.unassigned_student_ids


def test_matches_sequential_strategy_when_there_are_no_constraints() -> None:
    """With an empty ConstraintSet, every candidate seat always has zero
    violations, so the first candidate in room-then-seat order always
    wins — which is exactly SequentialSeatingStrategy's own fill order."""
    provider = _provider(A=(4, 10), B=(4, 10))
    room_allocations = [
        RoomAllocation(room_id=1, room_code="A", allocated_students=40, capacity=40),
        RoomAllocation(room_id=2, room_code="B", allocated_students=40, capacity=40),
    ]
    students = _students(80)

    constraint_result = ConstraintSeatingStrategy(
        topology_provider=provider, constraint_set=ConstraintSet()
    ).generate(EXAM, students, room_allocations)
    sequential_result = SequentialSeatingStrategy().generate(EXAM, students, room_allocations)

    assert constraint_result.assignments == sequential_result.assignments
    assert constraint_result.status == sequential_result.status
    assert constraint_result.assigned_student_count == sequential_result.assigned_student_count
    assert constraint_result.unassigned_student_count == sequential_result.unassigned_student_count


# --- Test 3: hard constraint -------------------------------------------


def test_hard_constraint_prevents_adjacent_placement_when_an_alternative_exists() -> None:
    provider = _provider(A=(2, 5))
    room_allocations = [RoomAllocation(room_id=1, room_code="A", allocated_students=10, capacity=10)]
    students = _students(2)  # ids 1, 2
    topology = provider.get_topology(room_id=1, room_code="A", capacity=10)
    not_adjacent = StudentsNotAdjacentConstraint(student_a_id=1, student_b_id=2, topologies={1: topology})
    strategy = ConstraintSeatingStrategy(
        topology_provider=provider,
        constraint_set=ConstraintSet(hard_constraints=(not_adjacent,)),
    )

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.status == GenerationStatus.SUCCESS
    assert result.assigned_student_count == 2
    seat_by_student = {a.student_id: a.seat_number for a in result.assignments}
    assert abs(seat_by_student[1] - seat_by_student[2]) > 1  # not seat-adjacent (seat 1 vs seat 2)


def test_hard_constraint_is_never_violated_even_when_it_costs_an_unassigned_student() -> None:
    """Only two seats exist, and they are adjacent — the hard constraint
    makes it impossible to seat both students, so one must go unassigned
    rather than the constraint being violated."""
    provider = _provider(A=(1, 2))  # 1x2: seat 1 and seat 2, adjacent
    room_allocations = [RoomAllocation(room_id=1, room_code="A", allocated_students=2, capacity=2)]
    students = _students(2)
    not_adjacent = StudentsNotAdjacentConstraint(
        student_a_id=1, student_b_id=2, topologies={1: provider.get_topology(1, "A", 2)}
    )
    strategy = ConstraintSeatingStrategy(
        topology_provider=provider,
        constraint_set=ConstraintSet(hard_constraints=(not_adjacent,)),
    )

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.assigned_student_count == 1
    assert result.unassigned_student_count == 1
    assert any("hard constraint" in w for w in result.warnings)
    # Not a capacity problem — there was physically enough room and
    # schedule for both students; the constraint alone made it infeasible.
    assert result.scheduled_allocation_shortage is False
    assert result.physical_capacity_shortage is False


# --- Test 4: soft constraint --------------------------------------------


def test_soft_constraint_prefers_the_candidate_with_fewer_violations() -> None:
    """Student 1 (course 100) is seated first, at seat 1. Student 2
    (course 200) is seated next: sequential fill order would put them at
    seat 2 (adjacent to student 1), but that candidate carries one soft
    violation (different courses, adjacent), while seat 3 carries zero
    (not adjacent to anyone placed yet) — the strategy must prefer seat 3,
    demonstrating that a candidate with fewer soft violations beats an
    otherwise-earlier one."""
    provider = _provider(A=(1, 5))  # single row of 5
    room_allocations = [RoomAllocation(room_id=1, room_code="A", allocated_students=5, capacity=5)]
    topology = provider.get_topology(1, "A", 5)

    course_by_student = {1: 100, 2: 200, 3: 200}
    soft = SeparateCoursesConstraint(student_course_ids=course_by_student, topologies={1: topology})
    strategy = ConstraintSeatingStrategy(
        topology_provider=provider,
        constraint_set=ConstraintSet(soft_constraints=(soft,)),
    )

    result = strategy.generate(EXAM, _students(3), room_allocations)

    seat_by_student = {a.student_id: a.seat_number for a in result.assignments}
    assert seat_by_student[1] == 1
    # Student 2 (different course) must not be placed adjacent to student 1
    # when a non-adjacent seat is available.
    assert seat_by_student[2] != 2


# --- Test 5: impossible constraint --------------------------------------


def test_impossible_hard_constraint_leaves_student_unassigned_without_crashing() -> None:
    """Physical capacity = 2, scheduled = 2, registered = 2, but a hard
    constraint makes the only two students impossible to seat together.
    This is a constraint feasibility problem, not a capacity shortage —
    neither shortage flag may be true."""
    provider = _provider(A=(1, 2))
    room_allocations = [RoomAllocation(room_id=1, room_code="A", allocated_students=2, capacity=2)]
    students = _students(2)
    topology = provider.get_topology(1, "A", 2)
    not_adjacent = StudentsNotAdjacentConstraint(student_a_id=1, student_b_id=2, topologies={1: topology})
    strategy = ConstraintSeatingStrategy(
        topology_provider=provider,
        constraint_set=ConstraintSet(hard_constraints=(not_adjacent,)),
    )

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.status == GenerationStatus.PARTIAL
    assert result.unassigned_student_count == 1
    assert len(result.unassigned_student_ids) == 1
    assert result.scheduled_allocation_shortage is False
    assert result.physical_capacity_shortage is False
    assert result.capacity_shortage is True  # someone *did* go unassigned — just not for a capacity reason
    assert any("hard constraint" in w for w in result.warnings)


# --- Test 6 & 7: duplicate seat / duplicate student prevention ---------


def test_no_seat_is_ever_assigned_to_two_students() -> None:
    provider = _provider(A=(2, 5))
    room_allocations = [RoomAllocation(room_id=1, room_code="A", allocated_students=10, capacity=10)]
    strategy = ConstraintSeatingStrategy(topology_provider=provider, constraint_set=ConstraintSet())

    result = strategy.generate(EXAM, _students(10), room_allocations)

    seat_keys = [(a.room_id, a.seat_number) for a in result.assignments]
    assert len(seat_keys) == len(set(seat_keys))


def test_no_student_is_ever_assigned_twice() -> None:
    provider = _provider(A=(2, 5))
    room_allocations = [RoomAllocation(room_id=1, room_code="A", allocated_students=10, capacity=10)]
    strategy = ConstraintSeatingStrategy(topology_provider=provider, constraint_set=ConstraintSet())

    result = strategy.generate(EXAM, _students(10), room_allocations)

    student_ids = [a.student_id for a in result.assignments]
    assert len(student_ids) == len(set(student_ids))


# --- Test 8: room boundaries ---------------------------------------------


def test_assignments_never_exceed_room_allocation_or_physical_capacity() -> None:
    provider = _provider(A=(2, 5), B=(1, 3))
    room_allocations = [
        RoomAllocation(room_id=1, room_code="A", allocated_students=6, capacity=10),  # under-allocated on purpose
        RoomAllocation(room_id=2, room_code="B", allocated_students=3, capacity=3),
    ]
    strategy = ConstraintSeatingStrategy(topology_provider=provider, constraint_set=ConstraintSet())

    result = strategy.generate(EXAM, _students(20), room_allocations)

    room_a_count = len([a for a in result.assignments if a.room_id == 1])
    room_b_count = len([a for a in result.assignments if a.room_id == 2])
    assert room_a_count <= 6
    assert room_b_count <= 3
    assert all(1 <= a.seat_number <= 10 for a in result.assignments if a.room_id == 1)
    assert all(1 <= a.seat_number <= 3 for a in result.assignments if a.room_id == 2)


def test_room_fill_order_matches_room_allocations_order() -> None:
    """Preserve the MVP's room ordering semantics: room A fills before
    room B when there are no constraints forcing otherwise."""
    provider = _provider(A=(1, 5), B=(1, 5))
    room_allocations = [
        RoomAllocation(room_id=1, room_code="A", allocated_students=5, capacity=5),
        RoomAllocation(room_id=2, room_code="B", allocated_students=5, capacity=5),
    ]
    strategy = ConstraintSeatingStrategy(topology_provider=provider, constraint_set=ConstraintSet())

    result = strategy.generate(EXAM, _students(7), room_allocations)

    room_a_students = {a.student_id for a in result.assignments if a.room_id == 1}
    room_b_students = {a.student_id for a in result.assignments if a.room_id == 2}
    assert room_a_students == {1, 2, 3, 4, 5}
    assert room_b_students == {6, 7}


# --- Milestone 10: usable seats / blocked seats -----------------------------


def test_blocked_seats_are_excluded_from_candidates() -> None:
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5, blocked_seat_numbers={7, 17})
    provider = _FixedTopologyProvider({1: topology})
    room_allocations = [RoomAllocation(room_id=1, room_code="500", allocated_students=20, capacity=20)]
    strategy = ConstraintSeatingStrategy(topology_provider=provider, constraint_set=ConstraintSet())

    result = strategy.generate(EXAM, _students(18), room_allocations)

    assert result.total_physical_capacity == 20
    assert result.total_usable_capacity == 18
    assert result.assigned_student_count == 18
    assert result.unassigned_student_count == 0
    seat_numbers = {a.seat_number for a in result.assignments}
    assert 7 not in seat_numbers
    assert 17 not in seat_numbers


def test_hard_constraints_remain_enforced_around_blocked_seats() -> None:
    topology = RectangularRoomTopology(room_id=1, rows=1, columns=5, blocked_seat_numbers={3})
    provider = _FixedTopologyProvider({1: topology})
    room_allocations = [RoomAllocation(room_id=1, room_code="500", allocated_students=5, capacity=5)]
    not_adjacent = StudentsNotAdjacentConstraint(student_a_id=1, student_b_id=2, topologies={1: topology})
    strategy = ConstraintSeatingStrategy(
        topology_provider=provider, constraint_set=ConstraintSet(hard_constraints=(not_adjacent,))
    )

    result = strategy.generate(EXAM, _students(2), room_allocations)

    seat_by_student = {a.student_id: a.seat_number for a in result.assignments}
    assert 3 not in seat_by_student.values()  # blocked seat never a candidate at all
    # Seat 1 and seat 2 are adjacent; seat 3 is blocked (skipped entirely,
    # not a candidate); student 1 gets seat 1, student 2 must skip seat 2
    # (adjacent, hard-blocked) and land on seat 4 (seat 3 not offered).
    assert seat_by_student[1] == 1
    assert seat_by_student[2] == 4


def test_soft_constraints_still_evaluated_with_blocked_seats_present() -> None:
    topology = RectangularRoomTopology(room_id=1, rows=1, columns=5, blocked_seat_numbers={3})
    provider = _FixedTopologyProvider({1: topology})
    room_allocations = [RoomAllocation(room_id=1, room_code="500", allocated_students=5, capacity=5)]
    course_ids = {1: 100, 2: 200}
    soft = SeparateCoursesConstraint(student_course_ids=course_ids, topologies={1: topology})
    strategy = ConstraintSeatingStrategy(
        topology_provider=provider, constraint_set=ConstraintSet(soft_constraints=(soft,))
    )

    result = strategy.generate(EXAM, _students(2), room_allocations)

    seat_by_student = {a.student_id: a.seat_number for a in result.assignments}
    assert seat_by_student[1] == 1
    # Seat 2 is adjacent to seat 1 (different course -> soft violation);
    # seat 3 is blocked; seat 4 is not adjacent to seat 1 -> preferred.
    assert seat_by_student[2] == 4


def test_anti_cheating_default_still_respects_blocked_seats() -> None:
    """The default (student_course_ids-driven) anti-cheating behavior is
    unaffected by blocked seats: seat 3 is never a candidate at all. With
    only one student per course here there is no same-course neighbor to
    score against, so placement falls back to plain earliest-available-
    seat order — seat 2 is *not* skipped, since adjacency to a
    *different* course is never penalized (see
    tests/seating/test_anti_cheating.py for the actual course-separation
    behavior with multiple same-course students)."""
    topology = RectangularRoomTopology(room_id=1, rows=1, columns=5, blocked_seat_numbers={3})
    provider = _FixedTopologyProvider({1: topology})
    room_allocations = [RoomAllocation(room_id=1, room_code="500", allocated_students=5, capacity=5)]
    strategy = ConstraintSeatingStrategy(
        topology_provider=provider, student_course_ids={1: 100, 2: 200}
    )

    result = strategy.generate(EXAM, _students(2), room_allocations)

    seat_by_student = {a.student_id: a.seat_number for a in result.assignments}
    assert 3 not in seat_by_student.values()
    assert seat_by_student[1] == 1
    assert seat_by_student[2] == 2


def test_blocked_seat_result_is_deterministic() -> None:
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5, blocked_seat_numbers={7, 17})
    provider = _FixedTopologyProvider({1: topology})
    room_allocations = [RoomAllocation(room_id=1, room_code="500", allocated_students=18, capacity=20)]
    strategy = ConstraintSeatingStrategy(topology_provider=provider, constraint_set=ConstraintSet())
    students = _students(18)

    first = strategy.generate(EXAM, students, room_allocations)
    second = strategy.generate(EXAM, students, room_allocations)

    assert first.assignments == second.assignments
