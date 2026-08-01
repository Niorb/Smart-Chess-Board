import pytest
import os
import sys

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

