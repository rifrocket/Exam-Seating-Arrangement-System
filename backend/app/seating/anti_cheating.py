"""Deterministic, topology-aware anti-cheating heuristics used by
`ConstraintSeatingStrategy`'s default (unconfigured) constraint set —
see that module's own docstring for how these two pieces are wired into
the greedy placement loop.

Two independent, composable pieces:

1. `order_students_for_placement` decides what *order* students are
   handed to the greedy placement loop in. Feeding the loop one course at
   a time (even with perfect per-seat scoring) lets an early course claim
   a long unbroken run of placement turns before any other course gets a
   turn at all, which is exactly how contiguous same-course blocks form
   even when every individual seat choice "looks" locally reasonable.
   Interleaving by remaining population — always taking the next student
   from whichever course still has the most students waiting — spreads
   each course's turns out over the whole run instead, for any number of
   courses and any distribution of course sizes, with no course-count-
   specific logic anywhere.

2. `same_course_penalty` scores one candidate seat against the positions
   already held by *the same course* as the student being placed, so the
   greedy loop can prefer whichever surviving candidate (i.e. one that
   already passed every hard constraint) is least likely to let that
   course cluster. It never compares a student against a different
   course's students — mixing courses in adjacent seats is the anti-
   cheating goal, not something to penalize.

Both are pure functions of their arguments: no database, no HTTP, no
randomness, no global state. Nothing here is a solver — this is a
deterministic constructive heuristic, and does not guarantee a globally
optimal arrangement (see docs/architecture.md's "Anti-cheating seating"
section for the full discussion of this limitation, and
`app/seating/quality_metrics.py` for the pure, test-only measurements
used to check that this heuristic materially improves on naive ordering).

Nothing in this module imports FastAPI, SQLAlchemy, HTTP, the filesystem,
ReportLab, or a repository.
"""

import math
from collections.abc import Mapping, Sequence

from app.domain import Student
from app.seating.topology import SeatAssignmentCandidate, SeatPosition, SeatTopology

# Relative severities, not calibrated probabilities or a tuned model.
# Each tier's weight is chosen to dominate every lower tier combined for
# any room size this application targets (a handful of rows/columns, not
# stadium seating) — so a candidate with fewer orthogonal-adjacent
# same-course neighbors always outranks one with more, regardless of the
# other terms, and only within a tied orthogonal/diagonal count do the
# row/column/density/proximity terms actually decide anything. This is a
# deliberate lexicographic-like ordering expressed as arithmetic, not a
# solver and not an attempt at a globally optimal weighting.
ORTHOGONAL_ADJACENT_WEIGHT = 100.0
DIAGONAL_ADJACENT_WEIGHT = 50.0
SAME_ROW_WEIGHT = 5.0
SAME_COLUMN_WEIGHT = 5.0
LOCAL_DENSITY_WEIGHT = 2.0
PROXIMITY_WEIGHT = 1.0

# A same-course neighbor within this many seat-units counts toward local
# density (a loose "cluster" measure, independent of strict adjacency).
LOCAL_DENSITY_RADIUS = 2.0

# Below this distance from the nearest already-placed same-course
# student, a candidate is charged a proportional proximity penalty (e.g.
# a same-course student 1.0 seat-units away costs more than one 1.8 away,
# even when neither is technically "adjacent" by `is_adjacent`'s 8-cell
# definition) — this is what lets the scorer prefer *more* separation
# between same-course students, not just "not adjacent."
SEPARATION_TARGET = 2.0


def order_students_for_placement(
    students: Sequence[Student], student_course_ids: Mapping[int, int]
) -> list[Student]:
    """Group `students` by course (preserving each course's own relative
    order — e.g. still ascending student_number within a course, if that's
    how `students` was already sorted), then interleave them: on every
    turn, take the next student from whichever course currently has the
    most students still waiting, ties broken by the smallest course_id so
    the result is fully deterministic. For a single course (or an empty
    list), this returns the students unchanged — there's nothing to
    interleave.

    This works identically for 2, 3, 6, or 50 courses, and for wildly
    unequal course sizes: a 40-student course simply keeps winning the
    "most remaining" tiebreak until its remaining count drops to meet the
    next-largest course, at which point they start alternating — no
    course-count branching, no assumption of equal sizes anywhere."""
    groups: dict[int, list[Student]] = {}
    for student in students:
        assert student.id is not None
        course_id = student_course_ids[student.id]
        groups.setdefault(course_id, []).append(student)

    if len(groups) <= 1:
        return list(students)

    counts = {course_id: len(members) for course_id, members in groups.items()}
    cursors = dict.fromkeys(groups, 0)
    ordered: list[Student] = []
    for _ in range(len(students)):
        remaining_course_ids = [cid for cid, cursor in cursors.items() if cursor < counts[cid]]
        next_course_id = max(remaining_course_ids, key=lambda cid: (counts[cid] - cursors[cid], -cid))
        ordered.append(groups[next_course_id][cursors[next_course_id]])
        cursors[next_course_id] += 1
    return ordered


def same_course_penalty(
    candidate: SeatPosition,
    course_id: int,
    placed: Sequence[SeatAssignmentCandidate],
    student_course_ids: Mapping[int, int],
    topology: SeatTopology,
) -> float:
    """How much `candidate` would cluster this course, given who from the
    same course is already seated. Zero when no same-course student has
    been placed yet (including whenever there is only one course
    altogether — nothing to separate from, see
    `ConstraintSeatingStrategy`'s own docstring on why single-course
    generations must never trigger this at all). Only ever compares
    `candidate` against *this course's own* already-placed positions —
    a different course nearby is never penalized, since mixing courses is
    the goal, not the problem."""
    same_course_positions = [
        entry.position for entry in placed if student_course_ids.get(entry.student_id) == course_id
    ]
    if not same_course_positions:
        return 0.0

    orthogonal_adjacent = 0
    diagonal_adjacent = 0
    same_row_count = 0
    same_column_count = 0
    local_density = 0
    nearest_distance = math.inf

    for other in same_course_positions:
        in_row = topology.same_row(candidate, other)
        in_column = topology.same_column(candidate, other)
        if in_row:
            same_row_count += 1
        if in_column:
            same_column_count += 1
        if topology.is_adjacent(candidate, other):
            if in_row or in_column:
                orthogonal_adjacent += 1
            else:
                diagonal_adjacent += 1
        seat_distance = topology.distance(candidate, other)
        if seat_distance <= LOCAL_DENSITY_RADIUS:
            local_density += 1
        nearest_distance = min(nearest_distance, seat_distance)

    proximity_penalty = (
        max(0.0, SEPARATION_TARGET - nearest_distance) if math.isfinite(nearest_distance) else 0.0
    )

    return (
        ORTHOGONAL_ADJACENT_WEIGHT * orthogonal_adjacent
        + DIAGONAL_ADJACENT_WEIGHT * diagonal_adjacent
        + SAME_ROW_WEIGHT * same_row_count
        + SAME_COLUMN_WEIGHT * same_column_count
        + LOCAL_DENSITY_WEIGHT * local_density
        + PROXIMITY_WEIGHT * proximity_penalty
    )
