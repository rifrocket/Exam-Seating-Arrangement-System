from collections.abc import Iterable
from dataclasses import dataclass, field


class InvalidRoomTopologyError(ValueError):
    """Raised when a Room is constructed with a rows/columns combination
    that doesn't describe its capacity, or with blocked seat numbers that
    don't describe a valid configuration — never silently accepted, never
    silently corrected."""


@dataclass
class Room:
    """A physical room with a seating capacity, and optionally an explicit
    rectangular seat layout (`rows` x `columns`) plus specific blocked
    seat numbers within it.

    Mirrors the (room, capacity) shape of the legacy `input/locations.csv`,
    which existing code never actually read — this is the first time room
    capacity becomes a real, queryable fact rather than a number buried in
    a schedule spreadsheet.

    `rows`/`columns` are optional, and always both-or-neither: a room
    without them is not an error, it simply has *no configured topology*
    yet — sequential seating never needs one (it only reads `capacity`),
    but constraint seating does (see `RoomTopologyProvider`). Topology is
    never inferred from capacity alone (a 10-seat room could be 2x5, 1x10,
    or something else entirely) — it must be given explicitly, and
    `__post_init__` enforces `rows * columns == capacity` exactly,
    rejecting anything else immediately rather than letting a mismatched
    layout reach a strategy.

    `blocked_seat_numbers` (Milestone 10) marks specific seats within that
    layout as physically unusable (a broken chair, a maintenance closure —
    anything short of the room no longer existing). It requires a
    configured topology (blocked seat *numbers* are meaningless without a
    layout to number seats against) and every entry must be within
    `1..capacity`; stored normalized (deduplicated, sorted) so two Rooms
    with the same effective blocked seats always compare equal. An empty
    tuple (the default) means "no blocked seats" — the common case, and
    the only case for every room that predates this milestone.
    """

    id: int | None
    code: str
    capacity: int
    rows: int | None = None
    columns: int | None = None
    blocked_seat_numbers: tuple[int, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        has_rows = self.rows is not None
        has_columns = self.columns is not None
        if has_rows != has_columns:
            raise InvalidRoomTopologyError(
                f"Room '{self.code}' must specify both rows and columns, or neither "
                f"(got rows={self.rows}, columns={self.columns})."
            )
        if not has_rows:
            if self.blocked_seat_numbers:
                raise InvalidRoomTopologyError(
                    f"Room '{self.code}' has blocked seat numbers but no configured topology "
                    "(rows/columns) — blocked seat numbers are meaningless without a layout."
                )
            return
        assert self.rows is not None and self.columns is not None
        if self.rows < 1 or self.columns < 1:
            raise InvalidRoomTopologyError(
                f"Room '{self.code}' topology must have at least one row and column "
                f"(got rows={self.rows}, columns={self.columns})."
            )
        if self.rows * self.columns != self.capacity:
            raise InvalidRoomTopologyError(
                f"Room '{self.code}' topology (rows={self.rows}, columns={self.columns} = "
                f"{self.rows * self.columns} seat(s)) does not match its capacity ({self.capacity})."
            )
        self.blocked_seat_numbers = _normalize_blocked_seats(self.code, self.blocked_seat_numbers, self.capacity)

    @property
    def has_topology(self) -> bool:
        return self.rows is not None and self.columns is not None


def _normalize_blocked_seats(code: str, seat_numbers: Iterable[int], capacity: int) -> tuple[int, ...]:
    seen: set[int] = set()
    for seat_number in seat_numbers:
        if not (1 <= seat_number <= capacity):
            raise InvalidRoomTopologyError(
                f"Room '{code}' has an invalid blocked seat number {seat_number} — must be between "
                f"1 and {capacity} (its capacity)."
            )
        seen.add(seat_number)  # a set: a duplicate is simply a no-op
    return tuple(sorted(seen))
