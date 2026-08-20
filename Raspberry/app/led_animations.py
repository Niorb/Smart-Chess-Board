"""
app/led_animations.py

Procedural WS2812B LED animation engine and frame renderers for the Smart Chess Board.
Provides lifecycle animations (GAME_STARTED, GAME_WON, GAME_LOST, GAME_DRAWN)
and dynamic comet move-trace interpolation.
"""

from dataclasses import dataclass, field
import math
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from app.config import (
        ANIM_CASTLE_PERIOD_S,
        ANIM_GAME_DRAWN_DURATION_S,
        ANIM_GAME_LOST_DURATION_S,
        ANIM_GAME_START_DURATION_S,
        ANIM_GAME_WON_DURATION_S,
        ANIM_SEEKING_DURATION_S,
        ANIM_SEEKING_PERIOD_S,
        MOVE_TRACE_PERIOD_S,
        NUM_LEDS,
    )
    from app.led_helpers import (
        COLOR_INT_CAPTURE_AURA_ATTACKER,
        COLOR_INT_CAPTURE_AURA_TARGET,
        COLOR_INT_DEFEAT_RED,
        COLOR_INT_DRAW_BLUE,
        COLOR_INT_DRAW_WHITE,
        COLOR_INT_GUARDRAIL_MISSING,
        COLOR_INT_GUARDRAIL_UNEXPECTED,
        COLOR_INT_MOVE_TRACE,
        COLOR_INT_NIGHT_DRAW_BLUE,
        COLOR_INT_NIGHT_MODE,
        COLOR_INT_NIGHT_SEEKING_BODY,
        COLOR_INT_NIGHT_SEEKING_HEAD,
        COLOR_INT_NIGHT_SEEKING_TAIL,
        COLOR_INT_NIGHT_START_BLACK_PRIMARY,
        COLOR_INT_NIGHT_START_BLACK_SECONDARY,
        COLOR_INT_OFF,
        COLOR_INT_OPPONENT_DISCONNECTED,
        COLOR_INT_OPPONENT_FROM,
        COLOR_INT_SEEKING_BODY,
        COLOR_INT_SEEKING_HEAD,
        COLOR_INT_SEEKING_TAIL,
        COLOR_INT_START_BLACK_PRIMARY,
        COLOR_INT_START_BLACK_SECONDARY,
        COLOR_INT_START_WHITE_PRIMARY,
        COLOR_INT_START_WHITE_SECONDARY,
        COLOR_INT_TURN_BLACK,
        COLOR_INT_TURN_WHITE,
        COLOR_INT_VICTORY_GOLD,
        COLOR_INT_VICTORY_GREEN,
        get_led_indices,
    )
except ImportError:
    from .config import (
        ANIM_CASTLE_PERIOD_S,
        ANIM_GAME_DRAWN_DURATION_S,
        ANIM_GAME_LOST_DURATION_S,
        ANIM_GAME_START_DURATION_S,
        ANIM_GAME_WON_DURATION_S,
        ANIM_SEEKING_DURATION_S,
        ANIM_SEEKING_PERIOD_S,
        MOVE_TRACE_PERIOD_S,
        NUM_LEDS,
    )
    from .led_helpers import (
        COLOR_INT_CAPTURE_AURA_ATTACKER,
        COLOR_INT_CAPTURE_AURA_TARGET,
        COLOR_INT_DEFEAT_RED,
        COLOR_INT_DRAW_BLUE,
        COLOR_INT_DRAW_WHITE,
        COLOR_INT_GUARDRAIL_MISSING,
        COLOR_INT_GUARDRAIL_UNEXPECTED,
        COLOR_INT_MOVE_TRACE,
        COLOR_INT_NIGHT_DRAW_BLUE,
        COLOR_INT_NIGHT_MODE,
        COLOR_INT_NIGHT_SEEKING_BODY,
        COLOR_INT_NIGHT_SEEKING_HEAD,
        COLOR_INT_NIGHT_SEEKING_TAIL,
        COLOR_INT_NIGHT_START_BLACK_PRIMARY,
        COLOR_INT_NIGHT_START_BLACK_SECONDARY,
        COLOR_INT_OFF,
        COLOR_INT_OPPONENT_DISCONNECTED,
        COLOR_INT_OPPONENT_FROM,
        COLOR_INT_SEEKING_BODY,
        COLOR_INT_SEEKING_HEAD,
        COLOR_INT_SEEKING_TAIL,
        COLOR_INT_START_BLACK_PRIMARY,
        COLOR_INT_START_BLACK_SECONDARY,
        COLOR_INT_START_WHITE_PRIMARY,
        COLOR_INT_START_WHITE_SECONDARY,
        COLOR_INT_TURN_BLACK,
        COLOR_INT_TURN_WHITE,
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


def unpack_rgb(color_int: int) -> Tuple[int, int, int]:
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


def set_square_in_frame(frame: List[int], c: int, r: int, color_val: int) -> None:
    """Sets all physical LEDs belonging to square (c, r) in the frame buffer."""
    if 0 <= c < 8 and 0 <= r < 8:
        for idx in get_led_indices(r, c):
            if 0 <= idx < len(frame):
                frame[idx] = color_val


def blend_square_in_frame(frame: List[int], c: int, r: int, color_val: int, alpha: float) -> None:
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
    path: List[Tuple[int, int]],
    sub_tau: float,
    frame: List[int],
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
    path: List[Tuple[int, int]],
    now: float,
    frame: List[int],
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
    king_path: List[Tuple[int, int]],
    rook_path: List[Tuple[int, int]],
    now: float,
    frame: List[int],
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

def render_game_started(progress: float, frame: List[int], params: Dict[str, Any]) -> None:
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

    # Phase 1 (progress 0.0 -> 0.65): Army Ignition Sweep
    if progress < 0.65:
        p_sweep = progress / 0.65
        n_sq = len(army_path)
        head_pos = p_sweep * (n_sq - 1)
        for i, (c, r) in enumerate(army_path):
            dist = abs(i - head_pos)
            if dist < 2.2:
                intensity = math.exp(-2.0 * dist * dist)
                if intensity > 0.03:
                    col = blend_colors(primary_col, secondary_col, min(1.0, dist * 0.7))
                    set_square_in_frame(frame, c, r, scale_color(col, intensity * 0.9))

    # Phase 2 (progress 0.50 -> 0.85): Royal Focus Pulse on King & Queen
    if 0.50 <= progress <= 0.85:
        p_royal = (progress - 0.50) / 0.35
        royal_intensity = math.sin(p_royal * math.pi) * 0.85
        if royal_intensity > 0.03:
            for k_c, k_r in royal_squares:
                col = blend_colors(primary_col, COLOR_INT_DRAW_WHITE, 0.3)
                set_square_in_frame(frame, k_c, k_r, scale_color(col, royal_intensity))

    # Phase 3 (progress 0.70 -> 1.0): Battle Line Center Ignition
    if progress >= 0.70:
        p_center = (progress - 0.70) / 0.30
        for (from_c, from_r), (to_c, to_r) in center_clash:
            curr_r = from_r + (to_r - from_r) * min(1.0, p_center * 1.4)
            for r_cand in range(min(from_r, to_r), max(from_r, to_r) + 1):
                dist = abs(r_cand - curr_r)
                if dist < 1.2:
                    spark_int = math.exp(-3.0 * dist * dist) * (1.0 - p_center * 0.5)
                    if spark_int > 0.03:
                        set_square_in_frame(frame, from_c, r_cand, scale_color(primary_col, spark_int * 0.7))


def render_game_won(
    progress: float, frame: List[int], params: Dict[str, Any], now: float = 0.0
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


# Game Lost Palette: "The Royal Cataclysm (Requiem for a Fallen Sovereign)"
COLOR_INT_CROWN_LIGHTNING = color_rgb(255, 245, 230)  # Fractured white lightning flash
COLOR_INT_STRIKE_RUBY = color_rgb(255, 18, 48)  # Blazing laser strike ruby
COLOR_INT_BLOOD_RUBY = color_rgb(196, 12, 32)  # Expanding shockwave ruby
COLOR_INT_CROWN_EMBER = color_rgb(235, 110, 10)  # Molten crown amber shards
COLOR_INT_OBSIDIAN_CRIMSON = color_rgb(120, 8, 18)  # Deep trailing fissure crimson
COLOR_INT_DYING_CINDER = color_rgb(68, 6, 4)  # Smoldering ember cinder
COLOR_INT_CHARRED_ASH = color_rgb(24, 2, 2)  # Fading charcoal ash


def render_game_lost(
    progress: float, frame: List[int], params: Dict[str, Any], now: float = 0.0
) -> None:
    """
    GAME_LOST animation: "The Royal Cataclysm (Requiem for a Fallen Sovereign)"
    A high-impact, 4-phase cyber-physical defeat sequence dynamically centered on the defeated King:
    - Phase 1: The Crimson Siege / Converging Crossfire (0.00 <= progress < 0.28).
      3 lethal ballistic laser bolts converging from board perimeters onto the King.
    - Phase 2: Crown Shatter & Hyper-Radial Shockwave (0.28 <= progress < 0.58).
      White-hot lightning detonation on King's square + expanding Gaussian shockwave ring + 4 flying shards.
    - Phase 3: Fissure Decay & Obsidian Abyss (0.58 <= progress < 0.82).
      Organic cinders & jagged cooling fissures collapsing back towards the King.
    - Phase 4: The Royal Eclipse / Dying Hearth Pulse (0.82 <= progress <= 1.00).
      Solitary biphasic cardiac pulse on the King's square fading into complete blackout.

    Hardware Budget: 8-14 active squares peak during shockwave (< 22% board power),
    safely managed by binary chunking and power rail stability.
    """
    if now == 0.0:
        now = time.time()

    # 1. Clear frame buffer
    for c in range(8):
        for r in range(8):
            set_square_in_frame(frame, c, r, COLOR_INT_OFF)

    progress = max(0.0, min(1.0, progress))

    # 2. Dynamic King Position Extraction
    if "king_c" in params and "king_r" in params:
        try:
            king_c = int(round(float(params["king_c"])))
            king_r = int(round(float(params["king_r"])))
            if not (0 <= king_c < 8 and 0 <= king_r < 8):
                king_c, king_r = 4, 0
        except (ValueError, TypeError):
            king_c, king_r = 4, 0
    elif "king_sq" in params and isinstance(params["king_sq"], (tuple, list)) and len(params["king_sq"]) == 2:
        try:
            king_c = int(round(float(params["king_sq"][0])))
            king_r = int(round(float(params["king_sq"][1])))
            if not (0 <= king_c < 8 and 0 <= king_r < 8):
                king_c, king_r = 4, 0
        except (ValueError, TypeError):
            king_c, king_r = 4, 0
    else:
        my_color = str(params.get("my_color", "white")).strip().lower()
        king_c, king_r = (4, 7) if my_color == "black" else (4, 0)

    # 3. Phase Dispatch & Choreography
    if progress < 0.25:
        # =========================================================================
        # PHASE 1: The Crimson Siege / Converging Crossfire (0.00 -> 0.25)
        # =========================================================================
        p1 = progress / 0.25  # 0.0 -> 1.0
        e1 = p1 ** 1.35  # Accelerating ballistic projectile

        # 3 distinct converging vectors from opposing board perimeters
        origins = [
            (7 - king_c, 7 if king_r < 4 else 0),  # Opposite rank mirror
            (7 if king_c < 4 else 0, 7 - king_r),  # Opposite file mirror
            (7 - king_c, 7 - king_r)  # Diagonal polar mirror
        ]

        for orig_c, orig_r in origins:
            cur_c = orig_c + (king_c - orig_c) * e1
            cur_r = orig_r + (king_r - orig_r) * e1

            # Render bolt head (blazing ruby with white tip)
            for c in range(8):
                for r in range(8):
                    dist = math.hypot(c - cur_c, r - cur_r)
                    if dist < 1.1:
                        intensity = math.exp(-4.0 * dist * dist) * (0.65 + 0.35 * p1)
                        if intensity > 0.06:
                            col = blend_colors(COLOR_INT_STRIKE_RUBY, COLOR_INT_CROWN_LIGHTNING, max(0.0, 1.0 - dist))
                            blend_square_in_frame(frame, c, r, scale_color(col, intensity), 0.9)

    elif progress < 0.55:
        # =========================================================================
        # PHASE 2: Crown Shatter & Hyper-Radial Shockwave (0.25 -> 0.55)
        # =========================================================================
        p2 = (progress - 0.25) / 0.30  # 0.0 -> 1.0

        # A. Central Detonation Flash (initial 35% of Phase 2)
        if p2 < 0.35:
            flash_p = p2 / 0.35
            flash_int = (1.0 - flash_p) ** 2
            flash_col = blend_colors(COLOR_INT_CROWN_LIGHTNING, COLOR_INT_CROWN_EMBER, flash_p)
            set_square_in_frame(frame, king_c, king_r, scale_color(flash_col, flash_int))

        # B. Expanding Gaussian Shockwave Ring
        wave_radius = (p2 ** 0.80) * 8.2
        wave_sigma = 0.28 + 0.12 * p2
        ring_decay = 1.0 - 0.55 * p2

        for c in range(8):
            for r in range(8):
                d_k = math.hypot(c - king_c, r - king_r)
                dr = abs(d_k - wave_radius)
                if dr < 0.48:
                    intensity = math.exp(-(dr * dr) / (2.0 * wave_sigma * wave_sigma)) * ring_decay
                    if intensity > 0.12:
                        col = blend_colors(COLOR_INT_BLOOD_RUBY, COLOR_INT_OBSIDIAN_CRIMSON, min(1.0, d_k / 8.0))
                        blend_square_in_frame(frame, c, r, scale_color(col, intensity), 0.85)

        # C. 4 Flying Molten Crown Shards
        shard_dirs = [(-1.0, 1.0), (1.0, 1.0), (-1.0, -1.0), (1.0, -1.0)]
        shard_dist = (p2 ** 0.75) * 3.2
        shard_int = (1.0 - p2) * 0.90 + 0.08

        for dir_x, dir_y in shard_dirs:
            s_c = king_c + dir_x * shard_dist
            s_r = king_r + dir_y * shard_dist
            sc_i, sr_i = int(round(s_c)), int(round(s_r))
            if 0 <= sc_i < 8 and 0 <= sr_i < 8 and shard_int > 0.06:
                shard_col = blend_colors(COLOR_INT_CROWN_EMBER, COLOR_INT_STRIKE_RUBY, p2)
                blend_square_in_frame(frame, sc_i, sr_i, scale_color(shard_col, shard_int), 0.95)

    elif progress < 0.80:
        # =========================================================================
        # PHASE 3: Fissure Decay & Obsidian Abyss (0.55 -> 0.80)
        # =========================================================================
        p3 = (progress - 0.55) / 0.25  # 0.0 -> 1.0
        decay_env = (1.0 - p3) ** 1.3

        for c in range(8):
            for r in range(8):
                d_k = math.hypot(c - king_c, r - king_r)
                if d_k <= 1.5:
                    # Harmonic cinder noise & tight radial falloff around shattered throne
                    flicker = 0.75 + 0.25 * math.sin(now * 16.0 + c * 19.3 + r * 31.7)
                    falloff = math.exp(-d_k / 0.95)
                    intensity = decay_env * falloff * flicker
                    if d_k < 0.1:
                        intensity = max(0.08 * decay_env, intensity)

                    if intensity > 0.02:
                        col = blend_colors(COLOR_INT_CROWN_EMBER, COLOR_INT_DYING_CINDER, min(1.0, p3 + d_k * 0.15))
                        set_square_in_frame(frame, c, r, scale_color(col, intensity * 0.90))

    else:
        # =========================================================================
        # PHASE 4: The Royal Eclipse / Dying Hearth Pulse (0.80 -> 1.00)
        # =========================================================================
        p4 = (progress - 0.80) / 0.20  # 0.0 -> 1.0

        if p4 < 0.98:
            # Bi-phasic heartbeat wave ("lub-dub")
            hb_osc = (math.sin(p4 * 2.5 * math.pi) ** 6) + 0.40 * (math.sin(max(0.0, p4 * 2.5 * math.pi - 0.35 * math.pi)) ** 6)
            hb_env = math.exp(-2.5 * p4)
            pulse_intensity = max(0.04, hb_osc * hb_env * 0.95)

            ember_col = blend_colors(COLOR_INT_BLOOD_RUBY, COLOR_INT_CHARRED_ASH, p4)
            set_square_in_frame(frame, king_c, king_r, scale_color(ember_col, pulse_intensity))
        else:
            set_square_in_frame(frame, king_c, king_r, COLOR_INT_OFF)





def render_game_drawn(
    progress: float, frame: List[int], params: Dict[str, Any], now: float = 0.0
) -> None:
    """
    GAME_DRAWN animation:
    Symmetrical curtain sweep across files a-d and e-h meeting in the center in tranquil blue and white.
    """
    if now == 0.0:
        now = time.time()

    curtain_pos = progress * 4.2  # 0.0 (perimeter a, h) to 3.5 (center d, e)
    fade = 1.0 - (progress * 0.4)
    blue_col = COLOR_INT_NIGHT_DRAW_BLUE if params.get("night_mode", False) else COLOR_INT_DRAW_BLUE

    for c in range(8):
        # Symmetrical file coordinate from perimeter (0 for a/h, 3 for d/e)
        file_dist = min(c, 7 - c)
        d = abs(file_dist - curtain_pos)
        wave = math.exp(-2.2 * d * d)
        settled = 0.35 if file_dist <= curtain_pos else 0.0

        for r in range(8):
            ripple = 0.85 + 0.15 * math.sin(now * 3.5 + r * 0.9)
            intensity = max(0.0, min(1.0, wave + settled)) * fade * ripple
            color = blend_colors(blue_col, COLOR_INT_DRAW_WHITE, 0.4)
            set_square_in_frame(frame, c, r, scale_color(color, intensity))


# =============================================================================
# PERIMETER COORDINATES & SEEKING ANIMATION
# =============================================================================

# 28 perimeter squares ordered clockwise:
# Rank 1: (0,0) -> (7,0)
# File h: (7,1) -> (7,7)
# Rank 8: (6,7) -> (0,7)
# File a: (0,6) -> (0,1)
PERIMETER_COORDS: List[Tuple[int, int]] = (
    [(c, 0) for c in range(8)]
    + [(7, r) for r in range(1, 8)]
    + [(c, 7) for c in range(6, -1, -1)]
    + [(0, r) for r in range(6, 0, -1)]
)


def render_seeking(
    now: float,
    frame: List[int],
    params: Dict[str, Any],
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


# =============================================================================
# LIFECYCLE ANIMATION CLASS & FACTORY
# =============================================================================

@dataclass
class LifecycleAnimation:
    """State and rendering coordinator for a procedural LED lifecycle animation."""
    name: str
    duration: float
    start_time: float = field(default_factory=time.time)
    params: Dict[str, Any] = field(default_factory=dict)

    def is_active(self, now: Optional[float] = None) -> bool:
        """Returns True if the animation is currently running within its duration."""
        if now is None:
            now = time.time()
        return (now - self.start_time) < self.duration

    def get_progress(self, now: Optional[float] = None) -> float:
        """Returns progress fraction clamped between 0.0 and 1.0."""
        if now is None:
            now = time.time()
        if self.duration <= 0:
            return 1.0
        return max(0.0, min(1.0, (now - self.start_time) / self.duration))

    def render(self, now: float, frame: List[int]) -> None:
        """Renders the current animation frame into the LED frame buffer."""
        progress = self.get_progress(now)
        anim_name = self.name.upper()

        if anim_name == "GAME_STARTED":
            render_game_started(progress, frame, self.params)
        elif anim_name == "GAME_WON":
            render_game_won(progress, frame, self.params, now=now)
        elif anim_name == "GAME_LOST":
            render_game_lost(progress, frame, self.params, now=now)
        elif anim_name == "GAME_DRAWN":
            render_game_drawn(progress, frame, self.params, now=now)
        elif anim_name in ("SEEKING", "WAITING_FOR_OPPONENT", "MATCHMAKING"):
            render_seeking(now, frame, self.params)


def create_animation(
    name: str, params: Optional[Dict[str, Any]] = None
) -> LifecycleAnimation:
    """
    Animation factory creating configured LifecycleAnimation instances.

    Args:
        name: Name of animation ('GAME_STARTED', 'GAME_WON', 'GAME_LOST', 'GAME_DRAWN', 'SEEKING', 'WAITING_FOR_OPPONENT').
        params: Optional metadata dict (e.g. {'my_color': 'white'}).

    Returns:
        LifecycleAnimation instance with predefined duration.
    """
    clean_name = name.strip().upper()
    durations = {
        "GAME_STARTED": ANIM_GAME_START_DURATION_S,
        "GAME_WON": ANIM_GAME_WON_DURATION_S,
        "GAME_LOST": ANIM_GAME_LOST_DURATION_S,
        "GAME_DRAWN": ANIM_GAME_DRAWN_DURATION_S,
        "SEEKING": ANIM_SEEKING_DURATION_S,
        "WAITING_FOR_OPPONENT": ANIM_SEEKING_DURATION_S,
        "MATCHMAKING": ANIM_SEEKING_DURATION_S,
    }
    duration = durations.get(clean_name, 2.0)
    return LifecycleAnimation(
        name=clean_name,
        duration=duration,
        start_time=time.time(),
        params=params or {},
    )


def render_capture_aura(
    target_sq: Tuple[int, int],
    candidate_attackers: List[Tuple[int, int]],
    now: float,
    frame: List[int],
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
    missing_pieces: List[Tuple[int, int]],
    unexpected_pieces: List[Tuple[int, int]],
    now: float,
    frame: List[int],
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
    frame: List[int],
    opponent_gone_info: Dict[str, Any],
    my_color: str,
    opponent_king_sq: Optional[Tuple[int, int]] = None,
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
