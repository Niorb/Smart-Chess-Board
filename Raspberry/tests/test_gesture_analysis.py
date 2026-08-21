"""
tests/test_gesture_analysis.py

Unit tests for CenterRoyalGateGesture (e2 -> d2 piece lift combination to activate Analysis).
"""

import time
import pytest
from app.gesture_engine import CenterRoyalGateGesture


class MockStateManager:
    def __init__(self):
        self.flashes = []
        self.analysis_started = False

    def trigger_arrival_flash(self, c, r, duration=0.6, is_capture=False, extra_squares=None):
        self.flashes.append(((c, r), extra_squares, duration))

    async def start_analysis_mode(self, moves_uci=None, game_id=None):
        self.analysis_started = True


def make_standard_starting_grid():
    grid = [[0] * 8 for _ in range(8)]
    for c in range(8):
        for r in (0, 1, 6, 7):
            grid[c][r] = 1
    return grid


def test_gesture_starter_properties():
    gesture = CenterRoyalGateGesture()
    assert gesture.starter_coord == (4, 1)  # e2
    assert gesture.name == "start_analysis"
    assert gesture.step == 0
    assert not gesture.is_active


def test_gesture_three_step_flow():
    mock_mgr = MockStateManager()
    gesture = CenterRoyalGateGesture(state_manager=mock_mgr)
    grid = make_standard_starting_grid()
    now = 1000.0

    # Step 0 -> Step 1: Lift e2 (4, 1)
    grid[4][1] = 0
    res = gesture.evaluate(grid, now)
    assert res is False
    assert gesture.step == 1
    assert gesture.is_active
    assert "Lift d2" in (gesture.hint or "")

    overlay1 = gesture.get_led_overlay(now)
    assert (4, 1) in overlay1
    assert (3, 1) in overlay1

    # Step 1 -> Step 2: Lift d2 (3, 1) while e2 is lifted
    grid[3][1] = 0
    res = gesture.evaluate(grid, now + 0.5)
    assert res is False
    assert gesture.step == 2
    assert "Replace e2 and d2" in (gesture.hint or "")

    overlay2 = gesture.get_led_overlay(now + 0.5)
    assert (4, 1) in overlay2
    assert (3, 1) in overlay2

    # Step 2 -> Step 3: Replace both e2 and d2 back to starting setup
    grid[4][1] = 1
    grid[3][1] = 1
    res = gesture.evaluate(grid, now + 1.0)
    assert res is True  # Gesture completed!
    assert gesture.step == 0
    assert not gesture.is_active

    # Execute completion
    gesture.execute_completion()
    assert len(mock_mgr.flashes) == 1
    assert mock_mgr.flashes[0][0] == (4, 1)
    assert mock_mgr.flashes[0][1] == [(3, 1)]


def test_gesture_premature_e2_replace_cancels():
    gesture = CenterRoyalGateGesture()
    grid = make_standard_starting_grid()
    now = 1000.0

    # Lift e2
    grid[4][1] = 0
    gesture.evaluate(grid, now)
    assert gesture.step == 1

    # Replace e2 before lifting d2
    grid[4][1] = 1
    res = gesture.evaluate(grid, now + 0.2)
    assert res is False
    assert gesture.step == 0  # Reset!


def test_gesture_timeout():
    gesture = CenterRoyalGateGesture(timeout=3.0)
    grid = make_standard_starting_grid()
    now = 1000.0

    # Lift e2
    grid[4][1] = 0
    gesture.evaluate(grid, now)
    assert gesture.step == 1

    # Evaluate after timeout
    res = gesture.evaluate(grid, now + 3.5)
    assert res is False
    assert gesture.step == 0  # Timed out!
