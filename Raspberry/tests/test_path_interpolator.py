"""
tests/test_path_interpolator.py

Unit tests for chess trajectory interpolation and discrete path calculation.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.path_interpolator import (
    bresenham_line,
    get_castle_rook_move,
    interpolate_move_path,
    interpolate_uci_move,
    is_castle_uci,
)


def test_stationary_move():
    assert interpolate_move_path(4, 4, 4, 4) == [(4, 4)]


def test_horizontal_moves():
    # Left to right: b1 (1,0) -> f1 (5,0)
    path = interpolate_move_path(1, 0, 5, 0)
    assert path == [(1, 0), (2, 0), (3, 0), (4, 0), (5, 0)]

    # Right to left: f1 (5,0) -> b1 (1,0)
    path_rev = interpolate_move_path(5, 0, 1, 0)
    assert path_rev == [(5, 0), (4, 0), (3, 0), (2, 0), (1, 0)]


def test_vertical_moves():
    # e2 (4,1) -> e4 (4,3)
    path = interpolate_move_path(4, 1, 4, 3)
    assert path == [(4, 1), (4, 2), (4, 3)]

    # e7 (4,6) -> e5 (4,4)
    path_down = interpolate_move_path(4, 6, 4, 4)
    assert path_down == [(4, 6), (4, 5), (4, 4)]


def test_diagonal_moves():
    # c1 (2,0) -> f4 (5,3)
    path = interpolate_move_path(2, 0, 5, 3)
    assert path == [(2, 0), (3, 1), (4, 2), (5, 3)]

    # f4 (5,3) -> c1 (2,0)
    path_down = interpolate_move_path(5, 3, 2, 0)
    assert path_down == [(5, 3), (4, 2), (3, 1), (2, 0)]

    # a8 (0,7) -> h1 (7,0)
    path_long_diag = interpolate_move_path(0, 7, 7, 0)
    assert len(path_long_diag) == 8
    assert path_long_diag[0] == (0, 7)
    assert path_long_diag[-1] == (7, 0)


def test_knight_moves():
    # b1 (1,0) -> c3 (2,2) [Vertical major L-shape]
    path_v = interpolate_move_path(1, 0, 2, 2)
    assert path_v == [(1, 0), (1, 1), (1, 2), (2, 2)]

    # g8 (6,7) -> e7 (4,6) [Horizontal major L-shape]
    path_h = interpolate_move_path(6, 7, 4, 6)
    assert path_h == [(6, 7), (5, 7), (4, 7), (4, 6)]

    # e4 (4,3) -> d6 (3,5) [Vertical major: dc=-1, dr=+2]
    path_v2 = interpolate_move_path(4, 3, 3, 5)
    assert path_v2 == [(4, 3), (4, 4), (4, 5), (3, 5)]


def test_interpolate_uci_move():
    assert interpolate_uci_move("e2e4") == [(4, 1), (4, 2), (4, 3)]
    assert interpolate_uci_move("g1f3") == [(6, 0), (6, 1), (6, 2), (5, 2)]
    assert interpolate_uci_move("a1h8") == [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7)]
    assert interpolate_uci_move("invalid") == []
    assert interpolate_uci_move("") == []


def test_bresenham_line():
    line = bresenham_line(0, 0, 2, 2)
    assert line == [(0, 0), (1, 1), (2, 2)]


def test_get_castle_rook_move():
    # White Kingside (e1g1)
    assert get_castle_rook_move(4, 0, 6, 0) == ((7, 0), (5, 0))
    # White Queenside (e1c1)
    assert get_castle_rook_move(4, 0, 2, 0) == ((0, 0), (3, 0))
    # Black Kingside (e8g8)
    assert get_castle_rook_move(4, 7, 6, 7) == ((7, 7), (5, 7))
    # Black Queenside (e8c8)
    assert get_castle_rook_move(4, 7, 2, 7) == ((0, 7), (3, 7))
    # Non-castling moves
    assert get_castle_rook_move(4, 1, 4, 3) is None
    assert get_castle_rook_move(4, 0, 4, 1) is None


def test_is_castle_uci():
    assert is_castle_uci("e1g1") is True
    assert is_castle_uci("e1c1") is True
    assert is_castle_uci("e8g8") is True
    assert is_castle_uci("e8c8") is True
    assert is_castle_uci("e2e4") is False
    assert is_castle_uci("g1f3") is False

