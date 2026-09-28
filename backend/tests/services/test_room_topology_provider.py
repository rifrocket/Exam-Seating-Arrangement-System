"""Tests for RepositoryRoomTopologyProvider against a real (in-memory)
database through the concrete Room repository, but never through HTTP.
All data synthetic.
"""

import pytest
from sqlalchemy.orm import Session

from app.db.repositories import SqlAlchemyRoomRepository
from app.domain import Room
from app.seating.topology_provider import (
    RoomTopologyMismatchError,
    RoomTopologyMissingError,
    UnknownRoomTopologyError,
)
from app.services.seating_generation.room_topology_provider import RepositoryRoomTopologyProvider


def test_returns_topology_for_a_room_with_arbitrary_code(db_session: Session) -> None:
    """Not "401"/"402" — proving this provider depends on the room's own
    configured rows/columns, never on a specific room code."""
    room_repo = SqlAlchemyRoomRepository(db_session)
    room = room_repo.add(Room(id=None, code="ROOM-X", capacity=10, rows=2, columns=5))
    db_session.commit()
    provider = RepositoryRoomTopologyProvider(room_repo)

    topology = provider.get_topology(room_id=room.id, room_code="ROOM-X", capacity=10)

    assert topology.physical_capacity == 10


def test_room_without_configured_topology_raises_missing_error(db_session: Session) -> None:
    room_repo = SqlAlchemyRoomRepository(db_session)
    room = room_repo.add(Room(id=None, code="101", capacity=40))  # no rows/columns
    db_session.commit()
    provider = RepositoryRoomTopologyProvider(room_repo)

    with pytest.raises(RoomTopologyMissingError, match="no configured seat topology"):
        provider.get_topology(room_id=room.id, room_code="101", capacity=40)


def test_unknown_room_id_raises_unknown_error(db_session: Session) -> None:
    room_repo = SqlAlchemyRoomRepository(db_session)
    provider = RepositoryRoomTopologyProvider(room_repo)

    with pytest.raises(UnknownRoomTopologyError):
        provider.get_topology(room_id=999, room_code="ghost", capacity=10)


def test_capacity_drift_since_allocation_raises_mismatch_error(db_session: Session) -> None:
    """If the room's capacity has genuinely changed since an exam's
    RoomAllocation was computed from it, that's a real inconsistency worth
    a clear, specific error rather than a silently wrong topology."""
    room_repo = SqlAlchemyRoomRepository(db_session)
    room = room_repo.add(Room(id=None, code="401", capacity=10, rows=2, columns=5))
    db_session.commit()
    provider = RepositoryRoomTopologyProvider(room_repo)

    with pytest.raises(RoomTopologyMismatchError):
        provider.get_topology(room_id=room.id, room_code="401", capacity=12)
