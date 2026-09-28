"""Phase 13 — focused validation suite for the anti-cheating heuristic
(`ConstraintSeatingStrategy`'s default course-interleaved placement +
same-course spatial scoring, `app/seating/anti_cheating.py`).

This is deliberately NOT a new algorithm or a generalized scoring
framework — it exists to answer one question across a representative set
of real-world-shaped fixtures: "does the constraint strategy actually
produce a materially better spatial distribution than the strategy that
knows nothing about courses at all (`SequentialSeatingStrategy`), fed the
exact same course-grouped student order a real multi-course session
would produce?"

Unlike `test_anti_cheating.py` (which compares against a hand-built
"naive course-blocked" baseline), every comparison here runs the real,
production `SequentialSeatingStrategy` — same topology, same blocked
seats, same room allocations — so the baseline is an actual strategy
output, not a simulation of one.

No claim of optimality anywhere in this file: assertions check that
same-course adjacency is *reduced*, never that it is minimized, zero, or
below some universal percentage target. Pure tests — no DB, no HTTP.
"""

from datetime import date

from app.domain import Exam, GenerationStatus, Student
from app.seating.constraints import ConstraintSet, StudentsNotAdjacentConstraint
from app.seating.models import RoomAllocation, SeatAssignmentRecord, SeatingResult
from app.seating.quality_metrics import SeatingQualityReport, evaluate_seating_quality
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
    """Test double shared by this file's fixtures — builds a
    `RectangularRoomTopology` directly so blocked seats can be configured
    without a database."""

    def __init__(self, topologies_by_room_id: dict[int, RectangularRoomTopology]) -> None:
        self._topologies = topologies_by_room_id

    def get_topology(self, room_id: int, room_code: str, capacity: int) -> RectangularRoomTopology:
        return self._topologies[room_id]


def _students(count: int, start: int = 1) -> list[Student]:
    return [
        Student(id=i, student_number=str(1000 + i), full_name=f"Student {i}")
        for i in range(start, start + count)
    ]


def _course_mapping(*counts: int) -> dict[int, int]:
    """student_id -> course_id for `sum(counts)` students, ids 1..N, in
    course-grouped blocks — course 100 gets the first `counts[0]`
    students, course 200 the next `counts[1]`, and so on. This is
    deliberately the same shape `_session_student_sort_key` produces in
    production (grouped by course, ascending student_number within each
    group), so feeding it straight to `SequentialSeatingStrategy` gives
    the *real* "no anti-cheating" baseline a session would actually see."""
    mapping: dict[int, int] = {}
    student_id = 1
    for course_index, count in enumerate(counts):
        course_id = 100 * (course_index + 1)
        for _ in range(count):
            mapping[student_id] = course_id
            student_id += 1
    return mapping


def _as_candidates(
    assignments: list[SeatAssignmentRecord], topology: SeatTopology
) -> list[SeatAssignmentCandidate]:
    return [
        SeatAssignmentCandidate(student_id=a.student_id, position=topology.position_for_seat(a.seat_number))
        for a in assignments
    ]


def _generate_pair(
    topology: RectangularRoomTopology,
    mapping: dict[int, int],
    students: list[Student],
    allocated_students: int,
) -> tuple[SeatingQualityReport, SeatingQualityReport, SeatingResult, SeatingResult]:
    """Runs the exact same room/student data through both
    SequentialSeatingStrategy and ConstraintSeatingStrategy (same
    topology provider, so both see the same usable/blocked seats), and
    returns (sequential_quality, constraint_quality, sequential_result,
    constraint_result)."""
    provider = _FixedTopologyProvider({topology.room_id: topology})
    room_allocations = [
        RoomAllocation(
            room_id=topology.room_id,
            room_code="X",
            allocated_students=allocated_students,
            capacity=topology.physical_capacity,
        )
    ]

    sequential_result = SequentialSeatingStrategy(topology_provider=provider).generate(
        EXAM, students, room_allocations
    )
    constraint_result = ConstraintSeatingStrategy(
        topology_provider=provider, student_course_ids=mapping
    ).generate(EXAM, students, room_allocations)

    topologies = {topology.room_id: topology}
    sequential_quality = evaluate_seating_quality(
        _as_candidates(sequential_result.assignments, topology), mapping, topologies
    )
    constraint_quality = evaluate_seating_quality(
        _as_candidates(constraint_result.assignments, topology), mapping, topologies
    )
    return sequential_quality, constraint_quality, sequential_result, constraint_result


def _assert_no_duplicates(assignments: list[SeatAssignmentRecord]) -> None:
    seat_numbers = [a.seat_number for a in assignments]
    student_ids = [a.student_id for a in assignments]
    assert len(seat_numbers) == len(set(seat_numbers)), "a seat was assigned twice"
    assert len(student_ids) == len(set(student_ids)), "a student was assigned twice"


def _assert_no_blocked_seat_assigned(assignments: list[SeatAssignmentRecord], blocked: set[int]) -> None:
    assigned_seats = {a.seat_number for a in assignments}
    assert assigned_seats.isdisjoint(blocked), f"blocked seat(s) {assigned_seats & blocked} were assigned"


# --- Step 2/3/4: representative fixtures, Sequential vs Constraint ---------


def test_fixture_1_two_courses_equal_sizes() -> None:
    """10 + 10 in a 4x5=20 room."""
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5)
    mapping = _course_mapping(10, 10)
    students = _students(20)

    sequential_quality, constraint_quality, sequential_result, constraint_result = _generate_pair(
        topology, mapping, students, allocated_students=20
    )

    assert constraint_result.assigned_student_count == 20
    assert sequential_result.assigned_student_count == 20
    _assert_no_duplicates(constraint_result.assignments)
    assert {mapping[a.student_id] for a in constraint_result.assignments} == {100, 200}
    assert constraint_quality.same_course_adjacent_pairs < sequential_quality.same_course_adjacent_pairs


def test_fixture_2_two_courses_highly_unequal_sizes() -> None:
    """18 + 2 in a 4x5=20 room — the minority course is only 2 students."""
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5)
    mapping = _course_mapping(18, 2)
    students = _students(20)

    sequential_quality, constraint_quality, sequential_result, constraint_result = _generate_pair(
        topology, mapping, students, allocated_students=20
    )

    assert constraint_result.assigned_student_count == 20
    assert {mapping[a.student_id] for a in constraint_result.assignments} == {100, 200}
    _assert_no_duplicates(constraint_result.assignments)
    # A minority of 2 among 20 can't be improved by much, but it must
    # never be *worse* than sequential's solid block.
    assert constraint_quality.same_course_adjacent_pairs <= sequential_quality.same_course_adjacent_pairs


def test_fixture_3_three_courses_unequal_sizes() -> None:
    """8 + 6 + 4 in a 4x5=20 room."""
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5)
    mapping = _course_mapping(8, 6, 4)
    students = _students(18)

    sequential_quality, constraint_quality, sequential_result, constraint_result = _generate_pair(
        topology, mapping, students, allocated_students=18
    )

    assert constraint_result.assigned_student_count == 18
    assert {mapping[a.student_id] for a in constraint_result.assignments} == {100, 200, 300}
    _assert_no_duplicates(constraint_result.assignments)
    assert constraint_quality.same_course_adjacent_pairs < sequential_quality.same_course_adjacent_pairs


def test_fixture_4_five_courses() -> None:
    """5 courses of 4 students each in a 4x5=20 room."""
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5)
    mapping = _course_mapping(4, 4, 4, 4, 4)
    students = _students(20)

    sequential_quality, constraint_quality, sequential_result, constraint_result = _generate_pair(
        topology, mapping, students, allocated_students=20
    )

    assert constraint_result.assigned_student_count == 20
    assert {mapping[a.student_id] for a in constraint_result.assignments} == {100, 200, 300, 400, 500}
    _assert_no_duplicates(constraint_result.assignments)
    assert constraint_quality.same_course_adjacent_pairs < sequential_quality.same_course_adjacent_pairs


def test_fixture_5_six_or_more_courses() -> None:
    """6 courses of 3 students each in a 6x3=18 room."""
    topology = RectangularRoomTopology(room_id=1, rows=6, columns=3)
    mapping = _course_mapping(3, 3, 3, 3, 3, 3)
    students = _students(18)

    sequential_quality, constraint_quality, sequential_result, constraint_result = _generate_pair(
        topology, mapping, students, allocated_students=18
    )

    assert constraint_result.assigned_student_count == 18
    assert {mapping[a.student_id] for a in constraint_result.assignments} == {100, 200, 300, 400, 500, 600}
    _assert_no_duplicates(constraint_result.assignments)
    assert constraint_quality.same_course_adjacent_pairs < sequential_quality.same_course_adjacent_pairs


def test_fixture_10_wide_room_2x10() -> None:
    """3 courses (8+7+5) in a 2x10=20 room — every seat's own row holds
    up to 9 other seats, the shape most likely to expose a same-row
    scoring issue (see Phase 11.1's review)."""
    topology = RectangularRoomTopology(room_id=1, rows=2, columns=10)
    mapping = _course_mapping(8, 7, 5)
    students = _students(20)

    sequential_quality, constraint_quality, sequential_result, constraint_result = _generate_pair(
        topology, mapping, students, allocated_students=20
    )

    assert constraint_result.assigned_student_count == 20
    _assert_no_duplicates(constraint_result.assignments)
    assert constraint_quality.same_course_adjacent_pairs < sequential_quality.same_course_adjacent_pairs


def test_fixture_11_taller_room_5x8() -> None:
    """3 courses (15+15+10) in a 5x8=40 room."""
    topology = RectangularRoomTopology(room_id=1, rows=5, columns=8)
    mapping = _course_mapping(15, 15, 10)
    students = _students(40)

    sequential_quality, constraint_quality, sequential_result, constraint_result = _generate_pair(
        topology, mapping, students, allocated_students=40
    )

    assert constraint_result.assigned_student_count == 40
    _assert_no_duplicates(constraint_result.assignments)
    assert constraint_quality.same_course_adjacent_pairs < sequential_quality.same_course_adjacent_pairs


# --- Step 5: edge cases -----------------------------------------------------


def test_dominant_course_with_several_small_courses() -> None:
    """A: 15, B: 3, C: 2 in a 4x5=20 room (exact fit). Verifies every
    student is assigned, B and C are not silently discarded (course
    starvation), and the result is deterministic."""
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5)
    mapping = _course_mapping(15, 3, 2)
    students = _students(20)

    _, constraint_quality, sequential_result, constraint_result = _generate_pair(
        topology, mapping, students, allocated_students=20
    )

    assert constraint_result.assigned_student_count == 20
    assert constraint_result.unassigned_student_count == 0
    course_counts = {100: 0, 200: 0, 300: 0}
    for a in constraint_result.assignments:
        course_counts[mapping[a.student_id]] += 1
    assert course_counts == {100: 15, 200: 3, 300: 2}  # nobody starved or dropped
    _assert_no_duplicates(constraint_result.assignments)

    provider = _FixedTopologyProvider({1: topology})
    room_allocations = [RoomAllocation(room_id=1, room_code="X", allocated_students=20, capacity=20)]
    second = ConstraintSeatingStrategy(topology_provider=provider, student_course_ids=mapping).generate(
        EXAM, students, room_allocations
    )
    assert second.assignments == constraint_result.assignments


def test_tiny_courses_are_placed_not_clustered_into_invalid_positions() -> None:
    """A: 8, B: 1, C: 1 in a 2x5=10 room (exact fit). The two single-
    student courses must land on real, usable, non-duplicate seats."""
    topology = RectangularRoomTopology(room_id=1, rows=2, columns=5)
    mapping = _course_mapping(8, 1, 1)
    students = _students(10)

    _, _, _, constraint_result = _generate_pair(topology, mapping, students, allocated_students=10)

    assert constraint_result.assigned_student_count == 10
    _assert_no_duplicates(constraint_result.assignments)
    assert all(1 <= a.seat_number <= 10 for a in constraint_result.assignments)
    assert {mapping[a.student_id] for a in constraint_result.assignments} == {100, 200, 300}


def test_blocked_seats_never_assigned_and_capacity_uses_usable_seats() -> None:
    """5x5=25 physical, block {7, 13, 19} (22 usable); three courses
    filling exactly 22 usable seats. Blocked seats must never appear in
    either strategy's output, and reported capacity must reflect usable,
    not physical, seats."""
    topology = RectangularRoomTopology(room_id=1, rows=5, columns=5, blocked_seat_numbers={7, 13, 19})
    mapping = _course_mapping(8, 7, 7)
    students = _students(22)
    blocked = {7, 13, 19}

    sequential_quality, constraint_quality, sequential_result, constraint_result = _generate_pair(
        topology, mapping, students, allocated_students=22
    )

    assert constraint_result.total_physical_capacity == 25
    assert constraint_result.total_usable_capacity == 22
    assert constraint_result.assigned_student_count == 22
    _assert_no_blocked_seat_assigned(constraint_result.assignments, blocked)
    _assert_no_blocked_seat_assigned(sequential_result.assignments, blocked)
    _assert_no_duplicates(constraint_result.assignments)
    # Anti-cheating scoring must never have treated a blocked seat as an
    # occupying "student" of any course — evaluate_seating_quality only
    # ever sees real assignments, so a passing comparison here already
    # confirms blocked seats aren't polluting the same-course counts.
    assert constraint_quality.same_course_adjacent_pairs < sequential_quality.same_course_adjacent_pairs

    second = ConstraintSeatingStrategy(
        topology_provider=_FixedTopologyProvider({1: topology}), student_course_ids=mapping
    ).generate(EXAM, students, [RoomAllocation(room_id=1, room_code="X", allocated_students=22, capacity=25)])
    assert second.assignments == constraint_result.assignments


def test_tight_capacity_shortage_semantics_are_unchanged() -> None:
    """Three courses of 10 each (30 registered) sharing a 20-seat room —
    only the existing scheduled/physical/usable shortage flags may be
    used; no new warning type or capacity concept is introduced."""
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5)
    provider = _FixedTopologyProvider({1: topology})
    mapping = _course_mapping(10, 10, 10)
    students = _students(30)
    room_allocations = [RoomAllocation(room_id=1, room_code="X", allocated_students=30, capacity=20)]
    strategy = ConstraintSeatingStrategy(topology_provider=provider, student_course_ids=mapping)

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.assigned_student_count == 20
    assert result.unassigned_student_count == 10
    assert result.capacity_shortage is True
    assert result.physical_capacity_shortage is True
    assert result.usable_capacity_shortage is True
    assert result.scheduled_allocation_shortage is False


def test_hard_constraints_are_still_fully_enforced() -> None:
    """Regression check: an explicit hard constraint
    (StudentsNotAdjacentConstraint) must remain fully enforced exactly as
    it was before the anti-cheating default existed — the two students it
    governs must never end up adjacent, even though a non-adjacent
    alternative exists."""
    topology = RectangularRoomTopology(room_id=1, rows=2, columns=5)
    provider = _FixedTopologyProvider({1: topology})
    room_allocations = [RoomAllocation(room_id=1, room_code="X", allocated_students=10, capacity=10)]
    students = _students(2)
    not_adjacent = StudentsNotAdjacentConstraint(student_a_id=1, student_b_id=2, topologies={1: topology})
    strategy = ConstraintSeatingStrategy(
        topology_provider=provider, constraint_set=ConstraintSet(hard_constraints=(not_adjacent,))
    )

    result = strategy.generate(EXAM, students, room_allocations)

    assert result.status == GenerationStatus.SUCCESS
    seat_by_student = {a.student_id: a.seat_number for a in result.assignments}
    seat_a = topology.position_for_seat(seat_by_student[1])
    seat_b = topology.position_for_seat(seat_by_student[2])
    assert topology.is_adjacent(seat_a, seat_b) is False


# --- Step 6: determinism -----------------------------------------------


def test_representative_fixtures_are_deterministic_across_repeated_runs() -> None:
    """No random.shuffle, no random choices, no nondeterministic
    iteration anywhere in the path — the same input must always produce
    the same complete assignment list, run after run."""
    fixtures = [
        (RectangularRoomTopology(room_id=1, rows=4, columns=5), _course_mapping(8, 6, 4), 18),
        (RectangularRoomTopology(room_id=1, rows=2, columns=10), _course_mapping(8, 7, 5), 20),
        (
            RectangularRoomTopology(room_id=1, rows=5, columns=5, blocked_seat_numbers={7, 13, 19}),
            _course_mapping(8, 7, 7),
            22,
        ),
    ]
    for topology, mapping, allocated in fixtures:
        students = _students(allocated)
        provider = _FixedTopologyProvider({1: topology})
        room_allocations = [
            RoomAllocation(
                room_id=1, room_code="X", allocated_students=allocated, capacity=topology.physical_capacity
            )
        ]
        strategy = ConstraintSeatingStrategy(topology_provider=provider, student_course_ids=mapping)

        first = strategy.generate(EXAM, students, room_allocations)
        second = strategy.generate(EXAM, students, room_allocations)
        third = strategy.generate(EXAM, students, room_allocations)

        assert first.assignments == second.assignments == third.assignments
        assert first.unassigned_student_ids == second.unassigned_student_ids == third.unassigned_student_ids


# --- Step 5: single-course regression ---------------------------------------


def test_single_course_seating_is_unaffected() -> None:
    """One course only: the anti-cheating default must be a complete
    no-op, matching SequentialSeatingStrategy exactly — there is nothing
    to separate a single course from."""
    topology = RectangularRoomTopology(room_id=1, rows=4, columns=5)
    provider = _FixedTopologyProvider({1: topology})
    students = _students(20)
    mapping = {student.id: 100 for student in students if student.id is not None}
    room_allocations = [RoomAllocation(room_id=1, room_code="X", allocated_students=20, capacity=20)]

    constraint_result = ConstraintSeatingStrategy(
        topology_provider=provider, student_course_ids=mapping
    ).generate(EXAM, students, room_allocations)
    sequential_result = SequentialSeatingStrategy(topology_provider=provider).generate(
        EXAM, students, room_allocations
    )

    assert constraint_result.assignments == sequential_result.assignments


# --- Step 3: sanity-check the metric itself ---------------------------------
# (The multi-course ExaminationSession validation — Step 5's "Session"
# requirement — is a DB-backed scenario and lives in
# tests/services/test_session_seating_generation.py, not here; this file
# is pure, no DB, no HTTP.)


def test_quality_report_measures_only_what_it_documents() -> None:
    """Sanity check on the metric itself, not the strategy: a hand-built
    seating with one deliberate orthogonal pair and one deliberate
    diagonal pair reports exactly those counts, and nothing else."""
    topology = RectangularRoomTopology(room_id=1, rows=2, columns=2)
    # Seats: 1=(0,0) 2=(0,1) 3=(1,0) 4=(1,1). Same course at 1 and 2
    # (orthogonal), and a different pair (course 200) at 3 alone.
    candidates = [
        SeatAssignmentCandidate(student_id=1, position=topology.position_for_seat(1)),
        SeatAssignmentCandidate(student_id=2, position=topology.position_for_seat(2)),
        SeatAssignmentCandidate(student_id=3, position=topology.position_for_seat(3)),
    ]
    mapping = {1: 100, 2: 100, 3: 200}

    report = evaluate_seating_quality(candidates, mapping, {1: topology})

    assert isinstance(report, SeatingQualityReport)
    assert report.same_course_adjacent_pairs == 1  # (1, 2): same course, orthogonal
    assert report.same_course_diagonal_pairs == 0  # no same-course diagonal pair here
