"""Plain dataclasses shared by the parser and the import service.

No FastAPI, no SQLAlchemy — these are what the parser hands to the
service, and what the service hands back to the API layer to render.
"""

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class NormalizedRegistrationRow:
    """One (student, course) registration fact extracted from a CSV, after
    whitespace normalization and in-file dedup/conflict resolution.

    `student_name`/`subject_name` are each the first-seen value for that
    student_id/subject_code within the file — never an arbitrarily altered
    or truncated value.
    """

    line_number: int
    student_id: str
    student_name: str
    subject_code: str
    subject_name: str


@dataclass(frozen=True)
class ValidationError:
    """A row (or the file as a whole) that could not be processed."""

    line_number: int | None
    field: str | None
    message: str


@dataclass(frozen=True)
class Conflict:
    """An identifier that maps to more than one distinct name.

    Detected either within a single file (two rows disagree) or between
    the file and already-stored data (see RegistrationImportService). The
    canonical stored value is never overwritten by a conflicting one —
    this record exists so a human can resolve it deliberately.
    """

    kind: str  # "student_name" | "course_name"
    key: str  # student_id or subject_code
    line_number: int
    existing_value: str
    incoming_value: str


@dataclass(frozen=True)
class ParsedRegistrationCSV:
    """Output of parsing a registration CSV, before anything touches a database."""

    rows_read: int
    records: list[NormalizedRegistrationRow]
    validation_errors: list[ValidationError]
    conflicts: list[Conflict]
    duplicate_rows: int


class ImportStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class RegistrationImportResult:
    """Structured, human-renderable outcome of a registration import.

    A successful (or partial) result never means "some records were
    silently dropped" — every excluded row is accounted for in either
    `validation_errors` or `conflicts`.
    """

    status: ImportStatus
    rows_read: int
    students_created: int = 0
    students_existing: int = 0
    courses_created: int = 0
    courses_existing: int = 0
    registrations_created: int = 0
    registrations_existing: int = 0
    duplicate_rows: int = 0
    validation_errors: list[ValidationError] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
