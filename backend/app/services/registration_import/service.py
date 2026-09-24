"""RegistrationImportService: turns parsed CSV records into persisted
Student/Course/Registration rows.

Independently testable without HTTP — it depends only on the repository
interfaces (app.repositories), never on FastAPI or a concrete SQLAlchemy
session type.

Conflict policy (deliberately simple, not automatic resolution):
a stored Student's or Course's canonical name is never overwritten once
set. If an incoming row disagrees with the stored name, that disagreement
is reported as a Conflict and the row's registration is still recorded
against the existing (identity-matched) student/course — the identifier
(student_id / subject_code) is what makes the entity the same one; the
name mismatch is a data-quality signal for a human to resolve, not a
reason to drop an otherwise-valid registration.
"""

from app.domain import Course, Registration, Student
from app.repositories.course_repository import CourseRepository
from app.repositories.registration_repository import RegistrationRepository
from app.repositories.student_repository import StudentRepository
from app.services.registration_import.parser import parse_registration_csv
from app.services.registration_import.records import (
    Conflict,
    ImportStatus,
    NormalizedRegistrationRow,
    RegistrationImportResult,
)


class RegistrationImportService:
    def __init__(
        self,
        student_repository: StudentRepository,
        course_repository: CourseRepository,
        registration_repository: RegistrationRepository,
    ) -> None:
        self._students = student_repository
        self._courses = course_repository
        self._registrations = registration_repository

    def import_csv(self, csv_text: str) -> RegistrationImportResult:
        parsed = parse_registration_csv(csv_text)

        if not parsed.records and parsed.validation_errors and parsed.rows_read == 0:
            # Nothing could even be attempted: no header, missing columns,
            # or a malformed file that failed before any row was read.
            return RegistrationImportResult(
                status=ImportStatus.FAILED,
                rows_read=parsed.rows_read,
                validation_errors=parsed.validation_errors,
                conflicts=parsed.conflicts,
                duplicate_rows=parsed.duplicate_rows,
            )

        result = RegistrationImportResult(
            status=ImportStatus.SUCCESS,
            rows_read=parsed.rows_read,
            validation_errors=list(parsed.validation_errors),
            conflicts=list(parsed.conflicts),
            duplicate_rows=parsed.duplicate_rows,
        )

        # Per-run caches so a student/course referenced by many rows is
        # resolved (and counted) exactly once, without re-querying the DB.
        resolved_students: dict[str, Student] = {}
        resolved_courses: dict[str, Course] = {}

        for row in parsed.records:
            student = self._resolve_student(row, resolved_students, result)
            course = self._resolve_course(row, resolved_courses, result)
            self._resolve_registration(student, course, result)

        if result.validation_errors or result.conflicts:
            result.status = ImportStatus.PARTIAL
        return result

    def _resolve_student(
        self,
        row: NormalizedRegistrationRow,
        cache: dict[str, Student],
        result: RegistrationImportResult,
    ) -> Student:
        if row.student_id in cache:
            return cache[row.student_id]

        existing = self._students.get_by_student_number(row.student_id)
        if existing is not None:
            if existing.full_name != row.student_name:
                result.conflicts.append(
                    Conflict(
                        "student_name",
                        row.student_id,
                        row.line_number,
                        existing.full_name,
                        row.student_name,
                    )
                )
            result.students_existing += 1
            cache[row.student_id] = existing
            return existing

        created = self._students.add(Student(id=None, student_number=row.student_id, full_name=row.student_name))
        result.students_created += 1
        cache[row.student_id] = created
        return created

    def _resolve_course(
        self,
        row: NormalizedRegistrationRow,
        cache: dict[str, Course],
        result: RegistrationImportResult,
    ) -> Course:
        if row.subject_code in cache:
            return cache[row.subject_code]

        existing = self._courses.get_by_code(row.subject_code)
        if existing is not None:
            if existing.name != row.subject_name:
                result.conflicts.append(
                    Conflict(
                        "course_name",
                        row.subject_code,
                        row.line_number,
                        existing.name,
                        row.subject_name,
                    )
                )
            result.courses_existing += 1
            cache[row.subject_code] = existing
            return existing

        created = self._courses.add(Course(id=None, code=row.subject_code, name=row.subject_name))
        result.courses_created += 1
        cache[row.subject_code] = created
        return created

    def _resolve_registration(self, student: Student, course: Course, result: RegistrationImportResult) -> None:
        assert student.id is not None
        assert course.id is not None

        existing = self._registrations.get_by_student_and_course(student.id, course.id)
        if existing is not None:
            result.registrations_existing += 1
            return

        self._registrations.add(Registration(id=None, student_id=student.id, course_id=course.id))
        result.registrations_created += 1
