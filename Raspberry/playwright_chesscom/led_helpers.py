"""
led_helpers.py

Shared LED strip helpers for the chess.com Playwright integration.
Used by game_seeker.py and interactive_game.py.

All public functions accept strip=None gracefully (no-op when hardware
is unavailable), so callers on non-Pi machines work without changes.
"""

import threading
import time

try:
    from playwright_chesscom.chesscom_config import (
        COLOR_CANCELLED,
        COLOR_CONNECTED,
        COLOR_CONNECTING,
        COLOR_ERROR,
        COLOR_FOUND_BLACK,
        COLOR_FOUND_WHITE,
        COLOR_IDLE,
        COLOR_SEARCHING,
        CONNECT_PULSE_STEP_S,
        FLASH_COUNT_CANCEL,
        FLASH_COUNT_CONNECT,
        FLASH_COUNT_ERROR,
        FLASH_COUNT_FOUND,
        FLASH_OFF_S,
        FLASH_ON_S,
        IDLE_PULSE_MAX_FRAC,
        IDLE_PULSE_STEP_S,
        IDLE_PULSE_STEPS,
        LED_COLS,
        LED_ROWS,
        NUM_LEDS,
        SEARCH_CHASE_DELAY_S,
    )
except ImportError:
    from .chesscom_config import (
        COLOR_CANCELLED,
        COLOR_CONNECTED,
        COLOR_CONNECTING,
        COLOR_ERROR,
        COLOR_FOUND_BLACK,
        COLOR_FOUND_WHITE,
        COLOR_IDLE,
        COLOR_SEARCHING,
        CONNECT_PULSE_STEP_S,
        FLASH_COUNT_CANCEL,
        FLASH_COUNT_CONNECT,
        FLASH_COUNT_ERROR,
        FLASH_COUNT_FOUND,
        FLASH_OFF_S,
        FLASH_ON_S,
        IDLE_PULSE_MAX_FRAC,
        IDLE_PULSE_STEP_S,
        IDLE_PULSE_STEPS,
        LED_COLS,
        LED_ROWS,
        NUM_LEDS,
        SEARCH_CHASE_DELAY_S,
    )

# Try to import LED hardware — degrades gracefully on non-Pi machines
try:
    from rpi_ws281x import Color

    HAS_LEDS = True
except ImportError:
    HAS_LEDS = False

    # Fallback implementation so client code doesn't break on non-Pi environments
    def Color(red, green, blue, white=0):
        return (white << 24) | (red << 16) | (green << 8) | blue


class DualPixelStrip:
    def __init__(self, num_leds_per_strip):
        self.num_leds_per_strip = num_leds_per_strip
        self.ser = None
        self.lock = None
        self.current_colors = [0] * (2 * num_leds_per_strip)
        self.shown_colors = [0] * (2 * num_leds_per_strip)

    def set_serial_conn(self, ser, lock=None):
        self.ser = ser
        self.lock = lock

    def begin(self):
        pass  # ESP32 does its own setup on boot

    def show(self):
        ser = self.ser
        if ser is None:
            return

        def _do_show():
            changed = False
            # Collect updates to send as few packets as possible
            for idx in range(2 * self.num_leds_per_strip):
                curr = self.current_colors[idx]
                if curr != self.shown_colors[idx]:
                    changed = True
                    r = (curr >> 16) & 0xFF
                    g = (curr >> 8) & 0xFF
                    b = curr & 0xFF
                    try:
                        ser.write(bytes([ord('L'), idx, r, g, b]))
                        self.shown_colors[idx] = curr
                    except Exception as e:
                        print(f"LED Wrapper: Error writing SetPixelColor command to serial: {e}")

            if changed:
                try:
                    ser.write(b'W')
                except Exception as e:
                    print(f"LED Wrapper: Error writing Show command to serial: {e}")

        if self.lock:
            with self.lock:
                _do_show()
        else:
            _do_show()

    def setPixelColor(self, index, color):
        if 0 <= index < len(self.current_colors):
            if isinstance(color, int):
                val = color
            else:
                try:
                    r, g, b = color
                    val = (r << 16) | (g << 8) | b
                except Exception:
                    val = 0
            self.current_colors[index] = val

    set_pixel_color = setPixelColor

    def numPixels(self):
        return 2 * self.num_leds_per_strip

    num_pixels = numPixels


# =============================================================================
# STRIP INIT
# =============================================================================


def init_strip():
    """Initialise and return the LED strip, or None if hardware is unavailable."""
    if not HAS_LEDS:
        return None
    # Initialize the DualPixelStrip wrapper which controls both halves of the board
    return DualPixelStrip(num_leds_per_strip=76)


def get_led_indices(col, row):
    """
    Convert board [col, row] to serpentine LED strip indices.
    Strip 1 (files a-d / row 0-3): 18 LEDs per column (16 active + 2 skipped OFF LEDs after Rank 7 and Rank 3).
    Strip 2 (files e-h / row 4-7): 16 LEDs per column (2 LEDs / square base). Starts at h8 down to h1, g1 to g8, etc.

    col: rank index 0..7 (0 = Rank 1, 7 = Rank 8)
    row: file index 0..7 (0 = file a, 7 = file h)
    """
    if row < 4:
        # Strip 1 (files a-d / row 0-3)
        offsets_strip1 = {
            0: [0, 1],
            1: [2, 3],
            2: [5, 6],
            3: [7, 8],
            4: [9, 10],
            5: [11, 12],
            6: [14, 15],
            7: [16, 17]
        }
        base = row * 18
        sq_idx = col if row % 2 == 0 else 7 - col
        return [base + o for o in offsets_strip1[sq_idx]]

    # Strip 2 (files e-h / row 4-7)
    # Relative column from right to left: h=0, g=1, f=2, e=3
    c_rel = 7 - row
    base = 76 + c_rel * 16
    sq_idx = 7 - col if c_rel % 2 == 0 else col
    first_led = base + sq_idx * 2
    return [first_led, first_led + 1]


def all_leds_off(strip):
    """Turn off all LEDs."""
    if not strip:
        return
    if hasattr(strip, 'ser') and strip.ser:
        def _do_off():
            try:
                strip.ser.write(b'C')
                if hasattr(strip, 'current_colors'):
                    for i in range(len(strip.current_colors)):
                        strip.current_colors[i] = 0
                        strip.shown_colors[i] = 0
                return True
            except Exception:
                return False

        lock = getattr(strip, 'lock', None)
        if lock:
            with lock:
                if _do_off():
                    return
        else:
            if _do_off():
                return

    # Fallback
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def all_leds_color(strip, rgb):
    """Set all LEDs to the same color."""
    if not strip:
        return
    r, g, b = rgb
    val = (r << 16) | (g << 8) | b
    if hasattr(strip, 'ser') and strip.ser:
        def _do_color():
            try:
                strip.ser.write(bytes([ord('A'), r, g, b]))
                if hasattr(strip, 'current_colors'):
                    for i in range(len(strip.current_colors)):
                        strip.current_colors[i] = val
                        strip.shown_colors[i] = val
                return True
            except Exception:
                return False

        lock = getattr(strip, 'lock', None)
        if lock:
            with lock:
                if _do_color():
                    return
        else:
            if _do_color():
                return

    # Fallback
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, Color(r, g, b))
    strip.show()


def get_perimeter_indices():
    """
    Get LED indices for the board perimeter in order (clockwise).
    Returns a list of lists (each inner list contains LEDs for one square).
    """
    perimeter_squares = []
    # Top col L->R (col 7, row 0 to 7)
    for r_idx in range(LED_ROWS):
        perimeter_squares.append(get_led_indices(7, r_idx))
    # Right row top->bottom (col 6 down to 0, row 7)
    for c_idx in range(LED_COLS - 2, -1, -1):
        perimeter_squares.append(get_led_indices(c_idx, LED_ROWS - 1))
    # Bottom col R->L (col 0, row 6 down to 0)
    for r_idx in range(LED_ROWS - 2, -1, -1):
        perimeter_squares.append(get_led_indices(0, r_idx))
    # Left row bottom->top (col 1 to 6, row 0)
    for c_idx in range(1, LED_COLS - 1):
        perimeter_squares.append(get_led_indices(c_idx, 0))
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
