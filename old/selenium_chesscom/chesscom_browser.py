"""
chesscom_browser.py

Selenium-based browser automation for chess.com.
Handles session persistence, login detection, game seeking, and color detection.

This module is synchronous and has no GPIO/LED knowledge.
It is imported by game_seeker.py (and later by smart_chess_board.py for Phase 2).

Usage (standalone test on any machine):
    from chesscom_browser import launch, is_logged_in, close
    driver = launch(headless=False)
    print("Logged in:", is_logged_in(driver))
    close(driver)

Requires: sudo apt install chromium-chromedriver && pip3 install selenium
"""

import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException,
)

from chesscom_config import (
    USER_DATA_DIR,
    CHESS_COM_PLAY_URL,
    WINDOW_SIZE,
    GAME_SEARCH_TIMEOUT,
    POLL_INTERVAL,
    TIME_CONTROL,
    SELECTORS,
)

# =============================================================================
# BROWSER LIFECYCLE
# =============================================================================

def launch(headless=True):
    """
    Launch a Chromium browser with a persistent user profile.
    Cookies and localStorage are saved in USER_DATA_DIR and reused
    on subsequent runs (no re-login needed).

    Returns: webdriver.Chrome instance
    """
    # Resolve to absolute path so Chromium doesn't get confused
    user_data_dir = os.path.abspath(USER_DATA_DIR)

    options = Options()
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument(f"--window-size={WINDOW_SIZE}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--shm-size=1gb")

    # RPi-friendly flags — prevent white screen / GPU stalls
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-translate")
    options.add_argument("--no-first-run")
    options.add_argument("--ignore-certificate-errors")

    if headless:
        options.add_argument("--headless=new")

    # Suppress "Chrome is being controlled by automated software" bar
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Use the system chromedriver (installed via apt)
    service = Service("/usr/bin/chromedriver")

    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(2)  # Short implicit wait for find_element calls

    return driver


def close(driver):
    """Clean shutdown: close browser and free resources."""
    try:
        driver.quit()
    except Exception:
        pass

# =============================================================================
# LOGIN
# =============================================================================

def is_logged_in(driver):
    """
    Check if the user is currently logged in to chess.com.
    Navigates to the play page if not already there, then looks for the
    logged-in indicator element.

    Returns: True if logged in, False otherwise.
    """
    if "chess.com" not in driver.current_url:
        driver.get(CHESS_COM_PLAY_URL)

    try:
        WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, SELECTORS["logged_in_indicator"])
            )
        )
        return True
    except TimeoutException:
        return False


def prompt_login():
    """
    Instruct the user to log in via a plain Chromium session (not Selenium).
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

def navigate_to_play(driver):
    """Navigate to the chess.com play page if not already there."""
    if "/play" not in driver.current_url:
        driver.get(CHESS_COM_PLAY_URL)
        # Wait for page to be reasonably loaded
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )


def seek_game(driver):
    """
    Start searching for a game on chess.com.
    Navigates to the play page, selects the time control, and clicks Play.

    Returns: True if the search was initiated, False on error.
    """
    try:
        navigate_to_play(driver)

        # Select time control (if the selector is configured)
        if SELECTORS["time_control_button"] != "PLACEHOLDER":
            try:
                btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, SELECTORS["time_control_button"])
                    )
                )
                btn.click()
            except TimeoutException:
                print("WARNING: Could not find time control button, "
                      "proceeding with default.")

        # Click Play
        play_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, SELECTORS["play_button"])
            )
        )
        play_btn.click()
        print("Searching for a game...")
        return True

    except TimeoutException:
        print("ERROR: Could not find the Play button on chess.com.")
        return False
    except Exception as e:
        print(f"ERROR: Failed to seek game: {e}")
        return False


def wait_for_game(driver, timeout=None, cancel_event=None):
    """
    Wait for a game to start (board container becomes visible).
    Polls at POLL_INTERVAL. Can be cancelled by setting cancel_event.

    Args:
        driver: Selenium WebDriver instance
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
            driver.find_element(By.CSS_SELECTOR, selector)
            return True
        except NoSuchElementException:
            pass

        time.sleep(POLL_INTERVAL)

    print("Search timed out — no game found.")
    return False


def cancel_search(driver):
    """Cancel an active game search by clicking the cancel button."""
    try:
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, SELECTORS["cancel_search"])
            )
        )
        btn.click()
        print("Search cancelled.")
        return True
    except TimeoutException:
        print("WARNING: Could not find cancel button.")
        return False

# =============================================================================
# GAME STATE DETECTION
# =============================================================================

def detect_my_color(driver):
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
        board = driver.find_element(By.CSS_SELECTOR, board_selector)
        element_classes = board.get_attribute("class").split()
        is_flipped = all(cls in element_classes for cls in flipped_classes)
        color = "black" if is_flipped else "white"
        print(f"Game found! Playing as {color.upper()}.")
        return color
    except Exception as e:
        print(f"WARNING: Could not detect color ({e}), defaulting to white.")
        return "white"
