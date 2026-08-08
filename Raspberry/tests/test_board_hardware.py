import os
import sys

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from board_hardware import (
    BOARD_COLS,
    BOARD_ROWS,
    apply_debounce,
    settings,
)


def test_board_dimensions():
    assert BOARD_ROWS == 8
    assert BOARD_COLS == 8

def test_apply_debounce_no_change():
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    sensor_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    stable_count = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    changed = apply_debounce(raw_state, sensor_state, stable_count, threshold=2)
    assert not changed
    assert sensor_state == raw_state
    assert stable_count[0][0] == 0

def test_apply_debounce_with_threshold():
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    sensor_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    stable_count = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    # Simulate magnet placement on c=2, r=3
    raw_state[2][3] = 1

    # First scan: state should not change yet (stable count becomes 1)
    changed = apply_debounce(raw_state, sensor_state, stable_count, threshold=2)
    assert not changed
    assert sensor_state[2][3] == 0
    assert stable_count[2][3] == 1

    # Second scan: threshold reached (stable count becomes 2 -> state flips to 1)
    changed = apply_debounce(raw_state, sensor_state, stable_count, threshold=2)
    assert changed
    assert sensor_state[2][3] == 1
    assert stable_count[2][3] == 0

def test_apply_debounce_reset_on_bounce():
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    sensor_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    stable_count = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    # Scan 1: noise on c=0, r=0
    raw_state[0][0] = 1
    apply_debounce(raw_state, sensor_state, stable_count, threshold=2)
    assert stable_count[0][0] == 1

    # Scan 2: noise disappears
    raw_state[0][0] = 0
    changed = apply_debounce(raw_state, sensor_state, stable_count, threshold=2)
    assert not changed
    assert stable_count[0][0] == 0
    assert sensor_state[0][0] == 0

def test_settings_defaults():
    assert "threshold_positive" in settings
    assert "threshold_negative" in settings
    assert "baselines" in settings
    assert len(settings["baselines"]) == BOARD_COLS
    assert len(settings["baselines"][0]) == BOARD_ROWS

def test_calibrate_board_clears_baseline_history():
    import struct
    from unittest.mock import MagicMock

    from board_hardware import baseline_history, calibrate_board, settings

    # Seed baseline_history with stale pre-calibration data
    baseline_history[(0, 0)] = [(100.0, 1200, False)]

    mock_ser = MagicMock()
    # Mock header 0xAA 0x55 + 64 uint16_t values (all set to 1900)
    packet_header = b'\xaa\x55'
    packet_data = struct.pack('<64H', *([1900] * 64))

    def mock_read(n):
        if n == 2:
            return packet_header
        elif n == 128:
            return packet_data
        return b''

    mock_ser.read.side_effect = mock_read

    res = calibrate_board("mock_h", mock_ser, duration_s=0.05)
    assert res is True
    assert settings["baselines"][0][0] == 1900
    assert len(baseline_history) == 0


