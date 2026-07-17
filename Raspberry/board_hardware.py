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
    BOARD_ROWS = 4
    BOARD_COLS = 4
    ANALOG_THRESHOLD = 2000
    ADC_BASELINE = 1550
    ADC_DEVIATION = 150

# =============================================================================
# PERSISTENT SETTINGS
# =============================================================================

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "board_settings.json")

# Default settings
settings = {
    "baselines": [[1550] * BOARD_COLS for _ in range(BOARD_ROWS)],
    "threshold_positive": 150,
    "threshold_negative": 150,
    "row_mode": "auto",
    "manual_row": 0,
    "scan_delay": 100,
    "mux_settle_us": 100,
    "debounce_threshold": 2,
    "baseline_window_s": 4
}

last_sent_settle_us = None

def load_settings():
    global settings
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                loaded = json.load(f)
                if "baselines" in loaded and "threshold_positive" in loaded and "threshold_negative" in loaded:
                    if "mux_settle_ms" in loaded and "mux_settle_us" not in loaded:
                        loaded["mux_settle_us"] = min(255, int(loaded["mux_settle_ms"] * 1000))
                    settings.update(loaded)
                    logger.info(f"Loaded board settings from {SETTINGS_FILE}")
                else:
                    logger.warning(f"Settings file {SETTINGS_FILE} is missing required fields. Using defaults.")
        except Exception as e:
            logger.error(f"Error loading settings: {e}")

    # Ensure baselines match current BOARD_ROWS and BOARD_COLS dimensions
    if len(settings["baselines"]) != BOARD_ROWS:
        settings["baselines"] = [[1550] * BOARD_COLS for _ in range(BOARD_ROWS)]
    else:
        for r in range(BOARD_ROWS):
            if len(settings["baselines"][r]) != BOARD_COLS:
                if len(settings["baselines"][r]) < BOARD_COLS:
                    settings["baselines"][r] = settings["baselines"][r] + [1550] * (BOARD_COLS - len(settings["baselines"][r]))
                else:
                    settings["baselines"][r] = settings["baselines"][r][:BOARD_COLS]

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
# MUX PIN ASSIGNMENTS (BCM numbering)
# =============================================================================

ROW_MUX_S0 = 17
ROW_MUX_S1 = 27
ROW_MUX_S2 = 22
ROW_MUX_S3 = 23  # Added S3 for full 16-channel support

COL_MUX_S0 = 5
COL_MUX_S1 = 6
COL_MUX_S2 = 13
COL_MUX_S3 = 19  # Added S3 for full 16-channel support

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
    Scans the entire 4x8 matrix of analog sensors using the serial batch scan command.
    """
    matrix = [[0] * BOARD_COLS for _ in range(BOARD_ROWS)]
    if serial_conn is None:
        return matrix

    # Flush any stale serial data
    serial_conn.reset_input_buffer()

    row_mode = settings.get("row_mode", "auto")
    manual_row = settings.get("manual_row", 0)
    settle_us = settings.get("mux_settle_us", 100)

    global last_sent_settle_us
    if last_sent_settle_us != settle_us:
        serial_conn.write(b'S' + bytes([settle_us]))
        last_sent_settle_us = settle_us

    serial_conn.write(b'B')

    # Read binary packet: 2 header bytes + data bytes
    header = serial_conn.read(2)
    if len(header) == 2 and header[0] == 0xAA and header[1] == 0x55:
        expected_bytes = BOARD_ROWS * BOARD_COLS * 2
        data = serial_conn.read(expected_bytes)
        if len(data) == expected_bytes:
            import struct
            vals = struct.unpack(f'<{BOARD_ROWS * BOARD_COLS}H', data)
            idx = 0
            for r in range(BOARD_ROWS):
                for c in range(BOARD_COLS):
                    val = vals[idx]
                    idx += 1
                    if row_mode == "manual" and r != manual_row:
                        matrix[r][c] = settings["baselines"][r][c]
                    else:
                        matrix[r][c] = val
    else:
        logger.warning(f"Serial sync error: expected header 0xAA55, got {header.hex() if header else 'nothing'}")
        serial_conn.reset_input_buffer()
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                matrix[r][c] = settings["baselines"][r][c]

    return matrix


def scan_board(h, serial_conn, raw_state):
    """
    Scans the board and returns both the raw matrix and a dictionary of diagnostic info.
    Reads values as a single batch from the serial interface.
    """
    matrix = [[0] * BOARD_COLS for _ in range(BOARD_ROWS)]
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

    row_mode = settings.get("row_mode", "auto")
    manual_row = settings.get("manual_row", 0)
    settle_us = settings.get("mux_settle_us", 100)
    non_mocked_count = (1 if row_mode == "manual" else BOARD_ROWS) * BOARD_COLS

    global last_sent_settle_us
    if last_sent_settle_us != settle_us:
        serial_conn.write(b'S' + bytes([settle_us]))
        last_sent_settle_us = settle_us

    serial_conn.write(b'B')

    # Read binary packet: 2 header bytes + data bytes
    header = serial_conn.read(2)
    if len(header) == 2 and header[0] == 0xAA and header[1] == 0x55:
        expected_bytes = BOARD_ROWS * BOARD_COLS * 2
        data = serial_conn.read(expected_bytes)
        if len(data) == expected_bytes:
            import struct
            vals = struct.unpack(f'<{BOARD_ROWS * BOARD_COLS}H', data)
            diag["last_raw_line"] = f"BINARY:{len(vals)} vals"
            idx = 0
            for r in range(BOARD_ROWS):
                for c in range(BOARD_COLS):
                    val = vals[idx]
                    idx += 1

                    if row_mode == "manual" and r != manual_row:
                        matrix[r][c] = settings["baselines"][r][c]
                        raw_state[r][c] = 0
                        continue

                    matrix[r][c] = val
                    diff = val - settings["baselines"][r][c]
                    if diff > settings["threshold_positive"]:
                        raw_state[r][c] = 1
                    elif diff < -settings["threshold_negative"]:
                        raw_state[r][c] = -1
                    else:
                        raw_state[r][c] = 0

                    # Dynamic baseline moving average update (4 seconds window)
                    now = time.time()
                    detected = (raw_state[r][c] != 0)
                    
                    if (r, c) not in baseline_history:
                        baseline_history[(r, c)] = []
                        
                    baseline_history[(r, c)].append((now, val, detected))
                    
                    # Keep only entries within the last baseline_window_s seconds
                    baseline_window = settings.get("baseline_window_s", 4)
                    baseline_history[(r, c)] = [entry for entry in baseline_history[(r, c)] if now - entry[0] <= baseline_window]
                    any_magnet = any(entry[2] for entry in baseline_history[(r, c)])
                    
                    if not any_magnet and len(baseline_history[(r, c)]) > 0:
                        avg_val = sum(entry[1] for entry in baseline_history[(r, c)]) / len(baseline_history[(r, c)])
                        settings["baselines"][r][c] = int(avg_val)
        else:
            diag["errors"] = non_mocked_count
            diag["status"] = "TIMEOUT"
            serial_conn.reset_input_buffer()
            for r in range(BOARD_ROWS):
                for c in range(BOARD_COLS):
                    matrix[r][c] = settings["baselines"][r][c]
                    raw_state[r][c] = 0
    else:
        diag["errors"] = non_mocked_count
        diag["status"] = "PARSE_ERROR"
        serial_conn.reset_input_buffer()
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                matrix[r][c] = settings["baselines"][r][c]
                raw_state[r][c] = 0

    return matrix, diag


def calibrate_board(h, serial_conn, samples=5):
    """
    Reads multiple samples per channel using the batch scan command, averages them, 
    and saves the new values as baselines in the persistent configuration settings.
    """
    if serial_conn is None:
        logger.error("Calibration failed: serial connection not initialized.")
        return False
        
    sums = [[0] * BOARD_COLS for _ in range(BOARD_ROWS)]
    counts = [[0] * BOARD_COLS for _ in range(BOARD_ROWS)]
    
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
            expected_bytes = BOARD_ROWS * BOARD_COLS * 2
            data = serial_conn.read(expected_bytes)
            if len(data) == expected_bytes:
                import struct
                vals = struct.unpack(f'<{BOARD_ROWS * BOARD_COLS}H', data)
                idx = 0
                for r in range(BOARD_ROWS):
                    for c in range(BOARD_COLS):
                        val = vals[idx]
                        idx += 1
                        sums[r][c] += val
                        counts[r][c] += 1
        time.sleep(0.02)
        
    # Update baselines
    for r in range(BOARD_ROWS):
        for c in range(BOARD_COLS):
            if counts[r][c] > 0:
                avg_val = int(sums[r][c] / counts[r][c])
                if avg_val > 0:
                    settings["baselines"][r][c] = avg_val
                else:
                    settings["baselines"][r][c] = 1550
            else:
                settings["baselines"][r][c] = 1550
                    
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
    for r in range(BOARD_ROWS):
        for c in range(BOARD_COLS):
            if raw_state[r][c] == sensor_state[r][c]:
                stable_count[r][c] = 0
            else:
                stable_count[r][c] += 1
                if stable_count[r][c] >= threshold:
                    sensor_state[r][c] = raw_state[r][c]
                    stable_count[r][c] = 0
                    changed = True
    return changed
