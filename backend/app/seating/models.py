"""Pure input/output value objects for the seating engine boundary.

These are deliberately NOT in app/domain/: they are computation-scoped
shapes specific to "what a SeatingStrategy consumes and produces," not
persisted entities the rest of the app shares. `RoomAllocation` is the
service's flattened join of ExamRoom + Room (a strategy never queries a
repository, so it can't look up a room's capacity itself); `SeatingResult`
carries figures that are useful for the immediate API response but are
not all persisted on SeatingGeneration (see app/services/seating_generation
for which are kept and why).
"""

from dataclasses import dataclass, field

from app.domain import GenerationStatus


@dataclass(frozen=True)
class RoomAllocation:
    """One room's scheduled allocation for an exam, with its physical
    capacity already joined in — the flattened form a strategy needs
    without querying anything itself."""

    room_id: int
    room_code: str
    allocated_students: int
    capacity: int


@dataclass(frozen=True)
class SeatAssignmentRecord:
    """One student's computed seat, before persistence."""

    student_id: int
    room_id: int
    seat_number: int


@dataclass(frozen=True)
class SeatingResult:
    """Output of a SeatingStrategy run.

    Three distinct counts, never collapsed into one (see docs/architecture.md):
    - `scheduled_student_count`: the schedule's own plan (sum of each
      room's `allocated_students`, as scheduled — even if that number
      exceeds the room's physical capacity).
    - `available_capacity`: the actually-usable seats after protecting
      against any room's allocation exceeding its own capacity
      (sum of min(allocated_students, capacity) per room).
    - `registered_student_count` / `assigned_student_count` /
      `unassigned_student_count`: who was supposed to be seated vs. who
      actually was.

    `capacity_shortage` is true exactly when `unassigned_student_count > 0`
    — in this model, a student is only ever left unassigned because there
    were not enough usable seats for them (never assigned beyond a room's
    physical capacity, never invented seats, never dropped without a seat
    existing for someone else instead).
    """

    status: GenerationStatus
    registered_student_count: int
    scheduled_student_count: int
    available_capacity: int
    assigned_student_count: int
    unassigned_student_count: int
    capacity_shortage: bool
    assignments: list[SeatAssignmentRecord]
    unassigned_student_ids: list[int]
    warnings: list[str] = field(default_factory=list)
