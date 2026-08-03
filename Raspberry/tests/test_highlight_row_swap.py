import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from board_hardware import settings, is_row_swapped
from playwright_chesscom.led_helpers import get_led_indices

def test_highlight_with_row_swap():
    # Configure left quadrant swapped and right quadrant not swapped
    settings["swap_row_quadrants_left"] = True
    settings["swap_row_quadrants_right"] = False

    # Check is_row_swapped for left (files 0..3) vs right (files 4..7)
    assert is_row_swapped(0) is True   # File a
    assert is_row_swapped(3) is True   # File d
    assert is_row_swapped(4) is True   # File e (row swap active by default)
    assert is_row_swapped(7) is True   # File h (row swap active by default)

    # For a1 (rank=0, file=0): row swap active, mapped to physical rank 4
    leds_a1 = get_led_indices(0, 0)
    assert leds_a1 == get_led_indices(4, 0, swap_rows=False)

    # For e1 (rank=0, file=4): row swap active by default, mapped to physical rank 4
    leds_e1 = get_led_indices(0, 4)
    assert leds_e1 == get_led_indices(4, 4, swap_rows=False)
