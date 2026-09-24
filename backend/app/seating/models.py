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

    Counts, never collapsed into one another (see docs/architecture.md):
    - `scheduled_student_count`: the schedule's own plan — sum of each
      room's `allocated_students`, exactly as scheduled, even if that
      number exceeds the room's physical capacity.
    - `total_physical_capacity`: sum of each assigned room's `capacity`,
      completely independent of what was scheduled — "how many seats
      physically exist across the rooms assigned to this exam."
    - `available_capacity`: the seats this generation actually tries to
      fill — sum of min(allocated_students, capacity) per room. This is
      an *operational* number (it drives the assignment loop below), not
      a diagnostic one; see the two shortage flags for diagnosis.
    - `registered_student_count` / `assigned_student_count` /
      `unassigned_student_count`: who was supposed to be seated vs. who
      actually was.

    Two distinct shortage diagnoses — students can end up unassigned for
    either reason, and conflating them (as a single `capacity_shortage`
    flag once did) hides which one actually happened:
    - `scheduled_allocation_shortage`: `registered_student_count >
      scheduled_student_count`. The schedule simply didn't allocate
      enough seats for this exam — independent of whether the rooms
      involved could *physically* have held more. Fixable by scheduling
      more/larger rooms; the rooms already assigned may have had room to
      spare.
    - `physical_capacity_shortage`: `registered_student_count >
      total_physical_capacity`. Even using every seat in every room
      assigned to this exam, there is nowhere for everyone to sit. Not
      fixable without assigning additional or larger rooms.
      A generation can have either flag true, both, or neither.

    `capacity_shortage` is kept, **unchanged in meaning**, for
    continuity with Milestone 4 and because it is what
    `SeatingGeneration.capacity_shortage` persists: true exactly when
    `unassigned_student_count > 0`, i.e. "at least one registered student
    was not seated, for whatever reason." It answers "did anyone go
    unassigned?"; the two flags above answer "why." Do not read
    `capacity_shortage` as meaning "physical capacity was the cause" —
    use `physical_capacity_shortage` for that specific claim.
    """

    status: GenerationStatus
    registered_student_count: int
    scheduled_student_count: int
    total_physical_capacity: int
    available_capacity: int
    assigned_student_count: int
    unassigned_student_count: int
    capacity_shortage: bool
    scheduled_allocation_shortage: bool
    physical_capacity_shortage: bool
    assignments: list[SeatAssignmentRecord]
    unassigned_student_ids: list[int]
    warnings: list[str] = field(default_factory=list)
