#!/usr/bin/env python3
"""
integration_test.py

Tests that all locators in chesscom_config.py resolve on chess.com.
Launches a Playwright browser, navigates to the play page,
and checks each locator one by one with visual LED feedback.

  GREEN flash  = locator found
  RED flash    = locator NOT found

Requires a saved login session (run game_seeker.py --first-login first).

Usage:
  sudo python3 integration_test.py              # headless (default)
  sudo python3 integration_test.py --visible    # visible browser for debugging
"""

import sys
import os
import time
import re

# Add playwright_chesscom to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "playwright_chesscom"))

from chesscom_config import (
    LOCATORS,
    TIME_CONTROL,
    CHESS_COM_PLAY_URL,
    LED_PIN,
    NUM_LEDS,
    LED_BRIGHTNESS,
    LED_FREQ_HZ,
    LED_DMA,
    LED_INVERT,
    LED_CHANNEL,
)
from chesscom_browser import (
    launch,
    close,
    is_logged_in,
    read_board,
    print_board,
    make_move,
)

# Try to import hardware support — gracefully degrade on non-Pi machines
try:
    from rpi_ws281x import PixelStrip, Color

    HAS_LEDS = True
except ImportError:
    HAS_LEDS = False

# =============================================================================
# LED HELPERS
# =============================================================================


def init_strip():
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


def flash_result(strip, success):
    """Flash green for pass, red for fail."""
    if not strip:
        return
    color = Color(0, 255, 0) if success else Color(255, 0, 0)
    for _ in range(2):
        for i in range(NUM_LEDS):
            strip.setPixelColor(i, color)
        strip.show()
        time.sleep(0.25)
        all_leds_off(strip)
        time.sleep(0.15)


def flash_all_pass(strip):
    """Celebratory green flash when all selectors pass."""
    if not strip:
        return
    for _ in range(5):
        for i in range(NUM_LEDS):
            strip.setPixelColor(i, Color(0, 255, 0))
        strip.show()
        time.sleep(0.15)
        all_leds_off(strip)
        time.sleep(0.1)


# =============================================================================
# INPUT HELPER
# =============================================================================


def wait_for_button(prompt="Press Enter to continue..."):
    """Wait for Enter key press."""
    input(f"  >> {prompt}")
    print("  PRESSED")


# =============================================================================
# LOCATOR TESTS
# =============================================================================

# Locators to test and what page state they need.
# "play_page" = just needs to be on /play/online while logged in.
# "dropdown"  = needs the time control dropdown open.
# "searching" = needs an active game search (tested separately).
# "in_game"   = needs a game in progress (tested separately).
# "class"     = class name check, not a locator test.
#
# Locator key "_time_control_dynamic" is a special case: it uses TIME_CONTROL
# as the button label rather than a key in LOCATORS.
LOCATOR_TESTS = [
    ("time_control_show_options", "dropdown", "Time control dropdown trigger"),
    (
        "_time_control_dynamic",
        "play_page",
        f'Time control option button ("{TIME_CONTROL}")',
    ),
    ("play_button", "play_page", "Play button"),
    ("cancel_search", "searching", "Cancel search button"),
    ("board_container", "in_game", "Board container"),
    ("board_flipped_class", "class", "Board flipped class name (not a locator)"),
]


def test_locator(page, locator_key, timeFormat=TIME_CONTROL):
    """
    Check if a locator resolves on the current page. Returns True/False.

    CSS selectors (board_container, starting with "#") use query_selector.
    Everything else uses get_by_role("button", name=...).
    """

    if locator_key == "_time_control_dynamic":
        try:
            locator = page.get_by_role("button", name=TIME_CONTROL, exact=True)
            count = locator.count()
            locator.click()
            print_board(read_board(page))
            return count > 0
        except Exception:
            return False

    if locator_key == "time_control_show_options":
        val = timeFormat
    else:
        val = LOCATORS[locator_key]

    # if locator_key == "cancel_search":
    #     print("Canceling search...")
    #     locator = page.get_by_role("button", name=LOCATORS["cancel_search"])
    #     count = locator.count()
    #     locator.nth(1).click()
    #     return count > 0

    if val.startswith("#") or val.startswith("."):
        try:
            return page.query_selector(val) is not None
        except Exception:
            return False
    else:
        try:
            return page.get_by_role("button", name=val).count() > 0
        except Exception:
            return False


def run_tests(page, strip, visible):
    results = {}
    passed = 0
    failed = 0
    skipped = 0

    print()
    print("=" * 55)
    print("  Phase 1: Play page locators")
    print("=" * 55)
    print()

    # Navigate to play page
    # print("Navigating to chess.com/play/online ...")
    # page.goto(CHESS_COM_PLAY_URL)
    # page.wait_for_load_state("load")
    # time.sleep(2)  # let JS settle

    for name, phase, desc in LOCATOR_TESTS:
        if phase == "class":
            val = LOCATORS[name]
            print(f"  [ SKIP ] {name}")
            print(f"           {desc}")
            print(f'           Value: "{val}" (class name, not tested as locator)')
            skipped += 1
            results[name] = "SKIP"
            print()
            continue

        if phase in ("searching", "in_game"):
            print(f"  [ SKIP ] {name}")
            print(f"           {desc}")
            print(f"           Requires active {phase} state — see Phase 2/3 below")
            skipped += 1
            results[name] = "SKIP"
            print()
            continue

        wait_for_button(f"Press button to test: {name}, {phase}")

        # For dropdown tests: open the time control menu first
        if phase == "dropdown":
            try:
                print("  Opening time control dropdown...")
                # Regex capturing things like 10 min (Rapid) 3 min (Blitz) 2 | 1 (Blitz)
                locator = page.get_by_text(
                    re.compile(r"^(?:\d+\s*min|\d+\s*\|\s*\d+)\s*\([^)]*\)$")
                )
                locator.click()
                timeFormat = locator.inner_text()
                print(timeFormat)
                # page.get_by_role(
                #     "button", name=LOCATORS["time_control_show_options"]
                # ).click()
                time.sleep(0.5)
                ok = test_locator(page, name, timeFormat)
            except Exception:
                pass  # might already be open or not needed

        if phase != "dropdown":
            ok = test_locator(page, name)
        tag = "PASS" if ok else "FAIL"
        results[name] = tag

        if ok:
            passed += 1
        else:
            failed += 1

        locator_display = (
            TIME_CONTROL if name == "_time_control_dynamic" else LOCATORS.get(name, "")
        )
        icon = " OK " if ok else "FAIL"
        print(f"  [ {icon} ] {name}")
        print(f"           {desc}")
        print(f"           Locator: {str(locator_display)[:70]}")
        flash_result(strip, ok)
        print()

    # --- Phase 2: searching locators ---
    print("=" * 55)
    print("  Phase 2: Searching locators")
    print("=" * 55)
    print()
    wait_for_button("Press button to start Phase 2 (will click Play)...")

    print("  Clicking Play to start a search...")

    search_started = False
    try:
        page.get_by_role("button", name=LOCATORS["play_button"], exact=True).click()
        time.sleep(2)
        search_started = True
    except Exception as e:
        print(f"  Could not click Play: {e}")
        print()

    if search_started:
        for name, phase, desc in LOCATOR_TESTS:
            if phase != "searching":
                continue

            wait_for_button(f"Press button to test: {name}")

            ok = test_locator(page, name)
            tag = "PASS" if ok else "FAIL"
            results[name] = tag

            if ok:
                passed += 1
            else:
                failed += 1

            icon = " OK " if ok else "FAIL"
            print(f"  [ {icon} ] {name}")
            print(f"           {desc}")
            print(f"           Locator: {LOCATORS[name][:70]}")
            flash_result(strip, ok)
            print()

        print("Making move")
        make_move(page, 5, 2, 5, 4, "white")
        # Cancel the search so we don't actually start a game
        print("  Cancelling search...")
        try:
            page.get_by_role("button", name=LOCATORS["cancel_search"]).nth(1)
            time.sleep(0.5)
        except Exception:
            print(
                "  WARNING: Could not cancel search — you may need to cancel manually."
            )
    else:
        for name, phase, _ in LOCATOR_TESTS:
            if phase == "searching":
                results[name] = "SKIP"
                skipped += 1
                print(f"  [ SKIP ] {name} (search not started)")

    print()

    # --- Phase 3: in-game selectors ---
    print("=" * 55)
    print("  Phase 3: In-game selectors")
    print("=" * 55)
    print()
    print("  Skipped — requires an active game.")
    print("  board_container and board_flipped_class need a game in progress.")
    for name, phase, _ in LOCATOR_TESTS:
        if phase == "in_game" and name not in results:
            results[name] = "SKIP"
            skipped += 1
    print()

    # --- Summary ---
    print("=" * 55)
    print("  SUMMARY")
    print("=" * 55)
    print()
    for name, phase, desc in LOCATOR_TESTS:
        tag = results.get(name, "SKIP")
        print(f"  [{tag:^4}]  {name}")
    print()
    print(f"  Passed: {passed}  Failed: {failed}  Skipped: {skipped}")
    print()

    if failed == 0 and passed > 0:
        print("  All testable locators found!")
        flash_all_pass(strip)
    elif failed > 0:
        print("  Some locators are broken — update chesscom_config.py LOCATORS.")

    return failed


# =============================================================================
# MAIN
# =============================================================================


def main():
    visible = "--visible" in sys.argv
    headless = not visible

    strip = init_strip()

    print()
    print("========================================")
    print("  Integration Test — Locators")
    print("========================================")
    print()
    print(f"Mode: {'visible' if visible else 'headless'}")
    print("Press Enter before each test step to advance.")
    print()

    print("Launching browser...")
    context, page = launch(headless=headless)

    try:
        # Check login first
        if not is_logged_in(page):
            print("ERROR: Not logged in.")
            print("Run: sudo python3 playwright_chesscom/game_seeker.py --first-login")
            flash_result(strip, False)
            return

        print("Logged in to chess.com.")
        failed = run_tests(page, strip, visible)
        sys.exit(1 if failed > 0 else 0)

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        all_leds_off(strip)
        close(context)
        print("Cleanup complete.")


if __name__ == "__main__":
    main()
