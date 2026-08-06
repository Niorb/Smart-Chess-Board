import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def parse_sq(sq):
    sq = sq.strip().lower()
    if len(sq) != 2:
        return None
    file_ch, rank_ch = sq[0], sq[1]
    if file_ch not in "abcdefgh" or rank_ch not in "12345678":
        return None
    return ord(file_ch) - ord("a") + 1, int(rank_ch)

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
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    response = client.get("/api/board/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "subsystems" in data
    assert "matrix" in data

def test_settings_update_route():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    
    payload = {
        "threshold_positive": 130,
        "threshold_negative": 130,
    }
    response = client.post("/api/board/settings", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["settings"]["threshold_positive"] == 130
    assert data["settings"]["threshold_negative"] == 130


def test_clear_leds_route():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    response = client.post("/api/board/clear_leds")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "All LEDs turned off"


