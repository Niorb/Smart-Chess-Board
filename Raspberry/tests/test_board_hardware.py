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
        if n == 128:
            return packet_data
        return b''

    mock_ser.read.side_effect = mock_read

    res = calibrate_board("mock_h", mock_ser, duration_s=0.05)
    assert res is True
    assert settings["baselines"][0][0] == 1900
    assert len(baseline_history) == 0


def test_scan_board_binary_packet_mapping():
    import struct
    from unittest.mock import MagicMock

    from board_hardware import DEFAULT_COL_MUX_MAP, scan_board, settings

    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    mock_ser = MagicMock()

    # 64 uint16_t values: all equal to baseline
    base_val = settings["baselines"][0][0]
    thresh = settings.get("threshold_positive", 150)
    vals = [base_val] * 64

    # With DEFAULT_COL_MUX_MAP = [7, 6, 5, 4, 3, 2, 1, 0]:
    # MUX channel 7, row 0 -> index 56 corresponds to square a1 (c=0, r=0)
    # MUX channel 0, row 0 -> index 0 corresponds to square h1 (c=7, r=0)
    # MUX channel 4, row 3 -> index 35 corresponds to square d4 (c=3, r=3)
    vals[56] = base_val + thresh + 500  # Magnet on physical MUX ch 7, row 0 -> a1
    vals[35] = base_val + thresh + 300  # Magnet on physical MUX ch 4, row 3 -> d4

    packet_header = b'\xaa\x55'
    packet_data = struct.pack('<64H', *vals)

    def mock_read(n):
        if n == 2:
            return packet_header
        if n == 128:
            return packet_data
        return b''

    mock_ser.read.side_effect = mock_read

    matrix, diag = scan_board("mock_h", mock_ser, raw_state)
    assert diag["status"] == "OK"
    # Square a1 (c=0, r=0) should register magnet
    assert matrix[0][0] == base_val + thresh + 500
    assert raw_state[0][0] == 1
    # Square d4 (c=3, r=3) should register magnet
    assert matrix[3][3] == base_val + thresh + 300
    assert raw_state[3][3] == 1
    # Square h1 (c=7, r=0) should NOT register magnet
    assert matrix[7][0] == base_val
    assert raw_state[7][0] == 0


def test_scan_board_custom_col_mux_map_override():
    import struct
    from unittest.mock import MagicMock

    from board_hardware import scan_board, settings

    # Direct 1:1 identity mapping override
    settings["col_mux_map"] = [0, 1, 2, 3, 4, 5, 6, 7]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    mock_ser = MagicMock()

    base_val = settings["baselines"][0][0]
    thresh = settings.get("threshold_positive", 150)
    vals = [base_val] * 64
    vals[0] = base_val + thresh + 500  # Index 0 with identity mapping -> c=0, r=0 (a1)

    packet_header = b'\xaa\x55'
    packet_data = struct.pack('<64H', *vals)

    def mock_read(n):
        if n == 2:
            return packet_header
        if n == 128:
            return packet_data
        return b''

    mock_ser.read.side_effect = mock_read

    matrix, diag = scan_board("mock_h", mock_ser, raw_state)
    assert diag["status"] == "OK"
    assert matrix[0][0] == base_val + thresh + 500
    assert raw_state[0][0] == 1

    # Reset back to default
    from board_hardware import DEFAULT_COL_MUX_MAP
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)


def test_settle_us_auto_migration_and_atomic_save(tmp_path=None):
    import json
    import tempfile
    from board_hardware import DEFAULT_COL_MUX_MAP, load_settings, save_settings, settings

    with tempfile.TemporaryDirectory() as tmpdir:
        settings_path = os.path.join(tmpdir, "test_settings.json")
        os.environ["BOARD_SETTINGS_PATH"] = settings_path

        # Write legacy settings file with mux_settle_ms, invalid baselines, and missing col_mux_map
        legacy_content = {
            "mux_settle_ms": 0.15,
            "baselines": [[1500] * 4 for _ in range(4)]  # Invalid 4x4 matrix
        }
        with open(settings_path, "w") as f:
            json.dump(legacy_content, f)

        load_settings()

        # Check auto-migration: 0.15 ms * 1000 = 150 us
        assert settings["mux_settle_us"] == 150
        # Check matrix shape validation fallback to 8x8
        assert len(settings["baselines"]) == 8
        assert len(settings["baselines"][0]) == 8
        # Check col_mux_map fallback to DEFAULT_COL_MUX_MAP
        assert settings["col_mux_map"] == DEFAULT_COL_MUX_MAP

        # Test atomic save_settings
        settings["threshold_positive"] = 222
        save_settings()

        assert os.path.exists(settings_path)
        # Ensure temporary file was removed after atomic replace
        assert not os.path.exists(settings_path + ".tmp")

        with open(settings_path) as f:
            saved_data = json.load(f)
        assert saved_data["threshold_positive"] == 222
        assert saved_data["mux_settle_us"] == 150
        assert saved_data["col_mux_map"] == DEFAULT_COL_MUX_MAP

        # Clean up env var
        del os.environ["BOARD_SETTINGS_PATH"]




