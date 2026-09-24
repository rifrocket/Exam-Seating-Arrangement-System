from dataclasses import dataclass
from datetime import date


@dataclass
class Exam:
    """One scheduled sitting of a course: a course on a given date and time slot.

    Room allocation and seating are derived from an Exam, not folded into it,
    so a single exam can later span multiple rooms without changing this shape.
    """

    id: int | None
    course_id: int
    exam_date: date
    time_slot: str
