#!/usr/bin/env python3
"""
hardware_test.py

Standalone test script for the Smart Chess Board hardware on Raspberry Pi 4.
Runs two tests in sequence:
  1. LED strip chase — lights each LED one by one, then flashes all.
  2. Live sensor monitor — scans the Hall sensor matrix and mirrors
     sensor state onto the LED strip in real time.

Usage:
  sudo python3 hardware_test.py

Requires: sudo pip3 install lgpio rpi-ws281x
"""

import time
import lgpio
from rpi_ws281x import PixelStrip, Color

from board_hardware import (
    BOARD_ROWS,
    BOARD_COLS,
    ROW_MUX_S0,
    ROW_MUX_S1,
    ROW_MUX_S2,
    COL_MUX_S0,
    COL_MUX_S1,
    COL_MUX_S2,
    MUX_READ_PIN,
    scan_board,
    apply_debounce,
    init_mux_pins,
)

# =============================================================================
# CONFIGURATION — hardware_test uses 53 LEDs
# =============================================================================

NUM_LEDS = 53
LED_PIN = 10  # GPIO 10 (SPI0 MOSI) — no root needed
LED_BRIGHTNESS = 50  # 0-255
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_INVERT = False
LED_CHANNEL = 0

# Timing
SCAN_INTERVAL_S = 0.03  # Between full board scans
DEBOUNCE_THRESHOLD = 3  # Consecutive matching reads to accept change

# =============================================================================
# LED HELPERS
# =============================================================================


def get_led_indices(row, col):
    """
    Convert board [row, col] to serpentine LED strip indices.
    Row 0 (Even, L-R): Skip 1, Col0(3), Col1(2), Skip 1, Col2(2), Col3(3), Skip 2.
    Row 1 (Odd, R-L): Skip 2, Col3(3), Col2(2), Skip 1, Col1(2), Col0(3).
    Total 13 LEDs per row after initial skip. Total 53 LEDs.
    """
    base = 1 + row * 13

    if row % 2 == 0:
        # Even row (L-R)
        col_offsets = {0: [0, 1, 2], 1: [3, 4], 2: [6, 7], 3: [8, 9, 10]}
        offsets = col_offsets[col]
    else:
        # Odd row (R-L)
        col_offsets = {3: [2, 3, 4], 2: [5, 6], 1: [8, 9], 0: [10, 11, 12]}
        offsets = col_offsets[col]

    return [base + o for o in offsets]


# =============================================================================
# TEST 1: LED STRIP CHASE
# =============================================================================


def test_led_chase(strip):
    print("========================================")
    print("  TEST 1: LED Strip Chase")
    print("========================================")
    print()
    print("Each square's 2 LEDs will light GREEN one by one.")
    print("Watch the strip and verify the order.")
    print()

    for row in range(BOARD_ROWS):
        for col in range(BOARD_COLS):
            # Clear all
            for j in range(NUM_LEDS):
                strip.setPixelColor(j, Color(0, 0, 0))
            # Light both LEDs for this square
            indices = get_led_indices(row, col)
            for idx in indices:
                strip.setPixelColor(idx, Color(0, 255, 0))  # Green
            strip.show()

            print(f"  Square (row {row}, col {col})  LEDs {indices[0]},{indices[1]}")
            time.sleep(0.1)

    # Clear
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()
    time.sleep(0.3)

    # Flash all white 3 times
    print()
    print("Flashing all LEDs WHITE 3 times...")
    for _ in range(3):
        for i in range(NUM_LEDS):
            strip.setPixelColor(i, Color(255, 255, 255))
        strip.show()
        time.sleep(0.3)

        for i in range(NUM_LEDS):
            strip.setPixelColor(i, Color(0, 0, 0))
        strip.show()
        time.sleep(0.3)

    print("LED chase test DONE.")
    print()


# =============================================================================
# TEST 2: LIVE SENSOR -> LED MONITOR
# =============================================================================


def print_sensor_grid(sensor_state):
    print()
    header = "   " + " ".join(str(c) for c in range(BOARD_COLS))
    print(header)
    print("   " + "--" * BOARD_COLS)
    for r in range(BOARD_ROWS):
        row_str = " ".join(
            "1" if sensor_state[r][c] else "0" for c in range(BOARD_COLS)
        )
        print(f" {r}| {row_str}")
    print()


def update_leds_from_sensors(strip, sensor_state):
    for r in range(BOARD_ROWS):
        for c in range(BOARD_COLS):
            indices = get_led_indices(r, c)
            color = Color(0, 255, 0) if sensor_state[r][c] else Color(0, 0, 0)
            for idx in indices:
                strip.setPixelColor(idx, color)
    strip.show()


# =============================================================================
# MAIN
# =============================================================================


def main():
    # Open GPIO chip
    try:
        h = lgpio.gpiochip_open(0)
    except lgpio.error as e:
        print(f"ERROR: Could not open GPIO chip: {e}")
        return

    # Configure MUX and read pins
    init_mux_pins(h)

    # LED strip setup
    strip = PixelStrip(
        NUM_LEDS, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL
    )
    strip.begin()

    # Initialize state
    sensor_state = [[False] * BOARD_COLS for _ in range(BOARD_ROWS)]
    raw_state = [[False] * BOARD_COLS for _ in range(BOARD_ROWS)]
    stable_count = [[0] * BOARD_COLS for _ in range(BOARD_ROWS)]

    print()
    print("========================================")
    print("  Smart Chess Board — Hardware Test")
    print("  (Raspberry Pi 4 + lgpio)")
    print("========================================")
    print()
    print("Pin assignments (BCM):")
    print(f"  Row MUX S0-S2 : GPIO {ROW_MUX_S0}, {ROW_MUX_S1}, {ROW_MUX_S2}")
    print(f"  Col MUX S0-S2 : GPIO {COL_MUX_S0}, {COL_MUX_S1}, {COL_MUX_S2}")
    print(f"  MUX Read      : GPIO {MUX_READ_PIN}")
    print(f"  LED strip     : GPIO {LED_PIN}")
    print()

    # ----- TEST 1: LED Chase -----
    test_led_chase(strip)

    # ----- TEST 2: Sensor Monitor -----
    print("========================================")
    print("  TEST 2: Live Sensor -> LED Monitor")
    print("========================================")
    print()
    print("Place/remove magnets on the board.")
    print("LED lights GREEN where a magnet is detected.")
    print("Grid: 1 = magnet, 0 = empty.")
    print("Press Ctrl+C to exit.")
    print()

    # Initial scan
    scan_board(h, raw_state)
    for r in range(BOARD_ROWS):
        for c in range(BOARD_COLS):
            sensor_state[r][c] = raw_state[r][c]
    update_leds_from_sensors(strip, sensor_state)
    print_sensor_grid(sensor_state)

    # Main loop
    try:
        while True:
            scan_board(h, raw_state)
            if apply_debounce(
                raw_state, sensor_state, stable_count, DEBOUNCE_THRESHOLD
            ):
                update_leds_from_sensors(strip, sensor_state)
                print_sensor_grid(sensor_state)
            time.sleep(SCAN_INTERVAL_S)
    finally:
        # Turn off all LEDs
        for i in range(NUM_LEDS):
            strip.setPixelColor(i, Color(0, 0, 0))
        strip.show()
        lgpio.gpiochip_close(h)
        print("GPIO chip closed.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
