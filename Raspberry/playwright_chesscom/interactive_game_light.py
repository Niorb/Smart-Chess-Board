#!/usr/bin/env python3
"""
interactive_game_light.py

Interactive chess session on chess.com via Lightpanda (CDP).
Alternative to interactive_game.py for low-RAM environments like Raspberry Pi.
Connects Playwright to a Lightpanda backend instead of launching Chromium.

Usage:
  python3 interactive_game_light.py                   # headless, default time control
  python3 interactive_game_light.py --time "10 min"   # override time control
"""

import os
import re
import sys
import time
import threading
import subprocess
from playwright.sync_api import sync_playwright

from chesscom_config import (
    LOCATORS,
    CHESS_COM_PLAY_URL,
    TIME_CONTROL,
    COLOR_FOUND_WHITE,
    COLOR_FOUND_BLACK,
)
from chesscom_browser import (
    is_logged_in,
    detect_my_color,
    read_board,
    print_board,
    read_clocks,
    make_move,
)
from led_helpers import (
    init_strip,
    all_leds_off,
    flash_leds,
    signal_connected,
    signal_game_found,
    signal_error,
    animate_connecting,
    animate_search,
    animate_idle,
    start_animation,
    stop_animation,
)

# =============================================================================
# LIGHTPANDA BROWSER LIFECYCLE
# =============================================================================

_playwright_instance = None
_lp_process = None

def launch_lightpanda():
    """
    Start Lightpanda CDP server and connect Playwright to it.
    Returns: (browser_context, page) tuple
    """
    global _playwright_instance, _lp_process

    print("  Starting Lightpanda CDP server (127.0.0.1:9222)...")
    # Add telemetry disable and specific host/port
    env = os.environ.copy()
    env["LIGHTPANDA_DISABLE_TELEMETRY"] = "true"
    
    _lp_process = subprocess.Popen(
        ["lightpanda", "serve", "--host", "127.0.0.1", "--port", "9222"],
        env=env
    )
    time.sleep(7)  # More time for WSL2/Pi to stabilize

    _playwright_instance = sync_playwright().start()
    
    try:
        if _lp_process.poll() is not None:
            print(f"  ERROR: Lightpanda process exited immediately with code {_lp_process.returncode}")
            sys.exit(1)

        # Connect using 127.0.0.1 explicitly
        browser = _playwright_instance.chromium.connect_over_cdp("ws://127.0.0.1:9222")
        
        # Create a fresh context and page
        context = browser.new_context()
        page = context.new_page()
        
        if _lp_process.poll() is not None:
            print("  ERROR: Lightpanda crashed after connection.")
            sys.exit(1)

        # Navigate to chess.com immediately to initialize
        page.goto(CHESS_COM_PLAY_URL, wait_until="commit", timeout=30000)
        return context, page
    except Exception as e:
        print(f"  ERROR: Could not connect to Lightpanda: {e}")
        close_lightpanda(None)
        sys.exit(1)

def close_lightpanda(context):
    """Clean shutdown: close Playwright and terminate Lightpanda."""
    global _playwright_instance, _lp_process
    try:
        if context:
            context.close()
    except Exception:
        pass
    try:
        if _playwright_instance:
            _playwright_instance.stop()
            _playwright_instance = None
    except Exception:
        pass
    try:
        if _lp_process:
            _lp_process.terminate()
            _lp_process.wait(timeout=5)
            _lp_process = None
    except Exception:
        pass

# =============================================================================
# HELPERS (Duplicated from interactive_game.py for autonomy)
# =============================================================================

def step(prompt):
    print(f"\n  >> {prompt}")
    input("     [Press Enter to continue]")

def parse_square(token):
    token = token.strip().lower()
    if len(token) != 2: return None
    file_ch, rank_ch = token[0], token[1]
    if file_ch not in "abcdefgh" or rank_ch not in "12345678": return None
    return ord(file_ch) - ord("a") + 1, int(rank_ch)

def parse_move(text):
    parts = text.strip().split()
    if len(parts) != 2: return None
    src = parse_square(parts[0])
    dst = parse_square(parts[1])
    if src is None or dst is None: return None
    return src[0], src[1], dst[0], dst[1]

def wait_for_game_start(page, timeout=120):
    resign_selector = LOCATORS["resign_button"]
    resign2_selector = LOCATORS["second_resign_button"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            el = page.query_selector(resign_selector)
            el2 = page.query_selector(resign2_selector)
            if (el and el.is_visible()) or (el2 and el2.is_visible()):
                return True
        except Exception: pass
        time.sleep(0.5)
    return False

STARTING_POSITION = [
    ["R", "N", "B", "Q", "K", "B", "N", "R"],
    ["P", "P", "P", "P", "P", "P", "P", "P"],
    [".", ".", ".", ".", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", ".", ".", "."],
    ["p", "p", "p", "p", "p", "p", "p", "p"],
    ["r", "n", "b", "q", "k", "b", "n", "r"],
]

def count_differences(a, b):
    return sum(a[r][c] != b[r][c] for r in range(8) for c in range(8))

def print_clocks(page, color):
    white, black = read_clocks(page, color)
    print(f"  Clocks — White: {white}  Black: {black}")

def wait_for_opponent(page, pre_move_board):
    print("\n  Waiting for opponent's move...")
    if pre_move_board is None:
        while True:
            time.sleep(0.5)
            current = read_board(page)
            if count_differences(current, STARTING_POSITION) >= 2:
                return current
    else:
        while True:
            time.sleep(0.5)
            current = read_board(page)
            if count_differences(current, pre_move_board) > 2:
                return current

def select_time_control(page, time_control):
    dropdown_pattern = re.compile(r"^(?:\d+\s*min|\d+\s*\|\s*\d+)\s*\([^)]*\)$")
    try:
        trigger = page.get_by_text(dropdown_pattern)
        trigger.click()
        time.sleep(0.5)
        selector = page.get_by_role("button", name=time_control, exact=True)
        selector.first.click(timeout=20000)
        return time_control
    except Exception as e:
        print(f"  FAIL — could not select '{time_control}': {e}")
        return None

# =============================================================================
# MAIN
# =============================================================================

def main():
    time_control = TIME_CONTROL
    if "--time" in sys.argv:
        idx = sys.argv.index("--time")
        if idx + 1 < len(sys.argv):
            time_control = sys.argv[idx + 1]

    print()
    print("=" * 50)
    print("  Interactive Chess (LIGHT) — chess.com")
    print("=" * 50)
    print(f"  Browser: Lightpanda (CDP)")
    print(f"  Time control: {time_control}")
    print()

    strip = init_strip()

    # --- Launch — orange connecting pulse ---
    stop_connect = threading.Event()
    connect_thread = start_animation(animate_connecting, strip, stop_connect)
    context, page = launch_lightpanda()

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
        
        # --- Select time control ---
        stop2_connect = threading.Event()
        connect2_thread = start_animation(animate_connecting, strip, stop2_connect)
        print(f"  Selecting time control: {time_control!r}")
        selected = select_time_control(page, time_control)
        stop_animation(stop2_connect, connect2_thread)

        # --- Click Play — idle pulse ---
        stop_idle = threading.Event()
        idle_thread = start_animation(animate_idle, strip, stop_idle)
        step("Click Play / Start Game")
        stop_animation(stop_idle, idle_thread)

        try:
            page.get_by_role("button", name=LOCATORS["play_button"], exact=True).click(timeout=8000)
            print("  OK — Play clicked, searching...")
        except Exception as e:
            signal_error(strip)
            print(f"  FAIL — Play button error: {e}")
            return

        # --- Searching — blue chase ---
        stop_search = threading.Event()
        search_thread = start_animation(animate_search, strip, stop_search)
        game_started = wait_for_game_start(page)
        stop_animation(stop_search, search_thread)

        if not game_started:
            signal_error(strip)
            print("  FAIL — timeout.")
            return

        # --- Game setup ---
        color = detect_my_color(page)
        signal_game_found(strip, color)
        board = read_board(page)

        print()
        print(f"  Playing as: {color.upper()}")
        print_board(board, color)
        print_clocks(page, color)

        my_turn = (color == "white")
        pre_move_board = None

        while True:
            if my_turn:
                stop_idle = threading.Event()
                idle_thread = start_animation(animate_idle, strip, stop_idle)
                while True:
                    raw = input("\n  Your move (e.g. e2 e4): ").strip()
                    if not raw: continue
                    parsed = parse_move(raw)
                    if parsed is None:
                        print("  Bad format: e2 e4")
                        continue
                    break
                stop_animation(stop_idle, idle_thread)

                from_file, from_rank, to_file, to_rank = parsed
                pre_move_board = board
                ok = make_move(page, from_file, from_rank, to_file, to_rank, color)
                if not ok:
                    signal_error(strip)
                    print("  ERROR: make_move failed.")
                    break

                flash_leds(strip, COLOR_FOUND_WHITE, 1)
                time.sleep(0.3)
                board = read_board(page)
                print_board(board, color)
                print_clocks(page, color)
                my_turn = False
            else:
                stop_search = threading.Event()
                search_thread = start_animation(animate_search, strip, stop_search)
                board = wait_for_opponent(page, pre_move_board)
                stop_animation(stop_search, search_thread)
                flash_leds(strip, COLOR_FOUND_BLACK, 1)
                print("\n  Opponent moved:")
                print_board(board, color)
                print_clocks(page, color)
                my_turn = True

    except KeyboardInterrupt:
        print("\n  Closing...")
    finally:
        all_leds_off(strip)
        close_lightpanda(context)

if __name__ == "__main__":
    main()
