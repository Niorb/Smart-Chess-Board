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
    MOVE_CLICK_DELAY_S,
    LOCATORS,
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
        # executable_path="/usr/bin/chromium",
        viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        args=[
            "--disable-gpu",  # Essential on Pi, no GPU
            "--disable-extensions",  # Clean, no overhead
            "--no-first-run",  # Skip setup dialogs
            "--disable-blink-features=AutomationControlled",  # Keep for chess.com detection avoidance
            "--no-sandbox",  # Safe in controlled Pi env, reduces overhead
            "--disable-dev-shm-usage",  # IMPORTANT: /dev/shm is tiny on Pi, causes crashes
            "--shm-size=1gb",  # Pair with above — or use --disable-dev-shm-usage alone
            "--single-process",  # Merges renderer into browser process, saves ~50MB RAM
            "--disable-setuid-sandbox",
            "--js-flags=--max-old-space-size=256",  # Cap V8 heap to 256MB
            "--memory-pressure-off",  # Prevents aggressive GC pauses
            "--disable-features=TranslateUI,BlinkGenPropertyTrees",
            "--disable-ipc-flooding-protection",  # Reduces IPC overhead
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
    Navigates to the play page if not already there, then checks whether
    chess.com redirected to a login/register page (which only happens when
    the session is missing or expired).

    Returns: True if logged in, False otherwise.
    """
    if CHESS_COM_PLAY_URL not in page.url:
        page.goto(CHESS_COM_PLAY_URL)
        page.wait_for_load_state("domcontentloaded", timeout=60000)

    return "/login" not in page.url and "/register" not in page.url


def do_first_login():
    """
    Open a visible Playwright browser so the user can log in to chess.com.
    The persistent context saves cookies automatically. After the user logs
    in and presses Enter, the browser is closed. The caller then relaunches
    headless.

    Returns: True if login was verified, False otherwise.
    """
    print()
    print("=" * 50)
    print("  FIRST-TIME LOGIN")
    print("=" * 50)
    print()
    print("A browser window will open — log in to chess.com.")
    print("Once logged in, come back here and press ENTER.")
    print()

    context, page = launch(headless=False)
    page.goto(CHESS_COM_PLAY_URL)

    input()  # Block until user presses Enter

    logged_in = is_logged_in(page)
    close(context)

    if logged_in:
        print("Login saved successfully.")
    else:
        print("WARNING: Could not detect login. Try again.")

    return logged_in


# =============================================================================
# GAME SEEKING
# =============================================================================


def navigate_to_play(page):
    """Navigate to the chess.com play page if not already there."""
    if "/play" not in page.url:
        page.goto(CHESS_COM_PLAY_URL)
        page.wait_for_load_state("load")


def seek_game(page, time_control=None):
    """
    Start searching for a game on chess.com.
    Navigates to the play page, selects the time control, and clicks Play.

    Returns: True if the search was initiated, False on error.
    """
    try:
        navigate_to_play(page)

        if time_control:
            print(f"Selecting time control: {time_control}")
            import re
            dropdown_pattern = re.compile(r"^(?:\d+\s*min|\d+\s*\|\s*\d+)\s*\([^)]*\)$")
            try:
                # 1. Click the dropdown trigger
                trigger = page.get_by_text(dropdown_pattern)
                trigger.click()
                time.sleep(0.5)
                # 2. Click the option (e.g. "10 min", "3 min", "1 min")
                selector = page.get_by_role("button", name=time_control, exact=True)
                selector.first.click(timeout=8000)
                print(f"Selected time control: {time_control}")
            except Exception as e:
                print(f"WARNING: Dynamic time control selection failed ({e}), trying standard select...")
                try:
                    page.get_by_role("button", name=time_control, exact=True).click(timeout=5000)
                except Exception:
                    pass
        else:
            # Select default time control from config
            try:
                # Open dropdown menu
                page.get_by_role(
                    "button", name=LOCATORS["time_control_show_options"]
                ).click(timeout=5000)
                # Click the option whose visible text matches TIME_CONTROL (e.g. "10 min")
                page.get_by_role("button", name=TIME_CONTROL, exact=True).click(
                    timeout=5000
                )
            except PlaywrightTimeout:
                print(
                    "WARNING: Could not find time control button, proceeding with default."
                )

        # Click Play
        page.get_by_role("button", name=LOCATORS["play_button"], exact=True).click(
            timeout=10000
        )
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
    board_locator = page.locator(LOCATORS["board_container"])

    while time.time() < deadline:
        # Check for cancellation
        if cancel_event and cancel_event.is_set():
            return None

        try:
            if board_locator.is_visible():
                return True
        except Exception:
            pass

        if cancel_event:
            cancel_event.wait(POLL_INTERVAL)
        else:
            time.sleep(POLL_INTERVAL)

    print("Search timed out — no game found.")
    return False


def cancel_search(page):
    """Cancel an active game search by clicking the cancel button."""
    try:
        page.get_by_role("button", name=LOCATORS["cancel_search"]).click(timeout=5000)
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
    flipped_classes = LOCATORS["board_flipped_class"].split()
    board_selector = LOCATORS["board_container"]

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


def read_board(page):
    """
    Read the current board position from the chess.com game page.

    Queries all piece elements inside the board container and parses their
    CSS classes (e.g. "piece bn square-78") to reconstruct the position.

    Returns: 8x8 list[list[str]]
        - Uppercase letters = White pieces  (K Q R B N P)
        - Lowercase letters = Black pieces  (k q r b n p)
        - '.'               = empty square
        piece_map[row][col]: row 0 = rank 1 (White back rank),
                             row 7 = rank 8 (Black back rank)
                             col 0 = file a, col 7 = file h

    Returns a blank board (all '.') if no pieces are found or on error.
    """
    PIECE_CODES = {
        "wp",
        "wr",
        "wn",
        "wb",
        "wq",
        "wk",
        "bp",
        "br",
        "bn",
        "bb",
        "bq",
        "bk",
    }

    piece_map = [["." for _ in range(8)] for _ in range(8)]
    pieces_selector = LOCATORS["board_container"] + " .piece"

    try:
        elements = page.query_selector_all(pieces_selector)
        for el in elements:
            classes = (el.get_attribute("class") or "").split()

            piece_code = None
            square_code = None
            for cls in classes:
                if cls in PIECE_CODES:
                    piece_code = cls
                elif cls.startswith("square-") and len(cls) == 9:
                    square_code = cls[7:]  # "78" from "square-78"

            if not piece_code or not square_code:
                continue

            file_n = int(square_code[0])  # 1-8
            rank_n = int(square_code[1])  # 1-8
            col = file_n - 1  # 0-7
            row = rank_n - 1  # 0-7

            if not (0 <= row <= 7 and 0 <= col <= 7):
                continue

            color, piece = piece_code[0], piece_code[1]  # 'w'/'b', 'p'/'r'/...
            piece_map[row][col] = piece.upper() if color == "w" else piece

    except Exception as e:
        print(f"WARNING: Could not read board ({e})")

    return piece_map


def print_board(piece_map, color="white"):
    """
    Print an 8x8 piece_map (from read_board) to the terminal.

    color="white" (default): rank 8 at top, file a on left (White's POV).
    color="black":           rank 1 at top, file h on left (Black's POV).
    Uppercase = White, lowercase = Black, '.' = empty.
    """
    print()
    if color == "black":
        print("    h g f e d c b a")
        print("   ----------------")
        for rank in range(1, 9):
            row = rank - 1
            row_str = " ".join(reversed(piece_map[row]))
            print(f" {rank}| {row_str}")
    else:
        print("    a b c d e f g h")
        print("   ----------------")
        for rank in range(8, 0, -1):
            row = rank - 1
            row_str = " ".join(piece_map[row])
            print(f" {rank}| {row_str}")
    print()


# =============================================================================
# CLOCKS
# =============================================================================


def read_clocks(page, color="white"):
    """
    Read both player clocks from the current game page.

    color: "white" or "black" — selects the correct selectors for the board orientation.
    Returns: (white_time, black_time) as strings (e.g. "9:45", "10:00").
    Returns "?" for any clock that cannot be read.
    """

    def read_clock(selector):
        try:
            el = page.query_selector(selector)
            if el:
                return el.inner_text().strip()
        except Exception:
            pass
        return None

    white = read_clock(LOCATORS.get(f"white_clock_{color}"))
    black = read_clock(LOCATORS.get(f"black_clock_{color}"))
    
    # Fallback to generic top/bottom containers if specific selectors failed
    if not white or white == "?":
        sel = "#board-layout-player-bottom .clock-component" if color == "white" else "#board-layout-player-top .clock-component"
        white = read_clock(sel) or "?"
        
    if not black or black == "?":
        sel = "#board-layout-player-top .clock-component" if color == "white" else "#board-layout-player-bottom .clock-component"
        black = read_clock(sel) or "?"
        
    return white, black


# =============================================================================
# MOVE EXECUTION
# =============================================================================


def make_move(page, from_file, from_rank, to_file, to_rank, color):
    """
    Make a move on chess.com by clicking source then destination square.

    Args:
        page: Playwright Page
        from_file, from_rank: source square (file 1-8 = a-h, rank 1-8)
        to_file, to_rank:     destination square (same indexing)
        color: "white" or "black" — determines board orientation for coordinate math

    Returns: True if both clicks were issued, False on error.
    """
    try:
        box = page.locator(LOCATORS["board_container"]).bounding_box()
        if box is None:
            print("ERROR: Board not visible, cannot make move.")
            return False

        sq_w = box["width"] / 8
        sq_h = box["height"] / 8

        if color == "white":

            def to_pixel(file, rank):
                x = box["x"] + (file - 1) * sq_w + sq_w / 2
                y = box["y"] + (8 - rank) * sq_h + sq_h / 2
                return x, y
        else:

            def to_pixel(file, rank):
                x = box["x"] + (8 - file) * sq_w + sq_w / 2
                y = box["y"] + (rank - 1) * sq_h + sq_h / 2
                return x, y

        src_x, src_y = to_pixel(from_file, from_rank)
        dst_x, dst_y = to_pixel(to_file, to_rank)

        page.mouse.click(src_x, src_y)
        time.sleep(MOVE_CLICK_DELAY_S)
        page.mouse.click(dst_x, dst_y)

        return True

    except Exception as e:
        print(f"ERROR: make_move failed ({e})")
        return False
