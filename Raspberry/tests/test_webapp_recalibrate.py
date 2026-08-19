"""
tests/test_webapp_recalibrate.py

Unit tests for calibrate_board_with_pieces:
- Tests that middle ranks 3-6 (r in 2, 3, 4, 5) are measured directly for all columns
- Tests that ranks 1 & 2 (r in 0, 1) inherit rank 3 (r=2) baselines per column
- Tests that ranks 7 & 8 (r in 6, 7) inherit rank 6 (r=5) baselines per column
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
        c_phys = DEFAULT_COL_MUX_MAP[mux_ch]
        for r_phys in range(8):
            c_chess = 7 - r_phys
            r_chess = c_phys
            # Give distinct values per chess rank r_chess:
            # ranks 1 & 2 (r_chess=0, 1): 2100 (occupied with pieces)
            # rank 3 (r_chess=2): 1600 (empty)
            # ranks 4, 5 (r_chess=3, 4): 1650 (empty)
            # rank 6 (r_chess=5): 1700 (empty)
            # ranks 7 & 8 (r_chess=6, 7): 2200 (occupied with pieces)
            if r_chess in (0, 1):
                val = 2100 + c_chess * 10
            elif r_chess == 2:
                val = 1600 + c_chess * 10
            elif r_chess in (3, 4):
                val = 1650 + c_chess * 10
            elif r_chess == 5:
                val = 1700 + c_chess * 10
            else:
                val = 2200 + c_chess * 10
            raw_vals[mux_ch * 8 + r_phys] = val

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

        for c in range(8):
            col_offset = c * 10
            # Ranks 1 & 2 (r=0, 1) must inherit Rank 3 baseline (1600 + col_offset), NOT 2100!
            assert settings["baselines"][c][0] == 1600 + col_offset
            assert settings["baselines"][c][1] == 1600 + col_offset

            # Rank 3 should be 1600 + col_offset
            assert settings["baselines"][c][2] == 1600 + col_offset

            # Rank 6 should be 1700 + col_offset
            assert settings["baselines"][c][5] == 1700 + col_offset

            # Ranks 7 & 8 (r=6, 7) must inherit Rank 6 baseline (1700 + col_offset), NOT 2200!
            assert settings["baselines"][c][6] == 1700 + col_offset
            assert settings["baselines"][c][7] == 1700 + col_offset


def test_calibrate_board_with_pieces_route():
    client = TestClient(app)
    with patch("app.board_state.state_manager._safe_calibrate_with_pieces", return_value=True):
        response = client.post("/api/board/calibrate_with_pieces")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "Calibration with pieces completed" in data["message"]
