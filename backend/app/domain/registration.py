from dataclasses import dataclass


@dataclass
class Registration:
    """A student's registration for a course.

    A student may hold many registrations (one per course); a course may
    have many registered students. This is the join fact the legacy CSV
    already represented as one row per (student, course) pair.
    """

    id: int | None
    student_id: int
    course_id: int
