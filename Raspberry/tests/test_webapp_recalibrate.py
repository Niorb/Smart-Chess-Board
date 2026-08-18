"""
tests/test_webapp_recalibrate.py

Unit tests for calibrate_board_with_pieces:
- Tests that middle columns 3-6 (c in 2, 3, 4, 5) are measured directly
- Tests that columns 1 & 2 (c in 0, 1) inherit column 3 (c=2) baselines
- Tests that columns 7 & 8 (c in 6, 7) inherit column 6 (c=5) baselines
- Tests POST /api/board/calibrate_with_pieces endpoint
"""

import os
import sys
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from board_hardware import DEFAULT_COL_MUX_MAP, calibrate_board_with_pieces, settings


def test_calibrate_board_with_pieces_mapping():
    mock_ser = MagicMock()
    # Mock ESP32 128-byte binary response (64 uint16_t values)
    import struct

    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    raw_vals = [0] * 64
    for mux_ch in range(8):
        c = DEFAULT_COL_MUX_MAP[mux_ch]
        for r in range(8):
            # Give distinct values per column c:
            # col 1 & 2 (c=0, 1): 2100 (occupied with pieces)
            # col 3 (c=2): 1600 (empty)
            # col 4, 5 (c=3, 4): 1650 (empty)
            # col 6 (c=5): 1700 (empty)
            # col 7 & 8 (c=6, 7): 2200 (occupied with pieces)
            if c in (0, 1):
                val = 2100
            elif c == 2:
                val = 1600
            elif c in (3, 4):
                val = 1650
            elif c == 5:
                val = 1700
            else:
                val = 2200
            raw_vals[mux_ch * 8 + r] = val

    packet_header = b'\xaa\x55'
    packet_data = struct.pack('<64H', *raw_vals)

    def mock_read(n):
        if n == 2:
            return packet_header
        if n == 128:
            return packet_data
        return b''

    mock_ser.read.side_effect = mock_read

    with patch("board_hardware.save_settings"):
        res = calibrate_board_with_pieces(None, mock_ser, duration_s=0.05)
        assert res is True

        for r in range(8):
            # Columns 1 & 2 (c=0, 1) must inherit Column 3 baseline (1600), NOT 2100!
            assert settings["baselines"][0][r] == 1600
            assert settings["baselines"][1][r] == 1600

            # Column 3 should be 1600
            assert settings["baselines"][2][r] == 1600

            # Column 6 should be 1700
            assert settings["baselines"][5][r] == 1700

            # Columns 7 & 8 (c=6, 7) must inherit Column 6 baseline (1700), NOT 2200!
            assert settings["baselines"][6][r] == 1700
            assert settings["baselines"][7][r] == 1700


def test_calibrate_board_with_pieces_route():
    client = TestClient(app)
    with patch("app.board_state.state_manager._safe_calibrate_with_pieces", return_value=True):
        response = client.post("/api/board/calibrate_with_pieces")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "Calibration with pieces completed" in data["message"]
