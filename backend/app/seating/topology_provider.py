"""RoomTopologyProvider: the boundary between "a room" (which today only
has a `code` and a physical `capacity` — see `app.domain.Room`) and "a
seat topology" (`app.seating.topology.SeatTopology`) a constraint-aware
strategy needs.

`Room` deliberately does not carry rows/columns — inferring geometry from
capacity alone (e.g. "capacity 10 implies 2 rows x 5 columns") would be
fabricating a physical fact the data doesn't actually have; two 10-seat
rooms can have completely different real layouts. So a topology has to
come from somewhere else: `RoomTopologyProvider` is that "somewhere else,"
kept as an explicit interface so a real, persisted, admin-configurable
room layout can be introduced later (see docs/architecture.md) without
`ConstraintSeatingStrategy` changing at all — only a new provider
implementation would be added.

`StaticRoomTopologyProvider` is a fixed, in-memory `room_code -> (rows,
columns)` mapping — useful for tests and synthetic scenarios, but no
longer the production default as of Milestone 8: `Room` now has its own
optional `rows`/`columns` (see `app.domain.room.Room`), and the actual
production provider (`RepositoryRoomTopologyProvider`) reads *those*,
rather than a hardcoded room-code table. It lives in
`app.services.seating_generation`, not here, specifically because it
needs a repository — the same reason `SeatingService` itself, not
anything in `app.seating`, is the layer allowed to query one.

Nothing in this module imports FastAPI, SQLAlchemy, HTTP, the filesystem,
ReportLab, or a repository.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from app.seating.topology import RectangularRoomTopology, SeatTopology


class UnknownRoomTopologyError(KeyError):
    """The room itself isn't recognized (no topology to even consider)."""


class RoomTopologyMissingError(ValueError):
    """The room is recognized but has no configured topology — this is
    normal, valid state for a room used only with sequential seating; it
    only becomes an error when constraint seating actually needs one."""


class RoomTopologyMismatchError(ValueError):
    """A configured topology's seat count doesn't exactly equal the room's
    actual physical capacity — never silently truncated or padded."""


class RoomTopologyProvider(ABC):
    @abstractmethod
    def get_topology(self, room_id: int, room_code: str, capacity: int) -> SeatTopology:
        """Return the seat topology for the room identified by
        `room_id`/`room_code`, whose actual physical capacity is
        `capacity`.

        Must raise `UnknownRoomTopologyError` if no topology is configured
        for this room, and `RoomTopologyMismatchError` if the configured
        topology's seat count does not exactly equal `capacity` — a
        provider must never silently create seats beyond physical
        capacity, and never silently truncate a topology to fit."""
        ...


class StaticRoomTopologyProvider(RoomTopologyProvider):
    """Looks a room's (rows, columns) up by `room_code` in a fixed,
    caller-supplied mapping. `room_id` is only used to give the returned
    `SeatTopology` the correct room identity (`RectangularRoomTopology`
    needs it to answer cross-room comparisons correctly) — the lookup key
    is the human-meaningful `room_code`, not the database-generated id,
    since a demo/test configuration naturally speaks in terms of the room
    codes an admin would recognize (e.g. "401"), not internal row ids that
    vary across databases."""

    def __init__(self, layouts: Mapping[str, tuple[int, int]]) -> None:
        self._layouts = dict(layouts)

    def get_topology(self, room_id: int, room_code: str, capacity: int) -> SeatTopology:
        dims = self._layouts.get(room_code)
        if dims is None:
            raise UnknownRoomTopologyError(
                f"No seat topology configured for room '{room_code}'. Configured rooms: "
                f"{sorted(self._layouts)}"
            )
        rows, columns = dims
        topology = RectangularRoomTopology(room_id=room_id, rows=rows, columns=columns)
        if topology.capacity != capacity:
            raise RoomTopologyMismatchError(
                f"Configured topology for room '{room_code}' has {topology.capacity} seat(s) "
                f"({rows}x{columns}), but the room's actual physical capacity is {capacity}. "
                "A topology must exactly match the room it describes."
            )
        return topology
