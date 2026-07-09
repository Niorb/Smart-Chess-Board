"""
led_helpers.py

Shared LED strip helpers for the chess.com Playwright integration.
Used by game_seeker.py and interactive_game.py.

All public functions accept strip=None gracefully (no-op when hardware
is unavailable), so callers on non-Pi machines work without changes.
"""

import time
import threading

from chesscom_config import (
    BOARD_ROWS,
    BOARD_COLS,
    NUM_LEDS,
    LED_PIN,
    LED_BRIGHTNESS,
    LED_FREQ_HZ,
    LED_DMA,
    LED_INVERT,
    LED_CHANNEL,
    COLOR_CONNECTING,
    COLOR_CONNECTED,
    COLOR_SEARCHING,
    COLOR_FOUND_WHITE,
    COLOR_FOUND_BLACK,
    COLOR_CANCELLED,
    COLOR_ERROR,
    COLOR_IDLE,
    IDLE_PULSE_MAX_FRAC,
    IDLE_PULSE_STEP_S,
    IDLE_PULSE_STEPS,
    CONNECT_PULSE_STEP_S,
    SEARCH_CHASE_DELAY_S,
    FLASH_ON_S,
    FLASH_OFF_S,
    FLASH_COUNT_FOUND,
    FLASH_COUNT_ERROR,
    FLASH_COUNT_CANCEL,
    FLASH_COUNT_CONNECT,
)

# Try to import LED hardware — degrades gracefully on non-Pi machines
try:
    from rpi_ws281x import PixelStrip, Color

    HAS_LEDS = True
except ImportError:
    HAS_LEDS = False

# =============================================================================
# STRIP INIT
# =============================================================================


def init_strip():
    """Initialise and return the LED strip, or None if hardware is unavailable."""
    if not HAS_LEDS:
        return None
    strip = PixelStrip(
        NUM_LEDS, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL
    )
    strip.begin()
    return strip


# =============================================================================
# BASIC HELPERS
# =============================================================================


def get_led_indices(row, col):
    """
    Convert board [row, col] to serpentine LED strip indices.
    4 rows and 8 columns, 18 LEDs per row.
    Columns 0 and 5 have 3 LEDs (offsets relative to wiring direction), others have 2.
    The 3rd LED on those columns is kept off (not returned in offsets).
    """
    base = row * 18
    
    if row % 2 == 0:
        # Even row (L-R)
        col_offsets = {
            0: [0, 1],      # offset 2 off
            1: [3, 4],
            2: [5, 6],
            3: [7, 8],
            4: [9, 10],
            5: [11, 12],    # offset 13 off
            6: [14, 15],
            7: [16, 17]
        }
        offsets = col_offsets[col]
    else:
        # Odd row (R-L)
        col_offsets = {
            7: [0, 1],
            6: [2, 3],
            5: [5, 6],      # offset 4 off
            4: [7, 8],
            3: [9, 10],
            2: [11, 12],
            1: [13, 14],
            0: [16, 17]     # offset 15 off
        }
        offsets = col_offsets[col]
        
    return [base + o for o in offsets]


def all_leds_off(strip):
    """Turn off all LEDs."""
    if not strip:
        return
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def all_leds_color(strip, rgb):
    """Set all LEDs to the same color."""
    if not strip:
        return
    r, g, b = rgb
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, Color(r, g, b))
    strip.show()


def get_perimeter_indices():
    """
    Get LED indices for the board perimeter in order (clockwise).
    Returns a list of lists (each inner list contains LEDs for one square).
    """
    perimeter_squares = []
    # Top row L->R
    for col in range(BOARD_COLS):
        perimeter_squares.append(get_led_indices(0, col))
    # Right col top->bottom
    for row in range(1, BOARD_ROWS):
        perimeter_squares.append(get_led_indices(row, BOARD_COLS - 1))
    # Bottom row R->L
    for col in range(BOARD_COLS - 2, -1, -1):
        perimeter_squares.append(get_led_indices(BOARD_ROWS - 1, col))
    # Left col bottom->top
    for row in range(BOARD_ROWS - 2, 0, -1):
        perimeter_squares.append(get_led_indices(row, 0))
    return perimeter_squares


def flash_leds(strip, rgb, count):
    """Flash all LEDs a given color a given number of times."""
    if not strip:
        return
    for _ in range(count):
        all_leds_color(strip, rgb)
        time.sleep(FLASH_ON_S)
        all_leds_off(strip)
        time.sleep(FLASH_OFF_S)


# =============================================================================
# ANIMATIONS (run in background threads)
# =============================================================================


def animate_connecting(strip, stop_event):
    """
    Orange breathing pulse on all LEDs while the browser launches.
    Runs in a background thread. Stops when stop_event is set.
    """
    if not strip:
        return
    r, g, b = COLOR_CONNECTING
    steps = 20

    while not stop_event.is_set():
        for i in range(steps + 1):
            if stop_event.is_set():
                break
            frac = i / steps
            cr, cg, cb = int(r * frac), int(g * frac), int(b * frac)
            for led in range(NUM_LEDS):
                strip.setPixelColor(led, Color(cr, cg, cb))
            strip.show()
            stop_event.wait(CONNECT_PULSE_STEP_S)
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


def animate_search(strip, stop_event):
    """
    Blue chase around the board perimeter while searching.
    Runs in a background thread. Stops when stop_event is set.
    """
    if not strip:
        return
    perimeter_squares = get_perimeter_indices()
    r, g, b = COLOR_SEARCHING

    while not stop_event.is_set():
        for indices in perimeter_squares:
            if stop_event.is_set():
                break
            all_leds_off(strip)
            for idx in indices:
                strip.setPixelColor(idx, Color(r, g, b))
            strip.show()
            stop_event.wait(SEARCH_CHASE_DELAY_S)

    all_leds_off(strip)


def animate_idle(strip, stop_event):
    """
    Very dim white breathing pulse while idle to confirm the system is online.
    Runs in a background thread. Stops when stop_event is set.
    """
    if not strip:
        return
    r, g, b = COLOR_IDLE

    while not stop_event.is_set():
        for i in range(IDLE_PULSE_STEPS + 1):
            if stop_event.is_set():
                break
            frac = (i / IDLE_PULSE_STEPS) * IDLE_PULSE_MAX_FRAC
            cr, cg, cb = int(r * frac), int(g * frac), int(b * frac)
            for led in range(NUM_LEDS):
                strip.setPixelColor(led, Color(cr, cg, cb))
            strip.show()
            stop_event.wait(IDLE_PULSE_STEP_S)
        for i in range(IDLE_PULSE_STEPS, -1, -1):
            if stop_event.is_set():
                break
            frac = (i / IDLE_PULSE_STEPS) * IDLE_PULSE_MAX_FRAC
            cr, cg, cb = int(r * frac), int(g * frac), int(b * frac)
            for led in range(NUM_LEDS):
                strip.setPixelColor(led, Color(cr, cg, cb))
            strip.show()
            stop_event.wait(IDLE_PULSE_STEP_S)

    all_leds_off(strip)


# =============================================================================
# SIGNALS (blocking one-shot patterns)
# =============================================================================


def signal_connected(strip):
    """Flash green to indicate successful connection and login."""
    flash_leds(strip, COLOR_CONNECTED, FLASH_COUNT_CONNECT)


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
# THREAD LIFECYCLE
# =============================================================================


def start_animation(target, strip, stop_event):
    """Start a daemon animation thread and return it."""
    t = threading.Thread(target=target, args=(strip, stop_event), daemon=True)
    t.start()
    return t


def stop_animation(stop_event, thread):
    """Signal a thread to stop and wait for it to finish."""
    stop_event.set()
    if thread:
        thread.join(timeout=2)
