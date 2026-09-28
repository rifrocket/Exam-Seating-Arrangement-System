"""Pure tests for RoomTopologyProvider / StaticRoomTopologyProvider — no
DB, no HTTP, no strategy involved. All data synthetic."""

import pytest

from app.seating.topology_provider import (
    RoomTopologyMismatchError,
    StaticRoomTopologyProvider,
    UnknownRoomTopologyError,
)


def test_get_topology_returns_a_topology_matching_the_configured_layout() -> None:
    provider = StaticRoomTopologyProvider({"401": (2, 5)})

    topology = provider.get_topology(room_id=1, room_code="401", capacity=10)

    assert topology.physical_capacity == 10
    position = topology.position_for_seat(6)
    assert (position.row, position.column) == (1, 0)


def test_topology_carries_the_given_room_id_for_cross_room_comparisons() -> None:
    provider = StaticRoomTopologyProvider({"401": (2, 5), "402": (2, 5)})

    topology_a = provider.get_topology(room_id=1, room_code="401", capacity=10)
    topology_b = provider.get_topology(room_id=2, room_code="402", capacity=10)

    seat_in_a = topology_a.position_for_seat(1)
    seat_in_b = topology_b.position_for_seat(1)
    assert seat_in_a.room_id == 1
    assert seat_in_b.room_id == 2
    assert topology_a.is_adjacent(seat_in_a, seat_in_b) is False


def test_unknown_room_code_fails_clearly() -> None:
    provider = StaticRoomTopologyProvider({"401": (2, 5)})

    with pytest.raises(UnknownRoomTopologyError, match="No seat topology configured for room '999'"):
        provider.get_topology(room_id=1, room_code="999", capacity=10)


def test_topology_seat_count_mismatch_fails_clearly_rather_than_truncating_or_padding() -> None:
    """The room's real physical capacity is 8, but the configured layout
    (2x5 = 10 seats) doesn't match it — this must be a loud failure, not a
    silently truncated or padded topology."""
    provider = StaticRoomTopologyProvider({"401": (2, 5)})

    with pytest.raises(RoomTopologyMismatchError, match="10 seat"):
        provider.get_topology(room_id=1, room_code="401", capacity=8)
