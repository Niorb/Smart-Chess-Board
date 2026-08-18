"""
tests/test_led_animations.py

Unit tests for procedural LED animation engine and frame rendering.
"""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import NUM_LEDS
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
    frame = [0] * NUM_LEDS
    render_game_won(0.5, frame, {}, now=time.time())
    assert any(frame)


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
    # The intermediate square (4,2) should have illuminated pixels
    assert any(frame)


def test_render_move_trace_diagonal():
    frame = [0] * NUM_LEDS
    # a1 (0,0) to h8 (7,7)
    path = [(i, i) for i in range(8)]
    render_move_trace(path, 0.4, frame)
    assert any(frame)
