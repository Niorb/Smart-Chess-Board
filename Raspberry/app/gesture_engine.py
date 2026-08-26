"""
app/gesture_engine.py

Extensible Physical Board Gesture Engine for the Smart Chess Board.
Provides base gesture abstractions, physical matrix evaluation during IDLE / GAME_OVER states,
LED overlay generation, and concrete physical gesture implementations such as the
"Replay Last Game" selection menu (lift h2 -> pick King/Bishop/Knight/Rook options -> replace h2).
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
    from app.led_animations import get_piece_type_color, scale_color
    from app.led_helpers import (
        COLOR_INT_AZURE,
        COLOR_INT_DAY_INDICATOR,
        COLOR_INT_MINT_EMERALD,
        COLOR_INT_NIGHT_INDICATOR,
        COLOR_INT_PIECE_BISHOP,
        COLOR_INT_PIECE_KING,
        COLOR_INT_PIECE_KNIGHT,
        COLOR_INT_PIECE_LIFTED,
        COLOR_INT_PIECE_PAWN,
        COLOR_INT_PIECE_QUEEN,
        COLOR_INT_PIECE_ROOK,
        COLOR_INT_ROYAL_VIOLET,
        Color,
    )
except ImportError:
    from .config import (
        BOARD_COLS,
        BOARD_ROWS,
    )
    from .led_animations import get_piece_type_color, scale_color
    from .led_helpers import (
        COLOR_INT_AZURE,
        COLOR_INT_DAY_INDICATOR,
        COLOR_INT_MINT_EMERALD,
        COLOR_INT_NIGHT_INDICATOR,
        COLOR_INT_PIECE_BISHOP,
        COLOR_INT_PIECE_KING,
        COLOR_INT_PIECE_KNIGHT,
        COLOR_INT_PIECE_LIFTED,
        COLOR_INT_PIECE_PAWN,
        COLOR_INT_PIECE_QUEEN,
        COLOR_INT_PIECE_ROOK,
        COLOR_INT_ROYAL_VIOLET,
        Color,
    )

logger = logging.getLogger("smart-chess-app.gesture")

# Dedicated Gesture LED Colors (unique to gestures; shared palettes come from led_helpers)
COLOR_INT_EMERALD = Color(0, 220, 90)     # Radiant emerald pulse for completion gate
COLOR_INT_MEMORY_GOLD = Color(255, 190, 40)  # Warm radiant gold for Memory Replay gate

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

    def __init__(
        self,
        name: str,
        description: str,
        timeout: float = 5.0,
        state_manager: Any = None,
    ):
        self.name = name
        self.description = description
        self.timeout = timeout
        self.state_manager = state_manager
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
    def evaluate(
        self,
        physical_state: list[list[int]],
        now: float,
        is_armed: bool = True,
    ) -> bool:
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
        super().__init__(name=name, description=description, timeout=timeout, state_manager=state_manager)

    def _overlay_palette(self, now: float) -> tuple[int, int, int, int]:
        """Returns (lifted_solid, next_pulse, completion_first, completion_second) colors."""
        return (
            COLOR_INT_PIECE_LIFTED,
            COLOR_INT_AZURE,
            COLOR_INT_EMERALD,
            COLOR_INT_EMERALD,
        )

    def evaluate(
        self,
        physical_state: list[list[int]],
        now: float,
        is_armed: bool = True,
    ) -> bool:
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
            if not is_armed:
                return False
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


class RestartPreviousGameGesture(BaseGesture):
    """
    "Replay Last Game" selection-menu gesture:
      - Initial setup: Full standard chess starting position.
      - Step 1: Lift h2 pawn (column 7, row 1).
                LEDs: Amber on h2 + four option squares lit on White's kingside back rank:
                  - e1 King   -> 15+10 time control
                  - f1 Bishop -> 10+0 time control
                  - g1 Knight -> 3+2 time control
                  (all three share the same Cyan Azure; the currently selected
                   time control glows in Royal Violet with a breathing pulse)
                  - h1 Rook   (Magenta=AI / Gold=Human) -> toggles AI vs Human opponent
      - Step 2: Lift an option piece:
                  - Time-control pieces register their choice when placed back down
                    (confirmed with an arrival flash on that square).
                  - Lifting the Rook instantly toggles AI/Human (LED color flips while held);
                    placing it back confirms with a flash.
                Multiple selections may be made while h2 stays lifted. Each interaction
                refreshes the inactivity timer.
      - Step 3 (Completion): Replace the h2 pawn to start the search with the chosen settings.
      - Cancellations: lifting any unrelated starting piece, holding two option pieces,
        dropping h2 while an option is still in hand, center-square occupation,
        or inactivity timeout. After any cancellation, all lifted pieces must be
        replaced before the gesture can re-arm.
      - Defaults: seeded from the persisted last_game_params at menu open.
    """

    H2_COORD: tuple[int, int] = (7, 1)  # File h (c=7), Rank 2 (r=1)
    KING_COORD: tuple[int, int] = (4, 0)  # e1 -> 15+10
    BISHOP_COORD: tuple[int, int] = (5, 0)  # f1 -> 10+0
    KNIGHT_COORD: tuple[int, int] = (6, 0)  # g1 -> 3+2
    ROOK_COORD: tuple[int, int] = (7, 0)  # h1 -> AI/Human toggle
    starter_coord: tuple[int, int] = H2_COORD
    starter_color: int = Color(240, 160, 20)  # Warm Amber

    TC_SELECTIONS: dict[tuple[int, int], str] = {
        KING_COORD: "15+10",
        BISHOP_COORD: "10+0",
        KNIGHT_COORD: "3+2",
    }

    COLOR_INT_TC_OPTION = COLOR_INT_AZURE          # Shared hue for all time-control options
    COLOR_INT_TC_SELECTED = COLOR_INT_ROYAL_VIOLET  # Distinct hue for the active selection
    COLOR_INT_AI_MODE = Color(255, 40, 180)  # Hot Magenta - Stockfish AI opponent selected
    COLOR_INT_HUMAN_MODE = Color(255, 200, 0)  # Golden Amber - Human opponent selected

    def __init__(self, state_manager: Any = None, timeout: float = 30.0):
        super().__init__(
            name="restart_previous_game",
            description="Replay menu: lift h2 -> pick K/B/N time control or toggle Rook AI/Human -> replace h2 to start",
            state_manager=state_manager,
            timeout=timeout,
        )
        self.selected_tc: str | None = None
        self.opponent_mode: str | None = None  # "ai" | "human"
        self._held_option: tuple[int, int] | None = None
        self._holdoff: bool = False
        self.log_prefix = "Restart gesture"

    @property
    def hint(self) -> str | None:
        if self.step != 1:
            return None
        mode_name = "AI" if self.opponent_mode == "ai" else "Human"
        return (
            f"Lift King=15+10 · Bishop=10+0 · Knight=3+2 · Rook toggles AI/Human "
            f"(now: {mode_name}) — replace h2 to start search ({self.selected_tc} vs {mode_name})"
        )

    def reset(self) -> None:
        super().reset()
        self._held_option = None

    def _soft_cancel(self, reason: str) -> None:
        """Cancels the active menu and waits for a full board reset before re-arming."""
        logger.debug(f"{self.log_prefix} cancelled: {reason}")
        self.reset()
        self._holdoff = True

    def _sync_defaults(self) -> None:
        """Seeds selection defaults from the persisted last-game matchmaking params."""
        try:
            from board_hardware import get_last_game_params

            params = get_last_game_params()
        except Exception:
            params = {}
        tc = params.get("time_control") or "10+0"
        self.selected_tc = tc if tc in set(self.TC_SELECTIONS.values()) else "10+0"
        self.opponent_mode = "human" if params.get("opponent") == "human" else "ai"

    def _confirm_selection(self, coord: tuple[int, int]) -> None:
        """Arrival-flash confirmation for a placed-back option piece."""
        logger.info(
            f"{self.log_prefix} selection confirmed: tc={self.selected_tc}, "
            f"opponent={self.opponent_mode} (square {coord})"
        )
        if self.state_manager:
            self.state_manager.trigger_arrival_flash(coord[0], coord[1], duration=0.6)

    def evaluate(
        self,
        physical_state: list[list[int]],
        now: float,
        is_armed: bool = True,
    ) -> bool:
        lifted_starting, extra_occupied = self._get_board_anomalies(physical_state)

        # Center squares bumped with pieces immediately cancels the menu
        if len(extra_occupied) > 0:
            if self.is_active:
                self._soft_cancel(f"center pieces occupied: {extra_occupied}")
            return False

        # Holdoff: after any cancellation/timeout wait until every piece is replaced
        if self._holdoff:
            if not lifted_starting:
                self._holdoff = False
            return False

        # Step 0 -> 1: arm the menu when ONLY the h2 pawn is lifted AND board was armed
        if not self.is_active:
            if not is_armed:
                return False
            if lifted_starting == {self.H2_COORD}:
                self.step = 1
                self.start_time = now
                self._held_option = None
                self._sync_defaults()
                logger.info(
                    f"{self.log_prefix}: replay menu opened (defaults: tc={self.selected_tc}, "
                    f"opponent={self.opponent_mode})"
                )
            return False

        # Menu open: inactivity timeout closes it
        if now - self.start_time > self.timeout:
            logger.info(f"{self.log_prefix} menu timed out after {self.timeout}s of inactivity.")
            had_lifts = bool(lifted_starting)
            self.reset()
            self._holdoff = had_lifts
            return False

        option_squares = set(self.TC_SELECTIONS) | {self.ROOK_COORD}
        allowed = {self.H2_COORD} | option_squares

        # Bumping any unrelated starting piece cancels the menu
        if not lifted_starting.issubset(allowed):
            self._soft_cancel(f"unexpected piece(s) lifted: {lifted_starting - allowed}")
            return False

        # h2 pawn replaced -> completion (only valid with no option piece still in hand)
        if self.H2_COORD not in lifted_starting:
            if lifted_starting & option_squares:
                self._soft_cancel("h2 replaced while an option piece was still in hand")
                return False
            logger.info(f"{self.log_prefix} COMPLETED: launching search (tc={self.selected_tc}, opponent={self.opponent_mode})")
            self.reset()
            return True

        held = lifted_starting & option_squares
        if len(held) > 1:
            self._soft_cancel("multiple option pieces lifted simultaneously")
            return False

        if not held:
            # An option piece was just placed back -> confirm its registration
            if self._held_option is not None:
                confirmed = self._held_option
                self._held_option = None
                self.start_time = now  # refresh inactivity timer
                self._confirm_selection(confirmed)
            return False

        coord = next(iter(held))
        if coord != self._held_option:
            self._held_option = coord
            self.start_time = now  # refresh inactivity timer
            if coord == self.ROOK_COORD:
                self.opponent_mode = "human" if self.opponent_mode == "ai" else "ai"
                logger.info(f"{self.log_prefix}: rook toggled opponent mode -> {self.opponent_mode}")
            else:
                self.selected_tc = self.TC_SELECTIONS[coord]
                logger.info(f"{self.log_prefix}: {coord} selected time control -> {self.selected_tc}")
        return False

    def get_led_overlay(self, now: float) -> dict[tuple[int, int], int]:
        overlay: dict[tuple[int, int], int] = {}
        if self.step != 1:
            return overlay

        # h2 anchor: solid warm amber
        overlay[self.H2_COORD] = self.starter_color

        pulse = math.sin(now * 6.0) * 0.5 + 0.5

        def _option_color(coord: tuple[int, int]) -> int:
            if coord == self.ROOK_COORD:
                return self.COLOR_INT_AI_MODE if self.opponent_mode == "ai" else self.COLOR_INT_HUMAN_MODE
            # All time-control options share one hue; the active selection stands out
            if self.TC_SELECTIONS.get(coord) == self.selected_tc:
                return self.COLOR_INT_TC_SELECTED
            return self.COLOR_INT_TC_OPTION

        options = [*self.TC_SELECTIONS, self.ROOK_COORD]
        for coord in options:
            color = _option_color(coord)
            if self._held_option == coord:
                # Piece currently in hand: solid full brightness
                overlay[coord] = color
            elif coord == self.ROOK_COORD or self.TC_SELECTIONS.get(coord) == self.selected_tc:
                # Actionable toggle / current selection: bright breathing pulse
                overlay[coord] = scale_color(color, 0.45 + 0.55 * pulse)
            else:
                # Non-selected alternatives: dim steady
                overlay[coord] = scale_color(color, 0.38)
        return overlay

    def to_dict(self, now: float | None = None) -> dict[str, Any]:
        data = super().to_dict(now)
        if self.is_active:
            data["selection"] = {
                "time_control": self.selected_tc,
                "opponent": self.opponent_mode,
            }
        return data

    def execute_completion(self) -> None:
        """Flashes the chosen squares and launches matchmaking with the selected settings."""
        extra_squares: list[tuple[int, int]] = []
        inverse_tc = {tc: coord for coord, tc in self.TC_SELECTIONS.items()}
        if self.selected_tc in inverse_tc:
            extra_squares.append(inverse_tc[self.selected_tc])
        if self.state_manager:
            self.state_manager.trigger_arrival_flash(
                self.H2_COORD[0],
                self.H2_COORD[1],
                duration=0.6,
                extra_squares=extra_squares,
            )

        async def _dispatch_restart():
            try:
                from board_hardware import get_last_game_params

                from app.lichess_engine import lichess_engine

                params = get_last_game_params()
                tc = self.selected_tc or params["time_control"]
                opponent = self.opponent_mode or params.get("opponent", "auto")
                logger.info(
                    f"Restarting game via gesture with params: tc={tc}, rated={params['rated']}, "
                    f"color={params['color']}, opponent={opponent}, ai_level={params['ai_level']}, "
                    f"range={params['rating_range']}"
                )
                await lichess_engine.seek(
                    self.state_manager,
                    time_control=tc,
                    rated=params["rated"],
                    color=params["color"],
                    opponent=opponent,
                    ai_level=params["ai_level"],
                    rating_range=params["rating_range"],
                )
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


class MemoryReplayGateGesture(CornerGateGesture):
    """
    Memory Replay Gate gesture (mirror of the Analysis gate, disambiguated by lift order):
      - Initial setup: Full standard chess starting position.
      - Step 1: Lift d2 pawn (column 3, row 1) FIRST.
                LEDs: Solid Radiant Gold on d2, pulsing Mint Emerald on e2.
      - Step 2: Lift e2 pawn (column 4, row 1) while d2 remains lifted.
                LEDs: Dual synchronous Gold/Emerald rapid pulse on d2 and e2.
      - Step 3 (Completion): Replace both d2 and e2 pawns back into starting setup.
      - Result: Starts a memory recall session replaying the last played game from
                memory (no learn phase, no move hints).

    Lifting e2 alone first still arms the Post-Game Analysis gesture instead,
    so the two center gates never collide.
    """

    E2_COORD: tuple[int, int] = (4, 1)  # File e (c=4), Rank 2 (r=1)
    D2_COORD: tuple[int, int] = (3, 1)  # File d (c=3), Rank 2 (r=1)
    starter_coord: tuple[int, int] = (3, 1)
    starter_color: int = COLOR_INT_MEMORY_GOLD

    def __init__(self, state_manager: Any = None, timeout: float = 5.0):
        super().__init__(
            name="memory_replay",
            description="Memory Replay Gate: lift d2 -> lift e2 -> replace both to replay your last game from memory",
            state_manager=state_manager,
            timeout=timeout,
        )
        self.first_coord = self.D2_COORD
        self.second_coord = self.E2_COORD
        self.log_prefix = "Memory Replay gesture"
        self.flash_primary = "first"

    @property
    def hint(self) -> str | None:
        if self.step == 1:
            return "Lift e2 (King Pawn) to arm Memory Replay"
        elif self.step == 2:
            return "Replace d2 and e2 to replay your last game from memory"
        return None

    def _overlay_palette(self, now: float) -> tuple[int, int, int, int]:
        return (
            COLOR_INT_MEMORY_GOLD,
            COLOR_INT_MINT_EMERALD,
            COLOR_INT_MEMORY_GOLD,
            COLOR_INT_EMERALD,
        )

    def execute_completion(self) -> None:
        """Triggers arrival confirmation flare on d2/e2 and starts memory recall."""
        self._flash_completion_squares()
        if self.state_manager:
            _schedule_task(self.state_manager.start_replay_recall())


class EndgameMenuGesture(BaseGesture):
    """
    Physical Endgame Tablebase Trainer ("Endgame Academy") selection menu:
      - Lift c2 (Bishop's Pawn) to open the Endgame Catalog menu.
      - Rank 1 illuminates the 4 category options:
          a1 (0, 0) = Pawn Endgames (Pearl White)
          b1 (1, 0) = Rook Endgames (Azure Cyan)
          c1 (2, 0) = Minor Piece Endgames (Mint Emerald)
          d1 (3, 0) = Queen Endgames (Royal Violet)
      - Lifting / tapping a category piece switches category and cycles drills in that category.
        The selected drill's target pieces preview on ranks 2-7 in their piece-type colors!
      - Replacing c2 confirms the selected drill and initiates two-phase setup!
      - Replacing c2 without lifting any option cancels back to IDLE.
    """

    C2_COORD: tuple[int, int] = (2, 1)  # File c (c=2), Rank 2 (r=1)
    PAWN_COORD: tuple[int, int] = (0, 0)   # a1
    ROOK_COORD: tuple[int, int] = (1, 0)   # b1
    MINOR_COORD: tuple[int, int] = (2, 0)  # c1
    QUEEN_COORD: tuple[int, int] = (3, 0)  # d1

    starter_coord: tuple[int, int] = (2, 1)
    starter_color: int = Color(220, 140, 0)  # Warm Sun Amber

    CATEGORY_MAP: dict[tuple[int, int], str] = {
        (0, 0): "pawn",
        (1, 0): "rook",
        (2, 0): "minor",
        (3, 0): "queen",
    }

    CATEGORY_COLORS: dict[str, int] = {
        "pawn": COLOR_INT_PIECE_PAWN,
        "rook": COLOR_INT_PIECE_ROOK,
        "minor": COLOR_INT_PIECE_KNIGHT,
        "queen": COLOR_INT_PIECE_QUEEN,
    }

    def __init__(self, state_manager: Any = None, timeout: float = 30.0):
        super().__init__(
            name="endgame_menu",
            description="Endgame Academy menu: lift c2 -> pick Pawn(a1)/Rook(b1)/Minor(c1)/Queen(d1) -> preview drill -> replace c2 to train",
            state_manager=state_manager,
            timeout=timeout,
        )
        self.selected_category: str = "pawn"
        self.category_drill_index: dict[str, int] = {
            "pawn": 0,
            "rook": 0,
            "minor": 0,
            "queen": 0,
        }
        self._held_option: tuple[int, int] | None = None
        self._holdoff: bool = False
        self.log_prefix = "Endgame gesture"

    @property
    def hint(self) -> str | None:
        if self.step != 1:
            return None
        drill = self.get_active_drill()
        title = drill.title if drill else "Selected Drill"
        return f"Pick category: a1=Pawn · b1=Rook · c1=Minor · d1=Queen — Active: {title} — Replace c2 to start"

    def get_active_drill(self) -> Any | None:
        try:
            from app.endgame_db import CORE_CURRICULUM
        except ImportError:
            from .endgame_db import CORE_CURRICULUM
        cat_drills = [d for d in CORE_CURRICULUM if d.category.value == self.selected_category]
        if not cat_drills:
            return CORE_CURRICULUM[0] if CORE_CURRICULUM else None
        idx = self.category_drill_index.get(self.selected_category, 0) % len(cat_drills)
        return cat_drills[idx]

    def reset(self) -> None:
        super().reset()
        self._held_option = None

    def _soft_cancel(self, reason: str) -> None:
        logger.debug(f"{self.log_prefix} cancelled: {reason}")
        self.reset()
        self._holdoff = True

    def evaluate(
        self,
        physical_state: list[list[int]],
        now: float,
        is_armed: bool = True,
    ) -> bool:
        lifted_starting, extra_occupied = self._get_board_anomalies(physical_state)

        if len(extra_occupied) > 0:
            if self.is_active:
                self._soft_cancel(f"center pieces occupied: {extra_occupied}")
            return False

        if self._holdoff:
            if len(lifted_starting) == 0:
                self._holdoff = False
            return False

        if self.step == 0:
            if not is_armed:
                return False
            if lifted_starting == {self.C2_COORD}:
                self.step = 1
                self.start_time = now
                logger.info(f"{self.log_prefix}: c2 lifted alone -> Endgame menu open")
            return False

        if self.step == 1:
            if self.time_remaining(now) <= 0.0:
                self._soft_cancel("timeout")
                return False

            if self.C2_COORD not in lifted_starting:
                # c2 replaced back on board
                if len(lifted_starting) == 0:
                    logger.info(f"{self.log_prefix}: c2 replaced with all options settled -> starting drill")
                    self.reset()
                    return True
                else:
                    self._soft_cancel("c2 dropped while an option was still lifted")
                    return False

            option_lifts = lifted_starting - {self.C2_COORD}

            if len(option_lifts) > 1:
                self._soft_cancel(f"multiple options lifted simultaneously: {option_lifts}")
                return False

            if len(option_lifts) == 1:
                coord = next(iter(option_lifts))
                if coord in self.CATEGORY_MAP:
                    if self._held_option != coord:
                        self._held_option = coord
                        cat = self.CATEGORY_MAP[coord]
                        if self.selected_category == cat:
                            # Tapping the same category cycles to next drill
                            self.category_drill_index[cat] = (self.category_drill_index.get(cat, 0) + 1)
                        else:
                            self.selected_category = cat
                        self.start_time = now
                        logger.info(f"{self.log_prefix}: category selected={self.selected_category}, drill_idx={self.category_drill_index.get(cat, 0)}")
                else:
                    self._soft_cancel(f"invalid piece lifted: {coord}")
                    return False
            else:
                if self._held_option is not None:
                    if self.state_manager:
                        self.state_manager.trigger_arrival_flash(self._held_option[0], self._held_option[1], duration=0.5)
                    self._held_option = None

            return False

        return False

    def get_led_overlay(self, now: float) -> dict[tuple[int, int], int]:
        if self.step != 1:
            return {}

        is_night = _read_night_mode()
        overlay: dict[tuple[int, int], int] = {}
        pulse = 0.5 + 0.5 * math.sin(now * 3.5)

        # 1. c2 origin glows starter color
        overlay[self.C2_COORD] = scale_color(self.starter_color, 0.4 + 0.5 * pulse)

        # 2. Rank 1 category indicators
        for coord, cat in self.CATEGORY_MAP.items():
            base_col = self.CATEGORY_COLORS.get(cat, COLOR_INT_AZURE)
            if self.selected_category == cat:
                # Active category: vibrant pulse
                overlay[coord] = scale_color(base_col, 0.75 + 0.25 * pulse)
            else:
                # Inactive category: dim steady
                overlay[coord] = scale_color(base_col, 0.25)

        # 3. Preview target pieces of active drill
        drill = self.get_active_drill()
        if drill and drill.fen:
            import chess
            try:
                board = chess.Board(drill.fen)
                for sq, piece in board.piece_map().items():
                    c = chess.square_file(sq)
                    r = chess.square_rank(sq)
                    if (c, r) not in overlay:
                        piece_col = get_piece_type_color(piece.piece_type, is_night)
                        overlay[(c, r)] = scale_color(piece_col, 0.45 + 0.30 * pulse)
            except Exception:
                pass

        return overlay

    def execute_completion(self) -> None:
        drill = self.get_active_drill()
        drill_id = drill.id if drill else "pawn_opposition"
        logger.info(f"{self.log_prefix} completed! Starting drill: {drill_id}")
        if self.state_manager:
            _schedule_task(self.state_manager.start_endgame_drill(drill_id=drill_id))


class PhysicalGestureEngine:
    """
    Subsystem manager for physical board gestures.
    Monitors board states during IDLE / GAME_OVER, generates LED overlay frames,
    and coordinates async gesture executions.
    """

    def __init__(self, state_manager: Any = None):
        self.state_manager = state_manager
        self.gestures: list[BaseGesture] = []
        self._armed_for_gestures: bool = False
        # Register standard gestures
        self.register_gesture(RestartPreviousGameGesture(state_manager=state_manager))
        self.register_gesture(ToggleNightModeGesture(state_manager=state_manager))
        self.register_gesture(CenterRoyalGateGesture(state_manager=state_manager))
        self.register_gesture(MemoryReplayGateGesture(state_manager=state_manager))
        self.register_gesture(EndgameMenuGesture(state_manager=state_manager))

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
        is_setup_ready: bool = False,
        now: float | None = None,
    ) -> list[str]:
        """
        Evaluates registered gestures. Gestures only operate during IDLE or GAME_OVER,
        and can only start when the board has previously been fully reset into the
        standard starting configuration (is_setup_ready == True).
        Returns list of completed gesture names.
        """
        if now is None:
            now = time.time()

        if game_status not in ["IDLE", "GAME_OVER"]:
            self.reset()
            return []

        # When all 32 pieces are in their starting positions, arm the gesture engine
        if is_setup_ready:
            self._armed_for_gestures = True

        can_arm = self._armed_for_gestures

        completed: list[str] = []
        for gesture in self.gestures:
            if gesture.evaluate(physical_state, now, is_armed=can_arm):
                completed.append(gesture.name)
                gesture.execute_completion()
                self._armed_for_gestures = False

        if self.is_active:
            self._armed_for_gestures = False

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
        self._armed_for_gestures = False
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
