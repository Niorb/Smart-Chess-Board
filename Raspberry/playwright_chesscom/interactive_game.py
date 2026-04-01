#!/usr/bin/env python3
"""
interactive_game.py

Interactive chess session on chess.com via Playwright.
Walks through browser launch → login check → game start, then runs a
turn-by-turn loop: prompt for moves as White, wait for opponent as Black.

Usage:
  python3 interactive_game.py                        # headless, default time control
  python3 interactive_game.py --visible              # visible browser
  python3 interactive_game.py --time "10 min"        # override time control
"""

import re
import sys
import time
import threading

from chesscom_config import (
    LOCATORS,
    CHESS_COM_PLAY_URL,
    TIME_CONTROL,
    BOARD_ROWS,
    BOARD_COLS,
    NUM_LEDS,
    LED_PIN,
    LED_BRIGHTNESS,
    LED_FREQ_HZ,
    LED_DMA,
    LED_INVERT,
    LED_CHANNEL,
    COLOR_CONNECTING,
    COLOR_CONNECTED,
    COLOR_SEARCHING,
    COLOR_FOUND_WHITE,
    COLOR_FOUND_BLACK,
    COLOR_ERROR,
    IDLE_PULSE_MAX_FRAC,
    IDLE_PULSE_STEP_S,
    IDLE_PULSE_STEPS,
    CONNECT_PULSE_STEP_S,
    SEARCH_CHASE_DELAY_S,
    FLASH_ON_S,
    FLASH_OFF_S,
    FLASH_COUNT_FOUND,
    FLASH_COUNT_ERROR,
    FLASH_COUNT_CONNECT,
)
from chesscom_browser import (
    launch,
    close,
    is_logged_in,
    detect_my_color,
    read_board,
    print_board,
    read_clocks,
    make_move,
)

# Try to import LED hardware — degrades gracefully on non-Pi machines
try:
    from rpi_ws281x import PixelStrip, Color

    HAS_LEDS = True
except ImportError:
    HAS_LEDS = False


# =============================================================================
# LED HELPERS
# =============================================================================


def init_strip():
    """Initialise and return the LED strip, or None if hardware is unavailable."""
    if not HAS_LEDS:
        return None
    strip = PixelStrip(
        NUM_LEDS, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL
    )
    strip.begin()
    return strip


def all_leds_off(strip):
    if not strip:
        return
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def all_leds_color(strip, rgb):
    if not strip:
        return
    r, g, b = rgb
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, Color(r, g, b))
    strip.show()


def flash_leds(strip, rgb, count):
    """Flash all LEDs a given color a given number of times."""
    if not strip:
        return
    for _ in range(count):
        all_leds_color(strip, rgb)
        time.sleep(FLASH_ON_S)
        all_leds_off(strip)
        time.sleep(FLASH_OFF_S)


def get_led_index(row, col):
    """Convert board [row, col] to serpentine LED strip index."""
    if row % 2 == 0:
        return row * BOARD_COLS + col
    else:
        return row * BOARD_COLS + (BOARD_COLS - 1 - col)


def get_perimeter_indices():
    """LED indices for the board perimeter in clockwise order."""
    indices = []
    for col in range(BOARD_COLS):
        indices.append(get_led_index(0, col))
    for row in range(1, BOARD_ROWS):
        indices.append(get_led_index(row, BOARD_COLS - 1))
    for col in range(BOARD_COLS - 2, -1, -1):
        indices.append(get_led_index(BOARD_ROWS - 1, col))
    for row in range(BOARD_ROWS - 2, 0, -1):
        indices.append(get_led_index(row, 0))
    return indices


def animate_connecting(strip, stop_event):
    """Orange breathing pulse while the browser is launching. Runs in a thread."""
    if not strip:
        return
    r, g, b = COLOR_CONNECTING
    steps = 20
    while not stop_event.is_set():
        for i in range(steps + 1):
            if stop_event.is_set():
                break
            frac = i / steps
            for led in range(NUM_LEDS):
                strip.setPixelColor(
                    led, Color(int(r * frac), int(g * frac), int(b * frac))
                )
            strip.show()
            stop_event.wait(CONNECT_PULSE_STEP_S)
        for i in range(steps, -1, -1):
            if stop_event.is_set():
                break
            frac = i / steps
            for led in range(NUM_LEDS):
                strip.setPixelColor(
                    led, Color(int(r * frac), int(g * frac), int(b * frac))
                )
            strip.show()
            stop_event.wait(CONNECT_PULSE_STEP_S)
    all_leds_off(strip)


def animate_search(strip, stop_event):
    """Blue chase around the board perimeter. Runs in a thread."""
    if not strip:
        return
    perimeter = get_perimeter_indices()
    r, g, b = COLOR_SEARCHING
    while not stop_event.is_set():
        for idx in perimeter:
            if stop_event.is_set():
                break
            all_leds_off(strip)
            strip.setPixelColor(idx, Color(r, g, b))
            strip.show()
            stop_event.wait(SEARCH_CHASE_DELAY_S)
    all_leds_off(strip)


def animate_idle(strip, stop_event):
    """Dim white breathing pulse (your turn — waiting for input). Runs in a thread."""
    if not strip:
        return
    r, g, b = (255, 255, 255)
    while not stop_event.is_set():
        for i in range(IDLE_PULSE_STEPS + 1):
            if stop_event.is_set():
                break
            frac = (i / IDLE_PULSE_STEPS) * IDLE_PULSE_MAX_FRAC
            for led in range(NUM_LEDS):
                strip.setPixelColor(
                    led, Color(int(r * frac), int(g * frac), int(b * frac))
                )
            strip.show()
            stop_event.wait(IDLE_PULSE_STEP_S)
        for i in range(IDLE_PULSE_STEPS, -1, -1):
            if stop_event.is_set():
                break
            frac = (i / IDLE_PULSE_STEPS) * IDLE_PULSE_MAX_FRAC
            for led in range(NUM_LEDS):
                strip.setPixelColor(
                    led, Color(int(r * frac), int(g * frac), int(b * frac))
                )
            strip.show()
            stop_event.wait(IDLE_PULSE_STEP_S)
    all_leds_off(strip)


def signal_connected(strip):
    """Green flash x2 — logged in and ready."""
    flash_leds(strip, COLOR_CONNECTED, FLASH_COUNT_CONNECT)


def signal_game_found(strip, color):
    """White flash x3 (White) or green flash x3 (Black)."""
    rgb = COLOR_FOUND_WHITE if color == "white" else COLOR_FOUND_BLACK
    flash_leds(strip, rgb, FLASH_COUNT_FOUND)


def signal_error(strip):
    """Red flash x3 — error."""
    flash_leds(strip, COLOR_ERROR, FLASH_COUNT_ERROR)


def _start_thread(target, strip, stop_event):
    """Start a daemon animation thread and return it."""
    t = threading.Thread(target=target, args=(strip, stop_event), daemon=True)
    t.start()
    return t


def _stop_thread(stop_event, thread):
    """Signal a thread to stop and wait for it to finish."""
    stop_event.set()
    if thread:
        thread.join(timeout=2)


# =============================================================================
# HELPERS
# =============================================================================


def step(prompt):
    """Print a prompt, wait for Enter, then confirm the press."""
    print(f"\n  >> {prompt}")
    input("     [Press Enter to continue]")


def parse_square(token):
    """
    Parse a square like "e2" → (file, rank) as 1-indexed ints.
    Returns None if the token is invalid.
    """
    token = token.strip().lower()
    if len(token) != 2:
        return None
    file_ch, rank_ch = token[0], token[1]
    if file_ch not in "abcdefgh" or rank_ch not in "12345678":
        return None
    return ord(file_ch) - ord("a") + 1, int(rank_ch)


def parse_move(text):
    """
    Parse a move string like "e2 e4" → (from_file, from_rank, to_file, to_rank).
    Returns None if the input is not parseable.
    """
    parts = text.strip().split()
    if len(parts) != 2:
        return None
    src = parse_square(parts[0])
    dst = parse_square(parts[1])
    if src is None or dst is None:
        return None
    return src[0], src[1], dst[0], dst[1]


def wait_for_game_start(page, timeout=120):
    """
    Poll until the resign button is visible (game has started).
    Returns True if the game started, False on timeout.
    """
    resign_selector = LOCATORS["resign_button"]
    resign2_selecotr = LOCATORS["second_resign_button"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            el = page.query_selector(resign_selector)
            el2 = page.query_selector(resign2_selecotr)
            if (el and el.is_visible()) or (el2 and el2.is_visible()):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


# Standard chess starting position.
# row 0 = rank 1 (White back rank), row 7 = rank 8 (Black back rank)
# col 0 = file a, col 7 = file h
# Uppercase = White, lowercase = Black, '.' = empty
STARTING_POSITION = [
    ["R", "N", "B", "Q", "K", "B", "N", "R"],  # rank 1
    ["P", "P", "P", "P", "P", "P", "P", "P"],  # rank 2
    [".", ".", ".", ".", ".", ".", ".", "."],  # rank 3
    [".", ".", ".", ".", ".", ".", ".", "."],  # rank 4
    [".", ".", ".", ".", ".", ".", ".", "."],  # rank 5
    [".", ".", ".", ".", ".", ".", ".", "."],  # rank 6
    ["p", "p", "p", "p", "p", "p", "p", "p"],  # rank 7
    ["r", "n", "b", "q", "k", "b", "n", "r"],  # rank 8
]


def count_differences(a, b):
    """Count squares that differ between two 8x8 boards."""
    return sum(a[r][c] != b[r][c] for r in range(8) for c in range(8))


def print_clocks(page, color):
    """Read and print both player clocks."""
    white, black = read_clocks(page, color)
    print(f"  Clocks — White: {white}  Black: {black}")


def wait_for_opponent(page, pre_move_board):
    """
    Poll board every 0.5 s until the opponent has moved.

    If pre_move_board is None (playing Black on move 1, before we have moved):
        Compares against STARTING_POSITION. White's first move changes exactly
        2 squares, so >= 2 differences means White has played. Using the fixed
        starting position avoids the race condition where White moves before the
        first read_board() call would establish a live baseline.

    Otherwise compares against pre_move_board (snapshot taken before our click).
        Our move = 2 square differences. Opponent's reply = 2 more. Threshold > 2
        fires only after both moves are reflected, handling premoves and instant
        replies that land before the next poll.

    Returns the new board state.
    """
    print("\n  Waiting for opponent's move...")
    if pre_move_board is None:
        # Move 1 as Black: compare against the known starting position
        while True:
            time.sleep(0.5)
            current = read_board(page)
            if count_differences(current, STARTING_POSITION) >= 2:
                return current
    else:
        # Mid-game: wait until both our move and opponent's move are visible
        while True:
            time.sleep(0.5)
            current = read_board(page)
            if count_differences(current, pre_move_board) > 2:
                return current


# =============================================================================
# MAIN
# =============================================================================


def select_time_control(page, time_control):
    """
    Open the time control dropdown and select the given time control.
    Returns the label that was actually clicked (as shown in the UI), or None on failure.

    The dropdown trigger matches text like "3 min (Blitz)" or "10 min (Rapid)".
    """
    # Regex matches "3 min (Blitz)", "10 min (Rapid)", "2 | 1 (Bullet)", etc.
    dropdown_pattern = re.compile(r"^(?:\d+\s*min|\d+\s*\|\s*\d+)\s*\([^)]*\)$")
    try:
        trigger = page.get_by_text(dropdown_pattern)
        current_label = trigger.inner_text()
        trigger.click()
        time.sleep(0.5)
        print(f"  Dropdown opened (was: {current_label!r})")
    except Exception as e:
        print(f"  FAIL — could not open time control dropdown: {e}")
        return None

    try:
        selector = page.get_by_role("button", name=time_control, exact=True)
        count = selector.count()
        print(f"Amount of 10 min: {count}")
        time.sleep(1)
        selector.first.click(timeout=20000)
        print(f"  OK — selected time control: {time_control!r}")
        trigger = page.get_by_text(dropdown_pattern)
        current_label = trigger.inner_text()
        print(f"  Dropdown closed (now: {current_label!r})")
        return time_control
    except Exception as e:
        print(f"  FAIL — could not select '{time_control}': {e}")
        return None


def main():
    visible = "--visible" in sys.argv

    # Optional: --time "10 min" overrides TIME_CONTROL from config
    time_control = TIME_CONTROL
    if "--time" in sys.argv:
        idx = sys.argv.index("--time")
        if idx + 1 < len(sys.argv):
            time_control = sys.argv[idx + 1]

    headless = not visible

    print()
    print("=" * 50)
    print("  Interactive Chess — chess.com")
    print("=" * 50)
    print(f"  Mode: {'visible' if visible else 'headless'}")
    print(f"  Time control: {time_control}")
    print()

    strip = init_strip()

    # --- Browser launch — orange connecting pulse ---
    stop_connect = threading.Event()
    connect_thread = _start_thread(animate_connecting, strip, stop_connect)
    print("  Launching Chromium...")
    context, page = launch(headless=headless)
    # Browser is up; stop the connecting pulse before checking login

    try:
        # --- Login check ---
        print("  Checking login...")
        if not is_logged_in(page):
            _stop_thread(stop_connect, connect_thread)
            signal_error(strip)
            print("  ERROR: Not logged in to chess.com.")
            print("  Run: python3 game_seeker.py --first-login")
            return
        _stop_thread(stop_connect, connect_thread)
        signal_connected(strip)
        time.sleep(1)
        print("  OK — logged in.")
        stop2_connect = threading.Event()
        connect2_thread = _start_thread(animate_connecting, strip, stop2_connect)
        # --- Select time control ---
        print(f"  Selecting time control: {time_control!r}")
        selected = select_time_control(page, time_control)
        if selected is None:
            print("  WARNING — proceeding with whatever time control is currently set.")

        _stop_thread(stop2_connect, connect2_thread)
        # --- Click Play — idle pulse while waiting for Enter ---
        stop_idle = threading.Event()
        idle_thread = _start_thread(animate_idle, strip, stop_idle)
        step("Click Play / Start Game")
        _stop_thread(stop_idle, idle_thread)

        try:
            page.get_by_role("button", name=LOCATORS["play_button"], exact=True).click(
                timeout=8000
            )
            print("  OK — Play button clicked, searching for a game...")
        except Exception as e:
            signal_error(strip)
            print(f"  FAIL — could not click Play button: {e}")
            return

        # --- Searching — blue chase while waiting for an opponent ---
        stop_search = threading.Event()
        search_thread = _start_thread(animate_search, strip, stop_search)
        print("  Searching for a game...")
        game_started = wait_for_game_start(page)
        _stop_thread(stop_search, search_thread)

        if not game_started:
            signal_error(strip)
            print("  FAIL — timed out waiting for game to start.")
            return
        print("  OK — game started!")

        # --- Detect color and flash the result ---
        color = detect_my_color(page)
        signal_game_found(strip, color)
        board = read_board(page)

        print()
        print(f"  Playing as: {color.upper()}")
        print_board(board, color)
        print_clocks(page, color)

        # --- Game loop ---
        # White moves first; if we're Black we wait for opponent's first move.
        my_turn = color == "white"
        pre_move_board = None  # set before each of our moves; None = haven't moved yet

        while True:
            if my_turn:
                # Dim white idle pulse while waiting for the player to type a move
                stop_idle = threading.Event()
                idle_thread = _start_thread(animate_idle, strip, stop_idle)

                while True:
                    raw = input("\n  Your move (e.g. e2 e4): ").strip()
                    if not raw:
                        continue
                    parsed = parse_move(raw)
                    if parsed is None:
                        print("  Bad input — use format: e2 e4")
                        continue
                    break

                _stop_thread(stop_idle, idle_thread)

                from_file, from_rank, to_file, to_rank = parsed
                pre_move_board = board  # snapshot before clicking
                ok = make_move(page, from_file, from_rank, to_file, to_rank, color)
                if not ok:
                    signal_error(strip)
                    print("  ERROR: make_move failed — is the game still active?")
                    break

                # Single white flash confirms the move was sent
                flash_leds(strip, COLOR_FOUND_WHITE, 1)

                # Show board after our move (may already include an opponent premove)
                time.sleep(0.3)
                board = read_board(page)
                print_board(board, color)
                print_clocks(page, color)
                my_turn = False

            else:
                # Blue chase while waiting for opponent
                stop_search = threading.Event()
                search_thread = _start_thread(animate_search, strip, stop_search)

                board = wait_for_opponent(page, pre_move_board)

                _stop_thread(stop_search, search_thread)
                # Single green flash signals the opponent has moved
                flash_leds(strip, COLOR_FOUND_BLACK, 1)

                print("\n  Opponent moved:")
                print_board(board, color)
                print_clocks(page, color)
                my_turn = True

    except KeyboardInterrupt:
        print("\n\n  Interrupted — closing browser.")
    finally:
        all_leds_off(strip)
        close(context)
        print("  Done.")


if __name__ == "__main__":
    main()
