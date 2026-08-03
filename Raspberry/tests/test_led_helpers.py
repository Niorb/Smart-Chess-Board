import pytest
import os
import sys

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright_chesscom.led_helpers import get_led_indices

def test_strip1_mapping():
    # Strip 1: files a-d (row 0-3), 2 LEDs per square
    # File a (row 0): a8 (top, col 7) -> a1 (bottom, col 0)
    assert get_led_indices(7, 0, swap_rows=False) == [0, 1]    # a8
    assert get_led_indices(0, 0, swap_rows=False) == [14, 15]  # a1

    # File b (row 1): b1 (bottom, col 0) -> b8 (top, col 7)
    assert get_led_indices(0, 1, swap_rows=False) == [16, 17]  # b1
    assert get_led_indices(7, 1, swap_rows=False) == [30, 31]  # b8

def test_strip2_mapping():
    # Strip 2: files e-h (row 4-7) are kept completely OFF (return [])
    assert get_led_indices(7, 7, swap_rows=False) == []   # h8
    assert get_led_indices(0, 7, swap_rows=False) == []   # h1
    assert get_led_indices(0, 6, swap_rows=False) == []   # g1
    assert get_led_indices(7, 6, swap_rows=False) == []   # g8
    assert get_led_indices(7, 5, swap_rows=False) == []   # f8
    assert get_led_indices(0, 5, swap_rows=False) == []   # f1
    assert get_led_indices(0, 4, swap_rows=False) == []   # e1
    assert get_led_indices(7, 4, swap_rows=False) == []   # e8

def test_row_swap_mapping():
    # When swap_rows=True, col (rank 0..7) is transformed: phys_col = (col + 4) % 8
    assert get_led_indices(0, 0, swap_rows=True) == get_led_indices(4, 0, swap_rows=False)
    assert get_led_indices(0, 0, swap_rows=True) == [6, 7]

    assert get_led_indices(4, 0, swap_rows=True) == get_led_indices(0, 0, swap_rows=False)
    assert get_led_indices(4, 0, swap_rows=True) == [14, 15]


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


