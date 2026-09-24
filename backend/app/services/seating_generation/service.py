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

from app.domain import SeatAssignment, SeatingGeneration, Student
from app.repositories.course_repository import CourseRepository
from app.repositories.exam_repository import ExamRepository
from app.repositories.exam_room_repository import ExamRoomRepository
from app.repositories.registration_repository import RegistrationRepository
from app.repositories.room_repository import RoomRepository
from app.repositories.seat_assignment_repository import SeatAssignmentRepository
from app.repositories.seating_generation_repository import SeatingGenerationRepository
from app.repositories.student_repository import StudentRepository
from app.seating import RoomAllocation, SeatingEngine, get_strategy
from app.services.seating_generation.records import ExamNotFoundError, SeatingGenerationOutcome


def _student_sort_key(student: Student) -> tuple[int, str]:
    """Deterministic ascending order by student number. Comparing by
    length first, then lexicographically, gives correct numeric ordering
    for same-format numeric IDs (this data's case) without assuming every
    ID is purely numeric."""
    return (len(student.student_number), student.student_number)


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
    ) -> None:
        self._exams = exam_repository
        self._exam_rooms = exam_room_repository
        self._rooms = room_repository
        self._courses = course_repository
        self._registrations = registration_repository
        self._students = student_repository
        self._seating_generations = seating_generation_repository
        self._seat_assignments = seat_assignment_repository

    def generate(self, exam_id: int, strategy_name: str = "sequential") -> SeatingGenerationOutcome:
        exam = self._exams.get(exam_id)
        if exam is None:
            raise ExamNotFoundError(exam_id)

        room_allocations = self._load_room_allocations(exam_id)
        students = self._load_registered_students(exam.course_id)

        engine = SeatingEngine(get_strategy(strategy_name))
        result = engine.run(exam, students, room_allocations)

        generation = self._seating_generations.add(
            SeatingGeneration(
                id=None,
                exam_id=exam_id,
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
            available_capacity=result.available_capacity,
            unassigned_student_ids=result.unassigned_student_ids,
            scheduled_allocation_shortage=result.scheduled_allocation_shortage,
            physical_capacity_shortage=result.physical_capacity_shortage,
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
        registrations = self._registrations.list_by_course(course_id)
        students = []
        for registration in registrations:
            student = self._students.get(registration.student_id)
            assert student is not None
            students.append(student)
        return sorted(students, key=_student_sort_key)
