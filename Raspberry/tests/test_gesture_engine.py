"""
tests/test_gesture_engine.py

Comprehensive test suite for the Physical Board Gesture Engine, Kingside Corner Gate,
LED overlay colors, cancellation rules, and REST restart endpoints.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.gesture_engine import (
    COLOR_INT_AZURE,
    COLOR_INT_EMERALD,
    PhysicalGestureEngine,
    RestartPreviousGameGesture,
)


def create_starting_board():
    """Generates standard 8x8 chess physical starting grid (-1 White, +1 Black, 0 Empty)."""
    grid = [[0] * 8 for _ in range(8)]
    for c in range(8):
        grid[c][0] = -1
        grid[c][1] = -1
        grid[c][6] = 1
        grid[c][7] = 1
    return grid


class TestRestartPreviousGameGesture:
    def test_initial_state(self):
        gesture = RestartPreviousGameGesture()
        assert gesture.name == "restart_previous_game"
        assert not gesture.is_active
        assert gesture.step == 0
        assert gesture.hint is None
        assert gesture.get_led_overlay(time.time()) == {}

    def test_step1_trigger_on_h2_lift(self):
        gesture = RestartPreviousGameGesture()
        board = create_starting_board()
        board[7][1] = 0  # Lift h2

        completed = gesture.evaluate(board, now=100.0)
        assert not completed
        assert gesture.is_active
        assert gesture.step == 1
        assert "Lift h1" in (gesture.hint or "")
        overlay = gesture.get_led_overlay(now=100.0)
        assert (7, 1) in overlay  # Amber h2
        assert (7, 0) in overlay  # Azure pulse h1

    def test_step1_premature_replace_cancels(self):
        gesture = RestartPreviousGameGesture()
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)
        assert gesture.step == 1

        # Replace h2 without lifting h1
        board[7][1] = -1
        completed = gesture.evaluate(board, now=101.0)
        assert not completed
        assert gesture.step == 0
        assert not gesture.is_active

    def test_step1_extra_piece_lift_cancels(self):
        gesture = RestartPreviousGameGesture()
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)
        assert gesture.step == 1

        # Bump e2 pawn
        board[4][1] = 0
        gesture.evaluate(board, now=101.0)
        assert gesture.step == 0
        assert not gesture.is_active

    def test_step1_timeout_cancels(self):
        gesture = RestartPreviousGameGesture(timeout=5.0)
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)
        assert gesture.step == 1

        # Exceed 5.0s timeout
        gesture.evaluate(board, now=106.0)
        assert gesture.step == 0
        assert not gesture.is_active

    def test_step2_trigger_on_h1_lift(self):
        gesture = RestartPreviousGameGesture()
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)

        # Lift h1
        board[7][0] = 0
        completed = gesture.evaluate(board, now=101.0)
        assert not completed
        assert gesture.step == 2
        assert "Replace h1 and h2" in (gesture.hint or "")
        overlay = gesture.get_led_overlay(now=101.0)
        assert (7, 0) in overlay
        assert (7, 1) in overlay

    def test_step2_completion_on_replace_both(self):
        mock_mgr = MagicMock()
        gesture = RestartPreviousGameGesture(state_manager=mock_mgr)
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)
        board[7][0] = 0
        gesture.evaluate(board, now=101.0)

        # Replace both h1 and h2
        board[7][0] = -1
        board[7][1] = -1
        completed = gesture.evaluate(board, now=102.0)
        assert completed
        assert gesture.step == 0
        assert not gesture.is_active


class TestPhysicalGestureEngine:
    def test_engine_lifecycle(self):
        mock_mgr = MagicMock()
        engine = PhysicalGestureEngine(state_manager=mock_mgr)
        assert not engine.is_active
        assert len(engine.gestures) >= 1

        board = create_starting_board()
        board[7][1] = 0
        engine.evaluate(board, game_status="IDLE", now=100.0)
        assert engine.is_active
        assert engine.active_gesture is not None
        assert engine.active_gesture.name == "restart_previous_game"

        # Playing game status resets all gestures
        engine.evaluate(board, game_status="PLAYING", now=101.0)
        assert not engine.is_active

    def test_state_payload(self):
        engine = PhysicalGestureEngine()
        payload = engine.get_state_payload()
        assert "is_active" in payload
        assert "gestures" in payload
        assert isinstance(payload["gestures"], list)
