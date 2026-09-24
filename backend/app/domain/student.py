from dataclasses import dataclass


@dataclass
class Student:
    """A student who can be registered for courses and seated in exams.

    ``full_name`` is stored complete and unabbreviated. Any shortening for
    a fixed-width PDF column is presentation formatting done in reports/,
    never a mutation of the canonical name.
    """

    id: int | None
    student_number: str
    full_name: str
