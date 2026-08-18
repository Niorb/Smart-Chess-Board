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
        ANIM_GAME_DRAWN_DURATION_S,
        ANIM_GAME_LOST_DURATION_S,
        ANIM_GAME_START_DURATION_S,
        ANIM_GAME_WON_DURATION_S,
        MOVE_TRACE_PERIOD_S,
        NUM_LEDS,
    )
    from app.led_helpers import (
        COLOR_INT_DEFEAT_RED,
        COLOR_INT_DRAW_BLUE,
        COLOR_INT_DRAW_WHITE,
        COLOR_INT_MOVE_TRACE,
        COLOR_INT_OFF,
        COLOR_INT_OPPONENT_FROM,
        COLOR_INT_VICTORY_GOLD,
        COLOR_INT_VICTORY_GREEN,
        get_led_indices,
    )
except ImportError:
    from .config import (
        ANIM_GAME_DRAWN_DURATION_S,
        ANIM_GAME_LOST_DURATION_S,
        ANIM_GAME_START_DURATION_S,
        ANIM_GAME_WON_DURATION_S,
        MOVE_TRACE_PERIOD_S,
        NUM_LEDS,
    )
    from .led_helpers import (
        COLOR_INT_DEFEAT_RED,
        COLOR_INT_DRAW_BLUE,
        COLOR_INT_DRAW_WHITE,
        COLOR_INT_MOVE_TRACE,
        COLOR_INT_OFF,
        COLOR_INT_OPPONENT_FROM,
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

def render_move_trace(
    path: List[Tuple[int, int]],
    now: float,
    frame: List[int],
    trace_color: int = COLOR_INT_MOVE_TRACE,
    period: float = MOVE_TRACE_PERIOD_S,
    blend_arrival: bool = True,
) -> None:
    """
    Renders an animated comet traveling along path coordinates from origin to destination.

    Intermediate squares receive a traveling Gaussian comet glow.
    The destination/arrival square pulses with an additive luminance flare upon comet arrival.

    Args:
        path: Ordered list of (file, rank) tuples from origin to destination (len >= 2).
        now: Current timestamp in seconds (time.time()).
        frame: LED frame buffer (list of integer colors).
        trace_color: Color of the moving pulse.
        period: Time in seconds for one complete traversal and decay cycle.
        blend_arrival: Whether to blend the arrival pulse onto the existing target square color.
    """
    if len(path) < 2 or period <= 0:
        return

    num_squares = len(path)
    num_steps = num_squares - 1
    delta_overshoot = 1.2
    total_span = num_steps + delta_overshoot
    tau = (now % period) / period  # 0.0 to 1.0
    comet_pos = tau * total_span

    # Render comet tail across intermediate squares
    for i in range(1, num_steps):
        c, r = path[i]
        dist = abs(comet_pos - i)
        # Pulse intensity with Gaussian falloff (width ~ 0.9 squares)
        intensity = math.exp(-2.5 * dist * dist)
        if intensity > 0.02:
            scaled = scale_color(trace_color, intensity)
            blend_square_in_frame(frame, c, r, scaled, intensity)

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


# =============================================================================
# PROCEDURAL LIFECYCLE RENDERERS
# =============================================================================

def render_game_started(progress: float, frame: List[int], params: Dict[str, Any]) -> None:
    """
    GAME_STARTED animation:
    Radial expanding wave from center (d4, d5, e4, e5) outward to perimeter.
    """
    my_color = params.get("my_color", "white")
    flare_color = (
        COLOR_INT_VICTORY_GOLD if my_color == "white" else COLOR_INT_VICTORY_GREEN
    )

    center_c = 3.5
    center_r = 3.5
    max_radius = 5.0
    current_radius = progress * (max_radius + 1.2)

    for c in range(8):
        for r in range(8):
            dist = math.sqrt((c - center_c) ** 2 + (r - center_r) ** 2)
            d = abs(dist - current_radius)
            # Gaussian wavefront
            wave = math.exp(-3.0 * d * d)
            # Fading trail
            trail = (
                math.exp(-1.5 * dist) * (1.0 - progress) * 0.4
                if dist < current_radius
                else 0.0
            )
            intensity = max(0.0, min(1.0, wave + trail)) * (1.0 - 0.3 * progress)

            if intensity > 0.02:
                col = blend_colors(COLOR_INT_VICTORY_GREEN, flare_color, 0.5)
                set_square_in_frame(frame, c, r, scale_color(col, intensity))


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
    # Phase 1: Diagonal sweep (a1 -> h8) for progress in [0.0, 0.48]
    p1 = progress / 0.48
    w1 = p1 * 18.0 - 2.0 if progress <= 0.48 else 99.0

    # Phase 2: Counter-diagonal sweep (a8 -> h1) for progress in [0.40, 0.84]
    p2 = (progress - 0.40) / 0.44
    w2 = p2 * 18.0 - 2.0 if 0.40 <= progress <= 0.84 else 99.0

    # Phase 3: Center Diamond Flare for progress in [0.78, 1.0]
    p3 = (progress - 0.78) / 0.22 if progress >= 0.78 else 0.0
    r3 = p3 * 2.4

    for c in range(8):
        for r in range(8):
            w1_val = 0.0
            w2_val = 0.0
            w3_val = 0.0

            # Phase 1: Diagonal Wavefront
            if progress <= 0.48:
                u1 = c + r
                v1 = c - r
                du1 = u1 - w1
                w1_val = math.exp(-2.5 * du1 * du1 - 0.07 * v1 * v1)

            # Phase 2: Counter-Diagonal Wavefront
            if 0.40 <= progress <= 0.84:
                u2 = c + (7 - r)
                v2 = c - (7 - r)
                du2 = u2 - w2
                w2_val = math.exp(-2.5 * du2 * du2 - 0.07 * v2 * v2)

            # Phase 3: Center Diamond Pulse
            if progress >= 0.78:
                dist_center = math.sqrt((c - 3.5) ** 2 + (r - 3.5) ** 2)
                dr = dist_center - r3
                w3_val = math.exp(-3.2 * dr * dr) * ((1.0 - p3) ** 2)

            # Primary wave composite
            w_total = w1_val + w2_val + w3_val
            if w_total > 0.001:
                # Color blending based on phase dominance
                blend_g = (w1_val * 0.3 + w2_val * 0.9) / w_total
                base_color = blend_colors(col_gold, col_green, blend_g)
            else:
                base_color = col_gold

            primary_intensity = w_total * envelope

            # 4. Sparse Stardust Twinkles (Only top ~2.5% threshold fires)
            h1 = math.sin(now * 13.0 + c * 17.1 + r * 31.7)
            h2 = math.cos(now * 8.5 + c * 29.3 + r * 11.9)
            sparkle_harmonic = h1 * h2
            if sparkle_harmonic > 0.82:
                s_factor = ((sparkle_harmonic - 0.82) / 0.18) ** 2
                sparkle_intensity = s_factor * 0.80 * envelope
            else:
                sparkle_intensity = 0.0

            # 5. Final Composite & Deadband Gating
            total_intensity = primary_intensity + sparkle_intensity
            if total_intensity > 0.025:
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


def create_animation(
    name: str, params: Optional[Dict[str, Any]] = None
) -> LifecycleAnimation:
    """
    Animation factory creating configured LifecycleAnimation instances.

    Args:
        name: Name of animation ('GAME_STARTED', 'GAME_WON', 'GAME_LOST', 'GAME_DRAWN').
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
    }
    duration = durations.get(clean_name, 2.0)
    return LifecycleAnimation(
        name=clean_name,
        duration=duration,
        start_time=time.time(),
        params=params or {},
    )
