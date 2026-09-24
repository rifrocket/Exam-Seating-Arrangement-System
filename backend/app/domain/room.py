from dataclasses import dataclass


@dataclass
class Room:
    """A physical room with a seating capacity.

    Mirrors the (room, capacity) shape of the legacy `input/locations.csv`,
    which existing code never actually read — this is the first time room
    capacity becomes a real, queryable fact rather than a number buried in
    a schedule spreadsheet.
    """

    id: int | None
    code: str
    capacity: int
