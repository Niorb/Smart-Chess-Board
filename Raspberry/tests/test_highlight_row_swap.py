import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.led_helpers import get_led_indices


def test_highlight_led_indices():
    # For a8 (rank=7, file=0): starts Strip 1 at physical LEDs 0, 1
    leds_a8 = get_led_indices(7, 0)
    assert leds_a8 == [0, 1]

    # For a1 (rank=0, file=0): mapped to physical LEDs 16, 17
    leds_a1 = get_led_indices(0, 0)
    assert leds_a1 == [16, 17]

    # For e1 (rank=0, file=4): mapped to physical LEDs 133, 134
    leds_e1 = get_led_indices(0, 4)
    assert leds_e1 == [133, 134]
