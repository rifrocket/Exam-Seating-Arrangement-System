"""ExaminationSession: a common seating session containing one or more
Exams — distinct from Exam itself.

    Exam
        = one course's scheduled examination (course, date, time, rooms).
    ExaminationSession
        = a shared seating event grouping one or more compatible Exams
          together — the foundation multi-course seating will build on.

This module only establishes the domain concept and its validation. It
does not change what `POST /exams/{exam_id}/seating/generate` does, does
not merge or redistribute `ExamRoom` allocations across exams, and is not
persisted (see docs/architecture.md for why — this milestone is a domain
concept, not a shipped multi-course workflow).

A session containing exactly one exam is always valid — the existing
MVP's single-exam generation is, conceptually, a session of size one,
without anything about today's behavior needing to change.

Pure Python: no FastAPI, no SQLAlchemy, no repository. Building a real
session (which needs each exam's actual schedule and registered
students) is the caller's job — a service loads that data via
repositories and passes plain `Exam`/`Student` objects in here.
"""

from dataclasses import dataclass
from datetime import date

from app.domain.exam import Exam
from app.domain.student import Student
from app.domain.student_seating_context import StudentSeatingContext


class IncompatibleExamScheduleError(ValueError):
    """Raised when the exams given to `build_examination_session` do not
    all share the same `exam_date` and `time_slot`. A session represents
    one shared seating event, not an arbitrary bundle of exams — silently
    picking one exam's schedule, or combining exams that were never meant
    to share a room, would misrepresent what actually happens."""


class DuplicateStudentInSessionError(ValueError):
    """Raised when the same student is registered in more than one exam
    within a single session. This milestone does not define what "the
    same student seated in two exams at once" should mean, so it is
    rejected outright rather than silently deduplicated or double-seated."""


@dataclass(frozen=True)
class ExaminationSession:
    id: int | None
    exam_ids: list[int]
    exam_date: date
    time_slot: str


def build_examination_session(exams: list[Exam]) -> ExaminationSession:
    """Pure construction + validation: every exam must share the same
    `exam_date` and `time_slot`. Raises `IncompatibleExamScheduleError`
    rather than guessing which schedule the session "really" means."""
    if not exams:
        raise ValueError("An examination session needs at least one exam.")
    for exam in exams:
        if exam.id is None:
            raise ValueError("Every exam in a session must already be persisted (have an id).")

    first = exams[0]
    for exam in exams[1:]:
        if exam.exam_date != first.exam_date or exam.time_slot != first.time_slot:
            raise IncompatibleExamScheduleError(
                f"Exam {exam.id} ({exam.exam_date} {exam.time_slot}) is not compatible with exam "
                f"{first.id} ({first.exam_date} {first.time_slot}) — every exam in a session must "
                "share the same date and time slot."
            )

    return ExaminationSession(
        id=None,
        exam_ids=[exam.id for exam in exams if exam.id is not None],
        exam_date=first.exam_date,
        time_slot=first.time_slot,
    )


def build_session_participants(
    session: ExaminationSession,
    students_by_exam_id: dict[int, list[Student]],
    course_id_by_exam_id: dict[int, int],
) -> list[StudentSeatingContext]:
    """Combines each of the session's exams' registered students into one
    participant list, retaining exactly the per-student attributes a
    constraint needs (student_id, course_id) — never a database model,
    never fetched by a constraint itself; the caller supplies both maps
    already loaded via repositories.

    A student registered in more than one of this session's exams is
    rejected outright (`DuplicateStudentInSessionError`) rather than
    silently deduplicated or seated twice."""
    first_seen_in_exam: dict[int, int] = {}
    contexts: list[StudentSeatingContext] = []
    for exam_id in session.exam_ids:
        course_id = course_id_by_exam_id[exam_id]
        for student in students_by_exam_id.get(exam_id, []):
            assert student.id is not None
            if student.id in first_seen_in_exam:
                raise DuplicateStudentInSessionError(
                    f"Student {student.id} is registered in both exam {first_seen_in_exam[student.id]} "
                    f"and exam {exam_id} within the same session."
                )
            first_seen_in_exam[student.id] = exam_id
            contexts.append(StudentSeatingContext(student_id=student.id, course_id=course_id))
    return contexts
