from dataclasses import dataclass


class InvalidRoomTopologyError(ValueError):
    """Raised when a Room is constructed with a rows/columns combination
    that doesn't describe its capacity — never silently accepted, never
    silently corrected."""


@dataclass
class Room:
    """A physical room with a seating capacity, and optionally an explicit
    rectangular seat layout (`rows` x `columns`).

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
    """

    id: int | None
    code: str
    capacity: int
    rows: int | None = None
    columns: int | None = None

    def __post_init__(self) -> None:
        has_rows = self.rows is not None
        has_columns = self.columns is not None
        if has_rows != has_columns:
            raise InvalidRoomTopologyError(
                f"Room '{self.code}' must specify both rows and columns, or neither "
                f"(got rows={self.rows}, columns={self.columns})."
            )
        if not has_rows:
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

    @property
    def has_topology(self) -> bool:
        return self.rows is not None and self.columns is not None
