"""
chesscom_browser.py

Playwright-based browser automation for chess.com.
Handles session persistence, login detection, game seeking, and color detection.

This module is synchronous and has no GPIO/LED knowledge.
It is imported by game_seeker.py (and later by smart_chess_board.py for Phase 2).

Usage (standalone test on any machine):
    from chesscom_browser import launch, is_logged_in, close
    browser, page = launch(headless=False)
    print("Logged in:", is_logged_in(page))
    close(browser)

Requires: pip3 install playwright && playwright install chromium
"""

import os
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from chesscom_config import (
    USER_DATA_DIR,
    CHESS_COM_PLAY_URL,
    VIEWPORT_WIDTH,
    VIEWPORT_HEIGHT,
    GAME_SEARCH_TIMEOUT,
    POLL_INTERVAL,
    TIME_CONTROL,
    SELECTORS,
)

# Keep a module-level reference so the Playwright context manager stays alive
_playwright_instance = None

# =============================================================================
# BROWSER LIFECYCLE
# =============================================================================

def launch(headless=True):
    """
    Launch a Chromium browser with a persistent user profile.
    Cookies and localStorage are saved in USER_DATA_DIR and reused
    on subsequent runs (no re-login needed).

    Returns: (browser_context, page) tuple
    """
    global _playwright_instance

    user_data_dir = os.path.abspath(USER_DATA_DIR)

    _playwright_instance = sync_playwright().start()

    context = _playwright_instance.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=headless,
        viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--shm-size=1gb",
            # RPi-friendly flags — prevent white screen / GPU stalls
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-translate",
            "--no-first-run",
            "--ignore-certificate-errors",
        ],
    )

    # Use the default page or create one
    page = context.pages[0] if context.pages else context.new_page()

    return context, page


def close(browser_context):
    """Clean shutdown: close browser and free resources."""
    global _playwright_instance
    try:
        browser_context.close()
    except Exception:
        pass
    try:
        if _playwright_instance:
            _playwright_instance.stop()
            _playwright_instance = None
    except Exception:
        pass

# =============================================================================
# LOGIN
# =============================================================================

def is_logged_in(page):
    """
    Check if the user is currently logged in to chess.com.
    Navigates to the play page if not already there, then looks for the
    logged-in indicator element.

    Returns: True if logged in, False otherwise.
    """
    if "chess.com" not in page.url:
        page.goto(CHESS_COM_PLAY_URL)

    try:
        page.wait_for_selector(
            SELECTORS["logged_in_indicator"],
            state="visible",
            timeout=5000,
        )
        return True
    except PlaywrightTimeout:
        return False


def prompt_login():
    """
    Instruct the user to log in via a plain Chromium session (not Playwright).
    The user runs Chromium manually with the same --user-data-dir so the
    session cookies are saved in the shared profile folder.

    Returns: None (the user must restart game_seeker.py after logging in).
    """
    user_data_dir = os.path.abspath(USER_DATA_DIR)

    print()
    print("=" * 50)
    print("  FIRST-TIME LOGIN")
    print("=" * 50)
    print()
    print("Open a SECOND terminal (or SSH session) and run:")
    print()
    print(f"  chromium-browser --user-data-dir={user_data_dir} https://www.chess.com")
    print()
    print("Log in to chess.com in that browser window.")
    print("Once logged in, CLOSE the browser, then come back")
    print("here and press ENTER to continue...")
    print()

    input()  # Block until user presses Enter
    print("Session should now be saved. Verifying...")

# =============================================================================
# GAME SEEKING
# =============================================================================

def navigate_to_play(page):
    """Navigate to the chess.com play page if not already there."""
    if "/play" not in page.url:
        page.goto(CHESS_COM_PLAY_URL)
        page.wait_for_load_state("load")


def seek_game(page):
    """
    Start searching for a game on chess.com.
    Navigates to the play page, selects the time control, and clicks Play.

    Returns: True if the search was initiated, False on error.
    """
    try:
        navigate_to_play(page)

        # Select time control (if the selector is configured)
        if SELECTORS["time_control_button"] != "PLACEHOLDER":
            try:
                page.click(SELECTORS["time_control_button"], timeout=5000)
            except PlaywrightTimeout:
                print("WARNING: Could not find time control button, "
                      "proceeding with default.")

        # Click Play
        page.click(SELECTORS["play_button"], timeout=10000)
        print("Searching for a game...")
        return True

    except PlaywrightTimeout:
        print("ERROR: Could not find the Play button on chess.com.")
        return False
    except Exception as e:
        print(f"ERROR: Failed to seek game: {e}")
        return False


def wait_for_game(page, timeout=None, cancel_event=None):
    """
    Wait for a game to start (board container becomes visible).
    Polls at POLL_INTERVAL. Can be cancelled by setting cancel_event.

    Args:
        page: Playwright Page instance
        timeout: Max seconds to wait (default: GAME_SEARCH_TIMEOUT)
        cancel_event: threading.Event — if set, stop waiting and return None

    Returns: True if game found, False if timeout, None if cancelled.
    """
    if timeout is None:
        timeout = GAME_SEARCH_TIMEOUT

    deadline = time.time() + timeout
    selector = SELECTORS["board_container"]

    while time.time() < deadline:
        # Check for cancellation
        if cancel_event and cancel_event.is_set():
            return None

        try:
            if page.query_selector(selector):
                return True
        except Exception:
            pass

        time.sleep(POLL_INTERVAL)

    print("Search timed out — no game found.")
    return False


def cancel_search(page):
    """Cancel an active game search by clicking the cancel button."""
    try:
        page.click(SELECTORS["cancel_search"], timeout=5000)
        print("Search cancelled.")
        return True
    except PlaywrightTimeout:
        print("WARNING: Could not find cancel button.")
        return False

# =============================================================================
# GAME STATE DETECTION
# =============================================================================

def detect_my_color(page):
    """
    Detect whether the player is White or Black in the current game.
    Checks if the board element has ALL the classes listed in board_flipped_class
    (space-separated). For example "board flipped" checks that the element has
    both the "board" class AND the "flipped" class.

    Returns: "white" or "black"
    """
    flipped_classes = SELECTORS["board_flipped_class"].split()
    board_selector = SELECTORS["board_container"]

    try:
        board = page.query_selector(board_selector)
        class_attr = board.get_attribute("class") or ""
        element_classes = class_attr.split()
        is_flipped = all(cls in element_classes for cls in flipped_classes)
        color = "black" if is_flipped else "white"
        print(f"Game found! Playing as {color.upper()}.")
        return color
    except Exception as e:
        print(f"WARNING: Could not detect color ({e}), defaulting to white.")
        return "white"
