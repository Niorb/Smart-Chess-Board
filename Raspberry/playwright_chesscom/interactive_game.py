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

from chesscom_config import LOCATORS, CHESS_COM_PLAY_URL, TIME_CONTROL
from chesscom_browser import (
    launch,
    close,
    is_logged_in,
    detect_my_color,
    read_board,
    print_board,
    make_move,
)


# =============================================================================
# HELPERS
# =============================================================================


def step(prompt):
    """Print a prompt, wait for Enter, then confirm the press."""
    print(f"\n  >> {prompt}")
    input("     [Press Enter to continue]")
    print("     PRESSED")


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
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            el = page.query_selector(resign_selector)
            if el and el.is_visible():
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def boards_differ(a, b):
    """Return True if two 8x8 board lists differ."""
    for r in range(8):
        for c in range(8):
            if a[r][c] != b[r][c]:
                return True
    return False


def wait_for_opponent(page, known_board):
    """
    Poll board every 0.5 s until it changes (opponent moved).
    Returns the new board state.
    """
    print("\n  Waiting for opponent's move...")
    while True:
        time.sleep(0.5)
        new_board = read_board(page)
        if boards_differ(known_board, new_board):
            return new_board


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
        page.get_by_role("button", name=time_control, exact=True).click(timeout=5000)
        print(f"  OK — selected time control: {time_control!r}")
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

    # --- Browser launch ---
    print("  Launching Chromium...")
    context, page = launch(headless=headless)

    try:
        # --- Login check ---
        print("  Checking login...")
        if not is_logged_in(page):
            print("  ERROR: Not logged in to chess.com.")
            print("  Run: python3 game_seeker.py --first-login")
            return
        print("  OK — logged in.")

        # --- Navigate to play page ---
        print("  Navigating to play page...")
        page.goto(CHESS_COM_PLAY_URL)
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        print(f"  OK — at {page.url}")

        # --- Select time control ---
        step(f"Select time control: {time_control!r}")
        selected = select_time_control(page, time_control)
        if selected is None:
            print("  WARNING — proceeding with whatever time control is currently set.")

        # --- Click Play ---
        step("Click Play / Start Game")
        try:
            page.get_by_role("button", name=LOCATORS["play_button"], exact=True).click(
                timeout=8000
            )
            print("  OK — Play button clicked, searching for a game...")
        except Exception as e:
            print(f"  FAIL — could not click Play button: {e}")
            return

        # --- Wait for game to start ---
        print("  Polling for resign button...")
        if not wait_for_game_start(page):
            print("  FAIL — timed out waiting for game to start.")
            return
        print("  OK — game started!")

        # --- Detect color and initial board ---
        color = detect_my_color(page)
        board = read_board(page)

        print()
        print(f"  Playing as: {color.upper()}")
        print_board(board)

        # --- Game loop ---
        # White moves first; if we're Black we wait for opponent's first move.
        my_turn = color == "white"

        while True:
            if my_turn:
                # Prompt for move
                while True:
                    raw = input("\n  Your move (e.g. e2 e4): ").strip()
                    if not raw:
                        continue
                    parsed = parse_move(raw)
                    if parsed is None:
                        print("  Bad input — use format: e2 e4")
                        continue
                    break

                from_file, from_rank, to_file, to_rank = parsed
                ok = make_move(page, from_file, from_rank, to_file, to_rank, color)
                if not ok:
                    print("  ERROR: make_move failed — is the game still active?")
                    break

                # Update board after our move
                time.sleep(0.3)
                board = read_board(page)
                print_board(board)
                my_turn = False

            else:
                board = wait_for_opponent(page, board)
                print("\n  Opponent moved:")
                print_board(board)
                my_turn = True

    except KeyboardInterrupt:
        print("\n\n  Interrupted — closing browser.")
    finally:
        close(context)
        print("  Done.")


if __name__ == "__main__":
    main()
