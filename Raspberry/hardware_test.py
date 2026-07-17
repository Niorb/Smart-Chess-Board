#!/usr/bin/env python3
"""
hardware_test.py

ULTRA-SIMPLIFIED diagnostic tool for the Smart Chess Board.
Goal: Keep Row 0 selected, scan Column MUX channels 0-3, calibrate a per-square
baseline from the first 10 readings, print differences from that baseline, and light
squares whose absolute difference exceeds the configured threshold.
"""

import time

import lgpio
import serial

from board_hardware import (
    COL_MUX_S0,
    COL_MUX_S1,
    COL_MUX_S2,
    COL_MUX_S3,
    MUX_SETTLE_S,
    ROW_MUX_S0,
    ROW_MUX_S1,
    ROW_MUX_S2,
    ROW_MUX_S3,
    init_mux_pins,
    set_mux_channel,
)
from playwright_chesscom.chesscom_config import (
    BAUD_RATE,
    LED_BRIGHTNESS,
    LED_CHANNEL,
    LED_DMA,
    LED_FREQ_HZ,
    LED_INVERT,
    LED_PIN,
    LED_PIN_2,
    NUM_LEDS,
    SERIAL_PORT,
)
from playwright_chesscom.led_helpers import init_strip, get_led_indices, Color

BASELINE_SAMPLES = 10
DIFF_LED_THRESHOLD = 150
SCAN_INTERVAL_S = 0.02
ACTIVE_COLS = [0, 1, 2, 3, 4, 5, 6, 7]
ACTIVE_ROWS = [0, 1, 2, 3, 4, 5, 6, 7]
LED_POSITIVE_COLOR = Color(255, 0, 0)  # Red for positive shift (> 150)
LED_NEGATIVE_COLOR = Color(0, 255, 0)  # Green for negative shift (< -150)
LED_OFF_COLOR = Color(0, 0, 0)


def init_led_strip():
    """Initialize the WS2812B LED strip."""
    strip = init_strip()
    if strip is not None:
        print(f"LED: Initialized {NUM_LEDS} LEDs on GPIO {LED_PIN} and {LED_PIN_2}.")
    return strip


def set_all_leds(strip, color):
    """Update every LED in the strip buffer without showing it yet."""
    if strip is None:
        return

    for led_index in range(NUM_LEDS):
        strip.setPixelColor(led_index, color)


def clear_leds(strip):
    """Turn off every LED on the strip."""
    if strip is None:
        return

    set_all_leds(strip, LED_OFF_COLOR)
    strip.show()


def update_leds_from_differences(strip, differences, previous_frame):
    """Light active squares green for positive diff and red for negative diff."""
    if strip is None:
        return previous_frame

    # Build the whole LED frame in memory, then call show() once only if it changed.
    # This avoids visible off/on flicker and avoids unnecessarily refreshing WS2812 data.
    frame = [LED_OFF_COLOR] * NUM_LEDS

    from board_hardware import settings
    col_mode = settings.get("col_mode", "auto")
    manual_col = settings.get("manual_col", 0)

    for col in ACTIVE_COLS:
        if col_mode == "manual" and col != manual_col:
            continue
        for row_index, diff in enumerate(differences[col]):
            row = ACTIVE_ROWS[row_index]
            if diff is None or abs(diff) <= DIFF_LED_THRESHOLD:
                continue

            color = LED_POSITIVE_COLOR if diff > 0 else LED_NEGATIVE_COLOR
            for led_index in get_led_indices(row, col):
                if 0 <= led_index < NUM_LEDS:
                    frame[led_index] = color

    if frame != previous_frame:
        for led_index, color in enumerate(frame):
            strip.setPixelColor(led_index, color)
        strip.show()

    return frame


def read_active_values(h, ser):
    """Read all configured active columns/rows into a column-specific dictionary using batch read."""
    values = {col: [None] * len(ACTIVE_ROWS) for col in ACTIVE_COLS}
    ser.reset_input_buffer()

    # Request batch scan
    ser.write(b"B")
    
    # Read binary packet: 2 header bytes + 128 data bytes (64 uint16_t values)
    header = ser.read(2)
    if len(header) == 2 and header[0] == 0xAA and header[1] == 0x55:
        expected_bytes = 8 * 8 * 2
        data = ser.read(expected_bytes)
        if len(data) == expected_bytes:
            import struct
            vals = struct.unpack('<64H', data)
            idx = 0
            for r in range(8):
                for c in range(8):
                    val = vals[idx]
                    idx += 1
                    if c in values:
                        if r in ACTIVE_ROWS:
                            row_idx = ACTIVE_ROWS.index(r)
                            values[c][row_idx] = val

    return values


def calibrate_baseline(h, ser):
    """Average the first readings per column/row to create default starting values."""
    sums = {col: [0] * len(ACTIVE_ROWS) for col in ACTIVE_COLS}
    counts = {col: [0] * len(ACTIVE_ROWS) for col in ACTIVE_COLS}

    print(f"Calibrating baseline from first {BASELINE_SAMPLES} readings...")
    print("Keep the board in its default starting state.")

    for sample_num in range(BASELINE_SAMPLES):
        values = read_active_values(h, ser)
        for col in ACTIVE_COLS:
            for row_index, value in enumerate(values[col]):
                if value is not None:
                    sums[col][row_index] += value
                    counts[col][row_index] += 1

        print(f"Baseline sample {sample_num + 1}/{BASELINE_SAMPLES}: {values}")
        time.sleep(0.1)

    baseline = {}
    for col in ACTIVE_COLS:
        baseline[col] = []
        for row_index in range(len(ACTIVE_ROWS)):
            if counts[col][row_index] == 0:
                baseline[col].append(None)
            else:
                baseline[col].append(sums[col][row_index] / counts[col][row_index])

    print(f"Baseline saved: {baseline}")
    return baseline


def build_difference_values(values, baseline):
    """Subtract the calibrated baseline from the latest readings."""
    differences = {}

    for col in ACTIVE_COLS:
        differences[col] = []
        for row_index, value in enumerate(values[col]):
            base_value = baseline[col][row_index]
            if value is None or base_value is None:
                differences[col].append(None)
            else:
                differences[col].append(round(value - base_value, 1))

    return differences


def print_diff_grid(differences):
    """Print the difference grid with aligned columns and rows."""
    header = "        " + "  ".join(f"  R{r}   " for r in ACTIVE_ROWS)
    print(header)
    for col in ACTIVE_COLS:
        values = differences.get(col, [])
        cells = []
        for v in values:
            if v is None:
                cells.append("  None ")
            else:
                marker = "*" if abs(v) > DIFF_LED_THRESHOLD else " "
                cells.append(f"{v:+7.1f}{marker}")
        print(f"  C{col}  [ " + "  ".join(cells) + " ]")
    print()


def main():
    print("--- Hardware Test (8x8 Grid, Baseline Differences) ---")
    print(f"Target columns: {ACTIVE_COLS}, rows: {ACTIVE_ROWS}")
    print(f"LED threshold: abs(diff) > {DIFF_LED_THRESHOLD}")

    strip = None
    try:
        strip = init_led_strip()
    except Exception as e:
        print(f"ERROR: LED init fail: {e}")
        print("Continuing without LED output.")

    # 1. Initialize GPIO
    try:
        h = lgpio.gpiochip_open(0)
        init_mux_pins(h)
        # Start on the first active column.
        set_mux_channel(
            h, COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, COL_MUX_S3, ACTIVE_COLS[0]
        )
        print(f"GPIO: Chip 0 opened. Active columns configured: {ACTIVE_COLS}.")
    except Exception as e:
        print(f"ERROR: GPIO fail: {e}")
        return

    ser = None
    baseline = None
    led_frame = None

    try:
        while True:
            # 2. Maintain Serial Connection
            if ser is None:
                try:
                    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
                    print(f"Serial: Connected to {SERIAL_PORT} at {BAUD_RATE}")
                    ser.reset_input_buffer()
                    if strip is not None:
                        strip.set_serial_conn(ser)
                except Exception as e:
                    print(f"Serial: Waiting for connection... ({e})")
                    time.sleep(1)
                    continue

            # 3. Calibrate once, then print differences from the default baseline.
            try:
                if baseline is None:
                    baseline = calibrate_baseline(h, ser)

                t0 = time.time()
                values = read_active_values(h, ser)
                t1 = time.time()
                differences = build_difference_values(values, baseline)
                t2 = time.time()
                led_frame = update_leds_from_differences(strip, differences, led_frame)
                t3 = time.time()

                print(f"[TIMING] Read: {t1-t0:.4f}s | Diff: {t2-t1:.4f}s | LED: {t3-t2:.4f}s")
                print_diff_grid(differences)
            except Exception as e:
                print(f"Serial: Read error: {e}")
                ser.close()
                ser = None

            time.sleep(SCAN_INTERVAL_S)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        clear_leds(strip)
        if ser:
            ser.close()
        if h:
            lgpio.gpiochip_close(h)


if __name__ == "__main__":
    main()
