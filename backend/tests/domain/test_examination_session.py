"""Pure tests for ExaminationSession construction/validation and
participant-building — no DB, no HTTP, no repositories. All data
synthetic."""

from datetime import date

import pytest

from app.domain import Exam, ExamRoomAllocation, Student
from app.domain.examination_session import (
    ConflictingRoomAllocationError,
    DuplicateStudentInSessionError,
    IncompatibleExamScheduleError,
    build_examination_session,
    build_session_participants,
    validate_no_conflicting_room_usage,
)

DATE = date(2026, 10, 2)
TIME_SLOT = "09:00-11:00"


def _exam(exam_id: int, course_id: int, exam_date: date = DATE, time_slot: str = TIME_SLOT) -> Exam:
    return Exam(
        id=exam_id,
        course_id=course_id,
        exam_date=exam_date,
        time_slot=time_slot,
        expected_student_count=10,
        day_label="Friday",
    )


def _student(student_id: int) -> Student:
    return Student(id=student_id, student_number=str(1000 + student_id), full_name=f"Student {student_id}")


# --- single exam ---------------------------------------------------------


def test_single_exam_is_a_valid_session() -> None:
    exam = _exam(exam_id=1, course_id=10)

    session = build_examination_session([exam])

    assert session.exam_ids == [1]
    assert session.exam_date == DATE
    assert session.time_slot == TIME_SLOT


# --- multiple compatible exams -------------------------------------------


def test_multiple_exams_with_same_date_and_time_form_a_valid_session() -> None:
    cs101 = _exam(exam_id=1, course_id=10)
    math101 = _exam(exam_id=2, course_id=20)

    session = build_examination_session([cs101, math101])

    assert session.exam_ids == [1, 2]
    assert session.exam_date == DATE
    assert session.time_slot == TIME_SLOT


# --- incompatible schedules -----------------------------------------------


def test_different_dates_are_rejected() -> None:
    cs101 = _exam(exam_id=1, course_id=10, exam_date=date(2026, 10, 2))
    math101 = _exam(exam_id=2, course_id=20, exam_date=date(2026, 10, 3))

    with pytest.raises(IncompatibleExamScheduleError):
        build_examination_session([cs101, math101])


def test_different_time_slots_are_rejected() -> None:
    cs101 = _exam(exam_id=1, course_id=10, time_slot="09:00-11:00")
    math101 = _exam(exam_id=2, course_id=20, time_slot="13:00-15:00")

    with pytest.raises(IncompatibleExamScheduleError):
        build_examination_session([cs101, math101])


def test_empty_exam_list_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one exam"):
        build_examination_session([])


# --- participant construction ---------------------------------------------


def test_participants_retain_student_id_and_course_id() -> None:
    cs101 = _exam(exam_id=1, course_id=10)
    math101 = _exam(exam_id=2, course_id=20)
    session = build_examination_session([cs101, math101])

    participants = build_session_participants(
        session,
        students_by_exam_id={1: [_student(1), _student(2)], 2: [_student(3)]},
        course_id_by_exam_id={1: 10, 2: 20},
    )

    by_student = {p.student_id: p.course_id for p in participants}
    assert by_student == {1: 10, 2: 10, 3: 20}


def test_duplicate_student_across_exams_is_rejected() -> None:
    cs101 = _exam(exam_id=1, course_id=10)
    math101 = _exam(exam_id=2, course_id=20)
    session = build_examination_session([cs101, math101])

    shared_student = _student(1)
    with pytest.raises(DuplicateStudentInSessionError):
        build_session_participants(
            session,
            students_by_exam_id={1: [shared_student], 2: [shared_student]},
            course_id_by_exam_id={1: 10, 2: 20},
        )


def test_participant_count_matches_total_registrations_when_no_duplicates() -> None:
    cs101 = _exam(exam_id=1, course_id=10)
    session = build_examination_session([cs101])

    participants = build_session_participants(
        session,
        students_by_exam_id={1: [_student(1), _student(2), _student(3)]},
        course_id_by_exam_id={1: 10},
    )

    assert len(participants) == 3


# --- room validation --------------------------------------------------------


def _allocation(exam_id: int, room_id: int, allocated_students: int, room_capacity: int) -> ExamRoomAllocation:
    return ExamRoomAllocation(
        exam_id=exam_id, room_id=room_id, allocated_students=allocated_students, room_capacity=room_capacity
    )


def test_disjoint_room_usage_is_valid() -> None:
    validate_no_conflicting_room_usage(
        [
            _allocation(1, 101, 10, 10),
            _allocation(1, 102, 10, 10),
            _allocation(2, 201, 10, 10),
        ]
    )  # does not raise


def test_shared_room_within_combined_capacity_is_valid() -> None:
    """The exact manual-acceptance scenario: two exams share one 20-seat
    room, 10 seats allocated to each — 10 + 10 == 20, so it fits exactly."""
    validate_no_conflicting_room_usage(
        [
            _allocation(1, 401, 10, 20),
            _allocation(2, 401, 10, 20),
        ]
    )  # does not raise


def test_shared_room_exceeding_combined_capacity_is_rejected() -> None:
    with pytest.raises(ConflictingRoomAllocationError):
        validate_no_conflicting_room_usage(
            [
                _allocation(1, 401, 15, 20),
                _allocation(2, 401, 10, 20),  # 15 + 10 = 25 > 20
            ]
        )


def test_room_used_by_only_one_exam_is_never_a_conflict_regardless_of_allocation() -> None:
    """Even an over-allocated single-exam room (already a SequentialSeatingStrategy
    warning case, not a session concern) is not this function's job to flag."""
    validate_no_conflicting_room_usage([_allocation(1, 101, 999, 10)])  # does not raise
