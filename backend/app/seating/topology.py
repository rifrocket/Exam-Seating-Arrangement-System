"""Physical seat topology — the spatial layer seating strategies need in
order to reason about "next to," "same row," "same column," "how far
apart," and (Milestone 10) "can a student even sit here at all."

Deliberately minimal: `SeatPosition` and `SeatTopology` are a pure
in-memory representation, not a persisted room layout. There is no seat
database table, no room-layout editor, and no frontend seat map here —
`RectangularRoomTopology` derives its positions from two integers (rows,
columns) plus an optional set of blocked seat numbers, each time it's
asked. A future milestone can introduce a persisted, non-rectangular
layout by adding another `SeatTopology` implementation; nothing above
this layer (the constraint model, or a strategy) depends on rooms being
rectangular — they only depend on the `SeatTopology` interface.

Physical existence vs. usability (Milestone 10): a blocked seat is still
a real position in the room — `all_positions()` still returns it, with
`available=False` — it simply cannot be assigned a student
(`usable_positions()` excludes it). This distinction is what lets a
constraint reason about "seat 3 is empty because it's physically
missing/broken" differently from "seat 3 is empty because no one's been
placed there yet" — a future anti-cheating rule may care about that
difference; nothing does yet.

Nothing in this module imports FastAPI, SQLAlchemy, HTTP, the filesystem,
ReportLab, or a repository.
"""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SeatPosition:
    """One seat's physical location: which room, its per-room ordinal
    (matching `SeatAssignmentRecord.seat_number`, so a real assignment can
    be mapped to a position without inventing a second numbering scheme),
    its row/column within that room's layout, and whether it can
    currently be assigned a student at all (`available`).

    `available=False` means the position physically exists but is
    blocked (a broken chair, a maintenance closure, anything that makes a
    real physical seat currently unusable) — it is not the same thing as
    "unoccupied." A strategy must never assign a student to an
    unavailable position; nothing else about it (row/column/distance
    queries) changes because of unavailability.
    """

    room_id: int
    seat_number: int
    row: int
    column: int
    available: bool = True


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
    """Answers spatial and availability questions about seats within a
    single room's layout. A future persisted, non-rectangular layout
    implements this same interface; nothing above this layer needs to
    know which implementation it's talking to."""

    @abstractmethod
    def position_for_seat(self, seat_number: int) -> SeatPosition: ...

    @abstractmethod
    def all_positions(self) -> list[SeatPosition]:
        """Every physical position in the room, in deterministic
        seat-number order, regardless of availability."""
        ...

    @abstractmethod
    def usable_positions(self) -> list[SeatPosition]:
        """Every position a student could actually be assigned to, in the
        same deterministic order `all_positions()` uses — i.e.
        `all_positions()` filtered to `available=True`, never reordered."""
        ...

    @property
    @abstractmethod
    def physical_capacity(self) -> int:
        """How many seat positions physically exist, regardless of
        availability. Never affected by blocked seats."""
        ...

    @property
    @abstractmethod
    def usable_capacity(self) -> int:
        """How many positions can currently accept a student —
        `physical_capacity` minus however many are blocked."""
        ...

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

    `blocked_seat_numbers` (Milestone 10) marks specific seat numbers as
    physically unusable — validated eagerly (every number must be within
    1..rows*columns; duplicates are harmless, since they're stored as a
    set). A blocked seat is still a real position (`all_positions()`
    includes it, `position_for_seat()` still resolves it, spatial queries
    still work on it) — only `usable_positions()`/`usable_capacity`
    exclude it, and only a strategy consulting those is guaranteed to
    never place a student there.

    Comparisons across two different rooms are always "not related" —
    `same_row`/`same_column`/`is_adjacent` are `False` and `distance` is
    infinite, rather than raising, so a constraint can compare every pair
    of currently-seated students without first filtering by room itself.
    """

    def __init__(
        self,
        room_id: int,
        rows: int,
        columns: int,
        blocked_seat_numbers: "frozenset[int] | set[int] | tuple[int, ...] | list[int] | None" = None,
    ) -> None:
        if rows < 1 or columns < 1:
            raise ValueError(f"A room layout needs at least one row and column, got rows={rows}, columns={columns}")
        self.room_id = room_id
        self.rows = rows
        self.columns = columns
        capacity = rows * columns
        blocked: set[int] = set()
        for seat_number in blocked_seat_numbers or ():
            if not (1 <= seat_number <= capacity):
                raise ValueError(
                    f"Blocked seat number {seat_number} is out of range for a {rows}x{columns} room "
                    f"(valid range is 1..{capacity})."
                )
            blocked.add(seat_number)  # a set: a duplicate is simply a no-op
        self._blocked = frozenset(blocked)

    @property
    def physical_capacity(self) -> int:
        return self.rows * self.columns

    @property
    def usable_capacity(self) -> int:
        return self.physical_capacity - len(self._blocked)

    def position_for_seat(self, seat_number: int) -> SeatPosition:
        if not (1 <= seat_number <= self.physical_capacity):
            raise ValueError(
                f"seat_number {seat_number} is out of range for a {self.rows}x{self.columns} "
                f"room (capacity {self.physical_capacity})"
            )
        zero_based = seat_number - 1
        row, column = divmod(zero_based, self.columns)
        return SeatPosition(
            room_id=self.room_id,
            seat_number=seat_number,
            row=row,
            column=column,
            available=seat_number not in self._blocked,
        )

    def all_positions(self) -> list[SeatPosition]:
        return [self.position_for_seat(n) for n in range(1, self.physical_capacity + 1)]

    def usable_positions(self) -> list[SeatPosition]:
        return [position for position in self.all_positions() if position.available]

    def _same_room(self, a: SeatPosition, b: SeatPosition) -> bool:
        return a.room_id == b.room_id

    def same_row(self, a: SeatPosition, b: SeatPosition) -> bool:
        return self._same_room(a, b) and a.row == b.row

    def same_column(self, a: SeatPosition, b: SeatPosition) -> bool:
        return self._same_room(a, b) and a.column == b.column

    def is_adjacent(self, a: SeatPosition, b: SeatPosition) -> bool:
        if not self._same_room(a, b) or (a.row, a.column) == (b.row, b.column):
            return False  # a seat is never adjacent to itself, regardless of seat_number/availability
        return abs(a.row - b.row) <= 1 and abs(a.column - b.column) <= 1

    def distance(self, a: SeatPosition, b: SeatPosition) -> float:
        if not self._same_room(a, b):
            return math.inf
        return math.hypot(a.row - b.row, a.column - b.column)
