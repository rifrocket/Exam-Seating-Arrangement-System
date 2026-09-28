from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class GenerationStatus(str, Enum):
    """Outcome of a seating generation run.

    PARTIAL exists because a successful generation must never silently
    lose students: if some students could not be seated, that is a
    distinct, visible outcome, not a hidden truncation.
    """

    PENDING = "pending"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class InvalidSeatingGenerationTargetError(ValueError):
    """A SeatingGeneration must reference exactly one of exam_id or
    session_id — never both (there's no single meaning for "this run
    belongs to both an exam and a session") and never neither (every
    generation must be traceable to something it was generated for)."""


@dataclass
class SeatingGeneration:
    """One identifiable, versioned run of a seating strategy — for a
    single Exam (Milestone 4) or, as of Milestone 9, for an
    ExaminationSession spanning multiple exams/courses. Exactly one of
    `exam_id`/`session_id` is set; `__post_init__` enforces this so a
    generation can never end up ambiguous about what it was generated for.

    Every generation records what it was asked to seat and what actually
    happened, so "how many students were registered vs. assigned vs. left
    over" is always an explicit, queryable fact rather than something you'd
    have to infer by diffing files (as the legacy `left.json` forced you to).
    """

    id: int | None
    exam_id: int | None
    session_id: int | None
    strategy_name: str
    status: GenerationStatus
    total_registered: int
    total_assigned: int
    total_unassigned: int
    capacity_shortage: bool
    warnings: list[str] = field(default_factory=list)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if (self.exam_id is None) == (self.session_id is None):
            raise InvalidSeatingGenerationTargetError(
                f"SeatingGeneration must reference exactly one of exam_id or session_id "
                f"(got exam_id={self.exam_id}, session_id={self.session_id})."
            )
