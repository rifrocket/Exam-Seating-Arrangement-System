"""Pure tests for Room's topology fields and validation — no DB, no HTTP.
All data synthetic."""

import pytest

from app.domain.room import InvalidRoomTopologyError, Room


def test_room_without_topology_is_valid_and_reports_no_topology() -> None:
    room = Room(id=1, code="101", capacity=40)

    assert room.has_topology is False
    assert room.rows is None
    assert room.columns is None


def test_room_with_matching_topology_is_valid() -> None:
    room = Room(id=1, code="401", capacity=10, rows=2, columns=5)

    assert room.has_topology is True


def test_room_topology_must_multiply_out_to_capacity() -> None:
    with pytest.raises(InvalidRoomTopologyError, match="does not match its capacity"):
        Room(id=1, code="401", capacity=10, rows=2, columns=4)


def test_room_topology_rows_and_columns_must_both_be_present_or_neither() -> None:
    with pytest.raises(InvalidRoomTopologyError, match="both rows and columns"):
        Room(id=1, code="401", capacity=10, rows=2, columns=None)
    with pytest.raises(InvalidRoomTopologyError, match="both rows and columns"):
        Room(id=1, code="401", capacity=10, rows=None, columns=5)


def test_room_topology_rows_and_columns_must_be_positive() -> None:
    with pytest.raises(InvalidRoomTopologyError, match="at least one row and column"):
        Room(id=1, code="401", capacity=0, rows=0, columns=10)
