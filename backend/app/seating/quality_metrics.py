"""Pure, read-only metrics for evaluating a *finished* seating's spatial
anti-cheating quality. Used by tests only — nothing in `app/api/` or
`app/services/` imports this module, and nothing here influences a
strategy's own placement decisions. It exists purely so a test can assert
"this arrangement is materially better distributed than naive sequential
ordering" without hand-counting adjacency pairs inline in every test.

What each measurement means, exactly:

- `same_course_adjacent_pairs`: the number of (student, student) pairs,
  same course, same room, whose seats are adjacent under
  `SeatTopology.is_adjacent` (any of the 8 surrounding cells) — the
  direct "close enough to plausibly copy off the seat next to you"
  measure.
- `same_course_diagonal_pairs`: the subset of the above pair count whose
  seats are diagonal neighbors specifically (not sharing a row or
  column). Included within `same_course_adjacent_pairs`, broken out
  separately because a diagonal neighbor is a different (lesser, but
  non-zero) risk than a direct orthogonal one.
- `same_course_pair_count`: the number of (student, student) pairs, same
  course, same room, within `anti_cheating.LOCAL_DENSITY_RADIUS` seat-
  units of each other — a looser "local clustering" measure, independent
  of strict adjacency (two same-course students two seats apart in the
  same row are not "adjacent" but do count here).
- `row_distribution` / `column_distribution`: for each room, how many
  students of each course occupy each row / column — used to assert a
  course is spread across multiple rows/columns rather than piled into
  one.

This module does not define a single combined "score," does not claim
any arrangement is globally optimal, and is never used to accept or
reject a generation — only to compare two already-produced seatings
against each other in a test.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.seating.anti_cheating import LOCAL_DENSITY_RADIUS
from app.seating.topology import SeatAssignmentCandidate, SeatTopology


@dataclass(frozen=True)
class SeatingQualityReport:
    same_course_adjacent_pairs: int
    same_course_diagonal_pairs: int
    same_course_pair_count: int
    # room_id -> row/column index -> course_id -> count of students of
    # that course in that row/column of that room.
    row_distribution: dict[int, dict[int, dict[int, int]]] = field(default_factory=dict)
    column_distribution: dict[int, dict[int, dict[int, int]]] = field(default_factory=dict)


def evaluate_seating_quality(
    assignments: Sequence[SeatAssignmentCandidate],
    student_course_ids: Mapping[int, int],
    topologies: Mapping[int, SeatTopology],
) -> SeatingQualityReport:
    """`assignments` is the finished, already-decided seating (as
    `SeatAssignmentCandidate`s — student_id + `SeatPosition`), not a
    candidate being considered. `topologies` is keyed by room_id, the
    same shape `ConstraintSeatingStrategy` already builds internally."""
    row_distribution: dict[int, dict[int, dict[int, int]]] = {}
    column_distribution: dict[int, dict[int, dict[int, int]]] = {}
    for entry in assignments:
        course_id = student_course_ids.get(entry.student_id)
        position = entry.position
        room_rows = row_distribution.setdefault(position.room_id, {})
        room_rows.setdefault(position.row, {}).setdefault(course_id, 0)
        room_rows[position.row][course_id] += 1
        room_columns = column_distribution.setdefault(position.room_id, {})
        room_columns.setdefault(position.column, {}).setdefault(course_id, 0)
        room_columns[position.column][course_id] += 1

    same_course_adjacent_pairs = 0
    same_course_diagonal_pairs = 0
    same_course_pair_count = 0
    for i, a in enumerate(assignments):
        course_a = student_course_ids.get(a.student_id)
        topology = topologies.get(a.position.room_id)
        if topology is None or course_a is None:
            continue
        for b in assignments[i + 1 :]:
            if a.position.room_id != b.position.room_id:
                continue
            course_b = student_course_ids.get(b.student_id)
            if course_b is None or course_a != course_b:
                continue
            in_row = topology.same_row(a.position, b.position)
            in_column = topology.same_column(a.position, b.position)
            if topology.is_adjacent(a.position, b.position):
                same_course_adjacent_pairs += 1
                if not in_row and not in_column:
                    same_course_diagonal_pairs += 1
            if topology.distance(a.position, b.position) <= LOCAL_DENSITY_RADIUS:
                same_course_pair_count += 1

    return SeatingQualityReport(
        same_course_adjacent_pairs=same_course_adjacent_pairs,
        same_course_diagonal_pairs=same_course_diagonal_pairs,
        same_course_pair_count=same_course_pair_count,
        row_distribution=row_distribution,
        column_distribution=column_distribution,
    )
