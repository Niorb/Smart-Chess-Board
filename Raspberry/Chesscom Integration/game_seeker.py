#!/usr/bin/env python3
"""
game_seeker.py

Main entry point for the chess.com game seeker (Phase 1).
Wires together: GPIO button -> Selenium browser -> WS2812B LED feedback.

Press the button to seek a game on chess.com.
LEDs flash to indicate the result (white/black/cancelled/error).

Usage:
  sudo pigpiod
  sudo python3 game_seeker.py               # normal (headless browser)
  sudo python3 game_seeker.py --first-login  # first time (shows browser on display)

Requires:
  sudo apt install chromium-chromedriver
  sudo pip3 install selenium pigpio rpi-ws281x
"""

import sys
import time
import threading
import pigpio
from rpi_ws281x import PixelStrip, Color

from chesscom_config import (
    # GPIO
    BUTTON_PIN, BUTTON_DEBOUNCE_MS,
    # LED
    BOARD_ROWS, BOARD_COLS, LED_PIN, NUM_LEDS, LED_BRIGHTNESS,
    LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_CHANNEL,
    # LED patterns
    COLOR_CONNECTING, COLOR_CONNECTED,
    COLOR_SEARCHING, COLOR_FOUND_WHITE, COLOR_FOUND_BLACK,
    COLOR_CANCELLED, COLOR_ERROR,
    CONNECT_PULSE_STEP_S, SEARCH_CHASE_DELAY_S,
    FLASH_ON_S, FLASH_OFF_S,
    FLASH_COUNT_FOUND, FLASH_COUNT_ERROR, FLASH_COUNT_CANCEL, FLASH_COUNT_CONNECT,
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
    For a 4x4 board: top row L->R, right col top->bottom,
    bottom row R->L, left col bottom->top.
    """
    indices = []
    for col in range(BOARD_COLS):
        indices.append(get_led_index(0, col))
    for row in range(1, BOARD_ROWS):
        indices.append(get_led_index(row, BOARD_COLS - 1))
    for col in range(BOARD_COLS - 2, -1, -1):
        indices.append(get_led_index(BOARD_ROWS - 1, col))
    for row in range(BOARD_ROWS - 2, 0, -1):
        indices.append(get_led_index(row, 0))
    return indices


# =============================================================================
# LED ANIMATIONS
# =============================================================================

def animate_connecting(strip, stop_event):
    """
    Orange breathing pulse on all LEDs while the browser launches.
    Runs in a background thread. Stops when stop_event is set.
    Fades brightness up and down smoothly for a "heartbeat" effect.
    """
    r, g, b = COLOR_CONNECTING
    steps = 20  # Number of brightness steps per half-cycle

    while not stop_event.is_set():
        # Fade in
        for i in range(steps + 1):
            if stop_event.is_set():
                break
            frac = i / steps
            cr, cg, cb = int(r * frac), int(g * frac), int(b * frac)
            for led in range(NUM_LEDS):
                strip.setPixelColor(led, Color(cr, cg, cb))
            strip.show()
            stop_event.wait(CONNECT_PULSE_STEP_S)
        # Fade out
        for i in range(steps, -1, -1):
            if stop_event.is_set():
                break
            frac = i / steps
            cr, cg, cb = int(r * frac), int(g * frac), int(b * frac)
            for led in range(NUM_LEDS):
                strip.setPixelColor(led, Color(cr, cg, cb))
            strip.show()
            stop_event.wait(CONNECT_PULSE_STEP_S)

    all_leds_off(strip)


def signal_connected(strip):
    """Flash green to indicate successful connection and login."""
    flash_leds(strip, COLOR_CONNECTED, FLASH_COUNT_CONNECT)


def animate_search(strip, stop_event):
    """
    Blue chase around the board perimeter while searching.
    Runs in a background thread. Stops when stop_event is set.
    """
    perimeter = get_perimeter_indices()
    r, g, b = COLOR_SEARCHING

    while not stop_event.is_set():
        for idx in perimeter:
            if stop_event.is_set():
                break
            all_leds_off(strip)
            strip.setPixelColor(idx, Color(r, g, b))
            strip.show()
            stop_event.wait(SEARCH_CHASE_DELAY_S)  # Sleep but wake on stop

    all_leds_off(strip)


def flash_leds(strip, rgb, count):
    """Flash all LEDs a given color a given number of times."""
    for _ in range(count):
        all_leds_color(strip, rgb)
        time.sleep(FLASH_ON_S)
        all_leds_off(strip)
        time.sleep(FLASH_OFF_S)


def signal_game_found(strip, color):
    """Flash LEDs to indicate game found and assigned color."""
    if color == "white":
        flash_leds(strip, COLOR_FOUND_WHITE, FLASH_COUNT_FOUND)
    else:
        flash_leds(strip, COLOR_FOUND_BLACK, FLASH_COUNT_FOUND)


def signal_cancelled(strip):
    """Flash LEDs to indicate search cancelled."""
    flash_leds(strip, COLOR_CANCELLED, FLASH_COUNT_CANCEL)


def signal_error(strip):
    """Flash LEDs to indicate an error."""
    flash_leds(strip, COLOR_ERROR, FLASH_COUNT_ERROR)


# =============================================================================
# MAIN
# =============================================================================

def run(first_login=False):
    """Main state machine: IDLE -> SEEKING -> GAME_FOUND -> IDLE."""

    # ---- pigpio setup ----
    pi = pigpio.pi()
    if not pi.connected:
        print("ERROR: Could not connect to pigpiod. Run: sudo pigpiod")
        return

    pi.set_mode(BUTTON_PIN, pigpio.INPUT)
    pi.set_pull_up_down(BUTTON_PIN, pigpio.PUD_UP)

    # Button event — set by pigpio callback, consumed by main loop
    button_event = threading.Event()
    last_press_tick = [0]

    def on_button_press(gpio, level, tick):
        dt = pigpio.tickDiff(last_press_tick[0], tick)
        if dt < BUTTON_DEBOUNCE_MS * 1000:  # tickDiff is in microseconds
            return
        last_press_tick[0] = tick
        print(last_press_tick[0])
        button_event.set()

    cb = pi.callback(BUTTON_PIN, pigpio.FALLING_EDGE, on_button_press)

    # ---- LED setup ----
    strip = PixelStrip(NUM_LEDS, LED_PIN, LED_FREQ_HZ, LED_DMA,
                       LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    strip.begin()
    all_leds_off(strip)

    # ---- Browser setup ----
    if first_login:
        # Let the user log in via a plain Chromium session first
        prompt_login()

    # Start connecting animation while the browser launches
    stop_connect_anim = threading.Event()
    connect_thread = threading.Thread(
        target=animate_connecting, args=(strip, stop_connect_anim), daemon=True
    )
    connect_thread.start()

    print("Launching browser (headless)...")
    try:
        driver = launch(headless=True)
    except Exception as e:
        stop_connect_anim.set()
        connect_thread.join(timeout=2)
        print(f"ERROR: Browser failed to launch: {e}")
        signal_error(strip)
        cb.cancel()
        pi.stop()
        return

    try:
        # ---- Check login ----
        print("Checking session...")
        logged_in = is_logged_in(driver)

        # Stop connecting animation
        stop_connect_anim.set()
        connect_thread.join(timeout=2)

        if not logged_in:
            print("ERROR: Not logged in.")
            print("Run with --first-login and follow the instructions.")
            signal_error(strip)
            return

        signal_connected(strip)
        print()
        print("Connected! Press the button to seek a game.")
        print("Press Ctrl+C to exit.")
        print()

        # ---- Main loop ----
        while True:
            # IDLE — wait for button press
            button_event.clear()
            button_event.wait()

            # CHECK_LOGIN
            if not is_logged_in(driver):
                print("Session expired! Re-run with --first-login.")
                signal_error(strip)
                continue

            # SEEKING
            success = seek_game(driver)
            if not success:
                signal_error(strip)
                continue

            # Start search LED animation in background thread
            stop_anim = threading.Event()
            anim_thread = threading.Thread(
                target=animate_search, args=(strip, stop_anim), daemon=True
            )
            anim_thread.start()

            # Wait for game, allowing cancellation via button
            button_event.clear()
            result = wait_for_game(driver, cancel_event=button_event)

            # Stop LED animation
            stop_anim.set()
            anim_thread.join(timeout=2)

            if result is True:
                # GAME_FOUND
                color = detect_my_color(driver)
                signal_game_found(strip, color)
                print(f"Game started — playing as {color.upper()}.")
                print("(Phase 2 will add move sync. For now, play on chess.com.)")
                print()
                print("Press button to seek another game when this one ends.")
            elif result is None:
                # CANCELLED (button pressed during search)
                cancel_search(driver)
                signal_cancelled(strip)
            else:
                # TIMEOUT / ERROR
                signal_error(strip)

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        all_leds_off(strip)
        cb.cancel()
        pi.stop()
        close(driver)
        print("Cleanup complete.")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    first_login = "--first-login" in sys.argv
    run(first_login=first_login)
