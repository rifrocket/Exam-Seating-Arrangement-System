"""Service-level tests: exercise SeatingService against a real (in-memory)
database through the concrete repositories, but never through HTTP. All
data here is synthetic.
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
from app.domain import Course, Exam, ExamRoom, GenerationStatus, Registration, Room, Student
from app.seating import UnknownStrategyError
from app.services.seating_generation import ExamNotFoundError, SeatingService


def _make_service(db_session: Session) -> SeatingService:
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


def _seed_exam_with_students(db_session: Session, student_count: int, allocated: list[int], capacities: list[int]):
    course = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="CS101", name="Intro to CS"))
    exam = SqlAlchemyExamRepository(db_session).add(
        Exam(
            id=None,
            course_id=course.id,
            exam_date=date(2024, 5, 30),
            time_slot="10:00-12:00",
            expected_student_count=student_count,
            day_label="Thursday",
        )
    )
    room_repo = SqlAlchemyRoomRepository(db_session)
    exam_room_repo = SqlAlchemyExamRoomRepository(db_session)
    for i, (alloc, cap) in enumerate(zip(allocated, capacities)):
        room = room_repo.add(Room(id=None, code=f"R{i}", capacity=cap))
        exam_room_repo.add(ExamRoom(id=None, exam_id=exam.id, room_id=room.id, allocated_students=alloc))

    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    # Insert in reverse-numeric order to prove the service sorts them, not just echoes insertion order.
    for i in range(student_count, 0, -1):
        student = student_repo.add(Student(id=None, student_number=f"{1000 + i}", full_name=f"Student {i}"))
        registration_repo.add(Registration(id=None, student_id=student.id, course_id=course.id))

    db_session.commit()
    return exam


def test_generate_creates_generation_and_assignments(db_session: Session) -> None:
    exam = _seed_exam_with_students(db_session, student_count=80, allocated=[40, 40], capacities=[50, 50])
    service = _make_service(db_session)

    outcome = service.generate(exam.id)
    db_session.commit()

    assert outcome.generation.status == GenerationStatus.SUCCESS
    assert outcome.generation.total_registered == 80
    assert outcome.generation.total_assigned == 80
    assert outcome.generation.total_unassigned == 0
    assert outcome.generation.capacity_shortage is False
    assert outcome.generation.strategy_name == "sequential"
    assert outcome.generation.id is not None
    assert outcome.scheduled_student_count == 80
    assert outcome.available_capacity == 80
    assert outcome.unassigned_student_ids == []

    assignments = SqlAlchemySeatAssignmentRepository(db_session).list_by_generation(outcome.generation.id)
    assert len(assignments) == 80
    # Lowest student_number (1001) must be seat 1 — proves the service
    # sorted students deterministically rather than using insertion order
    # (which was seeded in reverse, 1080 down to 1001).
    first_room_id = min(a.room_id for a in assignments)
    seat_one = next(a for a in assignments if a.seat_number == 1 and a.room_id == first_room_id)
    seated_student = SqlAlchemyStudentRepository(db_session).get(seat_one.student_id)
    assert seated_student is not None
    assert seated_student.student_number == "1001"


def test_regeneration_creates_a_new_generation_not_overwriting_the_old_one(db_session: Session) -> None:
    exam = _seed_exam_with_students(db_session, student_count=10, allocated=[10], capacities=[10])
    service = _make_service(db_session)

    first = service.generate(exam.id)
    db_session.commit()
    second = service.generate(exam.id)
    db_session.commit()

    assert first.generation.id != second.generation.id
    generation_repo = SqlAlchemySeatingGenerationRepository(db_session)
    assert generation_repo.count() == 2
    assert len(generation_repo.list_by_exam(exam.id)) == 2

    assignment_repo = SqlAlchemySeatAssignmentRepository(db_session)
    assert len(assignment_repo.list_by_generation(first.generation.id)) == 10
    assert len(assignment_repo.list_by_generation(second.generation.id)) == 10
    assert assignment_repo.count() == 20  # both generations' assignments coexist


def test_capacity_shortage_is_reported_end_to_end(db_session: Session) -> None:
    exam = _seed_exam_with_students(db_session, student_count=50, allocated=[30], capacities=[30])
    service = _make_service(db_session)

    outcome = service.generate(exam.id)
    db_session.commit()

    assert outcome.generation.status == GenerationStatus.PARTIAL
    assert outcome.generation.capacity_shortage is True
    assert outcome.generation.total_assigned == 30
    assert outcome.generation.total_unassigned == 20
    assert len(outcome.unassigned_student_ids) == 20


def test_unknown_exam_raises(db_session: Session) -> None:
    service = _make_service(db_session)

    with pytest.raises(ExamNotFoundError):
        service.generate(999)


def test_unknown_strategy_raises(db_session: Session) -> None:
    exam = _seed_exam_with_students(db_session, student_count=5, allocated=[5], capacities=[5])
    service = _make_service(db_session)

    with pytest.raises(UnknownStrategyError):
        service.generate(exam.id, strategy_name="does-not-exist")
