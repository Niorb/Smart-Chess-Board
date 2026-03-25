#!/usr/bin/env python3
"""
game_seeker.py

Main entry point for the chess.com game seeker (Phase 1).
Wires together: GPIO button → Playwright browser → WS2812B LED feedback.

Press the button to seek a game on chess.com.
LEDs flash to indicate the result (white/black/cancelled/error).

Usage:
  sudo pigpiod
  sudo python3 game_seeker.py               # normal (headless browser)
  sudo python3 game_seeker.py --first-login  # first time (shows browser via X11)

Requires: sudo pip3 install pigpio rpi-ws281x playwright
"""

import sys
import asyncio
import pigpio
from rpi_ws281x import PixelStrip, Color

from chesscom_config import (
    # GPIO
    BUTTON_PIN, BUTTON_DEBOUNCE_MS,
    # LED
    BOARD_ROWS, BOARD_COLS, LED_PIN, NUM_LEDS, LED_BRIGHTNESS,
    LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_CHANNEL,
    # LED patterns
    COLOR_SEARCHING, COLOR_FOUND_WHITE, COLOR_FOUND_BLACK,
    COLOR_CANCELLED, COLOR_ERROR,
    SEARCH_CHASE_DELAY_S, FLASH_ON_S, FLASH_OFF_S,
    FLASH_COUNT_FOUND, FLASH_COUNT_ERROR, FLASH_COUNT_CANCEL,
)
from chesscom_browser import (
    launch, close, is_logged_in, prompt_login,
    seek_game, wait_for_game, cancel_search, detect_my_color,
)

# =============================================================================
# LED HELPERS
# =============================================================================

def get_led_index(row, col):
    """Convert board [row, col] to serpentine LED strip index."""
    if row % 2 == 0:
        return row * BOARD_COLS + col
    else:
        return row * BOARD_COLS + (BOARD_COLS - 1 - col)


def all_leds_off(strip):
    """Turn off all LEDs."""
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def all_leds_color(strip, rgb):
    """Set all LEDs to the same color."""
    r, g, b = rgb
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, Color(r, g, b))
    strip.show()


def get_perimeter_indices():
    """
    Get LED indices for the board perimeter in order (clockwise).
    For a 4x4 board: top row L→R, right col top→bottom,
    bottom row R→L, left col bottom→top.
    """
    indices = []

    # Top row (row 0): left to right
    for col in range(BOARD_COLS):
        indices.append(get_led_index(0, col))

    # Right column (col BOARD_COLS-1): top+1 to bottom
    for row in range(1, BOARD_ROWS):
        indices.append(get_led_index(row, BOARD_COLS - 1))

    # Bottom row (row BOARD_ROWS-1): right-1 to left
    for col in range(BOARD_COLS - 2, -1, -1):
        indices.append(get_led_index(BOARD_ROWS - 1, col))

    # Left column (col 0): bottom-1 to top+1
    for row in range(BOARD_ROWS - 2, 0, -1):
        indices.append(get_led_index(row, 0))

    return indices


# =============================================================================
# LED ANIMATIONS (async — use asyncio.sleep so they don't block)
# =============================================================================

async def animate_search(strip):
    """
    Blue chase around the board perimeter while searching.
    Runs as a cancellable asyncio task.
    """
    perimeter = get_perimeter_indices()
    r, g, b = COLOR_SEARCHING

    try:
        while True:
            for idx in perimeter:
                all_leds_off(strip)
                strip.setPixelColor(idx, Color(r, g, b))
                strip.show()
                await asyncio.sleep(SEARCH_CHASE_DELAY_S)
    except asyncio.CancelledError:
        all_leds_off(strip)


async def flash_leds(strip, rgb, count):
    """Flash all LEDs a given color a given number of times."""
    for _ in range(count):
        all_leds_color(strip, rgb)
        await asyncio.sleep(FLASH_ON_S)
        all_leds_off(strip)
        await asyncio.sleep(FLASH_OFF_S)


async def signal_game_found(strip, color):
    """Flash LEDs to indicate game found and assigned color."""
    if color == "white":
        await flash_leds(strip, COLOR_FOUND_WHITE, FLASH_COUNT_FOUND)
    else:
        await flash_leds(strip, COLOR_FOUND_BLACK, FLASH_COUNT_FOUND)


async def signal_cancelled(strip):
    """Flash LEDs to indicate search cancelled."""
    await flash_leds(strip, COLOR_CANCELLED, FLASH_COUNT_CANCEL)


async def signal_error(strip):
    """Flash LEDs to indicate an error."""
    await flash_leds(strip, COLOR_ERROR, FLASH_COUNT_ERROR)


# =============================================================================
# STATE MACHINE
# =============================================================================

async def run(first_login=False):
    """Main state machine: IDLE → SEEKING → GAME_FOUND → IDLE."""

    # ---- pigpio setup ----
    pi = pigpio.pi()
    if not pi.connected:
        print("ERROR: Could not connect to pigpiod. Run: sudo pigpiod")
        return

    pi.set_mode(BUTTON_PIN, pigpio.INPUT)
    pi.set_pull_up_down(BUTTON_PIN, pigpio.PUD_UP)

    # Bridge pigpio button callback into asyncio
    loop = asyncio.get_event_loop()
    button_event = asyncio.Event()
    last_press_tick = [0]

    def on_button_press(gpio, level, tick):
        # Simple debounce: ignore if too soon after last press
        dt = pigpio.tickDiff(last_press_tick[0], tick)
        if dt < BUTTON_DEBOUNCE_MS * 1000:  # tickDiff is in microseconds
            return
        last_press_tick[0] = tick
        loop.call_soon_threadsafe(button_event.set)

    cb = pi.callback(BUTTON_PIN, pigpio.FALLING_EDGE, on_button_press)

    # ---- LED setup ----
    strip = PixelStrip(NUM_LEDS, LED_PIN, LED_FREQ_HZ, LED_DMA,
                       LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    strip.begin()
    all_leds_off(strip)

    # ---- Browser setup ----
    headless = not first_login
    print("Launching browser" + (" (visible for login)..." if first_login else " (headless)..."))
    pw, context, page = await launch(headless=headless)

    try:
        # ---- Check login ----
        logged_in = await is_logged_in(page)

        if not logged_in:
            if first_login:
                logged_in = await prompt_login(page)
                if not logged_in:
                    await signal_error(strip)
                    return
            else:
                print("ERROR: Not logged in. Run with --first-login to log in.")
                await signal_error(strip)
                return

        print()
        print("Ready! Press the button to seek a game.")
        print("Press Ctrl+C to exit.")
        print()

        # ---- Main loop ----
        while True:
            # IDLE — wait for button press
            button_event.clear()
            await button_event.wait()

            # CHECK_LOGIN
            if not await is_logged_in(page):
                print("Session expired! Re-run with --first-login.")
                await signal_error(strip)
                continue

            # SEEKING
            success = await seek_game(page)
            if not success:
                await signal_error(strip)
                continue

            # Start search animation alongside game wait
            search_anim = asyncio.create_task(animate_search(strip))

            # Also listen for a second button press (cancel)
            button_event.clear()
            cancel_task = asyncio.create_task(button_event.wait())

            # Wait for either: game found OR button pressed (cancel)
            game_wait = asyncio.create_task(wait_for_game(page))

            done, pending = await asyncio.wait(
                [game_wait, cancel_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Stop search animation
            search_anim.cancel()
            try:
                await search_anim
            except asyncio.CancelledError:
                pass

            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            if game_wait in done and game_wait.result():
                # GAME_FOUND
                color = await detect_my_color(page)
                await signal_game_found(strip, color)
                print(f"Game started — playing as {color.upper()}.")
                print("(Phase 2 will add move sync. For now, play on chess.com.)")
                print()
                print("Press button to seek another game when this one ends.")
            elif cancel_task in done:
                # CANCELLING
                await cancel_search(page)
                await signal_cancelled(strip)
            else:
                # TIMEOUT / ERROR
                await signal_error(strip)

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        all_leds_off(strip)
        cb.cancel()
        pi.stop()
        await close(pw, context)
        print("Cleanup complete.")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    first_login = "--first-login" in sys.argv
    asyncio.run(run(first_login=first_login))
