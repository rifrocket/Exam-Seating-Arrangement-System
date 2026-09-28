"""ConstraintSeatingStrategy: the first strategy built on the Milestone 6
constraint foundation (`app.seating.constraints`, `app.seating.topology`).

Algorithm — a deterministic constructive greedy placement, not a solver:

    students (given order)
        -> for each student, in order:
             candidate seats = remaining seats, in room-then-seat-number order
             -> evaluate hard constraints for each candidate
             -> keep only candidates with zero hard-constraint violations
             -> among those, prefer the one with the fewest soft-constraint
                violations (ties broken by earliest candidate in order)
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

Capacity semantics are untouched from `SequentialSeatingStrategy`:
`scheduled_allocation_shortage` and `physical_capacity_shortage` are
computed the same way, from the same raw counts, regardless of how the
constructive algorithm actually placed students. A student going
unassigned because every remaining seat violated a hard constraint is a
distinct fact — a *constraint* shortfall, not a *capacity* one — and is
reported only as an additional entry in `warnings`, never by
reinterpreting either shortage flag (see docs/architecture.md).

Topology (Milestone 8): this strategy no longer carries a hardcoded
room-code -> layout mapping. `get_strategy("constraint")` (called by
`SeatingService`) always supplies a real `RoomTopologyProvider` — in
production, `RepositoryRoomTopologyProvider`, which reads each room's own
configured `rows`/`columns` (see `app.domain.room.Room`). A room with no
configured topology causes `generate()` to raise `RoomTopologyMissingError`
for that exam, rather than guessing a layout for it — arbitrary room
codes are fully supported as long as their topology has actually been
configured.
"""

from app.domain import Exam, GenerationStatus, Student, StudentSeatingContext
from app.seating.constraints import ConstraintSet, SeparateCoursesConstraint, evaluate_constraints
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
    ) -> None:
        """`topology_provider` is threaded in uniformly by
        `get_strategy()` via `SeatingStrategy`'s own base constructor (see
        `app/seating/strategy.py`) — `SeatingService` supplies a real,
        repository-backed one in production. `constraint_set` defaults to
        `None`, which signals `generate()` to build a default set itself
        (a single `SeparateCoursesConstraint` derived from the exam being
        seated — see `_build_student_seating_contexts`). Passing an
        explicit `ConstraintSet()` (rather than leaving it `None`) opts
        out of that default and runs with genuinely zero constraints
        instead."""
        super().__init__(topology_provider=topology_provider)
        self._constraint_set = constraint_set

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
        for ra in room_allocations:
            topology = self._topology_provider.get_topology(
                room_id=ra.room_id, room_code=ra.room_code, capacity=ra.capacity
            )
            topologies[ra.room_id] = topology

            target = ra.allocated_students
            if ra.allocated_students > ra.capacity:
                target = ra.capacity
                warnings.append(
                    f"Room '{ra.room_code}' scheduled allocation ({ra.allocated_students}) exceeds its "
                    f"capacity ({ra.capacity}); capped at {ra.capacity} for this generation."
                )
            for seat_number in range(1, target + 1):
                candidate_seats.append(topology.position_for_seat(seat_number))

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

        constraint_set = self._constraint_set
        if constraint_set is None:
            contexts = _build_student_seating_contexts(exam, students)
            student_course_ids = {ctx.student_id: ctx.course_id for ctx in contexts}
            constraint_set = ConstraintSet(
                soft_constraints=(
                    (SeparateCoursesConstraint(student_course_ids=student_course_ids, topologies=topologies),)
                    if student_course_ids
                    else ()
                ),
            )

        remaining_seats = list(candidate_seats)
        placed: list[SeatAssignmentCandidate] = []
        assignments: list[SeatAssignmentRecord] = []
        unassigned_student_ids: list[int] = []
        constraint_blocked_count = 0

        for student in students:
            assert student.id is not None
            had_remaining_seats = len(remaining_seats) > 0

            best_candidate: SeatAssignmentCandidate | None = None
            best_index: int | None = None
            best_violation_count: int | None = None
            for index, seat in enumerate(remaining_seats):
                tentative = SeatAssignmentCandidate(student_id=student.id, position=seat)
                evaluation = evaluate_constraints(constraint_set, [*placed, tentative])
                if not evaluation.satisfied:
                    continue  # a hard constraint rejects this seat outright
                violation_count = len(evaluation.soft_violations)
                if best_violation_count is None or violation_count < best_violation_count:
                    best_candidate, best_index, best_violation_count = tentative, index, violation_count
                    if violation_count == 0:
                        break  # cannot do better than zero soft violations

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

        # Same three independent facts as SequentialSeatingStrategy, computed
        # the same way — see SeatingResult's docstring. A constraint-caused
        # unassignment is reported only via the warning above, never by
        # reinterpreting these two flags (see this module's docstring).
        capacity_shortage = unassigned_student_count > 0
        scheduled_allocation_shortage = registered_student_count > scheduled_student_count
        physical_capacity_shortage = registered_student_count > total_physical_capacity

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
            available_capacity=available_capacity,
            assigned_student_count=assigned_student_count,
            unassigned_student_count=unassigned_student_count,
            capacity_shortage=capacity_shortage,
            scheduled_allocation_shortage=scheduled_allocation_shortage,
            physical_capacity_shortage=physical_capacity_shortage,
            assignments=assignments,
            unassigned_student_ids=unassigned_student_ids,
            warnings=warnings,
        )
