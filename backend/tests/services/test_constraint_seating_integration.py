"""Integration test (Phase 7 section 12, updated for Phase 8's
RepositoryRoomTopologyProvider): exercises the complete path

    students, rooms (with configured topology), exam allocations
        -> RepositoryRoomTopologyProvider (reads Room.rows/Room.columns)
        -> ConstraintSeatingStrategy
        -> SeatingEngine
        -> SeatingService (real repositories, real in-memory DB)
        -> SeatingResult / SeatingGenerationOutcome

through `SeatingService.generate(exam_id, strategy_name="constraint")` —
the exact same entry point the API uses — with no FastAPI and no mocking
of the strategy or engine. All data synthetic.

Room codes here are deliberately *not* "401"/"402" (arbitrary codes like
"A101"/"B-204" instead) — proving the production path now depends on each
room's own configured `rows`/`columns`, never on a specific room code.
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
from app.seating.topology_provider import RoomTopologyMissingError
from app.services.seating_generation import SeatingService


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


def _seed_exam(db_session: Session, student_count: int) -> Exam:
    course = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="CS101", name="Intro to CS"))
    exam = SqlAlchemyExamRepository(db_session).add(
        Exam(
            id=None,
            course_id=course.id,
            exam_date=date(2026, 10, 2),
            time_slot="09:00-11:00",
            expected_student_count=student_count,
            day_label="Friday",
        )
    )
    room_repo = SqlAlchemyRoomRepository(db_session)
    exam_room_repo = SqlAlchemyExamRoomRepository(db_session)
    for code in ("A101", "B-204"):  # deliberately not 401/402
        room = room_repo.add(Room(id=None, code=code, capacity=10, rows=2, columns=5))
        exam_room_repo.add(ExamRoom(id=None, exam_id=exam.id, room_id=room.id, allocated_students=10))

    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    for i in range(1, student_count + 1):
        student = student_repo.add(Student(id=None, student_number=f"{1000 + i}", full_name=f"Student {i}"))
        registration_repo.add(Registration(id=None, student_id=student.id, course_id=course.id))

    db_session.commit()
    return exam


def test_constraint_strategy_generates_a_full_seating_through_the_real_service(db_session: Session) -> None:
    exam = _seed_exam(db_session, student_count=15)  # 20 physical seats across 2 rooms, 15 registered
    service = _make_service(db_session)

    outcome = service.generate(exam.id, strategy_name="constraint")
    db_session.commit()

    assert outcome.generation.strategy_name == "constraint"
    assert outcome.generation.status == GenerationStatus.SUCCESS
    assert outcome.generation.total_registered == 15
    assert outcome.generation.total_assigned == 15
    assert outcome.generation.total_unassigned == 0
    assert outcome.scheduled_student_count == 20
    assert outcome.total_physical_capacity == 20

    assignments = SqlAlchemySeatAssignmentRepository(db_session).list_by_generation(outcome.generation.id)
    assert len(assignments) == 15
    room_ids = {a.room_id for a in assignments}
    assert len(room_ids) == 2  # both demo rooms actually used
    student_ids = [a.student_id for a in assignments]
    assert len(student_ids) == len(set(student_ids))  # no student assigned twice
    seat_keys = [(a.room_id, a.seat_number) for a in assignments]
    assert len(seat_keys) == len(set(seat_keys))  # no seat assigned twice


def test_constraint_and_sequential_strategies_agree_when_unconstrained(db_session: Session) -> None:
    """Same exam data, generated once with each registered strategy name —
    the demo `ConstraintSeatingStrategy` only wires in a soft
    same-course preference by default, which is trivially satisfied here
    (single-course exam), so its placements must match sequential's."""
    exam = _seed_exam(db_session, student_count=15)
    service = _make_service(db_session)

    sequential_outcome = service.generate(exam.id, strategy_name="sequential")
    constraint_outcome = service.generate(exam.id, strategy_name="constraint")
    db_session.commit()

    sequential_assignments = SqlAlchemySeatAssignmentRepository(db_session).list_by_generation(
        sequential_outcome.generation.id
    )
    constraint_assignments = SqlAlchemySeatAssignmentRepository(db_session).list_by_generation(
        constraint_outcome.generation.id
    )
    sequential_keys = sorted((a.student_id, a.room_id, a.seat_number) for a in sequential_assignments)
    constraint_keys = sorted((a.student_id, a.room_id, a.seat_number) for a in constraint_assignments)
    assert sequential_keys == constraint_keys


def test_sequential_works_without_topology_but_constraint_reports_it_missing(db_session: Session) -> None:
    """A room with only a capacity (no rows/columns) is completely normal,
    valid state — sequential seating never needs a topology and must not
    be affected by its absence. Constraint seating does need one, and must
    fail with a clear, specific error rather than guessing a layout or
    crashing with something opaque."""
    course = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="CS101", name="Intro to CS"))
    exam = SqlAlchemyExamRepository(db_session).add(
        Exam(
            id=None,
            course_id=course.id,
            exam_date=date(2026, 10, 2),
            time_slot="09:00-11:00",
            expected_student_count=5,
            day_label="Friday",
        )
    )
    room_repo = SqlAlchemyRoomRepository(db_session)
    room = room_repo.add(Room(id=None, code="101", capacity=10))  # no topology configured
    SqlAlchemyExamRoomRepository(db_session).add(
        ExamRoom(id=None, exam_id=exam.id, room_id=room.id, allocated_students=10)
    )
    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    for i in range(1, 6):
        student = student_repo.add(Student(id=None, student_number=f"{1000 + i}", full_name=f"Student {i}"))
        registration_repo.add(Registration(id=None, student_id=student.id, course_id=course.id))
    db_session.commit()

    service = _make_service(db_session)

    sequential_outcome = service.generate(exam.id, strategy_name="sequential")
    db_session.commit()
    assert sequential_outcome.generation.status == GenerationStatus.SUCCESS
    assert sequential_outcome.generation.total_assigned == 5

    with pytest.raises(RoomTopologyMissingError):
        service.generate(exam.id, strategy_name="constraint")
