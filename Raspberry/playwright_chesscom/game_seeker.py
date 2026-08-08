#!/usr/bin/env python3
"""
game_seeker.py

Main entry point for the chess.com game seeker (Phase 1).
Wires together: GPIO button -> Playwright browser -> WS2812B LED feedback.

Press the button to seek a game on chess.com.
LEDs flash to indicate the result (white/black/cancelled/error).

Usage:
  sudo python3 game_seeker.py               # normal (headless browser)
  sudo python3 game_seeker.py --first-login  # first time (shows browser on display)

Requires:
  pip3 install playwright lgpio rpi-ws281x
  playwright install chromium
"""

import sys
import threading
import time

import lgpio
from chesscom_browser import (
    cancel_search,
    close,
    detect_my_color,
    do_first_login,
    is_logged_in,
    launch,
    seek_game,
    wait_for_game,
)
from chesscom_config import BUTTON_DEBOUNCE_MS, BUTTON_PIN
from led_helpers import (
    all_leds_off,
    animate_connecting,
    animate_idle,
    animate_search,
    init_strip,
    signal_cancelled,
    signal_connected,
    signal_error,
    signal_game_found,
    start_animation,
    stop_animation,
)

# =============================================================================
# MAIN
# =============================================================================


def run(first_login=False):
    """Main state machine: IDLE -> SEEKING -> GAME_FOUND -> IDLE."""

    # ---- lgpio setup ----
    try:
        h = lgpio.gpiochip_open(0)
    except lgpio.error as e:
        print(f"ERROR: Could not open GPIO chip: {e}")
        return

    # Claim button pin as input with pull-up and edge detection
    lgpio.gpio_claim_alert(h, BUTTON_PIN, lgpio.FALLING_EDGE, lgpio.SET_PULL_UP)

    # Button event — set by lgpio callback, consumed by main loop
    button_event = threading.Event()
    last_press_time = [0.0]

    def on_button_press(_chip, _gpio, _level, _tick):
        now = time.monotonic()
        dt_ms = (now - last_press_time[0]) * 1000
        print(f"button pressed, dt_ms={dt_ms}")
        if dt_ms < BUTTON_DEBOUNCE_MS:
            return
        last_press_time[0] = now
        button_event.set()

    cb = lgpio.callback(h, BUTTON_PIN, lgpio.FALLING_EDGE, on_button_press)

    # ---- LED setup ----
    strip = init_strip()
    all_leds_off(strip)

    # ---- Browser setup ----
    if first_login:
        if not do_first_login():
            signal_error(strip)
            cb.cancel()
            lgpio.gpiochip_close(h)
            return

    # Start connecting animation while the browser launches
    stop_connect_anim = threading.Event()
    connect_thread = start_animation(animate_connecting, strip, stop_connect_anim)

    print("Launching browser (headless)...")
    try:
        context, page = launch(headless=True)
    except Exception as e:
        stop_animation(stop_connect_anim, connect_thread)
        print(f"ERROR: Browser failed to launch: {e}")
        signal_error(strip)
        cb.cancel()
        lgpio.gpiochip_close(h)
        return

    # Pre-initialize so the finally block can always call .set()
    stop_idle = threading.Event()
    stop_anim = threading.Event()
    idle_thread = None
    anim_thread = None

    try:
        # ---- Check login ----
        print("Checking session...")
        logged_in = is_logged_in(page)

        # Stop connecting animation
        stop_animation(stop_connect_anim, connect_thread)

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
            # IDLE — start dim pulse to show we're online
            stop_idle = threading.Event()
            idle_thread = start_animation(animate_idle, strip, stop_idle)

            button_event.clear()
            button_event.wait()

            # Button pressed — stop idle pulse
            stop_animation(stop_idle, idle_thread)

            # CHECK_LOGIN
            if not is_logged_in(page):
                print("Session expired! Re-run with --first-login.")
                signal_error(strip)
                continue

            # SEEKING
            success = seek_game(page)
            if not success:
                signal_error(strip)
                continue

            # Start search LED animation in background thread
            stop_anim = threading.Event()
            anim_thread = start_animation(animate_search, strip, stop_anim)

            # Wait for game, allowing cancellation via button
            button_event.clear()
            result = wait_for_game(page, cancel_event=button_event)

            # Stop LED animation
            stop_animation(stop_anim, anim_thread)

            if result is True:
                # GAME_FOUND
                color = detect_my_color(page)
                signal_game_found(strip, color)
                print(f"Game started — playing as {color.upper()}.")
                print("(Phase 2 will add move sync. For now, play on chess.com.)")
                print()
                print("Press button to seek another game when this one ends.")
            elif result is None:
                # CANCELLED (button pressed during search)
                cancel_search(page)
                signal_cancelled(strip)
            else:
                # TIMEOUT / ERROR
                signal_error(strip)

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        # Stop connecting animation if it is still running (e.g. exception in is_logged_in)
        stop_connect_anim.set()
        connect_thread.join(timeout=2)
        # Stop any running LED animation threads
        stop_idle.set()
        stop_anim.set()
        if idle_thread:
            idle_thread.join(timeout=2)
        if anim_thread:
            anim_thread.join(timeout=2)
        all_leds_off(strip)
        cb.cancel()
        lgpio.gpiochip_close(h)
        close(context)
        print("Cleanup complete.")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    first_login = "--first-login" in sys.argv
    run(first_login=first_login)
