from dataclasses import dataclass


@dataclass(frozen=True)
class StudentSeatingContext:
    """The minimum per-student attribute set a seating constraint might
    need — never a generic metadata dict, never a SQLAlchemy model, and
    never fetched by a constraint itself. Only `course_id` exists today
    because only `SeparateCoursesConstraint` needs one; add a field only
    when a real constraint needs it.

    Lives in `app.domain` (not `app.seating`) so both a single-exam
    strategy (`app.seating.strategies.constraint`) and the multi-exam
    `app.domain.examination_session.build_session_participants` can
    produce it without either depending on the other.
    """

    student_id: int
    course_id: int
