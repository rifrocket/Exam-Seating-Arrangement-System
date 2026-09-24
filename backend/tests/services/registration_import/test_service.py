"""Service-level tests: exercise RegistrationImportService against a real
(in-memory) database through the concrete repositories, but never through
HTTP. All data here is synthetic.
"""

from sqlalchemy.orm import Session

from app.db.repositories import (
    SqlAlchemyCourseRepository,
    SqlAlchemyRegistrationRepository,
    SqlAlchemyStudentRepository,
)
from app.services.registration_import import ImportStatus, RegistrationImportService

VALID_CSV = (
    "student_id,student_name,subject_code,subject_name\n"
    "1001,Alice Example,CS101,Intro to Computer Science\n"
    "1002,Bob Sample,CS101,Intro to Computer Science\n"
    "1001,Alice Example,CS102,Data Structures\n"
)


def _make_service(db_session: Session) -> RegistrationImportService:
    return RegistrationImportService(
        student_repository=SqlAlchemyStudentRepository(db_session),
        course_repository=SqlAlchemyCourseRepository(db_session),
        registration_repository=SqlAlchemyRegistrationRepository(db_session),
    )


def test_valid_import_creates_students_courses_registrations(db_session: Session) -> None:
    service = _make_service(db_session)

    result = service.import_csv(VALID_CSV)
    db_session.commit()

    assert result.status == ImportStatus.SUCCESS
    assert result.rows_read == 3
    assert result.students_created == 2
    assert result.courses_created == 2
    assert result.registrations_created == 3
    assert result.students_existing == 0
    assert result.courses_existing == 0
    assert result.registrations_existing == 0


def test_reimporting_same_valid_csv_is_idempotent(db_session: Session) -> None:
    service = _make_service(db_session)

    first = service.import_csv(VALID_CSV)
    db_session.commit()

    student_repo = SqlAlchemyStudentRepository(db_session)
    course_repo = SqlAlchemyCourseRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    assert student_repo.count() == 2
    assert course_repo.count() == 2
    assert registration_repo.count() == 3

    second = service.import_csv(VALID_CSV)
    db_session.commit()

    assert second.status == ImportStatus.SUCCESS
    assert second.students_created == 0
    assert second.students_existing == 2
    assert second.courses_created == 0
    assert second.courses_existing == 2
    assert second.registrations_created == 0
    assert second.registrations_existing == 3

    # No duplicates were created in the database.
    assert student_repo.count() == 2
    assert course_repo.count() == 2
    assert registration_repo.count() == 3
    assert first.students_created == 2  # sanity: first run really did create them


def test_existing_student_with_conflicting_name_is_reported_and_not_overwritten(db_session: Session) -> None:
    service = _make_service(db_session)
    service.import_csv(
        "student_id,student_name,subject_code,subject_name\n"
        "1001,Alice Example,CS101,Intro to Computer Science\n"
    )
    db_session.commit()

    result = service.import_csv(
        "student_id,student_name,subject_code,subject_name\n"
        "1001,Alicia Example,CS102,Data Structures\n"
    )
    db_session.commit()

    assert result.status == ImportStatus.PARTIAL
    assert len(result.conflicts) == 1
    assert result.conflicts[0].kind == "student_name"
    assert result.conflicts[0].existing_value == "Alice Example"
    assert result.conflicts[0].incoming_value == "Alicia Example"
    # The registration itself is still recorded against the existing student.
    assert result.registrations_created == 1

    student_repo = SqlAlchemyStudentRepository(db_session)
    stored = student_repo.get_by_student_number("1001")
    assert stored is not None
    assert stored.full_name == "Alice Example"  # never overwritten


def test_existing_course_with_conflicting_name_is_reported_and_not_overwritten(db_session: Session) -> None:
    service = _make_service(db_session)
    service.import_csv(
        "student_id,student_name,subject_code,subject_name\n"
        "1001,Alice Example,CS101,Intro to Computer Science\n"
    )
    db_session.commit()

    result = service.import_csv(
        "student_id,student_name,subject_code,subject_name\n"
        "1002,Bob Sample,CS101,Introduction to CS\n"
    )
    db_session.commit()

    assert result.status == ImportStatus.PARTIAL
    assert len(result.conflicts) == 1
    assert result.conflicts[0].kind == "course_name"
    assert result.conflicts[0].existing_value == "Intro to Computer Science"
    assert result.conflicts[0].incoming_value == "Introduction to CS"

    course_repo = SqlAlchemyCourseRepository(db_session)
    stored = course_repo.get_by_code("CS101")
    assert stored is not None
    assert stored.name == "Intro to Computer Science"  # never overwritten


def test_import_with_validation_errors_still_processes_valid_rows(db_session: Session) -> None:
    service = _make_service(db_session)

    result = service.import_csv(
        "student_id,student_name,subject_code,subject_name\n"
        "1001,Alice Example,CS101,Intro to Computer Science\n"
        "1002,,CS101,Intro to Computer Science\n"
    )
    db_session.commit()

    assert result.status == ImportStatus.PARTIAL
    assert result.registrations_created == 1
    assert len(result.validation_errors) == 1


def test_failed_import_never_touches_the_database(db_session: Session) -> None:
    service = _make_service(db_session)

    result = service.import_csv("not,the,right,columns\n1,2,3,4\n")

    assert result.status == ImportStatus.FAILED
    student_repo = SqlAlchemyStudentRepository(db_session)
    assert student_repo.count() == 0
