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
from rpi_ws281x import Color, PixelStrip

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
    NUM_LEDS,
    SERIAL_PORT,
)

BASELINE_SAMPLES = 10
DIFF_LED_THRESHOLD = 150
SCAN_INTERVAL_S = 0.02
ACTIVE_ROWS = [0, 1, 2, 3]
ACTIVE_COLS = [0, 1, 2, 3, 4, 5, 6, 7]
LED_POSITIVE_COLOR = Color(255, 0, 0)  # Red for positive shift (> 150)
LED_NEGATIVE_COLOR = Color(0, 255, 0)  # Green for negative shift (< -150)
LED_OFF_COLOR = Color(0, 0, 0)


def get_led_indices(row, col):
    """
    Convert board [row, col] to LED strip indices.
    4 rows and 8 columns, 18 LEDs per row.
    Columns 0 and 5 have 3 LEDs, others have 2. The 3rd LED is kept off.
    """
    base = row * 18

    if row % 2 == 0:
        col_offsets = {
            0: [0, 1],
            1: [3, 4],
            2: [5, 6],
            3: [7, 8],
            4: [9, 10],
            5: [11, 12],
            6: [14, 15],
            7: [16, 17]
        }
    else:
        col_offsets = {
            7: [0, 1],
            6: [2, 3],
            5: [5, 6],
            4: [7, 8],
            3: [9, 10],
            2: [11, 12],
            1: [13, 14],
            0: [16, 17]
        }

    return [base + offset for offset in col_offsets[col]]


def init_led_strip():
    """Initialize the WS2812B LED strip."""
    strip = PixelStrip(
        NUM_LEDS,
        LED_PIN,
        LED_FREQ_HZ,
        LED_DMA,
        LED_INVERT,
        LED_BRIGHTNESS,
        LED_CHANNEL,
    )
    strip.begin()
    clear_leds(strip)
    print(f"LED: Initialized {NUM_LEDS} LEDs on GPIO {LED_PIN}.")
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

    for row in ACTIVE_ROWS:
        for col_index, diff in enumerate(differences[row]):
            col = ACTIVE_COLS[col_index]
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


def read_sensor(h, ser, row, col):
    """Read one analog value for a row/column MUX selection."""
    set_mux_channel(h, ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, ROW_MUX_S3, row)
    
    # Swap hardware column index: board column col (0-3) corresponds to hardware column 3-col
    hw_col = (3 - col) if col < 4 else col
    set_mux_channel(h, COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, COL_MUX_S3, hw_col)
    time.sleep(MUX_SETTLE_S)

    ser.write(b"R")
    line = ser.readline().decode("utf-8", errors="ignore").strip()
    try:
        return int(line)
    except ValueError:
        return None


def read_active_values(h, ser):
    """Read all configured active rows/columns into a row-specific dictionary."""
    values = {}
    ser.reset_input_buffer()

    for row in ACTIVE_ROWS:
        values[row] = []
        for col in ACTIVE_COLS:
            values[row].append(read_sensor(h, ser, row, col))

    return values


def calibrate_baseline(h, ser):
    """Average the first readings per row/column to create default starting values."""
    sums = {row: [0] * len(ACTIVE_COLS) for row in ACTIVE_ROWS}
    counts = {row: [0] * len(ACTIVE_COLS) for row in ACTIVE_ROWS}

    print(f"Calibrating baseline from first {BASELINE_SAMPLES} readings...")
    print("Keep the board in its default starting state.")

    for sample_num in range(BASELINE_SAMPLES):
        values = read_active_values(h, ser)
        for row in ACTIVE_ROWS:
            for col_index, value in enumerate(values[row]):
                if value is not None:
                    sums[row][col_index] += value
                    counts[row][col_index] += 1

        print(f"Baseline sample {sample_num + 1}/{BASELINE_SAMPLES}: {values}")
        time.sleep(0.1)

    baseline = {}
    for row in ACTIVE_ROWS:
        baseline[row] = []
        for col_index in range(len(ACTIVE_COLS)):
            if counts[row][col_index] == 0:
                baseline[row].append(None)
            else:
                baseline[row].append(sums[row][col_index] / counts[row][col_index])

    print(f"Baseline saved: {baseline}")
    return baseline


def build_difference_values(values, baseline):
    """Subtract the calibrated baseline from the latest readings."""
    differences = {}

    for row in ACTIVE_ROWS:
        differences[row] = []
        for col_index, value in enumerate(values[row]):
            base_value = baseline[row][col_index]
            if value is None or base_value is None:
                differences[row].append(None)
            else:
                differences[row].append(round(value - base_value, 1))

    return differences


def print_diff_grid(differences):
    """Print the 4x4 difference grid with aligned columns."""
    header = "        " + "  ".join(f"  C{c}   " for c in ACTIVE_COLS)
    print(header)
    for row in ACTIVE_ROWS:
        values = differences.get(row, [])
        cells = []
        for v in values:
            if v is None:
                cells.append("  None ")
            else:
                marker = "*" if abs(v) > DIFF_LED_THRESHOLD else " "
                cells.append(f"{v:+7.1f}{marker}")
        print(f"  R{row}  [ " + "  ".join(cells) + " ]")
    print()


def main():
    print("--- Hardware Test (4x4 Prototype, Baseline Differences) ---")
    print(f"Target rows: {ACTIVE_ROWS}, columns: {ACTIVE_COLS}")
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
        # Start on the first active row. The scan loop sets row/column per reading.
        set_mux_channel(
            h, ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, ROW_MUX_S3, ACTIVE_ROWS[0]
        )
        print(f"GPIO: Chip 0 opened. Active rows configured: {ACTIVE_ROWS}.")
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
                except Exception as e:
                    print(f"Serial: Waiting for connection... ({e})")
                    time.sleep(1)
                    continue

            # 3. Calibrate once, then print differences from the default baseline.
            try:
                if baseline is None:
                    baseline = calibrate_baseline(h, ser)

                values = read_active_values(h, ser)
                differences = build_difference_values(values, baseline)

                led_frame = update_leds_from_differences(strip, differences, led_frame)

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
