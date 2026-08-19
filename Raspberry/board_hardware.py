"""
board_hardware.py

Shared hardware helpers for the Smart Chess Board (Analog + Pi MUX Version).
Controls the MUX via lgpio on the Pi, but requests the analog value
from the ESP32 over a Serial Request-Response protocol.
"""

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger("smart-chess-app.hardware")

try:
    import lgpio
except ImportError:
    class MockLgpio:
        def gpiochip_open(self, _): return "mock_chip"
        def gpiochip_close(self, _): pass
        def gpio_claim_output(self, *args): pass
        def gpio_claim_input(self, *args): pass
        def gpio_write(self, *args): pass
        def gpio_read(self, *args): return 1
        def callback(self, *args): pass
        error = Exception
        FALLING_EDGE = 1
        SET_PULL_UP = 1
    lgpio = MockLgpio()
    print("WARNING: lgpio not found. Using MockLgpio.")

try:
    from app.config import (
        BOARD_COLS,
        BOARD_ROWS,
    )
except ImportError:
    BOARD_ROWS = 8
    BOARD_COLS = 8

# =============================================================================
# PERSISTENT SETTINGS
# =============================================================================

SETTINGS_FILE = os.environ.get(
    "BOARD_SETTINGS_PATH",
    os.path.join(os.path.dirname(__file__), "board_settings.json")
)


def get_settings_filepath():
    return os.environ.get(
        "BOARD_SETTINGS_PATH",
        SETTINGS_FILE
    )


DEFAULT_COL_MUX_MAP = [7, 6, 5, 4, 3, 2, 1, 0]

# Default settings (with swapped terminology: columns are ranks 8..1, rows are files a..h)
settings: dict[str, Any] = {
    "baselines": [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)],
    "threshold_positive": 200,
    "threshold_negative": 200,
    "col_mode": "auto",
    "manual_col": 0,
    "scan_delay": 100,
    "mux_settle_us": 100,
    "debounce_threshold": 2,
    "baseline_window_s": 2,
    "disabled_squares": [],
    "col_mux_map": list(DEFAULT_COL_MUX_MAP),
    "pieces_mode": "auto",  # "auto" | "pieces" | "empty"
    "coach_hints_enabled": True,
    "eval_bar_enabled": True,
    "coach_ai_only": True,
    "in_loop_calibration": True,
    "last_game_params": None,
}

last_sent_settle_us = None


def load_settings():
    global settings
    filepath = get_settings_filepath()
    source_file = None
    loaded = None

    # Tier 1: Check primary user settings file
    if os.path.exists(filepath):
        source_file = filepath
    else:
        # Tier 2: Check default factory template in the same directory
        default_template_path = os.path.join(
            os.path.dirname(filepath) if os.path.dirname(filepath) else ".",
            "board_settings.default.json"
        )
        if os.path.exists(default_template_path):
            source_file = default_template_path
            logger.info(f"User settings {filepath} not found. Initializing from template {default_template_path}")

    if source_file and os.path.exists(source_file):
        try:
            with open(source_file) as f:
                loaded = json.load(f)

                # Check for legacy row terminology keys and migrate them
                if "row_mode" in loaded:
                    loaded["col_mode"] = loaded["row_mode"]
                    del loaded["row_mode"]
                if "manual_row" in loaded:
                    loaded["manual_col"] = loaded["manual_row"]
                    del loaded["manual_row"]

                # Auto-migration for legacy mux_settle_ms -> mux_settle_us if absent
                if "mux_settle_us" not in loaded:
                    if "mux_settle_ms" in loaded:
                        try:
                            ms_val = float(loaded["mux_settle_ms"])
                            loaded["mux_settle_us"] = min(255, max(0, int(ms_val * 1000)))
                        except (TypeError, ValueError):
                            loaded["mux_settle_us"] = 100
                    else:
                        loaded["mux_settle_us"] = 100
                else:
                    try:
                        loaded["mux_settle_us"] = min(255, max(0, int(loaded["mux_settle_us"])))
                    except (TypeError, ValueError):
                        loaded["mux_settle_us"] = 100

                if "disabled_squares" not in loaded:
                    loaded["disabled_squares"] = []

                # Validate col_mux_map
                col_mux_map = loaded.get("col_mux_map")
                is_valid_col_mux_map = (
                    isinstance(col_mux_map, list)
                    and len(col_mux_map) == BOARD_COLS
                    and all(
                        isinstance(x, int) and 0 <= x < BOARD_COLS
                        for x in col_mux_map
                    )
                )
                if not is_valid_col_mux_map:
                    if "col_mux_map" in loaded:
                        logger.warning(
                            f"Invalid col_mux_map in {source_file}. Using standard default mapping."
                        )
                    loaded["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)

                # Validate baseline matrix shape (8 rows x 8 columns)
                baselines = loaded.get("baselines")
                is_valid_baselines = (
                    isinstance(baselines, list)
                    and len(baselines) == BOARD_COLS
                    and all(
                        isinstance(col, list) and len(col) == BOARD_ROWS
                        for col in baselines
                    )
                )
                if not is_valid_baselines:
                    logger.warning(
                        f"Invalid baselines matrix shape in {source_file}. Using standard default matrix."
                    )
                    loaded["baselines"] = [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)]

                settings.update(loaded)
                logger.info(f"Loaded board settings from {source_file}")
        except Exception as e:
            logger.error(f"Error loading settings from {source_file}: {e}")

    # If primary user settings file does not exist yet, save settings to initialize it
    if not os.path.exists(filepath):
        try:
            save_settings()
            logger.info(f"Initialized user settings file at {filepath}")
        except Exception as e:
            logger.error(f"Error auto-initializing settings file: {e}")

    # Ensure col_mux_map is valid in settings
    col_mux_map = settings.get("col_mux_map")
    is_valid_col_mux_map = (
        isinstance(col_mux_map, list)
        and len(col_mux_map) == BOARD_COLS
        and all(
            isinstance(x, int) and 0 <= x < BOARD_COLS
            for x in col_mux_map
        )
    )
    if not is_valid_col_mux_map:
        logger.warning("col_mux_map invalid in settings dictionary. Falling back to default mapping.")
        settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)

    # Ensure baseline matrix shape is valid in settings
    baselines = settings.get("baselines")
    is_valid_baselines = (
        isinstance(baselines, list)
        and len(baselines) == BOARD_COLS
        and all(
            isinstance(col, list) and len(col) == BOARD_ROWS
            for col in baselines
        )
    )
    if not is_valid_baselines:
        logger.warning("Baselines shape invalid in settings dictionary. Falling back to default matrix.")
        settings["baselines"] = [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)]


def save_settings():
    filepath = get_settings_filepath()
    tmp_path = filepath + ".tmp"
    try:
        target_dir = os.path.dirname(filepath)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)

        with open(tmp_path, "w") as f:
            json.dump(settings, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, filepath)
        logger.info(f"Saved board settings to {filepath}")
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def save_defaults(overwrite_factory_template: bool = True) -> bool:
    """
    Saves current in-memory settings (including dynamic baselines, thresholds,
    and board parameters) to persistent settings (board_settings.json) and
    optionally updates the default factory template (board_settings.default.json).
    """
    save_settings()
    if overwrite_factory_template:
        filepath = get_settings_filepath()
        default_template_path = os.path.join(
            os.path.dirname(filepath) if os.path.dirname(filepath) else ".",
            "board_settings.default.json"
        )
        tmp_path = default_template_path + ".tmp"
        try:
            target_dir = os.path.dirname(default_template_path)
            if target_dir:
                os.makedirs(target_dir, exist_ok=True)
            with open(tmp_path, "w") as f:
                json.dump(settings, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, default_template_path)
            logger.info(f"Saved default template to {default_template_path}")
        except Exception as e:
            logger.error(f"Error saving default template: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
    return True


# Initial load on module import
load_settings()

# Dynamic baseline history (timestamp, raw_value, detected_magnet) for each square
baseline_history: dict = {}

# Latest smart piece detection status
latest_detection_state: dict[str, Any] = {
    "pieces_detected": False,
    "detected_starting_count": 0,
    "pieces_mode": "auto",
    "effective_pieces_mode": False,
}


def get_latest_detection_state() -> dict[str, Any]:
    return dict(latest_detection_state)

# =============================================================================
# MUX PIN ASSIGNMENTS & COMPATIBILITY STUBS
# =============================================================================

COL_MUX_S0 = 17
COL_MUX_S1 = 27
COL_MUX_S2 = 22
COL_MUX_S3 = 23

def set_mux_channel(_h, _s0, _s1, _s2, _s3, _channel):
    """No-op on the Pi — MUX is controlled directly by the ESP32 coprocessor."""

def init_mux_pins(_h):
    """No-op on the Pi — MUX is controlled directly by the ESP32 coprocessor."""

def clear_baseline_history():
    """Clears dynamic baseline drift historical window samples."""
    global baseline_history
    baseline_history.clear()


def set_square_baseline(col: int, row: int, value: int | None = None) -> int:
    """
    Sets baseline for an individual square and removes it from dynamic baseline history.
    If value is provided, updates settings["baselines"][col][row].
    Returns the updated baseline value.
    """
    global baseline_history, settings
    if 0 <= col < BOARD_COLS and 0 <= row < BOARD_ROWS:
        if value is not None:
            settings["baselines"][col][row] = int(value)
            baseline_history.pop((col, row), None)
        return settings["baselines"][col][row]
    return -1


# =============================================================================
# BOARD SCANNING (HYBRID)
# =============================================================================

def scan_board(h, serial_conn, raw_state, freeze_baseline=False):
    """
    Scans the board and returns both the raw matrix and a dictionary of diagnostic info.
    Reads values as a single batch from the serial interface.
    When freeze_baseline is True, dynamic baseline drift updating is suppressed.
    """
    matrix = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    diag = {
        "status": "OK",
        "last_raw_line": "",
        "timeouts": 0,
        "errors": 0
    }
    if serial_conn is None:
        diag["status"] = "NO_HARDWARE"
        return matrix, diag

    # Flush any stale serial data
    serial_conn.reset_input_buffer()

    col_mode = settings.get("col_mode", "auto")
    manual_col = settings.get("manual_col", 0)
    col_mux_map = settings.get("col_mux_map", DEFAULT_COL_MUX_MAP)
    settle_us = min(255, max(0, int(settings.get("mux_settle_us", 100))))
    non_mocked_count = (1 if col_mode == "manual" else BOARD_COLS) * BOARD_ROWS

    global last_sent_settle_us
    if last_sent_settle_us != settle_us:
        serial_conn.write(b'S' + bytes([min(255, max(0, int(settle_us)))]))
        last_sent_settle_us = settle_us

    serial_conn.write(b'B')

    # Read binary packet: 2 header bytes + data bytes
    header = serial_conn.read(2)
    if len(header) == 2 and header[0] == 0xAA and header[1] == 0x55:
        expected_bytes = BOARD_COLS * BOARD_ROWS * 2
        data = serial_conn.read(expected_bytes)
        if len(data) == expected_bytes:
            import struct
            vals = struct.unpack(f'<{BOARD_COLS * BOARD_ROWS}H', data)
            diag["last_raw_line"] = f"BINARY:{len(vals)} vals"
            for mux_ch in range(BOARD_COLS):
                c_phys = col_mux_map[mux_ch]
                for r_phys in range(BOARD_ROWS):
                    val = vals[mux_ch * BOARD_ROWS + r_phys]
                    c = 7 - r_phys
                    r = c_phys

                    if col_mode == "manual" and c != manual_col:
                        matrix[c][r] = settings["baselines"][c][r]
                        raw_state[c][r] = 0
                        continue

                    disabled_squares = settings.get("disabled_squares", [])
                    if [c, r] in disabled_squares or (c, r) in disabled_squares:
                        matrix[c][r] = settings["baselines"][c][r]
                        raw_state[c][r] = 0
                        continue

                    matrix[c][r] = val
                    diff = val - settings["baselines"][c][r]
                    if diff > settings["threshold_positive"]:
                        raw_state[c][r] = 1
                    elif diff < -settings["threshold_negative"]:
                        raw_state[c][r] = -1
                    else:
                        raw_state[c][r] = 0

            # Smart Starting Piece Detection against Ranks 3 & 6
            thresh_pos = settings.get("threshold_positive", 200)
            thresh_neg = settings.get("threshold_negative", 200)
            detected_starting_count = 0

            for c in range(BOARD_COLS):
                ref_rank3 = matrix[c][2]  # Rank 3 reference
                ref_rank6 = matrix[c][5]  # Rank 6 reference

                # White starting pieces on Ranks 1 & 2 (r=0, 1)
                for r in (0, 1):
                    diff_white = matrix[c][r] - ref_rank3
                    if diff_white < -thresh_neg or diff_white > thresh_pos:
                        detected_starting_count += 1

                # Black starting pieces on Ranks 7 & 8 (r=6, 7)
                for r in (6, 7):
                    diff_black = matrix[c][r] - ref_rank6
                    if diff_black > thresh_pos or diff_black < -thresh_neg:
                        detected_starting_count += 1

            pieces_detected = (detected_starting_count >= 4)
            pieces_mode = settings.get("pieces_mode", "auto")

            if pieces_mode == "pieces":
                effective_pieces_mode = True
            elif pieces_mode == "empty":
                effective_pieces_mode = False
            else:
                effective_pieces_mode = pieces_detected

            global latest_detection_state
            latest_detection_state = {
                "pieces_detected": pieces_detected,
                "detected_starting_count": detected_starting_count,
                "pieces_mode": pieces_mode,
                "effective_pieces_mode": effective_pieces_mode,
            }

            diag["pieces_detected"] = pieces_detected
            diag["detected_starting_count"] = detected_starting_count
            diag["pieces_mode"] = pieces_mode
            diag["effective_pieces_mode"] = effective_pieces_mode

            # Dynamic baseline drift tracking (suppressed when baseline is frozen during animations or in_loop_calibration is disabled)
            in_loop_cal = settings.get("in_loop_calibration", True)
            baseline_window = settings.get("baseline_window_s", 2)
            if in_loop_cal and not freeze_baseline and baseline_window > 0:
                now = time.time()
                if effective_pieces_mode:
                    # Pieces Placed Mode: Only empty middle ranks 3..6 drift and propagate to ranks 1-2 & 7-8
                    for c in range(BOARD_COLS):
                        for r in (2, 3, 4, 5):
                            val = matrix[c][r]
                            detected = (raw_state[c][r] != 0)

                            if (c, r) not in baseline_history:
                                baseline_history[(c, r)] = []

                            baseline_history[(c, r)].append((now, val, detected))

                            history = baseline_history[(c, r)]
                            while history and (now - history[0][0]) > baseline_window:
                                history.pop(0)

                            if len(history) > 0 and not any(entry[2] for entry in history):
                                if (now - history[0][0]) >= (baseline_window * 0.8):
                                    avg_val = int(sum(entry[1] for entry in history) / len(history))
                                    settings["baselines"][c][r] = avg_val

                                    if r == 2:  # Rank 3 drift -> update Ranks 1 & 2
                                        settings["baselines"][c][0] = avg_val
                                        settings["baselines"][c][1] = avg_val
                                    elif r == 5:  # Rank 6 drift -> update Ranks 7 & 8
                                        settings["baselines"][c][6] = avg_val
                                        settings["baselines"][c][7] = avg_val
                else:
                    # Empty Board Mode: All 64 squares (ranks 1-8) drift directly on their own readings
                    for c in range(BOARD_COLS):
                        for r in range(BOARD_ROWS):
                            val = matrix[c][r]
                            detected = (raw_state[c][r] != 0)

                            if (c, r) not in baseline_history:
                                baseline_history[(c, r)] = []

                            baseline_history[(c, r)].append((now, val, detected))

                            history = baseline_history[(c, r)]
                            while history and (now - history[0][0]) > baseline_window:
                                history.pop(0)

                            if len(history) > 0 and not any(entry[2] for entry in history):
                                if (now - history[0][0]) >= (baseline_window * 0.8):
                                    avg_val = int(sum(entry[1] for entry in history) / len(history))
                                    settings["baselines"][c][r] = avg_val
        else:
            diag["errors"] = non_mocked_count
            diag["status"] = "TIMEOUT"
            serial_conn.reset_input_buffer()
            for c in range(BOARD_COLS):
                for r in range(BOARD_ROWS):
                    matrix[c][r] = settings["baselines"][c][r]
                    raw_state[c][r] = 0
    else:
        diag["errors"] = non_mocked_count
        diag["status"] = "PARSE_ERROR"
        serial_conn.reset_input_buffer()
        for c in range(BOARD_COLS):
            for r in range(BOARD_ROWS):
                matrix[c][r] = settings["baselines"][c][r]
                raw_state[c][r] = 0

    return matrix, diag


def calibrate_board(h, serial_conn, duration_s=2.0):
    """
    Reads samples per channel continuously over a specified duration (default 2 seconds),
    averages them, and saves the new values as baselines in the persistent configuration settings.
    """
    if serial_conn is None:
        logger.error("Calibration failed: serial connection not initialized.")
        return False

    sums = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    counts = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    # Flush buffers
    serial_conn.reset_input_buffer()

    col_mux_map = settings.get("col_mux_map", DEFAULT_COL_MUX_MAP)
    settle_us = min(255, max(0, int(settings.get("mux_settle_us", 100))))
    global last_sent_settle_us
    if last_sent_settle_us != settle_us:
        serial_conn.write(b'S' + bytes([min(255, max(0, int(settle_us)))]))
        last_sent_settle_us = settle_us

    start_time = time.time()
    while time.time() - start_time < duration_s:
        serial_conn.write(b'B')
        header = serial_conn.read(2)
        if len(header) == 2 and header[0] == 0xAA and header[1] == 0x55:
            expected_bytes = BOARD_COLS * BOARD_ROWS * 2
            data = serial_conn.read(expected_bytes)
            if len(data) == expected_bytes:
                import struct
                vals = struct.unpack(f'<{BOARD_COLS * BOARD_ROWS}H', data)
                for mux_ch in range(BOARD_COLS):
                    c_phys = col_mux_map[mux_ch]
                    for r_phys in range(BOARD_ROWS):
                        val = vals[mux_ch * BOARD_ROWS + r_phys]
                        c = 7 - r_phys
                        r = c_phys
                        sums[c][r] += val
                        counts[c][r] += 1
            else:
                serial_conn.reset_input_buffer()
        else:
            serial_conn.reset_input_buffer()
        time.sleep(0.01)

    total_valid_samples = sum(sum(counts[c]) for c in range(BOARD_COLS))
    if total_valid_samples == 0:
        logger.error("Calibration failed: no valid data packets received from hardware.")
        return False

    # Update baselines
    for c in range(BOARD_COLS):
        for r in range(BOARD_ROWS):
            if counts[c][r] > 0:
                avg_val = int(sums[c][r] / counts[c][r])
                if avg_val > 0:
                    settings["baselines"][c][r] = avg_val
                else:
                    settings["baselines"][c][r] = 1550
            else:
                settings["baselines"][c][r] = 1550

    save_settings()

    # Clear rolling baseline history
    global baseline_history
    baseline_history.clear()

    return True


def calibrate_board_with_pieces(h, serial_conn, duration_s=2.0):
    """
    Calibrates board baselines when pieces are already in standard starting layout.
    Ignores/does not read the first 2 ranks (r=0, 1) and last 2 ranks (r=6, 7)
    where pieces are placed. Reads empty middle ranks 3-6 (r=2, 3, 4, 5) directly:
    - Ranks 1 & 2 (r=0, 1) baselines are set to Rank 3 (r=2) baseline for each column.
    - Ranks 7 & 8 (r=6, 7) baselines are set to Rank 6 (r=5) baseline for each column.
    - Ranks 3, 4, 5, 6 (r in 2, 3, 4, 5) use their own directly measured baselines for each column.
    """
    if serial_conn is None:
        logger.error("Calibration with pieces failed: serial connection not initialized.")
        return False

    sums = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    counts = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]

    # Flush buffers
    serial_conn.reset_input_buffer()

    col_mux_map = settings.get("col_mux_map", DEFAULT_COL_MUX_MAP)
    settle_us = min(255, max(0, int(settings.get("mux_settle_us", 100))))
    global last_sent_settle_us
    if last_sent_settle_us != settle_us:
        serial_conn.write(b'S' + bytes([min(255, max(0, int(settle_us)))]))
        last_sent_settle_us = settle_us

    start_time = time.time()
    while time.time() - start_time < duration_s:
        serial_conn.write(b'B')
        header = serial_conn.read(2)
        if len(header) == 2 and header[0] == 0xAA and header[1] == 0x55:
            expected_bytes = BOARD_COLS * BOARD_ROWS * 2
            data = serial_conn.read(expected_bytes)
            if len(data) == expected_bytes:
                import struct
                vals = struct.unpack(f'<{BOARD_COLS * BOARD_ROWS}H', data)
                for mux_ch in range(BOARD_COLS):
                    c_phys = col_mux_map[mux_ch]
                    for r_phys in range(BOARD_ROWS):
                        val = vals[mux_ch * BOARD_ROWS + r_phys]
                        c = 7 - r_phys
                        r = c_phys
                        # Only read empty middle ranks 3, 4, 5, 6 (r=2, 3, 4, 5) for all columns
                        if r in (2, 3, 4, 5):
                            sums[c][r] += val
                            counts[c][r] += 1
            else:
                serial_conn.reset_input_buffer()
        else:
            serial_conn.reset_input_buffer()
        time.sleep(0.01)

    total_valid_samples = sum(sum(counts[c][r] for r in (2, 3, 4, 5)) for c in range(BOARD_COLS))
    if total_valid_samples == 0:
        logger.error("Calibration with pieces failed: no valid data packets received from hardware.")
        return False

    # Compute raw average for measured middle ranks across all columns
    measured_avg = [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)]
    for c in range(BOARD_COLS):
        for r in (2, 3, 4, 5):
            if counts[c][r] > 0:
                avg_val = int(sums[c][r] / counts[c][r])
                measured_avg[c][r] = avg_val if avg_val > 0 else 1550

    # Update settings baselines:
    for c in range(BOARD_COLS):
        base_rank3 = measured_avg[c][2]  # Rank 3 (r=2) baseline for column c
        base_rank6 = measured_avg[c][5]  # Rank 6 (r=5) baseline for column c

        # Ranks 1 & 2 (r=0, 1) -> mapped to Rank 3 (r=2) baseline of column c
        settings["baselines"][c][0] = base_rank3
        settings["baselines"][c][1] = base_rank3

        # Middle ranks 3, 4, 5, 6 (r in 2, 3, 4, 5) -> own measured baselines
        settings["baselines"][c][2] = measured_avg[c][2]
        settings["baselines"][c][3] = measured_avg[c][3]
        settings["baselines"][c][4] = measured_avg[c][4]
        settings["baselines"][c][5] = measured_avg[c][5]

        # Ranks 7 & 8 (r=6, 7) -> mapped to Rank 6 (r=5) baseline of column c
        settings["baselines"][c][6] = base_rank6
        settings["baselines"][c][7] = base_rank6

    save_settings()

    # Clear rolling baseline history
    global baseline_history
    baseline_history.clear()

    logger.info("Successfully calibrated board baselines with pieces in place.")
    return True


# =============================================================================
# DEBOUNCING
# =============================================================================

def apply_debounce(raw_state, sensor_state, stable_count, threshold):
    """
    Apply debouncing. Returns True if any square's state changed.
    """
    changed = False
    for c in range(BOARD_COLS):
        for r in range(BOARD_ROWS):
            if raw_state[c][r] == sensor_state[c][r]:
                stable_count[c][r] = 0
            else:
                stable_count[c][r] += 1
                if stable_count[c][r] >= threshold:
                    sensor_state[c][r] = raw_state[c][r]
                    stable_count[c][r] = 0
                    changed = True
    return changed
