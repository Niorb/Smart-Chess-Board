"""
app/board_state.py

State manager for the Smart Chess Board.
Maintains physical sensor matrix, virtual-only simulation state, layered WS2812B LED frame rendering,
setup verification, move tracking, and real-time synchronization with the Lichess engine.
"""

import asyncio
import datetime
import logging
import math
import os
import sys
import threading
import time
from typing import Any

import chess

# Ensure parent directory is accessible for local imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import lgpio
except ImportError:
    class MockLgpio:
        def gpiochip_open(self, _): return "mock_chip"
        def gpiochip_close(self, _): pass
        def gpio_claim_output(self, *args): pass
        def gpio_claim_input(self, *args): pass
        def gpio_write(self, *args): pass
        def gpio_read(self, *args): return 1
        def callback(self, *args): pass
        error = Exception
        FALLING_EDGE = 1
        SET_PULL_UP = 1
    lgpio = MockLgpio()

try:
    import serial
except ImportError:
    serial = None

from board_hardware import (
    BOARD_COLS,
    BOARD_ROWS,
    apply_debounce,
    clear_baseline_history,
    get_latest_detection_state,
    init_mux_pins,
    scan_board,
    settings,
)

from app.coach_engine import (
    TIER_BEST_MAX_LOSS,
    TIER_GOOD_MAX_LOSS,
    TIER_INACCURACY_MAX_LOSS,
    CoachEngineUnavailable,
    MoveQuality,
    analysis_cache_key,
    coach_engine,
    load_cached_analysis,
    save_cached_analysis,
)
from app.config import (
    ANIM_MOVE_CONFIRM_DURATION_S,
    ANIM_UNCHARTED_NOVELTY_DURATION_S,
    BAUD_RATE,
    MOVE_TRACE_PERIOD_S,
    NUM_LEDS,
    SERIAL_PORT,
)
from app.gesture_engine import (
    PhysicalGestureEngine,
)
from app.gm_games import get_gm_game
from app.led_animations import (
    render_analysis_computing,
    render_capture_aura,
    render_castle_trace,
    render_clock_bar,
    render_guardrail_mismatch,
    render_move_trace,
    render_opponent_disconnected,
    render_promotion_scepter,
    render_resignation_aura,
    render_return_home_guide,
    render_uncharted_novelty,
    scale_color,
)
from app.openings import (
    OpeningInfo,
    get_book_moves_for_square,
    get_opening_info,
)
from app.led_helpers import (
    COLOR_INT_AZURE,
    COLOR_INT_CAPTURE_AURA_ATTACKER,
    COLOR_INT_CAPTURE_AURA_TARGET,
    COLOR_INT_CAPTURE_CONFIRM,
    COLOR_INT_CAPTURE_TRACE,
    COLOR_INT_CHECK,
    COLOR_INT_CLOCK_CRIT,
    COLOR_INT_CLOCK_OK,
    COLOR_INT_CLOCK_WARN,
    COLOR_INT_EVAL_BLACK,
    COLOR_INT_EVAL_WHITE,
    COLOR_INT_GUARDRAIL_MISSING,
    COLOR_INT_GUARDRAIL_UNEXPECTED,
    COLOR_INT_ILLEGAL,
    COLOR_INT_LEGAL_CAPTURE,
    COLOR_INT_LEGAL_TARGET,
    COLOR_INT_MINT_EMERALD,
    COLOR_INT_MOVE_BEST,
    COLOR_INT_MOVE_BLUNDER,
    COLOR_INT_MOVE_CONFIRM,
    COLOR_INT_MOVE_GOOD,
    COLOR_INT_MOVE_INACCURACY,
    COLOR_INT_MOVE_TRACE,
    COLOR_INT_NIGHT_AZURE,
    COLOR_INT_NIGHT_CAPTURE_AURA_ATTACKER,
    COLOR_INT_NIGHT_CAPTURE_AURA_TARGET,
    COLOR_INT_NIGHT_CAPTURE_TRACE,
    COLOR_INT_NIGHT_CHECK,
    COLOR_INT_NIGHT_CLOCK_CRIT,
    COLOR_INT_NIGHT_CLOCK_OK,
    COLOR_INT_NIGHT_CLOCK_WARN,
    COLOR_INT_NIGHT_EVAL_BLACK,
    COLOR_INT_NIGHT_EVAL_WHITE,
    COLOR_INT_NIGHT_GUARDRAIL_MISSING,
    COLOR_INT_NIGHT_GUARDRAIL_UNEXPECTED,
    COLOR_INT_NIGHT_ILLEGAL,
    COLOR_INT_NIGHT_LEGAL_CAPTURE,
    COLOR_INT_NIGHT_LEGAL_TARGET,
    COLOR_INT_NIGHT_MINT_EMERALD,
    COLOR_INT_NIGHT_MODE,
    COLOR_INT_NIGHT_MOVE_BEST,
    COLOR_INT_NIGHT_MOVE_BLUNDER,
    COLOR_INT_NIGHT_MOVE_GOOD,
    COLOR_INT_NIGHT_MOVE_INACCURACY,
    COLOR_INT_NIGHT_MOVE_TRACE,
    COLOR_INT_NIGHT_OPPONENT_CAPTURE,
    COLOR_INT_NIGHT_OPPONENT_FROM,
    COLOR_INT_NIGHT_OPPONENT_TO,
    COLOR_INT_NIGHT_PIECE_LIFTED,
    COLOR_INT_NIGHT_RETURN_HOME,
    COLOR_INT_NIGHT_ROYAL_VIOLET,
    COLOR_INT_NIGHT_SETUP_MISPLACED,
    COLOR_INT_NIGHT_SETUP_MISSING,
    COLOR_INT_NIGHT_START_BLACK_PRIMARY,
    COLOR_INT_NIGHT_TURN_BLACK,
    COLOR_INT_NIGHT_TURN_WHITE,
    COLOR_INT_OFF,
    COLOR_INT_OPPONENT_CAPTURE,
    COLOR_INT_OPPONENT_FROM,
    COLOR_INT_OPPONENT_TO,
    COLOR_INT_PIECE_LIFTED,
    COLOR_INT_RETURN_HOME,
    COLOR_INT_ROYAL_VIOLET,
    COLOR_INT_SETUP_MISPLACED,
    COLOR_INT_SETUP_MISSING,
    COLOR_INT_START_BLACK_PRIMARY,
    COLOR_INT_START_WHITE_PRIMARY,
    COLOR_INT_TURN_BLACK,
    COLOR_INT_TURN_WHITE,
    Color,
    all_leds_off,
    get_led_indices,
    init_strip,
)
from app.lichess_engine import format_clock_ms, lichess_engine
from app.path_interpolator import get_castle_rook_move, interpolate_move_path
from app.physical_tracker import PhysicalMoveTracker
from app.setup_validator import GameGuardrailResult, SetupResult, SetupValidator

logger = logging.getLogger("smart-chess-app.state")


class AnalysisEngineAdapter:
    """Adapts an arbitrary chess.Board to the engine interface expected by PhysicalMoveTracker."""

    def __init__(self, board: chess.Board):
        self.board = board
        self.my_color = "white" if board.turn == chess.WHITE else "black"
        self.game_info = {}


class LocalGameEngine:
    """
    Dedicated local chess game coordinator for physical two-player over-the-board matches.
    Maintains python-chess Board, move stack, turn timers, and game over evaluations.
    """

    def __init__(self):
        self.board: chess.Board = chess.Board()
        self.game_id: str | None = None
        self.start_time: float = 0.0
        self.move_timestamps: list[float] = []
        self.is_active: bool = False
        self.winner: str | None = None  # "white" | "black" | "draw" | None
        self.end_reason: str | None = None  # "checkmate" | "stalemate" | "threefold" | "50-move" | "insufficient_material" | "resignation" | "reset"
        self._last_move_cache: tuple[int, bool] = (-1, False)

    @property
    def my_color(self) -> str:
        """Returns active side-to-move so PhysicalMoveTracker tracks whoever's turn it is."""
        return "white" if self.board.turn == chess.WHITE else "black"

    @property
    def game_info(self) -> dict[str, Any]:
        """Provides game_info dictionary compatible with PhysicalMoveTracker.sync_game."""
        last_move_uci = self.board.peek().uci() if self.board.move_stack else None
        return {
            "game_id": self.game_id,
            "rated": False,
            "speed": "unlimited",
            "turn": "white" if self.board.turn == chess.WHITE else "black",
            "my_color": self.my_color,
            "opponent": {"username": "Local Player", "rating": 0, "title": None, "is_ai": False},
            "last_move": last_move_uci,
            "legal_moves": [m.uci() for m in self.board.legal_moves],
            "is_check": self.board.is_check(),
            "is_game_over": self.is_game_over,
            "winner": self.winner,
            "end_reason": self.end_reason,
        }

    @property
    def is_game_over(self) -> bool:
        return self.winner is not None or self.board.is_game_over()

    def start_game(self, fen: str | None = None, game_id: str | None = None) -> None:
        """Initializes a new local match."""
        if fen:
            self.board = chess.Board(fen)
        else:
            self.board = chess.Board()
        self.game_id = game_id or f"local_{int(time.time())}"
        self.start_time = time.time()
        self.move_timestamps = [self.start_time]
        self.is_active = True
        self.winner = None
        self.end_reason = None
        self._last_move_cache = (-1, False)
        logger.info(f"LocalGameEngine started game {self.game_id}")

    def apply_move(self, uci: str) -> bool:
        """Applies a UCI move to the local board and checks for endgame conditions."""
        if not self.is_active:
            return False
        try:
            move = chess.Move.from_uci(uci)
            if move not in self.board.legal_moves:
                logger.warning(f"Illegal move rejected in LocalGameEngine: {uci}")
                return False
            self.board.push(move)
            self.move_timestamps.append(time.time())
            self._check_game_over()
            return True
        except Exception as e:
            logger.error(f"Error applying move {uci} in LocalGameEngine: {e}")
            return False

    def make_move(
        self,
        from_file: int,
        from_rank: int,
        to_file: int,
        to_rank: int,
        promotion: str | None = None,
    ) -> bool:
        """1-indexed coordinate helper for physical move tracker."""
        from_sq = f"{chr(ord('a') + from_file - 1)}{from_rank}"
        to_sq = f"{chr(ord('a') + to_file - 1)}{to_rank}"
        uci = f"{from_sq}{to_sq}{promotion or ''}"
        return self.apply_move(uci)

    def _check_game_over(self) -> None:
        """Evaluates checkmate, stalemate, and draw conditions."""
        if self.board.is_checkmate():
            self.winner = "black" if self.board.turn == chess.WHITE else "white"
            self.end_reason = "checkmate"
            logger.info(f"Local match finished: {self.winner.upper()} won by checkmate!")
        elif self.board.is_stalemate():
            self.winner = "draw"
            self.end_reason = "stalemate"
            logger.info("Local match finished: Draw by stalemate!")
        elif self.board.is_insufficient_material():
            self.winner = "draw"
            self.end_reason = "insufficient_material"
            logger.info("Local match finished: Draw by insufficient material!")
        elif self.board.can_claim_fifty_moves():
            self.winner = "draw"
            self.end_reason = "50_move_rule"
            logger.info("Local match finished: Draw by 50-move rule!")
        elif self.board.can_claim_threefold_repetition():
            self.winner = "draw"
            self.end_reason = "threefold_repetition"
            logger.info("Local match finished: Draw by threefold repetition!")

    def resign(self, player_color: str = "white") -> None:
        """Resigns the active game on behalf of player_color."""
        if not self.is_active:
            return
        self.winner = "black" if player_color.lower() == "white" else "white"
        self.end_reason = "resignation"
        logger.info(f"Local match resigned by {player_color}. Winner: {self.winner}")

    def reset(self) -> None:
        """Resets the local game state back to clean initial."""
        self.board = chess.Board()
        self.game_id = None
        self.start_time = 0.0
        self.move_timestamps = []
        self.is_active = False
        self.winner = None
        self.end_reason = None
        self._last_move_cache = (-1, False)

    def get_board(self) -> list[list[str]]:
        """Returns 8x8 piece grid matching frontend/hardware coordinates."""
        grid = [["." for _ in range(8)] for _ in range(8)]
        for rank_idx in range(8):
            for file_idx in range(8):
                sq = chess.square(file_idx, rank_idx)
                piece = self.board.piece_at(sq)
                grid[rank_idx][file_idx] = piece.symbol() if piece else "."
        return grid

    def get_game_payload(self) -> dict[str, Any]:
        """Returns structured metadata for WebSockets and API endpoints."""
        last_move_uci = None
        last_move_is_capture = False
        if self.board.move_stack:
            last_move = self.board.peek()
            last_move_uci = last_move.uci()
            cache_count, cache_capture = getattr(self, "_last_move_cache", (-1, False))
            if cache_count == len(self.board.move_stack):
                last_move_is_capture = cache_capture
            else:
                try:
                    m = self.board.pop()
                    last_move_is_capture = bool(self.board.is_capture(m))
                    self.board.push(m)
                except Exception:
                    last_move_is_capture = False

        turn_str = "white" if self.board.turn == chess.WHITE else "black"
        return {
            "game_id": self.game_id,
            "type": "local",
            "is_local": True,
            "rated": False,
            "speed": "unlimited",
            "turn": turn_str,
            "my_color": turn_str,
            "white": {"username": "White (Local)", "rating": None, "title": None},
            "black": {"username": "Black (Local)", "rating": None, "title": None},
            "opponent": {"username": "Local Player", "rating": None, "title": None, "is_ai": False},
            "opponent_gone": None,
            "last_move": last_move_uci,
            "last_move_is_capture": last_move_is_capture,
            "legal_moves": [m.uci() for m in self.board.legal_moves],
            "is_check": self.board.is_check(),
            "is_game_over": self.is_game_over,
            "winner": self.winner,
            "end_reason": self.end_reason,
        }


# Shared immutable-ish sync targets (identity-stable so broadcast digests can detect change)
EMPTY_DIGITAL_GRID = [["." for _ in range(8)] for _ in range(8)]
ANALYSIS_CLOCKS = {"white": "∞", "black": "∞"}
IDLE_CLOCKS = {"white": "?", "black": "?"}

BROADCAST_HEARTBEAT_S = 0.25


class BoardStateManager:
    def __init__(self):
        self.serial_lock = threading.RLock()
        self.physical_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
        self.raw_analog_values = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
        self.digital_state = [["." for _ in range(BOARD_COLS)] for _ in range(BOARD_ROWS)]
        self.game_status = "IDLE"  # IDLE, SEEKING, PLAYING, GAME_OVER, SETUP, ANALYSIS
        self.virtual_only: bool = False
        self.clocks = {"white": "?", "black": "?"}
        self.led_test_active = False
        self.testing_led_index = -1
        self.is_calibrating: bool = False
        self.active_animation = None  # LifecycleAnimation | None
        self.custom_trace_path = None  # list[tuple[int, int]] | None
        self.custom_trace_is_capture: bool = False
        self.frozen_baselines = None  # Snapshot of baselines preserved during animations
        self.arrival_flash: dict | None = None
        self.guardrail_result: GameGuardrailResult | None = None

        # Background asyncio tasks (strong references prevent mid-flight GC)
        self._bg_tasks: set[asyncio.Task] = set()
        # Update-loop bookkeeping
        self._calibration_reset_pending = False
        self._prev_gesture_status = "IDLE"
        self._last_restoration_sig = None
        self._cached_anchor_key = None
        self._cached_anchor_board = None
        self._analysis_grid_fen = None

        # Analysis & Training Mode State
        self.analysis_submode: str = "review"  # "review" | "blunder_drill" | "replay_learn" | "replay_recall"
        self.analysis_game_moves: list[str] = []
        self.analysis_current_ply: int = 0
        self.analysis_evaluations: list[dict] = []
        self.analysis_played_analyses: list[dict] = []
        self.analysis_accuracy: dict = {"white": 100.0, "black": 100.0}
        self.analysis_counts: dict = {}
        self.analysis_blunders: list[dict] = []
        self.analysis_branch_moves: list[str] = []
        self.analysis_anchor_ply: int | None = None
        self.analysis_anchor_coord: tuple[int, int] | None = None
        self.analysis_active_board: chess.Board = chess.Board()
        self.analysis_blunder_index: int = 0
        self.analysis_blunder_attempts: int = 3
        self.analysis_blunder_hint_active: bool = False
        self.analysis_gm_game_id: str | None = None
        # Replay Trainer (memory training) state
        self.replay_learned_ply: int = 0
        self.replay_results: list[dict] = []
        self.replay_mistakes: int = 0
        self.replay_reveal_uci: str | None = None
        self.replay_complete: bool = False
        # Web-only analysis: the physical board is unused; reset gates, move
        # tracking, and LED guidance are all suppressed for this session.
        self.analysis_web_only: bool = False
        self.analysis_is_loading: bool = False
        self.analysis_error: str | None = None
        self.analysis_has_advanced: bool = False
        # Last game metadata for post-game analysis recall
        self.last_game_moves: list[str] = []
        self.last_game_id: str | None = None
        self.last_game_metadata: dict[str, Any] = {}

        # Setup verification, move tracking, physical gestures, and local two-player engine
        self.setup_validator = SetupValidator()
        self.move_tracker = PhysicalMoveTracker()
        self.gesture_engine = PhysicalGestureEngine(state_manager=self)
        self.local_engine = LocalGameEngine()
        self.can_start_local_game: bool = False
        self.setup_result: SetupResult = self.setup_validator.validate(self.physical_state)
        self.prev_setup_ready: bool = False

        # Opening book classification and Novelty Flare
        self.current_opening: OpeningInfo | None = None
        self.active_novelty_flare: dict[str, Any] | None = None

        # Hardware initialization (Serial for board + lgpio for MUX)
        try:
            self.h = lgpio.gpiochip_open(0)
            init_mux_pins(self.h)
            if serial:
                self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.05)
            else:
                self.ser = None
            logger.info(f"Hybrid board hardware initialized (MUX: lgpio, ADC: {SERIAL_PORT}).")
        except Exception as e:
            logger.error(f"Hardware init failed: {e}")
            self.h = None
            self.ser = None

        # LED strip initialization
        try:
            self.strip = init_strip()
            if self.strip:
                if self.ser:
                    self.strip.set_serial_conn(self.ser, self.serial_lock)
                logger.info("LED strip initialized successfully in BoardStateManager.")
            else:
                logger.info("LED strip not initialized (mock or non-Pi).")
        except Exception as e:
            logger.error(f"LED strip init failed in BoardStateManager: {e}")
            self.strip = None

    def _spawn_task(self, coro) -> asyncio.Task:
        """Schedules a background task keeping a strong reference until it completes."""
        task = asyncio.get_running_loop().create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    def trigger_arrival_flash(
        self,
        c: int,
        r: int,
        is_capture: bool = False,
        duration: float = ANIM_MOVE_CONFIRM_DURATION_S,
        extra_squares: list[tuple[int, int]] | None = None,
    ) -> None:
        """Triggers an immediate visual confirmation flash on the arrival square(s)."""
        squares = [(c, r)]
        if extra_squares:
            squares.extend(extra_squares)
        self.arrival_flash = {
            "square": (c, r),
            "squares": squares,
            "start_time": time.time(),
            "duration": duration,
            "is_capture": is_capture,
        }

    def resolve_pending_promotion(self, piece: str) -> bool:
        """
        Resolves an active pending underpromotion from the Web UI or REST API.
        Dispatches the chosen promotion piece to Lichess engine or Analysis engine.
        """
        if not self.move_tracker or not self.move_tracker.pending_promotion:
            return False

        from app.lichess_engine import lichess_engine

        move_res = self.move_tracker.resolve_promotion(piece)
        if not move_res:
            return False

        from_f, from_r, to_f, to_r, promo = move_res
        if self.game_status == "PLAYING":
            async def _dispatch_promo(f_f, f_r, t_f, t_r, p):
                try:
                    success = await lichess_engine.make_move(f_f, f_r, t_f, t_r, p)
                    if not success:
                        logger.warning("Promotion move rejected by Lichess API. Releasing in-flight lock.")
                        self.move_tracker.clear_in_flight_move()
                except Exception as err:
                    logger.error(f"Unexpected error dispatching promotion: {err}")
                    self.move_tracker.clear_in_flight_move()

            self._spawn_task(_dispatch_promo(from_f, from_r, to_f, to_r, promo))
            return True
        elif self.game_status == "ANALYSIS":
            from_sq = f"{chr(ord('a') + from_f - 1)}{from_r}"
            to_sq = f"{chr(ord('a') + to_f - 1)}{to_r}"
            uci = f"{from_sq}{to_sq}{promo or ''}"
            self.handle_analysis_move(uci)
            return True
        return False

    def trigger_animation(self, name: str, params: dict | None = None) -> bool:
        """
        Triggers a procedural full-board lifecycle animation.
        Supported names: 'GAME_STARTED', 'GAME_WON', 'GAME_LOST', 'GAME_DRAWN'.
        Freezes current analog baselines to protect them from voltage drop transients.
        """
        try:
            from app.led_animations import create_animation
            if self.frozen_baselines is None and "baselines" in settings:
                self.frozen_baselines = [list(col) for col in settings["baselines"]]
                logger.info("Snapshotted and froze sensor baselines prior to lifecycle animation.")

            p = dict(params or {})
            p.setdefault("night_mode", bool(settings.get("night_mode", False)))
            anim = create_animation(name, p)
            self.active_animation = anim
            logger.info(f"Triggered LED lifecycle animation: {name} (duration={anim.duration}s)")
            return True
        except Exception as e:
            logger.error(f"Failed to trigger animation '{name}': {e}")
            return False

    def _safe_scan(self, raw_state, freeze_baseline=False):
        with self.serial_lock:
            return scan_board(self.h, self.ser, raw_state, freeze_baseline=freeze_baseline)

    def _safe_calibrate(self):
        with self.serial_lock:
            if self.strip:
                try:
                    all_leds_off(self.strip)
                except Exception as e:
                    logger.error(f"Error turning off LEDs before calibration: {e}")
            self.is_calibrating = True
            try:
                from board_hardware import calibrate_board
                res = calibrate_board(self.h, self.ser)
                if res:
                    self.physical_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
                    self.move_tracker.reset()
                    # Signal the update loop to rebuild its debounce buffers (thread-safe handoff)
                    self._calibration_reset_pending = True
                return res
            finally:
                self.is_calibrating = False
                if self.strip:
                    try:
                        all_leds_off(self.strip)
                    except Exception as e:
                        logger.error(f"Error turning off LEDs after calibration: {e}")

    def _safe_calibrate_with_pieces(self):
        with self.serial_lock:
            if self.strip:
                try:
                    all_leds_off(self.strip)
                except Exception as e:
                    logger.error(f"Error turning off LEDs before calibration with pieces: {e}")
            self.is_calibrating = True
            try:
                from board_hardware import calibrate_board_with_pieces
                res = calibrate_board_with_pieces(self.h, self.ser)
                if res:
                    self.move_tracker.reset()
                    self._calibration_reset_pending = True
                return res
            finally:
                self.is_calibrating = False
                if self.strip:
                    try:
                        all_leds_off(self.strip)
                    except Exception as e:
                        logger.error(f"Error turning off LEDs after calibration with pieces: {e}")

    def get_physical_payload(self):
        detection = get_latest_detection_state()
        tracker_data = self.move_tracker.to_dict()
        if self.arrival_flash:
            tracker_data["arrival_flash"] = {
                "square": list(self.arrival_flash["square"]),
                "start_time": self.arrival_flash["start_time"],
                "duration": self.arrival_flash["duration"],
                "is_capture": self.arrival_flash["is_capture"],
            }
        return {
            "rows": BOARD_ROWS,
            "cols": BOARD_COLS,
            "grid": self.physical_state,
            "adc": self.raw_analog_values,
            "baselines": settings.get("baselines"),
            "led_test_active": self.led_test_active,
            "testing_led_index": self.testing_led_index,
            "disabled_squares": settings.get("disabled_squares", []),
            "virtual_only": self.virtual_only,
            "setup": (
                self.setup_result.to_dict()
                if hasattr(self, "setup_result") and self.setup_result
                else self.setup_validator.validate(self.physical_state).to_dict()
            ),
            "pieces_detected": detection.get("pieces_detected", False),
            "detected_starting_count": detection.get("detected_starting_count", 0),
            "pieces_mode": settings.get("pieces_mode", "auto"),
            "effective_pieces_mode": detection.get("effective_pieces_mode", False),
            "led_intensity": settings.get("led_intensity", 100),
            "night_mode": settings.get("night_mode", False),
            **tracker_data,
            "guardrail": (
                self.guardrail_result.to_dict()
                if self.guardrail_result is not None
                else None
            ),
            "active_animation": self.active_animation.name if (self.active_animation and self.active_animation.is_active()) else None,
            "custom_trace_path": [list(sq) for sq in self.custom_trace_path] if self.custom_trace_path else None,
            "gesture": self.gesture_engine.get_state_payload() if hasattr(self, "gesture_engine") else None,
        }

    def start_local_game(self, fen: str | None = None) -> dict[str, Any]:
        """
        Starts a local two-player over-the-board match.
        """
        if self.game_status == "ANALYSIS":
            self.stop_analysis_mode()

        self.local_engine.start_game(fen=fen)
        self.game_status = "PLAYING"
        self.can_start_local_game = False
        self.move_tracker.reset(self.physical_state)
        if hasattr(self, "gesture_engine"):
            self.gesture_engine.reset()
        self.digital_state = self.local_engine.get_board()
        self.current_opening = get_opening_info(self.local_engine.board)
        logger.info(f"Local two-player game session activated ({self.local_engine.game_id}).")
        return {"status": "success", "game_id": self.local_engine.game_id, "turn": self.local_engine.my_color}

    def stop_local_game(self, winner: str | None = None, reason: str = "resignation") -> dict[str, Any]:
        """
        Concludes or resigns the active local game session.
        """
        if not hasattr(self, "local_engine") or not self.local_engine.is_active:
            return {"status": "error", "message": "No active local game to stop"}

        if winner:
            self.local_engine.winner = winner
        self.local_engine.end_reason = reason
        self.local_engine.is_active = False
        self._record_last_game_from_local()
        self.game_status = "GAME_OVER"
        self.trigger_animation("GAME_WON" if winner in ("white", "black") else "GAME_DRAWN")
        return {"status": "success", "winner": self.local_engine.winner, "reason": reason}

    def _record_last_game_from_local(self) -> None:
        """Records the moves and metadata of the most recently finished local game for post-game analysis."""
        if not (hasattr(self, "local_engine") and self.local_engine.board and self.local_engine.board.move_stack):
            return

        moves = [m.uci() for m in self.local_engine.board.move_stack]
        self.last_game_moves = list(moves)
        self.last_game_id = self.local_engine.game_id
        self.last_game_metadata = self.local_engine.get_game_payload()

        try:
            from board_hardware import save_settings, settings
            settings["last_game_moves"] = list(moves)
            settings["last_game_id"] = self.local_engine.game_id
            settings["last_game_my_color"] = "white"
            save_settings()
            logger.info(f"Recorded local game ({len(moves)} plies) for post-game analysis.")
        except Exception as e:
            logger.warning(f"Could not persist last_game_moves from local game: {e}")

    async def start_analysis_mode(
        self,
        moves_uci: list[str] | None = None,
        game_id: str | None = None,
        source: str = "board",
    ) -> dict[str, Any]:
        """
        Activates Post-Game Analysis mode on the board and starts asynchronous batch evaluation.

        source="web" starts a webapp-only session: the physical board is ignored
        (no reset-to-IDLE gate, no move tracking, no LED guidance).
        """
        self.game_status = "ANALYSIS"
        self.analysis_submode = "review"
        self.analysis_web_only = source == "web"
        self.analysis_is_loading = True
        self.analysis_has_advanced = False
        self.analysis_error = None
        self.analysis_branch_moves = []
        self.analysis_anchor_ply = None
        self.analysis_anchor_coord = None
        self._analysis_grid_fen = None
        self.analysis_active_board = chess.Board()

        if moves_uci is not None and len(moves_uci) > 0:
            self.analysis_game_moves = list(moves_uci)
        elif game_id:
            gm_game = get_gm_game(game_id)
            if gm_game and getattr(gm_game, "moves", None):
                self.analysis_game_moves = list(gm_game.moves)
            else:
                self.analysis_game_moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
        elif self.last_game_moves and len(self.last_game_moves) > 0:
            self.analysis_game_moves = list(self.last_game_moves)
        elif getattr(lichess_engine, "last_game_moves", None) and len(lichess_engine.last_game_moves) > 0:
            self.analysis_game_moves = list(lichess_engine.last_game_moves)
        elif (
            getattr(lichess_engine, "board", None)
            and getattr(lichess_engine.board, "move_stack", None)
            and len(lichess_engine.board.move_stack) > 0
        ):
            self.analysis_game_moves = [m.uci() for m in lichess_engine.board.move_stack]
        else:
            settings_moves = []
            try:
                settings_moves = settings.get("last_game_moves", [])
            except Exception:
                settings_moves = []

            if settings_moves and len(settings_moves) > 0:
                self.analysis_game_moves = list(settings_moves)
            else:
                # Fallback Italian game demo
                self.analysis_game_moves = [
                    "e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5",
                    "c2c3", "g8f6", "d2d4", "e5d4", "c3d4", "c5b4",
                ]

        self.analysis_current_ply = 0

        # Fast path: serve previously completed Stockfish analysis for this exact game
        cache_key = analysis_cache_key(self.analysis_game_moves)
        cached = await asyncio.to_thread(load_cached_analysis, cache_key)
        if cached and cached.get("moves") == list(self.analysis_game_moves):
            result = cached["result"]
            self.analysis_evaluations = result.get("evaluations", [])
            self.analysis_played_analyses = result.get("played_analyses", [])
            self.analysis_accuracy = {
                "white": result.get("white_accuracy", 100.0),
                "black": result.get("black_accuracy", 100.0),
            }
            self.analysis_counts = result.get("counts", {})
            self.analysis_blunders = result.get("blunders", [])
            self.analysis_error = None
            self.analysis_is_loading = False
            logger.info(
                f"Analysis loaded from persistent cache ({len(self.analysis_game_moves)} plies)."
            )
            return self.get_analysis_payload()

        try:
            res = await coach_engine.batch_evaluate_game(self.analysis_game_moves)
            self.analysis_evaluations = res.get("evaluations", [])
            self.analysis_played_analyses = res.get("played_analyses", [])
            self.analysis_accuracy = {
                "white": res.get("white_accuracy", 100.0),
                "black": res.get("black_accuracy", 100.0),
            }
            self.analysis_counts = res.get("counts", {})
            self.analysis_blunders = res.get("blunders", [])
            self.analysis_error = None
            # Persist for instant re-analysis of the same game later
            await asyncio.to_thread(save_cached_analysis, cache_key, self.analysis_game_moves, res)
        except CoachEngineUnavailable as e:
            logger.error(f"Game analysis unavailable (Stockfish required): {e}")
            self.analysis_error = f"Stockfish unavailable: {e}"
        finally:
            self.analysis_is_loading = False

        return self.get_analysis_payload()

    def step_analysis(self, target_ply: int) -> dict[str, Any]:
        """Steps forward/backward or jumps to a specific ply in the game review."""
        if not self.analysis_game_moves:
            return self.get_analysis_payload()

        target_ply = max(0, min(len(self.analysis_game_moves), target_ply))
        self.analysis_current_ply = target_ply
        if target_ply > 0:
            self.analysis_has_advanced = True
        self.analysis_branch_moves = []
        self.analysis_anchor_ply = None
        self.analysis_anchor_coord = None
        self._last_restoration_sig = None

        # Reconstruct active board position
        self.analysis_active_board = chess.Board()
        for idx in range(target_ply):
            try:
                move = chess.Move.from_uci(self.analysis_game_moves[idx])
                if move in self.analysis_active_board.legal_moves:
                    self.analysis_active_board.push(move)
            except Exception as e:
                logger.warning(f"Error stepping move at ply {idx}: {e}")
                break

        # Keep the engine lines panel warm for the freshly reached position
        # (async, non-blocking; cached results are served instantly).
        coach_engine.request_lines(self.analysis_active_board)

        return self.get_analysis_payload()

    def reset_analysis_branch(self) -> dict[str, Any]:
        """Snaps back to original game timeline from a virtual branch."""
        restore_ply = self.analysis_anchor_ply if self.analysis_anchor_ply is not None else self.analysis_current_ply
        return self.step_analysis(restore_ply)

    def navigate_analysis(self, direction: str) -> dict[str, Any]:
        """
        Web-only navigation for Game Review (keyboard arrows / vim keys).

        - "back": while branched, un-plays exactly ONE branch move; on the mainline,
          steps one ply back.
        - "forward": steps one ply forward along the mainline (no-op while branched).
        - "start" / "end": jump to the first/last mainline ply, leaving any branch.

        Purely virtual: never touches LEDs or the physical move tracker. The response
        always carries "on_mainline" so the UI can flag the exact transition back to
        the game line.
        """
        payload = self.get_analysis_payload()
        if self.game_status != "ANALYSIS" or self.analysis_submode != "review":
            return {"action": "inactive", "on_mainline": True, "analysis": payload}

        direction = (direction or "").lower().strip()
        branched = bool(self.analysis_branch_moves)
        action = "step"

        if direction == "back":
            if branched:
                # Un-play exactly one branch move and rebuild the position.
                self.analysis_branch_moves.pop()
                anchor_board = self._get_anchor_board()
                self.analysis_active_board = anchor_board
                for b_move in self.analysis_branch_moves:
                    try:
                        self.analysis_active_board.push_uci(b_move)
                    except Exception:
                        pass
                self._last_restoration_sig = None
                action = "branch_back"
                if not self.analysis_branch_moves:
                    # Variation fully un-played: back on the main timeline.
                    self.analysis_anchor_ply = None
                    self.analysis_anchor_coord = None
                else:
                    # Re-engage Stockfish for the remaining variation position.
                    coach_engine.request_analysis(self.analysis_active_board)
                    coach_engine.request_lines(self.analysis_active_board)
            else:
                self.step_analysis(max(0, self.analysis_current_ply - 1))
        elif direction == "forward":
            if not branched:
                self.step_analysis(self.analysis_current_ply + 1)
            else:
                action = "noop"
        elif direction in ("start", "end"):
            # Jumps operate on the main timeline: exit any variation sandbox.
            self.step_analysis(0 if direction == "start" else len(self.analysis_game_moves))
        else:
            return {"action": "invalid_direction", "on_mainline": True, "analysis": payload}

        on_mainline = self.analysis_anchor_coord is None and not self.analysis_branch_moves
        return {
            "action": action,
            "direction": direction,
            "ply": self.analysis_current_ply,
            "branch_depth": len(self.analysis_branch_moves),
            "on_mainline": on_mainline,
            "analysis": self.get_analysis_payload(),
        }

    def stop_analysis_mode(self) -> dict[str, Any]:
        """Exits analysis mode and returns to IDLE."""
        self.game_status = "IDLE"
        self.analysis_submode = "review"
        self.analysis_web_only = False
        self.analysis_branch_moves = []
        self.analysis_anchor_ply = None
        self.analysis_anchor_coord = None
        self.analysis_error = None
        self._last_restoration_sig = None
        self._reset_replay_session()
        return self.get_analysis_payload()

    def _reset_replay_session(self) -> None:
        """Clears all Replay Trainer (memory training) session state."""
        self.replay_learned_ply = 0
        self.replay_results = []
        self.replay_mistakes = 0
        self.replay_reveal_uci = None
        self.replay_complete = False

    def _conclude_analysis_to_idle(self) -> None:
        """Shared teardown: analysis mode -> IDLE with tracker reset and BOARD_READY animation."""
        self.move_tracker.reset(self.physical_state)
        logger.info(
            "Physical board fully reset to standard starting position after analysis. "
            "Concluding analysis mode and transitioning to IDLE (ready for gestures)."
        )
        self.stop_analysis_mode()
        self.prev_setup_ready = True
        if hasattr(self, "gesture_engine"):
            self.gesture_engine.reset()
        self.trigger_animation(
            "BOARD_READY",
            {"night_mode": bool(settings.get("night_mode", False))},
        )
        self.guardrail_result = None

    def _try_conclude_analysis_on_board_reset(self, setup_res: SetupResult) -> bool:
        """
        Detects when the physical board has been fully restored to the standard
        starting position during Analysis mode.

        In Review mode this transitions back to IDLE. In Replay Trainer submodes
        it drives the phase machine instead:
          - replay_learn: restoring all 32 pieces ends the learn phase and
            enters memory recall scoped to the plies just learned.
          - replay_recall: restoring the board after a completed (or clearly
            abandoned) recall concludes the session back to IDLE.

        A complete 32-piece starting layout proves no piece is genuinely in hand,
        so any lingering move-tracker transients (e.g. lifted_square wedged by
        illegal free-form placements while the user restored captured pieces)
        are discarded rather than allowed to block the transition.
        """
        if (
            getattr(self, "analysis_is_loading", False)
            or getattr(self, "analysis_web_only", False)
            or not setup_res.is_setup_ready
        ):
            return False

        if self.analysis_submode in ("replay_learn", "replay_recall"):
            return self._handle_replay_board_reset()

        if not getattr(self, "analysis_has_advanced", False):
            return False

        self._conclude_analysis_to_idle()
        return True

    def _handle_replay_board_reset(self) -> bool:
        """Replay Trainer board-reset gate: learn -> recall, completed recall -> IDLE."""
        if self.analysis_submode == "replay_learn":
            if self.replay_learned_ply < 1:
                # Nothing learned yet (session just armed): keep waiting.
                return False
            logger.info(
                f"Replay learn phase concluded after {self.replay_learned_ply} plies "
                "(board reset to start position detected). Entering memory recall phase."
            )
            self._enter_recall_phase()
            return True

        if not self.replay_complete:
            if not self.replay_results:
                # Recall just armed (no attempts yet): keep waiting.
                return False
            # Abandoned incomplete recall (at least one attempt recorded):
            # let the user out to IDLE instead of trapping them.
            logger.info(
                "Replay recall abandoned (board reset before completion). "
                "Concluding Replay Trainer."
            )
        else:
            logger.info("Replay recall complete and board restored. Concluding Replay Trainer.")
        self._conclude_analysis_to_idle()
        return True

    def _enter_recall_phase(self) -> None:
        """Transitions the active Replay Trainer session from learn into memory recall."""
        self.move_tracker.reset(self.physical_state)
        self.analysis_submode = "replay_recall"
        self.analysis_branch_moves = []
        self.analysis_anchor_ply = None
        self.analysis_anchor_coord = None
        self.analysis_error = None
        self._last_restoration_sig = None
        self._analysis_grid_fen = None
        self.step_analysis(0)
        self.analysis_has_advanced = True
        self.trigger_animation(
            "RECALL_START",
            {"night_mode": bool(settings.get("night_mode", False))},
        )
        logger.info(
            "Memory recall phase started: replay the first "
            f"{self.replay_learned_ply} plies from memory."
        )

    def start_blunder_drill(self, index: int = 0) -> dict[str, Any]:
        """Starts Blunder Blitz Drill mode for an extracted blunder."""
        self.game_status = "ANALYSIS"
        self.analysis_submode = "blunder_drill"
        self.analysis_has_advanced = True
        self.analysis_blunder_index = max(0, min(len(self.analysis_blunders) - 1, index)) if self.analysis_blunders else 0
        self.analysis_blunder_attempts = 3
        self.analysis_blunder_hint_active = False

        if self.analysis_blunders and 0 <= self.analysis_blunder_index < len(self.analysis_blunders):
            blunder = self.analysis_blunders[self.analysis_blunder_index]
            fen = blunder.get("fen_before")
            if fen:
                self.analysis_active_board = chess.Board(fen)
        return self.get_analysis_payload()

    def submit_blunder_attempt(self, uci: str) -> dict[str, Any]:
        """Evaluates a blunder challenge attempt."""
        if not self.analysis_blunders or self.analysis_blunder_index >= len(self.analysis_blunders):
            return {"correct": False, "message": "No active blunder challenge."}

        blunder = self.analysis_blunders[self.analysis_blunder_index]
        best_move = blunder.get("best_move", "")

        if uci.lower() == best_move.lower():
            if len(uci) >= 4:
                to_c = ord(uci[2]) - ord('a')
                to_r = int(uci[3]) - 1
                self.trigger_arrival_flash(to_c, to_r, is_capture=False, duration=0.8)
            return {
                "correct": True,
                "message": "Brilliant! You found the grandmaster solution.",
                "best_move": best_move,
            }
        else:
            self.analysis_blunder_attempts = max(0, self.analysis_blunder_attempts - 1)
            return {
                "correct": False,
                "message": "Not quite the best move. Try again!",
                "attempts_remaining": self.analysis_blunder_attempts,
            }

    def toggle_blunder_hint(self) -> bool:
        """Toggles LED hint for the active blunder challenge."""
        self.analysis_blunder_hint_active = not self.analysis_blunder_hint_active
        return self.analysis_blunder_hint_active

    def start_gm_game(self, game_id: str) -> dict[str, Any]:
        """
        Starts a Replay Trainer learn session for a curated Grandmaster masterpiece.
        The user physically plays through the famous game with LED guidance; when
        they set the board back to the starting position, memory recall begins.
        """
        game = get_gm_game(game_id)
        if not game:
            return {"error": f"GM game '{game_id}' not found."}

        self.game_status = "ANALYSIS"
        self.analysis_submode = "replay_learn"
        self.analysis_gm_game_id = game_id
        self.analysis_game_moves = list(game.moves)
        self.analysis_current_ply = 0
        self.analysis_active_board = chess.Board()
        self.analysis_evaluations = []
        self.analysis_played_analyses = []
        self.analysis_branch_moves = []
        self.analysis_anchor_ply = None
        self.analysis_anchor_coord = None
        self.analysis_error = None
        self.analysis_is_loading = False
        self.analysis_has_advanced = False
        self._analysis_grid_fen = None
        self._last_restoration_sig = None
        self.move_tracker.reset(self.physical_state)
        self._reset_replay_session()

        return self.get_analysis_payload()

    async def start_replay_recall(self, moves_uci: list[str] | None = None) -> dict[str, Any]:
        """
        Starts a Replay Trainer session directly in memory recall phase (no learn phase),
        replaying the last played game from memory. Used by the Memory Replay gesture.
        Returns an error (and stays in IDLE) if no previous game is available.
        """
        resolved: list[str] = []
        if moves_uci is not None and len(moves_uci) > 0:
            resolved = list(moves_uci)
        elif self.last_game_moves and len(self.last_game_moves) > 0:
            resolved = list(self.last_game_moves)
        elif getattr(lichess_engine, "last_game_moves", None) and len(lichess_engine.last_game_moves) > 0:
            resolved = list(lichess_engine.last_game_moves)
        elif (
            getattr(lichess_engine, "board", None)
            and getattr(lichess_engine.board, "move_stack", None)
            and len(lichess_engine.board.move_stack) > 0
        ):
            resolved = [m.uci() for m in lichess_engine.board.move_stack]
        else:
            try:
                settings_moves = settings.get("last_game_moves", [])
                if settings_moves and len(settings_moves) > 0:
                    resolved = list(settings_moves)
            except Exception:
                resolved = []

        if not resolved:
            logger.warning(
                "Memory recall requested but no previous game is stored. Staying IDLE."
            )
            # Error cue: crimson flash on the gesture gate squares (d2/e2)
            self.trigger_arrival_flash(
                3, 1, is_capture=True, duration=1.4, extra_squares=[(4, 1)]
            )
            return {"error": "No previous game stored to replay from memory."}

        self.game_status = "ANALYSIS"
        self.analysis_submode = "replay_recall"
        self.analysis_gm_game_id = None
        self.analysis_game_moves = resolved
        self.analysis_current_ply = 0
        self.analysis_active_board = chess.Board()
        self.analysis_evaluations = []
        self.analysis_played_analyses = []
        self.analysis_branch_moves = []
        self.analysis_anchor_ply = None
        self.analysis_anchor_coord = None
        self.analysis_error = None
        self.analysis_is_loading = False
        self.analysis_has_advanced = True
        self._analysis_grid_fen = None
        self._last_restoration_sig = None
        self.move_tracker.reset(self.physical_state)
        self.replay_learned_ply = len(resolved)
        self.replay_results = []
        self.replay_mistakes = 0
        self.replay_reveal_uci = None
        self.replay_complete = False

        logger.info(
            f"Memory recall session started directly on last game ({len(resolved)} plies)."
        )
        return self.get_analysis_payload()

    def _replay_move_matches(self, expected: str, uci: str) -> bool:
        """Compares a physical UCI move against the stored game move (handles SAN castling)."""
        if not expected or not uci:
            return False
        if uci == expected.strip().lower():
            return True

        # Handle SAN castling vs UCI castling (e.g. O-O / O-O-O vs e1g1 / e1c1 / e8g8 / e8c8)
        norm_san = expected.upper().replace("0", "O")
        if norm_san in ("O-O", "O-O-O"):
            turn = self.analysis_active_board.turn
            expected_uci = (
                ("e1g1" if turn == chess.WHITE else "e8g8")
                if norm_san == "O-O"
                else ("e1c1" if turn == chess.WHITE else "e8c8")
            )
            return uci == expected_uci

        try:
            m_expected = (
                self.analysis_active_board.parse_san(expected)
                if not (len(expected) in (4, 5) and expected[:2].isalnum())
                else chess.Move.from_uci(expected)
            )
            m_actual = chess.Move.from_uci(uci)
            return m_expected == m_actual
        except Exception:
            return False

    def _replay_diverge(self, uci: str) -> None:
        """
        Registers a divergence from the game line (wrong move): anchors the position
        so the restoration machinery guides the user to un-play the wrong move.
        """
        if not self.analysis_anchor_coord:
            self.analysis_anchor_ply = self.analysis_current_ply
            self.analysis_anchor_coord = (ord(uci[0]) - ord('a'), int(uci[1]) - 1)
        self.analysis_active_board.push(chess.Move.from_uci(uci))
        self.analysis_branch_moves.append(uci)
        self.analysis_has_advanced = True
        self.move_tracker.clear_in_flight_move()
        self._last_restoration_sig = None

    def _replay_advance(self, uci: str, duration: float = 0.6) -> int:
        """Advances to the next ply after a correct physical move; flashes arrival square."""
        next_ply = self.analysis_current_ply + 1
        self.step_analysis(next_ply)
        self.analysis_has_advanced = True
        self.move_tracker.clear_in_flight_move()
        self._check_replay_completion()
        if len(uci) >= 4:
            to_c = ord(uci[2]) - ord('a')
            to_r = int(uci[3]) - 1
            self.trigger_arrival_flash(to_c, to_r, is_capture=False, duration=duration)
        return next_ply

    def _check_replay_completion(self) -> None:
        """Fires victory celebration once the recall target depth has been reached."""
        if (
            self.analysis_submode == "replay_recall"
            and not self.replay_complete
            and self.analysis_current_ply >= self.replay_learned_ply
        ):
            self.replay_complete = True
            self.trigger_animation(
                "RECALL_COMPLETE",
                {"night_mode": bool(settings.get("night_mode", False))},
            )
            correct = sum(1 for r in self.replay_results if r.get("correct"))
            logger.info(
                f"Replay recall complete: {correct}/{self.replay_learned_ply} plies "
                f"remembered correctly ({self.replay_mistakes} mistakes)."
            )

    def handle_replay_move(self, uci: str) -> dict[str, Any]:
        """
        Handles a physical/UI move during Replay Trainer submodes.

        Learn phase: matching moves advance with green confirmation; diverging moves
        anchor for snap-back. Recall phase: no hints — matches confirm in green,
        wrong legal moves flash red, reveal the grandmaster continuation, and must
        be un-played before following the revealed move (free of charge).
        """
        ply = self.analysis_current_ply
        expected = (
            self.analysis_game_moves[ply].strip()
            if 0 <= ply < len(self.analysis_game_moves)
            else None
        )
        is_match = bool(expected) and self._replay_move_matches(expected, uci)

        # ---- Learn phase -------------------------------------------------
        if self.analysis_submode == "replay_learn":
            if expected is None:
                # Full game already played in learn phase: ignore further moves
                # (the user should set the pieces back to start memory recall).
                self.move_tracker.clear_in_flight_move()
                return {
                    "action": "learn_complete",
                    "phase": "learn",
                    "ply": ply,
                    "analysis": self.get_analysis_payload(),
                }
            if is_match:
                next_ply = self._replay_advance(uci)
                self.replay_learned_ply = max(self.replay_learned_ply, next_ply)
                logger.info(f"Replay learn advanced to ply {next_ply} on move {uci}")
                return {
                    "action": "advance",
                    "phase": "learn",
                    "ply": next_ply,
                    "learned_ply": self.replay_learned_ply,
                    "analysis": self.get_analysis_payload(),
                }
            # Wrong move during learning: crimson flash + guided snap-back to the line
            try:
                move = chess.Move.from_uci(uci)
                if move not in self.analysis_active_board.legal_moves:
                    return {"action": "illegal", "uci": uci}
                self._replay_diverge(uci)
                if len(uci) >= 4:
                    to_c = ord(uci[2]) - ord('a')
                    to_r = int(uci[3]) - 1
                    self.trigger_arrival_flash(to_c, to_r, is_capture=True, duration=0.9)
                logger.info(f"Replay learn divergence on move {uci} (expected {expected})")
                return {
                    "action": "incorrect",
                    "phase": "learn",
                    "ply": ply,
                    "gm_move": expected,
                    "analysis": self.get_analysis_payload(),
                }
            except Exception as e:
                logger.error(f"Error handling replay learn move {uci}: {e}")
                return {"action": "error", "error": str(e)}

        # ---- Recall phase ------------------------------------------------
        if self.replay_complete:
            self.move_tracker.clear_in_flight_move()
            return {"action": "complete", "phase": "recall"}

        if is_match and self.replay_reveal_uci:
            # User followed the revealed correction: advance free of charge.
            self.replay_reveal_uci = None
            next_ply = self._replay_advance(uci, duration=0.45)
            logger.info(f"Replay recall followed reveal at ply {ply}; advanced to {next_ply}")
            return {
                "action": "revealed_advance",
                "phase": "recall",
                "ply": next_ply,
                "complete": self.replay_complete,
                "analysis": self.get_analysis_payload(),
            }

        if is_match:
            self.replay_results.append({"ply": ply, "correct": True})
            next_ply = self._replay_advance(uci, duration=0.8)
            logger.info(f"Replay recall correct at ply {ply}: remembered {uci}")
            return {
                "action": "correct",
                "phase": "recall",
                "ply": next_ply,
                "mistakes": self.replay_mistakes,
                "complete": self.replay_complete,
                "analysis": self.get_analysis_payload(),
            }

        # Wrong move during recall
        try:
            move = chess.Move.from_uci(uci)
            if move not in self.analysis_active_board.legal_moves:
                return {"action": "illegal", "uci": uci}
            self.replay_results.append({"ply": ply, "correct": False})
            self.replay_mistakes += 1
            self.replay_reveal_uci = expected.lower() if expected else None
            self._replay_diverge(uci)
            if len(uci) >= 4:
                to_c = ord(uci[2]) - ord('a')
                to_r = int(uci[3]) - 1
                self.trigger_arrival_flash(to_c, to_r, is_capture=True, duration=0.9)
            logger.info(
                f"Replay recall mistake at ply {ply} ({uci}); revealing {expected}"
            )
            return {
                "action": "incorrect",
                "phase": "recall",
                "ply": ply,
                "gm_move": expected,
                "mistakes": self.replay_mistakes,
                "reveal_uci": self.replay_reveal_uci,
                "analysis": self.get_analysis_payload(),
            }
        except Exception as e:
            logger.error(f"Error handling replay recall move {uci}: {e}")
            return {"action": "error", "error": str(e)}

    def handle_analysis_move(self, uci: str, source: str = "board") -> dict[str, Any]:
        """
        Handles a move played on the board (physical move or web UI action) during ANALYSIS mode.
        If playing the move matching the current game ply, automatically advances to the next ply!
        If playing an alternative move, creates or extends a virtual exploration branch.

        source="board" (physical play) triggers arrival-flash LED feedback; source="web"
        keeps the physical board fully passive. Web input additionally accepts SAN
        (e.g. 'Nf3', 'exd5', 'O-O') in the review submode.
        """
        if self.game_status != "ANALYSIS":
            return {"error": "Not in analysis mode"}

        raw_text = uci.strip()
        uci = raw_text.lower()

        # 1. Blunder Drill submode
        if self.analysis_submode == "blunder_drill":
            return self.submit_blunder_attempt(uci)

        # 2. Replay Trainer submodes (learn / memory recall)
        if self.analysis_submode in ("replay_learn", "replay_recall"):
            return self.handle_replay_move(uci)

        # 3. Game Review submode
        web = source == "web"
        if web:
            # Accept SAN input by normalizing to UCI against the active position.
            try:
                uci = chess.Move.from_uci(uci).uci()
            except Exception:
                try:
                    uci = self.analysis_active_board.parse_san(raw_text).uci()
                except Exception:
                    pass  # left unparseable; reported as illegal below

        # If on main game timeline and played the move matching current ply:
        if (
            not self.analysis_anchor_coord
            and 0 <= self.analysis_current_ply < len(self.analysis_game_moves)
        ):
            expected_str = self.analysis_game_moves[self.analysis_current_ply].strip()
            is_match = (uci == expected_str.lower())
            if not is_match:
                # Handle SAN castling vs UCI castling (e.g. O-O / O-O-O vs e1g1 / e1c1 / e8g8 / e8c8)
                norm_san = expected_str.upper().replace("0", "O")
                if norm_san in ("O-O", "O-O-O"):
                    turn = self.analysis_active_board.turn
                    if norm_san == "O-O":
                        expected_uci = "e1g1" if turn == chess.WHITE else "e8g8"
                    else:
                        expected_uci = "e1c1" if turn == chess.WHITE else "e8c8"
                    is_match = (uci == expected_uci)
                else:
                    try:
                        m_expected = (
                            self.analysis_active_board.parse_san(expected_str)
                            if not (len(expected_str) in (4, 5) and expected_str[:2].isalnum())
                            else chess.Move.from_uci(expected_str)
                        )
                        m_actual = chess.Move.from_uci(uci)
                        is_match = (m_expected == m_actual)
                    except Exception:
                        pass

            if is_match:
                # Automatically advance to next ply!
                next_ply = self.analysis_current_ply + 1
                self.step_analysis(next_ply)
                self.analysis_has_advanced = True
                if not web:
                    self.move_tracker.clear_in_flight_move()
                    if len(uci) >= 4:
                        to_c = ord(uci[2]) - ord('a')
                        to_r = int(uci[3]) - 1
                        self.trigger_arrival_flash(to_c, to_r, is_capture=False, duration=0.6)
                logger.info(f"Analysis auto-advanced to ply {self.analysis_current_ply} on move {uci}")
                return {
                    "action": "advance",
                    "ply": self.analysis_current_ply,
                    "uci": uci,
                    "analysis": self.get_analysis_payload(),
                }

        # If user plays an alternative legal move in the active position:
        try:
            move = chess.Move.from_uci(uci)
            if move in self.analysis_active_board.legal_moves:
                if not self.analysis_anchor_coord:
                    self.analysis_anchor_ply = self.analysis_current_ply
                    self.analysis_anchor_coord = (ord(uci[0]) - ord('a'), int(uci[1]) - 1)
                self.analysis_active_board.push(move)
                self.analysis_branch_moves.append(uci)
                self.analysis_has_advanced = True
                if not web:
                    self.move_tracker.clear_in_flight_move()
                self._last_restoration_sig = None
                coach_engine.request_analysis(self.analysis_active_board)
                coach_engine.request_lines(self.analysis_active_board)
                if not web and len(uci) >= 4:
                    to_c = ord(uci[2]) - ord('a')
                    to_r = int(uci[3]) - 1
                    self.trigger_arrival_flash(to_c, to_r, is_capture=False, duration=0.6)
                logger.info(f"Analysis created virtual branch on move {uci} (Branch depth: {len(self.analysis_branch_moves)})")
                return {
                    "action": "branch",
                    "branch_moves": self.analysis_branch_moves,
                    "uci": uci,
                    "analysis": self.get_analysis_payload(),
                }
            else:
                logger.warning(f"Illegal analysis move attempted: {uci}")
                return {"action": "illegal", "uci": uci}
        except Exception as e:
            logger.error(f"Error executing analysis move {uci}: {e}")
            return {"action": "error", "error": str(e)}

    def _get_anchor_board(self) -> chess.Board:
        """Reconstructs (with caching) the board position at the analysis divergence anchor ply."""
        target_ply = min(self.analysis_anchor_ply, len(self.analysis_game_moves))
        key = (target_ply, tuple(self.analysis_game_moves))
        if self._cached_anchor_key == key and self._cached_anchor_board is not None:
            return self._cached_anchor_board.copy()

        anchor_board = chess.Board()
        for idx in range(target_ply):
            try:
                m_str = self.analysis_game_moves[idx].strip()
                if len(m_str) in (4, 5) and m_str[:2].isalnum():
                    anchor_board.push_uci(m_str)
                else:
                    anchor_board.push_san(m_str)
            except Exception:
                pass

        self._cached_anchor_key = key
        self._cached_anchor_board = anchor_board
        return anchor_board.copy()

    def _check_analysis_board_restoration(self) -> bool:
        """
        Checks if the physical board state has been restored to the divergence anchor position
        or an earlier intermediate branch position.
        If the physical board matches the divergence anchor board, automatically clears the branch
        and snaps back to the main game timeline.
        """
        if (
            self.game_status != "ANALYSIS"
            or self.analysis_anchor_coord is None
            or self.analysis_anchor_ply is None
            or self.physical_state is None
        ):
            return False

        # Don't snap back while the player is in the middle of lifting a piece or executing a move
        if (
            getattr(self.move_tracker, "lifted_square", None) is not None
            or getattr(self.move_tracker, "in_flight_move", None) is not None
            or getattr(self.move_tracker, "pending_castling_rook", None) is not None
        ):
            return False

        # Skip re-evaluation entirely while the physical matrix is unchanged since the last check
        state_sig = tuple(map(tuple, self.physical_state))
        if state_sig == self._last_restoration_sig:
            return False
        self._last_restoration_sig = state_sig

        # Reconstruct the anchor board from the game timeline (cached)
        anchor_board = self._get_anchor_board()

        # Validate if current physical board exactly matches the anchor board
        res = self.setup_validator.validate_game_state(self.physical_state, anchor_board, None)
        if res.is_synchronized:
            logger.info(
                f"Physical board restored to divergence anchor position at ply {self.analysis_anchor_ply}. "
                "Automatically snapping back to game timeline."
            )
            restored_ply = self.analysis_anchor_ply
            self.analysis_current_ply = restored_ply
            self.analysis_anchor_coord = None
            self.analysis_anchor_ply = None
            self.analysis_branch_moves = []
            self.analysis_active_board = anchor_board
            self.move_tracker.reset(self.physical_state)

            if 0 <= restored_ply < len(self.analysis_game_moves):
                m_str = self.analysis_game_moves[restored_ply]
                if len(m_str) >= 4:
                    try:
                        to_c = ord(m_str[2]) - ord('a')
                        to_r = int(m_str[3]) - 1
                        if 0 <= to_c < 8 and 0 <= to_r < 8:
                            self.trigger_arrival_flash(to_c, to_r, is_capture=False, duration=0.6)
                    except Exception:
                        pass
            return True

        # Check if physical board matches an earlier step in the branch (step-by-step un-playing)
        if len(self.analysis_branch_moves) > 1:
            for step_idx in range(len(self.analysis_branch_moves) - 1, 0, -1):
                temp_b = anchor_board.copy()
                for b_move in self.analysis_branch_moves[:step_idx]:
                    try:
                        temp_b.push_uci(b_move)
                    except Exception:
                        pass
                b_res = self.setup_validator.validate_game_state(self.physical_state, temp_b, None)
                if b_res.is_synchronized:
                    logger.info(f"Physical board restored to branch depth {step_idx}.")
                    self.analysis_branch_moves = self.analysis_branch_moves[:step_idx]
                    self.analysis_active_board = temp_b
                    self.move_tracker.reset(self.physical_state)
                    coach_engine.request_analysis(self.analysis_active_board)
                    return True

        return False

    def get_analysis_payload(self) -> dict[str, Any]:
        """Constructs serialized payload for Analysis and Training modes."""
        curr_eval = None
        if self.analysis_branch_moves:
            # Inside a variation sandbox: serve the LIVE Stockfish evaluation of
            # the branch position (requested on every branch move) so the engine
            # keeps suggesting candidates off the mainline.
            try:
                branch_eval = coach_engine.get_cached_evaluation(self.analysis_active_board.fen())
                if branch_eval is not None:
                    curr_eval = branch_eval.to_dict()
            except Exception as e:
                logger.debug(f"Branch evaluation lookup failed: {e}")
        elif 0 <= self.analysis_current_ply < len(self.analysis_evaluations):
            curr_eval = self.analysis_evaluations[self.analysis_current_ply]

        gm_game = get_gm_game(self.analysis_gm_game_id) if self.analysis_gm_game_id else None

        # Top-3 engine lines for the active position (cached; computed async in
        # the background so the UI never blocks on Stockfish).
        top_lines = coach_engine.get_cached_lines(self.analysis_active_board.fen())

        return {
            "active": self.game_status == "ANALYSIS",
            "submode": self.analysis_submode,
            "is_loading": self.analysis_is_loading,
            "error": self.analysis_error,
            "current_ply": self.analysis_current_ply,
            "total_plys": len(self.analysis_game_moves),
            "game_moves": self.analysis_game_moves,
            "evaluations": self.analysis_evaluations,
            "played_analyses": self.analysis_played_analyses,
            "accuracy": self.analysis_accuracy,
            "counts": self.analysis_counts,
            "current_eval": curr_eval,
            "branch_moves": self.analysis_branch_moves,
            "is_branching": bool(self.analysis_anchor_coord is not None),
            "anchor_ply": self.analysis_anchor_ply,
            "anchor_coord": list(self.analysis_anchor_coord) if self.analysis_anchor_coord else None,
            "blunders": self.analysis_blunders,
            "blunder_index": self.analysis_blunder_index,
            "blunder_attempts": self.analysis_blunder_attempts,
            "blunder_hint_active": self.analysis_blunder_hint_active,
            "gm_game": gm_game.to_dict() if gm_game else None,
            "replay": {
                "phase": (
                    self.analysis_submode.replace("replay_", "")
                    if self.analysis_submode.startswith("replay_")
                    else None
                ),
                "learned_ply": self.replay_learned_ply,
                "results": self.replay_results,
                "mistakes": self.replay_mistakes,
                "reveal_uci": self.replay_reveal_uci,
                "complete": self.replay_complete,
            },
            "fen": self.analysis_active_board.fen(),
            # Web-board interaction data (drag & drop legality, check indicator)
            "legal_moves": [m.uci() for m in self.analysis_active_board.legal_moves],
            "in_check": self.analysis_active_board.is_check(),
            "top_lines": top_lines,
        }

    def _build_coach_payload(self) -> dict[str, Any]:
        is_ai = getattr(lichess_engine, "is_ai_game", False)
        coach_ai_only = settings.get("coach_ai_only", True)
        fair_play_active = coach_ai_only and not is_ai
        coach_hints_enabled = settings.get("coach_hints_enabled", True)
        eval_bar_enabled = settings.get("eval_bar_enabled", True)

        return {
            "enabled": bool((coach_hints_enabled or eval_bar_enabled) and not fair_play_active),
            "eval_bar_enabled": bool(eval_bar_enabled and not fair_play_active),
            "coach_hints_enabled": bool(coach_hints_enabled and not fair_play_active),
            "is_ai_game": bool(is_ai),
            "fair_play_active": bool(fair_play_active),
            "evaluation": None,
            "lifted_move_hints": [],
        }

    def _build_broadcast_payload(self, diag_info) -> dict[str, Any]:
        """Constructs the unified WebSocket broadcast payload."""
        if hasattr(self, "local_engine") and self.local_engine.is_active:
            engine_board = self.local_engine.board
            game_payload = self.local_engine.get_game_payload()
            my_color = self.local_engine.my_color
            turn = "white" if engine_board.turn == chess.WHITE else "black"
            clocks_raw = {
                "white": None,
                "black": None,
                "updated_at": None,
                "turn": turn,
            }
        else:
            engine_board = getattr(lichess_engine, "board", None)
            game_payload = lichess_engine.get_game_payload()
            my_color = lichess_engine.my_color
            turn = None
            if engine_board is not None:
                turn = "white" if engine_board.turn == chess.WHITE else "black"
            try:
                interp_clocks = lichess_engine.get_interpolated_clocks()
            except Exception:
                interp_clocks = {"white": None, "black": None}
            clocks_raw = {
                "white": interp_clocks.get("white"),
                "black": interp_clocks.get("black"),
                "updated_at": getattr(lichess_engine, "clocks_updated_at", None),
                "turn": turn,
            }

        return {
            "status": self.game_status,
            "virtual_only": self.virtual_only,
            "physical": self.get_physical_payload(),
            "digital": self.digital_state,
            "clocks": self.clocks,
            "clocks_raw": clocks_raw,
            "my_color": my_color,
            "game": game_payload,
            "coach": self._build_coach_payload(),
            "opening": self.current_opening.to_dict() if self.current_opening else None,
            "gesture": self.gesture_engine.get_state_payload() if hasattr(self, "gesture_engine") else None,
            "analysis": self.get_analysis_payload(),
            "diagnostics": diag_info,
        }

    def _process_setup_ready_edge(self, is_ready: bool, gestures_just_completed: list[str]) -> None:
        """
        Fires/cancels the BOARD_READY animation on setup-readiness transitions and
        arms/disarms the local two-player game auto-start gate.

        Suppressed on the tick a physical gesture completes: the gate-closing
        placement restores the starting position and must not replay the
        setup animation.
        """
        if self.game_status not in ["IDLE", "SETUP", "GAME_OVER"]:
            self.prev_setup_ready = False
            return

        if is_ready and not self.prev_setup_ready:
            gesture_active = hasattr(self, "gesture_engine") and self.gesture_engine.is_active
            if not gestures_just_completed and not gesture_active:
                self.trigger_animation(
                    "BOARD_READY",
                    {"night_mode": bool(settings.get("night_mode", False))},
                )
            self.can_start_local_game = True
            self.prev_setup_ready = True
        elif not is_ready and self.prev_setup_ready:
            self.prev_setup_ready = False
            if self.active_animation and self.active_animation.name in ["BOARD_READY", "SETUP_COMPLETE"]:
                self.active_animation = None
                if self.frozen_baselines is not None:
                    settings["baselines"] = [list(col) for col in self.frozen_baselines]
                    clear_baseline_history()
                    self.frozen_baselines = None

    def get_full_state(self, diag_info=None):
        """Constructs a complete serialized snapshot of the full system state."""
        if diag_info is None:
            diag_info = {
                "status": "OK" if (self.ser or self.virtual_only) else "DISCONNECTED",
                "last_raw_line": "",
                "timeouts": 0,
                "errors": 0,
            }

        return self._build_broadcast_payload(diag_info)

    def get_health_status(self):
        serial_status = "CONNECTED" if (self.ser is not None and getattr(self.ser, "is_open", True)) else "DISCONNECTED"
        gpio_status = "CONNECTED" if self.h is not None else "DISCONNECTED"
        led_status = "CONNECTED" if self.strip is not None else "DISCONNECTED"
        engine_status = "CONNECTED" if getattr(lichess_engine, "is_running", False) else "DISCONNECTED"

        col_mode = settings.get("col_mode", "auto")
        disabled_squares = settings.get("disabled_squares", [])
        scan_delay_ms = settings.get("scan_delay", 100 if col_mode == "manual" else 10)

        subsystems = {
            "serial": serial_status,
            "gpio": gpio_status,
            "led_strip": led_status,
            "chess_engine": engine_status,
            "lichess_engine": engine_status,
        }

        matrix = {
            "col_mode": col_mode,
            "disabled_squares": disabled_squares,
            "scan_delay_ms": scan_delay_ms,
            "virtual_only": self.virtual_only,
        }

        if self.virtual_only:
            overall_status = "HEALTHY" if engine_status == "CONNECTED" else "DEGRADED"
        elif serial_status == "DISCONNECTED" or gpio_status == "DISCONNECTED":
            overall_status = "DISCONNECTED"
        elif (
            led_status == "DISCONNECTED"
            or engine_status == "DISCONNECTED"
            or len(disabled_squares) > 0
            or col_mode == "manual"
        ):
            overall_status = "DEGRADED"
        else:
            overall_status = "HEALTHY"

        return {
            "status": overall_status,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "subsystems": subsystems,
            "matrix": matrix,
        }

    def _update_leds(self):
        """
        Renders the layered physical WS2812B LED frame:
        0. Animation Layer: Procedural full-board lifecycle animations (Game start, win, loss, draw).
        1. Base Layer (IDLE/SETUP): Starting squares missing pieces / misplaced pieces.
        2. Game Layer (PLAYING): King check, pending opponent move (with animated comet trace), lifted piece & legal target dots.
        3. Custom Trace Diagnostic: custom_trace_path override.
        """
        if (
            self.virtual_only
            or not self.strip
            or self.led_test_active
            or self.is_calibrating
        ):
            return

        try:
            now = time.time()
            col_mode = settings.get("col_mode", "auto")
            manual_col = settings.get("manual_col", 0)
            night_mode = bool(settings.get("night_mode", False))

            base_color = COLOR_INT_NIGHT_MODE if night_mode else COLOR_INT_OFF
            frame = [base_color] * NUM_LEDS

            # Active Palette Selection (Day Mode 100% untouched; Night Mode uses vivid high-contrast colors)
            c_setup_missing = COLOR_INT_NIGHT_SETUP_MISSING if night_mode else COLOR_INT_SETUP_MISSING
            c_setup_misplaced = COLOR_INT_NIGHT_SETUP_MISPLACED if night_mode else COLOR_INT_SETUP_MISPLACED
            c_piece_lifted = COLOR_INT_NIGHT_PIECE_LIFTED if night_mode else COLOR_INT_PIECE_LIFTED
            c_legal_target = COLOR_INT_NIGHT_LEGAL_TARGET if night_mode else COLOR_INT_LEGAL_TARGET
            c_legal_capture = COLOR_INT_NIGHT_LEGAL_CAPTURE if night_mode else COLOR_INT_LEGAL_CAPTURE
            c_opp_from = COLOR_INT_NIGHT_OPPONENT_FROM if night_mode else COLOR_INT_OPPONENT_FROM
            c_opp_to_quiet = COLOR_INT_NIGHT_OPPONENT_TO if night_mode else COLOR_INT_OPPONENT_TO
            c_opp_to_capture = COLOR_INT_NIGHT_OPPONENT_CAPTURE if night_mode else COLOR_INT_OPPONENT_CAPTURE
            c_move_trace = COLOR_INT_NIGHT_MOVE_TRACE if night_mode else COLOR_INT_MOVE_TRACE
            c_capture_trace = COLOR_INT_NIGHT_CAPTURE_TRACE if night_mode else COLOR_INT_CAPTURE_TRACE
            c_check = COLOR_INT_NIGHT_CHECK if night_mode else COLOR_INT_CHECK
            c_turn_white = COLOR_INT_NIGHT_TURN_WHITE if night_mode else COLOR_INT_TURN_WHITE
            c_turn_black = COLOR_INT_NIGHT_TURN_BLACK if night_mode else COLOR_INT_TURN_BLACK
            c_illegal = COLOR_INT_NIGHT_ILLEGAL if night_mode else COLOR_INT_ILLEGAL
            c_eval_white = COLOR_INT_NIGHT_EVAL_WHITE if night_mode else COLOR_INT_EVAL_WHITE
            c_eval_black = COLOR_INT_NIGHT_EVAL_BLACK if night_mode else COLOR_INT_EVAL_BLACK
            c_clock_ok = COLOR_INT_NIGHT_CLOCK_OK if night_mode else COLOR_INT_CLOCK_OK
            c_clock_warn = COLOR_INT_NIGHT_CLOCK_WARN if night_mode else COLOR_INT_CLOCK_WARN
            c_clock_crit = COLOR_INT_NIGHT_CLOCK_CRIT if night_mode else COLOR_INT_CLOCK_CRIT
            c_move_best = COLOR_INT_NIGHT_MOVE_BEST if night_mode else COLOR_INT_MOVE_BEST
            c_move_good = COLOR_INT_NIGHT_MOVE_GOOD if night_mode else COLOR_INT_MOVE_GOOD
            c_move_inacc = COLOR_INT_NIGHT_MOVE_INACCURACY if night_mode else COLOR_INT_MOVE_INACCURACY
            c_move_blunder = COLOR_INT_NIGHT_MOVE_BLUNDER if night_mode else COLOR_INT_MOVE_BLUNDER
            c_guardrail_missing = COLOR_INT_NIGHT_GUARDRAIL_MISSING if night_mode else COLOR_INT_GUARDRAIL_MISSING
            c_guardrail_unexp = COLOR_INT_NIGHT_GUARDRAIL_UNEXPECTED if night_mode else COLOR_INT_GUARDRAIL_UNEXPECTED
            c_capture_aura_target = COLOR_INT_NIGHT_CAPTURE_AURA_TARGET if night_mode else COLOR_INT_CAPTURE_AURA_TARGET
            c_capture_aura_attacker = COLOR_INT_NIGHT_CAPTURE_AURA_ATTACKER if night_mode else COLOR_INT_CAPTURE_AURA_ATTACKER
            c_mint_emerald = COLOR_INT_NIGHT_MINT_EMERALD if night_mode else COLOR_INT_MINT_EMERALD
            c_azure = COLOR_INT_NIGHT_AZURE if night_mode else COLOR_INT_AZURE
            c_royal_violet = COLOR_INT_NIGHT_ROYAL_VIOLET if night_mode else COLOR_INT_ROYAL_VIOLET

            def set_square_leds(c: int, r: int, color_val: int):
                if col_mode == "manual" and c != manual_col:
                    return
                for idx in get_led_indices(r, c):
                    if 0 <= idx < NUM_LEDS:
                        frame[idx] = color_val

            def flush_frame():
                for idx, color in enumerate(frame):
                    self.strip.setPixelColor(idx, color)
                self.strip.show()

            def apply_arrival_flash(source: dict) -> bool:
                """Renders an exponential-decay confirmation flash. Returns False when expired."""
                flash_squares = source.get("squares") or [source["square"]]
                elapsed = now - source["start_time"]
                dur = source.get("duration", ANIM_MOVE_CONFIRM_DURATION_S)
                if not (0 <= elapsed < dur):
                    return False
                progress = elapsed / dur
                intensity = math.exp(-3.5 * progress) * (1.0 - progress)
                flash_color = (
                    COLOR_INT_CAPTURE_CONFIRM if source.get("is_capture", False) else COLOR_INT_MOVE_CONFIRM
                )
                for f_c, f_r in flash_squares:
                    set_square_leds(f_c, f_r, scale_color(flash_color, intensity))
                return True

            def render_eval_bar(win_chance: float):
                n_white = min(8, max(0, round((win_chance / 100.0) * 8)))
                for r in range(BOARD_ROWS):
                    set_square_leds(7, r, c_eval_white if r < n_white else c_eval_black)

            def render_trace(from_c, from_r, to_c, to_r, square_color, trace_color_val):
                """Renders from/to highlights plus comet trace, handling castling rook paths."""
                castle_rook = get_castle_rook_move(from_c, from_r, to_c, to_r)
                if castle_rook:
                    r_from, r_to = castle_rook
                    set_square_leds(from_c, from_r, square_color)
                    set_square_leds(to_c, to_r, square_color)
                    set_square_leds(r_from[0], r_from[1], square_color)
                    set_square_leds(r_to[0], r_to[1], square_color)
                    king_path = interpolate_move_path(from_c, from_r, to_c, to_r)
                    rook_path = interpolate_move_path(r_from[0], r_from[1], r_to[0], r_to[1])
                    render_castle_trace(king_path, rook_path, now, frame, trace_color=trace_color_val, blend_arrival=True)
                else:
                    set_square_leds(from_c, from_r, square_color)
                    set_square_leds(to_c, to_r, square_color)
                    path = interpolate_move_path(from_c, from_r, to_c, to_r)
                    render_move_trace(path, now, frame, trace_color=trace_color_val, blend_arrival=True)

            # Layer 0: Lifecycle Animation Override (High priority full-board)
            if self.active_animation is not None:
                if self.active_animation.is_active(now):
                    self.active_animation.render(now, frame)
                    flush_frame()
                    return
                else:
                    self.active_animation = None
                    if self.frozen_baselines is not None:
                        settings["baselines"] = [list(col) for col in self.frozen_baselines]
                        clear_baseline_history()
                        self.frozen_baselines = None
                        logger.info("Restored frozen baselines and reset drift window after lifecycle animation.")

            # Layer 0.5: Continuous Seeking / Matchmaking Radar Animation
            if self.game_status == "SEEKING":
                from app.led_animations import render_seeking
                render_seeking(now, frame, {"night_mode": night_mode})
                flush_frame()
                return

            # Layer 0.6: Continuous Analysis Computing Animation
            if self.game_status == "ANALYSIS" and getattr(self, "analysis_is_loading", False):
                render_analysis_computing(now, frame, {"night_mode": night_mode})
                # Apply active arrival flash if active (e.g. from closing gesture)
                if self.arrival_flash and not apply_arrival_flash(self.arrival_flash):
                    self.arrival_flash = None
                flush_frame()
                return

            # Layer 1: Setup / Idle Board Validation & Physical Gesture Overlay
            if self.game_status in ["IDLE", "SETUP", "GAME_OVER"] or (
                self.game_status == "ANALYSIS"
                and getattr(self, "replay_complete", False)
                and not getattr(self, "analysis_web_only", False)
            ):
                self.setup_result = self.setup_validator.validate(self.physical_state)
                setup_result = self.setup_result

                # Check if a White piece is lifted for an opening move in IDLE
                if self.game_status == "IDLE" and self.move_tracker.lifted_square is not None:
                    lifted_c, lifted_r = self.move_tracker.lifted_square
                    set_square_leds(lifted_c, lifted_r, c_piece_lifted)

                    # Get opening book moves for the lifted square if enabled
                    opening_hints_enabled = settings.get("opening_hints_enabled", True)
                    book_targets: dict[tuple[int, int], str] = {}
                    if opening_hints_enabled:
                        book_moves = get_book_moves_for_square(chess.Board(), lifted_c, lifted_r)
                        book_targets = {
                            bm.to_coord: bm.classification for bm in book_moves
                        }

                    for t_c, t_r in self.move_tracker.legal_targets:
                        target_coord = (t_c, t_r)
                        if opening_hints_enabled and target_coord in book_targets:
                            cls = book_targets[target_coord]
                            color_int = COLOR_INT_MINT_EMERALD if cls == "mainline" else COLOR_INT_AZURE
                            set_square_leds(t_c, t_r, color_int)
                        else:
                            set_square_leds(t_c, t_r, c_legal_target)

                    if self.move_tracker.invalid_placement:
                        inv_c, inv_r = self.move_tracker.invalid_placement
                        set_square_leds(inv_c, inv_r, c_invalid_placement)
                elif not setup_result.is_setup_ready:
                    # Missing starting pieces
                    for c, r in setup_result.missing_white + setup_result.missing_black:
                        set_square_leds(c, r, c_setup_missing)
                    # Misplaced pieces
                    for c, r in setup_result.misplaced_pieces:
                        set_square_leds(c, r, c_setup_misplaced)
                elif self.active_animation is None:
                    # Dynamic Gesture Starter Pawns Indication:
                    # Ambient breathing glow on the pawns that initiate physical gestures (e.g. a2, e2, h2)
                    if hasattr(self, "gesture_engine"):
                        starter_indicators = self.gesture_engine.get_starter_indicators(now)
                        for (s_c, s_r), s_color in starter_indicators.items():
                            set_square_leds(s_c, s_r, s_color)

                # Physical Gesture LED Overlay (Armed/Step1/Step2)
                if hasattr(self, "gesture_engine") and self.gesture_engine.is_active:
                    gesture_overlay = self.gesture_engine.get_led_overlay(now)
                    for (g_c, g_r), g_color in gesture_overlay.items():
                        set_square_leds(g_c, g_r, g_color)

            # Layer 2: Playing State Highlights
            elif self.game_status == "PLAYING":
                is_ai = getattr(lichess_engine, "is_ai_game", False)
                coach_ai_only = settings.get("coach_ai_only", True)
                fair_play_active = coach_ai_only and not is_ai
                eval_bar_enabled = settings.get("eval_bar_enabled", True)
                clock_bar_enabled = settings.get("clock_bar_enabled", True)

                raw_clocks = lichess_engine.raw_clocks_ms
                updated_at = lichess_engine.clocks_updated_at
                initial_clocks = lichess_engine.initial_clocks_ms
                clocks_ready = (
                    updated_at is not None
                    and getattr(lichess_engine, "board", None)
                    and all(
                        raw_clocks[c] is not None
                        and initial_clocks[c] is not None
                        and initial_clocks[c] > 0
                        for c in ("white", "black")
                    )
                )

                # 0. Chess Clock Drain Bars (Files a/h) or Live Perimeter Evaluation Bar (File h)
                if clock_bar_enabled and clocks_ready:
                    stm = "white" if lichess_engine.board.turn == chess.WHITE else "black"
                    elapsed = now - updated_at
                    white_total_s = initial_clocks["white"] / 1000.0
                    black_total_s = initial_clocks["black"] / 1000.0
                    white_remaining_s = (
                        max(0.0, raw_clocks["white"] / 1000.0 - elapsed) if stm == "white" else raw_clocks["white"] / 1000.0
                    )
                    black_remaining_s = (
                        max(0.0, raw_clocks["black"] / 1000.0 - elapsed) if stm == "black" else raw_clocks["black"] / 1000.0
                    )
                    render_clock_bar(now, frame, 0, black_remaining_s, black_total_s, c_clock_ok, c_clock_warn, c_clock_crit)
                    render_clock_bar(now, frame, 7, white_remaining_s, white_total_s, c_clock_ok, c_clock_warn, c_clock_crit)
                elif eval_bar_enabled and not fair_play_active and getattr(lichess_engine, "board", None):
                    fen = lichess_engine.board.fen()
                    cached_eval = coach_engine.get_cached_evaluation(fen)
                    win_chance = cached_eval.win_chance if cached_eval else 50.0
                    # File h corresponds to column/file index 7 (Strip 2, row 7)
                    render_eval_bar(win_chance)

                # 1. Opponent Move Indication & Animated Trace
                if self.move_tracker.pending_opponent_move:
                    opp_from = self.move_tracker.pending_opponent_move["from"]
                    opp_to = self.move_tracker.pending_opponent_move["to"]
                    from_c, from_r = opp_from
                    to_c, to_r = opp_to
                    is_capture = bool(self.move_tracker.pending_opponent_move.get("is_capture", False))
                    is_castling = bool(self.move_tracker.pending_opponent_move.get("is_castling", False))
                    rook_from = self.move_tracker.pending_opponent_move.get("rook_from")
                    rook_to = self.move_tracker.pending_opponent_move.get("rook_to")

                    # Harmonized trace & destination color (quiet moves: Sky Azure; captures: Ruby Crimson)
                    trace_color = c_capture_trace if is_capture else c_move_trace

                    if is_castling and rook_from and rook_to:
                        phase = self.move_tracker.pending_opponent_move.get("phase", "king")
                        if phase == "king":
                            # Phase 1: King move indication (e8 -> g8 / e1 -> g1)
                            set_square_leds(from_c, from_r, c_opp_from)
                            set_square_leds(to_c, to_r, trace_color)
                            king_path = interpolate_move_path(from_c, from_r, to_c, to_r)
                            render_move_trace(king_path, now, frame, trace_color=trace_color, blend_arrival=True)
                        else:
                            # Phase 2: Rook move indication (h8 -> f8 / h1 -> f1)
                            set_square_leds(rook_from[0], rook_from[1], c_opp_from)
                            set_square_leds(rook_to[0], rook_to[1], trace_color)
                            rook_path = interpolate_move_path(rook_from[0], rook_from[1], rook_to[0], rook_to[1])
                            render_move_trace(rook_path, now, frame, trace_color=trace_color, blend_arrival=True)
                    else:
                        # Standard Move Trace: Origin square in c_opp_from, Arrival square & comet in trace_color
                        set_square_leds(from_c, from_r, c_opp_from)
                        set_square_leds(to_c, to_r, trace_color)

                        # Interpolate path and render moving comet pulse with arrival flare in trace_color
                        path = interpolate_move_path(from_c, from_r, to_c, to_r)
                        render_move_trace(path, now, frame, trace_color=trace_color, blend_arrival=True)

                # 1.4. Royal Promotion Scepter (Multi-Piece Underpromotion Selector)
                if self.move_tracker.pending_promotion:
                    render_promotion_scepter(
                        now,
                        frame,
                        self.move_tracker.pending_promotion,
                        {"night_mode": night_mode},
                    )

                # 1.5. Player Pending Castling Rook Prompt & Animated Trace
                elif getattr(self.move_tracker, "pending_castling_rook", None):
                    r_from = self.move_tracker.pending_castling_rook["from"]
                    r_to = self.move_tracker.pending_castling_rook["to"]
                    set_square_leds(r_from[0], r_from[1], c_opp_from)
                    set_square_leds(r_to[0], r_to[1], c_opp_to_quiet)
                    rook_path = interpolate_move_path(r_from[0], r_from[1], r_to[0], r_to[1])
                    render_move_trace(rook_path, now, frame, trace_color=c_move_trace, blend_arrival=True)

                # 1.6. Capture in Progress Aura (Opponent piece lifted first)
                if self.move_tracker.pending_capture_target:
                    render_capture_aura(
                        self.move_tracker.pending_capture_target,
                        self.move_tracker.capture_candidate_attackers,
                        now,
                        frame,
                        target_color=c_capture_aura_target,
                        attacker_color=c_capture_aura_attacker,
                    )

                # 2. King in Check Indicator
                if getattr(lichess_engine, "board", None) and lichess_engine.board.is_check():
                    king_sq = lichess_engine.board.king(lichess_engine.board.turn)
                    if king_sq is not None:
                        k_c = chess.square_file(king_sq)
                        k_r = chess.square_rank(king_sq)
                        set_square_leds(k_c, k_r, c_check)

                # 3. Lifted Piece & Legal Target Dots (with Coach / Opening / Resignation Aura)
                if self.move_tracker.lifted_square:
                    l_c, l_r = self.move_tracker.lifted_square
                    if getattr(self.move_tracker, "resignation_armed", False):
                        lifted_elapsed = (
                            now - self.move_tracker.king_lift_time
                            if self.move_tracker.king_lift_time
                            else 3.0
                        )
                        render_resignation_aura(
                            now,
                            frame,
                            (l_c, l_r),
                            lifted_elapsed,
                            {"night_mode": night_mode},
                        )
                    else:
                        set_square_leds(l_c, l_r, c_piece_lifted)
                    coach_hints_enabled = settings.get("coach_hints_enabled", True)
                    opening_hints_enabled = settings.get("opening_hints_enabled", True)
                    coach_active = coach_hints_enabled and not fair_play_active
                    cached_eval = (
                        coach_engine.get_cached_evaluation(lichess_engine.board.fen())
                        if (coach_active and getattr(lichess_engine, "board", None))
                        else None
                    )

                    # Cartographer's Path Book Moves lookup for this lifted piece
                    book_moves_map = {}
                    active_playing_board = (
                        self.local_engine.board
                        if (hasattr(self, "local_engine") and self.local_engine.is_active)
                        else getattr(lichess_engine, "board", None)
                    )
                    if opening_hints_enabled and active_playing_board and self.current_opening and not self.current_opening.out_of_book:
                        candidate_book_moves = get_book_moves_for_square(active_playing_board, l_c, l_r)
                        for bm in candidate_book_moves:
                            book_moves_map[bm.to_coord] = bm

                    for t_c, t_r in self.move_tracker.legal_targets:
                        is_cap = (t_c, t_r) in getattr(self.move_tracker, "legal_captures", [])
                        target_col = c_legal_capture if is_cap else c_legal_target

                        # Priority 1: Coach evaluation hints
                        if coach_active and cached_eval and cached_eval.moves_map:
                            from_sq = chess.square_name(chess.square(l_c, l_r))
                            to_sq = chess.square_name(chess.square(t_c, t_r))
                            uci = f"{from_sq}{to_sq}"
                            move_analysis = cached_eval.moves_map.get(uci) or cached_eval.moves_map.get(f"{uci}q")
                            if move_analysis:
                                if move_analysis.classification == MoveQuality.BEST:
                                    target_col = c_move_best
                                elif move_analysis.classification == MoveQuality.GOOD:
                                    target_col = c_move_good
                                elif move_analysis.classification == MoveQuality.INACCURACY:
                                    target_col = c_move_inacc
                                else:
                                    target_col = c_move_blunder
                        # Priority 2: Cartographer's Path opening book hints
                        elif opening_hints_enabled and (t_c, t_r) in book_moves_map:
                            bm = book_moves_map[(t_c, t_r)]
                            if bm.classification == "mainline":
                                target_col = c_mint_emerald
                            elif bm.classification == "sideline":
                                target_col = c_azure

                        set_square_leds(t_c, t_r, target_col)

                # 4. Invalid Placement Indicator
                if self.move_tracker.invalid_placement:
                    inv_c, inv_r = self.move_tracker.invalid_placement
                    set_square_leds(inv_c, inv_r, c_illegal)

                # 5. Live State Guardrail Mismatch Indicator (Alert pulses for missing/unexpected pieces)
                if self.guardrail_result and not self.guardrail_result.is_synchronized:
                    render_guardrail_mismatch(
                        self.guardrail_result.missing_pieces,
                        self.guardrail_result.unexpected_pieces,
                        now,
                        frame,
                        missing_color=c_guardrail_missing,
                        unexpected_color=c_guardrail_unexp,
                    )

                # 6. Active Player Turn Ambient Indicator & First-Move Color Persistence Anchor
                if getattr(lichess_engine, "board", None) and not lichess_engine.board.is_check():
                    active_turn = lichess_engine.board.turn
                    my_col_str = str(getattr(lichess_engine, "my_color", "") or "").lower()
                    my_chess_color = chess.WHITE if my_col_str == "white" else (chess.BLACK if my_col_str == "black" else None)
                    move_count = len(lichess_engine.board.move_stack)

                    # Persistent player color reminder: active until player plays their first move
                    # (For White: move_count == 0; For Black: move_count <= 1 until Black plays move 1 at ply 2)
                    first_move_pending = False
                    if my_chess_color is not None:
                        if my_chess_color == chess.WHITE and move_count == 0:
                            first_move_pending = True
                        elif my_chess_color == chess.BLACK and move_count <= 1:
                            first_move_pending = True

                    if first_move_pending and my_chess_color is not None:
                        # Illuminate persistent player color reminder on player's royal thrones
                        my_king_sq = lichess_engine.board.king(my_chess_color)
                        if my_king_sq is not None:
                            k_c = chess.square_file(my_king_sq)
                            k_r = chess.square_rank(my_king_sq)
                            q_c = 3  # Queen file d (d1 or d8)
                            q_r = k_r
                            p_col = (
                                (COLOR_INT_START_WHITE_PRIMARY if not night_mode else COLOR_INT_NIGHT_TURN_WHITE)
                                if my_chess_color == chess.WHITE
                                else (COLOR_INT_NIGHT_START_BLACK_PRIMARY if night_mode else COLOR_INT_START_BLACK_PRIMARY)
                            )
                            p_pulse = math.sin(now * 3.0) * 0.5 + 0.5
                            p_intensity = 0.28 + 0.14 * p_pulse
                            if self.move_tracker.lifted_square != (k_c, k_r):
                                set_square_leds(k_c, k_r, scale_color(p_col, p_intensity))
                            if self.move_tracker.lifted_square != (q_c, q_r):
                                set_square_leds(q_c, q_r, scale_color(p_col, p_intensity * 0.75))
                    else:
                        active_king_sq = lichess_engine.board.king(active_turn)
                        if active_king_sq is not None:
                            ak_c = chess.square_file(active_king_sq)
                            ak_r = chess.square_rank(active_king_sq)
                            if self.move_tracker.lifted_square != (ak_c, ak_r):
                                turn_col = c_turn_white if active_turn == chess.WHITE else c_turn_black
                                turn_pulse = math.sin(now * 2.5) * 0.5 + 0.5
                                turn_intensity = 0.16 + 0.10 * turn_pulse
                                set_square_leds(ak_c, ak_r, scale_color(turn_col, turn_intensity))

                # 7. Opponent Disconnected Warning Beacon & Victory Claim Countdown Gauge
                if getattr(lichess_engine, "opponent_gone", None) and lichess_engine.opponent_gone.get("gone"):
                    opp_color = chess.BLACK if (getattr(lichess_engine, "my_color", "white") or "white").lower() == "white" else chess.WHITE
                    opp_king = lichess_engine.board.king(opp_color) if getattr(lichess_engine, "board", None) else None
                    opp_king_coord = (chess.square_file(opp_king), chess.square_rank(opp_king)) if opp_king is not None else None
                    render_opponent_disconnected(
                        now,
                        frame,
                        lichess_engine.opponent_gone,
                        getattr(lichess_engine, "my_color", "white"),
                        opp_king_coord,
                    )

            # Layer 2.2: Analysis & Training State Highlights
            # (web-only sessions keep the physical board completely dark)
            elif self.game_status == "ANALYSIS" and not getattr(self, "analysis_web_only", False):
                eval_bar_enabled = settings.get("eval_bar_enabled", True)
                # 0. Live Perimeter Evaluation Bar (File h, Strip 2)
                if eval_bar_enabled and self.analysis_evaluations:
                    curr_eval = None
                    if self.analysis_anchor_coord:
                        curr_eval = coach_engine.get_cached_evaluation(self.analysis_active_board.fen())
                    elif 0 <= self.analysis_current_ply < len(self.analysis_evaluations):
                        curr_eval = self.analysis_evaluations[self.analysis_current_ply]

                    if curr_eval:
                        win_chance = curr_eval.get("win_chance", 50.0) if isinstance(curr_eval, dict) else curr_eval.win_chance
                        render_eval_bar(win_chance)

                # 1. Sub-mode specific LED illumination
                if self.analysis_submode == "review":
                    # If player is in the middle of executing a physical castling move, prompt the Rook move
                    if getattr(self.move_tracker, "pending_castling_rook", None):
                        r_from = self.move_tracker.pending_castling_rook["from"]
                        r_to = self.move_tracker.pending_castling_rook["to"]
                        set_square_leds(r_from[0], r_from[1], c_opp_from)
                        set_square_leds(r_to[0], r_to[1], c_opp_to_quiet)
                        rook_path = interpolate_move_path(r_from[0], r_from[1], r_to[0], r_to[1])
                        render_move_trace(rook_path, now, frame, trace_color=c_move_trace, blend_arrival=True)
                    elif self.analysis_anchor_coord is not None:
                        # When diverged from main game:
                        # 1) 4 Corner rooks beacon: subtle 0.5Hz breathing glow in Royal Violet
                        beacon_pulse = math.sin(now * math.pi) * 0.5 + 0.5
                        beacon_color = scale_color(c_royal_violet, 0.20 + 0.40 * beacon_pulse)
                        for corner_c, corner_r in [(0, 0), (7, 0), (0, 7), (7, 7)]:
                            set_square_leds(corner_c, corner_r, beacon_color)

                        # 2) Anchor square illuminated in Royal Violet
                        set_square_leds(self.analysis_anchor_coord[0], self.analysis_anchor_coord[1], c_royal_violet)

                        # 3) Engine best reply for diverged position if available
                        cached_branch = coach_engine.get_cached_evaluation(self.analysis_active_board.fen())
                        if cached_branch and cached_branch.best_move and len(cached_branch.best_move) >= 4:
                            bm = cached_branch.best_move
                            bm_from_c = ord(bm[0]) - ord('a')
                            bm_from_r = int(bm[1]) - 1
                            bm_to_c = ord(bm[2]) - ord('a')
                            bm_to_r = int(bm[3]) - 1
                            if 0 <= bm_from_c < 8 and 0 <= bm_from_r < 8 and 0 <= bm_to_c < 8 and 0 <= bm_to_r < 8:
                                bm_pulse = math.sin(now * 3.0) * 0.5 + 0.5
                                bm_color = scale_color(c_move_best, 0.40 + 0.60 * bm_pulse)
                                set_square_leds(bm_from_c, bm_from_r, bm_color)
                                set_square_leds(bm_to_c, bm_to_r, bm_color)
                                bm_path = interpolate_move_path(bm_from_c, bm_from_r, bm_to_c, bm_to_r)
                                render_move_trace(bm_path, now, frame, trace_color=c_move_best, blend_arrival=True)

                        # 4) Step-by-step "path home" guide: pulsing halo on the arrival square of
                        # the last branch move (un-play this next) plus a dim dot on its origin.
                        if self.analysis_branch_moves:
                            c_return_home = COLOR_INT_NIGHT_RETURN_HOME if night_mode else COLOR_INT_RETURN_HOME
                            rh_uci = self.analysis_branch_moves[-1]
                            try:
                                if len(rh_uci) >= 4:
                                    rh_from = (ord(rh_uci[0]) - ord('a'), int(rh_uci[1]) - 1)
                                    rh_to = (ord(rh_uci[2]) - ord('a'), int(rh_uci[3]) - 1)
                                    if all(0 <= v < 8 for v in (*rh_from, *rh_to)):
                                        if rh_from == self.analysis_anchor_coord:
                                            rh_from = rh_to
                                        render_return_home_guide(now, frame, rh_from, rh_to, c_return_home)
                            except (ValueError, TypeError):
                                pass
                    else:
                        # On main game timeline:
                        if 0 <= self.analysis_current_ply < len(self.analysis_game_moves):
                            curr_move = self.analysis_game_moves[self.analysis_current_ply]
                            played_info = (
                                self.analysis_played_analyses[self.analysis_current_ply]
                                if self.analysis_current_ply < len(self.analysis_played_analyses)
                                else {}
                            )
                            pos_eval = (
                                self.analysis_evaluations[self.analysis_current_ply]
                                if self.analysis_current_ply < len(self.analysis_evaluations)
                                else None
                            )

                            delta_cp = played_info.get("delta_cp", 0)
                            classification = played_info.get("classification", "")
                            if not classification:
                                if delta_cp <= TIER_BEST_MAX_LOSS:
                                    classification = "best"
                                elif delta_cp <= TIER_GOOD_MAX_LOSS:
                                    classification = "good"
                                elif delta_cp <= TIER_INACCURACY_MAX_LOSS:
                                    classification = "inaccuracy"
                                else:
                                    classification = "blunder"

                            if len(curr_move) >= 4:
                                f_c = ord(curr_move[0]) - ord('a')
                                f_r = int(curr_move[1]) - 1
                                t_c = ord(curr_move[2]) - ord('a')
                                t_r = int(curr_move[3]) - 1

                                # Rule A: within GOOD tier or classification in ("best", "good")
                                is_rule_a = (delta_cp <= TIER_GOOD_MAX_LOSS) or (classification in ("best", "good"))

                                if is_rule_a:
                                    # Best (within BEST tier or classification == "best"): Mint Emerald
                                    # Good (BEST < delta <= GOOD tier or classification == "good"): Cyan Azure
                                    if delta_cp <= TIER_BEST_MAX_LOSS or classification == "best":
                                        trace_col = c_mint_emerald
                                    else:
                                        trace_col = c_azure
                                    render_trace(f_c, f_r, t_c, t_r, trace_col, trace_col)
                                    # Clean board: Do NOT suggest or show any alternative moves
                                else:
                                    # Rule B: delta_cp > 60 or classification in ("inaccuracy", "blunder")
                                    if classification == "inaccuracy" or (
                                        delta_cp <= TIER_INACCURACY_MAX_LOSS and classification != "blunder"
                                    ):
                                        mistake_col = c_move_inacc
                                    else:
                                        mistake_col = c_move_blunder

                                    # Animate played move trajectory in mistake color
                                    render_trace(f_c, f_r, t_c, t_r, mistake_col, mistake_col)

                                    # ALSO suggest the engine's best move:
                                    best_m = played_info.get("best_move")
                                    if not best_m and pos_eval:
                                        best_m = pos_eval.get("best_move") if isinstance(pos_eval, dict) else getattr(pos_eval, "best_move", None)

                                    if best_m and len(best_m) >= 4 and best_m.lower() != curr_move.lower():
                                        bm_f_c = ord(best_m[0]) - ord('a')
                                        bm_f_r = int(best_m[1]) - 1
                                        bm_t_c = ord(best_m[2]) - ord('a')
                                        bm_t_r = int(best_m[3]) - 1

                                        if 0 <= bm_f_c < 8 and 0 <= bm_f_r < 8 and 0 <= bm_t_c < 8 and 0 <= bm_t_r < 8:
                                            # Start & arrival squares illuminated with breathing Emerald Green
                                            breath_pulse = math.sin(now * 3.0) * 0.5 + 0.5
                                            bm_breath_col = scale_color(c_move_best, 0.40 + 0.60 * breath_pulse)
                                            set_square_leds(bm_f_c, bm_f_r, bm_breath_col)
                                            set_square_leds(bm_t_c, bm_t_r, bm_breath_col)

                                            # Best move path animated via render_move_trace in Emerald Green
                                            # with phase offset (half period) so user clearly sees both trajectories interleaved
                                            bm_path = interpolate_move_path(bm_f_c, bm_f_r, bm_t_c, bm_t_r)
                                            render_move_trace(
                                                bm_path,
                                                now + MOVE_TRACE_PERIOD_S * 0.5,
                                                frame,
                                                trace_color=c_move_best,
                                                blend_arrival=True,
                                            )

                elif self.analysis_submode == "blunder_drill":
                    if 0 <= self.analysis_blunder_index < len(self.analysis_blunders):
                        blunder = self.analysis_blunders[self.analysis_blunder_index]
                        if self.analysis_blunder_hint_active:
                            bm = blunder.get("best_move", "")
                            if len(bm) >= 4:
                                bm_f = (ord(bm[0]) - ord('a'), int(bm[1]) - 1)
                                set_square_leds(bm_f[0], bm_f[1], c_mint_emerald)

                elif self.analysis_submode in ("replay_learn", "replay_recall"):
                    # Side-to-move indicator: gentle pulse on the King square
                    active_turn = self.analysis_active_board.turn
                    k_sq = self.analysis_active_board.king(active_turn)
                    if k_sq is not None:
                        k_c, k_r = chess.square_file(k_sq), chess.square_rank(k_sq)
                        turn_col = c_turn_white if active_turn == chess.WHITE else c_turn_black
                        turn_pulse = math.sin(now * 3.0) * 0.5 + 0.5
                        set_square_leds(k_c, k_r, scale_color(turn_col, 0.25 + 0.25 * turn_pulse))

                    if self.analysis_anchor_coord is not None:
                        # Diverged from the game line (learn or recall): violet anchor
                        # square + "path home" guide for un-playing the wrong move.
                        set_square_leds(self.analysis_anchor_coord[0], self.analysis_anchor_coord[1], c_royal_violet)
                        if self.analysis_branch_moves:
                            c_return_home = COLOR_INT_NIGHT_RETURN_HOME if night_mode else COLOR_INT_RETURN_HOME
                            rh_uci = self.analysis_branch_moves[-1]
                            try:
                                if len(rh_uci) >= 4:
                                    rh_from = (ord(rh_uci[0]) - ord('a'), int(rh_uci[1]) - 1)
                                    rh_to = (ord(rh_uci[2]) - ord('a'), int(rh_uci[3]) - 1)
                                    if all(0 <= v < 8 for v in (*rh_from, *rh_to)):
                                        if rh_from == self.analysis_anchor_coord:
                                            rh_from = rh_to
                                        render_return_home_guide(now, frame, rh_from, rh_to, c_return_home)
                            except (ValueError, TypeError):
                                pass
                    elif self.analysis_submode == "replay_learn":
                        # Learn phase: guide with the next Grandmaster move trace,
                        # staged like in-game castling (king move first, rook prompt second).
                        pending_rook = getattr(self.move_tracker, "pending_castling_rook", None)
                        if pending_rook:
                            # Stage 2: king placed on its castle destination -> prompt the rook move
                            r_from = pending_rook.get("from")
                            r_to = pending_rook.get("to")
                            if r_from and r_to:
                                set_square_leds(r_from[0], r_from[1], c_opp_from)
                                set_square_leds(r_to[0], r_to[1], c_move_trace)
                                rook_path = interpolate_move_path(r_from[0], r_from[1], r_to[0], r_to[1])
                                render_move_trace(rook_path, now, frame, trace_color=c_move_trace, blend_arrival=True)
                        elif 0 <= self.analysis_current_ply < len(self.analysis_game_moves):
                            curr_move = self.analysis_game_moves[self.analysis_current_ply]
                            if len(curr_move) >= 4:
                                g_f_c = ord(curr_move[0]) - ord('a')
                                g_f_r = int(curr_move[1]) - 1
                                g_t_c = ord(curr_move[2]) - ord('a')
                                g_t_r = int(curr_move[3]) - 1
                                if all(0 <= v < 8 for v in (g_f_c, g_f_r, g_t_c, g_t_r)):
                                    castle_rook = get_castle_rook_move(g_f_c, g_f_r, g_t_c, g_t_r)
                                    if castle_rook:
                                        # Stage 1: show ONLY the king's move; the rook prompt
                                        # appears once the king reaches its castle square.
                                        set_square_leds(g_f_c, g_f_r, c_move_trace)
                                        set_square_leds(g_t_c, g_t_r, c_move_trace)
                                        king_path = interpolate_move_path(g_f_c, g_f_r, g_t_c, g_t_r)
                                        render_move_trace(king_path, now, frame, trace_color=c_move_trace, blend_arrival=True)
                                    else:
                                        render_trace(g_f_c, g_f_r, g_t_c, g_t_r, c_move_trace, c_move_trace)
                    elif self.replay_reveal_uci and len(self.replay_reveal_uci) >= 4:
                        # Recall phase reveal: correct continuation after a mistake (amber trace)
                        rv = self.replay_reveal_uci
                        r_f_c = ord(rv[0]) - ord('a')
                        r_f_r = int(rv[1]) - 1
                        r_t_c = ord(rv[2]) - ord('a')
                        r_t_r = int(rv[3]) - 1
                        if all(0 <= v < 8 for v in (r_f_c, r_f_r, r_t_c, r_t_r)):
                            reveal_pulse = math.sin(now * 4.0) * 0.5 + 0.5
                            reveal_col = scale_color(c_move_inacc, 0.45 + 0.55 * reveal_pulse)
                            render_trace(r_f_c, r_f_r, r_t_c, r_t_r, reveal_col, reveal_col)

            # Layer 2.5: Active Arrival Confirmation Flash (snappy exponential decay on arrival square(s))
            for flash_source in (self.arrival_flash, getattr(self.move_tracker, "arrival_flash", None)):
                if flash_source:
                    if not apply_arrival_flash(flash_source):
                        if self.arrival_flash is flash_source:
                            self.arrival_flash = None
                        if hasattr(self, "move_tracker") and self.move_tracker.arrival_flash is flash_source:
                            self.move_tracker.arrival_flash = None

            # Layer 2.6: Cartographer's Path Uncharted Novelty Flare
            if self.active_novelty_flare:
                elapsed_flare = now - self.active_novelty_flare["start_time"]
                dur_flare = self.active_novelty_flare.get("duration", ANIM_UNCHARTED_NOVELTY_DURATION_S)
                if elapsed_flare < dur_flare:
                    flare_p = elapsed_flare / max(0.001, dur_flare)
                    render_uncharted_novelty(flare_p, frame, self.active_novelty_flare["coord"], {"night_mode": night_mode})
                else:
                    self.active_novelty_flare = None

            # Layer 3: Custom Diagnostic Trace Override
            if self.custom_trace_path and len(self.custom_trace_path) >= 2:
                t_from_c, t_from_r = self.custom_trace_path[0]
                t_to_c, t_to_r = self.custom_trace_path[-1]
                target_color = COLOR_INT_OPPONENT_CAPTURE if self.custom_trace_is_capture else COLOR_INT_OPPONENT_TO
                trace_color = COLOR_INT_CAPTURE_TRACE if self.custom_trace_is_capture else COLOR_INT_MOVE_TRACE

                castle_rook = get_castle_rook_move(t_from_c, t_from_r, t_to_c, t_to_r)
                if castle_rook:
                    r_from, r_to = castle_rook
                    set_square_leds(t_from_c, t_from_r, COLOR_INT_OPPONENT_FROM)
                    set_square_leds(t_to_c, t_to_r, target_color)
                    set_square_leds(r_from[0], r_from[1], COLOR_INT_OPPONENT_FROM)
                    set_square_leds(r_to[0], r_to[1], target_color)
                    rook_path = interpolate_move_path(r_from[0], r_from[1], r_to[0], r_to[1])
                    render_castle_trace(self.custom_trace_path, rook_path, now, frame, trace_color=trace_color, blend_arrival=True)
                else:
                    set_square_leds(t_from_c, t_from_r, COLOR_INT_OPPONENT_FROM)
                    set_square_leds(t_to_c, t_to_r, target_color)
                    render_move_trace(self.custom_trace_path, now, frame, trace_color=trace_color, blend_arrival=True)

            flush_frame()
        except Exception as e:
            logger.error(f"Error in physical LED update: {e}")

    async def run_led_test(self):
        if not self.strip or self.led_test_active:
            return

        self.led_test_active = True
        if self.frozen_baselines is None and "baselines" in settings:
            self.frozen_baselines = [list(col) for col in settings["baselines"]]
        logger.info("Starting sequential LED strip test (baselines frozen)...")
        try:
            for idx in range(NUM_LEDS):
                self.strip.setPixelColor(idx, Color(0, 0, 0))
            self.strip.show()
            await asyncio.sleep(0.2)

            for idx in range(NUM_LEDS):
                self.testing_led_index = idx
                self.strip.setPixelColor(idx, Color(204, 64, 0))  # Orange
                self.strip.show()
                await asyncio.sleep(0.03)
                self.strip.setPixelColor(idx, Color(0, 0, 0))
                self.strip.show()
                await asyncio.sleep(0.005)
        except Exception as e:
            logger.error(f"Error during LED test: {e}")
        finally:
            self.led_test_active = False
            self.testing_led_index = -1
            if self.frozen_baselines is not None and self.active_animation is None:
                settings["baselines"] = [list(col) for col in self.frozen_baselines]
                clear_baseline_history()
                self.frozen_baselines = None
                logger.info("Restored frozen baselines after LED test.")
            logger.info("Sequential LED strip test completed.")

    def clear_all_leds(self):
        """Forces all physical LEDs off and clears any active animation, custom trace, or arrival flash."""
        self.arrival_flash = None
        if hasattr(self, "move_tracker") and self.move_tracker:
            self.move_tracker.arrival_flash = None
            self.move_tracker.pending_castling_rook = None
        if self.active_animation is not None and self.frozen_baselines is not None:
            settings["baselines"] = [list(col) for col in self.frozen_baselines]
            clear_baseline_history()
            self.frozen_baselines = None
        self.active_animation = None
        self.custom_trace_path = None
        self.custom_trace_is_capture = False
        if self.strip:
            try:
                all_leds_off(self.strip)
                logger.info("Forced all LEDs off.")
                return True
            except Exception as e:
                logger.error(f"Error clearing LEDs: {e}")
                return False
        return True

    def _broadcast_digest(self, diag_info):
        """Cheap change signature of everything the WebSocket payload exposes."""
        mt = self.move_tracker
        opp_gone = getattr(lichess_engine, "opponent_gone", None) or {}
        local_active = hasattr(self, "local_engine") and self.local_engine.is_active
        eval_board = self.local_engine.board if local_active else getattr(lichess_engine, "board", None)
        eval_res = (
            coach_engine.get_cached_evaluation(eval_board.fen())
            if (self.game_status == "PLAYING" and eval_board)
            else None
        )
        return (
            self.game_status,
            self.virtual_only,
            tuple(map(tuple, self.physical_state)),
            id(self.digital_state),
            str(self.clocks.get("white")),
            str(self.clocks.get("black")),
            self.local_engine.my_color if local_active else lichess_engine.my_color,
            getattr(lichess_engine, "is_ai_game", False),
            getattr(lichess_engine, "game_status", None),
            local_active,
            getattr(self.local_engine, "game_id", None) if hasattr(self, "local_engine") else None,
            getattr(self.local_engine, "winner", None) if hasattr(self, "local_engine") else None,
            self.can_start_local_game,
            diag_info["status"],
            diag_info["timeouts"],
            mt.lifted_square,
            len(mt.legal_targets),
            bool(mt.pending_opponent_move),
            bool(mt.pending_castling_rook),
            bool(mt.pending_capture_target),
            bool(mt.invalid_placement),
            bool(mt.in_flight_move),
            bool(mt.pending_promotion),
            None if mt.arrival_flash is None else mt.arrival_flash["start_time"],
            None if self.arrival_flash is None else self.arrival_flash["start_time"],
            id(self.active_animation) if self.active_animation is not None else None,
            self.analysis_current_ply if self.game_status == "ANALYSIS" else 0,
            self.analysis_is_loading if self.game_status == "ANALYSIS" else False,
            len(self.analysis_branch_moves),
            self.analysis_submode if self.game_status == "ANALYSIS" else "",
            getattr(self, "replay_complete", False) if self.game_status == "ANALYSIS" else False,
            self.analysis_active_board.fen() if self.game_status == "ANALYSIS" else "",
            id(coach_engine.get_cached_lines(self.analysis_active_board.fen())) if self.game_status == "ANALYSIS" else 0,
            opp_gone.get("gone", False),
            opp_gone.get("claim_win_in", 0),
            None if eval_res is None else (eval_res.score_cp, eval_res.mate, eval_res.win_chance),
            getattr(self.gesture_engine, "is_active", False) if hasattr(self, "gesture_engine") else False,
            self.current_opening.name if self.current_opening else "",
            self.current_opening.out_of_book if self.current_opening else False,
        )

    async def update_loop(self, broadcast_callback, clients_provider=None):
        """Background task to poll hardware/digital board and broadcast state.

        broadcasts are event-driven: the full payload is sent whenever anything in
        _broadcast_digest changes, plus a heartbeat at most every BROADCAST_HEARTBEAT_S.
        Payload construction is skipped entirely when no WebSocket clients exist.
        """
        raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
        stable_count = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
        diag_info = {"status": "NO_HARDWARE", "last_raw_line": "", "timeouts": 0, "errors": 0}

        last_digest = None
        last_broadcast_mono = 0.0

        logger.info("Starting background state update loop.")

        try:
            while True:
                try:
                    # Rebuild debounce buffers after a calibration reset them from another thread
                    if self._calibration_reset_pending:
                        self._calibration_reset_pending = False
                        for c in range(BOARD_COLS):
                            for r in range(BOARD_ROWS):
                                raw_state[c][r] = 0
                                stable_count[c][r] = 0

                    # 1. Physical Hardware Scan (skip if in virtual-only mode)
                    if self.virtual_only:
                        diag_info = {
                            "status": "VIRTUAL_ONLY",
                            "last_raw_line": "VIRTUAL_ONLY",
                            "timeouts": 0,
                            "errors": 0,
                        }
                    elif self.ser and self.h:
                        now_ts = time.time()
                        is_animating = bool(
                            (self.active_animation is not None and self.active_animation.is_active(now_ts))
                            or self.led_test_active
                        )
                        is_piece_moving = bool(
                            self.move_tracker.lifted_square is not None
                            or self.move_tracker.in_flight_move is not None
                        )
                        freeze_baseline = is_animating or is_piece_moving
                        raw_matrix, scan_diag = await asyncio.to_thread(self._safe_scan, raw_state, freeze_baseline)
                        self.raw_analog_values = raw_matrix
                        diag_info = scan_diag
                        col_mode = settings.get("col_mode", "auto")
                        manual_col = settings.get("manual_col", 0)

                        # Instantly clear raw state, physical state, and stable counts for inactive columns
                        for c in range(BOARD_COLS):
                            if col_mode == "manual" and c != manual_col:
                                for r in range(BOARD_ROWS):
                                    raw_state[c][r] = 0
                                    self.physical_state[c][r] = 0
                                    stable_count[c][r] = 0

                        # During animations, suppress reading processing to prevent false lifts from voltage transients
                        if not is_animating:
                            debounce_thresh = settings.get("debounce_threshold", 2)
                            apply_debounce(
                                raw_state, self.physical_state, stable_count, debounce_thresh
                            )

                            # Physical Move Tracking during PLAYING state
                            if self.game_status == "PLAYING":
                                if hasattr(self, "local_engine") and self.local_engine.is_active:
                                    self.move_tracker.sync_game(self.local_engine)
                                    move_result = self.move_tracker.process_physical_state(
                                        self.physical_state, self.local_engine
                                    )
                                    if move_result:
                                        from_f, from_r, to_f, to_r, promo = move_result
                                        if promo and str(promo).startswith("resign_"):
                                            resigning_color = str(promo).split("_", 1)[1]
                                            winner = "black" if resigning_color == "white" else "white"
                                            logger.info(
                                                f"Physical resignation gesture triggered in local game for {resigning_color}. Winner: {winner}"
                                            )
                                            self.stop_local_game(winner=winner, reason="resignation")
                                        else:
                                            from_sq = f"{chr(ord('a') + from_f - 1)}{from_r}"
                                            to_sq = f"{chr(ord('a') + to_f - 1)}{to_r}"
                                            uci = f"{from_sq}{to_sq}{promo or ''}"
                                            logger.info(f"Physical local move detected: {uci}")
                                            success = self.local_engine.apply_move(uci)
                                            if success:
                                                self.digital_state = self.local_engine.get_board()
                                                if self.local_engine.is_game_over:
                                                    self._record_last_game_from_local()
                                                    self.game_status = "GAME_OVER"
                                                    if self.local_engine.winner in ("white", "black"):
                                                        self.trigger_animation("GAME_WON")
                                                    else:
                                                        self.trigger_animation("GAME_DRAWN")
                                            else:
                                                logger.warning(f"Illegal physical move rejected by LocalGameEngine: {uci}")
                                                self.move_tracker.clear_in_flight_move()

                                    if getattr(self.local_engine, "board", None):
                                        self.guardrail_result = self.setup_validator.validate_game_state(
                                            self.physical_state,
                                            self.local_engine.board,
                                            self.move_tracker,
                                        )
                                    else:
                                        self.guardrail_result = None
                                else:
                                    self.move_tracker.sync_game(lichess_engine)
                                    move_result = self.move_tracker.process_physical_state(
                                        self.physical_state, lichess_engine
                                    )
                                    if move_result:
                                        from_f, from_r, to_f, to_r, promo = move_result
                                        if promo and str(promo).startswith("resign_"):
                                            resigning_color = str(promo).split("_", 1)[1]
                                            logger.info(
                                                f"Physical resignation gesture triggered in Lichess game for {resigning_color}."
                                            )
                                            self._spawn_task(lichess_engine.resign(self))
                                        else:
                                            logger.info(
                                                f"Physical move detected: ({from_f},{from_r}) -> ({to_f},{to_r}) promo={promo}"
                                            )

                                            async def _dispatch_move_task(f_f, f_r, t_f, t_r, p):
                                                try:
                                                    success = await lichess_engine.make_move(f_f, f_r, t_f, t_r, p)
                                                    if not success:
                                                        logger.warning("Move rejected by Lichess API. Releasing in-flight lock.")
                                                        self.move_tracker.clear_in_flight_move()
                                                except Exception as err:
                                                    logger.error(f"Unexpected error dispatching move: {err}")
                                                    self.move_tracker.clear_in_flight_move()

                                            self._spawn_task(_dispatch_move_task(from_f, from_r, to_f, to_r, promo))

                                    # Compute live guardrail synchronization status
                                    if getattr(lichess_engine, "board", None):
                                        self.guardrail_result = self.setup_validator.validate_game_state(
                                            self.physical_state,
                                            lichess_engine.board,
                                            self.move_tracker,
                                        )
                                    else:
                                        self.guardrail_result = None
                            elif self.game_status == "ANALYSIS":
                                # Web-only sessions ignore the physical board entirely:
                                # no reset gate, no move tracking, no guardrail noise.
                                if getattr(self, "analysis_web_only", False):
                                    self.guardrail_result = None
                                else:
                                    # Check physical starting position setup readiness
                                    setup_res = self.setup_validator.validate(self.physical_state)
                                    self.setup_result = setup_res

                                    # If the user puts all pieces back into the standard initial
                                    # starting position after reviewing, conclude Analysis mode.
                                    if not self._try_conclude_analysis_on_board_reset(setup_res):
                                        if not getattr(self, "analysis_is_loading", False):
                                            if self.analysis_current_ply > 0 or len(self.analysis_branch_moves) > 0:
                                                self.analysis_has_advanced = True

                                        # Auto-detect if physical board was restored to anchor position or earlier branch step
                                        if self.analysis_anchor_coord is not None:
                                            self._check_analysis_board_restoration()

                                        # Physical Move Tracking during ANALYSIS mode (skipped when replay is complete and user is resetting pieces)
                                        if not getattr(self, "replay_complete", False):
                                            adapter = AnalysisEngineAdapter(self.analysis_active_board)
                                            move_result = self.move_tracker.process_physical_state(
                                                self.physical_state, adapter
                                            )
                                            if move_result:
                                                from_f, from_r, to_f, to_r, promo = move_result
                                                from_sq = f"{chr(ord('a') + from_f - 1)}{from_r}"
                                                to_sq = f"{chr(ord('a') + to_f - 1)}{to_r}"
                                                uci = f"{from_sq}{to_sq}{promo or ''}"
                                                logger.info(f"Physical analysis move detected: {uci}")
                                                self.handle_analysis_move(uci)

                                        if getattr(self, "analysis_active_board", None) and not getattr(self, "replay_complete", False):
                                            self.guardrail_result = self.setup_validator.validate_game_state(
                                                self.physical_state,
                                                self.analysis_active_board,
                                                self.move_tracker,
                                            )
                                        else:
                                            self.guardrail_result = None
                            else:
                                self.setup_result = self.setup_validator.validate(self.physical_state)

                                # If in GAME_OVER and user restores starting 32-piece layout, transition cleanly to IDLE
                                if self.game_status == "GAME_OVER" and self.setup_result.is_setup_ready:
                                    logger.info("Board restored to standard starting setup from GAME_OVER. Resetting to IDLE.")
                                    if hasattr(self, "local_engine"):
                                        self.local_engine.reset()
                                    self.game_status = "IDLE"
                                    self.move_tracker.reset(self.physical_state)
                                    if hasattr(self, "gesture_engine"):
                                        self.gesture_engine.reset()

                                # Physical gesture evaluation during IDLE / GAME_OVER
                                completed_gestures: list[str] = []
                                if hasattr(self, "gesture_engine"):
                                    completed_gestures = self.gesture_engine.evaluate(
                                        self.physical_state,
                                        self.game_status,
                                        is_setup_ready=self.setup_result.is_setup_ready,
                                    )

                                # Setup Ready Edge Detection & Animation Triggering
                                self._process_setup_ready_edge(
                                    self.setup_result.is_setup_ready, completed_gestures
                                )

                                # Auto-Start Local Game Check when board is armed and ready in IDLE
                                gesture_in_progress = bool(
                                    hasattr(self, "gesture_engine")
                                    and self.gesture_engine.is_active
                                    and self.gesture_engine.active_gesture
                                    and self.gesture_engine.active_gesture.step > 1
                                )
                                if self.game_status == "IDLE" and self.can_start_local_game and not gesture_in_progress:
                                    initial_board = chess.Board()
                                    adapter = AnalysisEngineAdapter(initial_board)
                                    move_result = self.move_tracker.process_physical_state(
                                        self.physical_state, adapter
                                    )
                                    if move_result:
                                        from_f, from_r, to_f, to_r, promo = move_result
                                        from_sq = f"{chr(ord('a') + from_f - 1)}{from_r}"
                                        to_sq = f"{chr(ord('a') + to_f - 1)}{to_r}"
                                        uci = f"{from_sq}{to_sq}{promo or ''}"
                                        logger.info(f"White played opening move from IDLE setup: {uci}. Auto-starting local game!")
                                        self.start_local_game()
                                        self.local_engine.apply_move(uci)
                                        self.digital_state = self.local_engine.get_board()
                                        if hasattr(self, "gesture_engine"):
                                            self.gesture_engine.reset()
                                    elif self.move_tracker.lifted_square is None and not self.setup_result.is_setup_ready:
                                        # Only disarm if multiple pieces are missing or board was genuinely cleared
                                        missing_total = (
                                            len(self.setup_result.missing_white)
                                            + len(self.setup_result.missing_black)
                                            + len(self.setup_result.misplaced_pieces)
                                        )
                                        if missing_total > 1:
                                            self.can_start_local_game = False
                                else:
                                    mt = self.move_tracker
                                    has_transient = bool(
                                        mt.lifted_square
                                        or mt.in_flight_move
                                        or mt.pending_opponent_move
                                        or mt.pending_castling_rook
                                        or mt.pending_capture_target
                                        or mt.capture_candidate_attackers
                                        or mt.invalid_placement
                                        or mt.arrival_flash
                                        or mt.legal_targets
                                        or mt.legal_captures
                                    )
                                    if has_transient and not self.can_start_local_game:
                                        mt.reset(self.physical_state)
                                    elif mt.last_physical_state != self.physical_state:
                                        mt.last_physical_state = [row[:] for row in self.physical_state]
                                    self.guardrail_result = None

                            if hasattr(self, "gesture_engine"):
                                if self.game_status not in ["IDLE", "GAME_OVER"]:
                                    if self._prev_gesture_status in ["IDLE", "GAME_OVER"]:
                                        self.gesture_engine.reset()
                                self._prev_gesture_status = self.game_status

                        self._update_leds()
                    else:
                        diag_info = {
                            "status": "DISCONNECTED" if not self.ser else "NO_GPIO",
                            "last_raw_line": "",
                            "timeouts": 16,
                            "errors": 0,
                        }

                    # 2. Digital Board Sync with Lichess Engine, Local Engine, or Analysis Board
                    active_chess_board = None
                    if self.game_status == "PLAYING":
                        if hasattr(self, "local_engine") and self.local_engine.is_active:
                            new_grid = self.local_engine.get_board()
                            if new_grid != self.digital_state:
                                self.digital_state = new_grid
                            self.clocks = ANALYSIS_CLOCKS
                            active_chess_board = self.local_engine.board
                        else:
                            new_grid = lichess_engine.get_board()
                            if new_grid != self.digital_state:
                                self.digital_state = new_grid
                            interp = lichess_engine.get_interpolated_clocks()
                            self.clocks = {
                                "white": format_clock_ms(interp["white"]),
                                "black": format_clock_ms(interp["black"]),
                            }
                            active_chess_board = getattr(lichess_engine, "board", None)
                    elif self.game_status == "ANALYSIS":
                        fen = self.analysis_active_board.fen()
                        if fen != self._analysis_grid_fen:
                            board_grid = [["." for _ in range(BOARD_COLS)] for _ in range(BOARD_ROWS)]
                            for sq in chess.SQUARES:
                                piece = self.analysis_active_board.piece_at(sq)
                                if piece:
                                    f = chess.square_file(sq)
                                    r = chess.square_rank(sq)
                                    board_grid[r][f] = piece.symbol()
                            self.digital_state = board_grid
                            self._analysis_grid_fen = fen
                        self.clocks = ANALYSIS_CLOCKS
                        active_chess_board = self.analysis_active_board
                    elif self.game_status == "GAME_OVER":
                        if hasattr(self, "local_engine") and self.local_engine.game_id:
                            self.digital_state = self.local_engine.get_board()
                            active_chess_board = self.local_engine.board
                        else:
                            self.digital_state = lichess_engine.get_board()
                            active_chess_board = getattr(lichess_engine, "board", None)
                        self.clocks = IDLE_CLOCKS
                    else:
                        self.digital_state = EMPTY_DIGITAL_GRID
                        self.clocks = IDLE_CLOCKS
                        self.current_opening = None

                    # Update Opening Classification & Detect Out-Of-Book Novelty
                    if active_chess_board is not None:
                        new_opening = get_opening_info(active_chess_board)
                        opening_hints_enabled = settings.get("opening_hints_enabled", True)
                        if (
                            opening_hints_enabled
                            and self.current_opening is not None
                            and not self.current_opening.out_of_book
                            and new_opening.out_of_book
                        ):
                            if new_opening.novelty_move and len(new_opening.novelty_move) >= 4:
                                to_c = ord(new_opening.novelty_move[2].lower()) - ord('a')
                                to_r = int(new_opening.novelty_move[3]) - 1
                                if 0 <= to_c < 8 and 0 <= to_r < 8:
                                    self.active_novelty_flare = {
                                        "coord": (to_c, to_r),
                                        "start_time": time.time(),
                                        "duration": ANIM_UNCHARTED_NOVELTY_DURATION_S,
                                    }
                        self.current_opening = new_opening

                    # 3. Coach engine live analysis (drives the eval cache regardless of clients)
                    is_ai = getattr(lichess_engine, "is_ai_game", False)
                    coach_ai_only = settings.get("coach_ai_only", True)
                    fair_play_active = coach_ai_only and not is_ai

                    if not fair_play_active and getattr(lichess_engine, "board", None) and self.game_status == "PLAYING":
                        coach_engine.request_analysis(lichess_engine.board)

                    # 4. Event-driven broadcast: send on any digest change, plus a periodic heartbeat.
                    now_mono = time.monotonic()
                    client_count = clients_provider() if clients_provider else 1
                    if client_count > 0:
                        digest = self._broadcast_digest(diag_info)
                        if digest != last_digest or (now_mono - last_broadcast_mono) >= BROADCAST_HEARTBEAT_S:
                            payload = self._build_broadcast_payload(diag_info)

                            if not fair_play_active and getattr(lichess_engine, "board", None) and self.game_status == "PLAYING":
                                coach_hints_enabled = settings.get("coach_hints_enabled", True)
                                eval_res = coach_engine.get_cached_evaluation(lichess_engine.board.fen())
                                if eval_res:
                                    payload["coach"]["evaluation"] = {
                                        "score_cp": eval_res.score_cp,
                                        "mate": eval_res.mate,
                                        "win_chance": eval_res.win_chance,
                                        "best_move": eval_res.best_move,
                                    }
                                    if self.move_tracker.lifted_square and coach_hints_enabled:
                                        l_c, l_r = self.move_tracker.lifted_square
                                        from_sq = chess.square_name(chess.square(l_c, l_r))
                                        hints = []
                                        for t_c, t_r in self.move_tracker.legal_targets:
                                            to_sq = chess.square_name(chess.square(t_c, t_r))
                                            uci = f"{from_sq}{to_sq}"
                                            m_analysis = eval_res.moves_map.get(uci) or eval_res.moves_map.get(f"{uci}q")
                                            if m_analysis:
                                                hints.append({
                                                    "target_square": [t_c, t_r],
                                                    "uci": uci,
                                                    "tier": m_analysis.classification.value,
                                                    "delta_cp": m_analysis.delta_cp,
                                                })
                                        payload["coach"]["lifted_move_hints"] = hints

                            await broadcast_callback(payload)
                            last_digest = digest
                            last_broadcast_mono = now_mono
                    else:
                        # No listeners: keep only the heartbeat marker fresh
                        last_broadcast_mono = now_mono

                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Error in state update loop tick.")
                    await asyncio.sleep(0.05)

                # Poll interval
                col_mode = settings.get("col_mode", "auto")
                if col_mode == "manual":
                    delay_ms = settings.get("scan_delay", 100)
                else:
                    delay_ms = 10  # Fast 10ms poll interval in auto mode
                await asyncio.sleep(delay_ms / 1000.0)
        except asyncio.CancelledError:
            logger.info("State update loop cancelled.")
            if self.ser:
                self.ser.close()
            if self.h:
                lgpio.gpiochip_close(self.h)
            if self.strip:
                try:
                    all_leds_off(self.strip)
                except Exception as e:
                    logger.error(f"Error turning off LEDs on exit: {e}")


# Global singleton state manager
state_manager = BoardStateManager()
