"""
board_hardware.py

Shared hardware helpers for the Smart Chess Board.
Used by smart_chess_board.py and hardware_test.py.

Contains MUX pin assignments, board scanning, and debouncing logic
that is identical across both entry points.
"""

import time
try:
    import lgpio
except ImportError:
    class MockLgpio:
        def gpiochip_open(self, _): return "mock_chip"
        def gpiochip_close(self, _): pass
        def gpio_claim_output(self, *args): pass
        def gpio_claim_input(self, *args): pass
        def gpio_write(self, *args): pass
        def gpio_read(self, *args): return 1 # Default HIGH (no magnet)
        def callback(self, *args): pass
        error = Exception
        FALLING_EDGE = 1
        SET_PULL_UP = 1
    lgpio = MockLgpio()
    print("WARNING: lgpio not found. Using MockLgpio.")

# =============================================================================
# BOARD DIMENSIONS
# =============================================================================

BOARD_ROWS = 4
BOARD_COLS = 4

# =============================================================================
# MUX PIN ASSIGNMENTS (BCM numbering)
# =============================================================================

ROW_MUX_S0 = 17
ROW_MUX_S1 = 27
ROW_MUX_S2 = 22

COL_MUX_S0 = 5
COL_MUX_S1 = 6
COL_MUX_S2 = 13

MUX_READ_PIN = 24

# =============================================================================
# TIMING
# =============================================================================

MUX_SETTLE_S = 0.001  # 1ms settle after MUX switch

# =============================================================================
# MUX CONTROL
# =============================================================================


def set_mux_channel(h, s0, s1, s2, channel):
    """Set the 3 address pins of a CD74HC4067 to select a channel (0-7)."""
    lgpio.gpio_write(h, s0, (channel) & 1)
    lgpio.gpio_write(h, s1, (channel >> 1) & 1)
    lgpio.gpio_write(h, s2, (channel >> 2) & 1)


# =============================================================================
# BOARD SCANNING
# =============================================================================


def scan_board(h, raw_state):
    """Scan every cell in the matrix and store results in raw_state[][]."""
    for row in range(BOARD_ROWS):
        set_mux_channel(h, ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, row)
        lgpio.gpio_read(h, MUX_READ_PIN)  # Dummy read for settling
        time.sleep(MUX_SETTLE_S)

        for col in range(BOARD_COLS):
            set_mux_channel(h, COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, col)
            time.sleep(MUX_SETTLE_S)
            # LOW (0) = magnet detected = piece present (active-low sensor)
            raw_state[row][col] = lgpio.gpio_read(h, MUX_READ_PIN) == 0

    # Deselect both MUXes to an unused channel after scan
    set_mux_channel(h, ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2, 5)
    set_mux_channel(h, COL_MUX_S0, COL_MUX_S1, COL_MUX_S2, 5)


# =============================================================================
# DEBOUNCING
# =============================================================================


def apply_debounce(raw_state, sensor_state, stable_count, threshold):
    """
    Apply debouncing. Returns True if any square's state changed.

    threshold: number of consecutive matching reads required to accept a change.
    """
    changed = False
    for r in range(BOARD_ROWS):
        for c in range(BOARD_COLS):
            if raw_state[r][c] == sensor_state[r][c]:
                stable_count[r][c] = 0
            else:
                stable_count[r][c] += 1
                if stable_count[r][c] >= threshold:
                    sensor_state[r][c] = raw_state[r][c]
                    stable_count[r][c] = 0
                    changed = True
    return changed


# =============================================================================
# GPIO SETUP
# =============================================================================


def init_mux_pins(h):
    """Configure MUX select pins as outputs and read pin as input."""
    for pin in [ROW_MUX_S0, ROW_MUX_S1, ROW_MUX_S2,
                COL_MUX_S0, COL_MUX_S1, COL_MUX_S2]:
        lgpio.gpio_claim_output(h, pin)
    lgpio.gpio_claim_input(h, MUX_READ_PIN)
