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
    `scheduled_student_count`, `available_capacity`, and
    `unassigned_student_ids` are useful for the immediate API response
    but are intentionally NOT persisted fields on SeatingGeneration —
    that entity records only what Milestone 4 was asked to record
    (exam, strategy, status, total registered/assigned/unassigned,
    capacity shortage); adding fields nothing else reads yet would be
    speculative.
    """

    generation: SeatingGeneration
    scheduled_student_count: int
    available_capacity: int
    unassigned_student_ids: list[int]
