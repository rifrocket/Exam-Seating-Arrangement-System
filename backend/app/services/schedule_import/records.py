"""Plain dataclasses shared by the schedule parser and the import service.

No FastAPI, no SQLAlchemy.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


@dataclass(frozen=True)
class NormalizedExamRoomRow:
    """One room-row's scheduled allocation, before any DB lookup."""

    line_number: int
    room_code: str
    allocated_students: int


@dataclass(frozen=True)
class NormalizedExamGroup:
    """All room-rows for one (course, date, time) exam, after in-file
    dedup/conflict resolution — still nothing DB-touched yet."""

    course_code: str
    course_name: str
    exam_date: date
    time_slot: str
    day_label: str | None
    expected_student_count: int
    first_line_number: int
    exam_rooms: list[NormalizedExamRoomRow]


@dataclass(frozen=True)
class ValidationError:
    line_number: int | None
    field: str | None
    message: str


@dataclass(frozen=True)
class Conflict:
    """An identifier that maps to more than one distinct value.

    Kinds: "course_name" (same course code, different name — checked both
    within the file and against the stored Course), "expected_student_count"
    (same exam, different overall headcount across its room-rows or against
    an existing stored Exam), "exam_room_allocation" (same exam+room,
    different allocation across rows or against an existing ExamRoom).
    """

    kind: str
    key: str
    line_number: int
    existing_value: str
    incoming_value: str


@dataclass(frozen=True)
class Warning:
    """A non-blocking, structural fact worth surfacing but not an error —
    e.g. a room's scheduled allocation exceeding its physical capacity."""

    kind: str
    line_number: int | None
    message: str


@dataclass(frozen=True)
class ParsedScheduleCSV:
    """Output of parsing a schedule CSV, before anything touches a database."""

    rows_read: int
    exam_groups: list[NormalizedExamGroup]
    validation_errors: list[ValidationError]
    conflicts: list[Conflict]
    duplicate_rows: int


class ImportStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class ScheduleImportResult:
    """Structured, human-renderable outcome of a schedule import."""

    status: ImportStatus
    rows_read: int
    exams_created: int = 0
    exams_existing: int = 0
    exam_rooms_created: int = 0
    exam_rooms_existing: int = 0
    duplicate_rows: int = 0
    validation_errors: list[ValidationError] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
