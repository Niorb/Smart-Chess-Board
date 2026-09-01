"""
board_hardware.py

Shared hardware helpers for the Smart Chess Board (Analog + Pi MUX Version).
Controls the MUX via lgpio on the Pi, but requests the analog value
from the ESP32 over a Serial Request-Response protocol.
"""

import json
import logging
import os
import struct
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
    logger.warning("lgpio not found. Using MockLgpio.")

try:
    from app.config import (
        BOARD_COLS,
        BOARD_ROWS,
    )
    from app.led_helpers import (
        CMD_SCAN_ADC,
        CMD_SET_SETTLE,
        RESP_ADC_DATA,
        build_packet,
        calc_crc8,
    )
except ImportError:
    BOARD_ROWS = 8
    BOARD_COLS = 8
    CMD_SCAN_ADC = 0x01
    CMD_SET_SETTLE = 0x02
    RESP_ADC_DATA = 0x81

    def calc_crc8(data, initial=0x00):
        crc = initial
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 0x80:
                    crc = ((crc << 1) ^ 0x07) & 0xFF
                else:
                    crc = (crc << 1) & 0xFF
        return crc

    def build_packet(cmd_id, payload=b''):
        length = len(payload)
        len_bytes = bytes([length & 0xFF, (length >> 8) & 0xFF])
        cmd_bytes = bytes([cmd_id & 0xFF])
        crc = calc_crc8(cmd_bytes + len_bytes + payload)
        return b'\xaa\x55' + cmd_bytes + len_bytes + payload + bytes([crc])

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


DEFAULT_COL_MUX_MAP = [0, 1, 2, 3, 4, 5, 6, 7]


def _is_valid_mux_map(col_mux_map) -> bool:
    return (
        isinstance(col_mux_map, list)
        and len(col_mux_map) == BOARD_COLS
        and all(
            isinstance(x, int) and 0 <= x < BOARD_COLS
            for x in col_mux_map
        )
    )


def _is_valid_baseline_matrix(baselines) -> bool:
    return (
        isinstance(baselines, list)
        and len(baselines) == BOARD_COLS
        and all(
            isinstance(col, list) and len(col) == BOARD_ROWS
            for col in baselines
        )
    )

def get_default_settings() -> dict[str, Any]:
    return {
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
        "clock_bar_enabled": True,
        "coach_ai_only": True,
        "in_loop_calibration": True,
        "led_intensity": 100,
        "night_mode": False,
        "auto_queen_timeout_s": 5.0,
        "opening_hints_enabled": True,
        "max_sideline_hints": 2,
        "last_game_params": None,
    }


# Default settings
settings: dict[str, Any] = get_default_settings()

last_sent_settle_us = None


def load_settings():
    global settings
    filepath = get_settings_filepath()
    loaded = None

    if os.path.exists(filepath):
        try:
            with open(filepath) as f:
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

                # Auto-migration/validation for led_intensity (10..100)
                if "led_intensity" in loaded:
                    try:
                        loaded["led_intensity"] = min(100, max(10, int(loaded["led_intensity"])))
                    except (TypeError, ValueError):
                        loaded["led_intensity"] = 100
                else:
                    loaded["led_intensity"] = 100

                # Auto-migration/validation for night_mode
                if "night_mode" in loaded:
                    loaded["night_mode"] = bool(loaded["night_mode"])
                else:
                    loaded["night_mode"] = False

                # Validate col_mux_map
                if not _is_valid_mux_map(loaded.get("col_mux_map")):
                    if "col_mux_map" in loaded:
                        logger.warning(
                            f"Invalid col_mux_map in {filepath}. Using standard default mapping."
                        )
                    loaded["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)

                # Validate baseline matrix shape (8 rows x 8 columns)
                if not _is_valid_baseline_matrix(loaded.get("baselines")):
                    logger.warning(
                        f"Invalid baselines matrix shape in {filepath}. Using standard default matrix."
                    )
                    loaded["baselines"] = [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)]

                settings.update(loaded)
                logger.info(f"Loaded board settings from {filepath}")
        except Exception as e:
            logger.error(f"Error loading settings from {filepath}: {e}")
    else:
        logger.info(f"User settings {filepath} not found. Initializing with default settings.")
        settings.clear()
        settings.update(get_default_settings())
        try:
            save_settings()
            logger.info(f"Initialized user settings file at {filepath}")
        except Exception as e:
            logger.error(f"Error auto-initializing settings file: {e}")

    # Ensure col_mux_map is valid in settings
    if not _is_valid_mux_map(settings.get("col_mux_map")):
        logger.warning("col_mux_map invalid in settings dictionary. Falling back to default mapping.")
        settings["col_mux_map"] = list(DEFAULT_COL_MUX_MAP)

    # Ensure baseline matrix shape is valid in settings
    if not _is_valid_baseline_matrix(settings.get("baselines")):
        logger.warning("Baselines shape invalid in settings dictionary. Falling back to default matrix.")
        settings["baselines"] = [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)]


def save_settings():
    filepath = get_settings_filepath()
    tmp_path = filepath + ".tmp"
    try:
        target_dir = os.path.dirname(filepath)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)

        # Create a backup of the existing settings before atomic replace
        if os.path.exists(filepath):
            try:
                import shutil
                shutil.copyfile(filepath, filepath + ".bak")
            except Exception:
                pass

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


def save_defaults() -> bool:
    """
    Saves current in-memory settings (including dynamic baselines, thresholds,
    and board parameters) to persistent storage (board_settings.json).
    """
    save_settings()
    return True


def get_last_game_params() -> dict:
    """Returns the persisted last-game matchmaking parameters with standard defaults."""
    params = settings.get("last_game_params") or {}
    return {
        "time_control": params.get("time_control", "10+0"),
        "rated": bool(params.get("rated", False)),
        "color": params.get("color", "random"),
        "opponent": params.get("opponent", "auto"),
        "ai_level": params.get("ai_level", 3),
        "rating_range": params.get("rating_range", None),
    }


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
            save_settings()
        return settings["baselines"][col][row]
    return -1


def _read_adc_packet(serial_conn, timeout_s=0.08) -> bytes | None:
    """
    Reads 128-byte ADC payload from serial_conn.
    Fast path: reads 2-byte header (0xAA 0x55) in 1 shot.
    Recovery path: scans byte-by-byte to resynchronize if header is misaligned or noisy.
    Supports framed RESP_ADC_DATA packets (0xAA 0x55 0x81 LEN_LO LEN_HI ... 128B ... CRC8)
    and legacy raw response packets (0xAA 0x55 ... 128B ...).
    """
    header = serial_conn.read(2)
    synced = (len(header) == 2 and header[0] == 0xAA and header[1] == 0x55)

    if not synced:
        t0 = time.time()
        prev_byte = header[-1] if len(header) > 0 else None
        while time.time() - t0 < timeout_s:
            if prev_byte == 0xAA:
                b2 = serial_conn.read(1)
                if b2 and b2[0] == 0x55:
                    synced = True
                    break
                prev_byte = b2[0] if b2 else None
                continue
            b = serial_conn.read(1)
            if not b:
                continue
            if b[0] == 0xAA:
                b2 = serial_conn.read(1)
                if b2 and b2[0] == 0x55:
                    synced = True
                    break
                prev_byte = b2[0] if b2 else None
            else:
                prev_byte = b[0]

    if not synced:
        return None

    data = serial_conn.read(128)
    if len(data) == 128:
        if data[0] == RESP_ADC_DATA and data[1] == 0x80 and data[2] == 0x00:
            # Binary framed packet starting with 0x81 0x80 0x00
            extra = serial_conn.read(4)
            if len(extra) != 4:
                return None
            full_payload = data[3:] + extra[:3]
            if calc_crc8(data[:3] + full_payload) != extra[3]:
                return None
            return full_payload
        # Raw 128-byte ADC data
        return data
    return None


# =============================================================================
# BOARD SCANNING (HYBRID)
# =============================================================================

def _send_settle_if_needed(serial_conn, settle_us: int):
    """Sends CMD_SET_SETTLE to the ESP32 only when the settle time changed since last send."""
    global last_sent_settle_us
    if last_sent_settle_us != settle_us:
        packet = build_packet(CMD_SET_SETTLE, bytes([min(255, max(0, int(settle_us)))]))
        serial_conn.write(packet)
        last_sent_settle_us = settle_us


def _normalize_disabled_squares(raw_disabled) -> set:
    """Normalizes disabled_squares entries ([c, r] lists or (c, r) tuples) into a set of tuples."""
    if not raw_disabled:
        return set()
    return {
        tuple(sq) if isinstance(sq, (list, tuple)) else sq
        for sq in raw_disabled
    }


def scan_board(h, serial_conn, raw_state, freeze_baseline=False, expected_empty_squares=None):
    """
    Scans the board and returns both the raw matrix and a dictionary of diagnostic info.
    Reads values as a single batch from the serial interface using framed binary packets.
    When freeze_baseline is True, dynamic baseline drift updating is suppressed.
    """
    matrix = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    diag = {
        "status": "OK",
        "last_raw_line": "",
        "timeouts": 0,
        "errors": 0,
        "baselines_updated": False,
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

    _send_settle_if_needed(serial_conn, settle_us)

    serial_conn.write(build_packet(CMD_SCAN_ADC))

    # Read binary packet: framed or legacy
    data = _read_adc_packet(serial_conn)
    expected_bytes = BOARD_COLS * BOARD_ROWS * 2
    if data is not None and len(data) == expected_bytes:
        vals = struct.unpack(f'<{BOARD_COLS * BOARD_ROWS}H', data)
        diag["last_raw_line"] = f"BINARY:{len(vals)} vals"

        baselines = settings["baselines"]
        thresh_pos = settings["threshold_positive"]
        thresh_neg = settings["threshold_negative"]
        disabled = _normalize_disabled_squares(settings.get("disabled_squares"))

        for mux_ch in range(BOARD_COLS):
            c_phys = col_mux_map[mux_ch]
            for r_phys in range(BOARD_ROWS):
                val = vals[mux_ch * BOARD_ROWS + r_phys]
                c = 7 - r_phys
                r = c_phys

                if col_mode == "manual" and c != manual_col:
                    matrix[c][r] = baselines[c][r]
                    raw_state[c][r] = 0
                    continue

                if (c, r) in disabled:
                    matrix[c][r] = baselines[c][r]
                    raw_state[c][r] = 0
                    continue

                matrix[c][r] = val
                diff = val - baselines[c][r]
                if diff > thresh_pos:
                    raw_state[c][r] = 1
                elif diff < -thresh_neg:
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
            for c in range(BOARD_COLS):
                for r in range(BOARD_ROWS):
                    if (c, r) in disabled:
                        continue

                    if expected_empty_squares is not None and (c, r) not in expected_empty_squares:
                        baseline_history.pop((c, r), None)
                        continue

                    val = matrix[c][r]
                    detected = (raw_state[c][r] != 0)

                    history = baseline_history.setdefault((c, r), [])
                    history.append((now, val, detected))

                    # Prune expired samples in one pass (history is time-ordered)
                    stale = 0
                    for entry in history:
                        if now - entry[0] > baseline_window:
                            stale += 1
                        else:
                            break
                    if stale:
                        del history[:stale]

                    if history and not any(entry[2] for entry in history) and (now - history[0][0]) >= (baseline_window * 0.8):
                        avg_val = int(sum(entry[1] for entry in history) / len(history))
                        if settings["baselines"][c][r] != avg_val:
                            settings["baselines"][c][r] = avg_val
                            diag["baselines_updated"] = True
    else:
        diag["errors"] = non_mocked_count
        diag["status"] = "TIMEOUT" if data is None else "PARSE_ERROR"
        serial_conn.reset_input_buffer()
        for c in range(BOARD_COLS):
            for r in range(BOARD_ROWS):
                matrix[c][r] = settings["baselines"][c][r]
                raw_state[c][r] = 0

    return matrix, diag


def _prepare_serial_scan(serial_conn) -> list:
    """Flushes buffers and returns the active column MUX map, sending settle config if needed."""
    serial_conn.reset_input_buffer()
    col_mux_map = settings.get("col_mux_map", DEFAULT_COL_MUX_MAP)
    settle_us = min(255, max(0, int(settings.get("mux_settle_us", 100))))
    _send_settle_if_needed(serial_conn, settle_us)
    return col_mux_map


def _collect_calibration_samples(serial_conn, col_mux_map, duration_s, accumulate_ranks=None):
    """
    Repeatedly requests ADC scans for duration_s seconds, accumulating per-square sums/counts.
    If accumulate_ranks is provided (a set of row indices), only those ranks are accumulated.
    Returns (sums, counts) matrices.
    """
    sums = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    counts = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    expected_bytes = BOARD_COLS * BOARD_ROWS * 2
    start_time = time.time()
    while time.time() - start_time < duration_s:
        serial_conn.write(build_packet(CMD_SCAN_ADC))
        data = _read_adc_packet(serial_conn)
        if data is not None and len(data) == expected_bytes:
            vals = struct.unpack(f'<{BOARD_COLS * BOARD_ROWS}H', data)
            for mux_ch in range(BOARD_COLS):
                c_phys = col_mux_map[mux_ch]
                for r_phys in range(BOARD_ROWS):
                    val = vals[mux_ch * BOARD_ROWS + r_phys]
                    c = 7 - r_phys
                    r = c_phys
                    if accumulate_ranks is None or r in accumulate_ranks:
                        sums[c][r] += val
                        counts[c][r] += 1
        else:
            serial_conn.reset_input_buffer()
        time.sleep(0.01)
    return sums, counts


def _clear_baseline_history():
    global baseline_history
    baseline_history.clear()


def calibrate_board(h, serial_conn, duration_s=2.0):
    """
    Reads samples per channel continuously over a specified duration (default 2 seconds),
    averages them, and saves the new values as baselines in the persistent configuration settings.
    """
    if serial_conn is None:
        logger.error("Calibration failed: serial connection not initialized.")
        return False

    col_mux_map = _prepare_serial_scan(serial_conn)
    sums, counts = _collect_calibration_samples(serial_conn, col_mux_map, duration_s)

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
    _clear_baseline_history()

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

    col_mux_map = _prepare_serial_scan(serial_conn)
    sums, counts = _collect_calibration_samples(
        serial_conn, col_mux_map, duration_s, accumulate_ranks={2, 3, 4, 5}
    )

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
    _clear_baseline_history()

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
