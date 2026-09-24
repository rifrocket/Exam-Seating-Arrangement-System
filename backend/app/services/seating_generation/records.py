from dataclasses import dataclass

from app.domain import SeatingGeneration


class ExamNotFoundError(Exception):
    def __init__(self, exam_id: int) -> None:
        super().__init__(f"Exam {exam_id} not found.")
        self.exam_id = exam_id


@dataclass
class SeatingGenerationOutcome:
    """What the service returns for one generation run.

    `generation` is the persisted SeatingGeneration record (has an id).
    The remaining fields are useful for the immediate API response but
    intentionally NOT persisted fields on SeatingGeneration — that entity
    records only what it was asked to (exam, strategy, status, total
    registered/assigned/unassigned, capacity shortage); adding fields
    nothing else reads back later would be speculative. If a future
    milestone needs to inspect `scheduled_allocation_shortage` or
    `physical_capacity_shortage` for a *past* generation (not just the one
    just run), that's the point to add persisted columns — not before.
    """

    generation: SeatingGeneration
    scheduled_student_count: int
    total_physical_capacity: int
    available_capacity: int
    unassigned_student_ids: list[int]
    scheduled_allocation_shortage: bool
    physical_capacity_shortage: bool
