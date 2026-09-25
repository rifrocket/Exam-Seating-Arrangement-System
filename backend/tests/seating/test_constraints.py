"""Pure tests for the constraint model foundation — no DB, no HTTP, no
strategy involved. All data synthetic."""

from app.seating.constraints import (
    ConstraintSet,
    SeparateCoursesConstraint,
    StudentsNotAdjacentConstraint,
    evaluate_constraints,
)
from app.seating.topology import RectangularRoomTopology, SeatAssignmentCandidate, SeatTopology


def _layout() -> RectangularRoomTopology:
    return RectangularRoomTopology(room_id=1, rows=2, columns=5)


def _topologies(layout: RectangularRoomTopology) -> dict[int, SeatTopology]:
    return {layout.room_id: layout}


def _candidate(layout: RectangularRoomTopology, student_id: int, seat_number: int) -> SeatAssignmentCandidate:
    return SeatAssignmentCandidate(student_id=student_id, position=layout.position_for_seat(seat_number))


def test_hard_constraint_satisfied_when_students_not_adjacent() -> None:
    layout = _layout()
    constraint = StudentsNotAdjacentConstraint(student_a_id=1, student_b_id=2, topologies=_topologies(layout))
    assignments = [_candidate(layout, 1, 1), _candidate(layout, 2, 10)]  # opposite corners

    assert constraint.is_satisfied(assignments) is True


def test_hard_constraint_violated_when_students_adjacent() -> None:
    layout = _layout()
    constraint = StudentsNotAdjacentConstraint(student_a_id=1, student_b_id=2, topologies=_topologies(layout))
    assignments = [_candidate(layout, 1, 1), _candidate(layout, 2, 2)]  # neighboring seats

    assert constraint.is_satisfied(assignments) is False


def test_hard_constraint_is_vacuously_satisfied_before_both_students_are_seated() -> None:
    layout = _layout()
    constraint = StudentsNotAdjacentConstraint(student_a_id=1, student_b_id=2, topologies=_topologies(layout))
    assignments = [_candidate(layout, 1, 1)]  # student 2 not placed yet

    assert constraint.is_satisfied(assignments) is True


def test_soft_constraint_satisfied_when_adjacent_students_share_a_course() -> None:
    layout = _layout()
    constraint = SeparateCoursesConstraint(student_course_ids={1: 100, 2: 100}, topologies=_topologies(layout))
    assignments = [_candidate(layout, 1, 1), _candidate(layout, 2, 2)]

    assert constraint.is_satisfied(assignments) is True


def test_soft_constraint_violated_when_adjacent_students_differ_in_course() -> None:
    layout = _layout()
    constraint = SeparateCoursesConstraint(student_course_ids={1: 100, 2: 200}, topologies=_topologies(layout))
    assignments = [_candidate(layout, 1, 1), _candidate(layout, 2, 2)]

    assert constraint.is_satisfied(assignments) is False


def test_soft_constraint_satisfied_when_different_course_students_are_not_adjacent() -> None:
    layout = _layout()
    constraint = SeparateCoursesConstraint(student_course_ids={1: 100, 2: 200}, topologies=_topologies(layout))
    assignments = [_candidate(layout, 1, 1), _candidate(layout, 2, 10)]

    assert constraint.is_satisfied(assignments) is True


def test_evaluate_constraints_reports_satisfied_with_no_violations() -> None:
    layout = _layout()
    hard = StudentsNotAdjacentConstraint(student_a_id=1, student_b_id=2, topologies=_topologies(layout))
    constraint_set = ConstraintSet(hard_constraints=(hard,))
    assignments = [_candidate(layout, 1, 1), _candidate(layout, 2, 10)]

    evaluation = evaluate_constraints(constraint_set, assignments)

    assert evaluation.satisfied is True
    assert evaluation.violations == ()


def test_evaluate_constraints_reports_hard_violation_and_unsatisfied() -> None:
    layout = _layout()
    hard = StudentsNotAdjacentConstraint(student_a_id=1, student_b_id=2, topologies=_topologies(layout))
    constraint_set = ConstraintSet(hard_constraints=(hard,))
    assignments = [_candidate(layout, 1, 1), _candidate(layout, 2, 2)]

    evaluation = evaluate_constraints(constraint_set, assignments)

    assert evaluation.satisfied is False
    assert len(evaluation.hard_violations) == 1
    assert evaluation.soft_violations == ()
    assert "must not sit adjacent" in evaluation.hard_violations[0].description


def test_evaluate_constraints_soft_violation_never_flips_satisfied() -> None:
    """A soft-constraint violation must still be reported, but must not
    make the whole seating unacceptable — that's exactly what
    distinguishes it from a hard constraint."""
    layout = _layout()
    soft = SeparateCoursesConstraint(student_course_ids={1: 100, 2: 200}, topologies=_topologies(layout))
    constraint_set = ConstraintSet(soft_constraints=(soft,))
    assignments = [_candidate(layout, 1, 1), _candidate(layout, 2, 2)]

    evaluation = evaluate_constraints(constraint_set, assignments)

    assert evaluation.satisfied is True
    assert len(evaluation.soft_violations) == 1
    assert evaluation.hard_violations == ()


def test_evaluate_constraints_with_multiple_hard_and_soft_constraints() -> None:
    layout = _layout()
    hard_ok = StudentsNotAdjacentConstraint(student_a_id=1, student_b_id=2, topologies=_topologies(layout))
    hard_violated = StudentsNotAdjacentConstraint(student_a_id=3, student_b_id=4, topologies=_topologies(layout))
    soft_violated = SeparateCoursesConstraint(student_course_ids={3: 100, 4: 200}, topologies=_topologies(layout))
    constraint_set = ConstraintSet(
        hard_constraints=(hard_ok, hard_violated),
        soft_constraints=(soft_violated,),
    )
    assignments = [
        _candidate(layout, 1, 1),
        _candidate(layout, 2, 10),  # far apart: satisfies hard_ok
        _candidate(layout, 3, 3),
        _candidate(layout, 4, 4),  # adjacent: violates hard_violated and soft_violated
    ]

    evaluation = evaluate_constraints(constraint_set, assignments)

    assert evaluation.satisfied is False  # one hard violation is enough
    assert len(evaluation.hard_violations) == 1
    assert len(evaluation.soft_violations) == 1
