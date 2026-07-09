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
  sudo python3 smart_chess_board.py

Requires: sudo pip3 install lgpio rpi-ws281x
"""

import time
import math
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
# CONFIGURATION
# =============================================================================

# WS2812B LED strip
LED_PIN = 10  # GPIO 10 (SPI0 MOSI) — no root needed
NUM_LEDS = 53
LED_BRIGHTNESS = 50
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_INVERT = False
LED_CHANNEL = 0

# Timing
SCAN_INTERVAL_S = 0.1  # 100ms between full board scans
DEBOUNCE_THRESHOLD = 3  # Consecutive matching reads to accept change

# Piece Colors (for setup guide)
PIECE_COLORS = {
    "P": Color(0, 0, 255),      # Blue
    "N": Color(255, 165, 0),    # Orange
    "B": Color(0, 255, 255),    # Cyan
    "R": Color(255, 0, 255),    # Magenta
    "K": Color(255, 255, 255),  # White
    "Q": Color(128, 0, 128),    # Purple
}

PIECE_COLOR_NAMES = {
    "P": "Blue",
    "N": "Orange",
    "B": "Cyan",
    "R": "Magenta",
    "K": "White",
    "Q": "Purple",
}

# =============================================================================
# PIECE DEFINITIONS
# =============================================================================

PIECE_NAMES = {
    "K": "White King",
    "Q": "White Queen",
    "R": "White Rook",
    "B": "White Bishop",
    "N": "White Knight",
    "P": "White Pawn",
    "k": "Black King",
    "q": "Black Queen",
    "r": "Black Rook",
    "b": "Black Bishop",
    "n": "Black Knight",
    "p": "Black Pawn",
}


def piece_name(piece):
    return PIECE_NAMES.get(piece, "Empty")


def is_white(piece):
    return piece.isupper() and piece != "."


def is_black(piece):
    return piece.islower() and piece != "."


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
        ["R", "N", "B", "Q", "K", "B", "N", "R"],
        ["P", "P", "P", "P", "P", "P", "P", "P"],
        [".", ".", ".", ".", ".", ".", ".", "."],
        [".", ".", ".", ".", ".", ".", ".", "."],
        [".", ".", ".", ".", ".", ".", ".", "."],
        [".", ".", ".", ".", ".", ".", ".", "."],
        ["p", "p", "p", "p", "p", "p", "p", "p"],
        ["r", "n", "b", "q", "k", "b", "n", "r"],
    ]
elif BOARD_ROWS == 4 and BOARD_COLS == 4:
    INITIAL_POSITION = [
        ["B", "P", "N", "R"],
        [".", ".", ".", "."],
        [".", ".", ".", "."],
        ["r", "n", "k", "b"],
    ]
else:
    raise ValueError(f"Define an INITIAL_POSITION for {BOARD_ROWS}x{BOARD_COLS}")

# =============================================================================
# PIECE TRACKING
# =============================================================================


def process_changes(old_sensor, sensor_state, piece_map, lifted):
    """
    Process sensor changes and update the logical piece map.
    Returns (row, col) if a piece was moved to a new square, else None.
    """
    moved_to = None

    # First pass: detect lifts (removals)
    for row in range(BOARD_ROWS):
        for col in range(BOARD_COLS):
            if old_sensor[row][col] and not sensor_state[row][col]:
                piece = piece_map[row][col]
                if piece != ".":
                    if lifted["piece"] != ".":
                        # Capture lift: if another piece of opposite color is lifted, clear it
                        if (is_white(lifted["piece"]) and is_black(piece)) or (
                            is_black(lifted["piece"]) and is_white(piece)
                        ):
                            print(f"Capture in progress: {piece_name(piece)} removed.")
                            piece_map[row][col] = "."
                            lifted["capture_square"] = (row, col)
                            continue

                        print(
                            f"WARNING: {piece_name(lifted['piece'])} was still "
                            f"in the air from [{lifted['row']},{lifted['col']}] "
                            f"— placing it back."
                        )
                        piece_map[lifted["row"]][lifted["col"]] = lifted["piece"]

                    lifted["piece"] = piece
                    lifted["row"] = row
                    lifted["col"] = col
                    piece_map[row][col] = "."

                    print(f"{piece_name(piece)} lifted from [{row},{col}]")

    # Second pass: detect places (arrivals)
    for row in range(BOARD_ROWS):
        for col in range(BOARD_COLS):
            if not old_sensor[row][col] and sensor_state[row][col]:
                if lifted["piece"] != ".":
                    captured = piece_map[row][col]
                    if captured != ".":
                        print(f"{piece_name(captured)} captured at [{row},{col}]!")

                    piece_map[row][col] = lifted["piece"]

                    if row == lifted["row"] and col == lifted["col"]:
                        print(
                            f"{piece_name(lifted['piece'])} placed back on its square."
                        )
                    else:
                        print(
                            f"{piece_name(lifted['piece'])} moved "
                            f"[{lifted['row']},{lifted['col']}] -> [{row},{col}]"
                        )
                        moved_to = (row, col)

                    lifted["piece"] = "."
                    lifted["row"] = -1
                    lifted["col"] = -1
                    lifted["capture_square"] = None
                else:
                    print(
                        f"WARNING: Unknown piece placed at [{row},{col}] — marking as '?'"
                    )
                    piece_map[row][col] = "?"

    return moved_to


# =============================================================================
# SERIAL OUTPUT
# =============================================================================


def print_board_state(piece_map, lifted):
    """Print the piece map as a grid with file/rank labels."""
    print()

    # Column headers (files)
    files = "   " + " ".join(chr(ord("a") + c) for c in range(BOARD_COLS))
    print(files)
    print("   " + "--" * BOARD_COLS)

    # Board rows (ranks, row 0 = rank 1, printed bottom-up)
    for row in range(BOARD_ROWS - 1, -1, -1):
        row_str = " ".join(piece_map[row][c] for c in range(BOARD_COLS))
        print(f" {row + 1}| {row_str}")
    print()

    if lifted["piece"] != ".":
        print(
            f"In the air: {piece_name(lifted['piece'])} "
            f"(from [{lifted['row']},{lifted['col']}])"
        )
        print()


# =============================================================================
# CHESS LOGIC
# =============================================================================


def get_valid_moves(piece, row, col, piece_map):
    """
    Calculate valid moves for a given piece on the board.
    Returns a list of tuples (target_row, target_col, is_capture).
    """
    moves = []
    piece_type = piece.upper()
    white_turn = piece.isupper()

    def is_enemy(r, c):
        target = piece_map[r][c]
        if target == ".":
            return False
        return target.islower() if white_turn else target.isupper()

    def is_friend(r, c):
        target = piece_map[r][c]
        if target == ".":
            return False
        return target.isupper() if white_turn else target.islower()

    def in_bounds(r, c):
        return 0 <= r < BOARD_ROWS and 0 <= c < BOARD_COLS

    # --- PAWNS ---
    if piece_type == "P":
        direction = 1 if white_turn else -1
        # Forward move
        nr, nc = row + direction, col
        if in_bounds(nr, nc) and piece_map[nr][nc] == ".":
            moves.append((nr, nc, False))
        # Captures
        for dc in [-1, 1]:
            nr, nc = row + direction, col + dc
            if in_bounds(nr, nc) and is_enemy(nr, nc):
                moves.append((nr, nc, True))

    # --- KNIGHTS ---
    elif piece_type == "N":
        offsets = [
            (-2, -1),
            (-2, 1),
            (-1, -2),
            (-1, 2),
            (1, -2),
            (1, 2),
            (2, -1),
            (2, 1),
        ]
        for dr, dc in offsets:
            nr, nc = row + dr, col + dc
            if in_bounds(nr, nc) and not is_friend(nr, nc):
                moves.append((nr, nc, piece_map[nr][nc] != "."))

    # --- KINGS ---
    elif piece_type == "K":
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                nr, nc = row + dr, col + dc
                if in_bounds(nr, nc) and not is_friend(nr, nc):
                    moves.append((nr, nc, piece_map[nr][nc] != "."))

    # --- ROOKS, BISHOPS, QUEENS (Sliding) ---
    else:
        directions = []
        if piece_type in ["R", "Q"]:
            directions += [(0, 1), (0, -1), (1, 0), (-1, 0)]
        if piece_type in ["B", "Q"]:
            directions += [(1, 1), (1, -1), (-1, 1), (-1, -1)]

        for dr, dc in directions:
            nr, nc = row + dr, col + dc
            while in_bounds(nr, nc):
                if piece_map[nr][nc] == ".":
                    moves.append((nr, nc, False))
                elif is_enemy(nr, nc):
                    moves.append((nr, nc, True))
                    break
                else:  # friend
                    break
                nr += dr
                nc += dc

    return moves


# =============================================================================
# LED CONTROL
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


def flash_square(strip, row, col, color):
    """Temporarily flash a square's LEDs."""
    indices = get_led_indices(row, col)
    # Turn on
    for idx in indices:
        strip.setPixelColor(idx, color)
    strip.show()
    time.sleep(0.2)
    # Turn off
    for idx in indices:
        strip.setPixelColor(idx, Color(0, 0, 0))
    strip.show()


def update_leds(strip, piece_map, lifted):
    """
    Clear all LEDs, then highlight origin (blue) and valid moves (green/red)
    if a piece is currently lifted.
    """
    # 1. Clear all LEDs
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, Color(0, 0, 0))

    # 2. If piece lifted, show its moves
    if lifted["piece"] != ".":
        # Highlight origin square blue
        origin_indices = get_led_indices(lifted["row"], lifted["col"])
        for idx in origin_indices:
            strip.setPixelColor(idx, Color(0, 0, 255))

        if lifted.get("capture_square"):
            # Capture in progress: only highlight the target square (Red, flickering at 2Hz)
            cap_r, cap_c = lifted["capture_square"]
            cap_indices = get_led_indices(cap_r, cap_c)
            # 2Hz = 500ms period. 250ms ON, 250ms OFF.
            if int(time.time() * 4) % 2 == 0:
                color = Color(255, 0, 0)
            else:
                color = Color(0, 0, 0)
            for idx in cap_indices:
                strip.setPixelColor(idx, color)
        else:
            # Highlight valid moves
            valid_moves = get_valid_moves(
                lifted["piece"], lifted["row"], lifted["col"], piece_map
            )
            for r, c, is_capture in valid_moves:
                indices = get_led_indices(r, c)
                color = Color(255, 0, 0) if is_capture else Color(0, 255, 0)
                for idx in indices:
                    strip.setPixelColor(idx, color)

    strip.show()


def check_board_setup(h, strip, initial_position):
    """
    Visual guide for board setup.
    Blocks until board matches initial_position (piece presence only).
    """
    raw_state = [[False] * BOARD_COLS for _ in range(BOARD_ROWS)]
    sensor_state = [[False] * BOARD_COLS for _ in range(BOARD_ROWS)]
    stable_count = [[0] * BOARD_COLS for _ in range(BOARD_ROWS)]
    last_printed_state = None

    print("\n" + "=" * 40)
    print("      BOARD SETUP MODE")
    print("=" * 40)
    print("Color Legend:")
    for piece, color_name in PIECE_COLOR_NAMES.items():
        print(f"  {piece} : {color_name:8}")
    print("-" * 40)
    print("  - Black pieces pulse.")
    print("  - White pieces constant.")
    print("=" * 40 + "\n")

    try:
        while True:
            scan_board(h, raw_state)
            changed = apply_debounce(raw_state, sensor_state, stable_count, DEBOUNCE_THRESHOLD)

            setup_ok = True
            # Pulse: 0.3 to 1.0 brightness factor
            pulse_factor = 0.65 + 0.35 * math.sin(time.time() * 5)

            # Print status grid if state changed
            if changed or last_printed_state is None:
                print("\rStatus Grid (Target vs Actual):")
                print("   a  b  c  d")
                for r in range(BOARD_ROWS - 1, -1, -1):
                    row_str = f"{r+1} "
                    for c in range(BOARD_COLS):
                        target = initial_position[r][c]
                        present = sensor_state[r][c]
                        required = (target != ".")

                        if required and present:
                            row_str += " OK"
                        elif required and not present:
                            row_str += " !!" # Missing
                        elif not required and present:
                            row_str += " ??" # Extra
                        else:
                            row_str += " --" # Correctly empty
                    print(row_str)
                print("-" * 20)
                last_printed_state = [row[:] for row in sensor_state]

            for r in range(BOARD_ROWS):
                for c in range(BOARD_COLS):
                    target = initial_position[r][c]
                    present = sensor_state[r][c]
                    required = (target != ".")

                    if present != required:
                        setup_ok = False

                    indices = get_led_indices(r, c)
                    if required:
                        color = PIECE_COLORS.get(target.upper(), Color(100, 100, 100))
                        if is_black(target):
                            r_val = int(((color >> 16) & 0xFF) * pulse_factor)
                            g_val = int(((color >> 8) & 0xFF) * pulse_factor)
                            b_val = int((color & 0xFF) * pulse_factor)
                            color = Color(r_val, g_val, b_val)
                    else:
                        if present:
                            color = Color(255, 0, 0)  # Red for "remove piece"
                            setup_ok = False
                        else:
                            color = Color(0, 0, 0)

                    for idx in indices:
                        strip.setPixelColor(idx, color)

            strip.show()
            if setup_ok:
                print("\nBoard verified!")
                # Brief green confirmation flash
                for i in range(NUM_LEDS):
                    strip.setPixelColor(i, Color(0, 255, 0))
                strip.show()
                time.sleep(1.0)
                for i in range(NUM_LEDS):
                    strip.setPixelColor(i, Color(0, 0, 0))
                strip.show()
                break
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
        raise


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

    # Load starting position
    piece_map = [row[:] for row in INITIAL_POSITION]

    # Lifted piece tracking
    lifted = {"piece": ".", "row": -1, "col": -1, "capture_square": None}

    # Startup banner
    print("========================================")
    print("  Smart Chess Board - 4x4 Prototype")
    print("  (Raspberry Pi 4 + lgpio)")
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
    scan_board(h, raw_state)
    for r in range(BOARD_ROWS):
        for c in range(BOARD_COLS):
            sensor_state[r][c] = raw_state[r][c]

    # Visual setup guide (4x4 prototype only)
    if BOARD_ROWS == 4 and BOARD_COLS == 4:
        check_board_setup(h, strip, piece_map)
        # Sync sensor_state after setup
        scan_board(h, raw_state)
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
            scan_board(h, raw_state)
            changed = apply_debounce(
                raw_state, sensor_state, stable_count, DEBOUNCE_THRESHOLD
            )

            if changed:
                moved_to = process_changes(old_sensor, sensor_state, piece_map, lifted)
                update_leds(strip, piece_map, lifted)
                if moved_to:
                    flash_square(
                        strip, moved_to[0], moved_to[1], Color(255, 165, 0)
                    )  # Orange
                print_board_state(piece_map, lifted)
            elif lifted.get("capture_square"):
                # Drive flickering when a capture is in progress
                update_leds(strip, piece_map, lifted)

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
