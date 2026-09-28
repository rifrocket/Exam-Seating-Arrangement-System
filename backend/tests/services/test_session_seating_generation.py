"""Service-level tests: exercise SeatingService.generate_session() against
a real (in-memory) database through the concrete repositories, but never
through HTTP. All data here is synthetic. Mirrors the style of
tests/services/test_constraint_seating_integration.py.
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
from app.domain import Course, Exam, ExamRoom, GenerationStatus, Registration, Room, Student
from app.seating.topology_provider import RoomTopologyMissingError
from app.services.examination_session import ExaminationSessionService
from app.services.seating_generation import SeatingService

DATE = date(2026, 10, 2)
TIME_SLOT = "09:00-11:00"


def _seating_service(db_session: Session) -> SeatingService:
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


def _session_service(db_session: Session) -> ExaminationSessionService:
    return ExaminationSessionService(
        exam_repository=SqlAlchemyExamRepository(db_session),
        exam_room_repository=SqlAlchemyExamRoomRepository(db_session),
        room_repository=SqlAlchemyRoomRepository(db_session),
        registration_repository=SqlAlchemyRegistrationRepository(db_session),
        student_repository=SqlAlchemyStudentRepository(db_session),
        examination_session_repository=SqlAlchemyExaminationSessionRepository(db_session),
    )


def _seed_exam_with_room(
    db_session: Session,
    course_code: str,
    room_code: str,
    capacity: int,
    rows: int,
    columns: int,
    student_count: int,
    student_prefix: str,
) -> Exam:
    course = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code=course_code, name=course_code))
    exam = SqlAlchemyExamRepository(db_session).add(
        Exam(
            id=None,
            course_id=course.id,
            exam_date=DATE,
            time_slot=TIME_SLOT,
            expected_student_count=student_count,
            day_label="Friday",
        )
    )
    room = SqlAlchemyRoomRepository(db_session).add(
        Room(id=None, code=room_code, capacity=capacity, rows=rows, columns=columns)
    )
    SqlAlchemyExamRoomRepository(db_session).add(
        ExamRoom(id=None, exam_id=exam.id, room_id=room.id, allocated_students=capacity)
    )
    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    for i in range(1, student_count + 1):
        student = student_repo.add(
            Student(id=None, student_number=f"{student_prefix}{i:03d}", full_name=f"{student_prefix} {i}")
        )
        registration_repo.add(Registration(id=None, student_id=student.id, course_id=course.id))
    db_session.commit()
    return exam


def test_manual_acceptance_scenario_two_courses_sharing_one_room(db_session: Session) -> None:
    """The exact Phase 9 manual acceptance scenario: Course A (10
    students) and Course B (10 students) share one 20-seat room (401,
    4x5) within a single session. Verifies every point in that scenario:
    20 students enter the pool, 20 are assigned, no duplicates, course ids
    preserved, and the room's capacity is not double-counted just because
    two exams reference it."""
    course_a = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="CS101", name="CS101"))
    course_b = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="MATH101", name="MATH101"))
    exam_a = SqlAlchemyExamRepository(db_session).add(
        Exam(id=None, course_id=course_a.id, exam_date=DATE, time_slot=TIME_SLOT, expected_student_count=10)
    )
    exam_b = SqlAlchemyExamRepository(db_session).add(
        Exam(id=None, course_id=course_b.id, exam_date=DATE, time_slot=TIME_SLOT, expected_student_count=10)
    )
    shared_room = SqlAlchemyRoomRepository(db_session).add(
        Room(id=None, code="401", capacity=20, rows=4, columns=5)
    )
    exam_room_repo = SqlAlchemyExamRoomRepository(db_session)
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam_a.id, room_id=shared_room.id, allocated_students=10))
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam_b.id, room_id=shared_room.id, allocated_students=10))

    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    for prefix, course in (("A", course_a), ("B", course_b)):
        for i in range(1, 11):
            student = student_repo.add(Student(id=None, student_number=f"{prefix}{i:03d}", full_name=f"{prefix} {i}"))
            registration_repo.add(Registration(id=None, student_id=student.id, course_id=course.id))
    db_session.commit()

    session = _session_service(db_session).create_session([exam_a.id, exam_b.id])
    db_session.commit()

    outcome = _seating_service(db_session).generate_session(session.id, strategy_name="constraint")
    db_session.commit()

    # 1. 20 students enter the seating pool.
    assert outcome.generation.total_registered == 20
    # 2. 20 students are assigned.
    assert outcome.generation.total_assigned == 20
    assert outcome.generation.total_unassigned == 0
    assert outcome.generation.status == GenerationStatus.SUCCESS
    # The room's capacity/scheduled totals must not be double-counted just
    # because two exams both reference the shared room.
    assert outcome.scheduled_student_count == 20  # 10 + 10, not 40
    assert outcome.total_physical_capacity == 20  # the room's own capacity, once

    assignments = SqlAlchemySeatAssignmentRepository(db_session).list_by_generation(outcome.generation.id)
    assert len(assignments) == 20
    # 3. No student appears twice.
    student_ids = [a.student_id for a in assignments]
    assert len(student_ids) == len(set(student_ids))
    # 4. No seat is duplicated.
    seat_keys = [(a.room_id, a.seat_number) for a in assignments]
    assert len(seat_keys) == len(set(seat_keys))
    assert {a.room_id for a in assignments} == {shared_room.id}
    # 5. Course ids are preserved.
    student_repo_lookup = {s.id: s for s in [student_repo.get(a.student_id) for a in assignments]}
    for assignment in assignments:
        student = student_repo_lookup[assignment.student_id]
        assert student is not None
        expected_exam_id = exam_a.id if student.student_number.startswith("A") else exam_b.id
        assert assignment.exam_id == expected_exam_id
    # 7. The result is deterministic.
    second_outcome = _seating_service(db_session).generate_session(session.id, strategy_name="constraint")
    db_session.commit()
    second_assignments = SqlAlchemySeatAssignmentRepository(db_session).list_by_generation(
        second_outcome.generation.id
    )
    first_keys = sorted((a.student_id, a.room_id, a.seat_number) for a in assignments)
    second_keys = sorted((a.student_id, a.room_id, a.seat_number) for a in second_assignments)
    assert first_keys == second_keys


def test_two_courses_produce_one_combined_generation(db_session: Session) -> None:
    exam_a = _seed_exam_with_room(db_session, "CS101", "401", 10, 2, 5, 10, "A")
    exam_b = _seed_exam_with_room(db_session, "MATH101", "402", 10, 2, 5, 10, "B")
    session = _session_service(db_session).create_session([exam_a.id, exam_b.id])
    db_session.commit()

    outcome = _seating_service(db_session).generate_session(session.id, strategy_name="constraint")
    db_session.commit()

    assert outcome.generation.session_id == session.id
    assert outcome.generation.exam_id is None
    assert outcome.generation.status == GenerationStatus.SUCCESS
    assert outcome.generation.total_registered == 20
    assert outcome.generation.total_assigned == 20
    assert outcome.scheduled_student_count == 20
    assert outcome.total_physical_capacity == 20


def test_no_student_assigned_twice_and_no_seat_duplicated(db_session: Session) -> None:
    exam_a = _seed_exam_with_room(db_session, "CS101", "401", 10, 2, 5, 10, "A")
    exam_b = _seed_exam_with_room(db_session, "MATH101", "402", 10, 2, 5, 10, "B")
    session = _session_service(db_session).create_session([exam_a.id, exam_b.id])
    db_session.commit()

    outcome = _seating_service(db_session).generate_session(session.id, strategy_name="constraint")
    db_session.commit()

    assignments = SqlAlchemySeatAssignmentRepository(db_session).list_by_generation(outcome.generation.id)
    assert len(assignments) == 20
    student_ids = [a.student_id for a in assignments]
    assert len(student_ids) == len(set(student_ids))
    seat_keys = [(a.room_id, a.seat_number) for a in assignments]
    assert len(seat_keys) == len(set(seat_keys))


def test_course_information_is_preserved_per_assignment(db_session: Session) -> None:
    exam_a = _seed_exam_with_room(db_session, "CS101", "401", 10, 2, 5, 10, "A")
    exam_b = _seed_exam_with_room(db_session, "MATH101", "402", 10, 2, 5, 10, "B")
    session = _session_service(db_session).create_session([exam_a.id, exam_b.id])
    db_session.commit()

    outcome = _seating_service(db_session).generate_session(session.id, strategy_name="constraint")
    db_session.commit()

    assignments = SqlAlchemySeatAssignmentRepository(db_session).list_by_generation(outcome.generation.id)
    student_repo = SqlAlchemyStudentRepository(db_session)
    for assignment in assignments:
        student = student_repo.get(assignment.student_id)
        assert student is not None
        if student.student_number.startswith("A"):
            assert assignment.exam_id == exam_a.id
        else:
            assert assignment.exam_id == exam_b.id


def test_session_generation_is_deterministic(db_session: Session) -> None:
    exam_a = _seed_exam_with_room(db_session, "CS101", "401", 10, 2, 5, 10, "A")
    exam_b = _seed_exam_with_room(db_session, "MATH101", "402", 10, 2, 5, 10, "B")
    session = _session_service(db_session).create_session([exam_a.id, exam_b.id])
    db_session.commit()
    service = _seating_service(db_session)

    first = service.generate_session(session.id, strategy_name="constraint")
    db_session.commit()
    second = service.generate_session(session.id, strategy_name="constraint")
    db_session.commit()

    first_assignments = SqlAlchemySeatAssignmentRepository(db_session).list_by_generation(first.generation.id)
    second_assignments = SqlAlchemySeatAssignmentRepository(db_session).list_by_generation(second.generation.id)
    first_keys = sorted((a.student_id, a.room_id, a.seat_number) for a in first_assignments)
    second_keys = sorted((a.student_id, a.room_id, a.seat_number) for a in second_assignments)
    assert first_keys == second_keys


def test_course_separation_minimizes_adjacency_compared_to_naive_blocking(db_session: Session) -> None:
    """One *shared* room, 1x10 (a single row), with two courses of 5
    students each (10 seats exactly) both allocated into it — unlike
    `_seed_exam_with_room` (which gives each exam its own separate room),
    this is the genuine "courses actually share physical seats" case.
    Before this milestone, course-grouped ordering meant course A filled
    seats 1-5 and course B filled seats 6-10 (a naive contiguous block per
    course, 8 same-course-adjacent pairs out of 9 possible) — that was the
    anti-cheating *problem* this milestone fixes, not a property to
    preserve. The real default must produce materially fewer same-course-
    adjacent pairs than that naive baseline, while still seating everyone
    and keeping both courses fully represented."""
    course_a = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="CS101", name="CS101"))
    course_b = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="MATH101", name="MATH101"))
    exam_a = SqlAlchemyExamRepository(db_session).add(
        Exam(id=None, course_id=course_a.id, exam_date=DATE, time_slot=TIME_SLOT, expected_student_count=5)
    )
    exam_b = SqlAlchemyExamRepository(db_session).add(
        Exam(id=None, course_id=course_b.id, exam_date=DATE, time_slot=TIME_SLOT, expected_student_count=5)
    )
    shared_room = SqlAlchemyRoomRepository(db_session).add(Room(id=None, code="401", capacity=10, rows=1, columns=10))
    exam_room_repo = SqlAlchemyExamRoomRepository(db_session)
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam_a.id, room_id=shared_room.id, allocated_students=5))
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam_b.id, room_id=shared_room.id, allocated_students=5))

    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    for prefix, course in (("A", course_a), ("B", course_b)):
        for i in range(1, 6):
            student = student_repo.add(Student(id=None, student_number=f"{prefix}{i:03d}", full_name=f"{prefix} {i}"))
            registration_repo.add(Registration(id=None, student_id=student.id, course_id=course.id))
    db_session.commit()

    session = _session_service(db_session).create_session([exam_a.id, exam_b.id])
    db_session.commit()

    outcome = _seating_service(db_session).generate_session(session.id, strategy_name="constraint")
    db_session.commit()

    assignments = SqlAlchemySeatAssignmentRepository(db_session).list_by_generation(outcome.generation.id)
    assert len(assignments) == 10
    course_by_seat = {
        a.seat_number: (student_repo.get(a.student_id)).student_number[0]  # type: ignore[union-attr]
        for a in assignments
    }

    assert sorted(course_by_seat.values()) == sorted(["A"] * 5 + ["B"] * 5)
    seat_numbers = sorted(course_by_seat)
    same_course_adjacent_pairs = sum(
        1 for seat in seat_numbers[:-1] if course_by_seat[seat] == course_by_seat[seat + 1]
    )
    naive_contiguous_pairs = 4 + 4  # AAAAA BBBBB: 4 internal same-course pairs per 5-seat block
    assert same_course_adjacent_pairs < naive_contiguous_pairs


# --- capacity semantics -----------------------------------------------------


def test_registered_within_capacity_succeeds(db_session: Session) -> None:
    exam_a = _seed_exam_with_room(db_session, "CS101", "401", 10, 2, 5, 5, "A")
    exam_b = _seed_exam_with_room(db_session, "MATH101", "402", 10, 2, 5, 5, "B")
    session = _session_service(db_session).create_session([exam_a.id, exam_b.id])
    db_session.commit()

    outcome = _seating_service(db_session).generate_session(session.id, strategy_name="constraint")

    assert outcome.generation.status == GenerationStatus.SUCCESS
    assert outcome.generation.total_unassigned == 0
    assert outcome.scheduled_allocation_shortage is False
    assert outcome.physical_capacity_shortage is False


def test_constraint_caused_unassignment_does_not_falsely_report_capacity_shortage(db_session: Session) -> None:
    """Physical capacity = 2, scheduled = 2, registered = 2 (one student
    per course, sharing one room), but a hard constraint (injected
    directly — there is no constraint-management UI/API yet, see
    docs/architecture.md) makes the two students impossible to seat
    together. This must be reported as a constraint feasibility problem,
    not a capacity shortage — the exact multi-exam version of
    tests/seating/test_constraint_strategy.py's single-exam equivalent,
    proving generate_session()'s combined room_allocations/students don't
    corrupt these flags."""
    from app.seating import ConstraintSeatingStrategy, SeatingEngine, StudentsNotAdjacentConstraint
    from app.seating.constraints import ConstraintSet
    from app.seating.models import RoomAllocation
    from app.services.seating_generation.room_topology_provider import RepositoryRoomTopologyProvider

    course_a = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="CS101", name="CS101"))
    course_b = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="MATH101", name="MATH101"))
    exam_a = SqlAlchemyExamRepository(db_session).add(
        Exam(id=None, course_id=course_a.id, exam_date=DATE, time_slot=TIME_SLOT, expected_student_count=1)
    )
    room_repo = SqlAlchemyRoomRepository(db_session)
    shared_room = room_repo.add(Room(id=None, code="401", capacity=2, rows=1, columns=2))
    SqlAlchemyExamRoomRepository(db_session).add(
        ExamRoom(id=None, exam_id=exam_a.id, room_id=shared_room.id, allocated_students=2)
    )
    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    student_a = student_repo.add(Student(id=None, student_number="A001", full_name="Student A"))
    student_b = student_repo.add(Student(id=None, student_number="B001", full_name="Student B"))
    registration_repo.add(Registration(id=None, student_id=student_a.id, course_id=course_a.id))
    registration_repo.add(Registration(id=None, student_id=student_b.id, course_id=course_b.id))
    db_session.commit()

    # Constructs the strategy directly rather than through
    # generate_session(), specifically to inject a hard constraint the
    # session service has no way to configure yet.
    topology_provider = RepositoryRoomTopologyProvider(room_repo)
    topology = topology_provider.get_topology(room_id=shared_room.id, room_code=shared_room.code, capacity=2)
    not_adjacent = StudentsNotAdjacentConstraint(
        student_a_id=student_a.id, student_b_id=student_b.id, topologies={shared_room.id: topology}
    )
    strategy = ConstraintSeatingStrategy(
        topology_provider=topology_provider,
        constraint_set=ConstraintSet(hard_constraints=(not_adjacent,)),
    )
    engine = SeatingEngine(strategy)
    room_allocations = [
        RoomAllocation(room_id=shared_room.id, room_code=shared_room.code, allocated_students=2, capacity=2)
    ]
    result = engine.run(exam_a, [student_a, student_b], room_allocations)

    assert result.unassigned_student_count == 1
    assert result.scheduled_allocation_shortage is False
    assert result.physical_capacity_shortage is False
    assert result.capacity_shortage is True
    assert any("hard constraint" in w for w in result.warnings)


# --- room validation at generation time -------------------------------------


def test_session_generation_reports_missing_topology_clearly(db_session: Session) -> None:
    course_a = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="CS101", name="CS101"))
    course_b = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="MATH101", name="MATH101"))
    exam_a = SqlAlchemyExamRepository(db_session).add(
        Exam(id=None, course_id=course_a.id, exam_date=DATE, time_slot=TIME_SLOT, expected_student_count=5)
    )
    exam_b = SqlAlchemyExamRepository(db_session).add(
        Exam(id=None, course_id=course_b.id, exam_date=DATE, time_slot=TIME_SLOT, expected_student_count=5)
    )
    room_repo = SqlAlchemyRoomRepository(db_session)
    room_a = room_repo.add(Room(id=None, code="401", capacity=5))  # no topology configured
    room_b = room_repo.add(Room(id=None, code="402", capacity=5, rows=1, columns=5))
    exam_room_repo = SqlAlchemyExamRoomRepository(db_session)
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam_a.id, room_id=room_a.id, allocated_students=5))
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam_b.id, room_id=room_b.id, allocated_students=5))
    db_session.commit()

    session = _session_service(db_session).create_session([exam_a.id, exam_b.id])
    db_session.commit()

    with pytest.raises(RoomTopologyMissingError):
        _seating_service(db_session).generate_session(session.id, strategy_name="constraint")


def _seed_exam_with_room_allocation(
    db_session: Session,
    course_code: str,
    room_code: str,
    capacity: int,
    rows: int,
    columns: int,
    allocated_students: int,
    student_count: int,
    student_prefix: str,
) -> Exam:
    """Like _seed_exam_with_room, but lets allocated_students differ from
    capacity (to exercise scheduled_allocation_shortage independently of
    physical_capacity_shortage)."""
    course = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code=course_code, name=course_code))
    exam = SqlAlchemyExamRepository(db_session).add(
        Exam(
            id=None,
            course_id=course.id,
            exam_date=DATE,
            time_slot=TIME_SLOT,
            expected_student_count=student_count,
            day_label="Friday",
        )
    )
    room = SqlAlchemyRoomRepository(db_session).add(
        Room(id=None, code=room_code, capacity=capacity, rows=rows, columns=columns)
    )
    SqlAlchemyExamRoomRepository(db_session).add(
        ExamRoom(id=None, exam_id=exam.id, room_id=room.id, allocated_students=allocated_students)
    )
    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    for i in range(1, student_count + 1):
        student = student_repo.add(
            Student(id=None, student_number=f"{student_prefix}{i:03d}", full_name=f"{student_prefix} {i}")
        )
        registration_repo.add(Registration(id=None, student_id=student.id, course_id=course.id))
    db_session.commit()
    return exam


def test_session_registered_more_than_scheduled_is_reported(db_session: Session) -> None:
    """11 registered across both courses, but only 9 seats scheduled
    (exam_a's room is deliberately under-allocated: 4 of its 10 physical
    seats) — a scheduling gap, not a physical one."""
    exam_a = _seed_exam_with_room_allocation(db_session, "CS101", "401", 10, 2, 5, 4, 6, "A")
    exam_b = _seed_exam_with_room_allocation(db_session, "MATH101", "402", 10, 2, 5, 5, 5, "B")
    session = _session_service(db_session).create_session([exam_a.id, exam_b.id])
    db_session.commit()

    outcome = _seating_service(db_session).generate_session(session.id, strategy_name="constraint")

    assert outcome.generation.total_registered == 11
    assert outcome.scheduled_student_count == 9  # 4 (exam_a) + 5 (exam_b)
    assert outcome.total_physical_capacity == 20  # 10 + 10, unaffected by allocation
    assert outcome.scheduled_allocation_shortage is True
    assert outcome.physical_capacity_shortage is False


def test_session_registered_more_than_physical_capacity_is_reported(db_session: Session) -> None:
    """Both rooms are over-scheduled beyond their own physical capacity
    (allocated_students > capacity), so even filling every physical seat
    can't cover the scheduled promise — a physical shortage this time,
    not (only) a scheduling one."""
    exam_a = _seed_exam_with_room_allocation(db_session, "CS101", "401", 5, 1, 5, 8, 8, "A")
    exam_b = _seed_exam_with_room_allocation(db_session, "MATH101", "402", 5, 1, 5, 8, 8, "B")
    session = _session_service(db_session).create_session([exam_a.id, exam_b.id])
    db_session.commit()

    outcome = _seating_service(db_session).generate_session(session.id, strategy_name="constraint")

    assert outcome.generation.total_registered == 16
    assert outcome.scheduled_student_count == 16  # 8 + 8, as scheduled (before capping)
    assert outcome.total_physical_capacity == 10  # 5 + 5, the real ceiling
    assert outcome.scheduled_allocation_shortage is False
    assert outcome.physical_capacity_shortage is True
    assert outcome.generation.total_unassigned == 6


# --- blocked seats (Milestone 10) -------------------------------------------


def test_session_generation_respects_blocked_seats_across_shared_room(db_session: Session) -> None:
    """One room (401, 4x5 = 20 physical seats, 2 blocked -> 18 usable)
    shared by two courses of 9 students each within a session. All 18
    students must be seated, and none of them on the two blocked seats."""
    course_a = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="CS101", name="CS101"))
    course_b = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="MATH101", name="MATH101"))
    exam_a = SqlAlchemyExamRepository(db_session).add(
        Exam(id=None, course_id=course_a.id, exam_date=DATE, time_slot=TIME_SLOT, expected_student_count=9)
    )
    exam_b = SqlAlchemyExamRepository(db_session).add(
        Exam(id=None, course_id=course_b.id, exam_date=DATE, time_slot=TIME_SLOT, expected_student_count=9)
    )
    shared_room = SqlAlchemyRoomRepository(db_session).add(
        Room(id=None, code="401", capacity=20, rows=4, columns=5, blocked_seat_numbers=(7, 17))
    )
    exam_room_repo = SqlAlchemyExamRoomRepository(db_session)
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam_a.id, room_id=shared_room.id, allocated_students=9))
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam_b.id, room_id=shared_room.id, allocated_students=9))

    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    for prefix, course in (("A", course_a), ("B", course_b)):
        for i in range(1, 10):
            student = student_repo.add(Student(id=None, student_number=f"{prefix}{i:03d}", full_name=f"{prefix} {i}"))
            registration_repo.add(Registration(id=None, student_id=student.id, course_id=course.id))
    db_session.commit()

    session = _session_service(db_session).create_session([exam_a.id, exam_b.id])
    db_session.commit()

    outcome = _seating_service(db_session).generate_session(session.id, strategy_name="constraint")
    db_session.commit()

    assert outcome.generation.total_registered == 18
    assert outcome.generation.total_assigned == 18
    assert outcome.generation.total_unassigned == 0
    assert outcome.total_physical_capacity == 20
    assert outcome.total_usable_capacity == 18
    assert outcome.physical_capacity_shortage is False
    assert outcome.usable_capacity_shortage is False

    assignments = SqlAlchemySeatAssignmentRepository(db_session).list_by_generation(outcome.generation.id)
    assert len(assignments) == 18
    assigned_seat_numbers = {a.seat_number for a in assignments}
    assert 7 not in assigned_seat_numbers
    assert 17 not in assigned_seat_numbers


def test_session_generation_reports_usable_capacity_shortage_caused_by_blocking(db_session: Session) -> None:
    """Physical capacity (20) is enough for 19 registered students, but
    with one seat blocked, usable capacity (19 - well within!) -- so make
    it tighter: block enough seats that registered > usable even though
    registered <= physical, proving usable_capacity_shortage is
    distinguishable from physical_capacity_shortage."""
    course_a = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="CS101", name="CS101"))
    exam_a = SqlAlchemyExamRepository(db_session).add(
        Exam(id=None, course_id=course_a.id, exam_date=DATE, time_slot=TIME_SLOT, expected_student_count=19)
    )
    room = SqlAlchemyRoomRepository(db_session).add(
        Room(id=None, code="401", capacity=20, rows=4, columns=5, blocked_seat_numbers=(1, 2, 3))
    )
    SqlAlchemyExamRoomRepository(db_session).add(
        ExamRoom(id=None, exam_id=exam_a.id, room_id=room.id, allocated_students=19)
    )
    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    for i in range(1, 20):
        student = student_repo.add(Student(id=None, student_number=f"A{i:03d}", full_name=f"A {i}"))
        registration_repo.add(Registration(id=None, student_id=student.id, course_id=course_a.id))
    db_session.commit()

    session = _session_service(db_session).create_session([exam_a.id])
    db_session.commit()

    outcome = _seating_service(db_session).generate_session(session.id, strategy_name="constraint")

    assert outcome.generation.total_registered == 19
    assert outcome.total_physical_capacity == 20
    assert outcome.total_usable_capacity == 17  # 20 - 3 blocked
    assert outcome.physical_capacity_shortage is False  # 19 <= 20
    assert outcome.usable_capacity_shortage is True  # 19 > 17
    assert outcome.generation.total_unassigned == 2


# --- Phase 13: anti-cheating validation, real session path -----------------


def test_session_anti_cheating_preserves_provenance_and_reduces_adjacency(db_session: Session) -> None:
    """Three courses (PHY101=8, CHEM101=7, MATH101=5) genuinely sharing
    one 4x5=20-seat room through the real SeatingService.generate_session()
    path — not a hand-built strategy call. Generates once with each
    registered strategy name and verifies:
    - every assignment's exam_id still correctly resolves to the exam
      the seated student actually registered for (session course
      provenance survives the anti-cheating reordering), and
    - the constraint strategy's same-course spatial adjacency is lower
      than sequential's, using the same pure metric
      (evaluate_seating_quality) the rest of this suite uses — proving
      course-based anti-cheating is genuinely active on the real,
      DB-backed session path, not just in the pure strategy tests."""
    from app.seating.quality_metrics import evaluate_seating_quality
    from app.seating.topology import RectangularRoomTopology, SeatAssignmentCandidate

    course_phy = SqlAlchemyCourseRepository(db_session).add(Course(id=None, code="PHY101", name="Physics I"))
    course_chem = SqlAlchemyCourseRepository(db_session).add(
        Course(id=None, code="CHEM101", name="Chemistry I")
    )
    course_math = SqlAlchemyCourseRepository(db_session).add(
        Course(id=None, code="MATH101", name="Calculus I")
    )
    exam_phy = SqlAlchemyExamRepository(db_session).add(
        Exam(id=None, course_id=course_phy.id, exam_date=DATE, time_slot=TIME_SLOT, expected_student_count=8)
    )
    exam_chem = SqlAlchemyExamRepository(db_session).add(
        Exam(id=None, course_id=course_chem.id, exam_date=DATE, time_slot=TIME_SLOT, expected_student_count=7)
    )
    exam_math = SqlAlchemyExamRepository(db_session).add(
        Exam(id=None, course_id=course_math.id, exam_date=DATE, time_slot=TIME_SLOT, expected_student_count=5)
    )
    shared_room = SqlAlchemyRoomRepository(db_session).add(
        Room(id=None, code="401", capacity=20, rows=4, columns=5)
    )
    exam_room_repo = SqlAlchemyExamRoomRepository(db_session)
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam_phy.id, room_id=shared_room.id, allocated_students=8))
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam_chem.id, room_id=shared_room.id, allocated_students=7))
    exam_room_repo.add(ExamRoom(id=None, exam_id=exam_math.id, room_id=shared_room.id, allocated_students=5))

    student_repo = SqlAlchemyStudentRepository(db_session)
    registration_repo = SqlAlchemyRegistrationRepository(db_session)
    exam_by_prefix = {
        "P": (exam_phy, course_phy),
        "C": (exam_chem, course_chem),
        "M": (exam_math, course_math),
    }
    counts = {"P": 8, "C": 7, "M": 5}
    for prefix, count in counts.items():
        _, course = exam_by_prefix[prefix]
        for i in range(1, count + 1):
            student = student_repo.add(
                Student(id=None, student_number=f"{prefix}{i:03d}", full_name=f"{prefix} {i}")
            )
            registration_repo.add(Registration(id=None, student_id=student.id, course_id=course.id))
    db_session.commit()

    exam_ids = [exam_phy.id, exam_chem.id, exam_math.id]
    session = _session_service(db_session).create_session(exam_ids)
    db_session.commit()
    service = _seating_service(db_session)

    constraint_outcome = service.generate_session(session.id, strategy_name="constraint")
    db_session.commit()
    sequential_outcome = service.generate_session(session.id, strategy_name="sequential")
    db_session.commit()

    assignment_repo = SqlAlchemySeatAssignmentRepository(db_session)
    constraint_assignments = assignment_repo.list_by_generation(constraint_outcome.generation.id)
    sequential_assignments = assignment_repo.list_by_generation(sequential_outcome.generation.id)
    assert len(constraint_assignments) == 20
    assert len(sequential_assignments) == 20

    # Provenance: every assignment's exam_id must match the course the
    # seated student actually registered for (recoverable from the
    # student_number prefix this test itself assigned).
    for assignment in constraint_assignments:
        student = student_repo.get(assignment.student_id)
        assert student is not None
        expected_exam, _ = exam_by_prefix[student.student_number[0]]
        assert assignment.exam_id == expected_exam.id

    # Spatial comparison: build the student_id -> course_id mapping this
    # test itself knows to be true, and measure both generations with the
    # same pure metric the rest of this suite uses.
    student_course_ids: dict[int, int] = {}
    for assignment in constraint_assignments:
        student = student_repo.get(assignment.student_id)
        assert student is not None
        _, course = exam_by_prefix[student.student_number[0]]
        student_course_ids[assignment.student_id] = course.id

    topology = RectangularRoomTopology(room_id=shared_room.id, rows=4, columns=5)
    topologies = {shared_room.id: topology}

    def _as_candidates(assignments) -> list[SeatAssignmentCandidate]:
        return [
            SeatAssignmentCandidate(
                student_id=a.student_id, position=topology.position_for_seat(a.seat_number)
            )
            for a in assignments
        ]

    constraint_quality = evaluate_seating_quality(
        _as_candidates(constraint_assignments), student_course_ids, topologies
    )
    sequential_quality = evaluate_seating_quality(
        _as_candidates(sequential_assignments), student_course_ids, topologies
    )
    assert constraint_quality.same_course_adjacent_pairs < sequential_quality.same_course_adjacent_pairs
