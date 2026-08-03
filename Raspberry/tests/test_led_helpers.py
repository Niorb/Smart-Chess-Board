import pytest
import os
import sys

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright_chesscom.led_helpers import get_led_indices

def test_strip1_mapping():
    # Strip 1: files a-d (row 0-3)
    # File a (row 0): a8 -> a1
    assert get_led_indices(7, 0, swap_rows=False) == [16, 17]  # a8
    assert get_led_indices(0, 0, swap_rows=False) == [0, 1]    # a1

    # File b (row 1): b1 -> b8
    assert get_led_indices(0, 1, swap_rows=False) == [34, 35]  # b1
    assert get_led_indices(7, 1, swap_rows=False) == [18, 19]  # b8

def test_strip2_mapping():
    # Strip 2: files e-h (row 4-7)
    # 1. First LED at h8 (col=7, row=7) -> down to h1 (col=0, row=7)
    assert get_led_indices(7, 7, swap_rows=False) == [72, 73]   # h8 (Starts Strip 2!)
    assert get_led_indices(0, 7, swap_rows=False) == [89, 90]   # h1

    # 2. Next g1 (col=0, row=6) -> back up to g8 (col=7, row=6)
    assert get_led_indices(0, 6, swap_rows=False) == [91, 92]   # g1
    assert get_led_indices(7, 6, swap_rows=False) == [108, 109] # g8

    # 3. Next f8 (col=7, row=5) -> down to f1 (col=0, row=5)
    assert get_led_indices(7, 5, swap_rows=False) == [110, 111] # f8
    assert get_led_indices(0, 5, swap_rows=False) == [127, 128] # f1

    # 4. Next e1 (col=0, row=4) -> up to e8 (col=7, row=4) where it finishes
    assert get_led_indices(0, 4, swap_rows=False) == [129, 130] # e1
    assert get_led_indices(7, 4, swap_rows=False) == [146, 147] # e8 (Finishes Strip 2!)

def test_row_swap_mapping():
    # When swap_rows=True, col (rank 0..7) is transformed: phys_col = (col + 4) % 8
    # For a1 (col=0, row=0): non-swapped is [0, 1]. Swapped maps col 0 -> 4 (a5 position: [9, 10]).
    assert get_led_indices(0, 0, swap_rows=True) == get_led_indices(4, 0, swap_rows=False)
    assert get_led_indices(0, 0, swap_rows=True) == [9, 10]

    # For a5 (col=4, row=0): Swapped maps col 4 -> 0 (a1 position: [0, 1]).
    assert get_led_indices(4, 0, swap_rows=True) == get_led_indices(0, 0, swap_rows=False)
    assert get_led_indices(4, 0, swap_rows=True) == [0, 1]


def test_dual_pixel_strip_lock_and_show():
    from unittest.mock import MagicMock
    import threading
    from playwright_chesscom.led_helpers import DualPixelStrip, all_leds_off, all_leds_color

    strip = DualPixelStrip(num_leds_per_strip=76)
    mock_ser = MagicMock()
    lock = threading.Lock()
    strip.set_serial_conn(mock_ser, lock=lock)

    # Set pixel 0 to red
    strip.setPixelColor(0, (255, 0, 0))
    strip.show()

    # Check serial calls: L, 0, 255, 0, 0 followed by W
    mock_ser.write.assert_any_call(bytes([ord('L'), 0, 255, 0, 0]))
    mock_ser.write.assert_any_call(b'W')
    assert strip.shown_colors[0] == (255 << 16)

    # Test all_leds_off with lock
    mock_ser.reset_mock()
    all_leds_off(strip)
    mock_ser.write.assert_called_with(b'C')
    assert strip.current_colors[0] == 0
    assert strip.shown_colors[0] == 0

    # Test all_leds_color with lock
    mock_ser.reset_mock()
    all_leds_color(strip, (0, 255, 0))
    mock_ser.write.assert_called_with(bytes([ord('A'), 0, 255, 0]))
    assert strip.current_colors[0] == (255 << 8)
    assert strip.shown_colors[0] == (255 << 8)


