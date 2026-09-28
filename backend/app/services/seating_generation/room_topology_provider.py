"""RepositoryRoomTopologyProvider: the production RoomTopologyProvider,
reading each room's configured `rows`/`columns` (Milestone 8, see
`app.domain.room.Room`) through a `RoomRepository`.

Lives here, not in `app.seating`, specifically because it needs a
repository — the same reason `SeatingService` itself, not anything in
`app.seating`, is the layer allowed to query one. The `SeatTopology` it
returns is still pure; `ConstraintSeatingStrategy` never sees this class
or the repository behind it, only the `RoomTopologyProvider` interface.
"""

from app.repositories.room_repository import RoomRepository
from app.seating.topology import RectangularRoomTopology, SeatTopology
from app.seating.topology_provider import (
    RoomTopologyMismatchError,
    RoomTopologyMissingError,
    RoomTopologyProvider,
    UnknownRoomTopologyError,
)


class RepositoryRoomTopologyProvider(RoomTopologyProvider):
    def __init__(self, room_repository: RoomRepository) -> None:
        self._rooms = room_repository

    def get_topology(self, room_id: int, room_code: str, capacity: int) -> SeatTopology:
        room = self._rooms.get(room_id)
        if room is None:
            raise UnknownRoomTopologyError(f"Room id {room_id} ('{room_code}') does not exist.")
        if not room.has_topology:
            raise RoomTopologyMissingError(
                f"Room '{room_code}' has no configured seat topology (rows/columns) — constraint "
                "seating requires one; sequential seating does not. Configure it via the room "
                "import CSV's optional Rows/Columns columns."
            )
        if room.capacity != capacity:
            # Room.__post_init__ already guarantees rows * columns ==
            # room.capacity, so if the capacity passed in here (sourced
            # from this exam's RoomAllocation, itself joined from this
            # same Room row) disagrees, the room's capacity must have
            # changed since this exam's allocation was made.
            raise RoomTopologyMismatchError(
                f"Room '{room_code}' capacity has changed since this exam's allocation was made "
                f"({capacity} then vs {room.capacity} now)."
            )
        assert room.rows is not None and room.columns is not None
        return RectangularRoomTopology(room_id=room_id, rows=room.rows, columns=room.columns)
