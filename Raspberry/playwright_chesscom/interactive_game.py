#!/usr/bin/env python3
"""
interactive_game.py

Interactive chess session on chess.com via Playwright.
Walks through browser launch -> login check -> game start, then runs a
turn-by-turn loop: prompt for moves as White, wait for opponent as Black.

Usage:
  python3 interactive_game.py                        # headless, default time control
  python3 interactive_game.py --visible              # visible browser
  python3 interactive_game.py --time "10 min"        # override time control
"""

import re
import sys
import threading
import time

from chesscom_browser import (
    close,
    detect_my_color,
    is_logged_in,
    launch,
    make_move,
    print_board,
    read_board,
    read_clocks,
)
from chesscom_config import (
    COLOR_FOUND_BLACK,
    COLOR_FOUND_WHITE,
    LOCATORS,
    TIME_CONTROL,
)
from led_helpers import (
    all_leds_off,
    animate_connecting,
    animate_idle,
    animate_search,
    flash_leds,
    init_strip,
    signal_connected,
    signal_error,
    signal_game_found,
    start_animation,
    stop_animation,
)

# =============================================================================
# HELPERS
# =============================================================================


def step(prompt):
    """Print a prompt, wait for Enter, then confirm the press."""
    print(f"\n  >> {prompt}")
    input("     [Press Enter to continue]")


def parse_square(token):
    """
    Parse a square like "e2" -> (file, rank) as 1-indexed ints.
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
    Parse a move string like "e2 e4" -> (from_file, from_rank, to_file, to_rank).
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
    resign2_selector = LOCATORS["second_resign_button"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            el = page.query_selector(resign_selector)
            el2 = page.query_selector(resign2_selector)
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


def print_clocks(page, color):
    """Read and print both player clocks."""
    white, black = read_clocks(page, color)
    print(f"  Clocks — White: {white}  Black: {black}")


def wait_for_opponent(page, pre_move_board, my_color):
    """
    Poll board every 0.5 s until the opponent has moved.

    Specifically checks for the presence of an opponent piece on a square
    where they didn't have one before. This handles castling, en passant,
    and premoves more robustly than raw square difference counts.

    Returns the new board state.
    """
    print("\n  Waiting for opponent's move...")
    opponent_is_white = my_color == "black"

    def has_opponent_moved(old_board, new_board):
        for r in range(8):
            for c in range(8):
                old_p = old_board[r][c]
                new_p = new_board[r][c]
                if new_p == ".":
                    continue
                # Opponent pieces: Uppercase = White, Lowercase = Black
                is_opp = new_p.isupper() if opponent_is_white else new_p.islower()
                if not is_opp:
                    continue
                was_opp = old_p.isupper() if (old_p != "." and opponent_is_white) else (old_p != "." and old_p.islower())
                if is_opp and not was_opp:
                    return True
        return False

    baseline = STARTING_POSITION if pre_move_board is None else pre_move_board

    while True:
        time.sleep(0.5)
        current = read_board(page)
        if has_opponent_moved(baseline, current):
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
    connect_thread = start_animation(animate_connecting, strip, stop_connect)
    print("  Launching Chromium...")
    context, page = launch(headless=headless)

    try:
        # --- Login check ---
        print("  Checking login...")
        if not is_logged_in(page):
            stop_animation(stop_connect, connect_thread)
            signal_error(strip)
            print("  ERROR: Not logged in to chess.com.")
            print("  Run: python3 game_seeker.py --first-login")
            return
        stop_animation(stop_connect, connect_thread)
        signal_connected(strip)
        time.sleep(1)
        print("  OK — logged in.")
        stop2_connect = threading.Event()
        connect2_thread = start_animation(animate_connecting, strip, stop2_connect)
        # --- Select time control ---
        print(f"  Selecting time control: {time_control!r}")
        selected = select_time_control(page, time_control)
        if selected is None:
            print("  WARNING — proceeding with whatever time control is currently set.")

        stop_animation(stop2_connect, connect2_thread)
        # --- Click Play — idle pulse while waiting for Enter ---
        stop_idle = threading.Event()
        idle_thread = start_animation(animate_idle, strip, stop_idle)
        step("Click Play / Start Game")
        stop_animation(stop_idle, idle_thread)

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
        search_thread = start_animation(animate_search, strip, stop_search)
        print("  Searching for a game...")
        game_started = wait_for_game_start(page)
        stop_animation(stop_search, search_thread)

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
                idle_thread = start_animation(animate_idle, strip, stop_idle)

                while True:
                    raw = input("\n  Your move (e.g. e2 e4): ").strip()
                    if not raw:
                        continue
                    parsed = parse_move(raw)
                    if parsed is None:
                        print("  Bad input — use format: e2 e4")
                        continue
                    break

                stop_animation(stop_idle, idle_thread)

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
                search_thread = start_animation(animate_search, strip, stop_search)

                board = wait_for_opponent(page, pre_move_board, color)

                stop_animation(stop_search, search_thread)
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
