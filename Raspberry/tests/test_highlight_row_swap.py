import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.led_helpers import get_led_indices


def test_highlight_led_indices():
    # For a1 (rank=0, file=0): starts Strip 1 at physical LEDs 0, 1
    leds_a1 = get_led_indices(0, 0)
    assert leds_a1 == [0, 1]

    # For h1 (rank=0, file=7): mapped to physical LEDs 16, 17
    leds_h1 = get_led_indices(0, 7)
    assert leds_h1 == [16, 17]

    # For a8 (rank=7, file=0): starts Strip 2 at physical LEDs 76, 77
    leds_a8 = get_led_indices(7, 0)
    assert leds_a8 == [76, 77]
