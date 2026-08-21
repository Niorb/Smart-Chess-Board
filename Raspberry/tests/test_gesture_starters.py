"""
tests/test_gesture_starters.py

Unit tests for dynamic gesture starter indicators on board ready state.
"""

import time
import pytest
from app.gesture_engine import PhysicalGestureEngine


def test_gesture_starter_indicators():
    engine = PhysicalGestureEngine()
    now = 1000.0

    indicators = engine.get_starter_indicators(now)
    assert isinstance(indicators, dict)
    # Must contain starter coordinates for the 3 registered gestures:
    # a2 (0, 1) -> Night Mode
    # e2 (4, 1) -> Analysis Mode
    # h2 (7, 1) -> Restart Game
    assert (0, 1) in indicators
    assert (4, 1) in indicators
    assert (7, 1) in indicators

    # Verify colors are non-zero
    for coord, color in indicators.items():
        assert color > 0


def test_starter_coords_in_state_payload():
    engine = PhysicalGestureEngine()
    payload = engine.get_state_payload()
    assert "gestures" in payload
    starter_coords = [g.get("starter_coord") for g in payload["gestures"] if g.get("starter_coord")]
    assert [0, 1] in starter_coords
    assert [4, 1] in starter_coords
    assert [7, 1] in starter_coords
