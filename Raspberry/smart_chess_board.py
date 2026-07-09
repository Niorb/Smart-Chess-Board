#!/usr/bin/env python3
"""
smart_chess_board.py

Scans a 4x4 matrix of analog Hall effect sensors via an ESP32 connected 
over USB Serial. Detects chess piece presence via magnets. Tracks real 
piece identities and lights up squares with WS2812B LEDs.

Usage:
  python3 smart_chess_board.py

Requires: pip3 install pyserial rpi-ws281x lgpio
"""

import time
import math
import serial
from rpi_ws281x import PixelStrip, Color

from board_hardware import (
    BOARD_ROWS,
    BOARD_COLS,
    scan_board,
    apply_debounce,
    init_mux_pins,
)
from playwright_chesscom.chesscom_config import (
    SERIAL_PORT,
    BAUD_RATE,
    ANALOG_THRESHOLD,
    LED_PIN,
    NUM_LEDS,
    LED_BRIGHTNESS,
    LED_FREQ_HZ,
    LED_DMA,
    LED_INVERT,
    LED_CHANNEL,
)

# Timing
SCAN_INTERVAL_S = 2.0  # 0.5Hz (2 seconds between full board scans)
DEBOUNCE_THRESHOLD = 1  # With 2s interval, debounce is less critical

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

PIECE_NAMES = {
    "K": "White King", "Q": "White Queen", "R": "White Rook", "B": "White Bishop", "N": "White Knight", "P": "White Pawn",
    "k": "Black King", "q": "Black Queen", "r": "Black Rook", "b": "Black Bishop", "n": "Black Knight", "p": "Black Pawn",
}

def piece_name(piece): return PIECE_NAMES.get(piece, "Empty")
def is_white(piece): return piece.isupper() and piece != "."
def is_black(piece): return piece.islower() and piece != "."

# =============================================================================
# STARTING POSITION (4x4 prototype)
# =============================================================================

INITIAL_POSITION = [
    ["B", "P", "N", "R"],
    [".", ".", ".", "."],
    [".", ".", ".", "."],
    ["r", "n", "k", "b"],
]

# =============================================================================
# PIECE TRACKING
# =============================================================================

def process_changes(old_sensor, sensor_state, piece_map, lifted):
    moved_to = None
    for row in range(BOARD_ROWS):
        for col in range(BOARD_COLS):
            if old_sensor[row][col] and not sensor_state[row][col]:
                piece = piece_map[row][col]
                if piece != ".":
                    if lifted["piece"] != ".":
                        if (is_white(lifted["piece"]) and is_black(piece)) or (is_black(lifted["piece"]) and is_white(piece)):
                            print(f"Capture in progress: {piece_name(piece)} removed.")
                            piece_map[row][col] = "."
                            lifted["capture_square"] = (row, col)
                            continue
                        piece_map[lifted["row"]][lifted["col"]] = lifted["piece"]
                    lifted["piece"] = piece
                    lifted["row"], lifted["col"] = row, col
                    piece_map[row][col] = "."
                    print(f"{piece_name(piece)} lifted from [{row},{col}]")

    for row in range(BOARD_ROWS):
        for col in range(BOARD_COLS):
            if not old_sensor[row][col] and sensor_state[row][col]:
                if lifted["piece"] != ".":
                    captured = piece_map[row][col]
                    if captured != ".": print(f"{piece_name(captured)} captured at [{row},{col}]!")
                    piece_map[row][col] = lifted["piece"]
                    if row != lifted["row"] or col != lifted["col"]:
                        print(f"{piece_name(lifted['piece'])} moved [{lifted['row']},{lifted['col']}] -> [{row},{col}]")
                        moved_to = (row, col)
                    else:
                        print(f"{piece_name(lifted['piece'])} placed back.")
                    lifted["piece"], lifted["row"], lifted["col"], lifted["capture_square"] = ".", -1, -1, None
                else:
                    print(f"WARNING: Unknown piece at [{row},{col}]")
                    piece_map[row][col] = "?"
    return moved_to

def print_board_state(piece_map, lifted):
    print("\n   " + " ".join(chr(ord("a") + c) for c in range(BOARD_COLS)))
    print("   " + "--" * BOARD_COLS)
    for row in range(BOARD_ROWS - 1, -1, -1):
        print(f" {row + 1}| " + " ".join(piece_map[row][c] for c in range(BOARD_COLS)))
    if lifted["piece"] != ".":
        print(f"\nIn the air: {piece_name(lifted['piece'])} from [{lifted['row']},{lifted['col']}]")

# =============================================================================
# CHESS LOGIC / LEDS
# =============================================================================

def get_valid_moves(piece, row, col, piece_map):
    moves = []
    piece_type, white_turn = piece.upper(), piece.isupper()
    def is_enemy(r, c): return piece_map[r][c] != "." and (piece_map[r][c].islower() if white_turn else piece_map[r][c].isupper())
    def is_friend(r, c): return piece_map[r][c] != "." and (piece_map[r][c].isupper() if white_turn else piece_map[r][c].islower())
    def in_bounds(r, c): return 0 <= r < BOARD_ROWS and 0 <= c < BOARD_COLS

    if piece_type == "P":
        direction = 1 if white_turn else -1
        if in_bounds(row+direction, col) and piece_map[row+direction][col] == ".": moves.append((row+direction, col, False))
        for dc in [-1, 1]:
            if in_bounds(row+direction, col+dc) and is_enemy(row+direction, col+dc): moves.append((row+direction, col+dc, True))
    elif piece_type == "N":
        for dr, dc in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
            if in_bounds(row+dr, col+dc) and not is_friend(row+dr, col+dc): moves.append((row+dr, col+dc, piece_map[row+dr][col+dc] != "."))
    elif piece_type == "K":
        for dr in [-1,0,1]:
            for dc in [-1,0,1]:
                if dr==0 and dc==0: continue
                if in_bounds(row+dr, col+dc) and not is_friend(row+dr, col+dc): moves.append((row+dr, col+dc, piece_map[row+dr][col+dc] != "."))
    else:
        dirs = []
        if piece_type in ["R", "Q"]: dirs += [(0, 1), (0, -1), (1, 0), (-1, 0)]
        if piece_type in ["B", "Q"]: dirs += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
        for dr, dc in dirs:
            nr, nc = row+dr, col+dc
            while in_bounds(nr, nc):
                if piece_map[nr][nc] == ".": moves.append((nr, nc, False))
                elif is_enemy(nr, nc): moves.append((nr, nc, True)); break
                else: break
                nr, nc = nr+dr, nc+dc
    return moves

def get_led_indices(row, col):
    base = row * 18
    if row % 2 == 0:
        col_offsets = {0: [0, 1], 1: [3, 4], 2: [5, 6], 3: [7, 8], 4: [9, 10], 5: [11, 12], 6: [14, 15], 7: [16, 17]}
    else:
        col_offsets = {7: [0, 1], 6: [2, 3], 5: [5, 6], 4: [7, 8], 3: [9, 10], 2: [11, 12], 1: [13, 14], 0: [16, 17]}
    return [base + o for o in col_offsets[col]]

def update_leds(strip, piece_map, lifted):
    for i in range(NUM_LEDS): strip.setPixelColor(i, Color(0, 0, 0))
    if lifted["piece"] != ".":
        for idx in get_led_indices(lifted["row"], lifted["col"]): strip.setPixelColor(idx, Color(0, 0, 255))
        if lifted.get("capture_square"):
            cap_r, cap_c = lifted["capture_square"]
            color = Color(255, 0, 0) if int(time.time() * 4) % 2 == 0 else Color(0, 0, 0)
            for idx in get_led_indices(cap_r, cap_c): strip.setPixelColor(idx, color)
        else:
            for r, c, is_cap in get_valid_moves(lifted["piece"], lifted["row"], lifted["col"], piece_map):
                color = Color(255, 0, 0) if is_cap else Color(0, 255, 0)
                for idx in get_led_indices(r, c): strip.setPixelColor(idx, color)
    strip.show()

def check_board_setup(h, ser, strip, initial_position):
    raw_state = [[False] * BOARD_COLS for _ in range(BOARD_ROWS)]
    sensor_state = [[False] * BOARD_COLS for _ in range(BOARD_ROWS)]
    stable_count = [[0] * BOARD_COLS for _ in range(BOARD_ROWS)]
    print("\nBOARD SETUP MODE - Place pieces according to target grid.")
    try:
        while True:
            scan_board(h, ser, raw_state)
            apply_debounce(raw_state, sensor_state, stable_count, DEBOUNCE_THRESHOLD)
            setup_ok, pulse = True, 0.65 + 0.35 * math.sin(time.time() * 5)
            for r in range(BOARD_ROWS):
                for c in range(BOARD_COLS):
                    target, present = initial_position[r][c], sensor_state[r][c]
                    required = (target != ".")
                    if present != required: setup_ok = False
                    color = Color(0,0,0)
                    if required:
                        color = PIECE_COLORS.get(target.upper(), Color(100,100,100))
                        if is_black(target):
                            color = Color(int(((color>>16)&0xFF)*pulse), int(((color>>8)&0xFF)*pulse), int((color&0xFF)*pulse))
                    elif present:
                        color = Color(255, 0, 0); setup_ok = False
                    for idx in get_led_indices(r, c): strip.setPixelColor(idx, color)
            strip.show()
            if setup_ok:
                print("Board verified!"); time.sleep(1.0); break
            time.sleep(0.05)
    except KeyboardInterrupt: raise

def main():
    # Open GPIO chip for MUX control
    try:
        h = lgpio.gpiochip_open(0)
        init_mux_pins(h)
        print("GPIO: Chip 0 opened and MUX pins initialized.")
    except Exception as e:
        print(f"ERROR: Could not open GPIO chip: {e}")
        return

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
        print(f"Connected to ESP32 on {SERIAL_PORT}")
    except Exception as e:
        print(f"ERROR: Could not open serial port {SERIAL_PORT}: {e}")
        lgpio.gpiochip_close(h)
        return

    strip = PixelStrip(NUM_LEDS, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    strip.begin()

    sensor_state = [[False] * BOARD_COLS for _ in range(BOARD_ROWS)]
    raw_state = [[False] * BOARD_COLS for _ in range(BOARD_ROWS)]
    stable_count = [[0] * BOARD_COLS for _ in range(BOARD_ROWS)]
    piece_map = [row[:] for row in INITIAL_POSITION]
    lifted = {"piece": ".", "row": -1, "col": -1, "capture_square": None}

    print("Smart Chess Board - Analog ESP32 Version")
    check_board_setup(h, ser, strip, piece_map)

    try:
        while True:
            old_sensor = [row[:] for row in sensor_state]
            scan_board(h, ser, raw_state)
            if apply_debounce(raw_state, sensor_state, stable_count, DEBOUNCE_THRESHOLD):
                moved_to = process_changes(old_sensor, sensor_state, piece_map, lifted)
                update_leds(strip, piece_map, lifted)
                print_board_state(piece_map, lifted)
            elif lifted.get("capture_square"): update_leds(strip, piece_map, lifted)
            time.sleep(SCAN_INTERVAL_S)
    finally:
        for i in range(NUM_LEDS): strip.setPixelColor(i, Color(0, 0, 0))
        strip.show()
        ser.close()
        lgpio.gpiochip_close(h)

if __name__ == "__main__":
    main()
