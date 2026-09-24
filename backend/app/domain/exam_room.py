from dataclasses import dataclass


@dataclass
class ExamRoom:
    """One room's scheduled student allocation for a given exam.

    `allocated_students` is the legacy CSV's "No. of Students/ Room" value
    for this specific room-row — separate from Room.capacity (the room's
    physical limit) and from Exam.expected_student_count (the exam's
    overall headcount). Comparing these three is exactly what the future
    SeatingEngine needs; collapsing them here would destroy that ability.
    """

    id: int | None
    exam_id: int
    room_id: int
    allocated_students: int
