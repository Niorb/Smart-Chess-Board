#!/usr/bin/env python3
"""
smart_chess_board.py

Scans an 8x8 matrix of analog Hall effect sensors via an ESP32 connected 
over USB Serial. Detects chess piece presence via magnets. Tracks real 
piece identities and lights up squares with WS2812B LEDs.

Usage:
  python3 smart_chess_board.py

Requires: pip3 install pyserial rpi-ws281x lgpio
"""

import time
import math
import serial

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
from playwright_chesscom.led_helpers import init_strip, get_led_indices, Color

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
# STARTING POSITION (8x8 Standard chess board setup)
# =============================================================================

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

# =============================================================================
# PIECE TRACKING
# =============================================================================

def process_changes(old_sensor, sensor_state, piece_map, lifted):
    moved_to = None
    for col in range(BOARD_COLS):
        for row in range(BOARD_ROWS):
            if old_sensor[col][row] and not sensor_state[col][row]:
                piece = piece_map[col][row]
                if piece != ".":
                    if lifted["piece"] != ".":
                        if (is_white(lifted["piece"]) and is_black(piece)) or (is_black(lifted["piece"]) and is_white(piece)):
                            print(f"Capture in progress: {piece_name(piece)} removed.")
                            piece_map[col][row] = "."
                            lifted["capture_square"] = (col, row)
                            continue
                        piece_map[lifted["col"]][lifted["row"]] = lifted["piece"]
                    lifted["piece"] = piece
                    lifted["col"], lifted["row"] = col, row
                    piece_map[col][row] = "."
                    print(f"{piece_name(piece)} lifted from [{col},{row}]")

    for col in range(BOARD_COLS):
        for row in range(BOARD_ROWS):
            if not old_sensor[col][row] and sensor_state[col][row]:
                if lifted["piece"] != ".":
                    captured = piece_map[col][row]
                    if captured != ".": print(f"{piece_name(captured)} captured at [{col},{row}]!")
                    piece_map[col][row] = lifted["piece"]
                    if col != lifted["col"] or row != lifted["row"]:
                        print(f"{piece_name(lifted['piece'])} moved [{lifted['col']},{lifted['row']}] -> [{col},{row}]")
                        moved_to = (col, row)
                    else:
                        print(f"{piece_name(lifted['piece'])} placed back.")
                    lifted["piece"], lifted["col"], lifted["row"], lifted["capture_square"] = ".", -1, -1, None
                else:
                    print(f"WARNING: Unknown piece at [{col},{row}]")
                    piece_map[col][row] = "?"
    return moved_to

def print_board_state(piece_map, lifted):
    print("\n   " + " ".join(chr(ord("a") + r) for r in range(BOARD_ROWS)))
    print("   " + "--" * BOARD_ROWS)
    for col in range(BOARD_COLS - 1, -1, -1):
        print(f" {col + 1}| " + " ".join(piece_map[col][r] for r in range(BOARD_ROWS)))
    if lifted["piece"] != ".":
        print(f"\nIn the air: {piece_name(lifted['piece'])} from [{lifted['col']},{lifted['row']}]")

# =============================================================================
# CHESS LOGIC / LEDS
# =============================================================================

def get_valid_moves(piece, col, row, piece_map):
    moves = []
    piece_type, white_turn = piece.upper(), piece.isupper()
    def is_enemy(c, r): return piece_map[c][r] != "." and (piece_map[c][r].islower() if white_turn else piece_map[c][r].isupper())
    def is_friend(c, r): return piece_map[c][r] != "." and (piece_map[c][r].isupper() if white_turn else piece_map[c][r].islower())
    def in_bounds(c, r): return 0 <= c < BOARD_COLS and 0 <= r < BOARD_ROWS

    if piece_type == "P":
        direction = 1 if white_turn else -1
        if in_bounds(col+direction, row) and piece_map[col+direction][row] == ".": moves.append((col+direction, row, False))
        for dr in [-1, 1]:
            if in_bounds(col+direction, row+dr) and is_enemy(col+direction, row+dr): moves.append((col+direction, row+dr, True))
    elif piece_type == "N":
        for dc, dr in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
            if in_bounds(col+dc, row+dr) and not is_friend(col+dc, row+dr): moves.append((col+dc, row+dr, piece_map[col+dc][row+dr] != "."))
    elif piece_type == "K":
        for dc in [-1,0,1]:
            for dr in [-1,0,1]:
                if dc==0 and dr==0: continue
                if in_bounds(col+dc, row+dr) and not is_friend(col+dc, row+dr): moves.append((col+dc, row+dr, piece_map[col+dc][row+dr] != "."))
    else:
        dirs = []
        if piece_type in ["R", "Q"]: dirs += [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if piece_type in ["B", "Q"]: dirs += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
        for dc, dr in dirs:
            nc, nr = col+dc, row+dr
            while in_bounds(nc, nr):
                if piece_map[nc][nr] == ".": moves.append((nc, nr, False))
                elif is_enemy(nc, nr): moves.append((nc, nr, True)); break
                else: break
                nc, nr = nc+dc, nr+dr
    return moves

# get_led_indices imported from led_helpers

def update_leds(strip, piece_map, lifted):
    from board_hardware import settings
    col_mode = settings.get("col_mode", "auto")
    manual_col = settings.get("manual_col", 0)

    for i in range(NUM_LEDS): strip.setPixelColor(i, Color(0, 0, 0))
    if lifted["piece"] != ".":
        if col_mode != "manual" or lifted["col"] == manual_col:
            for idx in get_led_indices(lifted["col"], lifted["row"]): strip.setPixelColor(idx, Color(0, 0, 255))
        if lifted.get("capture_square"):
            cap_c, cap_r = lifted["capture_square"]
            if col_mode != "manual" or cap_c == manual_col:
                color = Color(255, 0, 0) if int(time.time() * 4) % 2 == 0 else Color(0, 0, 0)
                for idx in get_led_indices(cap_c, cap_r): strip.setPixelColor(idx, color)
        else:
            for c, r, is_cap in get_valid_moves(lifted["piece"], lifted["col"], lifted["row"], piece_map):
                if col_mode == "manual" and c != manual_col:
                    continue
                color = Color(255, 0, 0) if is_cap else Color(0, 255, 0)
                for idx in get_led_indices(c, r): strip.setPixelColor(idx, color)
    strip.show()

def check_board_setup(h, ser, strip, initial_position):
    from board_hardware import settings
    raw_state = [[False] * BOARD_ROWS for _ in range(BOARD_COLS)]
    sensor_state = [[False] * BOARD_ROWS for _ in range(BOARD_COLS)]
    stable_count = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    print("\nBOARD SETUP MODE - Place pieces according to target grid.")
    try:
        while True:
            col_mode = settings.get("col_mode", "auto")
            manual_col = settings.get("manual_col", 0)
            scan_board(h, ser, raw_state)
            apply_debounce(raw_state, sensor_state, stable_count, DEBOUNCE_THRESHOLD)
            setup_ok, pulse = True, 0.65 + 0.35 * math.sin(time.time() * 5)
            for c in range(BOARD_COLS):
                if col_mode == "manual" and c != manual_col:
                    for r in range(BOARD_ROWS):
                        for idx in get_led_indices(c, r): strip.setPixelColor(idx, Color(0, 0, 0))
                    continue
                for r in range(BOARD_ROWS):
                    target, present = initial_position[c][r], sensor_state[c][r]
                    required = (target != ".")
                    if present != required: setup_ok = False
                    color = Color(0,0,0)
                    if required:
                        color = PIECE_COLORS.get(target.upper(), Color(100,100,100))
                        if is_black(target):
                            color = Color(int(((color>>16)&0xFF)*pulse), int(((color>>8)&0xFF)*pulse), int((color&0xFF)*pulse))
                    elif present:
                        color = Color(255, 0, 0); setup_ok = False
                    for idx in get_led_indices(c, r): strip.setPixelColor(idx, color)
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
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1.0)
        print(f"Connected to ESP32 on {SERIAL_PORT}")
    except Exception as e:
        print(f"ERROR: Could not open serial port {SERIAL_PORT}: {e}")
        lgpio.gpiochip_close(h)
        return

    strip = init_strip()
    if strip is not None:
        strip.set_serial_conn(ser)

    sensor_state = [[False] * BOARD_ROWS for _ in range(BOARD_COLS)]
    raw_state = [[False] * BOARD_ROWS for _ in range(BOARD_COLS)]
    stable_count = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    piece_map = [row[:] for row in INITIAL_POSITION]
    lifted = {"piece": ".", "col": -1, "row": -1, "capture_square": None}

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
