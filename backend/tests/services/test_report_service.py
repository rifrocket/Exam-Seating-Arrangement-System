"""Service-level tests for ReportService against a real (in-memory)
database through the concrete repositories, but never through HTTP.
All data synthetic.

Critical property under test: a report for generation X must reflect
only generation X's persisted SeatAssignment rows — never the current
registrations, never a different generation for the same exam, and never
a freshly-computed seating result.
"""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.db.repositories import (
    SqlAlchemyCourseRepository,
    SqlAlchemyExamRepository,
    SqlAlchemyExamRoomRepository,
    SqlAlchemyRegistrationRepository,
    SqlAlchemyRoomRepository,
    SqlAlchemySeatAssignmentRepository,
    SqlAlchemySeatingGenerationRepository,
    SqlAlchemyStudentRepository,
)
from app.domain import Course, Exam, ExamRoom, Registration, Room, Student
from app.services.reports import EmptyGenerationError, GenerationNotFoundError, ReportService
from app.services.seating_generation import SeatingService


def _make_report_service(db_session: Session) -> ReportService:
    return ReportService(
        seating_generation_repository=SqlAlchemySeatingGenerationRepository(db_session),
        seat_assignment_repository=SqlAlchemySeatAssignmentRepository(db_session),
        exam_repository=SqlAlchemyExamRepository(db_session),
        exam_room_repository=SqlAlchemyExamRoomRepository(db_session),
        course_repository=SqlAlchemyCourseRepository(db_session),
        room_repository=SqlAlchemyRoomRepository(db_session),
        student_repository=SqlAlchemyStudentRepository(db_session),
    )


def _make_seating_service(db_session: Session) -> SeatingService:
    return SeatingService(
        exam_repository=SqlAlchemyExamRepository(db_session),
        exam_room_repository=SqlAlchemyExamRoomRepository(db_session),
        room_repository=SqlAlchemyRoomRepository(db_session),
        course_repository=SqlAlchemyCourseRepository(db_session),
        registration_repository=SqlAlchemyRegistrationRepository(db_session),
        student_repository=SqlAlchemyStudentRepository(db_session),
        seating_generation_repository=SqlAlchemySeatingGenerationRepository(db_session),
        seat_assignment_repository=SqlAlchemySeatAssignmentRepository(db_session),
    )


def _seed_exam(db_session: Session, course_code: str, students: list[tuple[str, str]], allocated: int, capacity: int):
    course = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code=course_code, name=f"{course_code} Name"))
    exam = SqlAlchemyExamRepository(db_session).add(
        Exam(
            id=None,
            course_id=course.id,
            exam_date=date(2024, 5, 30),
            time_slot="10:00-12:00",
            expected_student_count=len(students),
            day_label="Thursday",
        )
    )
    room = SqlAlchemyRoomRepository(db_session).add(Room(id=None, code=f"{course_code}-ROOM", capacity=capacity))
    SqlAlchemyExamRoomRepository(db_session).add(
        ExamRoom(id=None, exam_id=exam.id, room_id=room.id, allocated_students=allocated)
    )

    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    for number, name in students:
        student = student_repo.add(Student(id=None, student_number=number, full_name=name))
        registration_repo.add(Registration(id=None, student_id=student.id, course_id=course.id))

    db_session.commit()
    return exam


def test_seating_report_data_reflects_persisted_assignments(db_session: Session) -> None:
    exam = _seed_exam(
        db_session,
        "CS101",
        [("1001", "Alice Example"), ("1002", "Bob Sample")],
        allocated=2,
        capacity=10,
    )
    seating_service = _make_seating_service(db_session)
    outcome = seating_service.generate(exam.id)
    db_session.commit()

    report_service = _make_report_service(db_session)
    data = report_service.build_seating_report_data(outcome.generation.id)

    assert data.course_code == "CS101"
    assert data.generation_id == outcome.generation.id
    assert len(data.rooms) == 1
    assert data.rooms[0].room_code == "CS101-ROOM"
    assert [r.student_number for r in data.rooms[0].rows] == ["1001", "1002"]
    assert data.rooms[0].rows[0].seat_number == 1


def test_range_report_data_derives_start_end_from_assignments(db_session: Session) -> None:
    exam = _seed_exam(
        db_session,
        "CS102",
        [("2001", "A"), ("2002", "B"), ("2003", "C")],
        allocated=3,
        capacity=10,
    )
    seating_service = _make_seating_service(db_session)
    outcome = seating_service.generate(exam.id)
    db_session.commit()

    report_service = _make_report_service(db_session)
    data = report_service.build_range_report_data(outcome.generation.id)

    assert len(data.rows) == 1
    row = data.rows[0]
    assert row.start_student_number == "2001"
    assert row.end_student_number == "2003"
    assert row.assigned_count == 3


def test_report_for_unknown_generation_raises(db_session: Session) -> None:
    report_service = _make_report_service(db_session)

    with pytest.raises(GenerationNotFoundError):
        report_service.build_seating_report_data(999)
    with pytest.raises(GenerationNotFoundError):
        report_service.build_range_report_data(999)


def test_report_for_generation_with_no_assignments_raises(db_session: Session) -> None:
    # An exam with a room but zero registered students -> generation
    # succeeds trivially but has no SeatAssignment rows.
    exam = _seed_exam(db_session, "CS103", [], allocated=10, capacity=10)
    seating_service = _make_seating_service(db_session)
    outcome = seating_service.generate(exam.id)
    db_session.commit()
    assert outcome.generation.total_assigned == 0

    report_service = _make_report_service(db_session)
    with pytest.raises(EmptyGenerationError):
        report_service.build_seating_report_data(outcome.generation.id)
    with pytest.raises(EmptyGenerationError):
        report_service.build_range_report_data(outcome.generation.id)


def test_report_generation_isolation(db_session: Session) -> None:
    """Two generations for the same exam, with distinguishably different
    assignment data (achieved by adding a room between runs, changing who
    fits). Reporting on generation A must never reflect generation B."""
    course = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="CS104", name="Isolation Course"))
    exam = SqlAlchemyExamRepository(db_session).add(
        Exam(
            id=None,
            course_id=course.id,
            exam_date=date(2024, 5, 30),
            time_slot="10:00-12:00",
            expected_student_count=2,
            day_label="Thursday",
        )
    )
    room_repo = SqlAlchemyRoomRepository(db_session)
    exam_room_repo = SqlAlchemyExamRoomRepository(db_session)
    room_a = room_repo.add(Room(id=None, code="ROOM-A", capacity=1))
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam.id, room_id=room_a.id, allocated_students=1))

    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    student_1 = student_repo.add(Student(id=None, student_number="3001", full_name="Student One"))
    registration_repo.add(Registration(id=None, student_id=student_1.id, course_id=course.id))
    db_session.commit()

    seating_service = _make_seating_service(db_session)
    generation_a = seating_service.generate(exam.id)
    db_session.commit()

    # Add a second room and a second student before regenerating, so
    # generation B's assignment set is distinguishably different.
    room_b = room_repo.add(Room(id=None, code="ROOM-B", capacity=1))
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam.id, room_id=room_b.id, allocated_students=1))
    student_2 = student_repo.add(Student(id=None, student_number="3002", full_name="Student Two"))
    registration_repo.add(Registration(id=None, student_id=student_2.id, course_id=course.id))
    db_session.commit()

    generation_b = seating_service.generate(exam.id)
    db_session.commit()

    report_service = _make_report_service(db_session)
    data_a = report_service.build_seating_report_data(generation_a.generation.id)
    data_b = report_service.build_range_report_data(generation_b.generation.id)

    assert len(data_a.rooms) == 1
    assert {r.student_number for r in data_a.rooms[0].rows} == {"3001"}

    assert len(data_b.rows) == 2
    all_numbers_in_b = set()
    seating_data_b = report_service.build_seating_report_data(generation_b.generation.id)
    for room in seating_data_b.rooms:
        all_numbers_in_b.update(r.student_number for r in room.rows)
    assert all_numbers_in_b == {"3001", "3002"}
