import pytest
import os
import sys

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright_chesscom.led_helpers import get_led_indices

def test_strip1_mapping():
    # Strip 1: files a-d (row 0-3), 18 LEDs per column (16 active + 2 skipped OFF LEDs)
    # File a (row 0): a1 (bottom, col 0) -> a8 (top, col 7)
    assert get_led_indices(7, 0, swap_rows=False) == [16, 17]  # a8
    assert get_led_indices(6, 0, swap_rows=False) == [14, 15]  # a7
    assert get_led_indices(0, 0, swap_rows=False) == [0, 1]    # a1

    # File b (row 1): b8 (top, col 7) -> b1 (bottom, col 0)
    assert get_led_indices(7, 1, swap_rows=False) == [18, 19]  # b8
    assert get_led_indices(0, 1, swap_rows=False) == [34, 35]  # b1

    # File c (row 2): c1 (bottom, col 0) -> c8 (top, col 7)
    assert get_led_indices(0, 2, swap_rows=False) == [36, 37]  # c1
    assert get_led_indices(7, 2, swap_rows=False) == [52, 53]  # c8

    # File d (row 3): d8 (top, col 7) -> d1 (bottom, col 0)
    assert get_led_indices(7, 3, swap_rows=False) == [54, 55]  # d8
    assert get_led_indices(0, 3, swap_rows=False) == [70, 71]  # d1

def test_strip2_mapping():
    # Strip 2: files e-h (row 4-7), 2 LEDs per square base (base offset = 76)
    # File h (row 7, c_rel 0): h8 (top, col 7) -> h1 (bottom, col 0)
    assert get_led_indices(7, 7, swap_rows=False) == [76, 77]    # h8 (Starts Strip 2!)
    assert get_led_indices(0, 7, swap_rows=False) == [90, 91]    # h1

    # File g (row 6, c_rel 1): g1 (bottom, col 0) -> g8 (top, col 7)
    assert get_led_indices(0, 6, swap_rows=False) == [92, 93]    # g1
    assert get_led_indices(7, 6, swap_rows=False) == [106, 107]  # g8

    # File f (row 5, c_rel 2): f8 (top, col 7) -> f1 (bottom, col 0)
    assert get_led_indices(7, 5, swap_rows=False) == [108, 109]  # f8
    assert get_led_indices(0, 5, swap_rows=False) == [122, 123]  # f1

    # File e (row 4, c_rel 3): e1 (bottom, col 0) -> e8 (top, col 7)
    assert get_led_indices(0, 4, swap_rows=False) == [124, 125]  # e1
    assert get_led_indices(7, 4, swap_rows=False) == [138, 139]  # e8 (Finishes Strip 2!)

def test_row_swap_mapping():
    # When swap_rows=True, col (rank 0..7) is transformed: phys_col = (col + 4) % 8
    assert get_led_indices(0, 0, swap_rows=True) == get_led_indices(4, 0, swap_rows=False)
    assert get_led_indices(0, 0, swap_rows=True) == [9, 10]

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


