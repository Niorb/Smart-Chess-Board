#!/usr/bin/env python3
"""
smart_chess_board.py

Scans a 4x4 matrix of digital Hall effect sensors using two CD74HC4067
16-channel multiplexers on a Raspberry Pi 4. Detects chess piece presence
via magnets. Tracks real piece identities (type + color) using a known
starting position and lift/place move detection. Lights up squares with
WS2812B LEDs.

Piece encoding: standard chess notation characters.
  White: R N B Q K P   (uppercase)
  Black: r n b q k p   (lowercase)
  Empty: '.'

Usage:
  sudo pigpiod          # start the pigpio daemon (once)
  sudo python3 smart_chess_board.py

Requires: sudo pip3 install pigpio rpi-ws281x
"""

import time
import pigpio
from rpi_ws281x import PixelStrip, Color

# =============================================================================
# CONFIGURATION — change these to scale or rewire
# =============================================================================

# Board dimensions (change both to 8 for full-size board)
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
LED_BRIGHTNESS = 50
LED_FREQ_HZ    = 800000
LED_DMA        = 10
LED_INVERT     = False
LED_CHANNEL    = 0

# Timing
MUX_SETTLE_S       = 0.001   # 1ms settle after MUX switch
SCAN_INTERVAL_S    = 0.1     # 100ms between full board scans
DEBOUNCE_THRESHOLD = 3       # Consecutive matching reads to accept change

# =============================================================================
# PIECE DEFINITIONS
# =============================================================================

PIECE_NAMES = {
    'K': "White King",   'Q': "White Queen",  'R': "White Rook",
    'B': "White Bishop", 'N': "White Knight", 'P': "White Pawn",
    'k': "Black King",   'q': "Black Queen",  'r': "Black Rook",
    'b': "Black Bishop", 'n': "Black Knight", 'p': "Black Pawn",
}


def piece_name(piece):
    return PIECE_NAMES.get(piece, "Empty")


def is_white(piece):
    return piece.isupper() and piece != '.'


def is_black(piece):
    return piece.islower() and piece != '.'

# =============================================================================
# STARTING POSITION
# =============================================================================

# Standard chess starting position (8x8).
# Row 0 = White's back rank (rank 1), Row 7 = Black's back rank (rank 8).
#
# Full 8x8:
#   Row 0: R N B Q K B N R   (White back rank)
#   Row 1: P P P P P P P P   (White pawns)
#   Row 2-5: empty
#   Row 6: p p p p p p p p   (Black pawns)
#   Row 7: r n b q k b n r   (Black back rank)
#
# 4x4 prototype (condensed):
#   Row 0: R N B Q   (White back rank, files a-d)
#   Row 1: P P P P   (White pawns)
#   Row 2: p p p p   (Black pawns)
#   Row 3: r n b q   (Black back rank, files a-d)

if BOARD_ROWS == 8 and BOARD_COLS == 8:
    INITIAL_POSITION = [
        ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R'],
        ['P', 'P', 'P', 'P', 'P', 'P', 'P', 'P'],
        ['.', '.', '.', '.', '.', '.', '.', '.'],
        ['.', '.', '.', '.', '.', '.', '.', '.'],
        ['.', '.', '.', '.', '.', '.', '.', '.'],
        ['.', '.', '.', '.', '.', '.', '.', '.'],
        ['p', 'p', 'p', 'p', 'p', 'p', 'p', 'p'],
        ['r', 'n', 'b', 'q', 'k', 'b', 'n', 'r'],
    ]
elif BOARD_ROWS == 4 and BOARD_COLS == 4:
    INITIAL_POSITION = [
        ['R', 'N', 'B', 'Q'],
        ['P', 'P', 'P', 'P'],
        ['p', 'p', 'p', 'p'],
        ['r', 'n', 'b', 'q'],
    ]
else:
    raise ValueError(f"Define an INITIAL_POSITION for {BOARD_ROWS}x{BOARD_COLS}")

# =============================================================================
# MUX CONTROL
# =============================================================================

def set_mux_channel(pi, s0, s1, s2, channel):
    """Set the 3 address pins of a CD74HC4067 to select a channel (0-7)."""
    pi.write(s0, (channel     ) & 1)
    pi.write(s1, (channel >> 1) & 1)
    pi.write(s2, (channel >> 2) & 1)

# =============================================================================
# BOARD SCANNING
# =============================================================================

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

    # Deselect both MUXes to an unused channel after scan
    set_mux_channel(pi, ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, 5)
    set_mux_channel(pi, COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, 5)

# =============================================================================
# DEBOUNCING
# =============================================================================

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
# PIECE TRACKING
# =============================================================================

def process_changes(old_sensor, sensor_state, piece_map, lifted):
    """
    Process sensor changes and update the logical piece map.
    lifted = {"piece": '.', "row": -1, "col": -1}
    """
    # First pass: detect lifts (removals)
    for row in range(BOARD_ROWS):
        for col in range(BOARD_COLS):
            if old_sensor[row][col] and not sensor_state[row][col]:
                piece = piece_map[row][col]
                if piece != '.':
                    if lifted["piece"] != '.':
                        print(f"WARNING: {piece_name(lifted['piece'])} was still "
                              f"in the air from [{lifted['row']},{lifted['col']}] "
                              f"— placing it back.")
                        piece_map[lifted["row"]][lifted["col"]] = lifted["piece"]

                    lifted["piece"] = piece
                    lifted["row"]   = row
                    lifted["col"]   = col
                    piece_map[row][col] = '.'

                    print(f"{piece_name(piece)} lifted from [{row},{col}]")

    # Second pass: detect places (arrivals)
    for row in range(BOARD_ROWS):
        for col in range(BOARD_COLS):
            if not old_sensor[row][col] and sensor_state[row][col]:
                if lifted["piece"] != '.':
                    captured = piece_map[row][col]
                    if captured != '.':
                        print(f"{piece_name(captured)} captured at [{row},{col}]!")

                    piece_map[row][col] = lifted["piece"]

                    if row == lifted["row"] and col == lifted["col"]:
                        print(f"{piece_name(lifted['piece'])} placed back on its square.")
                    else:
                        print(f"{piece_name(lifted['piece'])} moved "
                              f"[{lifted['row']},{lifted['col']}] -> [{row},{col}]")

                    lifted["piece"] = '.'
                    lifted["row"]   = -1
                    lifted["col"]   = -1
                else:
                    print(f"WARNING: Unknown piece placed at [{row},{col}] — marking as '?'")
                    piece_map[row][col] = '?'

# =============================================================================
# SERIAL OUTPUT
# =============================================================================

def print_board_state(piece_map, lifted):
    """Print the piece map as a grid with file/rank labels."""
    print()

    # Column headers (files)
    files = "   " + " ".join(chr(ord('a') + c) for c in range(BOARD_COLS))
    print(files)
    print("   " + "--" * BOARD_COLS)

    # Board rows (ranks, row 0 = rank 1, printed bottom-up)
    for row in range(BOARD_ROWS - 1, -1, -1):
        row_str = " ".join(piece_map[row][c] for c in range(BOARD_COLS))
        print(f" {row + 1}| {row_str}")
    print()

    if lifted["piece"] != '.':
        print(f"In the air: {piece_name(lifted['piece'])} "
              f"(from [{lifted['row']},{lifted['col']}])")
        print()

# =============================================================================
# LED CONTROL
# =============================================================================

def get_led_index(row, col):
    """Convert board [row, col] to serpentine LED strip index."""
    if row % 2 == 0:
        return row * BOARD_COLS + col
    else:
        return row * BOARD_COLS + (BOARD_COLS - 1 - col)


def update_leds(strip, old_sensor, sensor_state):
    """Light blue where a piece was lifted; turn off where a piece landed."""
    need_show = False
    for row in range(BOARD_ROWS):
        for col in range(BOARD_COLS):
            if sensor_state[row][col] != old_sensor[row][col]:
                idx = get_led_index(row, col)
                if not sensor_state[row][col]:
                    # Piece LIFTED → blue
                    strip.setPixelColor(idx, Color(0, 0, 255))
                else:
                    # Piece PLACED → off
                    strip.setPixelColor(idx, Color(0, 0, 0))
                need_show = True

    if need_show:
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

    # Load starting position
    piece_map = [row[:] for row in INITIAL_POSITION]

    # Lifted piece tracking
    lifted = {"piece": '.', "row": -1, "col": -1}

    # Startup banner
    print("========================================")
    print("  Smart Chess Board - 4x4 Prototype")
    print("  (Raspberry Pi 4 + pigpio)")
    print("========================================")
    print()
    print("Pin assignments (BCM):")
    print(f"  Row MUX S0-S2 : GPIO {ROW_MUX_S0}, {ROW_MUX_S1}, {ROW_MUX_S2}")
    print(f"  Col MUX S0-S2 : GPIO {COL_MUX_S0}, {COL_MUX_S1}, {COL_MUX_S2}")
    print(f"  MUX Read      : GPIO {MUX_READ_PIN}")
    print(f"  MUX S3 (both) : tied to GND")
    print(f"  MUX EN (both) : tied to GND")
    print(f"  LED strip     : GPIO {LED_PIN}")
    print()
    print(f"Board size: {BOARD_ROWS}x{BOARD_COLS}")
    print(f"Scan interval: {SCAN_INTERVAL_S * 1000:.0f} ms")
    print(f"Debounce threshold: {DEBOUNCE_THRESHOLD} reads")
    print()

    # Initial scan — accept raw state directly (no debounce)
    scan_board(pi, raw_state)
    for r in range(BOARD_ROWS):
        for c in range(BOARD_COLS):
            sensor_state[r][c] = raw_state[r][c]

    print("Starting position loaded:")
    print_board_state(piece_map, lifted)
    print("Press Ctrl+C to exit.")
    print()

    # Main loop
    try:
        while True:
            # Save old sensor state
            old_sensor = [row[:] for row in sensor_state]

            # Scan and debounce
            scan_board(pi, raw_state)
            changed = apply_debounce(raw_state, sensor_state, stable_count)

            if changed:
                process_changes(old_sensor, sensor_state, piece_map, lifted)
                update_leds(strip, old_sensor, sensor_state)
                print_board_state(piece_map, lifted)

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
