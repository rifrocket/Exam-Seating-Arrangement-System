"""ReportService: assembles the plain data a ReportLab adapter needs,
strictly from a *persisted* SeatingGeneration's own SeatAssignment rows.

Important invariant (Milestone 5): a report is a read of an existing
generation, never a trigger to compute one. This service never calls
SeatingService, never touches the seating engine/strategies, and never
re-derives assignments from current registrations — only from the
SeatAssignment rows already stored under the requested generation_id.
That's what keeps generation A's report from ever reflecting generation
B's (or the current live schedule's) data, even though they may share the
same exam.
"""

from app.domain import Course, Exam, SeatAssignment, SeatingGeneration
from app.reports.models import (
    RangeReportData,
    RangeReportRow,
    SeatingReportData,
    SeatingReportRoom,
    SeatingReportRow,
)
from app.repositories.course_repository import CourseRepository
from app.repositories.exam_repository import ExamRepository
from app.repositories.exam_room_repository import ExamRoomRepository
from app.repositories.room_repository import RoomRepository
from app.repositories.seat_assignment_repository import SeatAssignmentRepository
from app.repositories.seating_generation_repository import SeatingGenerationRepository
from app.repositories.student_repository import StudentRepository
from app.services.reports.records import EmptyGenerationError, GenerationNotFoundError


class ReportService:
    def __init__(
        self,
        seating_generation_repository: SeatingGenerationRepository,
        seat_assignment_repository: SeatAssignmentRepository,
        exam_repository: ExamRepository,
        exam_room_repository: ExamRoomRepository,
        course_repository: CourseRepository,
        room_repository: RoomRepository,
        student_repository: StudentRepository,
    ) -> None:
        self._seating_generations = seating_generation_repository
        self._seat_assignments = seat_assignment_repository
        self._exams = exam_repository
        self._exam_rooms = exam_room_repository
        self._courses = course_repository
        self._rooms = room_repository
        self._students = student_repository

    def build_seating_report_data(self, generation_id: int) -> SeatingReportData:
        generation, assignments, exam, course, room_order = self._load(generation_id)

        rows_by_room: dict[int, list[SeatingReportRow]] = {}
        for assignment in assignments:
            student = self._students.get(assignment.student_id)
            assert student is not None
            rows_by_room.setdefault(assignment.room_id, []).append(
                SeatingReportRow(
                    seat_number=assignment.seat_number,
                    student_number=student.student_number,
                    student_name=student.full_name,
                )
            )

        rooms = []
        for room_id, room_code in room_order:
            rows = rows_by_room.get(room_id)
            if not rows:
                continue  # a scheduled room with zero seated students this run
            rows.sort(key=lambda r: r.seat_number)
            rooms.append(SeatingReportRoom(room_code=room_code, rows=rows))

        return SeatingReportData(
            course_code=course.code,
            course_name=course.name,
            exam_date=exam.exam_date.isoformat(),
            time_slot=exam.time_slot,
            generation_id=generation_id,
            strategy_name=generation.strategy_name,
            status=generation.status.value,
            rooms=rooms,
        )

    def build_range_report_data(self, generation_id: int) -> RangeReportData:
        generation, assignments, exam, course, room_order = self._load(generation_id)

        entries_by_room: dict[int, list[tuple[int, str]]] = {}
        for assignment in assignments:
            student = self._students.get(assignment.student_id)
            assert student is not None
            entries_by_room.setdefault(assignment.room_id, []).append(
                (assignment.seat_number, student.student_number)
            )

        rows = []
        for room_id, room_code in room_order:
            entries = entries_by_room.get(room_id)
            if not entries:
                continue
            entries.sort(key=lambda e: e[0])
            rows.append(
                RangeReportRow(
                    room_code=room_code,
                    start_student_number=entries[0][1],
                    end_student_number=entries[-1][1],
                    assigned_count=len(entries),
                )
            )

        return RangeReportData(
            course_code=course.code,
            course_name=course.name,
            generation_id=generation_id,
            rows=rows,
        )

    def _load(
        self, generation_id: int
    ) -> tuple[SeatingGeneration, list[SeatAssignment], Exam, Course, list[tuple[int, str]]]:
        generation = self._seating_generations.get(generation_id)
        if generation is None:
            raise GenerationNotFoundError(generation_id)

        assignments = self._seat_assignments.list_by_generation(generation_id)
        if not assignments:
            raise EmptyGenerationError(generation_id)

        exam = self._exams.get(generation.exam_id)
        assert exam is not None
        course = self._courses.get(exam.course_id)
        assert course is not None

        # Canonical room order = the exam's own ExamRoom insertion order
        # (see docs/architecture.md's "Deterministic ordering" section) —
        # the same order the seating strategy filled rooms in, not an
        # incidental alphabetical-by-code ordering.
        room_order = []
        for exam_room in self._exam_rooms.list_by_exam(generation.exam_id):
            room = self._rooms.get(exam_room.room_id)
            assert room is not None
            room_order.append((room.id, room.code))

        return generation, assignments, exam, course, room_order
