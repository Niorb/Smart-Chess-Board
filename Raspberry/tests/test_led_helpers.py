import os
import sys

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.led_helpers import get_led_indices


def test_strip1_mapping():
    # Strip 1: Ranks 1-4 (col 0-3), 18 LEDs per column (16 active + 2 skipped OFF LEDs)
    # Rank 1 (col 0): a1 (left, row 0) -> h1 (right, row 7)
    assert get_led_indices(0, 0) == (0, 1)    # a1 (Starts Strip 1!)
    assert get_led_indices(0, 1) == (2, 3)    # b1
    assert get_led_indices(0, 7) == (16, 17)  # h1

    # Rank 2 (col 1): h2 (right, row 7) -> a2 (left, row 0)
    assert get_led_indices(1, 7) == (18, 19)  # h2
    assert get_led_indices(1, 0) == (34, 35)  # a2

    # Rank 3 (col 2): a3 (left, row 0) -> h3 (right, row 7)
    assert get_led_indices(2, 0) == (36, 37)  # a3
    assert get_led_indices(2, 7) == (52, 53)  # h3

    # Rank 4 (col 3): h4 (right, row 7) -> a4 (left, row 0)
    assert get_led_indices(3, 7) == (54, 55)  # h4
    assert get_led_indices(3, 0) == (70, 71)  # a4


def test_strip2_mapping():
    # Strip 2: Ranks 5-8 (col 4-7), 19 LEDs per column (16 active + 3 skipped LEDs)
    # Rank 8 (col 7, c_rel 0): a8 (left, row 0) -> h8 (right, row 7)
    assert get_led_indices(7, 0) == (76, 77)    # a8 (Starts Strip 2!)
    assert get_led_indices(7, 7) == (93, 94)    # h8

    # Rank 7 (col 6, c_rel 1): h7 (right, row 7) -> a7 (left, row 0)
    assert get_led_indices(6, 7) == (95, 96)    # h7
    assert get_led_indices(6, 0) == (112, 113)  # a7

    # Rank 6 (col 5, c_rel 2): a6 (left, row 0) -> h6 (right, row 7)
    assert get_led_indices(5, 0) == (114, 115)  # a6
    assert get_led_indices(5, 7) == (131, 132)  # h6

    # Rank 5 (col 4, c_rel 3): h5 (right, row 7) -> a5 (left, row 0)
    assert get_led_indices(4, 7) == (133, 134)  # h5
    assert get_led_indices(4, 0) == (150, 151)  # a5 (Finishes Strip 2!)


def test_dual_pixel_strip_lock_and_show():
    import threading
    from unittest.mock import MagicMock

    from app.led_helpers import (
        CMD_CLEAR_LEDS,
        CMD_SET_ALL,
        CMD_SET_AND_SHOW,
        DualPixelStrip,
        all_leds_color,
        all_leds_off,
        build_packet,
    )

    strip = DualPixelStrip(num_leds_per_strip=76)
    mock_ser = MagicMock()
    lock = threading.Lock()
    strip.set_serial_conn(mock_ser, lock=lock)

    # Set pixel 0 to red (from initial all-off)
    strip.setPixelColor(0, (255, 0, 0))
    strip.show()

    # Binary framed check: CMD_SET_AND_SHOW packet with idx 0, r 255, g 0, b 0
    expected_packet = build_packet(CMD_SET_AND_SHOW, bytes([0, 255, 0, 0]))
    mock_ser.write.assert_called_with(expected_packet)
    assert strip.shown_colors[0] == (255 << 16)

    # Change pixel 0 to green
    mock_ser.reset_mock()
    strip.setPixelColor(0, (0, 255, 0))
    strip.show()
    expected_packet_green = build_packet(CMD_SET_AND_SHOW, bytes([0, 0, 255, 0]))
    mock_ser.write.assert_called_with(expected_packet_green)

    # Test all_leds_off with lock -> transitions to all-off, CMD_CLEAR_LEDS packet is sent
    mock_ser.reset_mock()
    all_leds_off(strip)
    expected_clear = build_packet(CMD_CLEAR_LEDS)
    mock_ser.write.assert_called_with(expected_clear)
    assert strip.current_colors[0] == 0
    assert strip.shown_colors[0] == 0

    # Test all_leds_color with lock -> CMD_SET_ALL packet is sent
    mock_ser.reset_mock()
    all_leds_color(strip, (0, 255, 0))
    expected_set_all = build_packet(CMD_SET_ALL, bytes([0, 255, 0]))
    mock_ser.write.assert_called_with(expected_set_all)
    assert strip.current_colors[0] == (255 << 8)
    assert strip.shown_colors[0] == (255 << 8)


def test_keyframe_self_healing():
    from unittest.mock import MagicMock

    from app.led_helpers import DualPixelStrip

    strip = DualPixelStrip(num_leds_per_strip=76)
    mock_ser = MagicMock()
    strip.set_serial_conn(mock_ser)

    # Frame 1: set pixel 5, show() transmits 1 chunk
    strip.setPixelColor(5, (100, 200, 50))
    strip.show()
    assert mock_ser.write.call_count == 1

    # Frame 2: unchanged frame -> show() does NOT send data
    mock_ser.reset_mock()
    strip.show()
    assert mock_ser.write.call_count == 0

    # Frames 3 to 59 (57 iterations): all unchanged -> 0 transmissions
    for _ in range(57):
        strip.show()
    assert mock_ser.write.call_count == 0

    # Frame 60: Keyframe triggered -> transmits full 152-LED buffer in 4 chunks (152 / 38)
    strip.show()
    assert mock_ser.write.call_count == 4
