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
    SqlAlchemyExaminationSessionRepository,
    SqlAlchemyExamRepository,
    SqlAlchemyExamRoomRepository,
    SqlAlchemyRegistrationRepository,
    SqlAlchemyRoomRepository,
    SqlAlchemySeatAssignmentRepository,
    SqlAlchemySeatingGenerationRepository,
    SqlAlchemyStudentRepository,
)
from app.domain import Course, Exam, ExamRoom, Registration, Room, Student
from app.services.examination_session import ExaminationSessionService
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
        examination_session_repository=SqlAlchemyExaminationSessionRepository(db_session),
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
        examination_session_repository=SqlAlchemyExaminationSessionRepository(db_session),
    )


def _make_session_service(db_session: Session) -> ExaminationSessionService:
    return ExaminationSessionService(
        exam_repository=SqlAlchemyExamRepository(db_session),
        exam_room_repository=SqlAlchemyExamRoomRepository(db_session),
        room_repository=SqlAlchemyRoomRepository(db_session),
        registration_repository=SqlAlchemyRegistrationRepository(db_session),
        student_repository=SqlAlchemyStudentRepository(db_session),
        examination_session_repository=SqlAlchemyExaminationSessionRepository(db_session),
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


# --- Phase 14: build_seat_map_report_data -----------------------------------


def test_seat_map_report_data_reflects_occupied_empty_and_blocked_seats(db_session: Session) -> None:
    """4x5=20 room, seats 3 and 12 blocked (18 usable), 5 students
    registered (13 usable seats left empty) — the seat-map data must
    classify every one of the 20 physical seats correctly."""
    course = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="CS105", name="Seat Map Course"))
    exam = SqlAlchemyExamRepository(db_session).add(
        Exam(
            id=None,
            course_id=course.id,
            exam_date=date(2024, 5, 30),
            time_slot="10:00-12:00",
            expected_student_count=5,
            day_label="Thursday",
        )
    )
    room = SqlAlchemyRoomRepository(db_session).add(
        Room(id=None, code="SEATMAP-ROOM", capacity=20, rows=4, columns=5, blocked_seat_numbers=(3, 12))
    )
    SqlAlchemyExamRoomRepository(db_session).add(
        ExamRoom(id=None, exam_id=exam.id, room_id=room.id, allocated_students=5)
    )
    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    for i in range(1, 6):
        student = student_repo.add(Student(id=None, student_number=f"90{i:02d}", full_name=f"Student {i}"))
        registration_repo.add(Registration(id=None, student_id=student.id, course_id=course.id))
    db_session.commit()

    seating_service = _make_seating_service(db_session)
    outcome = seating_service.generate(exam.id, strategy_name="sequential")
    db_session.commit()

    report_service = _make_report_service(db_session)
    data = report_service.build_seat_map_report_data(outcome.generation.id)

    assert len(data.rooms) == 1
    room_data = data.rooms[0]
    assert room_data.room_code == "SEATMAP-ROOM"
    assert room_data.rows == 4
    assert room_data.columns == 5
    assert len(room_data.seats) == 20  # every physical seat, not just occupied ones

    by_seat_number = {seat.seat_number: seat for seat in room_data.seats}
    assert by_seat_number[3].state == "blocked"
    assert by_seat_number[12].state == "blocked"
    assert by_seat_number[3].student_number is None
    occupied = [seat for seat in room_data.seats if seat.state == "occupied"]
    assert len(occupied) == 5
    assert {seat.student_number for seat in occupied} == {"9001", "9002", "9003", "9004", "9005"}
    assert all(seat.course_code == "CS105" for seat in occupied)
    empty = [seat for seat in room_data.seats if seat.state == "empty"]
    assert len(empty) == 20 - 2 - 5  # physical - blocked - occupied


def test_seat_map_report_data_handles_room_without_topology(db_session: Session) -> None:
    """A room with capacity only (no rows/columns) is valid for a
    sequential-only exam — the seat-map data must not crash, just report
    no rows/columns/seats for that room."""
    exam = _seed_exam(db_session, "CS106", [("9101", "Student A")], allocated=1, capacity=5)
    seating_service = _make_seating_service(db_session)
    outcome = seating_service.generate(exam.id, strategy_name="sequential")
    db_session.commit()

    report_service = _make_report_service(db_session)
    data = report_service.build_seat_map_report_data(outcome.generation.id)

    assert len(data.rooms) == 1
    assert data.rooms[0].rows is None
    assert data.rooms[0].columns is None
    assert data.rooms[0].seats == []


def test_shared_room_in_a_session_is_reported_once_not_once_per_exam(db_session: Session) -> None:
    """Regression: a room shared by every exam in a session must appear
    exactly once in each report type's room list, not once per sharing
    exam — found via this milestone's own manual PDF verification, where
    a room shared by 3 exams was rendered (and its full seat list
    repeated) 3 times over in both the seating and seat-map reports."""
    course_a = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="PHY101", name="Physics I"))
    course_b = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="CHEM101", name="Chemistry I"))
    exam_a = SqlAlchemyExamRepository(db_session).add(
        Exam(
            id=None,
            course_id=course_a.id,
            exam_date=date(2026, 10, 2),
            time_slot="09:00-11:00",
            expected_student_count=3,
        )
    )
    exam_b = SqlAlchemyExamRepository(db_session).add(
        Exam(
            id=None,
            course_id=course_b.id,
            exam_date=date(2026, 10, 2),
            time_slot="09:00-11:00",
            expected_student_count=2,
        )
    )
    room = SqlAlchemyRoomRepository(db_session).add(
        Room(id=None, code="SHARED-ROOM", capacity=10, rows=2, columns=5)
    )
    exam_room_repo = SqlAlchemyExamRoomRepository(db_session)
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam_a.id, room_id=room.id, allocated_students=3))
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam_b.id, room_id=room.id, allocated_students=2))

    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    for prefix, course, count in (("P", course_a, 3), ("C", course_b, 2)):
        for i in range(1, count + 1):
            student = student_repo.add(
                Student(id=None, student_number=f"{prefix}{i:03d}", full_name=f"{prefix} {i}")
            )
            registration_repo.add(Registration(id=None, student_id=student.id, course_id=course.id))
    db_session.commit()

    session = _make_session_service(db_session).create_session([exam_a.id, exam_b.id])
    db_session.commit()
    outcome = _make_seating_service(db_session).generate_session(session.id, strategy_name="constraint")
    db_session.commit()

    report_service = _make_report_service(db_session)

    seating_data = report_service.build_seating_report_data(outcome.generation.id)
    assert len(seating_data.rooms) == 1
    assert len(seating_data.rooms[0].rows) == 5  # 3 + 2, not tripled/duplicated

    range_data = report_service.build_range_report_data(outcome.generation.id)
    assert len(range_data.rows) == 1
    assert range_data.rows[0].assigned_count == 5

    seat_map_data = report_service.build_seat_map_report_data(outcome.generation.id)
    assert len(seat_map_data.rooms) == 1
    assert len(seat_map_data.rooms[0].seats) == 10  # every physical seat, once
    occupied = [s for s in seat_map_data.rooms[0].seats if s.state == "occupied"]
    assert len(occupied) == 5
