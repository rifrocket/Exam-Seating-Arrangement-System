"""ScheduleImportService: turns parsed schedule CSV groups into persisted
Exam/ExamRoom rows.

Independently testable without HTTP — depends only on repository
interfaces, never on FastAPI or a concrete SQLAlchemy session type.

Course/Room policy: courses and rooms are never created from a schedule
import. Registration data is the source of truth for courses (per the
approved Milestone 3 scope); rooms come from their own seed/import. An
unknown course code or room code excludes just that exam group / that
room-row and is reported as a validation error — nothing is silently
dropped, and nothing is silently invented.

Conflict policy (same shape as registration import): a stored Exam's
expected_student_count and an ExamRoom's allocated_students are never
overwritten once set. A disagreeing incoming value is reported as a
Conflict; the already-stored fact wins.
"""

from app.domain import Exam, ExamRoom
from app.repositories.course_repository import CourseRepository
from app.repositories.exam_repository import ExamRepository
from app.repositories.exam_room_repository import ExamRoomRepository
from app.repositories.room_repository import RoomRepository
from app.services.schedule_import.parser import parse_schedule_csv
from app.services.schedule_import.records import (
    Conflict,
    ImportStatus,
    NormalizedExamGroup,
    NormalizedExamRoomRow,
    ScheduleImportResult,
    ValidationError,
    Warning,
)


class ScheduleImportService:
    def __init__(
        self,
        course_repository: CourseRepository,
        room_repository: RoomRepository,
        exam_repository: ExamRepository,
        exam_room_repository: ExamRoomRepository,
    ) -> None:
        self._courses = course_repository
        self._rooms = room_repository
        self._exams = exam_repository
        self._exam_rooms = exam_room_repository

    def import_csv(self, csv_text: str) -> ScheduleImportResult:
        parsed = parse_schedule_csv(csv_text)

        if not parsed.exam_groups and parsed.validation_errors and parsed.rows_read == 0:
            return ScheduleImportResult(
                status=ImportStatus.FAILED,
                rows_read=parsed.rows_read,
                validation_errors=parsed.validation_errors,
                conflicts=parsed.conflicts,
                duplicate_rows=parsed.duplicate_rows,
            )

        result = ScheduleImportResult(
            status=ImportStatus.SUCCESS,
            rows_read=parsed.rows_read,
            validation_errors=list(parsed.validation_errors),
            conflicts=list(parsed.conflicts),
            duplicate_rows=parsed.duplicate_rows,
        )

        for group in parsed.exam_groups:
            self._import_exam_group(group, result)

        if result.validation_errors or result.conflicts:
            result.status = ImportStatus.PARTIAL
        return result

    def _import_exam_group(self, group: NormalizedExamGroup, result: ScheduleImportResult) -> None:
        course = self._courses.get_by_code(group.course_code)
        if course is None:
            result.validation_errors.append(
                ValidationError(
                    group.first_line_number,
                    "Course Code",
                    f"Unknown course code '{group.course_code}' — import registrations for it first.",
                )
            )
            return
        assert course.id is not None

        if course.name != group.course_name:
            result.conflicts.append(
                Conflict("course_name", group.course_code, group.first_line_number, course.name, group.course_name)
            )

        existing_exam = self._exams.get_by_identity(course.id, group.exam_date, group.time_slot)
        if existing_exam is not None:
            if existing_exam.expected_student_count != group.expected_student_count:
                result.conflicts.append(
                    Conflict(
                        "expected_student_count",
                        f"{group.course_code}|{group.exam_date.isoformat()}|{group.time_slot}",
                        group.first_line_number,
                        str(existing_exam.expected_student_count),
                        str(group.expected_student_count),
                    )
                )
            result.exams_existing += 1
            exam = existing_exam
        else:
            exam = self._exams.add(
                Exam(
                    id=None,
                    course_id=course.id,
                    exam_date=group.exam_date,
                    time_slot=group.time_slot,
                    expected_student_count=group.expected_student_count,
                    day_label=group.day_label,
                )
            )
            result.exams_created += 1

        assert exam.id is not None
        for exam_room_row in group.exam_rooms:
            self._import_exam_room(exam.id, group, exam_room_row, result)

    def _import_exam_room(
        self,
        exam_id: int,
        group: NormalizedExamGroup,
        exam_room_row: NormalizedExamRoomRow,
        result: ScheduleImportResult,
    ) -> None:
        room = self._rooms.get_by_code(exam_room_row.room_code)
        if room is None:
            result.validation_errors.append(
                ValidationError(
                    exam_room_row.line_number,
                    "Room(s)",
                    f"Unknown room code '{exam_room_row.room_code}' — seed rooms first.",
                )
            )
            return
        assert room.id is not None

        if exam_room_row.allocated_students > room.capacity:
            result.warnings.append(
                Warning(
                    "capacity_exceeded",
                    exam_room_row.line_number,
                    f"Room '{room.code}' scheduled allocation ({exam_room_row.allocated_students}) "
                    f"exceeds its capacity ({room.capacity}).",
                )
            )

        existing_exam_room = self._exam_rooms.get_by_exam_and_room(exam_id, room.id)
        if existing_exam_room is not None:
            if existing_exam_room.allocated_students != exam_room_row.allocated_students:
                result.conflicts.append(
                    Conflict(
                        "exam_room_allocation",
                        f"{group.course_code}|{group.exam_date.isoformat()}|{group.time_slot}|{room.code}",
                        exam_room_row.line_number,
                        str(existing_exam_room.allocated_students),
                        str(exam_room_row.allocated_students),
                    )
                )
            result.exam_rooms_existing += 1
        else:
            self._exam_rooms.add(
                ExamRoom(
                    id=None,
                    exam_id=exam_id,
                    room_id=room.id,
                    allocated_students=exam_room_row.allocated_students,
                )
            )
            result.exam_rooms_created += 1
