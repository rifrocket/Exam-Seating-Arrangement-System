from dataclasses import dataclass


@dataclass
class Course:
    """A course/subject that students register for and sit exams in."""

    id: int | None
    code: str
    name: str
