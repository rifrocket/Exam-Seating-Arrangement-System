"""Pure tests for the seat topology foundation — no DB, no HTTP, no
strategy involved. All data synthetic."""

import math

import pytest

from app.seating.topology import RectangularRoomTopology


def _layout() -> RectangularRoomTopology:
    # rows=2, columns=5:
    #   1  2  3  4  5
    #   6  7  8  9  10
    return RectangularRoomTopology(room_id=1, rows=2, columns=5)


def test_position_for_seat_is_row_major() -> None:
    layout = _layout()
    assert layout.position_for_seat(1).row == 0
    assert layout.position_for_seat(1).column == 0
    assert layout.position_for_seat(5).row == 0
    assert layout.position_for_seat(5).column == 4
    assert layout.position_for_seat(6).row == 1
    assert layout.position_for_seat(6).column == 0
    assert layout.position_for_seat(10).row == 1
    assert layout.position_for_seat(10).column == 4


def test_seat_number_out_of_range_raises() -> None:
    layout = _layout()
    with pytest.raises(ValueError, match="out of range"):
        layout.position_for_seat(0)
    with pytest.raises(ValueError, match="out of range"):
        layout.position_for_seat(11)


def test_same_row() -> None:
    layout = _layout()
    seat_1 = layout.position_for_seat(1)
    seat_5 = layout.position_for_seat(5)
    seat_6 = layout.position_for_seat(6)
    assert layout.same_row(seat_1, seat_5) is True
    assert layout.same_row(seat_1, seat_6) is False


def test_same_column() -> None:
    layout = _layout()
    seat_1 = layout.position_for_seat(1)
    seat_6 = layout.position_for_seat(6)
    seat_2 = layout.position_for_seat(2)
    assert layout.same_column(seat_1, seat_6) is True
    assert layout.same_column(seat_1, seat_2) is False


def test_adjacent_includes_orthogonal_and_diagonal_neighbors() -> None:
    layout = _layout()
    # Seat 7 (row 1, col 1) is surrounded by seats 1,2,3,6,8 (row0 cols0-2, row1 cols0,2).
    seat_7 = layout.position_for_seat(7)
    for neighbor_seat in (1, 2, 3, 6, 8):
        neighbor = layout.position_for_seat(neighbor_seat)
        assert layout.is_adjacent(seat_7, neighbor) is True, f"seat {neighbor_seat} should be adjacent to 7"


def test_non_adjacent_seats() -> None:
    layout = _layout()
    seat_1 = layout.position_for_seat(1)
    seat_5 = layout.position_for_seat(5)
    seat_10 = layout.position_for_seat(10)
    assert layout.is_adjacent(seat_1, seat_5) is False
    assert layout.is_adjacent(seat_1, seat_10) is False


def test_a_seat_is_not_adjacent_to_itself() -> None:
    layout = _layout()
    seat_1 = layout.position_for_seat(1)
    assert layout.is_adjacent(seat_1, seat_1) is False


def test_distance_between_seats() -> None:
    layout = _layout()
    seat_1 = layout.position_for_seat(1)  # row 0, col 0
    seat_2 = layout.position_for_seat(2)  # row 0, col 1
    seat_7 = layout.position_for_seat(7)  # row 1, col 1

    assert layout.distance(seat_1, seat_1) == 0
    assert layout.distance(seat_1, seat_2) == pytest.approx(1.0)
    assert layout.distance(seat_1, seat_7) == pytest.approx(math.sqrt(2))


def test_cross_room_comparisons_are_never_related() -> None:
    room_a = RectangularRoomTopology(room_id=1, rows=2, columns=5)
    room_b = RectangularRoomTopology(room_id=2, rows=2, columns=5)
    seat_in_a = room_a.position_for_seat(1)
    seat_in_b = room_b.position_for_seat(1)

    assert room_a.same_row(seat_in_a, seat_in_b) is False
    assert room_a.same_column(seat_in_a, seat_in_b) is False
    assert room_a.is_adjacent(seat_in_a, seat_in_b) is False
    assert room_a.distance(seat_in_a, seat_in_b) == math.inf


def test_invalid_layout_dimensions_raise() -> None:
    with pytest.raises(ValueError):
        RectangularRoomTopology(room_id=1, rows=0, columns=5)
    with pytest.raises(ValueError):
        RectangularRoomTopology(room_id=1, rows=2, columns=0)
