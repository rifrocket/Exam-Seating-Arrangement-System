"""SeatingService: the application service that sits between the API and
the (pure, DB-free) seating engine.

Responsibilities: load exam/room/registration/student data via
repositories, build the strategy's input, invoke the engine, and persist
the result. The strategy itself never touches a repository or a session.

Unlike registration/schedule import, generation is NOT idempotent by
design — each call creates a brand-new SeatingGeneration plus its own
SeatAssignment rows, never overwriting a previous run. That's what makes
future regeneration and generation-history comparison possible; merging
runs together the way imports merge rows would destroy exactly the
history a later milestone needs.
"""

from app.domain import (
    SeatAssignment,
    SeatingGeneration,
    Student,
    build_session_participants,
)
from app.repositories.course_repository import CourseRepository
from app.repositories.exam_repository import ExamRepository
from app.repositories.exam_room_repository import ExamRoomRepository
from app.repositories.examination_session_repository import ExaminationSessionRepository
from app.repositories.registration_repository import RegistrationRepository
from app.repositories.room_repository import RoomRepository
from app.repositories.seat_assignment_repository import SeatAssignmentRepository
from app.repositories.seating_generation_repository import SeatingGenerationRepository
from app.repositories.student_repository import StudentRepository
from app.seating import ConstraintSeatingStrategy, RoomAllocation, SeatingEngine, get_strategy
from app.services.seating_generation.records import (
    ExamNotFoundError,
    SeatingGenerationOutcome,
    SessionNotFoundError,
)
from app.services.seating_generation.room_topology_provider import RepositoryRoomTopologyProvider


def _student_sort_key(student: Student) -> tuple[int, str]:
    """Deterministic ascending order by student number. Comparing by
    length first, then lexicographically, gives correct numeric ordering
    for same-format numeric IDs (this data's case) without assuming every
    ID is purely numeric."""
    return (len(student.student_number), student.student_number)


def _merge_shared_room_allocations(allocations: list[RoomAllocation]) -> list[RoomAllocation]:
    """Two exams in the same session can share a physical room — see
    `ConflictingRoomAllocationError`'s docstring for why that's fine as
    long as the combined allocation still fits. `SeatingStrategy.generate()`
    itself treats two `RoomAllocation` entries with the same `room_id` as
    a data-integrity error (correctly, for the single-exam path, which
    should never see a duplicate), so this collapses each shared room's
    separate per-exam entries into one, summing `allocated_students` —
    never inventing a number, since each part was already explicitly
    recorded against its own exam (validated at session-creation time).
    Room order is preserved by first appearance, matching the order exams
    were processed in."""
    merged: dict[int, RoomAllocation] = {}
    order: list[int] = []
    for allocation in allocations:
        existing = merged.get(allocation.room_id)
        if existing is None:
            merged[allocation.room_id] = allocation
            order.append(allocation.room_id)
        else:
            merged[allocation.room_id] = RoomAllocation(
                room_id=existing.room_id,
                room_code=existing.room_code,
                allocated_students=existing.allocated_students + allocation.allocated_students,
                capacity=existing.capacity,
            )
    return [merged[room_id] for room_id in order]


def _session_student_sort_key(course_id: int, student: Student) -> tuple[int, int, str]:
    """Deterministic ascending order by (course_id, student_number) for a
    multi-course session. This only fixes each course's own *relative*
    order (still ascending student_number within a course) for stable
    tie-breaking — it does not determine the strategy's actual placement
    order. `ConstraintSeatingStrategy` re-interleaves this list by course
    internally before placing anyone (see `app.seating.anti_cheating`),
    specifically so this course-grouped shape here does *not* let one
    course claim a long unbroken run of placement turns before another
    gets one. A single-exam generation never calls this — it keeps using
    `_student_sort_key` unchanged, since one exam only ever has one
    course_id anyway."""
    return (course_id, len(student.student_number), student.student_number)


class SeatingService:
    def __init__(
        self,
        exam_repository: ExamRepository,
        exam_room_repository: ExamRoomRepository,
        room_repository: RoomRepository,
        course_repository: CourseRepository,
        registration_repository: RegistrationRepository,
        student_repository: StudentRepository,
        seating_generation_repository: SeatingGenerationRepository,
        seat_assignment_repository: SeatAssignmentRepository,
        examination_session_repository: ExaminationSessionRepository | None = None,
    ) -> None:
        self._exams = exam_repository
        self._exam_rooms = exam_room_repository
        self._rooms = room_repository
        self._courses = course_repository
        self._registrations = registration_repository
        self._students = student_repository
        self._seating_generations = seating_generation_repository
        self._seat_assignments = seat_assignment_repository
        # Optional (defaults to None) so existing callers that only ever
        # use generate() — never generate_session() — don't have to
        # start passing a repository they'd never use.
        self._sessions = examination_session_repository

    def generate(self, exam_id: int, strategy_name: str = "sequential") -> SeatingGenerationOutcome:
        exam = self._exams.get(exam_id)
        if exam is None:
            raise ExamNotFoundError(exam_id)

        room_allocations = self._load_room_allocations(exam_id)
        students = self._load_registered_students(exam.course_id)

        # Every strategy is constructed with this uniformly (see
        # SeatingStrategy's own base __init__) — only ConstraintSeatingStrategy
        # actually reads it. Built fresh per call, like the repositories
        # this service already holds, rather than cached: it's a thin,
        # stateless read-through wrapper over room_repository.
        topology_provider = RepositoryRoomTopologyProvider(self._rooms)
        engine = SeatingEngine(get_strategy(strategy_name, topology_provider=topology_provider))
        result = engine.run(exam, students, room_allocations)

        generation = self._seating_generations.add(
            SeatingGeneration(
                id=None,
                exam_id=exam_id,
                session_id=None,
                strategy_name=engine.strategy_name,
                status=result.status,
                total_registered=result.registered_student_count,
                total_assigned=result.assigned_student_count,
                total_unassigned=result.unassigned_student_count,
                capacity_shortage=result.capacity_shortage,
                warnings=result.warnings,
            )
        )
        assert generation.id is not None

        for assignment in result.assignments:
            self._seat_assignments.add(
                SeatAssignment(
                    id=None,
                    seating_generation_id=generation.id,
                    exam_id=exam_id,
                    room_id=assignment.room_id,
                    student_id=assignment.student_id,
                    seat_number=assignment.seat_number,
                )
            )

        return SeatingGenerationOutcome(
            generation=generation,
            scheduled_student_count=result.scheduled_student_count,
            total_physical_capacity=result.total_physical_capacity,
            total_usable_capacity=result.total_usable_capacity,
            available_capacity=result.available_capacity,
            unassigned_student_ids=result.unassigned_student_ids,
            scheduled_allocation_shortage=result.scheduled_allocation_shortage,
            physical_capacity_shortage=result.physical_capacity_shortage,
            usable_capacity_shortage=result.usable_capacity_shortage,
        )

    def generate_session(
        self, session_id: int, strategy_name: str = "constraint"
    ) -> SeatingGenerationOutcome:
        """The session counterpart to `generate()` — same engine, same
        strategies, same `SeatingResult`/`SeatingGenerationOutcome`
        contract, just built from several exams' combined room
        allocations and registered students instead of one exam's.
        `generate()` itself is completely untouched by this method's
        existence."""
        if self._sessions is None:
            raise RuntimeError("SeatingService was constructed without an ExaminationSessionRepository.")

        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        exams = []
        for exam_id in session.exam_ids:
            exam = self._exams.get(exam_id)
            assert exam is not None  # session creation already validated these exist
            exams.append(exam)

        raw_room_allocations: list[RoomAllocation] = []
        students_by_exam_id: dict[int, list[Student]] = {}
        course_id_by_exam_id: dict[int, int] = {}
        for exam in exams:
            assert exam.id is not None
            raw_room_allocations.extend(self._load_room_allocations(exam.id))
            # Unsorted here on purpose — _load_registered_students'
            # own sort only matters for the single-exam path; the
            # combined, session-wide sort happens once, below.
            students_by_exam_id[exam.id] = self._unsorted_registered_students(exam.course_id)
            course_id_by_exam_id[exam.id] = exam.course_id
        room_allocations = _merge_shared_room_allocations(raw_room_allocations)

        participants = build_session_participants(session, students_by_exam_id, course_id_by_exam_id)
        student_course_ids = {p.student_id: p.course_id for p in participants}
        students_by_id = {s.id: s for students in students_by_exam_id.values() for s in students}
        ordered_students = sorted(
            students_by_id.values(),
            key=lambda s: _session_student_sort_key(student_course_ids[s.id], s),
        )
        exam_id_by_student_id = {
            student.id: exam_id for exam_id, students in students_by_exam_id.items() for student in students
        }

        topology_provider = RepositoryRoomTopologyProvider(self._rooms)
        strategy = get_strategy(strategy_name, topology_provider=topology_provider)
        if isinstance(strategy, ConstraintSeatingStrategy):
            # ConstraintSeatingStrategy's own default course-mapping (built
            # from a single exam.course_id) doesn't apply to a session —
            # give it the real, per-student course ids directly instead.
            # See ConstraintSeatingStrategy's module docstring.
            strategy = ConstraintSeatingStrategy(
                topology_provider=topology_provider, student_course_ids=student_course_ids
            )
        engine = SeatingEngine(strategy)

        # The interface takes one Exam; a session has several. The first
        # exam stands in purely for that slot's identity (exam.id, used
        # only in an already-prevented duplicate-room-id error message) —
        # none of its other fields are read, since student_course_ids
        # above makes exam.course_id irrelevant here. See
        # ConstraintSeatingStrategy's module docstring.
        representative_exam = exams[0]
        result = engine.run(representative_exam, ordered_students, room_allocations)

        generation = self._seating_generations.add(
            SeatingGeneration(
                id=None,
                exam_id=None,
                session_id=session_id,
                strategy_name=engine.strategy_name,
                status=result.status,
                total_registered=result.registered_student_count,
                total_assigned=result.assigned_student_count,
                total_unassigned=result.unassigned_student_count,
                capacity_shortage=result.capacity_shortage,
                warnings=result.warnings,
            )
        )
        assert generation.id is not None

        for assignment in result.assignments:
            self._seat_assignments.add(
                SeatAssignment(
                    id=None,
                    seating_generation_id=generation.id,
                    exam_id=exam_id_by_student_id[assignment.student_id],
                    room_id=assignment.room_id,
                    student_id=assignment.student_id,
                    seat_number=assignment.seat_number,
                )
            )

        return SeatingGenerationOutcome(
            generation=generation,
            scheduled_student_count=result.scheduled_student_count,
            total_physical_capacity=result.total_physical_capacity,
            total_usable_capacity=result.total_usable_capacity,
            available_capacity=result.available_capacity,
            unassigned_student_ids=result.unassigned_student_ids,
            scheduled_allocation_shortage=result.scheduled_allocation_shortage,
            physical_capacity_shortage=result.physical_capacity_shortage,
            usable_capacity_shortage=result.usable_capacity_shortage,
        )

    def _load_room_allocations(self, exam_id: int) -> list[RoomAllocation]:
        exam_rooms = self._exam_rooms.list_by_exam(exam_id)
        allocations = []
        for exam_room in exam_rooms:
            room = self._rooms.get(exam_room.room_id)
            assert room is not None
            allocations.append(
                RoomAllocation(
                    room_id=exam_room.room_id,
                    room_code=room.code,
                    allocated_students=exam_room.allocated_students,
                    capacity=room.capacity,
                )
            )
        return allocations

    def _load_registered_students(self, course_id: int) -> list[Student]:
        return sorted(self._unsorted_registered_students(course_id), key=_student_sort_key)

    def _unsorted_registered_students(self, course_id: int) -> list[Student]:
        registrations = self._registrations.list_by_course(course_id)
        students = []
        for registration in registrations:
            student = self._students.get(registration.student_id)
            assert student is not None
            students.append(student)
        return students
