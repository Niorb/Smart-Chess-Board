import os
import sys
from unittest.mock import MagicMock, patch

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.board_state import BoardStateManager
from app.main import app
from fastapi.testclient import TestClient


def create_healthy_state_manager():
    """Helper to instantiate a BoardStateManager with mocked healthy hardware."""
    bsm = BoardStateManager()
    mock_ser = MagicMock()
    mock_ser.is_open = True
    bsm.ser = mock_ser
    bsm.h = MagicMock()
    bsm.strip = MagicMock()
    return bsm


def test_get_health_status_structure():
    """Verify that get_health_status returns the correct top-level keys and field types."""
    bsm = BoardStateManager()
    health = bsm.get_health_status()

    # Top-level fields
    assert "status" in health
    assert "timestamp" in health
    assert "subsystems" in health
    assert "matrix" in health

    # Field types
    assert isinstance(health["status"], str)
    assert isinstance(health["timestamp"], str)
    assert health["timestamp"].endswith("Z")
    assert isinstance(health["subsystems"], dict)
    assert isinstance(health["matrix"], dict)

    # Subsystems fields
    subsystems = health["subsystems"]
    assert "serial" in subsystems
    assert "gpio" in subsystems
    assert "led_strip" in subsystems
    assert "chess_engine" in subsystems

    # Matrix fields
    matrix = health["matrix"]
    assert "col_mode" in matrix
    assert "disabled_squares" in matrix
    assert "scan_delay_ms" in matrix


@patch("board_hardware.settings", {"col_mode": "auto", "disabled_squares": [], "scan_delay": 10})
@patch("app.board_state.lichess_engine")
def test_health_status_evaluation_healthy(mock_engine):
    """Verify HEALTHY status when all subsystems are operational and settings normal."""
    mock_engine.is_running = True
    bsm = create_healthy_state_manager()

    health = bsm.get_health_status()
    assert health["status"] == "HEALTHY"
    assert health["subsystems"]["serial"] == "CONNECTED"
    assert health["subsystems"]["gpio"] == "CONNECTED"
    assert health["subsystems"]["led_strip"] == "CONNECTED"
    assert health["subsystems"]["chess_engine"] == "CONNECTED"


@patch("board_hardware.settings", {"col_mode": "auto", "disabled_squares": [], "scan_delay": 10})
@patch("app.board_state.lichess_engine")
def test_health_status_evaluation_degraded_missing_led_strip(mock_engine):
    """Verify DEGRADED status when LED strip is missing/not initialized."""
    mock_engine.is_running = True
    bsm = create_healthy_state_manager()
    bsm.strip = None

    health = bsm.get_health_status()
    assert health["status"] == "DEGRADED"
    assert health["subsystems"]["led_strip"] == "DISCONNECTED"


@patch("board_hardware.settings", {"col_mode": "manual", "disabled_squares": [], "scan_delay": 100})
@patch("app.board_state.lichess_engine")
def test_health_status_evaluation_degraded_manual_col_mode(mock_engine):
    """Verify DEGRADED status when board is in manual column mode."""
    mock_engine.is_running = True
    bsm = create_healthy_state_manager()

    health = bsm.get_health_status()
    assert health["status"] == "DEGRADED"
    assert health["matrix"]["col_mode"] == "manual"


@patch("board_hardware.settings", {"col_mode": "auto", "disabled_squares": [[0, 1]], "scan_delay": 10})
@patch("app.board_state.lichess_engine")
def test_health_status_evaluation_degraded_disabled_squares(mock_engine):
    """Verify DEGRADED status when disabled squares are present."""
    mock_engine.is_running = True
    bsm = create_healthy_state_manager()

    health = bsm.get_health_status()
    assert health["status"] == "DEGRADED"
    assert len(health["matrix"]["disabled_squares"]) > 0


@patch("board_hardware.settings", {"col_mode": "auto", "disabled_squares": [], "scan_delay": 10})
@patch("app.board_state.lichess_engine")
def test_health_status_evaluation_degraded_engine_stopped(mock_engine):
    """Verify DEGRADED status when chess engine is not running."""
    mock_engine.is_running = False
    bsm = create_healthy_state_manager()

    health = bsm.get_health_status()
    assert health["status"] == "DEGRADED"
    assert health["subsystems"]["chess_engine"] == "DISCONNECTED"


@patch("board_hardware.settings", {"col_mode": "auto", "disabled_squares": [], "scan_delay": 10})
def test_health_status_evaluation_disconnected_no_serial():
    """Verify DISCONNECTED status when serial connection is None."""
    bsm = create_healthy_state_manager()
    bsm.ser = None

    health = bsm.get_health_status()
    assert health["status"] == "DISCONNECTED"
    assert health["subsystems"]["serial"] == "DISCONNECTED"


@patch("board_hardware.settings", {"col_mode": "auto", "disabled_squares": [], "scan_delay": 10})
def test_health_status_evaluation_disconnected_closed_serial():
    """Verify DISCONNECTED status when serial port is closed."""
    bsm = create_healthy_state_manager()
    bsm.ser.is_open = False

    health = bsm.get_health_status()
    assert health["status"] == "DISCONNECTED"
    assert health["subsystems"]["serial"] == "DISCONNECTED"


@patch("board_hardware.settings", {"col_mode": "auto", "disabled_squares": [], "scan_delay": 10})
def test_health_status_evaluation_disconnected_no_gpio():
    """Verify DISCONNECTED status when GPIO chip is not initialized."""
    bsm = create_healthy_state_manager()
    bsm.h = None

    health = bsm.get_health_status()
    assert health["status"] == "DISCONNECTED"
    assert health["subsystems"]["gpio"] == "DISCONNECTED"


def test_api_get_board_health_endpoint():
    """Verify GET /api/board/health returns HTTP 200 and valid health payload."""
    client = TestClient(app)
    response = client.get("/api/board/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "subsystems" in data
    assert "matrix" in data
    assert data["status"] in ["HEALTHY", "DEGRADED", "DISCONNECTED"]
