"""
app/gesture_engine.py

Extensible Physical Board Gesture Engine for the Smart Chess Board.
Provides base gesture abstractions, physical matrix evaluation during IDLE / GAME_OVER states,
LED overlay generation, and concrete physical gesture implementations such as the
"Kingside Corner Gate" (lift h2 -> lift h1 -> replace both) to restart the previous match.
"""

from abc import ABC, abstractmethod
import asyncio
import logging
import math
import time
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from app.config import (
        ANIM_MOVE_CONFIRM_DURATION_S,
        BOARD_COLS,
        BOARD_ROWS,
        COLOR_PIECE_LIFTED,
    )
    from app.led_animations import scale_color
    from app.led_helpers import (
        COLOR_INT_DAY_INDICATOR,
        COLOR_INT_NIGHT_INDICATOR,
        COLOR_INT_PIECE_LIFTED,
        Color,
    )
except ImportError:
    from .config import (
        ANIM_MOVE_CONFIRM_DURATION_S,
        BOARD_COLS,
        BOARD_ROWS,
        COLOR_PIECE_LIFTED,
    )
    from .led_animations import scale_color
    from .led_helpers import (
        COLOR_INT_DAY_INDICATOR,
        COLOR_INT_NIGHT_INDICATOR,
        COLOR_INT_PIECE_LIFTED,
        Color,
    )

logger = logging.getLogger("smart-chess-app.gesture")

# Dedicated Gesture LED Colors
COLOR_INT_AZURE = Color(0, 160, 255)      # Cool azure pulse for next step guidance
COLOR_INT_EMERALD = Color(0, 220, 90)     # Radiant emerald pulse for completion gate
COLOR_INT_ROYAL_VIOLET = Color(140, 40, 240)  # Royal violet for analysis mode
COLOR_INT_MINT_EMERALD = Color(0, 220, 140)  # Mint emerald for analysis step guidance


class BaseGesture(ABC):
    """
    Abstract Base Class for physical chessboard gestures.
    Subclasses evaluate the 8x8 sensor matrix and manage their step sequence and LED highlights.
    """

    starter_coord: Optional[Tuple[int, int]] = None
    starter_color: Optional[int] = None

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
    def hint(self) -> Optional[str]:
        """Provides a human-readable guidance hint for the active gesture step."""
        pass

    def time_remaining(self, now: float) -> float:
        """Returns remaining seconds before the active gesture times out."""
        if not self.is_active or self.start_time <= 0:
            return 0.0
        return max(0.0, self.timeout - (now - self.start_time))

    @abstractmethod
    def evaluate(self, physical_state: List[List[int]], now: float) -> bool:
        """
        Evaluates physical board sensor states.
        Returns True when the gesture successfully completes.
        """
        pass

    @abstractmethod
    def get_led_overlay(self, now: float) -> Dict[Tuple[int, int], int]:
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

    def to_dict(self, now: Optional[float] = None) -> Dict[str, Any]:
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


class RestartPreviousGameGesture(BaseGesture):
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

    H1_COORD: Tuple[int, int] = (7, 0)  # File h (c=7), Rank 1 (r=0)
    H2_COORD: Tuple[int, int] = (7, 1)  # File h (c=7), Rank 2 (r=1)
    starter_coord: Tuple[int, int] = (7, 1)
    starter_color: int = Color(240, 160, 20)  # Warm Amber

    def __init__(self, state_manager: Any = None, timeout: float = 5.0):
        super().__init__(
            name="restart_previous_game",
            description="Kingside Corner Gate: lift h2 -> lift h1 -> replace both to restart last game",
            timeout=timeout,
        )
        self.state_manager = state_manager

    @property
    def hint(self) -> Optional[str]:
        if self.step == 1:
            return "Lift h1 (Rook) to complete corner gate"
        elif self.step == 2:
            return "Replace h1 and h2 to restart previous game"
        return None

    def _get_board_anomalies(
        self, physical_state: List[List[int]]
    ) -> Tuple[Set[Tuple[int, int]], Set[Tuple[int, int]]]:
        """
        Returns (lifted_starting_squares, extra_occupied_center_squares).
        Starting squares: Ranks 0, 1 (White), Ranks 6, 7 (Black).
        Center squares: Ranks 2..5 (expected empty).
        """
        lifted_starting: Set[Tuple[int, int]] = set()
        extra_occupied: Set[Tuple[int, int]] = set()

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

    def evaluate(self, physical_state: List[List[int]], now: float) -> bool:
        lifted_starting, extra_occupied = self._get_board_anomalies(physical_state)

        # Center squares bumped with pieces immediately cancels gesture
        if len(extra_occupied) > 0:
            if self.is_active:
                logger.debug(f"Restart gesture cancelled due to center pieces: {extra_occupied}")
            self.reset()
            return False

        # Step 0: Idle / Armed
        if self.step == 0:
            # Gesture begins when ONLY h2 (7, 1) is lifted and h1 (7, 0) is placed
            if lifted_starting == {self.H2_COORD}:
                self.step = 1
                self.start_time = now
                logger.info("Restart gesture armed: Step 1 (h2 lifted). Waiting for h1...")
            return False

        # Timeout Check for active gesture (Steps 1 & 2)
        if now - self.start_time > self.timeout:
            logger.info("Restart gesture timed out. Resetting.")
            self.reset()
            return False

        # Step 1: h2 lifted, waiting for h1 lift
        if self.step == 1:
            # Premature replacement of h2 before lifting h1 cancels gesture
            if self.H2_COORD not in lifted_starting:
                logger.debug("Restart gesture cancelled: h2 replaced prematurely without lifting h1.")
                self.reset()
                return False

            # Bumping extra starting pieces outside of h2 cancels gesture
            if not lifted_starting.issubset({self.H2_COORD, self.H1_COORD}):
                logger.debug(f"Restart gesture cancelled: unexpected piece lifted {lifted_starting - {self.H2_COORD}}")
                self.reset()
                return False

            # h1 is lifted while h2 is also lifted -> advance to Step 2
            if lifted_starting == {self.H2_COORD, self.H1_COORD}:
                self.step = 2
                logger.info("Restart gesture: Step 2 (h1 & h2 both lifted). Ready for replacement.")
            return False

        # Step 2: Both h1 & h2 lifted, waiting for replacement
        if self.step == 2:
            # Bumping extra starting pieces outside of {h1, h2} cancels gesture
            if not lifted_starting.issubset({self.H2_COORD, self.H1_COORD}):
                logger.debug(f"Restart gesture cancelled in Step 2: extra pieces lifted {lifted_starting}")
                self.reset()
                return False

            # Completion condition: Both h1 & h2 replaced, and full starting position intact
            if len(lifted_starting) == 0:
                logger.info("Restart gesture COMPLETED: Kingside Corner Gate closed! Restarting game...")
                self.reset()
                return True

            return False

        return False

    def get_led_overlay(self, now: float) -> Dict[Tuple[int, int], int]:
        overlay: Dict[Tuple[int, int], int] = {}
        if self.step == 1:
            # h2: Solid Amber
            overlay[self.H2_COORD] = COLOR_INT_PIECE_LIFTED
            # h1: Azure Breathing Pulse
            pulse = math.sin(now * 8.0) * 0.5 + 0.5
            intensity = 0.25 + 0.75 * pulse
            overlay[self.H1_COORD] = scale_color(COLOR_INT_AZURE, intensity)
        elif self.step == 2:
            # Both h1 & h2: Rapid Emerald Pulse
            pulse = math.sin(now * 10.0) * 0.5 + 0.5
            intensity = 0.35 + 0.65 * pulse
            emerald_scaled = scale_color(COLOR_INT_EMERALD, intensity)
            overlay[self.H1_COORD] = emerald_scaled
            overlay[self.H2_COORD] = emerald_scaled
        return overlay

    def execute_completion(self) -> None:
        """Triggers arrival confirmation flash and launches previous game matchmaking."""
        if self.state_manager:
            # Visual confirmation flash on h1 & h2
            self.state_manager.trigger_arrival_flash(
                self.H1_COORD[0],
                self.H1_COORD[1],
                duration=0.6,
                extra_squares=[self.H2_COORD],
            )

        async def _dispatch_restart():
            try:
                from app.lichess_engine import lichess_engine
                from board_hardware import settings

                params = settings.get("last_game_params") or {}
                tc = params.get("time_control", "10+0")
                rated = bool(params.get("rated", False))
                color = params.get("color", "random")
                opponent = params.get("opponent", "auto")
                ai_level = params.get("ai_level", 3)
                rating_range = params.get("rating_range", None)

                logger.info(
                    f"Restarting game via gesture with params: tc={tc}, rated={rated}, "
                    f"color={color}, opponent={opponent}, ai_level={ai_level}, range={rating_range}"
                )
                await lichess_engine.seek(
                    self.state_manager,
                    time_control=tc,
                    rated=rated,
                    color=color,
                    opponent=opponent,
                    ai_level=ai_level,
                    rating_range=rating_range,
                )
            except Exception as e:
                logger.error(f"Error dispatching restart game seek in gesture: {e}")

        asyncio.create_task(_dispatch_restart())


class ToggleNightModeGesture(BaseGesture):
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

    A1_COORD: Tuple[int, int] = (0, 0)  # File a (c=0), Rank 1 (r=0)
    A2_COORD: Tuple[int, int] = (0, 1)  # File a (c=0), Rank 2 (r=1)
    starter_coord: Tuple[int, int] = (0, 1)
    starter_color: int = Color(0, 140, 255)  # Moonlight Azure

    def __init__(self, state_manager: Any = None, timeout: float = 5.0):
        super().__init__(
            name="toggle_night_mode",
            description="Queenside Corner Gate: lift a2 -> lift a1 -> replace both to toggle Night/Day mode",
            timeout=timeout,
        )
        self.state_manager = state_manager

    @property
    def hint(self) -> Optional[str]:
        try:
            from board_hardware import settings
            is_night = bool(settings.get("night_mode", False))
        except Exception:
            is_night = False
        target_name = "Day Mode" if is_night else "Night Mode"
        if self.step == 1:
            return f"Lift a1 (Rook) to toggle to {target_name}"
        elif self.step == 2:
            return f"Replace a1 and a2 to activate {target_name}"
        return None

    def _get_board_anomalies(
        self, physical_state: List[List[int]]
    ) -> Tuple[Set[Tuple[int, int]], Set[Tuple[int, int]]]:
        lifted_starting: Set[Tuple[int, int]] = set()
        extra_occupied: Set[Tuple[int, int]] = set()

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

    def evaluate(self, physical_state: List[List[int]], now: float) -> bool:
        lifted_starting, extra_occupied = self._get_board_anomalies(physical_state)

        # Center squares bumped with pieces immediately cancels gesture
        if len(extra_occupied) > 0:
            if self.is_active:
                logger.debug(f"Night mode gesture cancelled due to center pieces: {extra_occupied}")
            self.reset()
            return False

        # Step 0: Idle / Armed
        if self.step == 0:
            # Gesture begins when ONLY a2 (0, 1) is lifted and a1 (0, 0) is placed
            if lifted_starting == {self.A2_COORD}:
                self.step = 1
                self.start_time = now
                logger.info("Night mode gesture armed: Step 1 (a2 lifted). Waiting for a1...")
            return False

        # Timeout Check for active gesture (Steps 1 & 2)
        if now - self.start_time > self.timeout:
            logger.info("Night mode gesture timed out. Resetting.")
            self.reset()
            return False

        # Step 1: a2 lifted, waiting for a1 lift
        if self.step == 1:
            # Premature replacement of a2 before lifting a1 cancels gesture
            if self.A2_COORD not in lifted_starting:
                logger.debug("Night mode gesture cancelled: a2 replaced prematurely without lifting a1.")
                self.reset()
                return False

            # Bumping extra starting pieces outside of a2 cancels gesture
            if not lifted_starting.issubset({self.A2_COORD, self.A1_COORD}):
                logger.debug(f"Night mode gesture cancelled: unexpected piece lifted {lifted_starting - {self.A2_COORD}}")
                self.reset()
                return False

            # a1 is lifted while a2 is also lifted -> advance to Step 2
            if lifted_starting == {self.A2_COORD, self.A1_COORD}:
                self.step = 2
                logger.info("Night mode gesture: Step 2 (a1 & a2 both lifted). Ready for replacement.")
            return False

        # Step 2: Both a1 & a2 lifted, waiting for replacement
        if self.step == 2:
            # Bumping extra starting pieces outside of {a1, a2} cancels gesture
            if not lifted_starting.issubset({self.A2_COORD, self.A1_COORD}):
                logger.debug(f"Night mode gesture cancelled in Step 2: extra pieces lifted {lifted_starting}")
                self.reset()
                return False

            # Completion condition: Both a1 & a2 replaced, and full starting position intact
            if len(lifted_starting) == 0:
                logger.info("Night mode gesture COMPLETED: Queenside Corner Gate closed! Toggling Night Mode...")
                self.reset()
                return True

            return False

        return False

    def get_led_overlay(self, now: float) -> Dict[Tuple[int, int], int]:
        overlay: Dict[Tuple[int, int], int] = {}
        try:
            from board_hardware import settings
            is_night = bool(settings.get("night_mode", False))
        except Exception:
            is_night = False

        # Current mode indicator color: Dark Blue for Night Mode, Solar Gold for Day Mode
        curr_color = COLOR_INT_NIGHT_INDICATOR if is_night else COLOR_INT_DAY_INDICATOR
        # Target mode color: the opposite of current mode
        target_color = COLOR_INT_DAY_INDICATOR if is_night else COLOR_INT_NIGHT_INDICATOR

        if self.step == 1:
            # a2: Solid color reflecting current board mode (Dark Blue if Night, Gold if Day)
            overlay[self.A2_COORD] = curr_color
            # a1: Breathing pulse in current mode color guiding next piece lift
            pulse = math.sin(now * 8.0) * 0.5 + 0.5
            intensity = 0.25 + 0.75 * pulse
            overlay[self.A1_COORD] = scale_color(curr_color, intensity)
        elif self.step == 2:
            # Both a1 & a2: Rapid pulse in the TARGET mode's color
            pulse = math.sin(now * 10.0) * 0.5 + 0.5
            intensity = 0.35 + 0.65 * pulse
            scaled_target = scale_color(target_color, intensity)
            overlay[self.A1_COORD] = scaled_target
            overlay[self.A2_COORD] = scaled_target
        return overlay

    def execute_completion(self) -> None:
        """Toggles night_mode in settings, saves, and triggers arrival flash in new mode color."""
        try:
            from board_hardware import settings, save_settings
            new_night_mode = not bool(settings.get("night_mode", False))
            settings["night_mode"] = new_night_mode
            save_settings()
            logger.info(f"Physical gesture successfully toggled night_mode to: {new_night_mode}")
        except Exception as e:
            logger.error(f"Error toggling night_mode in gesture: {e}")
            new_night_mode = True

        if self.state_manager:
            self.state_manager.trigger_arrival_flash(
                self.A1_COORD[0],
                self.A1_COORD[1],
                duration=0.6,
                extra_squares=[self.A2_COORD],
            )


class CenterRoyalGateGesture(BaseGesture):
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

    E2_COORD: Tuple[int, int] = (4, 1)  # File e (c=4), Rank 2 (r=1)
    D2_COORD: Tuple[int, int] = (3, 1)  # File d (c=3), Rank 2 (r=1)
    starter_coord: Tuple[int, int] = (4, 1)
    starter_color: int = COLOR_INT_ROYAL_VIOLET

    def __init__(self, state_manager: Any = None, timeout: float = 5.0):
        super().__init__(
            name="start_analysis",
            description="Center Royal Gate: lift e2 -> lift d2 -> replace both to activate Post-Game Analysis",
            timeout=timeout,
        )
        self.state_manager = state_manager

    @property
    def hint(self) -> Optional[str]:
        if self.step == 1:
            return "Lift d2 (Queen Pawn) to arm Analysis Mode"
        elif self.step == 2:
            return "Replace e2 and d2 to activate Post-Game Analysis"
        return None

    def _get_board_anomalies(
        self, physical_state: List[List[int]]
    ) -> Tuple[Set[Tuple[int, int]], Set[Tuple[int, int]]]:
        lifted_starting: Set[Tuple[int, int]] = set()
        extra_occupied: Set[Tuple[int, int]] = set()

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

    def evaluate(self, physical_state: List[List[int]], now: float) -> bool:
        lifted_starting, extra_occupied = self._get_board_anomalies(physical_state)

        # Center squares bumped with pieces immediately cancels gesture
        if len(extra_occupied) > 0:
            if self.is_active:
                logger.debug(f"Analysis gesture cancelled due to center pieces: {extra_occupied}")
            self.reset()
            return False

        # Step 0: Idle / Armed
        if self.step == 0:
            # Begins when ONLY e2 (4, 1) is lifted and d2 (3, 1) is placed
            if lifted_starting == {self.E2_COORD}:
                self.step = 1
                self.start_time = now
                logger.info("Analysis gesture armed: Step 1 (e2 lifted). Waiting for d2...")
            return False

        # Timeout Check for active gesture (Steps 1 & 2)
        if now - self.start_time > self.timeout:
            logger.info("Analysis gesture timed out. Resetting.")
            self.reset()
            return False

        # Step 1: e2 lifted, waiting for d2 lift
        if self.step == 1:
            # Premature replacement of e2 without lifting d2 cancels gesture
            if self.E2_COORD not in lifted_starting:
                logger.debug("Analysis gesture cancelled: e2 replaced prematurely without lifting d2.")
                self.reset()
                return False

            # Extra starting pieces lifted cancels gesture
            if not lifted_starting.issubset({self.E2_COORD, self.D2_COORD}):
                logger.debug(f"Analysis gesture cancelled: unexpected piece lifted {lifted_starting - {self.E2_COORD}}")
                self.reset()
                return False

            # d2 lifted while e2 is lifted -> advance to Step 2
            if lifted_starting == {self.E2_COORD, self.D2_COORD}:
                self.step = 2
                logger.info("Analysis gesture: Step 2 (e2 & d2 both lifted). Ready for replacement.")
            return False

        # Step 2: Both e2 & d2 lifted, waiting for replacement
        if self.step == 2:
            # Extra starting pieces lifted cancels gesture
            if not lifted_starting.issubset({self.E2_COORD, self.D2_COORD}):
                logger.debug(f"Analysis gesture cancelled in Step 2: extra pieces lifted {lifted_starting}")
                self.reset()
                return False

            # Completion condition: Both e2 & d2 replaced, full starting position intact
            if len(lifted_starting) == 0:
                logger.info("Analysis gesture COMPLETED: Center Royal Gate closed! Activating Analysis Mode...")
                self.reset()
                return True

            return False

        return False

    def get_led_overlay(self, now: float) -> Dict[Tuple[int, int], int]:
        overlay: Dict[Tuple[int, int], int] = {}
        if self.step == 1:
            # e2: Solid Royal Violet
            overlay[self.E2_COORD] = COLOR_INT_ROYAL_VIOLET
            # d2: Pulsing Mint Emerald guiding next piece lift
            pulse = math.sin(now * 8.0) * 0.5 + 0.5
            intensity = 0.25 + 0.75 * pulse
            overlay[self.D2_COORD] = scale_color(COLOR_INT_MINT_EMERALD, intensity)
        elif self.step == 2:
            # Both e2 & d2: Rapid synchronized pulse in dual Emerald/Violet
            pulse = math.sin(now * 10.0) * 0.5 + 0.5
            intensity = 0.35 + 0.65 * pulse
            overlay[self.E2_COORD] = scale_color(COLOR_INT_ROYAL_VIOLET, intensity)
            overlay[self.D2_COORD] = scale_color(COLOR_INT_MINT_EMERALD, intensity)
        return overlay

    def execute_completion(self) -> None:
        """Triggers arrival confirmation flare on d2/e2 and activates analysis mode."""
        if self.state_manager:
            self.state_manager.trigger_arrival_flash(
                self.E2_COORD[0],
                self.E2_COORD[1],
                duration=0.6,
                extra_squares=[self.D2_COORD],
            )
            # Dispatch async start_analysis_mode
            asyncio.create_task(self.state_manager.start_analysis_mode())


class PhysicalGestureEngine:
    """
    Subsystem manager for physical board gestures.
    Monitors board states during IDLE / GAME_OVER, generates LED overlay frames,
    and coordinates async gesture executions.
    """

    def __init__(self, state_manager: Any = None):
        self.state_manager = state_manager
        self.gestures: List[BaseGesture] = []
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
    def active_gesture(self) -> Optional[BaseGesture]:
        """Returns the currently active gesture, or None."""
        for g in self.gestures:
            if g.is_active:
                return g
        return None

    def evaluate(
        self,
        physical_state: List[List[int]],
        game_status: str,
        now: Optional[float] = None,
    ) -> List[str]:
        """
        Evaluates registered gestures. Gestures only operate during IDLE or GAME_OVER.
        Returns list of completed gesture names.
        """
        if now is None:
            now = time.time()

        if game_status not in ["IDLE", "GAME_OVER"]:
            self.reset()
            return []

        completed: List[str] = []
        for gesture in self.gestures:
            if gesture.evaluate(physical_state, now):
                completed.append(gesture.name)
                gesture.execute_completion()

        return completed

    def get_starter_indicators(self, now: Optional[float] = None) -> Dict[Tuple[int, int], int]:
        """
        Aggregates subtle ambient breathing glows on all gesture starter pieces (e.g. a2, e2, h2 pawns)
        when the board is fully set up in starting configuration.
        """
        if now is None:
            now = time.time()
        indicators: Dict[Tuple[int, int], int] = {}
        # Gentle 0.5 Hz breathing glow
        pulse = 0.25 + 0.35 * (0.5 * (1.0 + math.sin(now * 3.0)))
        for gesture in self.gestures:
            if gesture.starter_coord and gesture.starter_color:
                indicators[gesture.starter_coord] = scale_color(gesture.starter_color, pulse)
        return indicators

    def get_led_overlay(self, now: Optional[float] = None) -> Dict[Tuple[int, int], int]:
        """Aggregates active LED overlays across all registered gestures."""
        if now is None:
            now = time.time()
        overlay: Dict[Tuple[int, int], int] = {}
        for gesture in self.gestures:
            if gesture.is_active:
                overlay.update(gesture.get_led_overlay(now))
        return overlay

    def reset(self) -> None:
        """Resets all registered gestures."""
        for gesture in self.gestures:
            gesture.reset()

    def get_state_payload(self, now: Optional[float] = None) -> Dict[str, Any]:
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
