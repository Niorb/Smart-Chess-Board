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
    "manual_row": 0
}

def load_settings():
    global settings
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                loaded = json.load(f)
                if "baselines" in loaded and "threshold_positive" in loaded and "threshold_negative" in loaded:
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

MUX_SETTLE_S = 0.002  # 2ms settling time for faster scanning

# =============================================================================
# MUX CONTROL
# =============================================================================

def set_mux_channel(h, s0, s1, s2, s3, channel):
    """Set the 4 address pins of a CD74HC4067 to select a channel (0-15)."""
    if channel < 0 or channel > 15:
        channel = 15
    lgpio.gpio_write(h, s0, (channel) & 1)
    lgpio.gpio_write(h, s1, (channel >> 1) & 1)
    lgpio.gpio_write(h, s2, (channel >> 2) & 1)
    lgpio.gpio_write(h, s3, (channel >> 3) & 1)

# =============================================================================
# GPIO SETUP
# =============================================================================

def init_mux_pins(h):
    """Configure MUX select pins as outputs."""
    for pin in [ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, ROW_MUX_S3,
                COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, COL_MUX_S3]:
        lgpio.gpio_claim_output(h, pin)


# =============================================================================
# BOARD SCANNING (HYBRID)
# =============================================================================

def get_raw_analog_matrix(h, serial_conn):
    """
    Scans the entire 4x8 matrix of analog sensors (mocking columns >= 4).
    """
    matrix = [[0] * BOARD_COLS for _ in range(BOARD_ROWS)]
    if serial_conn is None or h is None:
        return matrix

    # Flush any stale serial data
    serial_conn.reset_input_buffer()

    row_mode = settings.get("row_mode", "auto")
    manual_row = settings.get("manual_row", 0)

    for row in range(BOARD_ROWS):
        if row_mode == "manual":
            target_row = manual_row if row == manual_row else 15
            set_mux_channel(h, ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, ROW_MUX_S3, target_row)
        else:
            set_mux_channel(h, ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, ROW_MUX_S3, row)
        for col in range(BOARD_COLS):
            if col >= 4:
                # Last 4 columns are not wired yet, set to baseline value
                matrix[row][col] = settings["baselines"][row][col]
                continue

            # Swap hardware column index: board column col (0-3) corresponds to hardware column 3-col
            hw_col = 3 - col
            set_mux_channel(h, COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, COL_MUX_S3, hw_col)
            time.sleep(MUX_SETTLE_S)

            # Request analog value
            serial_conn.write(b'R')
            
            # Read response
            line = serial_conn.readline().decode('utf-8', errors='ignore').strip()
            if line:
                try:
                    matrix[row][col] = int(line)
                except ValueError:
                    pass

    return matrix


def scan_board(h, serial_conn, raw_state):
    """
    Scans the board and returns both the raw matrix and a dictionary of diagnostic info.
    Mocking columns >= 4.
    """
    matrix = [[0] * BOARD_COLS for _ in range(BOARD_ROWS)]
    diag = {
        "status": "OK",
        "last_raw_line": "",
        "timeouts": 0,
        "errors": 0
    }
    if serial_conn is None or h is None:
        diag["status"] = "NO_HARDWARE"
        return matrix, diag

    # Flush any stale serial data
    serial_conn.reset_input_buffer()

    row_mode = settings.get("row_mode", "auto")
    manual_row = settings.get("manual_row", 0)

    for r in range(BOARD_ROWS):
        if row_mode == "manual":
            target_row = manual_row if r == manual_row else 15
            set_mux_channel(h, ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, ROW_MUX_S3, target_row)
        else:
            set_mux_channel(h, ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, ROW_MUX_S3, r)
        for c in range(BOARD_COLS):
            if c >= 4:
                # Last 4 columns are not wired yet, set to baseline and idle
                matrix[r][c] = settings["baselines"][r][c]
                raw_state[r][c] = 0
                continue

            # Swap hardware column index: board column c (0-3) corresponds to hardware column 3-c
            hw_col = 3 - c
            set_mux_channel(h, COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, COL_MUX_S3, hw_col)
            time.sleep(MUX_SETTLE_S)

            serial_conn.write(b'R')
            line = serial_conn.readline().decode('utf-8', errors='ignore').strip()
            
            if not line:
                diag["timeouts"] += 1
            else:
                diag["last_raw_line"] = line
                try:
                    val = int(line)
                    matrix[r][c] = val
                except ValueError:
                    diag["errors"] += 1
                    
            diff = matrix[r][c] - settings["baselines"][r][c]
            if diff > settings["threshold_positive"]:
                raw_state[r][c] = 1   # Positive shift (grows > baseline + threshold)
            elif diff < -settings["threshold_negative"]:
                raw_state[r][c] = -1  # Negative shift (drops < baseline - threshold)
            else:
                raw_state[r][c] = 0   # Idle

    non_mocked_count = BOARD_ROWS * 4
    if diag["timeouts"] == non_mocked_count:
        diag["status"] = "TIMEOUT"
    elif diag["errors"] > 0:
        diag["status"] = "PARSE_ERROR"

    return matrix, diag


def calibrate_board(h, serial_conn, samples=5):
    """
    Reads multiple samples per channel, averages them, and saves the new values
    as baselines in the persistent configuration settings.
    Mocking columns >= 4.
    """
    if serial_conn is None or h is None:
        logger.error("Calibration failed: serial or GPIO chip not initialized.")
        return False
        
    sums = [[0] * BOARD_COLS for _ in range(BOARD_ROWS)]
    counts = [[0] * BOARD_COLS for _ in range(BOARD_ROWS)]
    
    # Flush buffers
    serial_conn.reset_input_buffer()
    
    for s in range(samples):
        for r in range(BOARD_ROWS):
            set_mux_channel(h, ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, ROW_MUX_S3, r)
            for c in range(BOARD_COLS):
                if c >= 4:
                    sums[r][c] += 1550
                    counts[r][c] += 1
                    continue
                # Swap hardware column index: board column c (0-3) corresponds to hardware column 3-c
                hw_col = 3 - c
                set_mux_channel(h, COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, COL_MUX_S3, hw_col)
                time.sleep(MUX_SETTLE_S)
                
                serial_conn.write(b'R')
                line = serial_conn.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    try:
                        val = int(line)
                        sums[r][c] += val
                        counts[r][c] += 1
                    except ValueError:
                        pass
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
                # Fallback if no scans succeeded for this channel
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
