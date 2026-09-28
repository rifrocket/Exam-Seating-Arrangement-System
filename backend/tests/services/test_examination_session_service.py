"""Service-level tests: exercise ExaminationSessionService against a real
(in-memory) database through the concrete repositories, but never through
HTTP. All data here is synthetic.
"""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.db.repositories import (
    SqlAlchemyCourseRepository,
    SqlAlchemyExaminationSessionRepository,
    SqlAlchemyExamRepository,
    SqlAlchemyExamRoomRepository,
    SqlAlchemyRegistrationRepository,
    SqlAlchemyRoomRepository,
    SqlAlchemyStudentRepository,
)
from app.domain import Course, Exam, ExamRoom, Registration, Room, Student
from app.domain.examination_session import (
    ConflictingRoomAllocationError,
    DuplicateStudentInSessionError,
    IncompatibleExamScheduleError,
)
from app.services.examination_session import ExaminationSessionService
from app.services.seating_generation.records import ExamNotFoundError

DATE = date(2026, 10, 2)
TIME_SLOT = "09:00-11:00"


def _make_service(db_session: Session) -> ExaminationSessionService:
    return ExaminationSessionService(
        exam_repository=SqlAlchemyExamRepository(db_session),
        exam_room_repository=SqlAlchemyExamRoomRepository(db_session),
        room_repository=SqlAlchemyRoomRepository(db_session),
        registration_repository=SqlAlchemyRegistrationRepository(db_session),
        student_repository=SqlAlchemyStudentRepository(db_session),
        examination_session_repository=SqlAlchemyExaminationSessionRepository(db_session),
    )


def _seed_course_and_exam(
    db_session: Session,
    code: str,
    room_code: str | None = None,
    capacity: int = 50,
    exam_date: date = DATE,
    time_slot: str = TIME_SLOT,
) -> Exam:
    course = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code=code, name=f"{code} course"))
    exam = SqlAlchemyExamRepository(db_session).add(
        Exam(
            id=None,
            course_id=course.id,
            exam_date=exam_date,
            time_slot=time_slot,
            expected_student_count=10,
            day_label="Friday",
        )
    )
    if room_code is not None:
        room_repo = SqlAlchemyRoomRepository(db_session)
        existing = room_repo.get_by_code(room_code)
        room = existing or room_repo.add(Room(id=None, code=room_code, capacity=capacity))
        SqlAlchemyExamRoomRepository(db_session).add(
            ExamRoom(id=None, exam_id=exam.id, room_id=room.id, allocated_students=capacity)
        )
    db_session.commit()
    return exam


def _register(db_session: Session, exam: Exam, count: int, prefix: str) -> None:
    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    for i in range(1, count + 1):
        student = student_repo.add(Student(id=None, student_number=f"{prefix}{i:03d}", full_name=f"{prefix} {i}"))
        registration_repo.add(Registration(id=None, student_id=student.id, course_id=exam.course_id))
    db_session.commit()


# --- session creation --------------------------------------------------------


def test_single_exam_creates_a_valid_session(db_session: Session) -> None:
    exam = _seed_course_and_exam(db_session, "CS101", room_code="401")
    service = _make_service(db_session)

    session = service.create_session([exam.id])

    assert session.id is not None
    assert session.exam_ids == [exam.id]
    assert session.exam_date == DATE
    assert session.time_slot == TIME_SLOT


def test_two_compatible_exams_create_a_valid_session(db_session: Session) -> None:
    cs101 = _seed_course_and_exam(db_session, "CS101", room_code="401")
    math101 = _seed_course_and_exam(db_session, "MATH101", room_code="402")
    service = _make_service(db_session)

    session = service.create_session([cs101.id, math101.id])

    assert session.exam_ids == [cs101.id, math101.id]


def test_incompatible_dates_are_rejected(db_session: Session) -> None:
    cs101 = _seed_course_and_exam(db_session, "CS101", room_code="401", exam_date=date(2026, 10, 2))
    math101 = _seed_course_and_exam(db_session, "MATH101", room_code="402", exam_date=date(2026, 10, 3))
    service = _make_service(db_session)

    with pytest.raises(IncompatibleExamScheduleError):
        service.create_session([cs101.id, math101.id])


def test_incompatible_times_are_rejected(db_session: Session) -> None:
    cs101 = _seed_course_and_exam(db_session, "CS101", room_code="401", time_slot="09:00-11:00")
    math101 = _seed_course_and_exam(db_session, "MATH101", room_code="402", time_slot="13:00-15:00")
    service = _make_service(db_session)

    with pytest.raises(IncompatibleExamScheduleError):
        service.create_session([cs101.id, math101.id])


def test_missing_exam_is_rejected(db_session: Session) -> None:
    exam = _seed_course_and_exam(db_session, "CS101", room_code="401")
    service = _make_service(db_session)

    with pytest.raises(ExamNotFoundError):
        service.create_session([exam.id, 999])


def test_duplicate_exam_id_in_request_is_rejected(db_session: Session) -> None:
    exam = _seed_course_and_exam(db_session, "CS101", room_code="401")
    service = _make_service(db_session)

    with pytest.raises(ValueError, match="Duplicate exam id"):
        service.create_session([exam.id, exam.id])


def test_duplicate_student_across_exams_is_rejected(db_session: Session) -> None:
    cs101 = _seed_course_and_exam(db_session, "CS101", room_code="401")
    math101 = _seed_course_and_exam(db_session, "MATH101", room_code="402")
    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    shared_student = student_repo.add(Student(id=None, student_number="9999", full_name="Shared Student"))
    registration_repo.add(Registration(id=None, student_id=shared_student.id, course_id=cs101.course_id))
    registration_repo.add(Registration(id=None, student_id=shared_student.id, course_id=math101.course_id))
    db_session.commit()
    service = _make_service(db_session)

    with pytest.raises(DuplicateStudentInSessionError):
        service.create_session([cs101.id, math101.id])


def test_conflicting_room_usage_is_rejected(db_session: Session) -> None:
    cs101 = _seed_course_and_exam(db_session, "CS101", room_code="401")
    math101 = _seed_course_and_exam(db_session, "MATH101", room_code="401")  # same room as CS101
    service = _make_service(db_session)

    with pytest.raises(ConflictingRoomAllocationError):
        service.create_session([cs101.id, math101.id])
