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
        COLOR_INT_PIECE_LIFTED,
        Color,
    )

logger = logging.getLogger("smart-chess-app.gesture")

# Dedicated Gesture LED Colors
COLOR_INT_AZURE = Color(0, 160, 255)      # Cool azure pulse for next step guidance
COLOR_INT_EMERALD = Color(0, 220, 90)     # Radiant emerald pulse for completion gate


class BaseGesture(ABC):
    """
    Abstract Base Class for physical chessboard gestures.
    Subclasses evaluate the 8x8 sensor matrix and manage their step sequence and LED highlights.
    """

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
