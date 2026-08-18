import copy
import os
import sys
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app, parse_sq


@pytest.fixture(autouse=True)
def preserve_settings():
    from board_hardware import settings
    saved = copy.deepcopy(settings)
    with patch("board_hardware.save_settings"):
        yield
    settings.clear()
    settings.update(saved)


def test_parse_sq_valid():
    assert parse_sq("a1") == (1, 1)
    assert parse_sq("h8") == (8, 8)
    assert parse_sq("e4") == (5, 4)
    assert parse_sq("  E4 ") == (5, 4)


def test_parse_sq_invalid():
    assert parse_sq("") is None
    assert parse_sq("a") is None
    assert parse_sq("i1") is None
    assert parse_sq("a9") is None
    assert parse_sq("e44") is None


def test_health_route():
    client = TestClient(app)
    response = client.get("/api/board/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "subsystems" in data
    assert "matrix" in data


def test_settings_update_route():
    client = TestClient(app)

    payload = {
        "threshold_positive": 3000,
        "threshold_negative": 3000,
    }
    response = client.post("/api/board/settings", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["settings"]["threshold_positive"] == 3000
    assert data["settings"]["threshold_negative"] == 3000


def test_settings_update_route_partial_and_floats():
    client = TestClient(app)

    payload_floats = {"threshold_positive": 2500.7, "threshold_negative": 1500.2}
    response = client.post("/api/board/settings", json=payload_floats)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["settings"]["threshold_positive"] == 2500
    assert data["settings"]["threshold_negative"] == 1500

    payload_partial = {"scan_delay": 150.0}
    response = client.post("/api/board/settings", json=payload_partial)
    assert response.status_code == 200
    assert response.json()["settings"]["scan_delay"] == 150

    payload_null = {"threshold_positive": None, "threshold_negative": None}
    response = client.post("/api/board/settings", json=payload_null)
    assert response.status_code == 200


def test_clear_leds_route():
    client = TestClient(app)
    response = client.post("/api/board/clear_leds")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "All LEDs turned off"


def test_lichess_account_route():
    client = TestClient(app)
    with patch("app.main.lichess_engine.get_account", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "username": "MockMaster",
            "rating": 1850,
            "authenticated": True,
            "online": True,
        }
        response = client.get("/api/lichess/account")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "MockMaster"
        assert data["rating"] == 1850
        assert data["authenticated"] is True


def test_game_seek_and_cancel_routes():
    client = TestClient(app)
    with patch("app.main.lichess_engine.seek", new_callable=AsyncMock) as mock_seek:
        mock_seek.return_value = True
        response = client.post(
            "/api/game/seek",
            json={
                "time_control": "15+10",
                "rated": True,
                "color": "white",
                "opponent": "human",
                "ai_level": 5,
                "rating_range": "1400-1800",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "seeking_initiated"
        assert data["time_control"] == "15+10"
        assert data["rated"] is True
        assert data["opponent"] == "human"
        assert data["rating_range"] == "1400-1800"

    with patch("app.main.lichess_engine.cancel", new_callable=AsyncMock) as mock_cancel:
        mock_cancel.return_value = None
        response = client.post("/api/game/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


def test_game_mode_switch_route():
    client = TestClient(app)
    response = client.post("/api/game/mode", json={"virtual_only": True})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["virtual_only"] is True

    # Restore to false
    response = client.post("/api/game/mode", json={"virtual_only": False})
    assert response.status_code == 200
    assert response.json()["virtual_only"] is False


def test_trigger_animation_route():
    client = TestClient(app)
    response = client.post("/api/leds/trigger_animation", json={"name": "GAME_WON"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["animation"] == "GAME_WON"


def test_test_trace_route():
    client = TestClient(app)
    response = client.post("/api/leds/test_trace", json={"uci": "e2e4"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["path"] == [[4, 1], [4, 2], [4, 3]]

    # Clear trace
    response = client.post("/api/leds/test_trace", json={"clear": True})
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_test_trace_route_with_is_capture():
    """Verify POST /api/leds/test_trace with is_capture flag."""
    client = TestClient(app)

    # 1. UCI move with is_capture=True
    response = client.post(
        "/api/leds/test_trace",
        json={"uci": "e2e4", "is_capture": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["path"] == [[4, 1], [4, 2], [4, 3]]

    # 2. Coordinate-based move with is_capture=True
    response_coords = client.post(
        "/api/leds/test_trace",
        json={"from_pos": [4, 1], "to_pos": [4, 3], "is_capture": True},
    )
    assert response_coords.status_code == 200
    assert response_coords.json()["status"] == "success"
    assert response_coords.json()["path"] == [[4, 1], [4, 2], [4, 3]]

    # 3. Clear trace
    response_clear = client.post("/api/leds/test_trace", json={"clear": True})
    assert response_clear.status_code == 200
    assert response_clear.json()["status"] == "success"


def test_claim_victory_route_success():
    """Verify POST /api/lichess/claim-victory succeeds when game is active."""
    from app.main import state_manager
    state_manager.game_status = "PLAYING"
    client = TestClient(app)

    with patch("app.main.lichess_engine.claim_victory", new_callable=AsyncMock) as mock_claim:
        mock_claim.return_value = True
        response = client.post("/api/lichess/claim-victory")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "claimed"
        mock_claim.assert_called_once_with(state_manager)


def test_claim_victory_game_route_alias_success():
    """Verify POST /api/game/claim-victory alias endpoint functions identically."""
    from app.main import state_manager
    state_manager.game_status = "PLAYING"
    client = TestClient(app)

    with patch("app.main.lichess_engine.claim_victory", new_callable=AsyncMock) as mock_claim:
        mock_claim.return_value = True
        response = client.post("/api/game/claim-victory")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "claimed"
        mock_claim.assert_called_once_with(state_manager)


def test_claim_victory_route_not_playing():
    """Verify POST /api/lichess/claim-victory returns error when no game is active."""
    from app.main import state_manager, lichess_engine
    state_manager.game_status = "IDLE"
    lichess_engine.current_game_id = None
    client = TestClient(app)

    response = client.post("/api/lichess/claim-victory")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert "No active game" in data["message"]


def test_settings_update_in_loop_calibration():
    """Verify REST API updates and returns in_loop_calibration correctly."""
    client = TestClient(app)

    # Disable in-loop calibration
    response = client.post("/api/board/settings", json={"in_loop_calibration": False})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["settings"]["in_loop_calibration"] is False

    # Re-enable in-loop calibration
    response = client.post("/api/board/settings", json={"in_loop_calibration": True})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["settings"]["in_loop_calibration"] is True


def test_calibrate_square_route_with_explicit_value():
    """Verify POST /api/board/calibrate_square sets square baseline to provided value."""
    from board_hardware import settings
    client = TestClient(app)

    response = client.post("/api/board/calibrate_square", json={"col": 2, "row": 3, "value": 1625})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["col"] == 2
    assert data["row"] == 3
    assert data["baseline"] == 1625
    assert settings["baselines"][2][3] == 1625


def test_calibrate_square_route_with_current_reading():
    """Verify POST /api/board/calibrate_square falls back to state_manager raw analog values."""
    from app.main import state_manager
    from board_hardware import settings
    state_manager.raw_analog_values[4][5] = 1780
    client = TestClient(app)

    response = client.post("/api/board/calibrate_square", json={"col": 4, "row": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["col"] == 4
    assert data["row"] == 5
    assert data["baseline"] == 1780
    assert settings["baselines"][4][5] == 1780


def test_calibrate_square_route_invalid_coordinates():
    """Verify POST /api/board/calibrate_square rejects out-of-bounds coordinates."""
    client = TestClient(app)

    response = client.post("/api/board/calibrate_square", json={"col": 8, "row": 0})
    assert response.status_code == 200
    assert response.json()["status"] == "error"

    response = client.post("/api/board/calibrate_square", json={"col": -1, "row": 3})
    assert response.status_code == 200
    assert response.json()["status"] == "error"





