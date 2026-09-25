"""Integration test (Phase 7, section 12): exercises the complete path

    students, rooms, exam allocations
        -> RoomTopologyProvider (the default static demo provider)
        -> ConstraintSeatingStrategy
        -> SeatingEngine
        -> SeatingService (real repositories, real in-memory DB)
        -> SeatingResult / SeatingGenerationOutcome

through `SeatingService.generate(exam_id, strategy_name="constraint")` —
the exact same entry point the API uses — with no FastAPI and no mocking
of the strategy or engine. All data synthetic.

Room codes here are deliberately "401" and "402" with capacity 10 each,
matching `ConstraintSeatingStrategy`'s built-in `DEFAULT_DEMO_ROOM_LAYOUTS`
(this milestone's explicit in-memory demo configuration) — an arbitrary
room code would raise `UnknownRoomTopologyError`, which is expected and
correct, not a bug to work around here.
"""

from datetime import date

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
    for code in ("401", "402"):
        room = room_repo.add(Room(id=None, code=code, capacity=10))
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
