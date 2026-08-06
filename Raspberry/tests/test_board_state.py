import pytest
import os
import sys
from unittest.mock import MagicMock, patch

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.board_state import BoardStateManager

def test_board_state_manager_init():
    # Instantiate board state manager (with mock/missing hardware gracefully handled)
    bsm = BoardStateManager()
    assert bsm.game_status == "IDLE"
    assert bsm.clocks == {"white": "?", "black": "?"}
    assert len(bsm.physical_state) == 8
    assert len(bsm.physical_state[0]) == 8
    assert len(bsm.digital_state) == 8

def test_physical_payload_structure():
    bsm = BoardStateManager()
    payload = bsm.get_physical_payload()
    assert payload["rows"] == 8
    assert payload["cols"] == 8
    assert "grid" in payload
    assert "adc" in payload
    assert "baselines" in payload
    assert "highlighted_square" in payload
    assert "disabled_squares" in payload

def test_health_status_structure():
    bsm = BoardStateManager()
    health = bsm.get_health_status()
    assert "status" in health
    assert health["status"] in ["HEALTHY", "DEGRADED", "DISCONNECTED"]
    assert "subsystems" in health
    assert "serial" in health["subsystems"]
    assert "gpio" in health["subsystems"]
    assert "led_strip" in health["subsystems"]
    assert "chess_engine" in health["subsystems"]
    assert "matrix" in health
    assert "col_mode" in health["matrix"]
    assert "disabled_squares" in health["matrix"]
    assert "scan_delay_ms" in health["matrix"]

def test_health_status_evaluations():
    bsm = BoardStateManager()
    
    # Force DISCONNECTED by removing serial & gpio
    bsm.ser = None
    bsm.h = None
    assert bsm.get_health_status()["status"] == "DISCONNECTED"
    assert bsm.get_health_status()["subsystems"]["serial"] == "DISCONNECTED"
    assert bsm.get_health_status()["subsystems"]["gpio"] == "DISCONNECTED"


def test_highlighted_square_single_square_update():
    from unittest.mock import MagicMock
    from playwright_chesscom.led_helpers import Color
    bsm = BoardStateManager()
    bsm.strip = MagicMock()

    # Highlight square A4: file=0, rank=3
    bsm.highlighted_square = (0, 3)
    bsm._update_leds()

    orange = Color(255, 80, 0)

    # A4 (col=3, row=0) indices are [9, 10] in 18-LED column layout
    bsm.strip.setPixelColor.assert_any_call(9, orange)
    bsm.strip.setPixelColor.assert_any_call(10, orange)

    # Verify D1 (col=0, row=3) indices [54, 55] were NOT set to orange
    calls = bsm.strip.setPixelColor.call_args_list
    d1_orange = any(call.args == (54, orange) or call.args == (55, orange) for call in calls)
    assert not d1_orange, "Transposed square D1 was erroneously highlighted!"


def test_led_suppression_during_calibration():
    from unittest.mock import MagicMock
    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.highlighted_square = (0, 3)

    bsm.initial_calibrating = True
    bsm._update_leds()
    bsm.strip.setPixelColor.assert_not_called()

def test_safe_calibrate_no_deadlock():
    from unittest.mock import MagicMock
    from playwright_chesscom.led_helpers import DualPixelStrip
    bsm = BoardStateManager()
    bsm.ser = MagicMock()
    bsm.strip = DualPixelStrip(num_leds_per_strip=76)
    bsm.strip.set_serial_conn(bsm.ser, bsm.serial_lock)

    # Calling _safe_calibrate must execute without deadlocking
    with patch("board_hardware.calibrate_board", return_value=True):
        res = bsm._safe_calibrate()
        assert res is True




