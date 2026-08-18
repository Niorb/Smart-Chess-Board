"""
app/led_helpers.py

Shared WS2812B LED strip helpers for the Smart Chess Board.
Provides DualPixelStrip wrapper for serial-based LED control on the ESP32 coprocessor,
serpentine LED index routing for the physical 8x8 chessboard, and animation routines.
"""

import threading
import time

try:
    from app.config import (
        ANIM_GAME_DRAWN_DURATION_S,
        ANIM_GAME_LOST_DURATION_S,
        ANIM_GAME_START_DURATION_S,
        ANIM_GAME_WON_DURATION_S,
        COLOR_CANCELLED,
        COLOR_CHECK,
        COLOR_CONNECTED,
        COLOR_CONNECTING,
        COLOR_DEFEAT_RED,
        COLOR_DRAW_BLUE,
        COLOR_DRAW_WHITE,
        COLOR_ERROR,
        COLOR_FOUND_BLACK,
        COLOR_FOUND_WHITE,
        COLOR_HIGHLIGHT,
        COLOR_IDLE,
        COLOR_ILLEGAL,
        COLOR_LEGAL_TARGET,
        COLOR_MOVE_TRACE,
        COLOR_OFF,
        COLOR_OPPONENT_FROM,
        COLOR_OPPONENT_TO,
        COLOR_PIECE_LIFTED,
        COLOR_SEARCHING,
        COLOR_SETUP_MISPLACED,
        COLOR_SETUP_MISSING,
        COLOR_VICTORY_GOLD,
        COLOR_VICTORY_GREEN,
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
        LEDS_PER_STRIP,
        LED_STRIP_COUNT,
        MOVE_TRACE_PERIOD_S,
        NUM_LEDS,
        SEARCH_CHASE_DELAY_S,
    )
except ImportError:
    from .config import (
        ANIM_GAME_DRAWN_DURATION_S,
        ANIM_GAME_LOST_DURATION_S,
        ANIM_GAME_START_DURATION_S,
        ANIM_GAME_WON_DURATION_S,
        COLOR_CANCELLED,
        COLOR_CHECK,
        COLOR_CONNECTED,
        COLOR_CONNECTING,
        COLOR_DEFEAT_RED,
        COLOR_DRAW_BLUE,
        COLOR_DRAW_WHITE,
        COLOR_ERROR,
        COLOR_FOUND_BLACK,
        COLOR_FOUND_WHITE,
        COLOR_HIGHLIGHT,
        COLOR_IDLE,
        COLOR_ILLEGAL,
        COLOR_LEGAL_TARGET,
        COLOR_MOVE_TRACE,
        COLOR_OFF,
        COLOR_OPPONENT_FROM,
        COLOR_OPPONENT_TO,
        COLOR_PIECE_LIFTED,
        COLOR_SEARCHING,
        COLOR_SETUP_MISPLACED,
        COLOR_SETUP_MISSING,
        COLOR_VICTORY_GOLD,
        COLOR_VICTORY_GREEN,
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
        LEDS_PER_STRIP,
        LED_STRIP_COUNT,
        MOVE_TRACE_PERIOD_S,
        NUM_LEDS,
        SEARCH_CHASE_DELAY_S,
    )

# Try to import LED hardware library — degrades gracefully on non-Pi environments
try:
    from rpi_ws281x import Color
    HAS_LEDS = True
except ImportError:
    HAS_LEDS = False

    def Color(red, green, blue, white=0):
        return (white << 24) | (red << 16) | (green << 8) | blue


# Integer color constants for layered rendering pipeline
COLOR_INT_OFF = Color(0, 0, 0)
COLOR_INT_IDLE = Color(*COLOR_IDLE)
COLOR_INT_CONNECTING = Color(*COLOR_CONNECTING)
COLOR_INT_CONNECTED = Color(*COLOR_CONNECTED)
COLOR_INT_SEARCHING = Color(*COLOR_SEARCHING)
COLOR_INT_FOUND_WHITE = Color(*COLOR_FOUND_WHITE)
COLOR_INT_FOUND_BLACK = Color(*COLOR_FOUND_BLACK)
COLOR_INT_CANCELLED = Color(*COLOR_CANCELLED)
COLOR_INT_ERROR = Color(*COLOR_ERROR)
COLOR_INT_SETUP_MISSING = Color(*COLOR_SETUP_MISSING)
COLOR_INT_SETUP_MISPLACED = Color(*COLOR_SETUP_MISPLACED)
COLOR_INT_PIECE_LIFTED = Color(*COLOR_PIECE_LIFTED)
COLOR_INT_LEGAL_TARGET = Color(*COLOR_LEGAL_TARGET)
COLOR_INT_OPPONENT_FROM = Color(*COLOR_OPPONENT_FROM)
COLOR_INT_OPPONENT_TO = Color(*COLOR_OPPONENT_TO)
COLOR_INT_CHECK = Color(*COLOR_CHECK)
COLOR_INT_HIGHLIGHT = Color(*COLOR_HIGHLIGHT)
COLOR_INT_ILLEGAL = Color(*COLOR_ILLEGAL)
COLOR_INT_MOVE_TRACE = Color(*COLOR_MOVE_TRACE)
COLOR_INT_VICTORY_GOLD = Color(*COLOR_VICTORY_GOLD)
COLOR_INT_VICTORY_GREEN = Color(*COLOR_VICTORY_GREEN)
COLOR_INT_DEFEAT_RED = Color(*COLOR_DEFEAT_RED)
COLOR_INT_DRAW_BLUE = Color(*COLOR_DRAW_BLUE)
COLOR_INT_DRAW_WHITE = Color(*COLOR_DRAW_WHITE)


class DualPixelStrip:
    """
    Controls two serial WS2812B strips mapped as a single 152-LED buffer
    via commands to the ESP32 coprocessor.
    """
    def __init__(self, num_leds_per_strip=76):
        self.num_leds_per_strip = num_leds_per_strip
        self.ser = None
        self.lock = None
        self.current_colors = [0] * (2 * num_leds_per_strip)
        self.shown_colors = [0] * (2 * num_leds_per_strip)

    def set_serial_conn(self, ser, lock=None):
        self.ser = ser
        self.lock = lock

    def begin(self):
        """ESP32 initializes strips on boot."""
        pass

    def show(self):
        ser = self.ser
        if ser is None:
            return

        def _do_show():
            # Check if frame changed
            if self.current_colors == self.shown_colors:
                return

            try:
                all_current_off = not any(self.current_colors)
                all_shown_off = not any(self.shown_colors)

                if all_current_off:
                    if not all_shown_off:
                        ser.write(b'C')
                    self.shown_colors = list(self.current_colors)
                    return

                changed = False
                for idx in range(len(self.current_colors)):
                    curr = self.current_colors[idx]
                    if curr != self.shown_colors[idx]:
                        changed = True
                        r = (curr >> 16) & 0xFF
                        g = (curr >> 8) & 0xFF
                        b = curr & 0xFF
                        ser.write(bytes([ord('L'), idx, r, g, b]))

                if changed:
                    ser.write(b'W')  # Commit show

                self.shown_colors = list(self.current_colors)
            except Exception as e:
                print(f"LED Wrapper: Error writing LED commands: {e}")

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
# STRIP INIT & COORDINATE MAPPING
# =============================================================================

def init_strip():
    """Initialise and return the DualPixelStrip instance, or None if unavailable."""
    return DualPixelStrip(num_leds_per_strip=LEDS_PER_STRIP)


def get_led_indices(col, row):
    """
    Convert board coordinates to serpentine physical LED indices.
    col: rank index 0..7 (0 = Rank 1, 7 = Rank 8)
    row: file index 0..7 (0 = file a, 7 = file h)

    Strip 1 (files a-d / row 0-3): 18 LEDs per column (16 active + 2 skipped OFF LEDs).
    Strip 2 (files e-h / row 4-7): 19 LEDs per column (16 active + 3 skipped OFF LEDs).
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
        sq_idx = 7 - col if row % 2 == 0 else col
        return [base + o for o in offsets_strip1[sq_idx]]

    # Strip 2 (files e-h / row 4-7)
    # Relative column from right to left: h=0, g=1, f=2, e=3
    offsets_strip2 = {
        0: [0, 1],    # Square 0 (2 LEDs)
        1: [2, 3],    # Square 1 (2 active + 1 extra/skipped at offset 4)
        2: [5, 6],    # Square 2 (2 LEDs)
        3: [7, 8],    # Square 3 (2 active + 1 OFF/skipped at offset 9)
        4: [10, 11],  # Square 4 (2 LEDs)
        5: [12, 13],  # Square 5 (2 LEDs)
        6: [14, 15],  # Square 6 (2 active + 1 extra/skipped at offset 16)
        7: [17, 18],  # Square 7 (2 LEDs)
    }
    c_rel = 7 - row
    base = LEDS_PER_STRIP + c_rel * 19
    sq_idx = 7 - col if c_rel % 2 == 0 else col
    return [base + o for o in offsets_strip2[sq_idx]]


def all_leds_off(strip):
    """Turn off all LEDs using hardware batch clear command 'C' when possible."""
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
    """Set all LEDs to the same color using hardware batch command 'A' when possible."""
    if not strip:
        return
    if isinstance(rgb, int):
        r = (rgb >> 16) & 0xFF
        g = (rgb >> 8) & 0xFF
        b = rgb & 0xFF
        val = rgb
    else:
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
    Get LED indices for the board perimeter in clockwise order.
    Returns a list of lists (each inner list contains LED indices for one square).
    """
    perimeter_squares = []
    # Top rank L->R (rank 7, file 0 to 7)
    for r_idx in range(LED_ROWS):
        perimeter_squares.append(get_led_indices(7, r_idx))
    # Right file top->bottom (rank 6 down to 0, file 7)
    for c_idx in range(LED_COLS - 2, -1, -1):
        perimeter_squares.append(get_led_indices(c_idx, LED_ROWS - 1))
    # Bottom rank R->L (rank 0, file 6 down to 0)
    for r_idx in range(LED_ROWS - 2, -1, -1):
        perimeter_squares.append(get_led_indices(0, r_idx))
    # Left file bottom->top (rank 1 to 6, file 0)
    for c_idx in range(1, LED_COLS - 1):
        perimeter_squares.append(get_led_indices(c_idx, 0))
    return perimeter_squares


def flash_leds(strip, rgb, count):
    """Flash all LEDs a given color a specified number of times."""
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
    """Orange breathing pulse on all LEDs while connecting."""
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
    """Blue chase around the board perimeter while seeking a game."""
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
    """Dim white breathing pulse while idle to indicate online status."""
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
    """Flash green on connection."""
    flash_leds(strip, COLOR_CONNECTED, FLASH_COUNT_CONNECT)


def signal_game_found(strip, color):
    """Flash white (playing White) or green (playing Black) on match found."""
    if color == "white":
        flash_leds(strip, COLOR_FOUND_WHITE, FLASH_COUNT_FOUND)
    else:
        flash_leds(strip, COLOR_FOUND_BLACK, FLASH_COUNT_FOUND)


def signal_cancelled(strip):
    """Flash red to indicate search cancelled."""
    flash_leds(strip, COLOR_CANCELLED, FLASH_COUNT_CANCEL)


def signal_error(strip):
    """Flash red to indicate an error."""
    flash_leds(strip, COLOR_ERROR, FLASH_COUNT_ERROR)


# =============================================================================
# THREAD LIFECYCLE HELPERS
# =============================================================================

def start_animation(target, strip, stop_event):
    """Start a daemon animation thread and return it."""
    t = threading.Thread(target=target, args=(strip, stop_event), daemon=True)
    t.start()
    return t


def stop_animation(stop_event, thread):
    """Signal an animation thread to stop and join it."""
    stop_event.set()
    if thread and thread.is_alive():
        thread.join(timeout=2)
