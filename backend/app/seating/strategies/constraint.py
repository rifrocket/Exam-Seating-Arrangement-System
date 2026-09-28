"""ConstraintSeatingStrategy: the first strategy built on the Milestone 6
constraint foundation (`app.seating.constraints`, `app.seating.topology`),
extended (this milestone) with topology-aware anti-cheating spatial
separation — see "Anti-cheating seating" below.

Algorithm — a deterministic constructive greedy placement, not a solver:

    students (given order, or the anti-cheating placement order below)
        -> for each student, in order:
             candidate seats = remaining seats, in room-then-seat-number order
             -> evaluate hard constraints for each candidate
             -> keep only candidates with zero hard-constraint violations
             -> among those, prefer the one with the lowest score (either
                the number of soft-constraint violations, or the
                anti-cheating penalty below — see "Anti-cheating seating")
                — ties broken by earliest candidate in order
             -> assign, or leave the student unassigned if no candidate
                survives the hard-constraint filter

This is deliberately not an optimization solver (no OR-Tools, no CP-SAT,
no ILP, no backtracking): it is not guaranteed to find a feasible seating
even when one exists — a different assignment order could occasionally
seat everyone where this greedy approach fails one student. That
trade-off is intentional for this milestone; choosing a real solver is
future work once the constraint model has proven itself.

When given an empty `ConstraintSet`, every candidate seat is always a
"zero violations" match, so the very first candidate in room-then-seat
order always wins — which is exactly `SequentialSeatingStrategy`'s own
fill order. `test_constraint_strategy.py::test_matches_sequential_strategy_when_there_are_no_constraints`
asserts this byte-for-byte.

Anti-cheating seating (this milestone): `ConstraintSeatingStrategy`'s own
*default* (`constraint_set=None`, as opposed to an explicit — even
empty — `ConstraintSet()`) no longer builds a `SeparateCoursesConstraint`.
That class still exists and is still fully tested
(`app/seating/constraints.py`) as a general-purpose, explicitly-opt-in
constraint — but its own effect (prefer that adjacent seats hold the
*same* course, i.e. each course seats as one contiguous block) is exactly
backwards from what an anti-cheating default needs, so it is no longer
what production seating actually uses. The default now does two things
instead, both in `app/seating/anti_cheating.py` (see that module's own
docstring for the full detail):

1. **Placement order**: `order_students_for_placement` interleaves the
   given students by course — always taking the next student from
   whichever course has the most students still waiting, ties broken by
   the smallest course_id — instead of processing one course's entire
   block before the next. This is what stops one course from claiming a
   long unbroken run of placement turns before another course gets one,
   for *any* number of courses (2, 3, 6, 50 — no course-count branching
   anywhere) and *any* distribution of course sizes (see
   `order_students_for_placement`'s own docstring for how a dominant
   course's turns taper off as its remaining count drops).
2. **Candidate scoring**: `same_course_penalty` replaces the old
   soft-constraint-violation count as the tie-breaking score among
   hard-constraint survivors. It scores a candidate seat purely against
   *the same course's* already-placed students (never a different
   course — mixing courses in adjacent seats is the goal, not a
   violation), weighing orthogonal same-course adjacency worst, diagonal
   adjacency next, then same-row/same-column concentration, then local
   density, then raw proximity — using only `SeatTopology`'s existing
   `same_row`/`same_column`/`is_adjacent`/`distance` methods, no second
   topology system.

Both are skipped entirely (falling back to the exact original
zero-violations-wins behavior) whenever fewer than two distinct courses
are present in `student_course_ids` — a single-course exam has no other
course to separate from, and applying anti-cheating scoring anyway would
just scatter that one exam's own students for no reason (see
"Single-course regression," `tests/services/test_constraint_seating_integration.py::test_constraint_and_sequential_strategies_agree_when_unconstrained`).

This is a deterministic heuristic, not a solver, and this module does not
claim it finds a globally optimal spatial arrangement — only that it
materially reduces same-course clustering relative to naive sequential/
course-blocked ordering (see `app/seating/quality_metrics.py`, a pure
test-only helper that measures exactly that, and is never used by
production code). An explicitly-supplied `ConstraintSet` (even an empty
one) bypasses all of this — see `__init__`'s own docstring.

Capacity semantics are untouched from `SequentialSeatingStrategy`:
`scheduled_allocation_shortage`, `physical_capacity_shortage`, and
`usable_capacity_shortage` (Milestone 10) are computed the same way, from
the same raw counts, regardless of how the constructive algorithm
actually placed students. A student going unassigned because every
remaining seat violated a hard constraint is a distinct fact — a
*constraint* shortfall, not a *capacity* one — and is reported only as an
additional entry in `warnings`, never by reinterpreting any shortage flag
(see docs/architecture.md).

Usable seats (Milestone 10): candidate seats are always drawn from
`topology.usable_positions()`, never `position_for_seat()` over a raw
`1..capacity` range — a blocked seat is never a seating candidate in the
first place, the same way an already-taken seat isn't (this strategy
already required a topology for every room, unlike sequential, so there
is no "topology unavailable" fallback path to reconcile here).

Topology (Milestone 8): this strategy no longer carries a hardcoded
room-code -> layout mapping. `get_strategy("constraint")` (called by
`SeatingService`) always supplies a real `RoomTopologyProvider` — in
production, `RepositoryRoomTopologyProvider`, which reads each room's own
configured `rows`/`columns` (see `app.domain.room.Room`). A room with no
configured topology causes `generate()` to raise `RoomTopologyMissingError`
for that exam, rather than guessing a layout for it — arbitrary room
codes are fully supported as long as their topology has actually been
configured.

Multi-course sessions (Milestone 9): `generate()` still takes a single
`exam` (the interface is unchanged), but `exam.course_id` only means
anything when every given student truly belongs to that one exam/course
— true for `SeatingService.generate()` (single-exam), not for
`SeatingService.generate_session()` (a session's students span several
courses). The optional `student_course_ids` constructor argument is the
escape hatch: when given, it overrides *how the default anti-cheating
course mapping is built* — the real,
per-student course ids the session service already looked up are used
directly, instead of deriving one course id for every student from
`exam.course_id`. `SeatingService.generate_session()` passes a
*representative* exam (the session's first) purely so this interface's
`exam.id` still has something real to reference in an error message;
none of its other fields are read when `student_course_ids` is given.
"""

from collections.abc import Mapping

from app.domain import Exam, GenerationStatus, Student, StudentSeatingContext
from app.seating.anti_cheating import order_students_for_placement, same_course_penalty
from app.seating.constraints import ConstraintSet, evaluate_constraints
from app.seating.models import RoomAllocation, SeatAssignmentRecord, SeatingResult
from app.seating.strategy import SeatingStrategy
from app.seating.topology import SeatAssignmentCandidate, SeatPosition, SeatTopology
from app.seating.topology_provider import RoomTopologyProvider


def _build_student_seating_contexts(exam: Exam, students: list[Student]) -> list[StudentSeatingContext]:
    """Every student in `students` is, today, registered for the same
    `exam.course_id` — this app does not support mixed-course exams yet.
    Building a real `StudentSeatingContext` per student (rather than
    reaching for `exam.course_id` directly wherever a constraint needs a
    course) keeps constraints decoupled from `Exam`'s shape and leaves
    room for a per-student attribute to actually vary later."""
    return [
        StudentSeatingContext(student_id=student.id, course_id=exam.course_id)
        for student in students
        if student.id is not None
    ]


class ConstraintSeatingStrategy(SeatingStrategy):
    name = "constraint"

    def __init__(
        self,
        topology_provider: RoomTopologyProvider | None = None,
        constraint_set: ConstraintSet | None = None,
        student_course_ids: Mapping[int, int] | None = None,
    ) -> None:
        """`topology_provider` is threaded in uniformly by
        `get_strategy()` via `SeatingStrategy`'s own base constructor (see
        `app/seating/strategy.py`) — `SeatingService` supplies a real,
        repository-backed one in production. `constraint_set` defaults to
        `None`, which signals `generate()` to run with the built-in
        anti-cheating default (course-interleaved placement order plus
        same-course spatial penalty scoring — see this module's docstring,
        "Anti-cheating seating") — see `student_course_ids` for where that
        default's course mapping comes from. Passing an explicit
        `ConstraintSet()` (rather than leaving it `None`) opts out of that
        default entirely and runs with the original boolean hard/soft
        constraint evaluation instead, exactly as before this milestone;
        when that's done, `student_course_ids` is ignored.

        `student_course_ids`, if given, is used as the default anti-
        cheating behavior's student_id -> course_id mapping directly,
        instead of deriving one course id for every student from
        `exam.course_id` (see this module's docstring — that derivation
        only makes sense for a single-exam generation)."""
        super().__init__(topology_provider=topology_provider)
        self._constraint_set = constraint_set
        self._student_course_ids = student_course_ids

    def generate(
        self,
        exam: Exam,
        students: list[Student],
        room_allocations: list[RoomAllocation],
    ) -> SeatingResult:
        room_ids = [ra.room_id for ra in room_allocations]
        if len(room_ids) != len(set(room_ids)):
            raise ValueError(f"Duplicate room allocation(s) for exam {exam.id}: room_ids={room_ids}")
        if self._topology_provider is None:
            raise ValueError(
                "ConstraintSeatingStrategy was constructed without a RoomTopologyProvider — "
                "constraint seating cannot determine seat adjacency without one."
            )

        registered_student_count = len(students)
        scheduled_student_count = sum(ra.allocated_students for ra in room_allocations)
        total_physical_capacity = sum(ra.capacity for ra in room_allocations)

        warnings: list[str] = []
        topologies: dict[int, SeatTopology] = {}
        candidate_seats: list[SeatPosition] = []
        total_usable_capacity = 0
        for ra in room_allocations:
            topology = self._topology_provider.get_topology(
                room_id=ra.room_id, room_code=ra.room_code, capacity=ra.capacity
            )
            topologies[ra.room_id] = topology
            usable_capacity = topology.usable_capacity
            total_usable_capacity += usable_capacity

            if ra.allocated_students > ra.capacity:
                warnings.append(
                    f"Room '{ra.room_code}' scheduled allocation ({ra.allocated_students}) exceeds its "
                    f"capacity ({ra.capacity}); capped at {ra.capacity} for this generation."
                )
            if usable_capacity < ra.capacity and ra.allocated_students > usable_capacity:
                warnings.append(
                    f"Room '{ra.room_code}' has {ra.capacity - usable_capacity} blocked seat(s); only "
                    f"{usable_capacity} of its {ra.capacity} physical seat(s) are usable, which is less "
                    f"than its scheduled allocation ({ra.allocated_students})."
                )

            target = min(ra.allocated_students, ra.capacity, usable_capacity)
            candidate_seats.extend(topology.usable_positions()[:target])

        available_capacity = len(candidate_seats)

        if registered_student_count > scheduled_student_count:
            warnings.append(
                f"{registered_student_count} student(s) registered but only {scheduled_student_count} "
                "seat(s) were scheduled across this exam's rooms."
            )
        elif registered_student_count < scheduled_student_count:
            warnings.append(
                f"Only {registered_student_count} student(s) registered; "
                f"{scheduled_student_count - registered_student_count} scheduled seat(s) will remain unused."
            )
        if registered_student_count > total_usable_capacity:
            if total_usable_capacity < total_physical_capacity:
                warnings.append(
                    f"{registered_student_count} student(s) registered but only {total_usable_capacity} usable "
                    f"seat(s) are available across this exam's rooms ({total_physical_capacity} physically "
                    "exist, but some are blocked)."
                )
            else:
                warnings.append(
                    f"{registered_student_count} student(s) registered but only {total_physical_capacity} "
                    "physical seat(s) exist across this exam's rooms."
                )

        # See this module's docstring ("Anti-cheating seating") for why
        # this branches on whether the caller supplied its own
        # ConstraintSet at all, not on anything about the students/rooms
        # themselves: an explicit ConstraintSet (even an empty one) opts
        # out of the anti-cheating default entirely and runs the original,
        # unmodified boolean hard/soft evaluation — this is what keeps
        # every existing constraint-model test byte-for-byte unchanged.
        using_default_constraint_set = self._constraint_set is None
        if using_default_constraint_set:
            constraint_set = ConstraintSet()
            if self._student_course_ids is not None:
                student_course_ids = dict(self._student_course_ids)
            else:
                contexts = _build_student_seating_contexts(exam, students)
                student_course_ids = {ctx.student_id: ctx.course_id for ctx in contexts}
            # Anti-cheating separation is meaningless with fewer than two
            # courses present — there is no "other course" to mix with,
            # and penalizing same-course adjacency in that case would
            # just scatter a single exam's own students for no reason
            # (see "Single-course regression" in this module's docstring).
            anti_cheating_enabled = len(set(student_course_ids.values())) >= 2
            placement_order = (
                order_students_for_placement(students, student_course_ids)
                if anti_cheating_enabled
                else students
            )
        else:
            constraint_set = self._constraint_set
            student_course_ids = {}
            anti_cheating_enabled = False
            placement_order = students

        remaining_seats = list(candidate_seats)
        placed: list[SeatAssignmentCandidate] = []
        assignments: list[SeatAssignmentRecord] = []
        unassigned_student_ids: list[int] = []
        constraint_blocked_count = 0

        for student in placement_order:
            assert student.id is not None
            had_remaining_seats = len(remaining_seats) > 0
            course_id = student_course_ids.get(student.id)

            best_candidate: SeatAssignmentCandidate | None = None
            best_index: int | None = None
            best_score: float | None = None
            for index, seat in enumerate(remaining_seats):
                tentative = SeatAssignmentCandidate(student_id=student.id, position=seat)
                evaluation = evaluate_constraints(constraint_set, [*placed, tentative])
                if not evaluation.satisfied:
                    continue  # a hard constraint rejects this seat outright
                if anti_cheating_enabled:
                    score = same_course_penalty(
                        seat, course_id, placed, student_course_ids, topologies[seat.room_id]
                    )
                else:
                    score = float(len(evaluation.soft_violations))
                if best_score is None or score < best_score:
                    best_candidate, best_index, best_score = tentative, index, score
                    if score == 0:
                        break  # cannot do better than zero

            if best_candidate is None or best_index is None:
                unassigned_student_ids.append(student.id)
                if had_remaining_seats:
                    constraint_blocked_count += 1
                continue

            placed.append(best_candidate)
            assignments.append(
                SeatAssignmentRecord(
                    student_id=student.id,
                    room_id=best_candidate.position.room_id,
                    seat_number=best_candidate.position.seat_number,
                )
            )
            remaining_seats.pop(best_index)

        if constraint_blocked_count > 0:
            warnings.append(
                f"{constraint_blocked_count} student(s) could not be seated because every remaining seat "
                "violated a hard constraint."
            )

        assigned_student_count = len(assignments)
        unassigned_student_count = len(unassigned_student_ids)

        # Same independent facts as SequentialSeatingStrategy, computed the
        # same way — see SeatingResult's docstring. A constraint-caused
        # unassignment is reported only via the warning above, never by
        # reinterpreting any of these flags (see this module's docstring).
        capacity_shortage = unassigned_student_count > 0
        scheduled_allocation_shortage = registered_student_count > scheduled_student_count
        physical_capacity_shortage = registered_student_count > total_physical_capacity
        usable_capacity_shortage = registered_student_count > total_usable_capacity

        if registered_student_count == 0:
            status = GenerationStatus.SUCCESS
            warnings.append("No students are registered for this exam's course.")
        elif unassigned_student_count == 0:
            status = GenerationStatus.SUCCESS
        elif assigned_student_count == 0:
            status = GenerationStatus.FAILED
        else:
            status = GenerationStatus.PARTIAL

        return SeatingResult(
            status=status,
            registered_student_count=registered_student_count,
            scheduled_student_count=scheduled_student_count,
            total_physical_capacity=total_physical_capacity,
            total_usable_capacity=total_usable_capacity,
            available_capacity=available_capacity,
            assigned_student_count=assigned_student_count,
            unassigned_student_count=unassigned_student_count,
            capacity_shortage=capacity_shortage,
            scheduled_allocation_shortage=scheduled_allocation_shortage,
            physical_capacity_shortage=physical_capacity_shortage,
            usable_capacity_shortage=usable_capacity_shortage,
            assignments=assignments,
            unassigned_student_ids=unassigned_student_ids,
            warnings=warnings,
        )
