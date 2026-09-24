from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models import CourseModel, StudentModel


def test_init_db_creates_expected_tables(engine: Engine) -> None:
    table_names = set(inspect(engine).get_table_names())

    assert {
        "students",
        "courses",
        "registrations",
        "exams",
        "rooms",
        "seating_generations",
        "seat_assignments",
    } <= table_names


def test_student_round_trip(db_session: Session) -> None:
    # Synthetic data — never real student records from data/*.csv.
    student = StudentModel(student_number="1001", full_name="Alice Example")
    db_session.add(student)
    db_session.commit()

    fetched = db_session.query(StudentModel).filter_by(student_number="1001").one()

    assert fetched.full_name == "Alice Example"


def test_course_round_trip(db_session: Session) -> None:
    course = CourseModel(code="CS101", name="Intro to Computer Science")
    db_session.add(course)
    db_session.commit()

    fetched = db_session.query(CourseModel).filter_by(code="CS101").one()

    assert fetched.name == "Intro to Computer Science"
