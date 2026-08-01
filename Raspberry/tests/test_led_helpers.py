import pytest
import os
import sys

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playwright_chesscom.led_helpers import get_led_indices

def test_strip1_mapping():
    # Strip 1: files a-d (row 0-3)
    # File a (row 0): a8 -> a1
    assert get_led_indices(7, 0) == [16, 17]  # a8
    assert get_led_indices(0, 0) == [0, 1]    # a1

    # File b (row 1): b1 -> b8
    assert get_led_indices(0, 1) == [34, 35]  # b1
    assert get_led_indices(7, 1) == [18, 19]  # b8

def test_strip2_mapping():
    # Strip 2: files e-h (row 4-7)
    # 1. First LED at h8 (col=7, row=7) -> down to h1 (col=0, row=7)
    assert get_led_indices(7, 7) == [72, 73]   # h8 (Starts Strip 2!)
    assert get_led_indices(0, 7) == [89, 90]   # h1

    # 2. Next g1 (col=0, row=6) -> back up to g8 (col=7, row=6)
    assert get_led_indices(0, 6) == [91, 92]   # g1
    assert get_led_indices(7, 6) == [108, 109] # g8

    # 3. Next f8 (col=7, row=5) -> down to f1 (col=0, row=5)
    assert get_led_indices(7, 5) == [110, 111] # f8
    assert get_led_indices(0, 5) == [127, 128] # f1

    # 4. Next e1 (col=0, row=4) -> up to e8 (col=7, row=4) where it finishes
    assert get_led_indices(0, 4) == [129, 130] # e1
    assert get_led_indices(7, 4) == [146, 147] # e8 (Finishes Strip 2!)
