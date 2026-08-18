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


def test_scan_board_dynamic_drift_middle_ranks():
    """Verify that empty middle ranks (r=2,3,4,5) drift over baseline_window_s when unoccupied."""
    import struct
    import time
    from unittest.mock import MagicMock
    from board_hardware import DEFAULT_COL_MUX_MAP, baseline_history, scan_board, settings

    baseline_history.clear()
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["baseline_window_s"] = 0.1
    settings["threshold_positive"] = 150
    settings["threshold_negative"] = 150

    # Start with baseline 1500 across the board
    settings["baselines"] = [[1500] * BOARD_ROWS for _ in range(BOARD_COLS)]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    # Provide raw reading of 1540 (within +/- 150 threshold, so raw_state == 0)
    raw_vals = [1540] * 64
    packet_header = b'\xaa\x55'
    packet_data = struct.pack('<64H', *raw_vals)

    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: packet_header if n == 2 else (packet_data if n == 128 else b'')

    # Seed baseline_history with an entry from 0.085s ago (within 0.1s window and >= 80% span)
    t0 = time.time() - 0.085
    for c in range(BOARD_COLS):
        for r in (2, 3, 4, 5):
            baseline_history[(c, r)] = [(t0, 1540, False)]

    scan_board(None, mock_ser, raw_state)

    # Middle ranks 3-6 (r in 2,3,4,5) should have drifted to 1540
    for c in range(BOARD_COLS):
        assert settings["baselines"][c][2] == 1540
        assert settings["baselines"][c][3] == 1540
        assert settings["baselines"][c][4] == 1540
        assert settings["baselines"][c][5] == 1540

        # Ranks 1 & 2 must inherit Rank 3 baseline (1540)
        assert settings["baselines"][c][0] == 1540
        assert settings["baselines"][c][1] == 1540

        # Ranks 7 & 8 must inherit Rank 6 baseline (1540)
        assert settings["baselines"][c][6] == 1540
        assert settings["baselines"][c][7] == 1540


def test_scan_board_starting_ranks_do_not_average_their_own_pieces():
    """Verify that pieces on ranks 1-2 and 7-8 are never directly averaged into baselines."""
    import struct
    import time
    from unittest.mock import MagicMock
    from board_hardware import DEFAULT_COL_MUX_MAP, baseline_history, scan_board, settings

    baseline_history.clear()
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["baseline_window_s"] = 0.1
    settings["threshold_positive"] = 120
    settings["threshold_negative"] = 120

    # Start with baseline 1550 everywhere
    settings["baselines"] = [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    # Ranks 1-2 have White piece reading 1200, Ranks 7-8 have Black piece reading 1900,
    # Middle ranks have empty reading 1550
    raw_vals = [0] * 64
    for mux_ch in range(8):
        c = DEFAULT_COL_MUX_MAP[mux_ch]
        for r in range(8):
            if r in (0, 1):
                val = 1200
            elif r in (6, 7):
                val = 1900
            else:
                val = 1550
            raw_vals[mux_ch * 8 + r] = val

    packet_header = b'\xaa\x55'
    packet_data = struct.pack('<64H', *raw_vals)

    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: packet_header if n == 2 else (packet_data if n == 128 else b'')

    # Seed baseline_history for middle ranks
    t0 = time.time() - 0.15
    for c in range(BOARD_COLS):
        for r in (2, 3, 4, 5):
            baseline_history[(c, r)] = [(t0, 1550, False)]

    # Run multiple scan cycles
    for _ in range(5):
        scan_board(None, mock_ser, raw_state)

    # Ranks 1-2 must NOT become 1200, Ranks 7-8 must NOT become 1900!
    for c in range(BOARD_COLS):
        assert settings["baselines"][c][0] == 1550
        assert settings["baselines"][c][1] == 1550
        assert settings["baselines"][c][6] == 1550
        assert settings["baselines"][c][7] == 1550


def test_scan_board_drift_suppressed_when_middle_square_occupied():
    """Verify that placing a piece on a middle rank stops drift updates for that square and inheritance."""
    import struct
    import time
    from unittest.mock import MagicMock
    from board_hardware import DEFAULT_COL_MUX_MAP, baseline_history, scan_board, settings

    baseline_history.clear()
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["baseline_window_s"] = 0.1
    settings["threshold_positive"] = 120
    settings["threshold_negative"] = 120

    # Initial baseline is 1550
    settings["baselines"] = [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    # Piece placed on d4 (c=3, r=3) and c3 (c=2, r=2) -> val = 1800 (> 1550 + 120)
    raw_vals = [1550] * 64
    for mux_ch in range(8):
        c = DEFAULT_COL_MUX_MAP[mux_ch]
        for r in range(8):
            if c == 3 and r == 3:
                raw_vals[mux_ch * 8 + r] = 1800
            elif c == 2 and r == 2:
                raw_vals[mux_ch * 8 + r] = 1800
            else:
                raw_vals[mux_ch * 8 + r] = 1550

    packet_header = b'\xaa\x55'
    packet_data = struct.pack('<64H', *raw_vals)

    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: packet_header if n == 2 else (packet_data if n == 128 else b'')

    t0 = time.time() - 0.15
    for c in range(BOARD_COLS):
        for r in (2, 3, 4, 5):
            baseline_history[(c, r)] = [(t0, 1550, False)]

    scan_board(None, mock_ser, raw_state)

    # Square (3, 3) must detect magnet (+1) and NOT drift to 1800
    assert raw_state[3][3] == 1
    assert settings["baselines"][3][3] == 1550

    # Square (2, 2) must detect magnet (+1), NOT drift to 1800, and NOT corrupt ranks 1-2
    assert raw_state[2][2] == 1
    assert settings["baselines"][2][2] == 1550
    assert settings["baselines"][2][0] == 1550
    assert settings["baselines"][2][1] == 1550


def test_starting_position_piece_detection_after_piece_calibration():
    """Verify piece calibration, detection on starting ranks, and SetupValidator readiness."""
    import struct
    from unittest.mock import MagicMock, patch
    from app.setup_validator import SetupValidator
    from board_hardware import (
        DEFAULT_COL_MUX_MAP,
        apply_debounce,
        calibrate_board_with_pieces,
        scan_board,
        settings,
    )

    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["threshold_positive"] = 120
    settings["threshold_negative"] = 120

    # 1. Simulate calibration with pieces placed:
    # Middle ranks 3..6 have ambient baseline 1550 + c * 10
    # Occupied ranks 1-2 have White piece reading (e.g. 1200)
    # Occupied ranks 7-8 have Black piece reading (e.g. 1900)
    calib_vals = [0] * 64
    for mux_ch in range(8):
        c = DEFAULT_COL_MUX_MAP[mux_ch]
        for r in range(8):
            if r in (0, 1):
                val = 1200 + c * 10  # White pieces on ranks 1-2
            elif r in (2, 3, 4, 5):
                val = 1550 + c * 10  # Empty ranks 3-6
            else:
                val = 1900 + c * 10  # Black pieces on ranks 7-8
            calib_vals[mux_ch * 8 + r] = val

    packet_header = b'\xaa\x55'
    calib_packet = struct.pack('<64H', *calib_vals)

    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: packet_header if n == 2 else (calib_packet if n == 128 else b'')

    with patch("board_hardware.save_settings"):
        res = calibrate_board_with_pieces(None, mock_ser, duration_s=0.05)
        assert res is True

    # Check baseline inheritance:
    for c in range(8):
        expected_rank3_base = 1550 + c * 10
        expected_rank6_base = 1550 + c * 10
        # Ranks 1-2 must inherit Rank 3 baseline
        assert settings["baselines"][c][0] == expected_rank3_base
        assert settings["baselines"][c][1] == expected_rank3_base
        # Ranks 7-8 must inherit Rank 6 baseline
        assert settings["baselines"][c][6] == expected_rank6_base
        assert settings["baselines"][c][7] == expected_rank6_base

    # 2. Simulate board scan with pieces placed in starting position
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    physical_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    stable_count = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    # Run scan
    scan_board(None, mock_ser, raw_state)

    # Check polarities:
    for c in range(8):
        # White pieces on ranks 1 & 2 -> -1 (South)
        assert raw_state[c][0] == -1
        assert raw_state[c][1] == -1
        # Empty ranks 3-6 -> 0
        assert raw_state[c][2] == 0
        assert raw_state[c][3] == 0
        assert raw_state[c][4] == 0
        assert raw_state[c][5] == 0
        # Black pieces on ranks 7 & 8 -> +1 (North)
        assert raw_state[c][6] == 1
        assert raw_state[c][7] == 1

    # Apply debounce over 2 cycles
    for _ in range(2):
        apply_debounce(raw_state, physical_state, stable_count, threshold=2)

    # Validate with SetupValidator
    validator = SetupValidator()
    setup_res = validator.validate(physical_state)
    assert setup_res.is_setup_ready is True
    assert len(setup_res.missing_white) == 0
    assert len(setup_res.missing_black) == 0
    assert len(setup_res.misplaced_pieces) == 0
    assert setup_res.white_count == 16
    assert setup_res.black_count == 16


def test_smart_pieces_detection_auto_and_manual_modes():
    """Verify smart pieces detection against ranks 3 & 6 and manual mode overrides."""
    import struct
    from unittest.mock import MagicMock
    from board_hardware import DEFAULT_COL_MUX_MAP, scan_board, settings

    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["threshold_positive"] = 100
    settings["threshold_negative"] = 100
    settings["baselines"] = [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    # 1. Full starting pieces layout
    raw_vals = [0] * 64
    for mux_ch in range(8):
        c = DEFAULT_COL_MUX_MAP[mux_ch]
        for r in range(8):
            if r in (0, 1):
                raw_vals[mux_ch * 8 + r] = 1200  # White pieces (< 1550 - 100)
            elif r in (6, 7):
                raw_vals[mux_ch * 8 + r] = 1900  # Black pieces (> 1550 + 100)
            else:
                raw_vals[mux_ch * 8 + r] = 1550  # Empty middle ranks
    
    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: b'\xaa\x55' if n == 2 else (struct.pack('<64H', *raw_vals) if n == 128 else b'')

    # Auto Mode with pieces placed
    settings["pieces_mode"] = "auto"
    _, diag = scan_board(None, mock_ser, raw_state)
    assert diag["pieces_detected"] is True
    assert diag["detected_starting_count"] == 32
    assert diag["effective_pieces_mode"] is True

    # Manual Override: Force Empty
    settings["pieces_mode"] = "empty"
    _, diag = scan_board(None, mock_ser, raw_state)
    assert diag["pieces_detected"] is True
    assert diag["pieces_mode"] == "empty"
    assert diag["effective_pieces_mode"] is False

    # 2. Empty board layout (all raw values near 1550)
    empty_vals = [1550] * 64
    mock_ser.read.side_effect = lambda n: b'\xaa\x55' if n == 2 else (struct.pack('<64H', *empty_vals) if n == 128 else b'')

    # Auto Mode with empty board
    settings["pieces_mode"] = "auto"
    _, diag = scan_board(None, mock_ser, raw_state)
    assert diag["pieces_detected"] is False
    assert diag["detected_starting_count"] == 0
    assert diag["effective_pieces_mode"] is False

    # Manual Override: Force Pieces
    settings["pieces_mode"] = "pieces"
    _, diag = scan_board(None, mock_ser, raw_state)
    assert diag["pieces_detected"] is False
    assert diag["pieces_mode"] == "pieces"
    assert diag["effective_pieces_mode"] is True


def test_empty_board_mode_calibrates_all_64_squares_directly():
    """Verify that when effective_pieces_mode is False, all 64 squares update directly."""
    import struct
    import time
    from unittest.mock import MagicMock
    from board_hardware import DEFAULT_COL_MUX_MAP, baseline_history, scan_board, settings

    baseline_history.clear()
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["pieces_mode"] = "empty"  # Force empty board mode
    settings["baseline_window_s"] = 0.1
    settings["threshold_positive"] = 100
    settings["threshold_negative"] = 100
    settings["baselines"] = [[1500] * BOARD_ROWS for _ in range(BOARD_COLS)]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    # Provide distinct reading of 1530 for all squares
    raw_vals = [1530] * 64
    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: b'\xaa\x55' if n == 2 else (struct.pack('<64H', *raw_vals) if n == 128 else b'')

    # Seed baseline_history for all 64 squares
    t0 = time.time() - 0.085
    for c in range(BOARD_COLS):
        for r in range(BOARD_ROWS):
            baseline_history[(c, r)] = [(t0, 1530, False)]

    scan_board(None, mock_ser, raw_state)

    # All 64 squares (ranks 0..7) should update directly to 1530
    for c in range(BOARD_COLS):
        for r in range(BOARD_ROWS):
            assert settings["baselines"][c][r] == 1530




