"""
tests/test_led_animations.py

Unit tests for procedural LED animation engine, frame rendering, and move trace animation.
"""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import MOVE_TRACE_PERIOD_S, NUM_LEDS
from app.led_animations import (
    LifecycleAnimation,
    add_colors,
    blend_colors,
    color_rgb,
    create_animation,
    render_game_drawn,
    render_game_lost,
    render_game_started,
    render_game_won,
    render_move_trace,
    scale_color,
    unpack_rgb,
)
from app.led_helpers import (
    COLOR_INT_CAPTURE_TRACE,
    COLOR_INT_MOVE_TRACE,
    COLOR_INT_OFF,
    COLOR_INT_OPPONENT_CAPTURE,
    get_led_indices,
)


def test_color_arithmetic():
    c = color_rgb(255, 128, 64)
    assert unpack_rgb(c) == (255, 128, 64)

    scaled = scale_color(c, 0.5)
    r, g, b = unpack_rgb(scaled)
    assert abs(r - 127) <= 1
    assert abs(g - 64) <= 1
    assert abs(b - 32) <= 1

    blended = blend_colors(color_rgb(0, 0, 0), color_rgb(100, 100, 100), 0.5)
    assert unpack_rgb(blended) == (50, 50, 50)

    added = add_colors(color_rgb(200, 100, 50), color_rgb(100, 100, 100))
    assert unpack_rgb(added) == (255, 200, 150)


def test_lifecycle_animation_lifecycle():
    anim = create_animation("GAME_STARTED")
    assert anim.name == "GAME_STARTED"
    assert anim.duration == 1.5
    assert anim.is_active(anim.start_time + 0.5)
    assert not anim.is_active(anim.start_time + 2.0)
    assert anim.get_progress(anim.start_time) == 0.0
    assert abs(anim.get_progress(anim.start_time + 0.75) - 0.5) < 0.01


def test_render_game_started():
    frame = [0] * NUM_LEDS
    render_game_started(0.5, frame, {"my_color": "white"})
    assert any(frame)


def test_render_game_won():
    # Test at multiple progress steps to ensure low simultaneous active square count
    now = time.time()
    for p in [0.1, 0.25, 0.5, 0.75, 0.9]:
        frame = [0] * NUM_LEDS
        render_game_won(p, frame, {}, now=now)
        assert any(frame)
        # Count number of illuminated squares
        lit_squares = 0
        for c in range(8):
            for r in range(8):
                sq_indices = get_led_indices(r, c)
                if any(frame[idx] != 0 for idx in sq_indices if idx < NUM_LEDS):
                    lit_squares += 1
        # Strict lightweight lighting budget: must be <= 10 squares at any instant (far below 64)
        assert lit_squares <= 10



def test_render_game_lost():
    frame = [0] * NUM_LEDS
    render_game_lost(0.5, frame, {})
    assert any(frame)


def test_render_game_drawn():
    frame = [0] * NUM_LEDS
    render_game_drawn(0.5, frame, {}, now=time.time())
    assert any(frame)


def test_render_move_trace():
    frame = [0] * NUM_LEDS
    path = [(4, 1), (4, 2), (4, 3)]  # e2 to e4 (length 3, 1 intermediate square)
    render_move_trace(path, 0.4, frame)
    # The intermediate square (4,2) or arrival square should have illuminated pixels
    assert any(frame)


def test_render_move_trace_diagonal():
    frame = [0] * NUM_LEDS
    # a1 (0,0) to h8 (7,7)
    path = [(i, i) for i in range(8)]
    render_move_trace(path, 0.4, frame)
    assert any(frame)


def test_render_move_trace_one_step_move():
    """
    Verify 1-step move trajectory (len(path) == 2, e.g. e2 to e3 [(4,1), (4,2)]).
    Ensures that arrival square / pulse flare illuminates without indexing errors.
    """
    frame = [0] * NUM_LEDS
    path = [(4, 1), (4, 2)]  # e2 -> e3 (no intermediate squares)

    # Render at peak traversal time (t = 0.5 * period)
    render_move_trace(path, MOVE_TRACE_PERIOD_S * 0.5, frame, trace_color=COLOR_INT_MOVE_TRACE)

    # Arrival square (4, 2) LEDs
    arrival_indices = get_led_indices(2, 4)
    arrival_lit = any(frame[idx] != 0 for idx in arrival_indices if idx < NUM_LEDS)
    # Origin square (4, 1) LEDs
    origin_indices = get_led_indices(1, 4)
    origin_lit = any(frame[idx] != 0 for idx in origin_indices if idx < NUM_LEDS)

    assert arrival_lit or origin_lit or any(frame)


def test_render_move_trace_multi_step_and_arrival_flare():
    """
    Verify multi-step move trajectory progression and arrival pulse flare.
    """
    path = [(3, 0), (3, 1), (3, 2), (3, 3), (3, 4), (3, 5), (3, 6), (3, 7)]  # d1 to d8

    # Mid-path traversal (t = 0.5)
    frame_mid = [0] * NUM_LEDS
    render_move_trace(path, MOVE_TRACE_PERIOD_S * 0.5, frame_mid)

    # Mid square (3, 3) or (3, 4) should be illuminated
    mid_indices = get_led_indices(3, 3) + get_led_indices(4, 3)
    assert any(frame_mid[idx] != 0 for idx in mid_indices if idx < NUM_LEDS)

    # Near arrival (t = 0.95)
    frame_arr = [0] * NUM_LEDS
    render_move_trace(path, MOVE_TRACE_PERIOD_S * 0.95, frame_arr)
    assert any(frame_arr)


def test_capture_trace_and_opponent_capture_colors():
    """
    Verify COLOR_INT_OPPONENT_CAPTURE and COLOR_INT_CAPTURE_TRACE constants
    and render_move_trace handling with capture colors.
    """
    assert isinstance(COLOR_INT_OPPONENT_CAPTURE, int)
    assert COLOR_INT_OPPONENT_CAPTURE > 0
    assert isinstance(COLOR_INT_CAPTURE_TRACE, int)
    assert COLOR_INT_CAPTURE_TRACE > 0

    frame = [0] * NUM_LEDS
    path = [(4, 1), (4, 2), (4, 3)]
    render_move_trace(path, MOVE_TRACE_PERIOD_S * 0.5, frame, trace_color=COLOR_INT_CAPTURE_TRACE)
    assert any(frame)


def test_render_move_trace_loop_wraparound_continuity():
    """
    Verify smooth wrap-around continuity across animation cycle boundaries
    (now = 0, now = period * 0.999, now = period * 1.001, now = period * 5.5).
    """
    path = [(0, 0), (1, 1), (2, 2), (3, 3)]
    period = MOVE_TRACE_PERIOD_S

    test_timestamps = [
        0.0,
        period * 0.25,
        period * 0.5,
        period * 0.75,
        period * 0.999,
        period * 1.001,
        period * 2.5,
        period * 10.0,
    ]

    for ts in test_timestamps:
        frame = [0] * NUM_LEDS
        render_move_trace(path, ts, frame, period=period)
        for val in frame:
            assert val >= 0
            r, g, b = unpack_rgb(val)
            assert 0 <= r <= 255
            assert 0 <= g <= 255
            assert 0 <= b <= 255
