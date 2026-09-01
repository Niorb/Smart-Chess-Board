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

    # With DEFAULT_COL_MUX_MAP = [0, 1, 2, 3, 4, 5, 6, 7] in 90-deg CCW rotation:
    # c_chess = 7 - r_phys, r_chess = c_phys
    # MUX channel 0 (c_phys=0), r_phys 7 -> index 7 corresponds to square a1 (c=0, r=0)
    # MUX channel 0 (c_phys=0), r_phys 0 -> index 0 corresponds to square h1 (c=7, r=0)
    # MUX channel 3 (c_phys=3), r_phys 4 -> index 28 corresponds to square d4 (c=3, r=3)
    vals[7] = base_val + thresh + 500   # Magnet on physical MUX ch 0, r_phys 7 -> a1 (c=0, r=0)
    vals[28] = base_val + thresh + 300  # Magnet on physical MUX ch 3, r_phys 4 -> d4 (c=3, r=3)

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

    from board_hardware import DEFAULT_COL_MUX_MAP, scan_board, settings

    # Custom mapping override: col_mux_map = [7, 6, 5, 4, 3, 2, 1, 0]
    settings["col_mux_map"] = [7, 6, 5, 4, 3, 2, 1, 0]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    mock_ser = MagicMock()

    base_val = settings["baselines"][0][0]
    thresh = settings.get("threshold_positive", 150)
    vals = [base_val] * 64
    # MUX ch 7 (c_phys=0 -> r_chess=0), r_phys 7 (c_chess = 7 - 7 = 0) -> a1 (c=0, r=0) -> idx = 7*8 + 7 = 63
    vals[63] = base_val + thresh + 500

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
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)


def test_settle_us_auto_migration_and_atomic_save(tmp_path=None):
    import json
    import tempfile

    from board_hardware import DEFAULT_COL_MUX_MAP, load_settings, save_settings, settings

    with tempfile.TemporaryDirectory() as tmpdir:
        settings_path = os.path.join(tmpdir, "test_settings.json")
        old_env = os.environ.get("BOARD_SETTINGS_PATH")
        os.environ["BOARD_SETTINGS_PATH"] = settings_path

        try:
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
        finally:
            if old_env is not None:
                os.environ["BOARD_SETTINGS_PATH"] = old_env
            else:
                os.environ.pop("BOARD_SETTINGS_PATH", None)


def test_scan_board_dynamic_drift_middle_ranks():
    """Verify that unoccupied squares drift over baseline_window_s when unoccupied."""
    import struct
    import time
    from unittest.mock import MagicMock

    from board_hardware import DEFAULT_COL_MUX_MAP, baseline_history, scan_board, settings

    baseline_history.clear()
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["pieces_mode"] = "pieces"
    settings["baseline_window_s"] = 0.1
    settings["threshold_positive"] = 150
    settings["threshold_negative"] = 150
    settings["in_loop_calibration"] = True

    # Start with baseline 1500 across the board
    settings["baselines"] = [[1500] * BOARD_ROWS for _ in range(BOARD_COLS)]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    # Provide raw reading of 1540 (within +/- 150 threshold, so raw_state == 0)
    raw_vals = [1540] * 64
    packet_header = b'\xaa\x55'
    packet_data = struct.pack('<64H', *raw_vals)

    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: packet_header if n == 2 else (packet_data if n == 128 else b'')

    # Seed baseline_history for all squares with an entry from 0.085s ago (within 0.1s window and >= 80% span)
    t0 = time.time() - 0.085
    for c in range(BOARD_COLS):
        for r in range(BOARD_ROWS):
            baseline_history[(c, r)] = [(t0, 1540, False)]

    scan_board(None, mock_ser, raw_state)

    # All unoccupied squares should have drifted directly to 1540
    for c in range(BOARD_COLS):
        for r in range(BOARD_ROWS):
            assert settings["baselines"][c][r] == 1540


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
        c_phys = DEFAULT_COL_MUX_MAP[mux_ch]
        for r_phys in range(8):
            7 - r_phys
            r_chess = c_phys
            if r_chess in (0, 1):
                val = 1200
            elif r_chess in (6, 7):
                val = 1900
            else:
                val = 1550
            raw_vals[mux_ch * 8 + r_phys] = val

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
        c_phys = DEFAULT_COL_MUX_MAP[mux_ch]
        for r_phys in range(8):
            c_chess = 7 - r_phys
            r_chess = c_phys
            if c_chess == 3 and r_chess == 3 or c_chess == 2 and r_chess == 2:
                raw_vals[mux_ch * 8 + r_phys] = 1800
            else:
                raw_vals[mux_ch * 8 + r_phys] = 1550

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
        c_phys = DEFAULT_COL_MUX_MAP[mux_ch]
        for r_phys in range(8):
            c_chess = 7 - r_phys
            r_chess = c_phys
            if r_chess in (0, 1):
                val = 1200 + c_chess * 10  # White pieces on ranks 1-2
            elif r_chess in (2, 3, 4, 5):
                val = 1550 + c_chess * 10  # Empty ranks 3-6
            else:
                val = 1900 + c_chess * 10  # Black pieces on ranks 7-8
            calib_vals[mux_ch * 8 + r_phys] = val

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
        c_phys = DEFAULT_COL_MUX_MAP[mux_ch]
        for r_phys in range(8):
            7 - r_phys
            r_chess = c_phys
            if r_chess in (0, 1):
                raw_vals[mux_ch * 8 + r_phys] = 1200  # White pieces (< 1550 - 100)
            elif r_chess in (6, 7):
                raw_vals[mux_ch * 8 + r_phys] = 1900  # Black pieces (> 1550 + 100)
            else:
                raw_vals[mux_ch * 8 + r_phys] = 1550  # Empty middle ranks

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
    settings["in_loop_calibration"] = True
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


def test_freeze_baseline_suppresses_drift():
    """Verify that when freeze_baseline is True, baselines and history are not mutated."""
    import struct
    from unittest.mock import MagicMock

    from board_hardware import DEFAULT_COL_MUX_MAP, baseline_history, scan_board, settings

    baseline_history.clear()
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["pieces_mode"] = "empty"
    settings["baseline_window_s"] = 0.1
    settings["threshold_positive"] = 180
    settings["threshold_negative"] = 180
    settings["baselines"] = [[1500] * BOARD_ROWS for _ in range(BOARD_COLS)]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    raw_vals = [1700] * 64
    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: b'\xaa\x55' if n == 2 else (struct.pack('<64H', *raw_vals) if n == 128 else b'')

    # Call scan_board with freeze_baseline=True
    scan_board(None, mock_ser, raw_state, freeze_baseline=True)

    # Baseline must remain untouched at 1500
    assert settings["baselines"][0][0] == 1500
    assert len(baseline_history) == 0


def test_load_settings_creates_settings_file():
    """
    Verify that when board_settings.json does not exist,
    load_settings() initializes default settings and creates board_settings.json.
    """
    import json
    import tempfile

    from board_hardware import load_settings, settings

    with tempfile.TemporaryDirectory() as tmpdir:
        settings_path = os.path.join(tmpdir, "board_settings.json")
        old_env = os.environ.get("BOARD_SETTINGS_PATH")
        os.environ["BOARD_SETTINGS_PATH"] = settings_path

        try:
            assert not os.path.exists(settings_path)

            load_settings()

            assert settings["threshold_positive"] == 200
            assert settings["threshold_negative"] == 200

            assert os.path.exists(settings_path)
            with open(settings_path) as f:
                saved_content = json.load(f)
            assert saved_content["threshold_positive"] == 200
        finally:
            if old_env is not None:
                os.environ["BOARD_SETTINGS_PATH"] = old_env
            else:
                os.environ.pop("BOARD_SETTINGS_PATH", None)


def test_baseline_not_calibrated_when_piece_lifted():
    """
    Verify that when a piece was on a square and is lifted, in-loop calibration / drift
    does NOT immediately adopt the reading, because the history window contains detected entries.
    """
    import struct
    import time
    from unittest.mock import MagicMock

    from board_hardware import DEFAULT_COL_MUX_MAP, baseline_history, scan_board, settings

    baseline_history.clear()
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["baseline_window_s"] = 2.0
    settings["threshold_positive"] = 120
    settings["threshold_negative"] = 120
    settings["pieces_mode"] = "pieces"

    # Baseline is 1550
    settings["baselines"] = [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    now = time.time()
    # History contains recent detection entries from when piece was still on d4 (3, 3)
    baseline_history[(3, 3)] = [
        (now - 1.5, 1850, True),  # Piece was on square
        (now - 1.0, 1850, True),  # Piece was on square
        (now - 0.5, 1850, True),  # Piece was on square
    ]

    # Piece is now lifted: raw reading returns to 1570 (minor offset)
    raw_vals = [1550] * 64
    for mux_ch in range(8):
        c_phys = DEFAULT_COL_MUX_MAP[mux_ch]
        for r_phys in range(8):
            c_chess = 7 - r_phys
            r_chess = c_phys
            if c_chess == 3 and r_chess == 3:
                raw_vals[mux_ch * 8 + r_phys] = 1570
            else:
                raw_vals[mux_ch * 8 + r_phys] = 1550

    packet_header = b'\xaa\x55'
    packet_data = struct.pack('<64H', *raw_vals)

    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: packet_header if n == 2 else (packet_data if n == 128 else b'')

    scan_board(None, mock_ser, raw_state)

    # Square (3, 3) is now empty (raw_state == 0), but baseline must NOT update to 1570
    assert raw_state[3][3] == 0
    assert settings["baselines"][3][3] == 1550


def test_in_loop_calibration_default_setting():
    """Verify that in_loop_calibration defaults to True in settings."""
    from board_hardware import settings
    assert settings.get("in_loop_calibration", True) is True


def test_scan_board_in_loop_calibration_disabled_suppresses_drift():
    """Verify that when in_loop_calibration is False, baseline drift is suppressed in scan_board."""
    import struct
    import time
    from unittest.mock import MagicMock

    from board_hardware import DEFAULT_COL_MUX_MAP, baseline_history, scan_board, settings

    baseline_history.clear()
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["pieces_mode"] = "empty"
    settings["baseline_window_s"] = 0.1
    settings["threshold_positive"] = 150
    settings["threshold_negative"] = 150
    settings["in_loop_calibration"] = False
    settings["baselines"] = [[1500] * BOARD_ROWS for _ in range(BOARD_COLS)]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    raw_vals = [1540] * 64
    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: b'\xaa\x55' if n == 2 else (struct.pack('<64H', *raw_vals) if n == 128 else b'')

    t0 = time.time() - 0.085
    for c in range(BOARD_COLS):
        for r in range(BOARD_ROWS):
            baseline_history[(c, r)] = [(t0, 1540, False)]

    scan_board(None, mock_ser, raw_state, freeze_baseline=False)

    # Baseline must NOT change when in_loop_calibration is False
    for c in range(BOARD_COLS):
        for r in range(BOARD_ROWS):
            assert settings["baselines"][c][r] == 1500

    # Reset
    settings["in_loop_calibration"] = True


def test_set_square_baseline_with_explicit_value():
    """Verify that set_square_baseline updates settings and clears history for that square."""
    from board_hardware import baseline_history, set_square_baseline, settings

    baseline_history[(3, 4)] = [(100.0, 1600, False)]
    val = set_square_baseline(3, 4, 1650)
    assert val == 1650
    assert settings["baselines"][3][4] == 1650
    assert (3, 4) not in baseline_history


def test_set_square_baseline_invalid_coords_returns_negative():
    """Verify set_square_baseline returns -1 on invalid coordinates."""
    from board_hardware import set_square_baseline
    assert set_square_baseline(-1, 0, 1500) == -1
    assert set_square_baseline(8, 0, 1500) == -1
    assert set_square_baseline(0, 8, 1500) == -1


def test_save_defaults_function(tmp_path, monkeypatch):
    """Verify that save_defaults saves directly to board_settings.json."""
    import json

    from board_hardware import save_defaults, settings
    user_file = str(tmp_path / "board_settings.json")
    monkeypatch.setenv("BOARD_SETTINGS_PATH", user_file)

    settings["threshold_positive"] = 350
    settings["threshold_negative"] = 450

    res = save_defaults()
    assert res is True
    assert os.path.exists(user_file)

    with open(user_file) as f:
        data = json.load(f)
        assert data["threshold_positive"] == 350
        assert data["threshold_negative"] == 450


def test_vacated_square_calibrates_to_own_baseline_after_piece_moves():
    """Verify that when a piece moves off a square, that square cleanly self-calibrates to its empty reading."""
    import struct
    import time
    from unittest.mock import MagicMock

    from board_hardware import DEFAULT_COL_MUX_MAP, baseline_history, scan_board, settings

    baseline_history.clear()
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["baseline_window_s"] = 0.1
    settings["threshold_positive"] = 120
    settings["threshold_negative"] = 120
    settings["in_loop_calibration"] = True

    # Initial baselines
    settings["baselines"] = [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    # e2 (c=4, r=1) vacates and has empty reading 1580; e1 (c=4, r=0) still has piece (1200)
    raw_vals = [1550] * 64
    for mux_ch in range(8):
        c_phys = DEFAULT_COL_MUX_MAP[mux_ch]
        for r_phys in range(8):
            c_chess = 7 - r_phys
            r_chess = c_phys
            if c_chess == 4 and r_chess == 0:
                raw_vals[mux_ch * 8 + r_phys] = 1200  # Occupied piece on e1
            elif c_chess == 4 and r_chess == 1:
                raw_vals[mux_ch * 8 + r_phys] = 1580  # Vacated e2
            else:
                raw_vals[mux_ch * 8 + r_phys] = 1550

    packet_header = b'\xaa\x55'
    packet_data = struct.pack('<64H', *raw_vals)

    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: packet_header if n == 2 else (packet_data if n == 128 else b'')

    # Seed baseline_history for e2 (c=4, r=1) with 1580
    t0 = time.time() - 0.085
    baseline_history[(4, 1)] = [(t0, 1580, False)]
    # Seed baseline_history for e1 (c=4, r=0) with 1200 (detected)
    baseline_history[(4, 0)] = [(t0, 1200, True)]

    scan_board(None, mock_ser, raw_state)

    # e2 (4, 1) drifts to 1580
    assert settings["baselines"][4][1] == 1580
    # e1 (4, 0) remains stable at 1550 (does NOT drift into 1200 piece reading)
    assert settings["baselines"][4][0] == 1550


def test_occupied_square_on_rank3_does_not_block_other_column_squares():
    """Verify that an occupied piece on rank 3 does not block other unoccupied squares in that column from drifting."""
    import struct
    import time
    from unittest.mock import MagicMock

    from board_hardware import DEFAULT_COL_MUX_MAP, baseline_history, scan_board, settings

    baseline_history.clear()
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["baseline_window_s"] = 0.1
    settings["threshold_positive"] = 120
    settings["threshold_negative"] = 120
    settings["in_loop_calibration"] = True

    settings["baselines"] = [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    # c3 (c=2, r=2) has a piece (1850). Other squares in col 2 have drifted to 1530.
    raw_vals = [1550] * 64
    for mux_ch in range(8):
        c_phys = DEFAULT_COL_MUX_MAP[mux_ch]
        for r_phys in range(8):
            c_chess = 7 - r_phys
            r_chess = c_phys
            if c_chess == 2 and r_chess == 2:
                raw_vals[mux_ch * 8 + r_phys] = 1850  # Occupied c3
            elif c_chess == 2:
                raw_vals[mux_ch * 8 + r_phys] = 1530  # Empty squares on c-file
            else:
                raw_vals[mux_ch * 8 + r_phys] = 1550

    packet_header = b'\xaa\x55'
    packet_data = struct.pack('<64H', *raw_vals)

    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: packet_header if n == 2 else (packet_data if n == 128 else b'')

    t0 = time.time() - 0.085
    for r in range(BOARD_ROWS):
        if r == 2:
            baseline_history[(2, r)] = [(t0, 1850, True)]
        else:
            baseline_history[(2, r)] = [(t0, 1530, False)]

    scan_board(None, mock_ser, raw_state)

    # c3 (2, 2) is occupied and stays at 1550
    assert settings["baselines"][2][2] == 1550
    # c1, c2, c4, c5, c6, c7, c8 all drift independently to 1530 despite c3 being occupied
    assert settings["baselines"][2][0] == 1530
    assert settings["baselines"][2][1] == 1530
    assert settings["baselines"][2][3] == 1530
    assert settings["baselines"][2][4] == 1530
    assert settings["baselines"][2][5] == 1530
    assert settings["baselines"][2][6] == 1530
    assert settings["baselines"][2][7] == 1530


def test_independent_sensor_offsets_preserved():
    """Verify that independent quiescent sensor baselines are preserved and do not overwrite each other."""
    import struct
    import time
    from unittest.mock import MagicMock

    from board_hardware import DEFAULT_COL_MUX_MAP, baseline_history, scan_board, settings

    baseline_history.clear()
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["baseline_window_s"] = 0.1
    settings["threshold_positive"] = 120
    settings["threshold_negative"] = 120
    settings["in_loop_calibration"] = True

    # Set distinct initial baselines
    settings["baselines"] = [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)]
    settings["baselines"][0][0] = 1510
    settings["baselines"][0][1] = 1530
    settings["baselines"][0][2] = 1570

    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    raw_vals = [1550] * 64
    for mux_ch in range(8):
        c_phys = DEFAULT_COL_MUX_MAP[mux_ch]
        for r_phys in range(8):
            c_chess = 7 - r_phys
            r_chess = c_phys
            if c_chess == 0 and r_chess == 0:
                raw_vals[mux_ch * 8 + r_phys] = 1515
            elif c_chess == 0 and r_chess == 1:
                raw_vals[mux_ch * 8 + r_phys] = 1535
            elif c_chess == 0 and r_chess == 2:
                raw_vals[mux_ch * 8 + r_phys] = 1575
            else:
                raw_vals[mux_ch * 8 + r_phys] = 1550

    packet_header = b'\xaa\x55'
    packet_data = struct.pack('<64H', *raw_vals)

    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: packet_header if n == 2 else (packet_data if n == 128 else b'')

    t0 = time.time() - 0.085
    baseline_history[(0, 0)] = [(t0, 1515, False)]
    baseline_history[(0, 1)] = [(t0, 1535, False)]
    baseline_history[(0, 2)] = [(t0, 1575, False)]

    scan_board(None, mock_ser, raw_state)

    assert settings["baselines"][0][0] == 1515
    assert settings["baselines"][0][1] == 1535
    assert settings["baselines"][0][2] == 1575


def test_read_adc_packet_with_noisy_preamble():
    """Verify _read_adc_packet recovers from noisy/boot preamble and captures 128B payload."""
    import struct
    from unittest.mock import MagicMock

    from board_hardware import _read_adc_packet

    raw_vals = [1550] * 64
    payload = struct.pack('<64H', *raw_vals)

    # Stream with junk bytes before 0xAA 0x55
    stream_buffer = list(b'BOOTLOG:ESP32\r\n\xaa\x55' + payload)

    mock_ser = MagicMock()
    def mock_read(n=1):
        nonlocal stream_buffer
        if not stream_buffer:
            return b''
        chunk = stream_buffer[:n]
        stream_buffer = stream_buffer[n:]
        return bytes(chunk)

    mock_ser.read.side_effect = mock_read

    res = _read_adc_packet(mock_ser, timeout_s=0.5)
    assert res is not None
    assert len(res) == 128
    assert res == payload


def test_scan_board_expected_empty_squares_filters_drift():
    """Verify that scan_board only allows squares in expected_empty_squares to drift."""
    import struct
    import time
    from unittest.mock import MagicMock

    from board_hardware import DEFAULT_COL_MUX_MAP, baseline_history, scan_board, settings

    baseline_history.clear()
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["baseline_window_s"] = 0.1
    settings["threshold_positive"] = 120
    settings["threshold_negative"] = 120
    settings["in_loop_calibration"] = True
    settings["baselines"] = [[1500] * BOARD_ROWS for _ in range(BOARD_COLS)]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    raw_vals = [1540] * 64
    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: b'\xaa\x55' if n == 2 else (struct.pack('<64H', *raw_vals) if n == 128 else b'')

    # Seed baseline_history for e2 (4, 1) and e4 (4, 3)
    t0 = time.time() - 0.085
    baseline_history[(4, 1)] = [(t0, 1540, False)]
    baseline_history[(4, 3)] = [(t0, 1540, False)]

    # Only e2 (4, 1) is expected empty (e4 is expected to have a piece)
    expected_empty = {(4, 1)}

    _, diag = scan_board(None, mock_ser, raw_state, expected_empty_squares=expected_empty)

    # e2 should have drifted to 1540
    assert settings["baselines"][4][1] == 1540
    # e4 was not in expected_empty, so it must NOT drift and its history must be cleared
    assert settings["baselines"][4][3] == 1500
    assert (4, 3) not in baseline_history
    assert diag["baselines_updated"] is True


def test_scan_board_expected_empty_with_unexpected_physical_piece_suppresses_drift():
    """Verify that an unexpected physical piece on an expected empty square suppresses baseline drift."""
    import struct
    import time
    from unittest.mock import MagicMock

    from board_hardware import DEFAULT_COL_MUX_MAP, baseline_history, scan_board, settings

    baseline_history.clear()
    settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)
    settings["baseline_window_s"] = 0.1
    settings["threshold_positive"] = 120
    settings["threshold_negative"] = 120
    settings["in_loop_calibration"] = True
    settings["baselines"] = [[1500] * BOARD_ROWS for _ in range(BOARD_COLS)]
    raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    # e4 (4, 3) has an unexpected piece reading 1850 (> 1500 + 120)
    raw_vals = [1500] * 64
    for mux_ch in range(8):
        c_phys = DEFAULT_COL_MUX_MAP[mux_ch]
        for r_phys in range(8):
            if (7 - r_phys) == 4 and c_phys == 3:
                raw_vals[mux_ch * 8 + r_phys] = 1850

    mock_ser = MagicMock()
    mock_ser.read.side_effect = lambda n: b'\xaa\x55' if n == 2 else (struct.pack('<64H', *raw_vals) if n == 128 else b'')

    t0 = time.time() - 0.085
    baseline_history[(4, 3)] = [(t0, 1850, True)]

    expected_empty = {(4, 3)}
    _, diag = scan_board(None, mock_ser, raw_state, expected_empty_squares=expected_empty)

    # e4 must remain 1500 (not drift to 1850)
    assert settings["baselines"][4][3] == 1500
    assert diag["baselines_updated"] is False


def test_set_square_baseline_persists_settings():
    """Verify set_square_baseline calls save_settings when updating a square."""
    from unittest.mock import patch
    from board_hardware import set_square_baseline, settings

    settings["baselines"][2][2] = 1500
    with patch("board_hardware.save_settings") as mock_save:
        res = set_square_baseline(2, 2, 1620)
        assert res == 1620
        assert settings["baselines"][2][2] == 1620
        mock_save.assert_called_once()












