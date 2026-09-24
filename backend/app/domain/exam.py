from dataclasses import dataclass
from datetime import date


@dataclass
class Exam:
    """One scheduled sitting of a course: a course on a given date and time slot.

    Room allocation and seating are derived from an Exam via ExamRoom, not
    folded into it, so a single exam can span multiple rooms.

    `expected_student_count` is the exam's overall expected headcount (the
    legacy CSV's "No. of Students" column) — distinct from any single
    room's scheduled allocation (see ExamRoom.allocated_students) and from
    a room's physical capacity (see Room.capacity). Never collapse these
    into one number; that was the legacy system's actual bug.

    `time_slot` is a normalized "HH:MM-HH:MM" string, not a real time
    object — the source data has no AM/PM marker, so treating it as a
    timezone-naive display/identity string (rather than inventing a
    disambiguation) is the honest representation.

    `day_label` is the raw, unvalidated "Day" text from the source row —
    kept only for display; it is never cross-checked against the actual
    weekday of `exam_date` (the source data isn't reliable enough for that
    to be meaningful, and re-deriving it would silently mask a bad date).
    """

    id: int | None
    course_id: int
    exam_date: date
    time_slot: str
    expected_student_count: int
    day_label: str | None = None
