#!/usr/bin/env python3
"""
integration_test.py

Tests that all CSS selectors in chesscom_config.py resolve on chess.com.
Launches a visible Playwright browser, navigates to the play page,
and checks each selector one by one with visual LED feedback.

  GREEN flash  = selector found
  RED flash    = selector NOT found

Requires a saved login session (run game_seeker.py --first-login first).

Usage:
  sudo python3 integration_test.py              # headless (default)
  sudo python3 integration_test.py --visible    # visible browser for debugging
"""

import sys
import os
import time

# Add playwright_chesscom to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "playwright_chesscom"))

from chesscom_config import (
    SELECTORS,
    CHESS_COM_PLAY_URL,
    LED_PIN,
    NUM_LEDS,
    LED_BRIGHTNESS,
    LED_FREQ_HZ,
    LED_DMA,
    LED_INVERT,
    LED_CHANNEL,
)
from chesscom_browser import launch, close, is_logged_in

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
# SELECTOR TESTS
# =============================================================================

# Selectors to test and what page state they need.
# "play_page" = just needs to be on /play/online while logged in.
# "searching" = needs an active game search (tested separately).
# "in_game"   = needs a game in progress (tested separately).
# "class"     = not a CSS selector, just a class name check.
SELECTOR_TESTS = [
    ("logged_in_indicator", "play_page", "Logged-in indicator (avatar/profile link)"),
    ("time_control_show_options", "dropdown", "Time control dropdown trigger"),
    ("time_control_button", "dropdown", "Time control option button"),
    ("play_button", "play_page", "Play button"),
    ("searching_indicator", "searching", "Searching indicator toast"),
    ("cancel_search", "searching", "Cancel search button"),
    ("board_container", "in_game", "Board container"),
    ("board_flipped_class", "class", "Board flipped class name (not a selector)"),
]


def test_selector(page, selector_name):
    """Check if a selector is present on the current page right now. Returns True/False."""
    selector = SELECTORS[selector_name]
    if selector == "PLACEHOLDER":
        return False
    try:
        el = page.query_selector(selector)
        return el is not None
    except Exception:
        return False


def run_tests(page, strip, visible):
    results = {}
    passed = 0
    failed = 0
    skipped = 0

    total_testable = sum(
        1 for _, phase, _ in SELECTOR_TESTS if phase in ("play_page", "dropdown")
    )

    print()
    print("=" * 55)
    print("  Phase 1: Play page selectors")
    print("=" * 55)
    print()

    # Navigate to play page
    print("Navigating to chess.com/play/online ...")
    page.goto(CHESS_COM_PLAY_URL)
    page.wait_for_load_state("load")
    time.sleep(2)  # let JS settle

    for name, phase, desc in SELECTOR_TESTS:
        selector_val = SELECTORS[name]

        if phase == "class":
            print(f"  [ SKIP ] {name}")
            print(f"           {desc}")
            print(
                f'           Value: "{selector_val}" (class name, not tested as selector)'
            )
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

        wait_for_button(f"Press button to test: {name}")

        # For dropdown: open the time control menu first
        if phase == "dropdown":
            try:
                print("  Opening time control dropdown...")
                page.click(SELECTORS["time_control_show_options"])
                time.sleep(0.5)
            except Exception:
                pass  # might already be open or not needed

        ok = test_selector(page, name)
        tag = "PASS" if ok else "FAIL"
        results[name] = tag

        if ok:
            passed += 1
        else:
            failed += 1

        icon = " OK " if ok else "FAIL"
        print(f"  [ {icon} ] {name}")
        print(f"           {desc}")
        print(f"           Selector: {selector_val[:70]}")
        flash_result(strip, ok)
        print()

    # --- Phase 2: searching selectors ---
    print("=" * 55)
    print("  Phase 2: Searching selectors")
    print("=" * 55)
    print()
    wait_for_button("Press button to start Phase 2 (will click Play)...")

    print("  Clicking Play to start a search...")

    search_started = False
    try:
        page.click(SELECTORS["play_button"])
        time.sleep(2)
        search_started = True
    except Exception as e:
        print(f"  Could not click Play: {e}")
        print()

    if search_started:
        for name, phase, desc in SELECTOR_TESTS:
            if phase != "searching":
                continue

            wait_for_button(f"Press button to test: {name}")

            ok = test_selector(page, name)
            tag = "PASS" if ok else "FAIL"
            results[name] = tag

            if ok:
                passed += 1
            else:
                failed += 1

            icon = " OK " if ok else "FAIL"
            print(f"  [ {icon} ] {name}")
            print(f"           {desc}")
            print(f"           Selector: {SELECTORS[name][:70]}")
            flash_result(strip, ok)
            print()

        # Cancel the search so we don't actually start a game
        print("  Cancelling search...")
        try:
            page.click(SELECTORS["cancel_search"])
            time.sleep(1)
        except Exception:
            print(
                "  WARNING: Could not cancel search — you may need to cancel manually."
            )
    else:
        for name, phase, _ in SELECTOR_TESTS:
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
    for name, phase, _ in SELECTOR_TESTS:
        if phase == "in_game" and name not in results:
            results[name] = "SKIP"
            skipped += 1
    print()

    # --- Summary ---
    print("=" * 55)
    print("  SUMMARY")
    print("=" * 55)
    print()
    for name, phase, desc in SELECTOR_TESTS:
        tag = results.get(name, "SKIP")
        print(f"  [{tag:^4}]  {name}")
    print()
    print(f"  Passed: {passed}  Failed: {failed}  Skipped: {skipped}")
    print()

    if failed == 0 and passed > 0:
        print("  All testable selectors found!")
        flash_all_pass(strip)
    elif failed > 0:
        print("  Some selectors are broken — update chesscom_config.py SELECTORS.")

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
    print("  Integration Test — CSS Selectors")
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
