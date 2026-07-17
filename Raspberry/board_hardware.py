"""
board_hardware.py

Shared hardware helpers for the Smart Chess Board (Analog + Pi MUX Version).
Controls the MUX via lgpio on the Pi, but requests the analog value
from the ESP32 over a Serial Request-Response protocol.
"""

import time
import serial
import json
import os
import logging

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
    from playwright_chesscom.chesscom_config import (
        BOARD_ROWS,
        BOARD_COLS,
        ANALOG_THRESHOLD,
        ADC_BASELINE,
        ADC_DEVIATION,
    )
except ImportError:
    BOARD_ROWS = 8
    BOARD_COLS = 8
    ANALOG_THRESHOLD = 2000
    ADC_BASELINE = 1550
    ADC_DEVIATION = 150

# =============================================================================
# PERSISTENT SETTINGS
# =============================================================================

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "board_settings.json")

# Default settings (with swapped terminology: columns are ranks 8..1, rows are files a..h)
settings = {
    "baselines": [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)],
    "threshold_positive": 150,
    "threshold_negative": 150,
    "col_mode": "auto",
    "manual_col": 0,
    "scan_delay": 100,
    "mux_settle_us": 100,
    "debounce_threshold": 2,
    "baseline_window_s": 4,
    "disabled_squares": []
}

last_sent_settle_us = None

def load_settings():
    global settings
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                loaded = json.load(f)
                
                # Check for legacy row terminology keys and migrate them
                if "row_mode" in loaded:
                    loaded["col_mode"] = loaded["row_mode"]
                    del loaded["row_mode"]
                if "manual_row" in loaded:
                    loaded["manual_col"] = loaded["manual_row"]
                    del loaded["manual_row"]

                if "baselines" in loaded and "threshold_positive" in loaded and "threshold_negative" in loaded:
                    if "mux_settle_ms" in loaded and "mux_settle_us" not in loaded:
                        loaded["mux_settle_us"] = min(255, int(loaded["mux_settle_ms"] * 1000))
                    
                    if "disabled_squares" not in loaded:
                        loaded["disabled_squares"] = []
                    
                    settings.update(loaded)
                    logger.info(f"Loaded board settings from {SETTINGS_FILE}")
                else:
                    logger.warning(f"Settings file {SETTINGS_FILE} is missing required fields. Using defaults.")
        except Exception as e:
            logger.error(f"Error loading settings: {e}")

    # Ensure baselines match current BOARD_COLS and BOARD_ROWS dimensions
    if len(settings["baselines"]) != BOARD_COLS:
        settings["baselines"] = [[1550] * BOARD_ROWS for _ in range(BOARD_COLS)]
    else:
        for c in range(BOARD_COLS):
            if len(settings["baselines"][c]) != BOARD_ROWS:
                if len(settings["baselines"][c]) < BOARD_ROWS:
                    settings["baselines"][c] = settings["baselines"][c] + [1550] * (BOARD_ROWS - len(settings["baselines"][c]))
                else:
                    settings["baselines"][c] = settings["baselines"][c][:BOARD_ROWS]

def save_settings():
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)
        logger.info(f"Saved board settings to {SETTINGS_FILE}")
    except Exception as e:
        logger.error(f"Error saving settings: {e}")

# Initial load on module import
load_settings()

# Dynamic baseline history (timestamp, raw_value, detected_magnet) for each square
baseline_history = {}

# =============================================================================
# MUX PIN ASSIGNMENTS (BCM numbering - swapped names)
# =============================================================================

COL_MUX_S0 = 17
COL_MUX_S1 = 27
COL_MUX_S2 = 22
COL_MUX_S3 = 23

ROW_MUX_S0 = 5
ROW_MUX_S1 = 6
ROW_MUX_S2 = 13
ROW_MUX_S3 = 19

# =============================================================================
# TIMING
# =============================================================================

MUX_SETTLE_S = 0.0001  # 100us settling time default for faster scanning

# =============================================================================
# MUX CONTROL
# =============================================================================

def set_mux_channel(h, s0, s1, s2, s3, channel):
    """No-op on the Pi — MUX is now controlled directly by the ESP32 coprocessor."""
    pass

# =============================================================================
# GPIO SETUP
# =============================================================================

def init_mux_pins(h):
    """No-op on the Pi — MUX is now controlled directly by the ESP32 coprocessor."""
    pass


# =============================================================================
# BOARD SCANNING (HYBRID)
# =============================================================================

def get_raw_analog_matrix(h, serial_conn):
    """
    Scans the entire 8x8 matrix of analog sensors using the serial batch scan command.
    """
    matrix = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    if serial_conn is None:
        return matrix

    # Flush any stale serial data
    serial_conn.reset_input_buffer()

    col_mode = settings.get("col_mode", "auto")
    manual_col = settings.get("manual_col", 0)
    settle_us = settings.get("mux_settle_us", 100)

    global last_sent_settle_us
    if last_sent_settle_us != settle_us:
        serial_conn.write(b'S' + bytes([settle_us]))
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
            idx = 0
            for r in reversed(range(BOARD_ROWS)):
                for c in range(BOARD_COLS):
                    val = vals[idx]
                    idx += 1
                    disabled_squares = settings.get("disabled_squares", [])
                    if col_mode == "manual" and c != manual_col:
                        matrix[c][r] = settings["baselines"][c][r]
                    elif [c, r] in disabled_squares or (c, r) in disabled_squares:
                        matrix[c][r] = settings["baselines"][c][r]
                    else:
                        matrix[c][r] = val
    else:
        logger.warning(f"Serial sync error: expected header 0xAA55, got {header.hex() if header else 'nothing'}")
        serial_conn.reset_input_buffer()
        for c in range(BOARD_COLS):
            for r in range(BOARD_ROWS):
                matrix[c][r] = settings["baselines"][c][r]

    return matrix


def scan_board(h, serial_conn, raw_state):
    """
    Scans the board and returns both the raw matrix and a dictionary of diagnostic info.
    Reads values as a single batch from the serial interface.
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
    settle_us = settings.get("mux_settle_us", 100)
    non_mocked_count = (1 if col_mode == "manual" else BOARD_COLS) * BOARD_ROWS

    global last_sent_settle_us
    if last_sent_settle_us != settle_us:
        serial_conn.write(b'S' + bytes([settle_us]))
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
            idx = 0
            for r in reversed(range(BOARD_ROWS)):
                for c in range(BOARD_COLS):
                    val = vals[idx]
                    idx += 1

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

                    # Dynamic baseline moving average update (4 seconds window)
                    now = time.time()
                    detected = (raw_state[c][r] != 0)
                    
                    if (c, r) not in baseline_history:
                        baseline_history[(c, r)] = []
                        
                    baseline_history[(c, r)].append((now, val, detected))
                    
                    # Keep only entries within the last baseline_window_s seconds
                    baseline_window = settings.get("baseline_window_s", 4)
                    baseline_history[(c, r)] = [entry for entry in baseline_history[(c, r)] if now - entry[0] <= baseline_window]
                    any_magnet = any(entry[2] for entry in baseline_history[(c, r)])
                    
                    if not any_magnet and len(baseline_history[(c, r)]) > 0:
                        avg_val = sum(entry[1] for entry in baseline_history[(c, r)]) / len(baseline_history[(c, r)])
                        settings["baselines"][c][r] = int(avg_val)
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


def calibrate_board(h, serial_conn, samples=5):
    """
    Reads multiple samples per channel using the batch scan command, averages them, 
    and saves the new values as baselines in the persistent configuration settings.
    """
    if serial_conn is None:
        logger.error("Calibration failed: serial connection not initialized.")
        return False
        
    sums = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    counts = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    
    # Flush buffers
    serial_conn.reset_input_buffer()
    
    settle_us = settings.get("mux_settle_us", 100)
    global last_sent_settle_us
    if last_sent_settle_us != settle_us:
        serial_conn.write(b'S' + bytes([settle_us]))
        last_sent_settle_us = settle_us

    for s in range(samples):
        serial_conn.write(b'B')
        header = serial_conn.read(2)
        if len(header) == 2 and header[0] == 0xAA and header[1] == 0x55:
            expected_bytes = BOARD_COLS * BOARD_ROWS * 2
            data = serial_conn.read(expected_bytes)
            if len(data) == expected_bytes:
                import struct
                vals = struct.unpack(f'<{BOARD_COLS * BOARD_ROWS}H', data)
                idx = 0
                for r in reversed(range(BOARD_ROWS)):
                    for c in range(BOARD_COLS):
                        val = vals[idx]
                        idx += 1
                        sums[c][r] += val
                        counts[c][r] += 1
        time.sleep(0.02)
        
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
