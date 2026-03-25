"""
chesscom_browser.py

Playwright-based browser automation for chess.com.
Handles session persistence, login detection, game seeking, and color detection.

This module is purely async and has no GPIO/LED knowledge.
It is imported by game_seeker.py (and later by smart_chess_board.py for Phase 2).

Usage (standalone test on any machine):
    import asyncio
    from chesscom_browser import launch, is_logged_in, close
    async def test():
        pw, ctx, page = await launch(headless=False)
        print("Logged in:", await is_logged_in(page))
        await close(pw, ctx)
    asyncio.run(test())
"""

import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from chesscom_config import (
    USER_DATA_DIR,
    CHESS_COM_PLAY_URL,
    BROWSER_VIEWPORT,
    GAME_SEARCH_TIMEOUT,
    TIME_CONTROL,
    SELECTORS,
)

# =============================================================================
# BROWSER LIFECYCLE
# =============================================================================

async def launch(headless=True):
    """
    Launch a persistent Chromium browser context.
    Cookies, localStorage, and sessionStorage are saved in USER_DATA_DIR
    and reused on subsequent runs (no re-login needed).

    Returns: (playwright_instance, browser_context, page)
    """
    pw = await async_playwright().start()

    context = await pw.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR,
        headless=headless,
        viewport=BROWSER_VIEWPORT,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )

    # Use existing page if the context restored one, otherwise create new
    page = context.pages[0] if context.pages else await context.new_page()

    return pw, context, page


async def close(pw, context):
    """Clean shutdown: close context (saves session) and stop Playwright."""
    try:
        await context.close()
    except Exception:
        pass
    try:
        await pw.stop()
    except Exception:
        pass

# =============================================================================
# LOGIN
# =============================================================================

async def is_logged_in(page):
    """
    Check if the user is currently logged in to chess.com.
    Navigates to the play page if not already there, then looks for the
    logged-in indicator element.

    Returns: True if logged in, False otherwise.
    """
    current_url = page.url
    if "chess.com" not in current_url:
        await page.goto(CHESS_COM_PLAY_URL, wait_until="domcontentloaded")

    try:
        await page.wait_for_selector(
            SELECTORS["logged_in_indicator"],
            state="visible",
            timeout=5000,
        )
        return True
    except PlaywrightTimeout:
        return False


async def prompt_login(page):
    """
    Navigate to chess.com and wait for the user to log in manually.
    The user sees the browser window (via X11 forwarding or local display)
    and enters their credentials. Once done, they press Enter in the terminal.

    Returns: True if login succeeded after user confirmation, False otherwise.
    """
    await page.goto(CHESS_COM_PLAY_URL, wait_until="domcontentloaded")

    print()
    print("=" * 50)
    print("  FIRST-TIME LOGIN")
    print("=" * 50)
    print()
    print("A browser window should be visible.")
    print("Please log in to chess.com manually.")
    print()
    print("Once you are logged in, come back here")
    print("and press ENTER to continue...")
    print()

    # Wait for Enter without blocking the event loop
    await asyncio.get_event_loop().run_in_executor(None, input)

    # Verify login succeeded
    logged_in = await is_logged_in(page)
    if logged_in:
        print("Login successful! Session saved.")
    else:
        print("WARNING: Login could not be verified.")
        print("Check the browser window and try again.")

    return logged_in

# =============================================================================
# GAME SEEKING
# =============================================================================

async def navigate_to_play(page):
    """Navigate to the chess.com play page if not already there."""
    if "/play" not in page.url:
        await page.goto(CHESS_COM_PLAY_URL, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")


async def seek_game(page):
    """
    Start searching for a game on chess.com.
    Navigates to the play page, selects the time control, and clicks Play.

    Returns: True if the search was initiated, False on error.
    """
    try:
        await navigate_to_play(page)

        # Select time control (if the selector is configured)
        if SELECTORS["time_control_button"] != "PLACEHOLDER":
            try:
                await page.click(SELECTORS["time_control_button"], timeout=5000)
            except PlaywrightTimeout:
                print("WARNING: Could not find time control button, "
                      "proceeding with default.")

        # Click Play
        await page.click(SELECTORS["play_button"], timeout=10000)
        print("Searching for a game...")
        return True

    except PlaywrightTimeout:
        print("ERROR: Could not find the Play button on chess.com.")
        return False
    except Exception as e:
        print(f"ERROR: Failed to seek game: {e}")
        return False


async def wait_for_game(page, timeout_ms=None):
    """
    Wait for a game to start (board container becomes visible).

    Returns: True if a game was found, False on timeout.
    """
    if timeout_ms is None:
        timeout_ms = GAME_SEARCH_TIMEOUT

    try:
        await page.wait_for_selector(
            SELECTORS["board_container"],
            state="visible",
            timeout=timeout_ms,
        )
        return True
    except PlaywrightTimeout:
        print("Search timed out — no game found.")
        return False


async def cancel_search(page):
    """Cancel an active game search by clicking the cancel button."""
    try:
        await page.click(SELECTORS["cancel_search"], timeout=5000)
        print("Search cancelled.")
        return True
    except PlaywrightTimeout:
        print("WARNING: Could not find cancel button.")
        return False

# =============================================================================
# GAME STATE DETECTION
# =============================================================================

async def detect_my_color(page):
    """
    Detect whether the player is White or Black in the current game.
    Checks if the board element has the "flipped" class (= playing as Black).

    Returns: "white" or "black"
    """
    flipped_class = SELECTORS["board_flipped_class"]

    try:
        is_flipped = await page.evaluate(f"""
            () => {{
                const board = document.querySelector('{SELECTORS["board_container"]}');
                if (!board) return false;
                return board.classList.contains('{flipped_class}');
            }}
        """)
        color = "black" if is_flipped else "white"
        print(f"Game found! Playing as {color.upper()}.")
        return color
    except Exception as e:
        print(f"WARNING: Could not detect color ({e}), defaulting to white.")
        return "white"
