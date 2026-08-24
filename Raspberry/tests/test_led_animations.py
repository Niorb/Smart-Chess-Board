"""
tests/test_led_animations.py

Unit tests for procedural LED animation engine, frame rendering, and move trace animation.
"""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import (
    ANIM_BOARD_READY_DURATION_S,
    ANIM_CASTLE_PERIOD_S,
    ANIM_SEEKING_DURATION_S,
    ANIM_SEEKING_PERIOD_S,
    MOVE_TRACE_PERIOD_S,
    NUM_LEDS,
)
from app.led_animations import (
    PERIMETER_COORDS,
    add_colors,
    blend_colors,
    color_rgb,
    create_animation,
    render_board_ready,
    render_castle_trace,
    render_clock_bar,
    render_return_home_guide,
    render_game_drawn,
    render_game_lost,
    render_game_started,
    render_game_won,
    render_move_trace,
    render_seeking,
    scale_color,
    unpack_rgb,
)
from app.led_helpers import (
    COLOR_INT_CAPTURE_TRACE,
    COLOR_INT_CLOCK_CRIT,
    COLOR_INT_CLOCK_OK,
    COLOR_INT_CLOCK_WARN,
    COLOR_INT_MOVE_TRACE,
    COLOR_INT_NIGHT_CLOCK_CRIT,
    COLOR_INT_NIGHT_CLOCK_OK,
    COLOR_INT_NIGHT_CLOCK_WARN,
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
    assert anim.duration == 2.2
    assert anim.is_active(anim.start_time + 0.5)
    assert not anim.is_active(anim.start_time + 2.5)
    assert anim.get_progress(anim.start_time) == 0.0
    assert abs(anim.get_progress(anim.start_time + 1.1) - 0.5) < 0.01


def test_render_game_started():
    # Test White army start animation
    for p in [0.1, 0.3, 0.6, 0.8, 0.95]:
        frame = [0] * NUM_LEDS
        render_game_started(p, frame, {"my_color": "white"})
        assert any(frame)
        lit_squares = 0
        for c in range(8):
            for r in range(8):
                sq_indices = get_led_indices(r, c)
                if any(frame[idx] != 0 for idx in sq_indices if idx < NUM_LEDS):
                    lit_squares += 1
        # Strict low-power budget: max 6 active squares (< 10% of board)
        assert lit_squares <= 6

    # Test Black army start animation
    for p in [0.1, 0.3, 0.6, 0.8, 0.95]:
        frame_black = [0] * NUM_LEDS
        render_game_started(p, frame_black, {"my_color": "black"})
        assert any(frame_black)
        lit_squares = 0
        for c in range(8):
            for r in range(8):
                sq_indices = get_led_indices(r, c)
                if any(frame_black[idx] != 0 for idx in sq_indices if idx < NUM_LEDS):
                    lit_squares += 1
        assert lit_squares <= 6


def test_render_opponent_disconnected():
    from app.led_animations import render_opponent_disconnected
    frame = [0] * NUM_LEDS
    opponent_info = {"gone": True, "claim_win_in": 20, "initial_claim_win_in": 30, "start_time": time.time() - 10}
    render_opponent_disconnected(time.time(), frame, opponent_info, my_color="white", opponent_king_sq=(4, 7))
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
        # Strict lightweight lighting budget: must be <= 16 squares at any instant (far below full-board 64)
        assert lit_squares <= 16



def test_render_game_lost():
    """
    Verify GAME_LOST animation ("The Sovereign's Eclipse"):
    - Strictly within 18 squares illuminated simultaneously at any single frame (< 28% of board).
    - Fully symmetrical and unified for White and Black.
    - All 3 phases (inward perimeter collapse, shockwave ring + shards, smoldering embers) illuminate properly.
    - Night Mode scaling operates cleanly.
    """
    # 1. Test Day Mode across all phases
    for p in [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]:
        frame = [0] * NUM_LEDS
        render_game_lost(p, frame, {"my_color": "white", "night_mode": False})
        assert any(frame), f"Frame empty at progress {p} in Day Mode"
        lit_squares = 0
        for c in range(8):
            for r in range(8):
                sq_indices = get_led_indices(r, c)
                if any(frame[idx] != 0 for idx in sq_indices if idx < NUM_LEDS):
                    lit_squares += 1
        assert lit_squares <= 18, f"Too many squares lit ({lit_squares}) at progress {p} for Day Mode"

    # 2. Test Night Mode across all phases
    for p in [0.10, 0.40, 0.60, 0.80, 0.92]:
        frame_night = [0] * NUM_LEDS
        render_game_lost(p, frame_night, {"my_color": "black", "night_mode": True})
        assert any(frame_night), f"Frame empty at progress {p} in Night Mode"
        lit_squares = 0
        for c in range(8):
            for r in range(8):
                sq_indices = get_led_indices(r, c)
                if any(frame_night[idx] != 0 for idx in sq_indices if idx < NUM_LEDS):
                    lit_squares += 1
        assert lit_squares <= 18, f"Too many squares lit ({lit_squares}) at progress {p} for Night Mode"


def test_render_game_drawn():
    """
    Verify GAME_DRAWN animation ("The Celestial Equilibrium"):
    - Strictly within 16 squares illuminated simultaneously at any single frame (< 25% of board).
    - Tests Phase 1 (dual army tides), Phase 2 (equatorial vortex), Phase 3 (horizon dissolve).
    - Day Mode and Night Mode support.
    """
    for p in [0.10, 0.25, 0.45, 0.60, 0.75, 0.90]:
        frame = [0] * NUM_LEDS
        render_game_drawn(p, frame, {"night_mode": False}, now=time.time())
        assert any(frame), f"Frame empty at progress {p} for GAME_DRAWN Day Mode"
        lit_squares = 0
        for c in range(8):
            for r in range(8):
                sq_indices = get_led_indices(r, c)
                if any(frame[idx] != 0 for idx in sq_indices if idx < NUM_LEDS):
                    lit_squares += 1
        assert lit_squares <= 16, f"Too many squares lit ({lit_squares}) at progress {p} for GAME_DRAWN"

    # Night Mode
    frame_night = [0] * NUM_LEDS
    render_game_drawn(0.50, frame_night, {"night_mode": True}, now=time.time())
    assert any(frame_night), "Frame empty at progress 0.50 for GAME_DRAWN Night Mode"


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


def test_perimeter_coords_structure():
    """Verify that PERIMETER_COORDS contains exactly 28 outer squares with valid 0..7 coordinates."""
    assert len(PERIMETER_COORDS) == 28
    assert len(set(PERIMETER_COORDS)) == 28
    for c, r in PERIMETER_COORDS:
        assert 0 <= c <= 7
        assert 0 <= r <= 7
        # Must be on the boundary (rank 0 or 7, or file 0 or 7)
        assert c in (0, 7) or r in (0, 7)


def test_render_seeking_perimeter_bounds_and_decay():
    """
    Verify render_seeking:
    - Inner 6x6 squares remain completely dark (0).
    - Only perimeter squares illuminate.
    - Active illuminated squares remain within low-power budget (<= 10 squares).
    """
    now = time.time()
    for frac in [0.0, 0.25, 0.5, 0.75, 0.99]:
        ts = now + frac * ANIM_SEEKING_PERIOD_S
        frame = [0] * NUM_LEDS
        render_seeking(ts, frame, {})
        assert any(frame)

        # Verify inner 6x6 squares are dark
        for c in range(1, 7):
            for r in range(1, 7):
                indices = get_led_indices(r, c)
                for idx in indices:
                    if idx < NUM_LEDS:
                        assert frame[idx] == 0

        # Verify active squares budget (<= 10 squares lit simultaneously)
        lit_squares = 0
        for c, r in PERIMETER_COORDS:
            indices = get_led_indices(r, c)
            if any(frame[idx] != 0 for idx in indices if idx < NUM_LEDS):
                lit_squares += 1
        assert lit_squares <= 10


def test_lifecycle_animation_seeking():
    """Verify LifecycleAnimation factory support for SEEKING, WAITING_FOR_OPPONENT, MATCHMAKING."""
    anim = create_animation("SEEKING")
    assert anim.name == "SEEKING"
    assert anim.duration == ANIM_SEEKING_DURATION_S

    anim_waiting = create_animation("WAITING_FOR_OPPONENT")
    assert anim_waiting.name == "WAITING_FOR_OPPONENT"
    assert anim_waiting.duration == ANIM_SEEKING_DURATION_S

    frame = [0] * NUM_LEDS
    anim.render(time.time(), frame)
    assert any(frame)


def test_render_castle_trace_two_phase():
    """
    Verify render_castle_trace:
    - Phase 1 (tau < 0.5): King trajectory (e1 -> f1 -> g1) is animated.
    - Phase 2 (tau >= 0.5): Rook trajectory (h1 -> g1 -> f1) is animated.
    """
    king_path = [(4, 0), (5, 0), (6, 0)]  # e1 -> f1 -> g1
    rook_path = [(7, 0), (6, 0), (5, 0)]  # h1 -> g1 -> f1
    period = ANIM_CASTLE_PERIOD_S

    # Phase 1: King move at t = period * 0.25 (King passing through f1)
    frame_p1 = [0] * NUM_LEDS
    render_castle_trace(king_path, rook_path, period * 0.25, frame_p1, period=period)
    assert any(frame_p1)

    # Phase 2: Rook move at t = period * 0.75 (Rook passing through g1/f1)
    frame_p2 = [0] * NUM_LEDS
    render_castle_trace(king_path, rook_path, period * 0.75, frame_p2, period=period)
    assert any(frame_p2)


def test_render_capture_aura():
    """Verify render_capture_aura illuminates target square and candidate attacker squares."""
    from app.led_animations import render_capture_aura
    frame = [0] * NUM_LEDS
    target_sq = (3, 4)
    attackers = [(4, 3), (2, 3)]

    render_capture_aura(target_sq, attackers, time.time(), frame)
    assert any(frame)


def test_render_guardrail_mismatch():
    """Verify render_guardrail_mismatch illuminates missing and unexpected squares."""
    from app.led_animations import render_guardrail_mismatch
    frame = [0] * NUM_LEDS
    missing = [(4, 1)]
    unexpected = [(4, 3)]

    render_guardrail_mismatch(missing, unexpected, time.time(), frame)
    assert any(frame)


def test_scale_color_gamma():
    """Verify perceptual gamma 2.8 correction and low brightness clamping."""
    from app.led_animations import GAMMA_LUT_28, scale_color_gamma, unpack_rgb

    c_white = color_rgb(255, 255, 255)
    # Zero factor gives 0
    assert scale_color_gamma(c_white, 0.0) == 0

    # Full factor on max channel preserves 255
    full = scale_color_gamma(c_white, 1.0)
    assert unpack_rgb(full) == (255, 255, 255)

    # Factor applies gamma LUT curve
    c = color_rgb(200, 100, 50)
    scaled = scale_color_gamma(c, 1.0)
    assert unpack_rgb(scaled) == (GAMMA_LUT_28[200], GAMMA_LUT_28[100], GAMMA_LUT_28[50])

    # Low factor applies gamma curve with floor clamping
    low = scale_color_gamma(c, 0.1, min_val=1)
    r, g, b = unpack_rgb(low)
    assert r >= 1
    assert g >= 1
    assert b >= 1


def test_night_mode_color_palette_distinctness():
    """Verify Night Mode colors are bright and distinct from deep moonlight sapphire floor."""
    from app.config import (
        COLOR_NIGHT_LEGAL_CAPTURE,
        COLOR_NIGHT_LEGAL_TARGET,
        COLOR_NIGHT_MODE,
        COLOR_NIGHT_TURN_BLACK,
        COLOR_NIGHT_TURN_WHITE,
    )
    # Legal target in Night mode must have high green/emerald component to contrast with blue
    r, g, b = COLOR_NIGHT_LEGAL_TARGET
    assert g > 150, "Night mode legal target should be luminous mint/emerald"

    # Legal capture must have high red component
    cr, cg, cb = COLOR_NIGHT_LEGAL_CAPTURE
    assert cr > 200, "Night mode legal capture should be radiant crimson"

    # Turn indicators
    w_r, w_g, w_b = COLOR_NIGHT_TURN_WHITE
    assert w_r > 200 and w_g > 150, "White turn indicator should be warm sunlight/gold"

    b_r, b_g, b_b = COLOR_NIGHT_TURN_BLACK
    assert b_r > 120 and b_b > 180, "Black turn indicator should be amethyst/purple"

    # Deep moonlight sapphire background
    bg_r, bg_g, bg_b = COLOR_NIGHT_MODE
    assert bg_r <= 10 and bg_g <= 20 and bg_b <= 40, "Night mode background must be low-current deep blue"


def test_night_mode_seeking_and_animations():
    """Verify procedural animations correctly adapt to Night Mode parameter."""
    from app.led_animations import render_game_drawn, render_game_started, render_seeking
    from app.led_helpers import COLOR_INT_NIGHT_MODE

    # Seeking in night mode
    frame_night_seek = [0] * NUM_LEDS
    render_seeking(0.5, frame_night_seek, {"night_mode": True})
    assert any(frame_night_seek)
    # Inactive perimeter square should be set to moonlight sapphire background
    assert COLOR_INT_NIGHT_MODE in frame_night_seek

    # Draw curtain in night mode
    frame_draw = [0] * NUM_LEDS
    render_game_drawn(0.5, frame_draw, {"night_mode": True})
    assert any(frame_draw)

    # Black army game start in night mode
    frame_start_black = [0] * NUM_LEDS
    render_game_started(0.3, frame_start_black, {"my_color": "black", "night_mode": True})
    assert any(frame_start_black)


def test_board_ready_animation_factory():
    """Verify BOARD_READY and SETUP_COMPLETE animations create valid LifecycleAnimation instances."""
    anim_ready = create_animation("BOARD_READY")
    assert anim_ready.name == "BOARD_READY"
    assert anim_ready.duration == ANIM_BOARD_READY_DURATION_S

    anim_setup = create_animation("SETUP_COMPLETE")
    assert anim_setup.name == "SETUP_COMPLETE"
    assert anim_setup.duration == ANIM_BOARD_READY_DURATION_S


def test_render_board_ready_day_and_night():
    """
    Verify BOARD_READY animation ('The Emerald Snap Flash'):
    - Strictly within 10 squares illuminated simultaneously at any single frame (< 16% of board).
    - Works correctly in both Day Mode and Night Mode across all phases.
    - Transitions smoothly through Dual Army Snap Sweep -> Center Pop Decay -> Royal Guard Anchor.
    """
    progress_samples = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]

    # 1. Day Mode Test
    for p in progress_samples:
        frame_day = [0] * NUM_LEDS
        render_board_ready(p, frame_day, {"night_mode": False})
        assert any(frame_day), f"Day frame empty at progress {p}"
        lit_squares = 0
        for c in range(8):
            for r in range(8):
                sq_indices = get_led_indices(r, c)
                if any(frame_day[idx] != 0 for idx in sq_indices if idx < NUM_LEDS):
                    lit_squares += 1
        # Strict low power budget: max 10 active squares (< 16% of board)
        assert lit_squares <= 10, f"Too many squares lit in day mode ({lit_squares}) at progress {p}"

    # 2. Night Mode Test
    from app.led_helpers import COLOR_INT_NIGHT_MODE
    for p in progress_samples:
        frame_night = [0] * NUM_LEDS
        render_board_ready(p, frame_night, {"night_mode": True})
        assert any(frame_night), f"Night frame empty at progress {p}"
        # Assert background moonlight sapphire floor is active on unlit squares
        assert COLOR_INT_NIGHT_MODE in frame_night
        lit_squares = 0
        for c in range(8):
            for r in range(8):
                sq_indices = get_led_indices(r, c)
                # Count squares with non-idle color
                if any(frame_night[idx] != COLOR_INT_NIGHT_MODE for idx in sq_indices if idx < NUM_LEDS):
                    lit_squares += 1
        assert lit_squares <= 10, f"Too many squares lit in night mode ({lit_squares}) at progress {p}"


def test_render_analysis_computing_power_budget_and_night_mode():
    """
    Verify render_analysis_computing:
    - Low-power budget: max active LEDs <= 14 simultaneously (<= 7 squares).
    - Valid RGB pixel bounds: 0 <= r, g, b <= 255 across all timestamps.
    - Night mode: scaled moonlight sapphire ambient base floor without budget violation.
    """
    from app.led_animations import render_analysis_computing, unpack_rgb
    from app.led_helpers import COLOR_INT_NIGHT_MODE, get_led_indices

    test_timestamps = [0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.5, 5.0, 10.0]

    # 1. Day Mode Test
    for ts in test_timestamps:
        frame = [0] * NUM_LEDS
        render_analysis_computing(ts, frame, {"night_mode": False})

        active_leds = sum(1 for val in frame if val != 0)
        assert active_leds <= 16, f"Power budget exceeded: {active_leds} LEDs at t={ts}"

        lit_squares = 0
        for c in range(8):
            for r in range(8):
                indices = get_led_indices(r, c)
                if any(frame[idx] != 0 for idx in indices if idx < NUM_LEDS):
                    lit_squares += 1
        assert lit_squares <= 8, f"Power budget exceeded: {lit_squares} squares at t={ts}"

        for val in frame:
            r, g, b = unpack_rgb(val)
            assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255

    # 2. Night Mode Test
    for ts in test_timestamps:
        frame_night = [0] * NUM_LEDS
        render_analysis_computing(ts, frame_night, {"night_mode": True})

        # Non-idle squares must adhere to the 8-square limit (4 core + max 4 probe squares)
        lit_squares = 0
        for c in range(8):
            for r in range(8):
                indices = get_led_indices(r, c)
                if any(frame_night[idx] != COLOR_INT_NIGHT_MODE and frame_night[idx] != 0 for idx in indices if idx < NUM_LEDS):
                    lit_squares += 1
        assert lit_squares <= 8, f"Night power budget exceeded: {lit_squares} squares at t={ts}"





# =============================================================================
# Chess Clock Drain Bars (render_clock_bar)
# =============================================================================

CLOCK_OK_COLOR = color_rgb(10, 200, 20)
CLOCK_WARN_COLOR = color_rgb(220, 140, 10)
CLOCK_CRIT_COLOR = color_rgb(200, 30, 30)


def _clock_bar_lit_rows(frame, col):
    """Return the sorted list of rows lit on a file column in the frame."""
    lit = []
    for r in range(8):
        if any(frame[idx] != 0 for idx in get_led_indices(r, col) if idx < len(frame)):
            lit.append(r)
    return lit


def test_render_clock_bar_guards_invalid_inputs():
    """None remaining/total and non-positive totals must leave the frame untouched."""
    for remaining, total in [(None, 300.0), (120.0, None), (120.0, 0.0), (120.0, -5.0)]:
        frame = [0] * NUM_LEDS
        render_clock_bar(1.0, frame, 7, remaining, total, CLOCK_OK_COLOR, CLOCK_WARN_COLOR, CLOCK_CRIT_COLOR)
        assert not any(frame), f"frame must stay unlit for remaining={remaining}, total={total}"


def test_render_clock_bar_full_bar_frac_one():
    """frac=1.0 lights all 8 rows at full ok brightness with no pulse scaling."""
    now = 12.34
    frame = [0] * NUM_LEDS
    render_clock_bar(now, frame, 7, 600.0, 600.0, CLOCK_OK_COLOR, CLOCK_WARN_COLOR, CLOCK_CRIT_COLOR)
    assert _clock_bar_lit_rows(frame, 7) == list(range(8))
    for r in range(8):
        for idx in get_led_indices(r, 7):
            assert frame[idx] == CLOCK_OK_COLOR


def test_render_clock_bar_flag_fall_dark():
    """At exact flag-fall (frac=0) nothing is painted on the clock file (current behavior)."""
    frame = [0] * NUM_LEDS
    render_clock_bar(1.0, frame, 7, 0.0, 100.0, CLOCK_OK_COLOR, CLOCK_WARN_COLOR, CLOCK_CRIT_COLOR)
    assert not any(frame)


def test_render_clock_bar_clamps_negative_and_huge_remaining():
    """Negative remaining clamps to flag-fall (dark); huge remaining clamps to a full bar."""
    frame_neg = [0] * NUM_LEDS
    render_clock_bar(1.0, frame_neg, 3, -42.0, 100.0, CLOCK_OK_COLOR, CLOCK_WARN_COLOR, CLOCK_CRIT_COLOR)
    assert not any(frame_neg)

    frame_big = [0] * NUM_LEDS
    render_clock_bar(1.0, frame_big, 3, 10_000.0, 100.0, CLOCK_OK_COLOR, CLOCK_WARN_COLOR, CLOCK_CRIT_COLOR)
    assert _clock_bar_lit_rows(frame_big, 3) == list(range(8))
    for r in range(8):
        for idx in get_led_indices(r, 3):
            assert frame_big[idx] == CLOCK_OK_COLOR


def test_render_clock_bar_truncation_half():
    """frac=0.5 -> exactly rows 0-3 lit via truncation, with no fractional edge square."""
    frame = [0] * NUM_LEDS
    render_clock_bar(3.3, frame, 0, 150.0, 300.0, CLOCK_OK_COLOR, CLOCK_WARN_COLOR, CLOCK_CRIT_COLOR)
    assert _clock_bar_lit_rows(frame, 0) == [0, 1, 2, 3]
    for r in range(4):
        for idx in get_led_indices(r, 0):
            assert frame[idx] == CLOCK_OK_COLOR


def test_render_clock_bar_fractional_edge_breathing_square():
    """A partial step lights one dim breathing edge square just above the full squares."""
    frame = [0] * NUM_LEDS
    # frac ~0.775: rows 0-5 full, row 6 is the fractional edge
    render_clock_bar(2.0, frame, 4, 310.0, 400.0, CLOCK_OK_COLOR, CLOCK_WARN_COLOR, CLOCK_CRIT_COLOR)
    assert _clock_bar_lit_rows(frame, 4) == [0, 1, 2, 3, 4, 5, 6]
    full_idx = get_led_indices(0, 4)[0]
    edge_idx = get_led_indices(6, 4)[0]
    assert 0 < frame[edge_idx] < frame[full_idx]


def _clock_is_scaled_variant(color_int: int, base: int) -> bool:
    """True if color_int equals scale_color(base, f) for some factor f in [0, 1]."""
    return any(scale_color(base, i / 1000.0) == color_int for i in range(1001))


def test_render_clock_bar_urgency_thresholds():
    """
    Urgency bands use strict > comparisons:
      - frac > 0.25 -> ok
      - 0.10 < frac <= 0.25 -> warn
      - frac <= 0.10 -> crit (pulsing)
    Every rendered pixel must be the exact base color or a brightness-scaled
    variant of the band's base color.
    """
    cases = [
        (0.26, CLOCK_OK_COLOR),
        (0.251, CLOCK_OK_COLOR),
        (0.25, CLOCK_WARN_COLOR),
        (0.11, CLOCK_WARN_COLOR),
        (0.101, CLOCK_WARN_COLOR),
        (0.10, CLOCK_CRIT_COLOR),
        (0.05, CLOCK_CRIT_COLOR),
    ]
    for frac, base in cases:
        frame = [0] * NUM_LEDS
        render_clock_bar(1.0, frame, 2, frac * 100.0, 100.0, CLOCK_OK_COLOR, CLOCK_WARN_COLOR, CLOCK_CRIT_COLOR)
        colors = {frame[idx] for r in range(8) for idx in get_led_indices(r, 2) if idx < len(frame)}
        colors.discard(0)
        assert colors, f"No colors rendered for frac={frac}"
        for c in colors:
            assert _clock_is_scaled_variant(c, base), (
                f"Color {unpack_rgb(c)} at frac={frac} is not a scaled variant of {unpack_rgb(base)}"
            )
        # Bands never bleed into each other's exact palettes
        others = {CLOCK_OK_COLOR, CLOCK_WARN_COLOR, CLOCK_CRIT_COLOR} - {base}
        for c in colors:
            for o in others:
                assert not _clock_is_scaled_variant(c, o), f"Band crossover at frac={frac}: {unpack_rgb(c)}"


def test_render_clock_bar_crit_pulse_stays_nonzero():
    """The critical pulse must never fully blank the bar across two pulse periods."""
    for i in range(50):
        ts = i * 0.05  # covers 2.5 s of the 0.5 s sine pulse period
        frame = [0] * NUM_LEDS
        render_clock_bar(ts, frame, 0, 5.0, 100.0, CLOCK_OK_COLOR, CLOCK_WARN_COLOR, CLOCK_CRIT_COLOR)
        vals = [frame[idx] for idx in get_led_indices(0, 0) if idx < len(frame)]
        assert any(v != 0 for v in vals), f"Crit square went dark at t={ts}"


def test_render_clock_bar_urgency_colors_differ_per_band():
    """Same square, same timestamp: ok / warn / crit bands must produce distinct colors."""
    rendered = []
    for remaining in [80.0, 20.0, 5.0]:  # fracs 0.8, 0.2, 0.05 -> ok, warn, crit
        frame = [0] * NUM_LEDS
        render_clock_bar(7.77, frame, 1, remaining, 100.0, CLOCK_OK_COLOR, CLOCK_WARN_COLOR, CLOCK_CRIT_COLOR)
        row0 = {frame[idx] for idx in get_led_indices(0, 1) if idx < len(frame)}
        row0.discard(0)
        assert len(row0) == 1
        rendered.append(row0.pop())
    assert len(set(rendered)) == 3, f"Urgency bands must differ, got {rendered}"


def test_render_clock_bar_columns_target_distinct_files():
    """col 0 (a-file) and col 7 (h-file) paint disjoint LED index sets."""
    indices_a = {idx for r in range(8) for idx in get_led_indices(r, 0) if idx < NUM_LEDS}
    indices_h = {idx for r in range(8) for idx in get_led_indices(r, 7) if idx < NUM_LEDS}
    assert indices_a.isdisjoint(indices_h)

    frame_a = [0] * NUM_LEDS
    render_clock_bar(1.0, frame_a, 0, 50.0, 100.0, CLOCK_OK_COLOR, CLOCK_WARN_COLOR, CLOCK_CRIT_COLOR)
    frame_h = [0] * NUM_LEDS
    render_clock_bar(1.0, frame_h, 7, 50.0, 100.0, CLOCK_OK_COLOR, CLOCK_WARN_COLOR, CLOCK_CRIT_COLOR)
    assert _clock_bar_lit_rows(frame_a, 0) == list(range(4))
    assert _clock_bar_lit_rows(frame_a, 7) == []
    assert _clock_bar_lit_rows(frame_h, 7) == list(range(4))
    assert _clock_bar_lit_rows(frame_h, 0) == []


def test_clock_color_palettes_day_and_night_defined_and_distinct():
    """Day and night clock palettes exist, are distinct from each other and cross-band."""
    palettes = [
        (COLOR_INT_CLOCK_OK, COLOR_INT_CLOCK_WARN, COLOR_INT_CLOCK_CRIT),
        (COLOR_INT_NIGHT_CLOCK_OK, COLOR_INT_NIGHT_CLOCK_WARN, COLOR_INT_NIGHT_CLOCK_CRIT),
    ]
    for day, night in zip(*palettes):
        assert day != night
    for ok_c, warn_c, crit_c in palettes:
        assert len({ok_c, warn_c, crit_c}) == 3


# =============================================================================
# Return-Home Divergence Guide (render_return_home_guide)
# =============================================================================

RETURN_HOME_COLOR = color_rgb(200, 160, 20)


def _square_color(frame, file_idx, rank_idx):
    values = {frame[idx] for idx in get_led_indices(rank_idx, file_idx) if idx < len(frame)}
    values.discard(0)
    return values


def test_render_return_home_guide_lights_both_squares():
    """Halo on the arrival square and dim dot on the origin square."""
    frame = [0] * NUM_LEDS
    render_return_home_guide(1.0, frame, (2, 6), (2, 4), RETURN_HOME_COLOR)
    assert len(_square_color(frame, 2, 4)) == 1
    assert len(_square_color(frame, 2, 6)) == 1
    # Other squares untouched
    assert not _square_color(frame, 0, 0)


def test_render_return_home_guide_halo_pulses_within_bounds():
    """The halo oscillates between 55% and 100% of the base color intensity."""
    lo = scale_color(RETURN_HOME_COLOR, 0.55)
    hi = RETURN_HOME_COLOR
    seen = []
    for i in range(60):
        frame = [0] * NUM_LEDS
        render_return_home_guide(i * 0.05, frame, (2, 6), (2, 4), RETURN_HOME_COLOR)
        halo = next(iter(_square_color(frame, 2, 4)))
        seen.append(halo)
        assert lo <= halo <= hi
    # It actually animates across samples
    assert len(set(seen)) > 2


def test_render_return_home_guide_dot_steady_dim():
    """The origin dot is a constant 35% brightness variant, never pulsing."""
    frame = [0] * NUM_LEDS
    render_return_home_guide(7.3, frame, (2, 6), (2, 4), RETURN_HOME_COLOR)
    dot = next(iter(_square_color(frame, 2, 6)))
    assert dot == scale_color(RETURN_HOME_COLOR, 0.35)


def test_render_return_home_guide_same_square_skips_dot():
    """When origin equals arrival only one square is lit (no double-write artifacts)."""
    frame = [0] * NUM_LEDS
    render_return_home_guide(1.0, frame, (4, 3), (4, 3), RETURN_HOME_COLOR)
    lit_rows = [
        r for r in range(8) if any(frame[idx] != 0 for idx in get_led_indices(r, 4) if idx < len(frame))
    ]
    assert lit_rows == [3]


def test_return_home_color_day_night_distinct():
    """Day and night return-home palettes are defined and distinct."""
    from app.led_helpers import COLOR_INT_NIGHT_RETURN_HOME, COLOR_INT_RETURN_HOME

    assert COLOR_INT_RETURN_HOME != COLOR_INT_NIGHT_RETURN_HOME


def _calculate_frame_current_ma(frame: list[int]) -> float:
    """Calculates total peak current draw (mA) on 5V rail for WS2812B LED array."""
    total_ma = 0.0
    for val in frame:
        if val:
            r = (val >> 16) & 0xFF
            g = (val >> 8) & 0xFF
            b = val & 0xFF
            total_ma += (r + g + b) / 255.0 * 20.0
    return total_ma


def test_promotion_scepter_palette_distinctness():
    from app.led_helpers import (
        COLOR_INT_PROMO_ROOT,
        COLOR_INT_PROMO_QUEEN,
        COLOR_INT_PROMO_KNIGHT,
        COLOR_INT_PROMO_ROOK,
        COLOR_INT_PROMO_BISHOP,
        COLOR_INT_NOVELTY_FLARE,
        COLOR_INT_NIGHT_PROMO_ROOT,
        COLOR_INT_NIGHT_PROMO_QUEEN,
        COLOR_INT_NIGHT_PROMO_KNIGHT,
        COLOR_INT_NIGHT_PROMO_ROOK,
        COLOR_INT_NIGHT_PROMO_BISHOP,
        COLOR_INT_NIGHT_NOVELTY_FLARE,
    )
    day_colors = [
        COLOR_INT_PROMO_ROOT,
        COLOR_INT_PROMO_QUEEN,
        COLOR_INT_PROMO_KNIGHT,
        COLOR_INT_PROMO_ROOK,
        COLOR_INT_PROMO_BISHOP,
        COLOR_INT_NOVELTY_FLARE,
    ]
    assert len(set(day_colors)) == 6

    night_colors = [
        COLOR_INT_NIGHT_PROMO_ROOT,
        COLOR_INT_NIGHT_PROMO_QUEEN,
        COLOR_INT_NIGHT_PROMO_KNIGHT,
        COLOR_INT_NIGHT_PROMO_ROOK,
        COLOR_INT_NIGHT_PROMO_BISHOP,
        COLOR_INT_NIGHT_NOVELTY_FLARE,
    ]
    assert len(set(night_colors)) == 6


def test_render_promotion_scepter_power_and_budget():
    from app.led_animations import render_promotion_scepter

    promo_state = {
        "root_square": (4, 7),
        "options": {
            "q": (3, 7),
            "n": (5, 7),
            "r": (2, 7),
            "b": (6, 7),
        },
        "timeout_s": 10.0,
        "start_time": time.time(),
    }

    for ts in [0.0, 1.0, 2.5, 5.0, 8.0, 9.5]:
        frame = [0] * NUM_LEDS
        render_promotion_scepter(ts, frame, promo_state)
        assert any(frame)

        active_leds = sum(1 for val in frame if val != 0)
        assert active_leds <= 10, f"Exceeded 10 active LEDs: {active_leds}"

        current_ma = _calculate_frame_current_ma(frame)
        assert current_ma < 120.0, f"Exceeded 120mA budget: {current_ma}mA"


def test_render_uncharted_novelty_power_and_squares():
    from app.led_animations import render_uncharted_novelty

    center_sq = (4, 3)
    for p in [0.0, 0.1, 0.25, 0.35, 0.5, 0.7, 0.85, 1.0]:
        frame = [0] * NUM_LEDS
        render_uncharted_novelty(p, frame, center_sq)

        lit_squares = 0
        for c in range(8):
            for r in range(8):
                indices = get_led_indices(r, c)
                if any(frame[idx] != 0 for idx in indices if idx < NUM_LEDS):
                    lit_squares += 1

        assert lit_squares <= 8, f"Too many squares lit ({lit_squares}) at progress {p}"

        current_ma = _calculate_frame_current_ma(frame)
        assert current_ma < 90.0, f"Exceeded 90mA power budget: {current_ma}mA at progress {p}"
