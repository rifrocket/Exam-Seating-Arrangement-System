"""Constraint model — the foundation a future `ConstraintSeatingStrategy`
will build on. Nothing here is wired into `SeatingEngine` or any strategy
yet; this module only defines what a constraint *is* and how a proposed
seating is checked against a set of them.

Hard vs soft, deliberately as two distinct types rather than one type with
a severity flag: a hard constraint is a pass/fail gate on the whole
proposed seating (any violation makes the seating unacceptable); a soft
constraint is a preference a future strategy should try to satisfy but may
trade off against others. Keeping them as separate types means a future
solver can iterate "all hard constraints" and "all soft constraints"
without a runtime severity check, and a constraint author can't
accidentally leave severity unset.

This is deliberately not a generic rule language: adding a new constraint
means writing one small class implementing `HardConstraint` or
`SoftConstraint`, the same way adding a new `SeatingStrategy` means writing
one small class — no rule DSL, no config schema, no registry beyond
whatever list a future strategy is constructed with.

Nothing in this module imports FastAPI, SQLAlchemy, HTTP, the filesystem,
ReportLab, or a repository. `SeparateCoursesConstraint` takes a plain
`Mapping[int, int]` of student_id -> course_id supplied by whatever calls
it — it does not look courses up itself. This is *not* mixed-course
seating support: nothing here changes how `Exam`/`ExamRoom`/`SeatingService`
allocate a single course's students into rooms.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.seating.topology import SeatAssignmentCandidate, SeatTopology


class Constraint(ABC):
    """Common shape both hard and soft constraints share: check a
    proposed (student_id -> position) seating and explain yourself in
    words if it fails."""

    @abstractmethod
    def is_satisfied(self, assignments: Sequence[SeatAssignmentCandidate]) -> bool: ...

    @abstractmethod
    def describe(self) -> str:
        """A short, human-readable explanation of what this constraint
        requires — used to report a violation, not to identify the
        constraint programmatically."""
        ...


class HardConstraint(Constraint):
    """Must never be violated. A seating that violates any hard
    constraint is not an acceptable seating at all."""


class SoftConstraint(Constraint):
    """Should be satisfied when possible, but a seating that violates one
    is still an acceptable seating — just not a preferred one."""


@dataclass(frozen=True)
class ConstraintSet:
    """The constraints a future `ConstraintSeatingStrategy` run is asked to
    respect, split by severity exactly as the strategy needs to treat
    them differently (reject vs. prefer-against)."""

    hard_constraints: tuple[HardConstraint, ...] = ()
    soft_constraints: tuple[SoftConstraint, ...] = ()


@dataclass(frozen=True)
class ConstraintViolation:
    constraint: Constraint
    is_hard: bool
    description: str


@dataclass(frozen=True)
class ConstraintEvaluation:
    """Result of checking one proposed seating against a `ConstraintSet`.

    `satisfied` answers only "is this seating acceptable at all" — true
    iff there are no hard-constraint violations. A soft-constraint
    violation never flips `satisfied` to False; it only appears in
    `violations` (via `soft_violations`) for a future strategy to weigh
    when choosing between multiple otherwise-acceptable seatings.
    """

    satisfied: bool
    violations: tuple[ConstraintViolation, ...]

    @property
    def hard_violations(self) -> tuple[ConstraintViolation, ...]:
        return tuple(v for v in self.violations if v.is_hard)

    @property
    def soft_violations(self) -> tuple[ConstraintViolation, ...]:
        return tuple(v for v in self.violations if not v.is_hard)


def evaluate_constraints(
    constraint_set: ConstraintSet,
    assignments: Sequence[SeatAssignmentCandidate],
) -> ConstraintEvaluation:
    """Pure function: no database, no HTTP, no knowledge of how
    `assignments` was produced. A future `ConstraintSeatingStrategy` calls
    this once per candidate seating it considers."""
    violations: list[ConstraintViolation] = []
    for hard in constraint_set.hard_constraints:
        if not hard.is_satisfied(assignments):
            violations.append(ConstraintViolation(constraint=hard, is_hard=True, description=hard.describe()))
    for soft in constraint_set.soft_constraints:
        if not soft.is_satisfied(assignments):
            violations.append(ConstraintViolation(constraint=soft, is_hard=False, description=soft.describe()))

    satisfied = not any(v.is_hard for v in violations)
    return ConstraintEvaluation(satisfied=satisfied, violations=tuple(violations))


def _find_candidate(assignments: Sequence[SeatAssignmentCandidate], student_id: int) -> SeatAssignmentCandidate | None:
    return next((a for a in assignments if a.student_id == student_id), None)


class StudentsNotAdjacentConstraint(HardConstraint):
    """Example hard constraint: two specific students must never end up
    in adjacent seats (e.g. known collaborators, or students who must be
    kept apart for any other reason a future admin workflow decides)."""

    def __init__(self, student_a_id: int, student_b_id: int, topology: SeatTopology) -> None:
        self._student_a_id = student_a_id
        self._student_b_id = student_b_id
        self._topology = topology

    def is_satisfied(self, assignments: Sequence[SeatAssignmentCandidate]) -> bool:
        a = _find_candidate(assignments, self._student_a_id)
        b = _find_candidate(assignments, self._student_b_id)
        if a is None or b is None:
            return True  # nothing to violate until both are actually seated
        return not self._topology.is_adjacent(a.position, b.position)

    def describe(self) -> str:
        return f"Student {self._student_a_id} and student {self._student_b_id} must not sit adjacent to each other."


class SeparateCoursesConstraint(SoftConstraint):
    """Example soft constraint: prefer that adjacent seats are not held by
    students from different courses (i.e. prefer each course to seat as a
    contiguous block) — satisfied when no two *currently seated* adjacent
    students belong to different courses. `student_course_ids` is supplied
    by the caller; this constraint never looks a course up itself."""

    def __init__(self, student_course_ids: Mapping[int, int], topology: SeatTopology) -> None:
        self._student_course_ids = student_course_ids
        self._topology = topology

    def is_satisfied(self, assignments: Sequence[SeatAssignmentCandidate]) -> bool:
        for i, a in enumerate(assignments):
            for b in assignments[i + 1 :]:
                if not self._topology.is_adjacent(a.position, b.position):
                    continue
                course_a = self._student_course_ids.get(a.student_id)
                course_b = self._student_course_ids.get(b.student_id)
                if course_a is not None and course_b is not None and course_a != course_b:
                    return False
        return True

    def describe(self) -> str:
        return "Adjacent seats should preferably hold students from the same course."
