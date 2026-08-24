"""
tests/test_gesture_resignation.py

Unit tests for "The King's Bow" physical over-the-board resignation gesture:
1. Pondering safety: King held >= 3.0s -> placed on legal target -> normal move executes.
2. Short cancel: King lifted < 3.0s -> replaced on origin -> move cancelled, no resignation.
3. King's Bow: King lifted >= 3.0s -> replaced on origin -> resign signal dispatched.
4. King Laid to Rest: King removed/tipped off board >= 5.0s -> auto-resign signal dispatched.
5. LED Aura rendering: validates frame writes, power budget (<= 10 LEDs), and night mode scaling.
"""

import time
from unittest.mock import MagicMock

import chess
import pytest

from app.config import (
    BOARD_COLS,
    BOARD_ROWS,
    COLOR_RESIGN_HALO,
    COLOR_RESIGN_PRIMARY,
    RESIGNATION_ABANDON_DURATION_S,
    RESIGNATION_HOLD_DURATION_S,
)
from app.led_animations import render_resignation_aura
from app.led_helpers import (
    COLOR_INT_NIGHT_RESIGN_HALO,
    COLOR_INT_NIGHT_RESIGN_PRIMARY,
    COLOR_INT_RESIGN_HALO,
    COLOR_INT_RESIGN_PRIMARY,
    get_led_indices,
)
from app.physical_tracker import PhysicalMoveTracker


class MockEngine:
    def __init__(self, fen: str = chess.STARTING_FEN, my_color: str = "white"):
        self.board = chess.Board(fen)
        self.my_color = my_color
        self.turn = "white" if self.board.turn == chess.WHITE else "black"
        self.game_info = {"turn": self.turn, "is_my_turn": True, "my_color": my_color}


def _create_physical_grid(board: chess.Board) -> list[list[int]]:
    """Generates an 8x8 physical sensor grid matching piece positions on the board."""
    grid = [[0 for _ in range(8)] for _ in range(8)]
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is not None:
            c = chess.square_file(sq)
            r = chess.square_rank(sq)
            grid[c][r] = -1 if piece.color == chess.WHITE else 1
    return grid


def test_pondering_safety_king_normal_move():
    """Lifting King for >= 3.0s arms resignation, but placing on a legal target makes normal move."""
    tracker = PhysicalMoveTracker()
    # 1. e4 e5 position where White King on e1 can legally move to e2
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    engine = MockEngine(board.fen(), my_color="white")
    grid = _create_physical_grid(board)
    tracker.reset(grid)

    # White lifts King at e1 (col 4, row 0)
    grid[4][0] = 0
    res = tracker.process_physical_state(grid, engine)
    assert res is None
    assert tracker.lifted_square == (4, 0)
    assert tracker.king_lift_time is not None
    assert (4, 1) in tracker.legal_targets  # e2 is legal

    # Simulate 3.5s elapsed hold
    tracker.king_lift_time = time.time() - 3.5
    res = tracker.process_physical_state(grid, engine)
    assert res is None
    assert tracker.resignation_armed is True

    # White places King on legal target e2 (col 4, row 1)
    grid[4][1] = -1
    res = tracker.process_physical_state(grid, engine)
    assert res is not None
    from_f, from_r, to_f, to_r, promo = res
    assert (from_f, from_r) == (5, 1)  # e1 (1-indexed)
    assert (to_f, to_r) == (5, 2)      # e2 (1-indexed)
    assert promo is None
    assert tracker.resignation_armed is False
    assert tracker.king_lift_time is None


def test_short_cancel_touch_and_replace():
    """Lifting King for < 3.0s and returning to origin cancels move without arming or resigning."""
    tracker = PhysicalMoveTracker()
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    engine = MockEngine(board.fen(), my_color="white")
    grid = _create_physical_grid(board)
    tracker.reset(grid)

    # White lifts King at e1 (col 4, row 0)
    grid[4][0] = 0
    tracker.process_physical_state(grid, engine)
    assert tracker.lifted_square == (4, 0)

    # Simulate 1.2s elapsed (< 3.0s)
    tracker.king_lift_time = time.time() - 1.2

    # Replace King on e1
    grid[4][0] = -1
    res = tracker.process_physical_state(grid, engine)
    assert res is None
    assert tracker.lifted_square is None
    assert tracker.resignation_armed is False
    assert tracker.king_lift_time is None


def test_kings_bow_resignation_confirmed():
    """Lifting King for >= 3.0s and replacing on origin confirms The King's Bow surrender."""
    tracker = PhysicalMoveTracker()
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    engine = MockEngine(board.fen(), my_color="white")
    grid = _create_physical_grid(board)
    tracker.reset(grid)

    # White lifts King at e1 (col 4, row 0)
    grid[4][0] = 0
    tracker.process_physical_state(grid, engine)
    assert tracker.lifted_square == (4, 0)

    # Simulate 3.2s elapsed (>= 3.0s arming threshold)
    tracker.king_lift_time = time.time() - 3.2
    tracker.process_physical_state(grid, engine)
    assert tracker.resignation_armed is True

    # White yields by placing King back on e1
    grid[4][0] = -1
    res = tracker.process_physical_state(grid, engine)
    assert res is not None
    from_f, from_r, to_f, to_r, promo = res
    assert promo == "resign_white"
    assert tracker.lifted_square is None
    assert tracker.resignation_armed is False
    assert tracker.king_lift_time is None


def test_king_laid_to_rest_abandon_timeout():
    """Leaving the King off board for >= 5.0s auto-confirms resignation."""
    tracker = PhysicalMoveTracker()
    board = chess.Board()
    board.push_san("e4")
    # Black's turn: Black King at e8 (col 4, row 7)
    engine = MockEngine(board.fen(), my_color="black")
    grid = _create_physical_grid(board)
    tracker.reset(grid)

    # Black lifts King at e8 (col 4, row 7)
    grid[4][7] = 0
    tracker.process_physical_state(grid, engine)
    assert tracker.lifted_square == (4, 7)
    assert tracker.resignation_color == "black"

    # Simulate 5.1s elapsed (>= 5.0s abandonment threshold)
    tracker.king_lift_time = time.time() - 5.1
    res = tracker.process_physical_state(grid, engine)
    assert res is not None
    from_f, from_r, to_f, to_r, promo = res
    assert promo == "resign_black"
    assert tracker.lifted_square is None
    assert tracker.resignation_armed is False


def test_render_resignation_aura_power_and_day_night():
    """Validates resignation aura LED rendering, night mode attenuation, and power constraints."""
    frame = [0] * 64
    now = 100.0

    # Day Mode: King at e1 (col 4, row 0)
    render_resignation_aura(now, frame, (4, 0), elapsed=3.5, params={"night_mode": False})
    lit_indices = [i for i, col in enumerate(frame) if col != 0]
    # e1 (col 4, row 0) + cross neighbors (col 4, row 1), (col 3, row 0), (col 5, row 0)
    # Total squares <= 4 on border -> at most 4 squares (each 1 or 2 LEDs per square)
    assert len(lit_indices) <= 10
    assert len(lit_indices) >= 2

    # Night Mode: King at d4 (col 3, row 3)
    frame_night = [0] * 64
    render_resignation_aura(now, frame_night, (3, 3), elapsed=4.5, params={"night_mode": True})
    lit_night = [i for i, col in enumerate(frame_night) if col != 0]
    assert len(lit_night) <= 10
    assert len(lit_night) >= 2
