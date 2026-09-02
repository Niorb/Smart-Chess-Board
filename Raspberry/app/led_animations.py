"""
app/led_animations.py

Procedural WS2812B LED animation engine and frame renderers for the Smart Chess Board.
Provides lifecycle animations (GAME_STARTED, GAME_WON, GAME_LOST, GAME_DRAWN)
and dynamic comet move-trace interpolation.
"""

import math
import time
from dataclasses import dataclass, field
from typing import Any

try:
    from app.config import (
        ANIM_ANALYSIS_COMPUTING_DURATION_S,
        ANIM_BOARD_READY_DURATION_S,
        ANIM_CASTLE_PERIOD_S,
        ANIM_GAME_DRAWN_DURATION_S,
        ANIM_GAME_LOST_DURATION_S,
        ANIM_GAME_START_DURATION_S,
        ANIM_GAME_WON_DURATION_S,
        ANIM_RECALL_COMPLETE_DURATION_S,
        ANIM_RECALL_START_DURATION_S,
        ANIM_SEEKING_DURATION_S,
        ANIM_SEEKING_PERIOD_S,
        MOVE_TRACE_PERIOD_S,
    )
    from app.led_helpers import (
        COLOR_INT_AZURE,
        COLOR_INT_BOARD_READY_AMBIENT,
        COLOR_INT_BOARD_READY_PRIMARY,
        COLOR_INT_BOARD_READY_SECONDARY,
        COLOR_INT_CAPTURE_AURA_ATTACKER,
        COLOR_INT_CAPTURE_AURA_TARGET,
        COLOR_INT_DRAW_EQUILIBRIUM,
        COLOR_INT_DRAW_PEARL,
        COLOR_INT_DRAW_SAPPHIRE,
        COLOR_INT_DRAW_TWILIGHT,
        COLOR_INT_DRAW_WHITE,
        COLOR_INT_ECLIPSE_ASH,
        COLOR_INT_ECLIPSE_CRIMSON,
        COLOR_INT_ECLIPSE_EMBER,
        COLOR_INT_ECLIPSE_FLASH,
        COLOR_INT_ECLIPSE_GARNET,
        COLOR_INT_ECLIPSE_GOLD,
        COLOR_INT_ECLIPSE_RUBY,
        COLOR_INT_GUARDRAIL_MISSING,
        COLOR_INT_GUARDRAIL_UNEXPECTED,
        COLOR_INT_MOVE_TRACE,
        COLOR_INT_NIGHT_AZURE,
        COLOR_INT_NIGHT_BOARD_READY_AMBIENT,
        COLOR_INT_NIGHT_BOARD_READY_PRIMARY,
        COLOR_INT_NIGHT_BOARD_READY_SECONDARY,
        COLOR_INT_NIGHT_DRAW_EQUILIBRIUM,
        COLOR_INT_NIGHT_DRAW_PEARL,
        COLOR_INT_NIGHT_DRAW_SAPPHIRE,
        COLOR_INT_NIGHT_DRAW_TWILIGHT,
        COLOR_INT_NIGHT_ECLIPSE_CRIMSON,
        COLOR_INT_NIGHT_ECLIPSE_EMBER,
        COLOR_INT_NIGHT_ECLIPSE_FLASH,
        COLOR_INT_NIGHT_ECLIPSE_GARNET,
        COLOR_INT_NIGHT_ECLIPSE_GOLD,
        COLOR_INT_NIGHT_ECLIPSE_RUBY,
        COLOR_INT_NIGHT_GUARDRAIL_UNEXPECTED,
        COLOR_INT_NIGHT_MINT_EMERALD,
        COLOR_INT_NIGHT_MODE,
        COLOR_INT_NIGHT_NOVELTY_FLARE,
        COLOR_INT_NIGHT_PIECE_BISHOP,
        COLOR_INT_NIGHT_PIECE_KING,
        COLOR_INT_NIGHT_PIECE_KNIGHT,
        COLOR_INT_NIGHT_PIECE_PAWN,
        COLOR_INT_NIGHT_PIECE_QUEEN,
        COLOR_INT_NIGHT_PIECE_ROOK,
        COLOR_INT_NIGHT_PROMO_BISHOP,
        COLOR_INT_NIGHT_PROMO_KNIGHT,
        COLOR_INT_NIGHT_PROMO_QUEEN,
        COLOR_INT_NIGHT_PROMO_ROOK,
        COLOR_INT_NIGHT_PROMO_ROOT,
        COLOR_INT_NIGHT_RESIGN_HALO,
        COLOR_INT_NIGHT_RESIGN_PRIMARY,
        COLOR_INT_NIGHT_ROYAL_VIOLET,
        COLOR_INT_NIGHT_SEEKING_BODY,
        COLOR_INT_NIGHT_SEEKING_HEAD,
        COLOR_INT_NIGHT_SEEKING_TAIL,
        COLOR_INT_NIGHT_SETUP_MISPLACED,
        COLOR_INT_NIGHT_START_BLACK_PRIMARY,
        COLOR_INT_NIGHT_START_BLACK_SECONDARY,
        COLOR_INT_NIGHT_TURN_WHITE,
        COLOR_INT_NOVELTY_FLARE,
        COLOR_INT_OFF,
        COLOR_INT_OPPONENT_DISCONNECTED,
        COLOR_INT_PIECE_BISHOP,
        COLOR_INT_PIECE_KING,
        COLOR_INT_PIECE_KNIGHT,
        COLOR_INT_PIECE_PAWN,
        COLOR_INT_PIECE_QUEEN,
        COLOR_INT_PIECE_ROOK,
        COLOR_INT_PROMO_BISHOP,
        COLOR_INT_PROMO_KNIGHT,
        COLOR_INT_PROMO_QUEEN,
        COLOR_INT_PROMO_ROOK,
        COLOR_INT_PROMO_ROOT,
        COLOR_INT_RESIGN_HALO,
        COLOR_INT_RESIGN_PRIMARY,
        COLOR_INT_ROYAL_VIOLET,
        COLOR_INT_SEEKING_BODY,
        COLOR_INT_SEEKING_HEAD,
        COLOR_INT_SEEKING_TAIL,
        COLOR_INT_SETUP_MISPLACED,
        COLOR_INT_START_BLACK_PRIMARY,
        COLOR_INT_START_BLACK_SECONDARY,
        COLOR_INT_START_WHITE_PRIMARY,
        COLOR_INT_START_WHITE_SECONDARY,
        COLOR_INT_VICTORY_GOLD,
        COLOR_INT_VICTORY_GREEN,
        get_led_indices,
    )
except ImportError:
    from .config import (
        ANIM_ANALYSIS_COMPUTING_DURATION_S,
        ANIM_BOARD_READY_DURATION_S,
        ANIM_CASTLE_PERIOD_S,
        ANIM_GAME_DRAWN_DURATION_S,
        ANIM_GAME_LOST_DURATION_S,
        ANIM_GAME_START_DURATION_S,
        ANIM_GAME_WON_DURATION_S,
        ANIM_RECALL_COMPLETE_DURATION_S,
        ANIM_RECALL_START_DURATION_S,
        ANIM_SEEKING_DURATION_S,
        ANIM_SEEKING_PERIOD_S,
        MOVE_TRACE_PERIOD_S,
    )
    from .led_helpers import (
        COLOR_INT_AZURE,
        COLOR_INT_BOARD_READY_AMBIENT,
        COLOR_INT_BOARD_READY_PRIMARY,
        COLOR_INT_BOARD_READY_SECONDARY,
        COLOR_INT_CAPTURE_AURA_ATTACKER,
        COLOR_INT_CAPTURE_AURA_TARGET,
        COLOR_INT_DRAW_EQUILIBRIUM,
        COLOR_INT_DRAW_PEARL,
        COLOR_INT_DRAW_SAPPHIRE,
        COLOR_INT_DRAW_TWILIGHT,
        COLOR_INT_DRAW_WHITE,
        COLOR_INT_ECLIPSE_ASH,
        COLOR_INT_ECLIPSE_CRIMSON,
        COLOR_INT_ECLIPSE_EMBER,
        COLOR_INT_ECLIPSE_FLASH,
        COLOR_INT_ECLIPSE_GARNET,
        COLOR_INT_ECLIPSE_GOLD,
        COLOR_INT_ECLIPSE_RUBY,
        COLOR_INT_GUARDRAIL_MISSING,
        COLOR_INT_GUARDRAIL_UNEXPECTED,
        COLOR_INT_MOVE_TRACE,
        COLOR_INT_NIGHT_AZURE,
        COLOR_INT_NIGHT_BOARD_READY_AMBIENT,
        COLOR_INT_NIGHT_BOARD_READY_PRIMARY,
        COLOR_INT_NIGHT_BOARD_READY_SECONDARY,
        COLOR_INT_NIGHT_DRAW_EQUILIBRIUM,
        COLOR_INT_NIGHT_DRAW_PEARL,
        COLOR_INT_NIGHT_DRAW_SAPPHIRE,
        COLOR_INT_NIGHT_DRAW_TWILIGHT,
        COLOR_INT_NIGHT_ECLIPSE_CRIMSON,
        COLOR_INT_NIGHT_ECLIPSE_EMBER,
        COLOR_INT_NIGHT_ECLIPSE_FLASH,
        COLOR_INT_NIGHT_ECLIPSE_GARNET,
        COLOR_INT_NIGHT_ECLIPSE_GOLD,
        COLOR_INT_NIGHT_ECLIPSE_RUBY,
        COLOR_INT_NIGHT_GUARDRAIL_UNEXPECTED,
        COLOR_INT_NIGHT_MINT_EMERALD,
        COLOR_INT_NIGHT_MODE,
        COLOR_INT_NIGHT_NOVELTY_FLARE,
        COLOR_INT_NIGHT_PIECE_BISHOP,
        COLOR_INT_NIGHT_PIECE_KING,
        COLOR_INT_NIGHT_PIECE_KNIGHT,
        COLOR_INT_NIGHT_PIECE_PAWN,
        COLOR_INT_NIGHT_PIECE_QUEEN,
        COLOR_INT_NIGHT_PIECE_ROOK,
        COLOR_INT_NIGHT_PROMO_BISHOP,
        COLOR_INT_NIGHT_PROMO_KNIGHT,
        COLOR_INT_NIGHT_PROMO_QUEEN,
        COLOR_INT_NIGHT_PROMO_ROOK,
        COLOR_INT_NIGHT_PROMO_ROOT,
        COLOR_INT_NIGHT_RESIGN_HALO,
        COLOR_INT_NIGHT_RESIGN_PRIMARY,
        COLOR_INT_NIGHT_ROYAL_VIOLET,
        COLOR_INT_NIGHT_SEEKING_BODY,
        COLOR_INT_NIGHT_SEEKING_HEAD,
        COLOR_INT_NIGHT_SEEKING_TAIL,
        COLOR_INT_NIGHT_SETUP_MISPLACED,
        COLOR_INT_NIGHT_START_BLACK_PRIMARY,
        COLOR_INT_NIGHT_START_BLACK_SECONDARY,
        COLOR_INT_NIGHT_TURN_WHITE,
        COLOR_INT_NOVELTY_FLARE,
        COLOR_INT_OFF,
        COLOR_INT_OPPONENT_DISCONNECTED,
        COLOR_INT_PIECE_BISHOP,
        COLOR_INT_PIECE_KING,
        COLOR_INT_PIECE_KNIGHT,
        COLOR_INT_PIECE_PAWN,
        COLOR_INT_PIECE_QUEEN,
        COLOR_INT_PIECE_ROOK,
        COLOR_INT_PROMO_BISHOP,
        COLOR_INT_PROMO_KNIGHT,
        COLOR_INT_PROMO_QUEEN,
        COLOR_INT_PROMO_ROOK,
        COLOR_INT_PROMO_ROOT,
        COLOR_INT_RESIGN_HALO,
        COLOR_INT_RESIGN_PRIMARY,
        COLOR_INT_ROYAL_VIOLET,
        COLOR_INT_SEEKING_BODY,
        COLOR_INT_SEEKING_HEAD,
        COLOR_INT_SEEKING_TAIL,
        COLOR_INT_SETUP_MISPLACED,
        COLOR_INT_START_BLACK_PRIMARY,
        COLOR_INT_START_BLACK_SECONDARY,
        COLOR_INT_START_WHITE_PRIMARY,
        COLOR_INT_START_WHITE_SECONDARY,
        COLOR_INT_VICTORY_GOLD,
        COLOR_INT_VICTORY_GREEN,
        get_led_indices,
    )


# Precomputed Gamma 2.8 perceptual brightness correction table (exact 256 entries)
GAMMA_LUT_28 = bytes([round(255 * ((i / 255.0) ** 2.8)) for i in range(256)])


# =============================================================================
# COLOR ARITHMETIC HELPERS
# =============================================================================

def color_rgb(r: int, g: int, b: int) -> int:
    """Encodes R, G, B channels (0..255) into a 24-bit integer color."""
    return (max(0, min(255, int(r))) << 16) | (max(0, min(255, int(g))) << 8) | max(0, min(255, int(b)))


def unpack_rgb(color_int: int) -> tuple[int, int, int]:
    """Unpacks a 24-bit integer color into (R, G, B) tuple."""
    return (color_int >> 16) & 0xFF, (color_int >> 8) & 0xFF, color_int & 0xFF


def scale_color(color_int: int, factor: float) -> int:
    """Scales color brightness by a float factor (0.0 to 1.0) with proper rounding."""
    if factor <= 0.0:
        return 0
    factor = min(1.0, factor)
    r = round(((color_int >> 16) & 0xFF) * factor)
    g = round(((color_int >> 8) & 0xFF) * factor)
    b = round((color_int & 0xFF) * factor)
    return (r << 16) | (g << 8) | b


def scale_color_gamma(color_int: int, factor: float, min_val: int = 0) -> int:
    """Scales color intensity linearly and applies Gamma 2.8 perceptual correction."""
    if factor <= 0.0:
        return 0
    factor = min(1.0, factor)
    r_lin = min(255, round(((color_int >> 16) & 0xFF) * factor))
    g_lin = min(255, round(((color_int >> 8) & 0xFF) * factor))
    b_lin = min(255, round((color_int & 0xFF) * factor))

    r_out = GAMMA_LUT_28[r_lin]
    g_out = GAMMA_LUT_28[g_lin]
    b_out = GAMMA_LUT_28[b_lin]

    if min_val > 0:
        if r_lin > 0 and r_out < min_val:
            r_out = min_val
        if g_lin > 0 and g_out < min_val:
            g_out = min_val
        if b_lin > 0 and b_out < min_val:
            b_out = min_val

    return (r_out << 16) | (g_out << 8) | b_out


def blend_colors(c1: int, c2: int, factor: float) -> int:
    """Linear interpolation between c1 (factor=0.0) and c2 (factor=1.0) with proper rounding."""
    if factor <= 0.0:
        return c1
    if factor >= 1.0:
        return c2
    r1, g1, b1 = (c1 >> 16) & 0xFF, (c1 >> 8) & 0xFF, c1 & 0xFF
    r2, g2, b2 = (c2 >> 16) & 0xFF, (c2 >> 8) & 0xFF, c2 & 0xFF
    r = round(r1 + (r2 - r1) * factor)
    g = round(g1 + (g2 - g1) * factor)
    b = round(b1 + (b2 - b1) * factor)
    return (r << 16) | (g << 8) | b


def add_colors(c1: int, c2: int) -> int:
    """Adds two colors channel-wise with clamping at 255."""
    r1, g1, b1 = (c1 >> 16) & 0xFF, (c1 >> 8) & 0xFF, c1 & 0xFF
    r2, g2, b2 = (c2 >> 16) & 0xFF, (c2 >> 8) & 0xFF, c2 & 0xFF
    return color_rgb(min(255, r1 + r2), min(255, g1 + g2), min(255, b1 + b2))


def set_square_in_frame(frame: list[int], c: int, r: int, color_val: int) -> None:
    """Sets all physical LEDs belonging to square (c, r) in the frame buffer."""
    if 0 <= c < 8 and 0 <= r < 8:
        for idx in get_led_indices(r, c):
            if 0 <= idx < len(frame):
                frame[idx] = color_val


def blend_square_in_frame(frame: list[int], c: int, r: int, color_val: int, alpha: float) -> None:
    """Blends color_val into existing square LEDs in the frame buffer with opacity alpha."""
    if 0 <= c < 8 and 0 <= r < 8 and alpha > 0.0:
        for idx in get_led_indices(r, c):
            if 0 <= idx < len(frame):
                curr = frame[idx]
                frame[idx] = blend_colors(curr, color_val, alpha)


# =============================================================================
# MOVE TRACE RENDERER
# =============================================================================

def _render_sub_trace(
    path: list[tuple[int, int]],
    sub_tau: float,
    frame: list[int],
    trace_color: int,
    blend_arrival: bool,
) -> None:
    """Renders a single-trajectory moving comet pulse with destination arrival flare."""
    if len(path) < 2:
        return

    num_squares = len(path)
    num_steps = num_squares - 1
    delta_overshoot = 1.2
    total_span = num_steps + delta_overshoot
    comet_pos = max(0.0, min(1.0, sub_tau)) * total_span

    # Render comet tail across intermediate squares
    for i in range(1, num_steps):
        c, r = path[i]
        dist = abs(comet_pos - i)
        # Pulse intensity with Gaussian falloff (width ~ 0.9 squares)
        intensity = math.exp(-2.5 * dist * dist)
        if intensity > 0.02:
            scaled = scale_color(trace_color, intensity)
            if 0 <= c < 8 and 0 <= r < 8:
                for idx in get_led_indices(r, c):
                    if 0 <= idx < len(frame):
                        frame[idx] = add_colors(frame[idx], scaled)

    # Render arrival pulse flare on destination square
    c_arr, r_arr = path[num_steps]
    d_arr = abs(comet_pos - num_steps)
    intensity_arr = math.exp(-2.5 * d_arr * d_arr)
    if intensity_arr > 0.02 and blend_arrival:
        flare = scale_color(trace_color, intensity_arr * 0.85)
        if 0 <= c_arr < 8 and 0 <= r_arr < 8:
            for idx in get_led_indices(r_arr, c_arr):
                if 0 <= idx < len(frame):
                    frame[idx] = add_colors(frame[idx], flare)


def render_move_trace(
    path: list[tuple[int, int]],
    now: float,
    frame: list[int],
    trace_color: int = COLOR_INT_MOVE_TRACE,
    period: float = MOVE_TRACE_PERIOD_S,
    blend_arrival: bool = True,
) -> None:
    """Renders an animated comet pulse along a move trajectory path on top of an existing frame."""
    if len(path) < 2 or period <= 0:
        return
    tau = (now % period) / period  # 0.0 to 1.0
    _render_sub_trace(path, tau, frame, trace_color, blend_arrival)


def render_castle_trace(
    king_path: list[tuple[int, int]],
    rook_path: list[tuple[int, int]],
    now: float,
    frame: list[int],
    trace_color: int = COLOR_INT_MOVE_TRACE,
    period: float = ANIM_CASTLE_PERIOD_S,
    blend_arrival: bool = True,
) -> None:
    """Renders a choreographed 2-phase castling move animation."""
    if not king_path or not rook_path or period <= 0:
        return

    tau = (now % period) / period  # 0.0 to 1.0

    if tau < 0.5:
        sub_tau = tau * 2.0
        _render_sub_trace(king_path, sub_tau, frame, trace_color, blend_arrival)
    else:
        sub_tau = (tau - 0.5) * 2.0
        _render_sub_trace(rook_path, sub_tau, frame, trace_color, blend_arrival)


# =============================================================================
# PROCEDURAL LIFECYCLE RENDERERS
# =============================================================================

def render_game_started(progress: float, frame: list[int], params: dict[str, Any]) -> None:
    """
    GAME_STARTED animation:
    Choreographed, low-power color announcement and army ignition sequence.
    - Low power budget: Max 2-4 squares illuminated simultaneously (<6% board).
    - Color Announcement:
      * Playing White: Sweeping luminous warm ivory/gold beam across ranks 1 & 2 (White army),
        followed by a focused royal pulse on King (e1) and Queen (d1).
      * Playing Black: Sweeping cosmic electric cyan/sapphire beam across ranks 8 & 7 (Black army),
        followed by a focused royal pulse on King (e8) and Queen (d8).
      * Final battle line ignition: Dual spark pulses meeting at center battle squares (d4, e4).
    """
    my_color = str(params.get("my_color", "white")).lower()
    is_white = (my_color == "white")

    # 1. Path of 16 piece squares for player's army
    if is_white:
        # Ranks 1 and 2: a1->h1 then h2->a2
        army_path = [
            (0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0), (7, 0),
            (7, 1), (6, 1), (5, 1), (4, 1), (3, 1), (2, 1), (1, 1), (0, 1),
        ]
        primary_col = COLOR_INT_START_WHITE_PRIMARY
        secondary_col = COLOR_INT_START_WHITE_SECONDARY
        royal_squares = [(4, 0), (3, 0)]  # e1 (King), d1 (Queen)
        center_clash = [((3, 1), (3, 3)), ((4, 1), (4, 3))]  # d2->d4, e2->e4
    else:
        # Ranks 8 and 7: h8->a8 then a7->h7
        army_path = [
            (7, 7), (6, 7), (5, 7), (4, 7), (3, 7), (2, 7), (1, 7), (0, 7),
            (0, 6), (1, 6), (2, 6), (3, 6), (4, 6), (5, 6), (6, 6), (7, 6),
        ]
        if params.get("night_mode", False):
            primary_col = COLOR_INT_NIGHT_START_BLACK_PRIMARY
            secondary_col = COLOR_INT_NIGHT_START_BLACK_SECONDARY
        else:
            primary_col = COLOR_INT_START_BLACK_PRIMARY
            secondary_col = COLOR_INT_START_BLACK_SECONDARY
        royal_squares = [(4, 7), (3, 7)]  # e8 (King), d8 (Queen)
        center_clash = [((3, 6), (3, 4)), ((4, 6), (4, 4))]  # d7->d5, e7->e5

    # Phase 1 (progress 0.0 -> 0.60): Fast Lightning Army Ignition Sweep
    if progress < 0.60:
        p_sweep = progress / 0.60
        n_sq = len(army_path)
        head_pos = p_sweep * (n_sq - 1)
        for i, (c, r) in enumerate(army_path):
            dist = abs(i - head_pos)
            if dist < 2.0:
                intensity = math.exp(-2.5 * dist * dist)
                if intensity > 0.03:
                    col = blend_colors(primary_col, secondary_col, min(1.0, dist * 0.7))
                    set_square_in_frame(frame, c, r, scale_color(col, intensity * 0.95))

    # Phase 2 (progress 0.40 -> 0.85): Royal Focus Pulse on King & Queen
    if 0.40 <= progress <= 0.85:
        p_royal = (progress - 0.40) / 0.45
        royal_intensity = math.sin(p_royal * math.pi) * 0.95
        if royal_intensity > 0.03:
            for k_c, k_r in royal_squares:
                col = blend_colors(primary_col, COLOR_INT_DRAW_WHITE, 0.35)
                blend_square_in_frame(frame, k_c, k_r, scale_color(col, royal_intensity), 0.90)

    # Phase 3 (progress 0.70 -> 1.0): Battle Line Center Ignition
    if progress >= 0.70:
        p_center = (progress - 0.70) / 0.30
        for (from_c, from_r), (_to_c, to_r) in center_clash:
            curr_r = from_r + (to_r - from_r) * min(1.0, p_center * 1.4)
            for r_cand in range(min(from_r, to_r), max(from_r, to_r) + 1):
                dist = abs(r_cand - curr_r)
                if dist < 1.2:
                    spark_int = math.exp(-3.0 * dist * dist) * (1.0 - p_center * 0.5)
                    if spark_int > 0.03:
                        set_square_in_frame(frame, from_c, r_cand, scale_color(primary_col, spark_int * 0.7))


def render_game_won(
    progress: float, frame: list[int], params: dict[str, Any], now: float = 0.0
) -> None:
    """
    GAME_WON animation:
    Lightweight, high-contrast victory celebration featuring sweeping dual diagonal
    laser comets, sparse stardust twinkling, and a central diamond flare.

    Lighting budget: Only 3-6 squares active simultaneously at any frame (<10% of board).
    """
    if now == 0.0:
        now = time.time()

    # 1. Global Attack-Sustain-Release Envelope
    if progress < 0.08:
        envelope = progress / 0.08
    elif progress > 0.85:
        rel = (progress - 0.85) / 0.15
        envelope = 0.5 * (1.0 + math.cos(math.pi * rel))
    else:
        envelope = 1.0

    if envelope <= 0.001:
        for c in range(8):
            for r in range(8):
                set_square_in_frame(frame, c, r, COLOR_INT_OFF)
        return

    # Color definitions
    col_gold = COLOR_INT_VICTORY_GOLD
    col_green = COLOR_INT_VICTORY_GREEN
    col_sparkle = blend_colors(col_gold, 0xFFFFFF, 0.70)

    # 2. Phase Wavefront Positions
    # Phase 1: Diagonal sweep (a1 -> h8) for progress in [0.0, 0.45]
    p1 = progress / 0.45
    w1 = p1 * 18.0 - 2.0 if progress <= 0.45 else 99.0

    # Phase 2: Counter-diagonal sweep (a8 -> h1) for progress in [0.45, 0.82]
    p2 = (progress - 0.45) / 0.37
    w2 = p2 * 18.0 - 2.0 if 0.45 <= progress <= 0.82 else 99.0

    # Phase 3: Center Diamond Flare for progress in [0.80, 1.0]
    p3 = (progress - 0.80) / 0.20 if progress >= 0.80 else 0.0
    r3 = p3 * 2.4

    for c in range(8):
        for r in range(8):
            w1_val = 0.0
            w2_val = 0.0
            w3_val = 0.0

            # Phase 1: Diagonal Wavefront (sweeping beam along a1 -> h8)
            if progress <= 0.45:
                u1 = c + r
                v1 = c - r
                du1 = u1 - w1
                w1_val = math.exp(-4.5 * du1 * du1 - 0.25 * v1 * v1)

            # Phase 2: Counter-Diagonal Wavefront (sweeping beam along a8 -> h1)
            if 0.45 <= progress <= 0.82:
                u2 = c + (7 - r)
                v2 = c - (7 - r)
                du2 = u2 - w2
                w2_val = math.exp(-4.5 * du2 * du2 - 0.25 * v2 * v2)

            # Phase 3: Center Diamond Pulse
            if progress >= 0.80:
                dist_center = math.sqrt((c - 3.5) ** 2 + (r - 3.5) ** 2)
                dr = dist_center - r3
                w3_val = math.exp(-4.5 * dr * dr) * ((1.0 - p3) ** 2)

            # Primary wave composite
            w_total = w1_val + w2_val + w3_val
            if w_total > 0.001:
                # Color blending based on phase dominance
                blend_g = (w1_val * 0.3 + w2_val * 0.9) / w_total
                base_color = blend_colors(col_gold, col_green, blend_g)
            else:
                base_color = col_gold

            primary_intensity = w_total * envelope

            # 4. Sparse Stardust Twinkles (Only top ~1% threshold fires, 1-2 squares max)
            h1 = math.sin(now * 13.0 + c * 17.1 + r * 31.7)
            h2 = math.cos(now * 8.5 + c * 29.3 + r * 11.9)
            sparkle_harmonic = h1 * h2
            if sparkle_harmonic > 0.93:
                s_factor = ((sparkle_harmonic - 0.93) / 0.07) ** 2
                sparkle_intensity = s_factor * 0.80 * envelope
            else:
                sparkle_intensity = 0.0

            # 5. Final Composite & Deadband Gating
            total_intensity = primary_intensity + sparkle_intensity
            if total_intensity > 0.05:
                # Blend in diamond white-gold for sparkle contribution
                if sparkle_intensity > 0.001:
                    sparkle_ratio = sparkle_intensity / total_intensity
                    final_color = blend_colors(base_color, col_sparkle, sparkle_ratio)
                else:
                    final_color = base_color

                clamped_intensity = min(1.0, total_intensity)
                set_square_in_frame(frame, c, r, scale_color(final_color, clamped_intensity))
            else:
                set_square_in_frame(frame, c, r, COLOR_INT_OFF)


# =============================================================================
# REDESIGNED LIFECYCLE ANIMATIONS: GAME_LOST & GAME_DRAWN
# =============================================================================

def render_game_lost(
    progress: float, frame: list[int], params: dict[str, Any], now: float = 0.0
) -> None:
    """
    GAME_LOST animation: "The Sovereign's Eclipse"
    A unified, symmetrical 3-phase imperial cataclysm sequence operating across
    the entire 8x8 realm (identical visual drama for White and Black):

    - Phase 1: Inward Perimeter Collapse / The Closing Vice (0.00 <= progress < 0.35).
      Imperial shadow closing inward from the 28 perimeter squares to the central throne core.
    - Phase 2: Crown Fracture & Shatter Shockwave (0.35 <= progress < 0.70).
      White-hot crown detonation + expanding Gaussian ruby shockwave ring + 4 flying molten gold shards.
    - Phase 3: Smoldering Embers & Obsidian Dissolve (0.70 <= progress <= 1.00).
      Organic dual-harmonic flickering cinders + central dying cardiac hearth pulse fading into dark.

    Hardware Budget: <= 14 active squares peak (< 180mA on 5V rail).
    """
    if now == 0.0:
        now = time.time()

    is_night = bool(params.get("night_mode", False))
    col_flash = COLOR_INT_NIGHT_ECLIPSE_FLASH if is_night else COLOR_INT_ECLIPSE_FLASH
    col_gold = COLOR_INT_NIGHT_ECLIPSE_GOLD if is_night else COLOR_INT_ECLIPSE_GOLD
    col_ruby = COLOR_INT_NIGHT_ECLIPSE_RUBY if is_night else COLOR_INT_ECLIPSE_RUBY
    col_crimson = COLOR_INT_NIGHT_ECLIPSE_CRIMSON if is_night else COLOR_INT_ECLIPSE_CRIMSON
    col_garnet = COLOR_INT_NIGHT_ECLIPSE_GARNET if is_night else COLOR_INT_ECLIPSE_GARNET
    col_ember = COLOR_INT_NIGHT_ECLIPSE_EMBER if is_night else COLOR_INT_ECLIPSE_EMBER
    col_ash = COLOR_INT_NIGHT_MODE if is_night else COLOR_INT_ECLIPSE_ASH
    col_idle = COLOR_INT_NIGHT_MODE if is_night else COLOR_INT_OFF

    # Clear frame buffer
    for c in range(8):
        for r in range(8):
            set_square_in_frame(frame, c, r, col_idle)

    progress = max(0.0, min(1.0, progress))
    c0, r0 = 3.5, 3.5  # Symmetrical realm center

    # =========================================================================
    # PHASE 1: Inward Perimeter Collapse / The Closing Vice (0.00 -> 0.35)
    # =========================================================================
    if progress < 0.35:
        p1 = progress / 0.35  # 0.0 -> 1.0
        r_max = 4.95
        r_collapse = r_max * (1.0 - (p1 ** 1.15)) + 0.6
        sigma1 = 0.24 + 0.06 * (1.0 - p1)
        phase_int = 0.65 + 0.35 * (p1 ** 2)

        for c in range(8):
            for r in range(8):
                d_c = math.hypot(c - c0, r - r0)
                dr = abs(d_c - r_collapse)
                if dr < (sigma1 * 1.5):
                    w = math.exp(-(dr * dr) / (2.0 * sigma1 * sigma1)) * phase_int
                    if w > 0.18:
                        col = blend_colors(col_garnet, col_ruby, min(1.0, p1 ** 1.5))
                        set_square_in_frame(frame, c, r, scale_color(col, min(1.0, w)))

    # =========================================================================
    # PHASE 2: Crown Fracture & Shatter Shockwave (0.35 -> 0.70)
    # =========================================================================
    elif progress < 0.70:
        p2 = (progress - 0.35) / 0.35  # 0.0 -> 1.0

        # A. Central Crown Fracture Flash (Initial 25% of Phase 2)
        if p2 < 0.25:
            flash_p = p2 / 0.25
            flash_int = (1.0 - flash_p) ** 2
            flash_col = blend_colors(col_flash, col_gold, flash_p)
            for c in (3, 4):
                for r in (3, 4):
                    set_square_in_frame(frame, c, r, scale_color(flash_col, flash_int))

        # B. Expanding Gaussian Shockwave Ring
        r_shock = (p2 ** 0.82) * 5.8
        sigma2 = 0.28 + 0.12 * p2
        ring_decay = 1.0 - 0.55 * p2

        for c in range(8):
            for r in range(8):
                d_c = math.hypot(c - c0, r - r0)
                dr = abs(d_c - r_shock)
                if dr < (sigma2 * 1.6):
                    w = math.exp(-(dr * dr) / (2.0 * sigma2 * sigma2)) * ring_decay
                    if w > 0.15:
                        col = blend_colors(col_ruby, col_crimson, min(1.0, d_c / 4.5))
                        blend_square_in_frame(frame, c, r, scale_color(col, min(1.0, w)), 0.90)

        # C. 4 Flying Molten Gold Shards Along Diagonal Rays
        shard_dist = (p2 ** 0.75) * 4.8
        shard_int = (1.0 - p2) * 0.92
        shard_rays = [(-1.0, -1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0)]

        if shard_int > 0.10:
            shard_col = blend_colors(col_gold, col_ruby, p2 * 0.8)
            for dx, dy in shard_rays:
                sc = c0 + dx * 0.7071 * shard_dist
                sr = r0 + dy * 0.7071 * shard_dist
                sci, sri = int(round(sc)), int(round(sr))
                if 0 <= sci < 8 and 0 <= sri < 8:
                    blend_square_in_frame(frame, sci, sri, scale_color(shard_col, shard_int), 0.95)

    # =========================================================================
    # PHASE 3: Smoldering Embers & Obsidian Dissolve (0.70 -> 1.00)
    # =========================================================================
    else:
        p3 = (progress - 0.70) / 0.30  # 0.0 -> 1.0
        decay_env = (1.0 - p3) ** 1.4

        # A. Organic Dual-Harmonic Smoldering Cinders
        for c in range(8):
            for r in range(8):
                d_c = math.hypot(c - c0, r - r0)
                h = 0.5 * (math.sin(now * 15.0 + c * 19.3 + r * 31.7) + math.cos(now * 9.5 + c * 27.1 + r * 13.9))
                if h > 0.48:
                    cinder_int = (((h - 0.48) / 0.52) ** 2) * decay_env * 0.65
                    if cinder_int > 0.05:
                        cinder_col = blend_colors(col_gold, col_ember, p3)
                        set_square_in_frame(frame, c, r, scale_color(cinder_col, cinder_int))

        # B. Central Dying Hearth Pulse (Biphasic Heartbeat + Smoldering Glow)
        if p3 < 0.98:
            hb_osc = (math.sin(p3 * 2.5 * math.pi) ** 4) + 0.35 * (math.sin(max(0.0, p3 * 2.5 * math.pi - 0.4 * math.pi)) ** 4)
            hearth_factor = (hb_osc * 0.85 + 0.15 * (1.0 - p3)) * math.exp(-2.2 * p3)
            for c in (3, 4):
                for r in (3, 4):
                    d_c = math.hypot(c - c0, r - r0)
                    hearth_int = hearth_factor * math.exp(-d_c / 1.2)
                    if hearth_int > 0.01:
                        hearth_col = blend_colors(col_crimson, col_ash, p3)
                        blend_square_in_frame(frame, c, r, scale_color(hearth_col, hearth_int), 0.90)


def render_game_drawn(
    progress: float, frame: list[int], params: dict[str, Any], now: float = 0.0
) -> None:
    """
    GAME_DRAWN animation: "The Celestial Equilibrium"
    A graceful 3-phase procedural sequence portraying the balance of two equal cosmic forces:

    - Phase 1: Dual Army Tidal Waves (0.00 <= progress < 0.38).
      Pearl White tide (Rank 1-2) advancing upward from SW vs Deep Celestial Sapphire tide (Rank 7-8) advancing downward from NE.
    - Phase 2: The Equatorial Vortex (0.38 <= progress < 0.72).
      Harmonic orbital swirl and gentle breathing equilibrium at Ranks 4-5 blending into Radiant Aqua.
    - Phase 3: Serene Horizon Dissolve (0.72 <= progress <= 1.00).
      Tranquil outward flank ripple settling the board peacefully to rest.

    Hardware Budget: <= 14 active squares peak (< 140mA on 5V rail).
    """
    if now == 0.0:
        now = time.time()

    is_night = bool(params.get("night_mode", False))
    col_pearl = COLOR_INT_NIGHT_DRAW_PEARL if is_night else COLOR_INT_DRAW_PEARL
    col_sapphire = COLOR_INT_NIGHT_DRAW_SAPPHIRE if is_night else COLOR_INT_DRAW_SAPPHIRE
    col_equilibrium = COLOR_INT_NIGHT_DRAW_EQUILIBRIUM if is_night else COLOR_INT_DRAW_EQUILIBRIUM
    col_twilight = COLOR_INT_NIGHT_DRAW_TWILIGHT if is_night else COLOR_INT_DRAW_TWILIGHT
    col_idle = COLOR_INT_NIGHT_MODE if is_night else COLOR_INT_OFF

    # Clear frame buffer
    for c in range(8):
        for r in range(8):
            set_square_in_frame(frame, c, r, col_idle)

    progress = max(0.0, min(1.0, progress))
    c0, r0 = 3.5, 3.5

    # =========================================================================
    # PHASE 1: Dual Army Tidal Waves (0.00 -> 0.38)
    # =========================================================================
    if progress < 0.38:
        p1 = progress / 0.38  # 0.0 -> 1.0
        y_white = -0.5 + 4.0 * p1
        y_black = 7.5 - 4.0 * p1
        sigma_t = 0.34

        for c in range(8):
            for r in range(8):
                dy_w = abs(r - y_white)
                dy_b = abs(r - y_black)
                # Counter-flowing spatial envelopes: White from SW, Black from NE
                w_w = math.exp(-(dy_w * dy_w) / (2.0 * sigma_t * sigma_t)) * math.exp(-((c - 2.5) ** 2) / 4.5)
                w_b = math.exp(-(dy_b * dy_b) / (2.0 * sigma_t * sigma_t)) * math.exp(-((c - 4.5) ** 2) / 4.5)

                total_w = w_w + w_b
                if total_w > 0.15:
                    ratio_w = w_w / (total_w + 1e-5)
                    wave_col = blend_colors(col_sapphire, col_pearl, ratio_w)
                    set_square_in_frame(frame, c, r, scale_color(wave_col, min(1.0, total_w)))

    # =========================================================================
    # PHASE 2: The Equatorial Vortex (0.38 -> 0.72)
    # =========================================================================
    elif progress < 0.72:
        _p2 = (progress - 0.38) / 0.34  # 0.0 -> 1.0
        breathing = 0.82 + 0.18 * math.sin(now * 7.0)

        for c in range(8):
            for r in range(8):
                d_c = math.hypot(c - c0, r - r0)
                theta = math.atan2(r - r0, c - c0)
                swirl = math.sin(2.0 * theta + 6.0 * now - 1.6 * d_c)

                # Equatorial spatial envelope concentrated along Ranks 4-5
                w_vortex = math.exp(-((r - 3.5) ** 2) / 1.6) * math.exp(-((d_c - 1.8) ** 2) / (2.0 * 0.75 * 0.75))
                vortex_int = w_vortex * breathing * (0.80 + 0.20 * swirl)

                if vortex_int > 0.10:
                    blend_factor = max(0.0, min(1.0, 0.5 + 0.35 * ((r - 3.5) / max(0.2, d_c)) + 0.25 * swirl))
                    base_col = blend_colors(col_sapphire, col_pearl, blend_factor)
                    final_col = blend_colors(base_col, col_equilibrium, 0.45)
                    set_square_in_frame(frame, c, r, scale_color(final_col, min(1.0, vortex_int)))

    # =========================================================================
    # PHASE 3: Serene Horizon Dissolve (0.72 -> 1.00)
    # =========================================================================
    else:
        p3 = (progress - 0.72) / 0.28  # 0.0 -> 1.0
        dissolve_env = 0.5 * (1.0 + math.cos(math.pi * p3)) * (1.0 - 0.3 * p3)
        r_flank = p3 * 4.2

        for c in range(8):
            for r in range(8):
                dr = abs(abs(c - c0) - r_flank)
                w_horizon = math.exp(-((r - 3.5) ** 2) / 1.4) * math.exp(-(dr * dr) / (2.0 * 0.65 * 0.65)) * dissolve_env
                if w_horizon > 0.06:
                    horizon_col = blend_colors(col_equilibrium, col_twilight, p3)
                    set_square_in_frame(frame, c, r, scale_color(horizon_col, min(1.0, w_horizon)))


def render_board_ready(
    progress: float, frame: list[int], params: dict[str, Any], now: float = 0.0
) -> None:
    """
    BOARD_READY / SETUP_COMPLETE animation ("The Emerald Snap Flash"):
    Quick, punchy procedural confirmation when all 32 pieces are correctly
    placed in starting positions.

    Phasing (Duration: 0.5s):
    - Phase 1 (0.00 -> 0.40): Rapid dual-army inward snap sweep from flank files (a/h)
      toward center files (d/e) along Ranks 1-2 (White) and Ranks 7-8 (Black).
    - Phase 2 (0.40 -> 1.00): Bright center battle-line pop on (d4, e4, d5, e5) with a
      fast exponential decay, while the 4 corner rooks (a1, h1, a8, h8) and 2 kings
      (e1, e8) quickly fade in to hand off to the persistent ambient breathing state.

    Lighting Budget: Strictly <= 10 squares active simultaneously (< 16% of board).
    Adaptive: Supports both Day Mode and Night Mode sapphire palettes.
    """
    if now == 0.0:
        now = time.time()

    is_night = bool(params.get("night_mode", False))

    col_primary = COLOR_INT_NIGHT_BOARD_READY_PRIMARY if is_night else COLOR_INT_BOARD_READY_PRIMARY
    col_secondary = COLOR_INT_NIGHT_BOARD_READY_SECONDARY if is_night else COLOR_INT_BOARD_READY_SECONDARY
    col_ambient = COLOR_INT_NIGHT_BOARD_READY_AMBIENT if is_night else COLOR_INT_BOARD_READY_AMBIENT
    col_idle = COLOR_INT_NIGHT_MODE if is_night else COLOR_INT_OFF

    # Clear entire frame to idle baseline
    for c in range(8):
        for r in range(8):
            set_square_in_frame(frame, c, r, col_idle)

    progress = max(0.0, min(1.0, progress))

    # =========================================================================
    # PHASE 1 (progress 0.00 -> 0.40): Dual Army Snap Sweep
    # =========================================================================
    if progress < 0.40:
        p1 = progress / 0.40  # 0.0 -> 1.0
        # Active flank file index: 0 (a/h) -> 1 (b/g) -> 2 (c/f) -> 3 (d/e)
        flank_idx = min(3, max(0, int(p1 * 4.0)))
        file_w = flank_idx
        file_e = 7 - flank_idx

        # Local intra-step pulse
        step_phase = (p1 * 4.0) % 1.0
        intensity = 0.7 + 0.3 * math.sin(step_phase * math.pi)
        wave_col = blend_colors(col_primary, col_secondary, p1 * 0.5)
        scaled_col = scale_color(wave_col, intensity)

        # Army ranks: White = [0, 1] (Ranks 1-2), Black = [6, 7] (Ranks 7-8)
        for r in [0, 1, 6, 7]:
            set_square_in_frame(frame, file_w, r, scaled_col)
            set_square_in_frame(frame, file_e, r, scaled_col)

    # =========================================================================
    # PHASE 2 (progress 0.40 -> 1.00): Center Pop Decay + Royal Guard Handshake
    # =========================================================================
    else:
        p2 = (progress - 0.40) / 0.60  # 0.0 -> 1.0

        # Fast exponential decay flash on the center diamond: d4, e4, d5, e5
        flare_int = 0.9 * math.exp(-5.5 * p2)
        if flare_int > 0.03:
            center_squares = [(3, 3), (4, 3), (3, 4), (4, 4)]
            flare_col = blend_colors(col_primary, COLOR_INT_DRAW_WHITE, 0.45)
            scaled_flare = scale_color(flare_col, flare_int)

            for c_sq, r_sq in center_squares:
                set_square_in_frame(frame, c_sq, r_sq, scaled_flare)

        # Corner rooks + kings fade in during the tail to transition into ambient
        anchor_fade = max(0.0, min(1.0, (p2 - 0.55) / 0.45))
        anchor_int = 0.10 + 0.15 * anchor_fade
        if anchor_int > 0.02:
            # 4 Corner Rooks + 2 Kings: a1, h1, a8, h8, e1, e8
            anchor_squares = [(0, 0), (7, 0), (0, 7), (7, 7), (4, 0), (4, 7)]
            anchor_col = blend_colors(col_ambient, col_primary, 0.4)
            scaled_anchor = scale_color(anchor_col, anchor_int)

            for c_sq, r_sq in anchor_squares:
                set_square_in_frame(frame, c_sq, r_sq, scaled_anchor)


# =============================================================================
# PERIMETER COORDINATES & SEEKING ANIMATION
# =============================================================================

# 28 perimeter squares ordered clockwise:
# Rank 1: (0,0) -> (7,0)
# File h: (7,1) -> (7,7)
# Rank 8: (6,7) -> (0,7)
# File a: (0,6) -> (0,1)
PERIMETER_COORDS: list[tuple[int, int]] = (
    [(c, 0) for c in range(8)]
    + [(7, r) for r in range(1, 8)]
    + [(c, 7) for c in range(6, -1, -1)]
    + [(0, r) for r in range(6, 0, -1)]
)


def render_seeking(
    now: float,
    frame: list[int],
    params: dict[str, Any],
    period: float = ANIM_SEEKING_PERIOD_S,
) -> None:
    """
    SEEKING / WAITING_FOR_OPPONENT animation:
    Smooth comet pulse orbiting the 28 perimeter squares clockwise.
    Features a bright icy cyan head, electric blue body, and deep royal blue tail decay.
    Inner 6x6 squares remain completely dark and inactive (< 6% active squares).
    """
    if period <= 0:
        return

    n = len(PERIMETER_COORDS)
    tau = (now % period) / period  # 0.0 to 1.0
    head_pos = tau * n
    tail_length = 7.0  # Tail span in perimeter squares (~1/4 ring)

    is_night = bool(params.get("night_mode", False))
    col_head = COLOR_INT_NIGHT_SEEKING_HEAD if is_night else COLOR_INT_SEEKING_HEAD
    col_body = COLOR_INT_NIGHT_SEEKING_BODY if is_night else COLOR_INT_SEEKING_BODY
    col_tail = COLOR_INT_NIGHT_SEEKING_TAIL if is_night else COLOR_INT_SEEKING_TAIL
    col_idle = COLOR_INT_NIGHT_MODE if is_night else COLOR_INT_OFF

    for i, (c, r) in enumerate(PERIMETER_COORDS):
        delta_behind = (head_pos - i) % n

        if delta_behind <= 1.0:
            # Head and immediate trailing gradient
            intensity = 1.0 - 0.25 * delta_behind
            col = blend_colors(col_head, col_body, delta_behind)
        elif delta_behind <= tail_length:
            # Body to tail decay
            t = (delta_behind - 1.0) / (tail_length - 1.0)
            intensity = 0.75 * ((1.0 - t) ** 1.8)
            col = blend_colors(col_body, col_tail, t)
        elif delta_behind > (n - 0.75):
            # Smooth leading edge ahead of head
            delta_ahead = n - delta_behind
            intensity = (1.0 - delta_ahead / 0.75) ** 2
            col = col_head
        else:
            intensity = 0.0
            col = col_idle

        if intensity > 0.02:
            set_square_in_frame(frame, c, r, scale_color(col, intensity))
        else:
            set_square_in_frame(frame, c, r, col_idle)


# Color constants for Analysis Computing Animation
COLOR_INT_ANALYSIS_CORE = 0x5000A0   # Royal Violet power-scaled
COLOR_INT_ANALYSIS_PULSE = 0x009040  # Mint Emerald power-scaled
COLOR_INT_ANALYSIS_ACCENT = 0x006090 # Cyan Azure power-scaled

ANALYSIS_CORE_COORDS: list[tuple[int, int]] = [
    (3, 3), (4, 3), (3, 4), (4, 4)
]

ANALYSIS_ORBITAL_RING: list[tuple[int, int]] = [
    (2, 2), (3, 2), (4, 2), (5, 2),
    (5, 3), (5, 4), (5, 5),
    (4, 5), (3, 5), (2, 5),
    (2, 4), (2, 3),
]


def render_analysis_computing(
    now: float,
    frame: list[int],
    params: dict[str, Any] | None = None,
) -> None:
    """
    Renders the Analysis Computing Animation on the board during Stockfish evaluation:
    - Central 2x2 Core (d4, e4, d5, e5) breathing softly in Royal Violet.
    - Orbital 12-square ring surrounding center with dual sweeping Mint Emerald / Azure
      probes rotating at ~1.35 rev/sec (180 degrees opposing phase).
    - Power-optimized to illuminate <= 8 squares simultaneously (< 250mA power budget).
    - Respects night_mode with a 0.45 power attenuation factor.
    """
    params = params or {}
    night_mode = bool(params.get("night_mode", False))
    p_scale = 0.45 if night_mode else 1.0
    col_idle = COLOR_INT_NIGHT_MODE if night_mode else COLOR_INT_OFF

    # 1. Central 2x2 Core Breathing in Royal Violet (d4, e4, d5, e5)
    core_breath = math.sin(now * 3.5) * 0.5 + 0.5
    core_intensity = (0.25 + 0.60 * core_breath) * p_scale
    core_color = scale_color(COLOR_INT_ANALYSIS_CORE, core_intensity)
    for c, r in ANALYSIS_CORE_COORDS:
        set_square_in_frame(frame, c, r, core_color)

    # 2. Orbital 12-Square Ring with Dual Sweeping Probes (~1.35 rev/sec)
    n_ring = len(ANALYSIS_ORBITAL_RING)  # 12
    rot_speed = 1.35  # rev/sec
    tau = (now * rot_speed) % 1.0  # 0.0 to 1.0
    head1 = tau * n_ring
    head2 = (head1 + n_ring / 2.0) % n_ring

    for i, (c, r) in enumerate(ANALYSIS_ORBITAL_RING):
        # Probe 1: Mint Emerald (head1)
        d_behind1 = (head1 - i) % n_ring
        if d_behind1 <= 0.4:
            int1 = 1.0 - 0.5 * d_behind1
        elif d_behind1 <= 1.8:
            int1 = 0.8 * ((1.0 - (d_behind1 - 0.4) / 1.4) ** 2)
        elif d_behind1 > (n_ring - 0.4):
            int1 = (n_ring - d_behind1) / 0.4 * 0.5
        else:
            int1 = 0.0

        # Probe 2: Cyan Azure (head2)
        d_behind2 = (head2 - i) % n_ring
        if d_behind2 <= 0.4:
            int2 = 1.0 - 0.5 * d_behind2
        elif d_behind2 <= 1.8:
            int2 = 0.8 * ((1.0 - (d_behind2 - 0.4) / 1.4) ** 2)
        elif d_behind2 > (n_ring - 0.4):
            int2 = (n_ring - d_behind2) / 0.4 * 0.5
        else:
            int2 = 0.0

        col = col_idle
        if int1 > 0.02:
            col = add_colors(col, scale_color(COLOR_INT_ANALYSIS_PULSE, int1 * p_scale))
        if int2 > 0.02:
            col = add_colors(col, scale_color(COLOR_INT_ANALYSIS_ACCENT, int2 * p_scale))

        set_square_in_frame(frame, c, r, col)


# =============================================================================
# LIFECYCLE ANIMATION CLASS & FACTORY
# =============================================================================

def render_recall_complete(progress: float, frame: list[int], params: dict[str, Any]) -> None:
    """
    "Memory Bloom" celebration for a completed Replay Trainer recall session.

    Phase A (p < 0.55): Expanding golden memory-bloom diamond ring radiating from
    the board center (Manhattan-distance ring), shimmering with a subtle flicker.
    Phase B (p >= 0.40): Four corner rook squares breathe in Mint Emerald while
    the central royal thrones pulse in Victory Gold, all dissolving to stillness.
    Peak active squares <= ~22 (~170mA day, ~75mA night) - within power budget.
    """
    night = bool(params.get("night_mode", False))
    gold = COLOR_INT_NIGHT_PROMO_ROOT if night else COLOR_INT_VICTORY_GOLD
    green = COLOR_INT_NIGHT_MINT_EMERALD if night else COLOR_INT_VICTORY_GREEN

    def set_sq(c: int, r: int, color_val: int) -> None:
        for idx in get_led_indices(r, c):
            if 0 <= idx < len(frame):
                frame[idx] = color_val

    if progress < 0.55:
        # Expanding Manhattan ring from center (3.5, 3.5)
        ring_p = progress / 0.55
        radius = ring_p * 7.5
        intensity = (1.0 - ring_p) * (0.85 + 0.15 * math.sin(time.time() * 20.0))
        col = scale_color(gold, max(0.0, intensity))
        for c in range(8):
            for r in range(8):
                dist = abs(c - 3.5) + abs(r - 3.5)
                if abs(dist * 2.0 - radius) < 1.1:  # ring band (dist*2 spans 1..14)
                    set_sq(c, r, col)

    if progress >= 0.40:
        # Corner emerald breathing + central royal gold pulse, fading out
        fade = 1.0 - max(0.0, (progress - 0.40) / 0.60)
        now = time.time()
        corner_pulse = math.sin(now * 6.0) * 0.5 + 0.5
        corner_col = scale_color(green, 0.35 + 0.65 * corner_pulse)
        corner_col = scale_color(corner_col, fade)
        for c_c, c_r in [(0, 0), (7, 0), (0, 7), (7, 7)]:
            set_sq(c_c, c_r, corner_col)

        center_pulse = math.sin(now * 5.0) * 0.5 + 0.5
        center_col = scale_color(scale_color(gold, 0.5 + 0.5 * center_pulse), fade)
        set_sq(3, 3, center_col)
        set_sq(4, 3, center_col)
        set_sq(3, 4, center_col)
        set_sq(4, 4, center_col)


def render_recall_start(progress: float, frame: list[int], params: dict[str, Any]) -> None:
    """
    "Memory Arm" sweep announcing the recall phase start.

    A rising Royal Violet wave sweeps from White's home ranks toward Black's,
    trailed by a soft Azure shimmer, then dissolves. Peak active squares
    <= 16 (~125mA day, ~55mA night) - within power budget.
    """
    night = bool(params.get("night_mode", False))
    violet = COLOR_INT_NIGHT_ROYAL_VIOLET if night else COLOR_INT_ROYAL_VIOLET
    azure = COLOR_INT_NIGHT_AZURE if night else COLOR_INT_AZURE

    wave_row = progress * 10.0 - 1.0  # -1 .. 9 (enters/exits gracefully)

    for r in range(8):
        d = r - wave_row  # rows below the crest have negative d
        if -1.2 < d <= 0:
            # Crest: bright royal violet with breathing shimmer
            intensity = (1.0 + d / 1.2) * (0.75 + 0.25 * math.sin(time.time() * 18.0))
            col = scale_color(violet, max(0.0, intensity))
        elif 0 < d <= 1.6:
            # Trailing azure shimmer above the crest
            fade = 1.0 - d / 1.6
            col = scale_color(azure, 0.45 * fade)
        else:
            continue
        for c in range(8):
            for idx in get_led_indices(r, c):
                if 0 <= idx < len(frame):
                    frame[idx] = col


@dataclass
class LifecycleAnimation:
    """State and rendering coordinator for a procedural LED lifecycle animation."""
    name: str
    duration: float
    start_time: float = field(default_factory=time.time)
    params: dict[str, Any] = field(default_factory=dict)

    def is_active(self, now: float | None = None) -> bool:
        """Returns True if the animation is currently running within its duration."""
        if now is None:
            now = time.time()
        return (now - self.start_time) < self.duration

    def get_progress(self, now: float | None = None) -> float:
        """Returns progress fraction clamped between 0.0 and 1.0."""
        if now is None:
            now = time.time()
        if self.duration <= 0:
            return 1.0
        return max(0.0, min(1.0, (now - self.start_time) / self.duration))

    def render(self, now: float, frame: list[int]) -> None:
        """Renders the current animation frame into the LED frame buffer."""
        progress = self.get_progress(now)
        anim_name = self.name.upper()

        if anim_name == "GAME_STARTED":
            render_game_started(progress, frame, self.params)
        elif anim_name == "RECALL_COMPLETE":
            render_recall_complete(progress, frame, self.params)
        elif anim_name == "RECALL_START":
            render_recall_start(progress, frame, self.params)
        elif anim_name == "GAME_WON":
            render_game_won(progress, frame, self.params, now=now)
        elif anim_name == "GAME_LOST":
            render_game_lost(progress, frame, self.params, now=now)
        elif anim_name == "GAME_DRAWN":
            render_game_drawn(progress, frame, self.params, now=now)
        elif anim_name in ("BOARD_READY", "SETUP_COMPLETE"):
            render_board_ready(progress, frame, self.params, now=now)
        elif anim_name in ("SEEKING", "WAITING_FOR_OPPONENT", "MATCHMAKING"):
            render_seeking(now, frame, self.params)
        elif anim_name in ("ANALYSIS_COMPUTING", "ANALYSIS_LOADING"):
            render_analysis_computing(now, frame, self.params)


def create_animation(
    name: str, params: dict[str, Any] | None = None
) -> LifecycleAnimation:
    """
    Animation factory creating configured LifecycleAnimation instances.

    Args:
        name: Name of animation ('GAME_STARTED', 'GAME_WON', 'GAME_LOST', 'GAME_DRAWN', 'BOARD_READY', 'SETUP_COMPLETE', 'SEEKING', 'WAITING_FOR_OPPONENT', 'ANALYSIS_COMPUTING').
        params: Optional metadata dict (e.g. {'my_color': 'white'}).

    Returns:
        LifecycleAnimation instance with predefined duration.
    """
    clean_name = name.strip().upper()
    durations = {
        "GAME_STARTED": ANIM_GAME_START_DURATION_S,
        "RECALL_COMPLETE": ANIM_RECALL_COMPLETE_DURATION_S,
        "RECALL_START": ANIM_RECALL_START_DURATION_S,
        "GAME_WON": ANIM_GAME_WON_DURATION_S,
        "GAME_LOST": ANIM_GAME_LOST_DURATION_S,
        "GAME_DRAWN": ANIM_GAME_DRAWN_DURATION_S,
        "BOARD_READY": ANIM_BOARD_READY_DURATION_S,
        "SETUP_COMPLETE": ANIM_BOARD_READY_DURATION_S,
        "SEEKING": ANIM_SEEKING_DURATION_S,
        "WAITING_FOR_OPPONENT": ANIM_SEEKING_DURATION_S,
        "MATCHMAKING": ANIM_SEEKING_DURATION_S,
        "ANALYSIS_COMPUTING": ANIM_ANALYSIS_COMPUTING_DURATION_S,
        "ANALYSIS_LOADING": ANIM_ANALYSIS_COMPUTING_DURATION_S,
    }
    duration = durations.get(clean_name, 2.0)
    return LifecycleAnimation(
        name=clean_name,
        duration=duration,
        start_time=time.time(),
        params=params or {},
    )


def render_capture_aura(
    target_sq: tuple[int, int],
    candidate_attackers: list[tuple[int, int]],
    now: float,
    frame: list[int],
    target_color: int = COLOR_INT_CAPTURE_AURA_TARGET,
    attacker_color: int = COLOR_INT_CAPTURE_AURA_ATTACKER,
) -> None:
    """
    Renders an active capture-in-progress aura on the board when the player
    has lifted the opponent's piece first.
    - Pulsing radiant ruby/gold aura on the target square.
    - Warm golden breathing pulse on candidate friendly attacker squares.
    """
    t_c, t_r = target_sq
    # Target square pulse: smooth sinusoidal oscillation between ruby/crimson and gold
    pulse_t = math.sin(now * 5.0) * 0.5 + 0.5
    target_col = blend_colors(target_color, attacker_color, pulse_t * 0.4)
    intensity = 0.6 + 0.4 * pulse_t
    scaled_target = scale_color(target_col, intensity)
    set_square_in_frame(frame, t_c, t_r, scaled_target)

    # Candidate attackers: rhythmic golden breathing pulse
    for i, (a_c, a_r) in enumerate(candidate_attackers):
        att_pulse = math.sin(now * 4.0 + i * 0.8) * 0.5 + 0.5
        att_intensity = 0.4 + 0.6 * att_pulse
        att_col = scale_color(attacker_color, att_intensity)
        set_square_in_frame(frame, a_c, a_r, att_col)


def render_guardrail_mismatch(
    missing_pieces: list[tuple[int, int]],
    unexpected_pieces: list[tuple[int, int]],
    now: float,
    frame: list[int],
    missing_color: int = COLOR_INT_GUARDRAIL_MISSING,
    unexpected_color: int = COLOR_INT_GUARDRAIL_UNEXPECTED,
) -> None:
    """
    Renders visual alert pulses on squares with state mismatches during games.
    - Missing pieces: Distinct pulsing amber alert (6 Hz).
    - Unexpected pieces: Sharp pulsing crimson alert (8 Hz).
    """
    # Missing pieces pulse (amber/orange)
    if missing_pieces:
        miss_pulse = math.sin(now * 6.0 * 2.0 * math.pi) * 0.5 + 0.5
        miss_intensity = 0.3 + 0.7 * miss_pulse
        miss_col = scale_color(missing_color, miss_intensity)
        for c, r in missing_pieces:
            set_square_in_frame(frame, c, r, miss_col)

    # Unexpected pieces pulse (crimson/red)
    if unexpected_pieces:
        unexp_pulse = math.sin(now * 8.0 * 2.0 * math.pi) * 0.5 + 0.5
        unexp_intensity = 0.35 + 0.65 * unexp_pulse
        unexp_col = scale_color(unexpected_color, unexp_intensity)
        for c, r in unexpected_pieces:
            set_square_in_frame(frame, c, r, unexp_col)


def render_opponent_disconnected(
    now: float,
    frame: list[int],
    opponent_gone_info: dict[str, Any],
    my_color: str,
    opponent_king_sq: tuple[int, int] | None = None,
) -> None:
    """
    Renders visual alerts on the physical board when the opponent disconnects:
    1. Warning beacon: Alert pulsing amber beacon on the opponent's King square.
    2. Linear Victory Claim Countdown Gauge: An 8-LED progress meter along the opponent's
       back rank (Rank 8 for White player, Rank 1 for Black player) smoothly draining down
       as the victory claim window elapses.
    """
    # 1. Warning beacon on opponent's King
    if opponent_king_sq:
        k_c, k_r = opponent_king_sq
        pulse = math.sin(now * 3.0 * math.pi) * 0.5 + 0.5
        beacon_col = scale_color(COLOR_INT_OPPONENT_DISCONNECTED, 0.35 + 0.65 * pulse)
        set_square_in_frame(frame, k_c, k_r, beacon_col)

    # 2. Linear countdown gauge along opponent's back rank
    gauge_rank = 7 if str(my_color).lower() == "white" else 0
    total_time = opponent_gone_info.get("initial_claim_win_in", 30)
    if total_time <= 0:
        total_time = 30
    start_time = opponent_gone_info.get("start_time", now)
    elapsed = max(0.0, now - start_time)
    remaining = max(0.0, total_time - elapsed)
    frac = max(0.0, min(1.0, remaining / total_time))  # 1.0 down to 0.0

    # 8 segments from file 0 to 7
    active_segments = frac * 8.0  # 8.0 down to 0.0
    for c in range(8):
        if c < int(active_segments):
            # Fully active segment
            set_square_in_frame(frame, c, gauge_rank, scale_color(COLOR_INT_OPPONENT_DISCONNECTED, 0.55))
        elif c == int(active_segments):
            # Fractional draining edge segment with subtle breathing pulse
            rem = active_segments - int(active_segments)
            edge_pulse = math.sin(now * 5.0) * 0.2 + 0.8
            set_square_in_frame(
                frame, c, gauge_rank, scale_color(COLOR_INT_OPPONENT_DISCONNECTED, 0.55 * rem * edge_pulse)
            )


def render_clock_bar(
    now: float,
    frame: list[int],
    col: int,
    remaining_s: float | None,
    total_s: float | None,
    ok_color: int,
    warn_color: int,
    crit_color: int,
) -> None:
    """Draining chess-clock bar along a file (col 0 = black/a-file, col 7 = white/h-file).

    Painted early in the PLAYING layer stack so piece-move highlights overwrite it.
    NOTE: render_opponent_disconnected paints the back ranks incl. cols 0/7 later in
    the frame and intentionally overwrites the clock-bar end squares.
    """
    if total_s is None or total_s <= 0 or remaining_s is None:
        return
    frac = min(1.0, max(0.0, remaining_s / total_s))
    n_lit = int(frac * 8)

    if frac > 0.25:
        urgency_color = ok_color
    elif frac > 0.10:
        urgency_color = warn_color
    else:
        urgency_color = crit_color

    if urgency_color == crit_color:
        pulse = math.sin(now * 4.0 * math.pi) * 0.5 + 0.5
        intensity = 0.65 + 0.35 * pulse
        urgency_color = scale_color(urgency_color, intensity)

    for r in range(n_lit):
        set_square_in_frame(frame, col, r, urgency_color)

    rem = frac * 8 - n_lit
    if n_lit < 8 and rem > 0:
        edge_pulse = math.sin(now * 5.0) * 0.2 + 0.8
        set_square_in_frame(frame, col, n_lit, scale_color(urgency_color, rem * edge_pulse))


def render_return_home_guide(
    now: float,
    frame: list[int],
    from_sq: tuple[int, int],
    to_sq: tuple[int, int],
    color: int,
) -> None:
    """Pulsing halo on the arrival square of the last branch move (un-play this next)
    plus a steady dim dot on its origin square. Guides the user back to the game
    timeline during ANALYSIS branching."""
    halo_intensity = 0.55 + 0.45 * (math.sin(now * 2 * math.pi * 0.9) * 0.5 + 0.5)
    set_square_in_frame(frame, to_sq[0], to_sq[1], scale_color(color, halo_intensity))
    if from_sq != to_sq:
        set_square_in_frame(frame, from_sq[0], from_sq[1], scale_color(color, 0.35))


def render_promotion_scepter(
    now: float,
    frame: list[int],
    promo_state: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> None:
    """
    Renders the Royal Promotion Scepter visual guide on the physical chessboard:
    1. Root Square Halo: Luminous pulsating countdown aura on the promotion square (to_col, to_row).
    2. Piece Selection Options: Distinct breathing pulses on each allocated option square
       (Queen in Royal Violet, Knight in Mint Emerald, Rook in Azure Cyan, Bishop in Warm Sun Amber).

    Respects Night Mode attenuation and strictly complies with the low-power budget
    (<= 5 squares / 10 active LEDs, < 120mA peak on 5V rail).
    """
    if promo_state is None:
        return

    params = params or {}
    is_night = bool(params.get("night_mode") or promo_state.get("night_mode", False))

    if is_night:
        col_root = COLOR_INT_NIGHT_PROMO_ROOT
        piece_colors = {
            "q": COLOR_INT_NIGHT_PROMO_QUEEN,
            "n": COLOR_INT_NIGHT_PROMO_KNIGHT,
            "r": COLOR_INT_NIGHT_PROMO_ROOK,
            "b": COLOR_INT_NIGHT_PROMO_BISHOP,
        }
        power_scale = 0.85
    else:
        col_root = COLOR_INT_PROMO_ROOT
        piece_colors = {
            "q": COLOR_INT_PROMO_QUEEN,
            "n": COLOR_INT_PROMO_KNIGHT,
            "r": COLOR_INT_PROMO_ROOK,
            "b": COLOR_INT_PROMO_BISHOP,
        }
        power_scale = 1.0

    # 1. Root Promotion Square Halo with Countdown Progress
    col_root = COLOR_INT_NIGHT_PROMO_ROOT if is_night else COLOR_INT_PROMO_ROOT
    power_scale = 0.40 if is_night else 0.48

    piece_colors = {
        "q": COLOR_INT_NIGHT_PROMO_QUEEN if is_night else COLOR_INT_PROMO_QUEEN,
        "n": COLOR_INT_NIGHT_PROMO_KNIGHT if is_night else COLOR_INT_PROMO_KNIGHT,
        "r": COLOR_INT_NIGHT_PROMO_ROOK if is_night else COLOR_INT_PROMO_ROOK,
        "b": COLOR_INT_NIGHT_PROMO_BISHOP if is_night else COLOR_INT_PROMO_BISHOP,
    }

    # 1. Root Square Halo & Progress Indicator
    root_sq = (
        promo_state.get("root_square")
        or promo_state.get("to")
        or promo_state.get("dest")
        or promo_state.get("to_square")
        or promo_state.get("to_sq")
    )
    if root_sq and isinstance(root_sq, (tuple, list)) and len(root_sq) == 2:
        root_c, root_r = int(root_sq[0]), int(root_sq[1])
        if 0 <= root_c < 8 and 0 <= root_r < 8:
            timeout_s = float(
                promo_state.get("timeout_s")
                or promo_state.get("duration_s")
                or promo_state.get("total_time")
                or 10.0
            )
            start_time = promo_state.get("start_time") or promo_state.get("started_at")
            remaining_s = promo_state.get("remaining_s")

            if remaining_s is not None:
                time_frac = max(0.0, min(1.0, float(remaining_s) / max(0.001, timeout_s)))
            elif start_time is not None:
                elapsed = max(0.0, now - float(start_time))
                time_frac = max(0.0, min(1.0, 1.0 - (elapsed / max(0.001, timeout_s))))
            else:
                time_frac = float(promo_state.get("time_frac", 1.0))

            # Pulse rate accelerates as countdown expires (2 Hz -> 6 Hz)
            pulse_freq = 2.0 + (1.0 - time_frac) * 4.0
            root_pulse = math.sin(now * pulse_freq * 2.0 * math.pi) * 0.5 + 0.5
            root_intensity = (0.40 + 0.60 * root_pulse) * power_scale * 0.50
            set_square_in_frame(frame, root_c, root_r, scale_color(col_root, root_intensity))

    # 2. Piece Selection Options Breathing Halos
    options = promo_state.get("options", {})
    if isinstance(options, dict):
        phase_offsets = {
            "q": 0.0,
            "n": 0.5 * math.pi,
            "r": 1.0 * math.pi,
            "b": 1.5 * math.pi,
        }
        for piece_char, sq_coord in options.items():
            if not isinstance(sq_coord, (tuple, list)) or len(sq_coord) != 2:
                continue
            opt_c, opt_r = int(sq_coord[0]), int(sq_coord[1])
            if not (0 <= opt_c < 8 and 0 <= opt_r < 8):
                continue
            k = str(piece_char).lower()
            opt_col = piece_colors.get(k, col_root)
            phase = phase_offsets.get(k, 0.0)

            # Harmonious breathing oscillation (~0.6 Hz)
            breath_wave = math.sin(now * 3.8 + phase) * 0.5 + 0.5
            opt_intensity = (0.35 + 0.65 * breath_wave) * power_scale * 0.55
            set_square_in_frame(frame, opt_c, opt_r, scale_color(opt_col, opt_intensity))


def render_uncharted_novelty(
    progress: float,
    frame: list[int],
    center_coord: tuple[int, int],
    params: dict[str, Any] | None = None,
) -> None:
    """
    Renders Cartographer's Path Uncharted Novelty Flare:
    A high-speed 350ms outward radial starburst pulse from center_coord with exponential decay.
    Peak illuminated squares <= 8, peak current < 90mA on 5V rail.
    """
    p = max(0.0, min(1.0, float(progress)))
    params = params or {}
    is_night = bool(params.get("night_mode", False))

    col_flare = COLOR_INT_NIGHT_NOVELTY_FLARE if is_night else COLOR_INT_NOVELTY_FLARE
    power_scale = 0.50 if is_night else 0.60

    c0, r0 = int(center_coord[0]), int(center_coord[1])
    if not (0 <= c0 < 8 and 0 <= r0 < 8):
        return

    # Expanding wavefront radius (0.0 to 2.6 squares)
    wave_radius = p * 2.6
    # Temporal exponential decay envelope
    envelope = math.exp(-4.2 * p)

    min_c = max(0, c0 - 3)
    max_c = min(7, c0 + 3)
    min_r = max(0, r0 - 3)
    max_r = min(7, r0 + 3)

    for c in range(min_c, max_c + 1):
        for r in range(min_r, max_r + 1):
            dist = math.hypot(c - c0, r - r0)
            if dist > 3.0:
                continue

            dr = dist - wave_radius
            # Tight spatial Gaussian ring profile
            ring_int = math.exp(-7.5 * dr * dr)
            sq_int = envelope * ring_int * power_scale

            if sq_int > 0.05:
                clamped_int = min(1.0, sq_int)
                set_square_in_frame(frame, c, r, scale_color(col_flare, clamped_int))


def render_resignation_aura(
    now: float,
    frame: list[int],
    king_origin: tuple[int, int],
    elapsed: float,
    params: dict[str, Any] | None = None,
) -> None:
    """
    Renders "The King's Bow" Resignation Gesture Aura:
    - On King origin square: Sinusoidal breathing pulse in Laser Crimson (Color(220, 24, 40))
    - On 4 cross-adjacent squares (up, down, left, right): Soft radial breathing halo in Radiant Garnet
    - Frequency accelerates smoothly as elapsed approaches the 5.0s abandonment ceiling
    Peak active LEDs <= 10, power draw <= 95mA on 5V rail.
    """
    params = params or {}
    is_night = bool(params.get("night_mode", False))

    col_primary = COLOR_INT_NIGHT_RESIGN_PRIMARY if is_night else COLOR_INT_RESIGN_PRIMARY
    col_halo = COLOR_INT_NIGHT_RESIGN_HALO if is_night else COLOR_INT_RESIGN_HALO
    power_scale = 0.50 if is_night else 0.70

    k_c, k_r = int(king_origin[0]), int(king_origin[1])
    if not (0 <= k_c < 8 and 0 <= k_r < 8):
        return

    # Breathing rate accelerates from 2.5Hz at 3.0s to 5.0Hz at 5.0s
    progress = max(0.0, min(1.0, (elapsed - 3.0) / 2.0))
    freq = 2.5 + 2.5 * progress
    wave = 0.5 + 0.5 * math.sin(2.0 * math.pi * freq * now)

    # Origin square intensity
    origin_int = (0.35 + 0.65 * wave) * power_scale
    set_square_in_frame(frame, k_c, k_r, scale_color(col_primary, origin_int))

    # Cross-adjacent halo squares
    halo_int = (0.15 + 0.25 * wave) * power_scale
    for dc, dr in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        nc, nr = k_c + dc, k_r + dr
        if 0 <= nc < 8 and 0 <= nr < 8:
            set_square_in_frame(frame, nc, nr, scale_color(col_halo, halo_int))


# =============================================================================
# ENDGAME TRAINER SETUP & LIFECYCLE RENDERERS
# =============================================================================

_NIGHT_PIECE_COLORS = {
    6: COLOR_INT_NIGHT_PIECE_KING,
    5: COLOR_INT_NIGHT_PIECE_QUEEN,
    4: COLOR_INT_NIGHT_PIECE_ROOK,
    3: COLOR_INT_NIGHT_PIECE_BISHOP,
    2: COLOR_INT_NIGHT_PIECE_KNIGHT,
    1: COLOR_INT_NIGHT_PIECE_PAWN,
}
_DAY_PIECE_COLORS = {
    6: COLOR_INT_PIECE_KING,
    5: COLOR_INT_PIECE_QUEEN,
    4: COLOR_INT_PIECE_ROOK,
    3: COLOR_INT_PIECE_BISHOP,
    2: COLOR_INT_PIECE_KNIGHT,
    1: COLOR_INT_PIECE_PAWN,
}


def get_piece_type_color(piece_type: int, is_night: bool = False, night_mode: bool | None = None) -> int:
    """Returns the harmonized WS2812B LED Color for a given chess piece type."""
    if night_mode is not None:
        is_night = night_mode
    return (
        _NIGHT_PIECE_COLORS.get(piece_type, COLOR_INT_NIGHT_PIECE_PAWN)
        if is_night
        else _DAY_PIECE_COLORS.get(piece_type, COLOR_INT_PIECE_PAWN)
    )


def render_endgame_setup(
    now: float,
    frame: list[int],
    target_pieces: dict[tuple[int, int], tuple[int, bool]],  # (c, r) -> (piece_type, is_white)
    physical_state: list[list[int]],
    phase: str,  # "setup_white" | "setup_black" | "preview"
    params: dict[str, Any] | None = None,
) -> None:
    """
    Renders layered LED guidance for Endgame sparse piece setup:
    - Target squares glow in piece-type colors (breathing pulse if missing, locked-in steady if placed).
    - Extraneous / misplaced physical pieces glow in Misplaced Amber / Red.
    - Low power budgeting (<= 10 active squares).
    """
    params = params or {}
    is_night = bool(params.get("night_mode", False))
    col_misplaced = COLOR_INT_NIGHT_SETUP_MISPLACED if is_night else COLOR_INT_SETUP_MISPLACED
    col_unexpected = COLOR_INT_NIGHT_GUARDRAIL_UNEXPECTED if is_night else COLOR_INT_GUARDRAIL_UNEXPECTED

    pulse = 0.55 + 0.40 * math.sin(4.0 * now)
    base_int = 0.45 if is_night else 0.65

    # 1. Render target pieces according to phase
    for (c, r), (ptype, is_white) in target_pieces.items():
        if not (0 <= c < 8 and 0 <= r < 8):
            continue

        val = physical_state[c][r] if c < len(physical_state) and r < len(physical_state[c]) else 0
        piece_col = get_piece_type_color(ptype, is_night)

        if phase == "preview":
            # In preview mode, all target squares glow in their piece colors
            set_square_in_frame(frame, c, r, scale_color(piece_col, (0.50 + 0.35 * pulse) * base_int))
        elif phase == "setup_white":
            if is_white:
                if val == -1:
                    # Correct White piece placed: locked-in steady glow
                    set_square_in_frame(frame, c, r, scale_color(piece_col, 0.85 * base_int))
                elif val == 0:
                    # Missing White piece: breathing pulse to guide placement
                    set_square_in_frame(frame, c, r, scale_color(piece_col, pulse * base_int))
                else:
                    # Misplaced polarity (Black piece on White target square)
                    set_square_in_frame(frame, c, r, scale_color(col_misplaced, pulse))
        elif phase == "setup_black":
            if is_white:
                # White pieces already placed stay dim/steady
                if val == -1:
                    set_square_in_frame(frame, c, r, scale_color(piece_col, 0.35 * base_int))
                else:
                    # White piece was removed or disturbed!
                    set_square_in_frame(frame, c, r, scale_color(piece_col, pulse * base_int))
            else:
                if val == 1:
                    # Correct Black piece placed: locked-in steady glow
                    set_square_in_frame(frame, c, r, scale_color(piece_col, 0.85 * base_int))
                elif val == 0:
                    # Missing Black piece: breathing pulse to guide placement
                    set_square_in_frame(frame, c, r, scale_color(piece_col, pulse * base_int))
                else:
                    # Misplaced polarity (White piece on Black target square)
                    set_square_in_frame(frame, c, r, scale_color(col_misplaced, pulse))

    # 2. Highlight extraneous pieces currently on non-target squares
    if phase in ("setup_white", "setup_black"):
        for c in range(8):
            for r in range(8):
                val = physical_state[c][r] if c < len(physical_state) and r < len(physical_state[c]) else 0
                if val != 0 and (c, r) not in target_pieces:
                    # Non-target square is occupied: warn player to remove it
                    warn_pulse = 0.40 + 0.35 * math.sin(6.0 * now)
                    set_square_in_frame(frame, c, r, scale_color(col_unexpected, warn_pulse))


def render_white_setup_complete_wave(
    progress: float,
    frame: list[int],
    params: dict[str, Any] | None = None,
) -> None:
    """
    Renders the transition wave when all White pieces are placed:
    - A smooth warm Ivory wave sweeps across ranks 1-2 from file a to h (0.0 <= progress <= 1.0).
    """
    params = params or {}
    is_night = bool(params.get("night_mode", False))
    col_wave = COLOR_INT_NIGHT_TURN_WHITE if is_night else COLOR_INT_START_WHITE_PRIMARY

    p = max(0.0, min(1.0, progress))
    sweep_col = p * 8.0  # Travels from file 0 to file 7

    for c in range(8):
        dist = abs(c - sweep_col)
        wave_int = math.exp(-2.5 * dist * dist)
        if wave_int > 0.05:
            # Highlight ranks 1 and 2
            set_square_in_frame(frame, c, 0, scale_color(col_wave, wave_int * 0.8))
            set_square_in_frame(frame, c, 1, scale_color(col_wave, wave_int * 0.8))
