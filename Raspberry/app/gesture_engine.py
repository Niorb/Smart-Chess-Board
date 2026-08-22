"""
app/gesture_engine.py

Extensible Physical Board Gesture Engine for the Smart Chess Board.
Provides base gesture abstractions, physical matrix evaluation during IDLE / GAME_OVER states,
LED overlay generation, and concrete physical gesture implementations such as the
"Kingside Corner Gate" (lift h2 -> lift h1 -> replace both) to restart the previous match.
"""

import asyncio
import logging
import math
import time
from abc import ABC, abstractmethod
from typing import Any

try:
    from app.config import (
        BOARD_COLS,
        BOARD_ROWS,
    )
    from app.led_animations import scale_color
    from app.led_helpers import (
        COLOR_INT_AZURE,
        COLOR_INT_DAY_INDICATOR,
        COLOR_INT_MINT_EMERALD,
        COLOR_INT_NIGHT_INDICATOR,
        COLOR_INT_PIECE_LIFTED,
        COLOR_INT_ROYAL_VIOLET,
        Color,
    )
except ImportError:
    from .config import (
        BOARD_COLS,
        BOARD_ROWS,
    )
    from .led_animations import scale_color
    from .led_helpers import (
        COLOR_INT_AZURE,
        COLOR_INT_DAY_INDICATOR,
        COLOR_INT_MINT_EMERALD,
        COLOR_INT_NIGHT_INDICATOR,
        COLOR_INT_PIECE_LIFTED,
        COLOR_INT_ROYAL_VIOLET,
        Color,
    )

logger = logging.getLogger("smart-chess-app.gesture")

# Dedicated Gesture LED Colors (unique to gestures; shared palettes come from led_helpers)
COLOR_INT_EMERALD = Color(0, 220, 90)     # Radiant emerald pulse for completion gate

# Strong references to fire-and-forget tasks so they cannot be GC'd mid-flight
_pending_tasks: set[asyncio.Task] = set()


def _schedule_task(coro) -> asyncio.Task | None:
    """Schedules a coroutine on the running loop, keeping a strong reference until done."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("No running event loop; cannot dispatch gesture action.")
        return None
    task = loop.create_task(coro)
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)
    return task


def _read_night_mode() -> bool:
    try:
        from board_hardware import settings
        return bool(settings.get("night_mode", False))
    except Exception:
        return False


class BaseGesture(ABC):
    """
    Abstract Base Class for physical chessboard gestures.
    Subclasses evaluate the 8x8 sensor matrix and manage their step sequence and LED highlights.
    """

    starter_coord: tuple[int, int] | None = None
    starter_color: int | None = None

    def __init__(self, name: str, description: str, timeout: float = 5.0):
        self.name = name
        self.description = description
        self.timeout = timeout
        self.step: int = 0
        self.start_time: float = 0.0

    @property
    def is_active(self) -> bool:
        """Returns True if the gesture is currently in progress (step > 0)."""
        return self.step > 0

    @property
    @abstractmethod
    def hint(self) -> str | None:
        """Provides a human-readable guidance hint for the active gesture step."""
        pass

    def time_remaining(self, now: float) -> float:
        """Returns remaining seconds before the active gesture times out."""
        if not self.is_active or self.start_time <= 0:
            return 0.0
        return max(0.0, self.timeout - (now - self.start_time))

    @abstractmethod
    def evaluate(self, physical_state: list[list[int]], now: float) -> bool:
        """
        Evaluates physical board sensor states.
        Returns True when the gesture successfully completes.
        """
        pass

    @abstractmethod
    def get_led_overlay(self, now: float) -> dict[tuple[int, int], int]:
        """
        Returns a mapping of (col, row) -> 24-bit integer color for gesture LED illumination.
        """
        pass

    def reset(self) -> None:
        """Resets the gesture state to idle (step 0)."""
        self.step = 0
        self.start_time = 0.0

    @abstractmethod
    def execute_completion(self) -> None:
        """Dispatches the completion action (e.g. async task creation)."""
        pass

    def to_dict(self, now: float | None = None) -> dict[str, Any]:
        """Serializes the gesture status for WebSocket state payloads."""
        if now is None:
            now = time.time()
        return {
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "step": self.step,
            "hint": self.hint,
            "time_remaining": round(self.time_remaining(now), 1),
            "starter_coord": list(self.starter_coord) if self.starter_coord else None,
        }


class CornerGateGesture(BaseGesture):
    """
    Generic two-piece corner gate gesture state machine:
      - Step 1: first_coord piece lifted alone.
      - Step 2: second_coord piece lifted while first remains lifted.
      - Step 3 (Completion): both pieces replaced into the standard starting configuration.
    Any extra starting piece lift or center-square occupation cancels the gesture.
    """

    first_coord: tuple[int, int] = (7, 1)
    second_coord: tuple[int, int] = (7, 0)
    hint_step1: str = ""
    hint_step2: str = ""
    log_prefix: str = "Gesture"
    # Which gate square is the primary arrival-flash target ('first' or 'second')
    flash_primary: str = "second"

    def __init__(
        self,
        name: str,
        description: str,
        state_manager: Any = None,
        timeout: float = 5.0,
    ):
        super().__init__(name=name, description=description, timeout=timeout)
        self.state_manager = state_manager

    def _get_board_anomalies(
        self, physical_state: list[list[int]]
    ) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
        """
        Returns (lifted_starting_squares, extra_occupied_center_squares).
        Starting squares: Ranks 0, 1 (White), Ranks 6, 7 (Black).
        Center squares: Ranks 2..5 (expected empty).
        """
        lifted_starting: set[tuple[int, int]] = set()
        extra_occupied: set[tuple[int, int]] = set()

        for c in range(BOARD_COLS):
            for r in range(BOARD_ROWS):
                val = physical_state[c][r] if c < len(physical_state) and r < len(physical_state[c]) else 0
                if r in (0, 1, 6, 7):
                    if val == 0:
                        lifted_starting.add((c, r))
                else:
                    if val != 0:
                        extra_occupied.add((c, r))

        return lifted_starting, extra_occupied

    def _overlay_palette(self, now: float) -> tuple[int, int, int, int]:
        """Returns (lifted_solid, next_pulse, completion_first, completion_second) colors."""
        return (
            COLOR_INT_PIECE_LIFTED,
            COLOR_INT_AZURE,
            COLOR_INT_EMERALD,
            COLOR_INT_EMERALD,
        )

    def evaluate(self, physical_state: list[list[int]], now: float) -> bool:
        first = self.first_coord
        second = self.second_coord
        prefix = self.log_prefix
        lifted_starting, extra_occupied = self._get_board_anomalies(physical_state)

        # Center squares bumped with pieces immediately cancels gesture
        if len(extra_occupied) > 0:
            if self.is_active:
                logger.debug(f"{prefix} cancelled due to center pieces: {extra_occupied}")
            self.reset()
            return False

        # Step 0: Idle / Armed
        if self.step == 0:
            # Gesture begins when ONLY the first piece is lifted and the second is placed
            if lifted_starting == {first}:
                self.step = 1
                self.start_time = now
                logger.info(f"{prefix} armed: Step 1 ({first} lifted). Waiting for {second}...")
            return False

        # Timeout Check for active gesture (Steps 1 & 2)
        if now - self.start_time > self.timeout:
            logger.info(f"{prefix} timed out. Resetting.")
            self.reset()
            return False

        gate = {first, second}

        # Step 1: first piece lifted, waiting for second lift
        if self.step == 1:
            # Premature replacement of the first piece before lifting the second cancels gesture
            if first not in lifted_starting:
                logger.debug(f"{prefix} cancelled: {first} replaced prematurely without lifting {second}.")
                self.reset()
                return False

            # Bumping extra starting pieces outside of the gate cancels gesture
            if not lifted_starting.issubset(gate):
                logger.debug(f"{prefix} cancelled: unexpected piece lifted {lifted_starting - {first}}")
                self.reset()
                return False

            # Second piece is lifted while the first is also lifted -> advance to Step 2
            if lifted_starting == gate:
                self.step = 2
                logger.info(f"{prefix}: Step 2 ({first} & {second} both lifted). Ready for replacement.")
            return False

        # Step 2: Both gate pieces lifted, waiting for replacement
        if self.step == 2:
            # Bumping extra starting pieces outside of the gate cancels gesture
            if not lifted_starting.issubset(gate):
                logger.debug(f"{prefix} cancelled in Step 2: extra pieces lifted {lifted_starting}")
                self.reset()
                return False

            # Completion condition: Both gate pieces replaced, full starting position intact
            if len(lifted_starting) == 0:
                logger.info(f"{prefix} COMPLETED: Corner Gate closed!")
                self.reset()
                return True

            return False

        return False

    def get_led_overlay(self, now: float) -> dict[tuple[int, int], int]:
        lifted_col, next_col, comp_first, comp_second = self._overlay_palette(now)
        overlay: dict[tuple[int, int], int] = {}
        if self.step == 1:
            # First square: solid color; second square: breathing pulse guiding next lift
            overlay[self.first_coord] = lifted_col
            pulse = math.sin(now * 8.0) * 0.5 + 0.5
            intensity = 0.25 + 0.75 * pulse
            overlay[self.second_coord] = scale_color(next_col, intensity)
        elif self.step == 2:
            # Both squares: rapid synchronized pulse in completion colors
            pulse = math.sin(now * 10.0) * 0.5 + 0.5
            intensity = 0.35 + 0.65 * pulse
            overlay[self.first_coord] = scale_color(comp_first, intensity)
            overlay[self.second_coord] = scale_color(comp_second, intensity)
        return overlay

    def _flash_completion_squares(self, duration: float = 0.6) -> None:
        if self.state_manager:
            primary, extra = (
                (self.first_coord, self.second_coord)
                if self.flash_primary == "first"
                else (self.second_coord, self.first_coord)
            )
            self.state_manager.trigger_arrival_flash(
                primary[0],
                primary[1],
                duration=duration,
                extra_squares=[extra],
            )


class RestartPreviousGameGesture(CornerGateGesture):
    """
    Kingside Corner Gate gesture:
      - Initial setup: Full standard chess starting position.
      - Step 1: Lift h2 (column 7, row 1).
                LEDs: Amber on h2, pulsing Azure on h1.
      - Step 2: Lift h1 (column 7, row 0) while h2 remains lifted.
                LEDs: Pulsing Emerald on both h1 and h2.
      - Step 3 (Completion): Replace both pieces back to (7, 1) and (7, 0)
                in standard starting configuration.
      - Result: Triggers confirmation arrival flash on h1/h2 and starts
                matchmaking with the stored last_game_params.
    """

    H1_COORD: tuple[int, int] = (7, 0)  # File h (c=7), Rank 1 (r=0)
    H2_COORD: tuple[int, int] = (7, 1)  # File h (c=7), Rank 2 (r=1)
    starter_coord: tuple[int, int] = (7, 1)
    starter_color: int = Color(240, 160, 20)  # Warm Amber

    def __init__(self, state_manager: Any = None, timeout: float = 5.0):
        super().__init__(
            name="restart_previous_game",
            description="Kingside Corner Gate: lift h2 -> lift h1 -> replace both to restart last game",
            state_manager=state_manager,
            timeout=timeout,
        )
        self.first_coord = self.H2_COORD
        self.second_coord = self.H1_COORD
        self.hint_step1 = "Lift h1 (Rook) to complete corner gate"
        self.hint_step2 = "Replace h1 and h2 to restart previous game"
        self.log_prefix = "Restart gesture"

    @property
    def hint(self) -> str | None:
        if self.step == 1:
            return self.hint_step1
        elif self.step == 2:
            return self.hint_step2
        return None

    def execute_completion(self) -> None:
        """Triggers arrival confirmation flash and launches previous game matchmaking."""
        self._flash_completion_squares()

        async def _dispatch_restart():
            try:
                from board_hardware import get_last_game_params

                from app.lichess_engine import lichess_engine

                params = get_last_game_params()
                logger.info(
                    f"Restarting game via gesture with params: tc={params['time_control']}, rated={params['rated']}, "
                    f"color={params['color']}, opponent={params['opponent']}, ai_level={params['ai_level']}, "
                    f"range={params['rating_range']}"
                )
                await lichess_engine.seek(self.state_manager, **params)
            except Exception as e:
                logger.error(f"Error dispatching restart game seek in gesture: {e}")

        _schedule_task(_dispatch_restart())


class ToggleNightModeGesture(CornerGateGesture):
    """
    Queenside Corner Gate gesture to toggle Night Mode / Day Mode:
      - Initial setup: Full standard chess starting position.
      - Step 1: Lift a2 pawn (column 0, row 1).
                Visual Feedback:
                  - If currently in Night Mode: a2 solid Dark Blue, a1 pulsing Dark Blue.
                  - If currently in Day Mode: a2 solid Sun Amber/Gold, a1 pulsing Sun Amber/Gold.
      - Step 2: Lift a1 rook (column 0, row 0) while a2 remains lifted.
                Visual Feedback:
                  - Both a1 & a2: Rapid pulse in the TARGET mode's color.
      - Step 3 (Completion): Replace both pieces back to standard starting position (0, 1) and (0, 0).
      - Result:
          - Toggles `settings["night_mode"] = not settings["night_mode"]`.
          - Saves updated settings to disk.
          - Triggers arrival confirmation flash on a1 & a2 in the new mode's theme color (0.6s).
    """

    A1_COORD: tuple[int, int] = (0, 0)  # File a (c=0), Rank 1 (r=0)
    A2_COORD: tuple[int, int] = (0, 1)  # File a (c=0), Rank 2 (r=1)
    starter_coord: tuple[int, int] = (0, 1)
    starter_color: int = Color(0, 140, 255)  # Moonlight Azure

    def __init__(self, state_manager: Any = None, timeout: float = 5.0):
        super().__init__(
            name="toggle_night_mode",
            description="Queenside Corner Gate: lift a2 -> lift a1 -> replace both to toggle Night/Day mode",
            state_manager=state_manager,
            timeout=timeout,
        )
        self.first_coord = self.A2_COORD
        self.second_coord = self.A1_COORD
        self.log_prefix = "Night mode gesture"

    @property
    def hint(self) -> str | None:
        target_name = "Day Mode" if _read_night_mode() else "Night Mode"
        if self.step == 1:
            return f"Lift a1 (Rook) to toggle to {target_name}"
        elif self.step == 2:
            return f"Replace a1 and a2 to activate {target_name}"
        return None

    def _overlay_palette(self, now: float) -> tuple[int, int, int, int]:
        is_night = _read_night_mode()

        # Current mode indicator color: Dark Blue for Night Mode, Solar Gold for Day Mode
        curr_color = COLOR_INT_NIGHT_INDICATOR if is_night else COLOR_INT_DAY_INDICATOR
        # Target mode color: the opposite of current mode
        target_color = COLOR_INT_DAY_INDICATOR if is_night else COLOR_INT_NIGHT_INDICATOR
        return (curr_color, curr_color, target_color, target_color)

    def execute_completion(self) -> None:
        """Toggles night_mode in settings, saves, and triggers arrival flash."""
        try:
            from board_hardware import save_settings, settings
            new_night_mode = not bool(settings.get("night_mode", False))
            settings["night_mode"] = new_night_mode
            save_settings()
            logger.info(f"Physical gesture successfully toggled night_mode to: {new_night_mode}")
        except Exception as e:
            logger.error(f"Error toggling night_mode in gesture: {e}")

        self._flash_completion_squares()


class CenterRoyalGateGesture(CornerGateGesture):
    """
    Center Royal Gate gesture:
      - Initial setup: Full standard chess starting position.
      - Step 1: Lift e2 pawn (column 4, row 1).
                LEDs: Solid Royal Violet on e2, pulsing Mint Emerald on d2.
      - Step 2: Lift d2 pawn (column 3, row 1) while e2 remains lifted.
                LEDs: Dual synchronous Emerald/Violet rapid pulse on d2 and e2.
      - Step 3 (Completion): Replace both d2 and e2 pawns back into starting setup.
      - Result: Activates Post-Game Analysis mode on the board and starts
                batch Stockfish analysis of the last game.
    """

    E2_COORD: tuple[int, int] = (4, 1)  # File e (c=4), Rank 2 (r=1)
    D2_COORD: tuple[int, int] = (3, 1)  # File d (c=3), Rank 2 (r=1)
    starter_coord: tuple[int, int] = (4, 1)
    starter_color: int = COLOR_INT_ROYAL_VIOLET

    def __init__(self, state_manager: Any = None, timeout: float = 5.0):
        super().__init__(
            name="start_analysis",
            description="Center Royal Gate: lift e2 -> lift d2 -> replace both to activate Post-Game Analysis",
            state_manager=state_manager,
            timeout=timeout,
        )
        self.first_coord = self.E2_COORD
        self.second_coord = self.D2_COORD
        self.log_prefix = "Analysis gesture"
        self.flash_primary = "first"

    @property
    def hint(self) -> str | None:
        if self.step == 1:
            return "Lift d2 (Queen Pawn) to arm Analysis Mode"
        elif self.step == 2:
            return "Replace e2 and d2 to activate Post-Game Analysis"
        return None

    def _overlay_palette(self, now: float) -> tuple[int, int, int, int]:
        return (
            COLOR_INT_ROYAL_VIOLET,
            COLOR_INT_MINT_EMERALD,
            COLOR_INT_ROYAL_VIOLET,
            COLOR_INT_MINT_EMERALD,
        )

    def execute_completion(self) -> None:
        """Triggers arrival confirmation flare on d2/e2 and activates analysis mode."""
        self._flash_completion_squares()
        if self.state_manager:
            _schedule_task(self.state_manager.start_analysis_mode())


class PhysicalGestureEngine:
    """
    Subsystem manager for physical board gestures.
    Monitors board states during IDLE / GAME_OVER, generates LED overlay frames,
    and coordinates async gesture executions.
    """

    def __init__(self, state_manager: Any = None):
        self.state_manager = state_manager
        self.gestures: list[BaseGesture] = []
        # Register standard gestures
        self.register_gesture(RestartPreviousGameGesture(state_manager=state_manager))
        self.register_gesture(ToggleNightModeGesture(state_manager=state_manager))
        self.register_gesture(CenterRoyalGateGesture(state_manager=state_manager))

    def register_gesture(self, gesture: BaseGesture) -> None:
        """Registers a new gesture in the evaluation pipeline."""
        self.gestures.append(gesture)

    @property
    def is_active(self) -> bool:
        """Returns True if any registered gesture is actively progressing."""
        return any(g.is_active for g in self.gestures)

    @property
    def active_gesture(self) -> BaseGesture | None:
        """Returns the currently active gesture, or None."""
        for g in self.gestures:
            if g.is_active:
                return g
        return None

    def evaluate(
        self,
        physical_state: list[list[int]],
        game_status: str,
        now: float | None = None,
    ) -> list[str]:
        """
        Evaluates registered gestures. Gestures only operate during IDLE or GAME_OVER.
        Returns list of completed gesture names.
        """
        if now is None:
            now = time.time()

        if game_status not in ["IDLE", "GAME_OVER"]:
            self.reset()
            return []

        completed: list[str] = []
        for gesture in self.gestures:
            if gesture.evaluate(physical_state, now):
                completed.append(gesture.name)
                gesture.execute_completion()

        return completed

    def get_starter_indicators(self, now: float | None = None) -> dict[tuple[int, int], int]:
        """
        Aggregates subtle ambient breathing glows on all gesture starter pieces (e.g. a2, e2, h2 pawns)
        when the board is fully set up in starting configuration.
        """
        if now is None:
            now = time.time()
        indicators: dict[tuple[int, int], int] = {}
        # Gentle 0.5 Hz breathing glow
        pulse = 0.25 + 0.35 * (0.5 * (1.0 + math.sin(now * 3.0)))
        for gesture in self.gestures:
            if gesture.starter_coord is not None and gesture.starter_color is not None:
                indicators[gesture.starter_coord] = scale_color(gesture.starter_color, pulse)
        return indicators

    def get_led_overlay(self, now: float | None = None) -> dict[tuple[int, int], int]:
        """Aggregates active LED overlays across all registered gestures."""
        if now is None:
            now = time.time()
        overlay: dict[tuple[int, int], int] = {}
        for gesture in self.gestures:
            if gesture.is_active:
                overlay.update(gesture.get_led_overlay(now))
        return overlay

    def reset(self) -> None:
        """Resets all registered gestures."""
        for gesture in self.gestures:
            gesture.reset()

    def get_state_payload(self, now: float | None = None) -> dict[str, Any]:
        """Returns serialized gesture payload for WebSocket broadcasting."""
        if now is None:
            now = time.time()
        act = self.active_gesture
        return {
            "is_active": self.is_active,
            "active_gesture": act.name if act else None,
            "step": act.step if act else 0,
            "hint": act.hint if act else None,
            "time_remaining": round(act.time_remaining(now), 1) if act else 0.0,
            "gestures": [g.to_dict(now) for g in self.gestures],
        }
