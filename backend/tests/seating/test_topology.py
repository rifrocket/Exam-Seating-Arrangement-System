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


# --- small/edge-case layouts (Milestone 10) --------------------------------


def test_1x1_layout() -> None:
    layout = RectangularRoomTopology(room_id=1, rows=1, columns=1)
    assert layout.physical_capacity == 1
    assert layout.usable_capacity == 1
    position = layout.position_for_seat(1)
    assert (position.row, position.column) == (0, 0)
    assert layout.is_adjacent(position, position) is False


def test_2x2_layout() -> None:
    layout = RectangularRoomTopology(room_id=1, rows=2, columns=2)
    assert layout.physical_capacity == 4
    seat_1, seat_2, seat_3, seat_4 = (layout.position_for_seat(n) for n in (1, 2, 3, 4))
    assert (seat_1.row, seat_1.column) == (0, 0)
    assert (seat_2.row, seat_2.column) == (0, 1)
    assert (seat_3.row, seat_3.column) == (1, 0)
    assert (seat_4.row, seat_4.column) == (1, 1)
    # In a 2x2 grid every seat is adjacent (including diagonally) to every other.
    for a in (seat_1, seat_2, seat_3, seat_4):
        for b in (seat_1, seat_2, seat_3, seat_4):
            if a != b:
                assert layout.is_adjacent(a, b) is True


def test_all_seats_usable_by_default() -> None:
    layout = _layout()
    assert layout.usable_capacity == layout.physical_capacity == 10
    assert [p.seat_number for p in layout.usable_positions()] == list(range(1, 11))
    assert all(p.available for p in layout.all_positions())


def test_all_positions_returns_every_physical_seat_in_seat_number_order() -> None:
    layout = _layout()
    assert [p.seat_number for p in layout.all_positions()] == list(range(1, 11))


# --- blocked seats (Milestone 10) ------------------------------------------


def test_one_blocked_seat() -> None:
    layout = RectangularRoomTopology(room_id=1, rows=4, columns=5, blocked_seat_numbers={7})
    assert layout.physical_capacity == 20
    assert layout.usable_capacity == 19
    assert layout.position_for_seat(7).available is False
    assert 7 not in [p.seat_number for p in layout.usable_positions()]


def test_multiple_blocked_seats_deterministic_usable_order() -> None:
    # The exact example from the Phase 10 spec.
    layout = RectangularRoomTopology(room_id=1, rows=4, columns=5, blocked_seat_numbers={7, 17})
    assert layout.physical_capacity == 20
    assert layout.usable_capacity == 18
    assert [p.seat_number for p in layout.usable_positions()] == [
        1, 2, 3, 4, 5,
        6, 8, 9, 10,
        11, 12, 13, 14, 15,
        16, 18, 19, 20,
    ]


def test_duplicate_blocked_seat_numbers_are_harmless() -> None:
    layout = RectangularRoomTopology(room_id=1, rows=4, columns=5, blocked_seat_numbers=[7, 7, 17, 17, 17])
    assert layout.usable_capacity == 18


def test_invalid_blocked_seat_number_is_rejected() -> None:
    with pytest.raises(ValueError, match="out of range"):
        RectangularRoomTopology(room_id=1, rows=4, columns=5, blocked_seat_numbers={21})


def test_blocked_seat_number_zero_is_rejected() -> None:
    with pytest.raises(ValueError, match="out of range"):
        RectangularRoomTopology(room_id=1, rows=4, columns=5, blocked_seat_numbers={0})


def test_blocked_seat_number_negative_is_rejected() -> None:
    with pytest.raises(ValueError, match="out of range"):
        RectangularRoomTopology(room_id=1, rows=4, columns=5, blocked_seat_numbers={-1})


def test_all_seats_blocked_leaves_zero_usable_capacity() -> None:
    layout = RectangularRoomTopology(room_id=1, rows=2, columns=2, blocked_seat_numbers={1, 2, 3, 4})
    assert layout.physical_capacity == 4
    assert layout.usable_capacity == 0
    assert layout.usable_positions() == []
    assert len(layout.all_positions()) == 4  # still physically present


def test_blocked_seats_never_appear_in_usable_positions() -> None:
    layout = RectangularRoomTopology(room_id=1, rows=4, columns=5, blocked_seat_numbers={7, 17})
    usable_numbers = {p.seat_number for p in layout.usable_positions()}
    assert 7 not in usable_numbers
    assert 17 not in usable_numbers


# --- physical existence vs. usability (Milestone 10, spec section 12) ------


def test_blocked_seat_still_has_real_row_column_and_participates_in_queries() -> None:
    """01 02 -- 04 / 05 06 07 08 — seat 3 is blocked but seats 2 and 4
    remain real physical positions, and adjacency between OTHER seats is
    computed exactly as if seat 3 were usable — blocking a seat does not
    invent special adjacency semantics."""
    layout = RectangularRoomTopology(room_id=1, rows=2, columns=4, blocked_seat_numbers={3})
    seat_2 = layout.position_for_seat(2)
    seat_3 = layout.position_for_seat(3)
    seat_4 = layout.position_for_seat(4)

    assert seat_3.available is False
    assert (seat_3.row, seat_3.column) == (0, 2)  # still a real position
    # Seat 2 and seat 4 are each still adjacent to (blocked) seat 3 —
    # physical adjacency is unaffected by usability.
    assert layout.is_adjacent(seat_2, seat_3) is True
    assert layout.is_adjacent(seat_3, seat_4) is True
    # And seat 2 / seat 4 are not adjacent to each other (two apart).
    assert layout.is_adjacent(seat_2, seat_4) is False
