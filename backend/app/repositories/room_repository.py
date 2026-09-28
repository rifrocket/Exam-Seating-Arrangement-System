from abc import abstractmethod

from app.domain import Room
from app.repositories.base import Repository


class RoomRepository(Repository[Room]):
    @abstractmethod
    def get_by_code(self, code: str) -> Room | None: ...

    @abstractmethod
    def set_topology(self, room_id: int, rows: int, columns: int) -> Room:
        """Backfills rows/columns on an existing room. Not a generic
        update() — this project prefers narrow, explicitly-named
        operations over one that could change any field."""
        ...

    @abstractmethod
    def set_blocked_seats(self, room_id: int, blocked_seat_numbers: tuple[int, ...]) -> Room:
        """Backfills blocked_seat_numbers on an existing room. Not a
        generic update(), for the same reason as set_topology()."""
        ...
