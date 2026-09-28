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
    - `total_usable_capacity` (Milestone 10): sum of each assigned room's
      *usable* seat count — `total_physical_capacity` minus however many
      of those physical seats are currently blocked (see
      `app.seating.topology.SeatTopology.usable_capacity`). Equal to
      `total_physical_capacity` for every room with no blocked seats
      (i.e. every exam that predates this milestone) — this is an
      additive field, never a redefinition of `total_physical_capacity`,
      which still means exactly what it always has.
    - `available_capacity`: the seats this generation actually tries to
      fill — sum of min(allocated_students, capacity, usable_capacity)
      per room. This is an *operational* number (it drives the assignment
      loop below), not a diagnostic one; see the shortage flags for
      diagnosis.
    - `registered_student_count` / `assigned_student_count` /
      `unassigned_student_count`: who was supposed to be seated vs. who
      actually was.

    Three distinct shortage diagnoses — students can end up unassigned
    for any of these reasons, and conflating them (as a single
    `capacity_shortage` flag once did) hides which one actually happened:
    - `scheduled_allocation_shortage`: `registered_student_count >
      scheduled_student_count`. The schedule simply didn't allocate
      enough seats for this exam — independent of whether the rooms
      involved could *physically* have held more. Fixable by scheduling
      more/larger rooms; the rooms already assigned may have had room to
      spare.
    - `physical_capacity_shortage`: `registered_student_count >
      total_physical_capacity`. Even using every seat in every room
      assigned to this exam, there is nowhere for everyone to sit. Not
      fixable without assigning additional or larger rooms. **Never
      affected by blocked seats** — a room's physical capacity doesn't
      change just because some of its seats are temporarily unusable.
    - `usable_capacity_shortage` (Milestone 10):
      `registered_student_count > total_usable_capacity`, but *not*
      `physical_capacity_shortage`. This is the "there was physically
      enough room, but some of those seats are currently blocked" case —
      distinct from both flags above, and must never be reported as a
      `physical_capacity_shortage` (the room itself is not smaller; some
      of its seats are just temporarily unavailable).
      A generation can have any combination of these three flags true.

    `capacity_shortage` is kept, **unchanged in meaning**, for
    continuity with Milestone 4 and because it is what
    `SeatingGeneration.capacity_shortage` persists: true exactly when
    `unassigned_student_count > 0`, i.e. "at least one registered student
    was not seated, for whatever reason." It answers "did anyone go
    unassigned?"; the flags above answer "why." Do not read
    `capacity_shortage` as meaning any one specific cause — use the
    specific flag for that claim.
    """

    status: GenerationStatus
    registered_student_count: int
    scheduled_student_count: int
    total_physical_capacity: int
    total_usable_capacity: int
    available_capacity: int
    assigned_student_count: int
    unassigned_student_count: int
    capacity_shortage: bool
    scheduled_allocation_shortage: bool
    physical_capacity_shortage: bool
    usable_capacity_shortage: bool
    assignments: list[SeatAssignmentRecord]
    unassigned_student_ids: list[int]
    warnings: list[str] = field(default_factory=list)
