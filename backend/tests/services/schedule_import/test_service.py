"""Service-level tests: exercise ScheduleImportService against a real
(in-memory) database through the concrete repositories, but never through
HTTP. All data here is synthetic.
"""

from sqlalchemy.orm import Session

from app.db.repositories import (
    SqlAlchemyCourseRepository,
    SqlAlchemyExamRepository,
    SqlAlchemyExamRoomRepository,
    SqlAlchemyRoomRepository,
)
from app.domain import Course, Room
from app.services.schedule_import import ImportStatus, ScheduleImportService

HEADER = "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"


def _make_service(db_session: Session) -> ScheduleImportService:
    return ScheduleImportService(
        course_repository=SqlAlchemyCourseRepository(db_session),
        room_repository=SqlAlchemyRoomRepository(db_session),
        exam_repository=SqlAlchemyExamRepository(db_session),
        exam_room_repository=SqlAlchemyExamRoomRepository(db_session),
    )


def _seed_course(db_session: Session, code: str, name: str) -> None:
    SqlAlchemyCourseRepository(db_session).add(Course(id=None, code=code, name=name))
    db_session.commit()


def _seed_room(db_session: Session, code: str, capacity: int) -> None:
    SqlAlchemyRoomRepository(db_session).add(Room(id=None, code=code, capacity=capacity))
    db_session.commit()


def test_unknown_course_code_is_rejected_without_creating_a_course(db_session: Session) -> None:
    _seed_room(db_session, "101", 50)
    service = _make_service(db_session)

    result = service.import_csv(
        HEADER + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
    )

    assert result.status == ImportStatus.PARTIAL
    assert result.exams_created == 0
    assert any("Unknown course code" in e.message for e in result.validation_errors)
    assert SqlAlchemyCourseRepository(db_session).count() == 0


def test_unknown_room_is_rejected_without_creating_a_room(db_session: Session) -> None:
    _seed_course(db_session, "CS101", "Intro to Computer Science")
    service = _make_service(db_session)

    result = service.import_csv(
        HEADER + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
    )

    assert result.status == ImportStatus.PARTIAL
    assert result.exams_created == 1  # the exam itself is still created
    assert result.exam_rooms_created == 0
    assert any("Unknown room code" in e.message for e in result.validation_errors)
    assert SqlAlchemyRoomRepository(db_session).count() == 0


def test_valid_import_creates_exam_and_exam_rooms(db_session: Session) -> None:
    _seed_course(db_session, "CS101", "Intro to Computer Science")
    _seed_room(db_session, "101", 50)
    _seed_room(db_session, "102", 50)
    service = _make_service(db_session)

    result = service.import_csv(
        HEADER
        + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
        + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,102,40\n"
    )

    assert result.status == ImportStatus.SUCCESS
    assert result.exams_created == 1
    assert result.exam_rooms_created == 2

    exam_repo = SqlAlchemyExamRepository(db_session)
    assert exam_repo.count() == 1
    exam_room_repo = SqlAlchemyExamRoomRepository(db_session)
    assert exam_room_repo.count() == 2


def test_reimporting_same_schedule_is_idempotent(db_session: Session) -> None:
    _seed_course(db_session, "CS101", "Intro to Computer Science")
    _seed_room(db_session, "101", 50)
    _seed_room(db_session, "102", 50)
    service = _make_service(db_session)
    csv_text = (
        HEADER
        + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
        + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,102,40\n"
    )

    first = service.import_csv(csv_text)
    db_session.commit()
    second = service.import_csv(csv_text)
    db_session.commit()

    assert first.exams_created == 1
    assert first.exam_rooms_created == 2
    assert second.exams_created == 0
    assert second.exams_existing == 1
    assert second.exam_rooms_created == 0
    assert second.exam_rooms_existing == 2

    assert SqlAlchemyExamRepository(db_session).count() == 1
    assert SqlAlchemyExamRoomRepository(db_session).count() == 2


def test_course_name_conflict_against_stored_course_is_reported(db_session: Session) -> None:
    _seed_course(db_session, "CS101", "Intro to Computer Science")
    _seed_room(db_session, "101", 50)
    service = _make_service(db_session)

    result = service.import_csv(
        HEADER + "Thursday,30-May-24,10:00-12:00,CS101,Introduction to CS,80,101,40\n"
    )

    assert len(result.conflicts) == 1
    assert result.conflicts[0].kind == "course_name"
    assert result.conflicts[0].existing_value == "Intro to Computer Science"
    stored = SqlAlchemyCourseRepository(db_session).get_by_code("CS101")
    assert stored is not None
    assert stored.name == "Intro to Computer Science"  # never overwritten
    assert result.exams_created == 1  # exam is still created against the existing course


def test_expected_student_count_conflict_against_stored_exam(db_session: Session) -> None:
    _seed_course(db_session, "CS101", "Intro to Computer Science")
    _seed_room(db_session, "101", 50)
    service = _make_service(db_session)

    service.import_csv(HEADER + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n")
    db_session.commit()

    result = service.import_csv(
        HEADER + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,90,101,40\n"
    )

    assert result.exams_existing == 1
    assert len(result.conflicts) == 1
    assert result.conflicts[0].kind == "expected_student_count"
    exam_repo = SqlAlchemyExamRepository(db_session)
    stored_exam = exam_repo.list()[0]
    assert stored_exam.expected_student_count == 80  # never overwritten


def test_room_allocation_exceeding_capacity_is_a_warning_not_an_error(db_session: Session) -> None:
    _seed_course(db_session, "CS101", "Intro to Computer Science")
    _seed_room(db_session, "101", 10)  # capacity smaller than the allocation
    service = _make_service(db_session)

    result = service.import_csv(
        HEADER + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,40,101,40\n"
    )

    assert result.status == ImportStatus.SUCCESS  # a warning does not block the import
    assert result.exam_rooms_created == 1
    assert len(result.warnings) == 1
    assert result.warnings[0].kind == "capacity_exceeded"


def test_failed_import_never_touches_the_database(db_session: Session) -> None:
    service = _make_service(db_session)

    result = service.import_csv("not,the,right,columns\n1,2,3,4\n")

    assert result.status == ImportStatus.FAILED
    assert SqlAlchemyExamRepository(db_session).count() == 0
