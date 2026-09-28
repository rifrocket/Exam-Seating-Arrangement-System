"""Tests for the anti-cheating default behavior added to
`ConstraintSeatingStrategy` this milestone: course-interleaved placement
order (`app.seating.anti_cheating.order_students_for_placement`) plus
same-course spatial penalty scoring (`same_course_penalty`), and the
pure, test-only `app.seating.quality_metrics.evaluate_seating_quality`
helper used to measure it. Pure tests — no DB, no HTTP. All data
synthetic.

Deliberately generic across course *counts*: the same helpers below build
2, 3, 4, and 6-course scenarios with one function, never course-count-
specific logic, matching the requirement that this algorithm not special-
case any particular number of courses.
"""

from datetime import date

from app.domain import Exam, Student
from app.seating.anti_cheating import order_students_for_placement, same_course_penalty
from app.seating.models import RoomAllocation
from app.seating.quality_metrics import evaluate_seating_quality
from app.seating.strategies.constraint import ConstraintSeatingStrategy
from app.seating.strategies.sequential import SequentialSeatingStrategy
from app.seating.topology import RectangularRoomTopology, SeatAssignmentCandidate, SeatTopology
from app.seating.topology_provider import RoomTopologyProvider

EXAM = Exam(
    id=1,
    course_id=1,
    exam_date=date(2024, 5, 30),
    time_slot="10:00-12:00",
    expected_student_count=10,
    day_label="Thursday",
)


class _FixedTopologyProvider(RoomTopologyProvider):
    """Same minimal test double `test_constraint_strategy.py` already
    uses — builds a `RectangularRoomTopology` directly so tests can
    configure blocked seats without a database."""

    def __init__(self, topologies_by_room_id: dict[int, RectangularRoomTopology]) -> None:
        self._topologies = topologies_by_room_id

    def get_topology(self, room_id: int, room_code: str, capacity: int):
        return self._topologies[room_id]


def _students(count: int, start: int = 1) -> list[Student]:
    return [
        Student(id=i, student_number=str(1000 + i), full_name=f"Student {i}") for i in range(start, start + count)
    ]


def _course_mapping(*counts: int) -> dict[int, int]:
    """student_id -> course_id for `sum(counts)` students, ids 1..N, the
    first `counts[0]` students in course 100, the next `counts[1]` in
    course 200, and so on — one call handles any number of courses."""
    mapping: dict[int, int] = {}
    student_id = 1
    for course_index, count in enumerate(counts):
        course_id = 100 * (course_index + 1)
        for _ in range(count):
            mapping[student_id] = course_id
            student_id += 1
    return mapping


def _naive_course_blocked_candidates(
    topology: SeatTopology, students: list[Student], student_course_ids: dict[int, int]
) -> list[SeatAssignmentCandidate]:
    """The literal pre-this-milestone default behavior, used only as a
    comparison baseline in these tests: seats filled in topology order,
    students processed strictly course-block by course-block (grouped,
    never interleaved) — i.e. exactly what produced contiguous same-course
    blocks before this milestone."""
    ordered = sorted(students, key=lambda s: (student_course_ids[s.id], s.id))
    positions = topology.usable_positions()
    return [
        SeatAssignmentCandidate(student_id=student.id, position=position)
        for student, position in zip(ordered, positions, strict=True)
    ]


def _real_candidates(result_assignments, topology: SeatTopology) -> list[SeatAssignmentCandidate]:
    return [
        SeatAssignmentCandidate(student_id=a.student_id, position=topology.position_for_seat(a.seat_number))
        for a in result_assignments
    ]


# --- order_students_for_placement (unit) ------------------------------------


def test_order_students_for_placement_is_identity_for_a_single_course() -> None:
    students = _students(5)
    mapping = dict.fromkeys((s.id for s in students), 100)

    ordered = order_students_for_placement(students, mapping)

    assert ordered == students


def test_order_students_for_placement_alternates_equal_sized_courses() -> None:
    students = _students(6)
    mapping = _course_mapping(3, 3)

    ordered = order_students_for_placement(students, mapping)

    course_sequence = [mapping[s.id] for s in ordered]
    # Perfectly alternating for equal-sized courses (deterministic tie-break).
    assert course_sequence == [100, 200, 100, 200, 100, 200]


def test_order_students_for_placement_tapers_a_dominant_course() -> None:
    """A much larger course keeps winning the 'most remaining' tiebreak
    until its remaining count drops to meet the next-largest course —
    never a hardcoded alternation pattern, and it must still place every
    student exactly once."""
    students = _students(16)
    mapping = _course_mapping(12, 4)

    ordered = order_students_for_placement(students, mapping)

    assert len(ordered) == 16
    assert {s.id for s in ordered} == {s.id for s in students}
    course_sequence = [mapping[s.id] for s in ordered]
    # The very first turns are dominated by the 12-student course...
    assert course_sequence[0] == 100
    # ...but the smaller course does get turns well before the end, not
    # merely appended after every course-100 student is placed.
    assert 200 in course_sequence[:12]


def test_order_students_for_placement_works_for_six_courses_with_no_special_casing() -> None:
    students = _students(18)
    mapping = _course_mapping(3, 3, 3, 3, 3, 3)

    ordered = order_students_for_placement(students, mapping)

    assert len(ordered) == 18
    assert {mapping[s.id] for s in ordered} == {100, 200, 300, 400, 500, 600}


# --- same_course_penalty (unit) ---------------------------------------------


def test_same_course_penalty_is_zero_with_no_same_course_neighbor_placed() -> None:
    topology = RectangularRoomTopology(room_id=1, rows=2, columns=5)
    candidate = topology.position_for_seat(1)
    placed = [SeatAssignmentCandidate(student_id=99, position=topology.position_for_seat(10))]
    mapping = {1: 100, 99: 200}  # student 99 is a *different* course

    penalty = same_course_penalty(candidate, 100, placed, mapping, topology)

    assert penalty == 0.0


def test_same_course_penalty_penalizes_orthogonal_adjacency_most() -> None:
    topology = RectangularRoomTopology(room_id=1, rows=1, columns=5)
    placed = [SeatAssignmentCandidate(student_id=1, position=topology.position_for_seat(1))]
    mapping = {1: 100}

    adjacent_penalty = same_course_penalty(topology.position_for_seat(2), 100, placed, mapping, topology)
    far_penalty = same_course_penalty(topology.position_for_seat(5), 100, placed, mapping, topology)

    assert adjacent_penalty > far_penalty


def test_same_course_penalty_penalizes_diagonal_less_than_orthogonal() -> None:
    topology = RectangularRoomTopology(room_id=1, rows=2, columns=2)
    placed = [SeatAssignmentCandidate(student_id=1, position=topology.position_for_seat(1))]  # (row0, col0)
    mapping = {1: 100}

    orthogonal_candidate = topology.position_for_seat(2)  # (row0, col1): same row
    diagonal_candidate = topology.position_for_seat(4)  # (row1, col1): diagonal only

    orthogonal_penalty = same_course_penalty(orthogonal_candidate, 100, placed, mapping, topology)
    diagonal_penalty = same_course_penalty(diagonal_candidate, 100, placed, mapping, topology)

    assert orthogonal_penalty > diagonal_penalty > 0.0


# --- ConstraintSeatingStrategy: multi-course separation (generic algorithm) -


def test_two_course_separation() -> None:
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5)  # 20 seats
    provider = _FixedTopologyProvider({1: topology})
    mapping = _course_mapping(10, 10)
    students = _students(20)
    room_allocations = [RoomAllocation(room_id=1, room_code="X", allocated_students=20, capacity=20)]
    strategy = ConstraintSeatingStrategy(topology_provider=provider, student_course_ids=mapping)

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.assigned_student_count == 20
    assert result.unassigned_student_count == 0
    seat_numbers = [a.seat_number for a in result.assignments]
    assert len(seat_numbers) == len(set(seat_numbers))
    assert {mapping[a.student_id] for a in result.assignments} == {100, 200}

    real_quality = evaluate_seating_quality(_real_candidates(result.assignments, topology), mapping, {1: topology})
    naive_quality = evaluate_seating_quality(
        _naive_course_blocked_candidates(topology, students, mapping), mapping, {1: topology}
    )
    assert real_quality.same_course_adjacent_pairs < naive_quality.same_course_adjacent_pairs

    second = strategy.generate(EXAM, students, room_allocations)
    assert second.assignments == result.assignments


def test_three_course_separation() -> None:
    """Section 9's exact shape: 4x5 = 20 seats, A=7, B=7, C=6."""
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5)
    provider = _FixedTopologyProvider({1: topology})
    mapping = _course_mapping(7, 7, 6)
    students = _students(20)
    room_allocations = [RoomAllocation(room_id=1, room_code="X", allocated_students=20, capacity=20)]
    strategy = ConstraintSeatingStrategy(topology_provider=provider, student_course_ids=mapping)

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.assigned_student_count == 20
    seat_keys = {a.seat_number for a in result.assignments}
    assert len(seat_keys) == 20
    assert {mapping[a.student_id] for a in result.assignments} == {100, 200, 300}

    real_quality = evaluate_seating_quality(_real_candidates(result.assignments, topology), mapping, {1: topology})
    naive_quality = evaluate_seating_quality(
        _naive_course_blocked_candidates(topology, students, mapping), mapping, {1: topology}
    )
    assert real_quality.same_course_adjacent_pairs < naive_quality.same_course_adjacent_pairs


def test_four_course_separation() -> None:
    """Section 8's exact shape: 5x5 = 25 seats, A=7, B=6, C=6, D=6."""
    topology = RectangularRoomTopology(room_id=1, rows=5, columns=5)
    provider = _FixedTopologyProvider({1: topology})
    mapping = _course_mapping(7, 6, 6, 6)
    students = _students(25)
    room_allocations = [RoomAllocation(room_id=1, room_code="X", allocated_students=25, capacity=25)]
    strategy = ConstraintSeatingStrategy(topology_provider=provider, student_course_ids=mapping)

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.assigned_student_count == 25
    assert result.unassigned_student_count == 0
    seat_keys = {a.seat_number for a in result.assignments}
    assert len(seat_keys) == 25
    student_ids = {a.student_id for a in result.assignments}
    assert len(student_ids) == 25
    assert {mapping[a.student_id] for a in result.assignments} == {100, 200, 300, 400}

    real_quality = evaluate_seating_quality(_real_candidates(result.assignments, topology), mapping, {1: topology})
    naive_quality = evaluate_seating_quality(
        _naive_course_blocked_candidates(topology, students, mapping), mapping, {1: topology}
    )
    assert real_quality.same_course_adjacent_pairs < naive_quality.same_course_adjacent_pairs

    second = strategy.generate(EXAM, students, room_allocations)
    assert second.assignments == result.assignments


def test_six_course_separation_with_no_special_casing() -> None:
    """Section 10's exact shape: 6x3 = 18 seats, six courses of 3 each —
    proves the algorithm needs no course-count-specific branching."""
    topology = RectangularRoomTopology(room_id=1, rows=6, columns=3)
    provider = _FixedTopologyProvider({1: topology})
    mapping = _course_mapping(3, 3, 3, 3, 3, 3)
    students = _students(18)
    room_allocations = [RoomAllocation(room_id=1, room_code="X", allocated_students=18, capacity=18)]
    strategy = ConstraintSeatingStrategy(topology_provider=provider, student_course_ids=mapping)

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.assigned_student_count == 18
    assert {mapping[a.student_id] for a in result.assignments} == {100, 200, 300, 400, 500, 600}
    seat_keys = {a.seat_number for a in result.assignments}
    assert len(seat_keys) == 18

    real_quality = evaluate_seating_quality(_real_candidates(result.assignments, topology), mapping, {1: topology})
    naive_quality = evaluate_seating_quality(
        _naive_course_blocked_candidates(topology, students, mapping), mapping, {1: topology}
    )
    assert real_quality.same_course_adjacent_pairs < naive_quality.same_course_adjacent_pairs


def test_unequal_course_sizes_are_distributed_not_clustered() -> None:
    """Section 11's exact shape: 4x5 = 20 seats, A=12, B=4, C=3, D=1."""
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5)
    provider = _FixedTopologyProvider({1: topology})
    mapping = _course_mapping(12, 4, 3, 1)
    students = _students(20)
    room_allocations = [RoomAllocation(room_id=1, room_code="X", allocated_students=20, capacity=20)]
    strategy = ConstraintSeatingStrategy(topology_provider=provider, student_course_ids=mapping)

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.assigned_student_count == 20
    assert {mapping[a.student_id] for a in result.assignments} == {100, 200, 300, 400}
    seat_keys = {a.seat_number for a in result.assignments}
    assert len(seat_keys) == 20

    real_quality = evaluate_seating_quality(_real_candidates(result.assignments, topology), mapping, {1: topology})
    naive_quality = evaluate_seating_quality(
        _naive_course_blocked_candidates(topology, students, mapping), mapping, {1: topology}
    )
    # The dominant 12-student course is what the naive baseline clusters
    # hardest; the real algorithm must still improve materially on it even
    # though a course occupying 60% of the room can never be perfectly
    # isolated from itself.
    assert real_quality.same_course_adjacent_pairs < naive_quality.same_course_adjacent_pairs


def test_blocked_seats_respected_during_course_separation() -> None:
    """Section 12's exact shape: 5x5 = 25 physical seats, block 7/13/19
    (22 usable), three courses filling exactly 22 usable seats."""
    topology = RectangularRoomTopology(room_id=1, rows=5, columns=5, blocked_seat_numbers={7, 13, 19})
    provider = _FixedTopologyProvider({1: topology})
    mapping = _course_mapping(8, 7, 7)
    students = _students(22)
    room_allocations = [RoomAllocation(room_id=1, room_code="X", allocated_students=22, capacity=25)]
    strategy = ConstraintSeatingStrategy(topology_provider=provider, student_course_ids=mapping)

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.total_physical_capacity == 25
    assert result.total_usable_capacity == 22
    assert result.assigned_student_count == 22
    assert result.unassigned_student_count == 0
    seat_numbers = {a.seat_number for a in result.assignments}
    assert seat_numbers.isdisjoint({7, 13, 19})
    assert len(seat_numbers) == 22

    real_quality = evaluate_seating_quality(_real_candidates(result.assignments, topology), mapping, {1: topology})
    naive_quality = evaluate_seating_quality(
        _naive_course_blocked_candidates(topology, students, mapping), mapping, {1: topology}
    )
    assert real_quality.same_course_adjacent_pairs < naive_quality.same_course_adjacent_pairs


# --- single-course regression (anti-cheating must be a no-op) --------------


def test_single_course_default_matches_sequential_strategy_exactly() -> None:
    """Section 13: with one course only, anti-cheating separation is
    meaningless (nothing to separate from) — the default must produce
    exactly the same seating as SequentialSeatingStrategy, not scatter
    students for no reason. Uses the `student_course_ids` constructor path
    directly (not an explicit ConstraintSet) so this proves the
    `anti_cheating_enabled` gate itself works, not just that an empty
    ConstraintSet is a no-op."""
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5)
    provider = _FixedTopologyProvider({1: topology})
    students = _students(20)
    mapping = dict.fromkeys((s.id for s in students), 100)  # one course only
    room_allocations = [RoomAllocation(room_id=1, room_code="X", allocated_students=20, capacity=20)]

    constraint_strategy = ConstraintSeatingStrategy(topology_provider=provider, student_course_ids=mapping)
    constraint_result = constraint_strategy.generate(EXAM, students, room_allocations)
    sequential_result = SequentialSeatingStrategy().generate(EXAM, students, room_allocations)

    assert constraint_result.assignments == sequential_result.assignments
    assert constraint_result.assigned_student_count == sequential_result.assigned_student_count


def test_single_course_default_via_exam_course_id_also_matches_sequential() -> None:
    """Same regression, but through the *other* default path — no
    `student_course_ids` given at all, so the course mapping is derived
    from `exam.course_id` for every student (the single-exam production
    path) — must be equally unaffected."""
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5)
    provider = _FixedTopologyProvider({1: topology})
    students = _students(20)
    room_allocations = [RoomAllocation(room_id=1, room_code="X", allocated_students=20, capacity=20)]

    constraint_strategy = ConstraintSeatingStrategy(topology_provider=provider)
    constraint_result = constraint_strategy.generate(EXAM, students, room_allocations)
    sequential_result = SequentialSeatingStrategy().generate(EXAM, students, room_allocations)

    assert constraint_result.assignments == sequential_result.assignments


# --- capacity shortage in an anti-cheating (multi-course) context ----------


def test_capacity_shortage_with_multiple_courses_present() -> None:
    """Three courses of 10 each (30 registered) sharing a 20-seat room —
    the anti-cheating default must still assign exactly 20, leave exactly
    10 unassigned, and report the same capacity flags any other strategy
    would for this shape, deterministically."""
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5)
    provider = _FixedTopologyProvider({1: topology})
    mapping = _course_mapping(10, 10, 10)
    students = _students(30)
    room_allocations = [RoomAllocation(room_id=1, room_code="X", allocated_students=30, capacity=20)]
    strategy = ConstraintSeatingStrategy(topology_provider=provider, student_course_ids=mapping)

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.assigned_student_count == 20
    assert result.unassigned_student_count == 10
    assert result.physical_capacity_shortage is True
    assert result.capacity_shortage is True

    second = strategy.generate(EXAM, students, room_allocations)
    assert second.assignments == result.assignments
    assert second.unassigned_student_ids == result.unassigned_student_ids
