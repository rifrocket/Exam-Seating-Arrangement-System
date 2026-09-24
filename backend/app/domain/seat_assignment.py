from dataclasses import dataclass


@dataclass
class SeatAssignment:
    """One student's assignment to a room for a given exam, produced by a
    seating generation run.

    `seat_number` is a per-room running position (matching the legacy
    "Seating#" column), not a reference to a physical Seat entity — that
    entity is intentionally deferred until a strategy needs seat-level
    adjacency (anti-cheating, constraint seating).
    """

    id: int | None
    seating_generation_id: int
    exam_id: int
    room_id: int
    student_id: int
    seat_number: int
