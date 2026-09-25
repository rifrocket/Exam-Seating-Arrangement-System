"""Physical seat topology — the spatial layer future seating strategies
(constraint-based, then optimization-based) need in order to reason about
"next to," "same row," "same column," and "how far apart."

`SequentialSeatingStrategy` never needs any of this: it only cares about a
per-room ordinal (`seat_number`). This module exists purely as foundation
for strategies that do not exist yet.

Deliberately minimal for this milestone: `SeatPosition` and `SeatTopology`
are a pure in-memory representation, not a persisted room layout. There is
no database table, no room-layout editor, and no frontend seat map here —
`RectangularRoomTopology` derives its positions from two integers (rows,
columns) each time it's asked, exactly like a test fixture would. A future
milestone can introduce a persisted, non-rectangular layout by adding
another `SeatTopology` implementation; nothing above this layer (the
constraint model, or a future strategy) depends on rooms being
rectangular — they only depend on the `SeatTopology` interface.

Nothing in this module imports FastAPI, SQLAlchemy, HTTP, the filesystem,
ReportLab, or a repository.
"""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SeatPosition:
    """One seat's location: which room, its per-room ordinal (matching
    `SeatAssignmentRecord.seat_number`, so a real assignment can be mapped
    to a position without inventing a second numbering scheme), and its
    row/column within that room's layout."""

    room_id: int
    seat_number: int
    row: int
    column: int


@dataclass(frozen=True)
class SeatAssignmentCandidate:
    """A proposed (not yet persisted) student-to-seat placement, in the
    spatial terms a constraint needs. Distinct from
    `app.seating.models.SeatAssignmentRecord`: that type is the engine's
    persistence-facing output (room_id + seat_number only); this one is the
    constraint layer's input, expressed as a full `SeatPosition` so a
    constraint never has to re-derive row/column itself."""

    student_id: int
    position: SeatPosition


class SeatTopology(ABC):
    """Answers spatial questions about seats within a single room's
    layout. A future persisted, non-rectangular layout implements this
    same interface; nothing above this layer needs to know which
    implementation it's talking to."""

    @abstractmethod
    def same_row(self, a: SeatPosition, b: SeatPosition) -> bool: ...

    @abstractmethod
    def same_column(self, a: SeatPosition, b: SeatPosition) -> bool: ...

    @abstractmethod
    def is_adjacent(self, a: SeatPosition, b: SeatPosition) -> bool: ...

    @abstractmethod
    def distance(self, a: SeatPosition, b: SeatPosition) -> float: ...


class RectangularRoomTopology(SeatTopology):
    """The simplest possible layout: `rows` x `columns` seats, numbered
    left-to-right then top-to-bottom starting at 1 (row-major), e.g. for
    rows=2, columns=5:

        1  2  3  4  5
        6  7  8  9  10

    A seat's row/column are derived from its seat_number on demand — there
    is nothing to persist. `is_adjacent` treats any of the eight
    surrounding cells (including diagonals) as adjacent, which is the
    conservative definition an anti-cheating "must not sit next to" rule
    needs: a diagonal neighbor is still within arm's reach.

    Comparisons across two different rooms are always "not related" —
    `same_row`/`same_column`/`is_adjacent` are `False` and `distance` is
    infinite, rather than raising, so a constraint can compare every pair
    of currently-seated students without first filtering by room itself.
    """

    def __init__(self, room_id: int, rows: int, columns: int) -> None:
        if rows < 1 or columns < 1:
            raise ValueError(f"A room layout needs at least one row and column, got rows={rows}, columns={columns}")
        self.room_id = room_id
        self.rows = rows
        self.columns = columns

    @property
    def capacity(self) -> int:
        return self.rows * self.columns

    def position_for_seat(self, seat_number: int) -> SeatPosition:
        if not (1 <= seat_number <= self.capacity):
            raise ValueError(
                f"seat_number {seat_number} is out of range for a {self.rows}x{self.columns} "
                f"room (capacity {self.capacity})"
            )
        zero_based = seat_number - 1
        row, column = divmod(zero_based, self.columns)
        return SeatPosition(room_id=self.room_id, seat_number=seat_number, row=row, column=column)

    def _same_room(self, a: SeatPosition, b: SeatPosition) -> bool:
        return a.room_id == b.room_id

    def same_row(self, a: SeatPosition, b: SeatPosition) -> bool:
        return self._same_room(a, b) and a.row == b.row

    def same_column(self, a: SeatPosition, b: SeatPosition) -> bool:
        return self._same_room(a, b) and a.column == b.column

    def is_adjacent(self, a: SeatPosition, b: SeatPosition) -> bool:
        if not self._same_room(a, b) or a == b:
            return False
        return abs(a.row - b.row) <= 1 and abs(a.column - b.column) <= 1

    def distance(self, a: SeatPosition, b: SeatPosition) -> float:
        if not self._same_room(a, b):
            return math.inf
        return math.hypot(a.row - b.row, a.column - b.column)
