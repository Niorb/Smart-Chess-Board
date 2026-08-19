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
        COLOR_INT_OFF,
        COLOR_INT_OPPONENT_FROM,
        COLOR_INT_SEEKING_BODY,
        COLOR_INT_SEEKING_HEAD,
        COLOR_INT_SEEKING_TAIL,
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
        COLOR_INT_OFF,
        COLOR_INT_OPPONENT_FROM,
        COLOR_INT_SEEKING_BODY,
        COLOR_INT_SEEKING_HEAD,
        COLOR_INT_SEEKING_TAIL,
        COLOR_INT_VICTORY_GOLD,
        COLOR_INT_VICTORY_GREEN,
        get_led_indices,
    )


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
    """Scales color brightness by a float factor (0.0 to 1.0)."""
    factor = max(0.0, min(1.0, factor))
    r = int(((color_int >> 16) & 0xFF) * factor)
    g = int(((color_int >> 8) & 0xFF) * factor)
    b = int((color_int & 0xFF) * factor)
    return (r << 16) | (g << 8) | b


def blend_colors(c1: int, c2: int, factor: float) -> int:
    """Linear interpolation between c1 (factor=0.0) and c2 (factor=1.0)."""
    factor = max(0.0, min(1.0, factor))
    r1, g1, b1 = (c1 >> 16) & 0xFF, (c1 >> 8) & 0xFF, c1 & 0xFF
    r2, g2, b2 = (c2 >> 16) & 0xFF, (c2 >> 8) & 0xFF, c2 & 0xFF
    r = int(r1 + (r2 - r1) * factor)
    g = int(g1 + (g2 - g1) * factor)
    b = int(b1 + (b2 - b1) * factor)
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
        d = head_pos - i
        # Asymmetric tail: head is sharp (d < 0), tail decays backwards (d >= 0)
        if -0.3 <= d <= 2.2:
            if d < 0:
                intensity = math.exp(-6.0 * d * d)
            else:
                intensity = math.exp(-1.4 * d)

            if intensity > 0.03:
                sq_color = scale_color(trace_color, intensity * 0.9)
                if 0 <= c < 8 and 0 <= r < 8:
                    for idx in get_led_indices(r, c):
                        if 0 <= idx < len(frame):
                            frame[idx] = add_colors(frame[idx], sq_color)

    # 2. Additive Arrival Square Pulse Flare
    if blend_arrival and head_pos >= (n - 1.2):
        c_arr, r_arr = path[-1]
        progress_arr = min(1.0, max(0.0, (head_pos - (n - 1.2)) / 1.5))
        intensity_arr = math.exp(-2.5 * progress_arr) * (1.0 - progress_arr)
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


def render_game_lost(progress: float, frame: List[int], params: Dict[str, Any]) -> None:
    """
    GAME_LOST animation:
    Collapsing perimeter red wave converging toward center and fading into dim ember glow.
    """
    king_c = params.get("king_c", 3.5)
    king_r = params.get("king_r", 3.5)

    max_dist = 5.2
    target_radius = (1.0 - progress) * max_dist
    fade = max(0.0, 1.0 - (progress * progress))

    for c in range(8):
        for r in range(8):
            dist = math.sqrt((c - king_c) ** 2 + (r - king_r) ** 2)
            d = abs(dist - target_radius)
            wave = math.exp(-2.5 * d * d)
            trailing_embers = math.exp(-0.8 * dist) * 0.3 * (1.0 - progress)

            intensity = max(0.0, min(1.0, wave + trailing_embers)) * fade
            color = blend_colors(COLOR_INT_DEFEAT_RED, COLOR_INT_OPPONENT_FROM, progress * 0.7)
            set_square_in_frame(frame, c, r, scale_color(color, intensity))


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

    for c in range(8):
        # Symmetrical file coordinate from perimeter (0 for a/h, 3 for d/e)
        file_dist = min(c, 7 - c)
        d = abs(file_dist - curtain_pos)
        wave = math.exp(-2.2 * d * d)
        settled = 0.35 if file_dist <= curtain_pos else 0.0

        for r in range(8):
            ripple = 0.85 + 0.15 * math.sin(now * 3.5 + r * 0.9)
            intensity = max(0.0, min(1.0, wave + settled)) * fade * ripple
            color = blend_colors(COLOR_INT_DRAW_BLUE, COLOR_INT_DRAW_WHITE, 0.4)
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

    for i, (c, r) in enumerate(PERIMETER_COORDS):
        delta_behind = (head_pos - i) % n

        if delta_behind <= 1.0:
            # Head and immediate trailing gradient
            intensity = 1.0 - 0.25 * delta_behind
            col = blend_colors(COLOR_INT_SEEKING_HEAD, COLOR_INT_SEEKING_BODY, delta_behind)
        elif delta_behind <= tail_length:
            # Body to tail decay
            t = (delta_behind - 1.0) / (tail_length - 1.0)
            intensity = 0.75 * ((1.0 - t) ** 1.8)
            col = blend_colors(COLOR_INT_SEEKING_BODY, COLOR_INT_SEEKING_TAIL, t)
        elif delta_behind > (n - 0.75):
            # Smooth leading edge ahead of head
            delta_ahead = n - delta_behind
            intensity = (1.0 - delta_ahead / 0.75) ** 2
            col = COLOR_INT_SEEKING_HEAD
        else:
            intensity = 0.0
            col = COLOR_INT_OFF

        if intensity > 0.02:
            set_square_in_frame(frame, c, r, scale_color(col, intensity))
        else:
            set_square_in_frame(frame, c, r, COLOR_INT_OFF)


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
            render_game_lost(progress, frame, self.params)
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
    target_col = blend_colors(COLOR_INT_CAPTURE_AURA_TARGET, COLOR_INT_CAPTURE_AURA_ATTACKER, pulse_t * 0.4)
    intensity = 0.6 + 0.4 * pulse_t
    scaled_target = scale_color(target_col, intensity)
    set_square_in_frame(frame, t_c, t_r, scaled_target)

    # Candidate attackers: rhythmic golden breathing pulse
    for i, (a_c, a_r) in enumerate(candidate_attackers):
        att_pulse = math.sin(now * 4.0 + i * 0.8) * 0.5 + 0.5
        att_intensity = 0.4 + 0.6 * att_pulse
        att_col = scale_color(COLOR_INT_CAPTURE_AURA_ATTACKER, att_intensity)
        set_square_in_frame(frame, a_c, a_r, att_col)


def render_guardrail_mismatch(
    missing_pieces: List[Tuple[int, int]],
    unexpected_pieces: List[Tuple[int, int]],
    now: float,
    frame: List[int],
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
        miss_col = scale_color(COLOR_INT_GUARDRAIL_MISSING, miss_intensity)
        for c, r in missing_pieces:
            set_square_in_frame(frame, c, r, miss_col)

    # Unexpected pieces pulse (crimson/red)
    if unexpected_pieces:
        unexp_pulse = math.sin(now * 8.0 * 2.0 * math.pi) * 0.5 + 0.5
        unexp_intensity = 0.35 + 0.65 * unexp_pulse
        unexp_col = scale_color(COLOR_INT_GUARDRAIL_UNEXPECTED, unexp_intensity)
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
