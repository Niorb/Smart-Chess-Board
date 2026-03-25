#!/usr/bin/env python3
"""
hardware_test.py

Standalone test script for the Smart Chess Board hardware on Raspberry Pi 4.
Runs two tests in sequence:
  1. LED strip chase — lights each LED one by one, then flashes all.
  2. Live sensor monitor — scans the Hall sensor matrix and mirrors
     sensor state onto the LED strip in real time.

Usage:
  sudo pigpiod          # start the pigpio daemon (once)
  sudo python3 hardware_test.py

Requires: sudo pip3 install pigpio rpi-ws281x
"""

import time
import pigpio
from rpi_ws281x import PixelStrip, Color

# =============================================================================
# CONFIGURATION — must match smart_chess_board.py
# =============================================================================

BOARD_ROWS = 4
BOARD_COLS = 4

# Row MUX select pins (BCM numbering)
ROW_MUX_S0 = 17
ROW_MUX_S1 = 27
ROW_MUX_S2 = 22

# Column MUX select pins (BCM numbering)
COL_MUX_S0 = 5
COL_MUX_S1 = 6
COL_MUX_S2 = 13

# Read pin
MUX_READ_PIN = 24

# WS2812B LED strip
LED_PIN        = 18    # Must be GPIO 18 (PWM0) for rpi_ws281x
NUM_LEDS       = BOARD_ROWS * BOARD_COLS
LED_BRIGHTNESS = 50    # 0-255
LED_FREQ_HZ    = 800000
LED_DMA        = 10
LED_INVERT     = False
LED_CHANNEL    = 0

# Timing
MUX_SETTLE_S       = 0.001   # Settle after MUX switch (tune as needed)
SCAN_INTERVAL_S    = 0.03     # Between full board scans
DEBOUNCE_THRESHOLD = 3     # Consecutive matching reads to accept change

# =============================================================================
# SHARED HELPERS
# =============================================================================

def set_mux_channel(pi, s0, s1, s2, channel):
    """Set the 3 address pins of a CD74HC4067 to select a channel (0-7)."""
    pi.write(s0, (channel     ) & 1)
    pi.write(s1, (channel >> 1) & 1)
    pi.write(s2, (channel >> 2) & 1)


def get_led_index(row, col):
    """Convert board [row, col] to serpentine LED strip index."""
    if row % 2 == 0:
        return row * BOARD_COLS + col
    else:
        return row * BOARD_COLS + (BOARD_COLS - 1 - col)


def scan_board(pi, raw_state):
    """Scan every cell in the matrix and store results in raw_state[][]."""
    for row in range(BOARD_ROWS):
        set_mux_channel(pi, ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, row)
        pi.read(MUX_READ_PIN)  # Dummy read for settling
        time.sleep(MUX_SETTLE_S)

        for col in range(BOARD_COLS):
            set_mux_channel(pi, COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, col)
            time.sleep(MUX_SETTLE_S)
            # LOW (0) = magnet detected = piece present (active-low sensor)
            raw_state[row][col] = (pi.read(MUX_READ_PIN) == 0)


def apply_debounce(raw_state, sensor_state, stable_count):
    """Apply debouncing. Returns True if any square's state changed."""
    changed = False
    for r in range(BOARD_ROWS):
        for c in range(BOARD_COLS):
            if raw_state[r][c] == sensor_state[r][c]:
                stable_count[r][c] = 0
            else:
                stable_count[r][c] += 1
                if stable_count[r][c] >= DEBOUNCE_THRESHOLD:
                    sensor_state[r][c] = raw_state[r][c]
                    stable_count[r][c] = 0
                    changed = True
    return changed

# =============================================================================
# TEST 1: LED STRIP CHASE
# =============================================================================

def test_led_chase(strip):
    print("========================================")
    print("  TEST 1: LED Strip Chase")
    print("========================================")
    print()
    print("Each LED will light GREEN one by one.")
    print("Watch the strip and verify the order.")
    print()

    for i in range(NUM_LEDS):
        # Clear all, light one
        for j in range(NUM_LEDS):
            strip.setPixelColor(j, Color(0, 0, 0))
        strip.setPixelColor(i, Color(0, 255, 0))  # Green
        strip.show()

        # Reverse-map LED index to row, col
        row = i // BOARD_COLS
        if row % 2 == 0:
            col = i % BOARD_COLS
        else:
            col = (BOARD_COLS - 1) - (i % BOARD_COLS)

        print(f"  LED {i} ON  (row {row}, col {col})")
        time.sleep(0.2)

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
# TEST 2: LIVE SENSOR → LED MONITOR
# =============================================================================

def print_sensor_grid(sensor_state):
    print()
    header = "   " + " ".join(str(c) for c in range(BOARD_COLS))
    print(header)
    print("   " + "--" * BOARD_COLS)
    for r in range(BOARD_ROWS):
        row_str = " ".join("1" if sensor_state[r][c] else "0"
                           for c in range(BOARD_COLS))
        print(f" {r}| {row_str}")
    print()


def update_leds_from_sensors(strip, sensor_state):
    for r in range(BOARD_ROWS):
        for c in range(BOARD_COLS):
            idx = get_led_index(r, c)
            if sensor_state[r][c]:
                strip.setPixelColor(idx, Color(0, 255, 0))  # Green = magnet
            else:
                strip.setPixelColor(idx, Color(0, 0, 0))    # Off = no magnet
    strip.show()

# =============================================================================
# MAIN
# =============================================================================

def main():
    # Connect to pigpio daemon
    pi = pigpio.pi()
    if not pi.connected:
        print("ERROR: Could not connect to pigpiod. Run: sudo pigpiod")
        return

    # Configure MUX select pins as outputs
    for pin in [ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2,
                COL_MUX_S0, COL_MUX_S1, COL_MUX_S2]:
        pi.set_mode(pin, pigpio.OUTPUT)

    # Configure read pin as input
    pi.set_mode(MUX_READ_PIN, pigpio.INPUT)

    # LED strip setup
    strip = PixelStrip(NUM_LEDS, LED_PIN, LED_FREQ_HZ, LED_DMA,
                       LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    strip.begin()

    # Initialize state
    sensor_state = [[False] * BOARD_COLS for _ in range(BOARD_ROWS)]
    raw_state    = [[False] * BOARD_COLS for _ in range(BOARD_ROWS)]
    stable_count = [[0]     * BOARD_COLS for _ in range(BOARD_ROWS)]

    print()
    print("========================================")
    print("  Smart Chess Board — Hardware Test")
    print("  (Raspberry Pi 4 + pigpio)")
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
    scan_board(pi, raw_state)
    for r in range(BOARD_ROWS):
        for c in range(BOARD_COLS):
            sensor_state[r][c] = raw_state[r][c]
    update_leds_from_sensors(strip, sensor_state)
    print_sensor_grid(sensor_state)

    # Main loop
    try:
        while True:
            scan_board(pi, raw_state)
            if apply_debounce(raw_state, sensor_state, stable_count):
                update_leds_from_sensors(strip, sensor_state)
                print_sensor_grid(sensor_state)
            time.sleep(SCAN_INTERVAL_S)
    finally:
        # Turn off all LEDs
        for i in range(NUM_LEDS):
            strip.setPixelColor(i, Color(0, 0, 0))
        strip.show()
        pi.stop()
        print("pigpio connection closed.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
