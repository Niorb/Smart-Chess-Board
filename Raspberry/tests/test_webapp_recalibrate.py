"""
tests/test_webapp_recalibrate.py

Unit tests for calibrate_board_with_pieces:
- Tests that middle ranks 3-6 are measured directly
- Tests that ranks 1 & 2 inherit rank 3 baselines
- Tests that ranks 7 & 8 inherit rank 6 baselines
- Tests POST /api/board/calibrate_with_pieces endpoint
"""

import os
import sys
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from board_hardware import calibrate_board_with_pieces, settings


def test_calibrate_board_with_pieces_mapping():
    mock_ser = MagicMock()
    # Mock ESP32 128-byte binary response
    # 64 values: uint16_t (2 bytes each)
    import struct

    raw_vals = []
    for mux_ch in range(8):
        for r in range(8):
            # Give distinct values per rank
            # e.g., rank 1=2100, rank 2=2100, rank 3=1600, rank 4=1600, rank 5=1600, rank 6=1700, rank 7=2200, rank 8=2200
            if r in (0, 1):
                raw_vals.append(2100)
            elif r in (2, 3, 4):
                raw_vals.append(1600)
            elif r == 5:
                raw_vals.append(1700)
            else:
                raw_vals.append(2200)

    data_bytes = struct.pack('<64H', *raw_vals)
    mock_ser.read.side_effect = [b'\xaa\x55', data_bytes]

    with patch("board_hardware.save_settings"):
        res = calibrate_board_with_pieces(None, mock_ser, duration_s=0.05)
        assert res is True

        for c in range(8):
            # Ranks 1 and 2 (r=0, 1) should inherit Rank 3 baseline (1600), NOT 2100!
            assert settings["baselines"][c][0] == 1600
            assert settings["baselines"][c][1] == 1600

            # Rank 3 should be 1600
            assert settings["baselines"][c][2] == 1600

            # Rank 6 should be 1700
            assert settings["baselines"][c][5] == 1700

            # Ranks 7 and 8 (r=6, 7) should inherit Rank 6 baseline (1700), NOT 2200!
            assert settings["baselines"][c][6] == 1700
            assert settings["baselines"][c][7] == 1700


def test_calibrate_board_with_pieces_route():
    client = TestClient(app)
    with patch("app.board_state.state_manager._safe_calibrate_with_pieces", return_value=True):
        response = client.post("/api/board/calibrate_with_pieces")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "Calibration with pieces completed" in data["message"]
