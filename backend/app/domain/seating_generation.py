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


@dataclass
class SeatingGeneration:
    """One identifiable, versioned run of a seating strategy for an exam.

    Every generation records what it was asked to seat and what actually
    happened, so "how many students were registered vs. assigned vs. left
    over" is always an explicit, queryable fact rather than something you'd
    have to infer by diffing files (as the legacy `left.json` forced you to).
    """

    id: int | None
    exam_id: int
    strategy_name: str
    status: GenerationStatus
    total_registered: int
    total_assigned: int
    total_unassigned: int
    capacity_shortage: bool
    warnings: list[str] = field(default_factory=list)
    created_at: datetime | None = None
