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

from app.config import (
    ANIM_MOVE_CONFIRM_DURATION_S,
    BAUD_RATE,
    COLOR_NIGHT_TURN_BLACK,
    COLOR_NIGHT_TURN_WHITE,
    COLOR_TURN_BLACK,
    COLOR_TURN_WHITE,
    MOVE_TRACE_PERIOD_S,
    NUM_LEDS,
    SERIAL_PORT,
)
from app.led_helpers import (
    COLOR_INT_AZURE,
    COLOR_INT_BOARD_READY_AMBIENT,
    COLOR_INT_BOARD_READY_PRIMARY,
    COLOR_INT_CAPTURE_AURA_ATTACKER,
    COLOR_INT_CAPTURE_AURA_TARGET,
    COLOR_INT_CAPTURE_CONFIRM,
    COLOR_INT_CAPTURE_TRACE,
    COLOR_INT_CHECK,
    COLOR_INT_DRAW_BLUE,
    COLOR_INT_DRAW_WHITE,
    COLOR_INT_EVAL_BLACK,
    COLOR_INT_EVAL_NEUTRAL,
    COLOR_INT_EVAL_WHITE,
    COLOR_INT_GUARDRAIL_MISSING,
    COLOR_INT_GUARDRAIL_UNEXPECTED,
    COLOR_INT_HIGHLIGHT,
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
    COLOR_INT_NIGHT_BOARD_READY_AMBIENT,
    COLOR_INT_NIGHT_BOARD_READY_PRIMARY,
    COLOR_INT_NIGHT_CAPTURE_AURA_ATTACKER,
    COLOR_INT_NIGHT_CAPTURE_AURA_TARGET,
    COLOR_INT_NIGHT_CAPTURE_TRACE,
    COLOR_INT_NIGHT_CHECK,
    COLOR_INT_NIGHT_EVAL_BLACK,
    COLOR_INT_NIGHT_EVAL_NEUTRAL,
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
    COLOR_INT_NIGHT_ROYAL_VIOLET,
    COLOR_INT_NIGHT_SETUP_MISPLACED,
    COLOR_INT_NIGHT_SETUP_MISSING,
    COLOR_INT_NIGHT_TURN_BLACK,
    COLOR_INT_NIGHT_TURN_WHITE,
    COLOR_INT_OFF,
    COLOR_INT_OPPONENT_CAPTURE,
    COLOR_INT_OPPONENT_DISCONNECTED,
    COLOR_INT_OPPONENT_FROM,
    COLOR_INT_OPPONENT_TO,
    COLOR_INT_PIECE_LIFTED,
    COLOR_INT_ROYAL_VIOLET,
    COLOR_INT_SETUP_MISPLACED,
    COLOR_INT_SETUP_MISSING,
    COLOR_INT_TURN_BLACK,
    COLOR_INT_TURN_WHITE,
    Color,
    all_leds_off,
    get_led_indices,
    init_strip,
)
from app.coach_engine import MoveQuality, coach_engine
from app.led_animations import (
    blend_colors,
    render_castle_trace,
    render_capture_aura,
    render_guardrail_mismatch,
    render_move_trace,
    render_opponent_disconnected,
    scale_color,
)
from app.gesture_engine import (
    PhysicalGestureEngine,
)
from app.gm_games import get_all_gm_games, get_gm_game
from app.lichess_engine import lichess_engine
from app.path_interpolator import get_castle_rook_move, interpolate_move_path
from app.physical_tracker import PhysicalMoveTracker
from app.setup_validator import GameGuardrailResult, SetupResult, SetupValidator
from board_hardware import (
    BOARD_COLS,
    BOARD_ROWS,
    apply_debounce,
    init_mux_pins,
    scan_board,
    settings,
)

logger = logging.getLogger("smart-chess-app.state")


class BoardStateManager:
    def __init__(self):
        self.serial_lock = threading.RLock()
        self.physical_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
        self.raw_analog_values = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
        self.digital_state = [["." for _ in range(8)] for _ in range(8)]
        self.game_status = "IDLE"  # IDLE, SEEKING, PLAYING, GAME_OVER, SETUP, ANALYSIS
        self.virtual_only: bool = False
        self.clocks = {"white": "?", "black": "?"}
        self.highlighted_square = None
        self.led_test_active = False
        self.testing_led_index = -1
        self.is_calibrating: bool = False
        self.active_animation = None  # LifecycleAnimation | None
        self.custom_trace_path = None  # list[tuple[int, int]] | None
        self.custom_trace_is_capture: bool = False
        self.frozen_baselines = None  # Snapshot of baselines preserved during animations
        self.arrival_flash: dict | None = None
        self.guardrail_result: GameGuardrailResult | None = None

        # Analysis & Training Mode State
        self.analysis_submode: str = "review"  # "review" | "blunder_drill" | "gm_relive"
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
        self.analysis_gm_score: int = 0
        self.analysis_gm_guesses: list[dict] = []
        self.analysis_is_loading: bool = False
        self.analysis_has_advanced: bool = False
        # Last game metadata for post-game analysis recall
        self.last_game_moves: list[str] = []
        self.last_game_id: str | None = None
        self.last_game_metadata: dict[str, Any] = {}

        # Setup verification, move tracking, and physical gesture subsystems
        self.setup_validator = SetupValidator()
        self.move_tracker = PhysicalMoveTracker()
        self.gesture_engine = PhysicalGestureEngine(state_manager=self)
        self.setup_result: SetupResult = self.setup_validator.validate(self.physical_state)
        self.prev_setup_ready: bool = False

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

    def trigger_animation(self, name: str, params: dict | None = None) -> bool:
        """
        Triggers a procedural full-board lifecycle animation.
        Supported names: 'GAME_STARTED', 'GAME_WON', 'GAME_LOST', 'GAME_DRAWN'.
        Freezes current analog baselines to protect them from voltage drop transients.
        """
        try:
            from app.led_animations import create_animation
            from board_hardware import settings
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
                return res
            finally:
                self.is_calibrating = False
                if self.strip:
                    try:
                        all_leds_off(self.strip)
                    except Exception as e:
                        logger.error(f"Error turning off LEDs after calibration with pieces: {e}")

    def get_physical_payload(self):
        from board_hardware import get_latest_detection_state, settings
        setup_data = (
            self.setup_result.to_dict()
            if hasattr(self, "setup_result") and self.setup_result
            else self.setup_validator.validate(self.physical_state).to_dict()
        )
        detection = get_latest_detection_state()
        return {
            "rows": BOARD_ROWS,
            "cols": BOARD_COLS,
            "grid": self.physical_state,
            "adc": self.raw_analog_values,
            "baselines": settings.get("baselines"),
            "highlighted_square": self.highlighted_square,
            "led_test_active": self.led_test_active,
            "testing_led_index": self.testing_led_index,
            "disabled_squares": settings.get("disabled_squares", []),
            "virtual_only": self.virtual_only,
            "setup": setup_data,
            "pieces_detected": detection.get("pieces_detected", False),
            "detected_starting_count": detection.get("detected_starting_count", 0),
            "pieces_mode": settings.get("pieces_mode", "auto"),
            "effective_pieces_mode": detection.get("effective_pieces_mode", False),
            "led_intensity": settings.get("led_intensity", 100),
            "night_mode": settings.get("night_mode", False),
            "lifted_square": list(self.move_tracker.lifted_square) if self.move_tracker.lifted_square else None,
            "legal_targets": [list(sq) for sq in self.move_tracker.legal_targets],
            "legal_captures": [list(sq) for sq in self.move_tracker.legal_captures],
            "pending_capture_target": list(self.move_tracker.pending_capture_target) if self.move_tracker.pending_capture_target else None,
            "capture_candidate_attackers": [list(sq) for sq in self.move_tracker.capture_candidate_attackers],
            "guardrail": (
                self.guardrail_result.to_dict()
                if self.guardrail_result is not None
                else None
            ),
            "invalid_placement": list(self.move_tracker.invalid_placement) if self.move_tracker.invalid_placement else None,
            "pending_opponent_move": self.move_tracker.pending_opponent_move,
            "pending_castling_rook": self.move_tracker.pending_castling_rook,
            "arrival_flash": (
                {
                    "square": list(self.arrival_flash["square"] if self.arrival_flash else self.move_tracker.arrival_flash["square"]),
                    "start_time": (self.arrival_flash or self.move_tracker.arrival_flash)["start_time"],
                    "duration": (self.arrival_flash or self.move_tracker.arrival_flash)["duration"],
                    "is_capture": (self.arrival_flash or self.move_tracker.arrival_flash)["is_capture"],
                }
                if (self.arrival_flash or (hasattr(self, "move_tracker") and self.move_tracker and self.move_tracker.arrival_flash))
                else None
            ),
            "active_animation": self.active_animation.name if (self.active_animation and self.active_animation.is_active()) else None,
            "custom_trace_path": [list(sq) for sq in self.custom_trace_path] if self.custom_trace_path else None,
            "in_flight_move": (
                {
                    "from": list(self.move_tracker.in_flight_move["from"]),
                    "to": list(self.move_tracker.in_flight_move["to"]),
                    "uci": self.move_tracker.in_flight_move["uci"],
                    "timestamp": self.move_tracker.in_flight_move.get("timestamp", 0.0),
                }
                if self.move_tracker.in_flight_move
                else None
            ),
            "gesture": self.gesture_engine.get_state_payload() if hasattr(self, "gesture_engine") else None,
        }

    async def start_analysis_mode(
        self, moves_uci: list[str] | None = None, game_id: str | None = None
    ) -> dict[str, Any]:
        """
        Activates Post-Game Analysis mode on the board and starts asynchronous batch evaluation.
        """
        self.game_status = "ANALYSIS"
        self.analysis_submode = "review"
        self.analysis_is_loading = True
        self.analysis_has_advanced = False
        self.analysis_branch_moves = []
        self.analysis_anchor_ply = None
        self.analysis_anchor_coord = None
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
                try:
                    from app.board_hardware import settings
                except ImportError:
                    from board_hardware import settings
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
        except Exception as e:
            logger.error(f"Error in batch game evaluation: {e}")
            self.analysis_evaluations = []
            self.analysis_played_analyses = []
            self.analysis_accuracy = {"white": 100.0, "black": 100.0}
            self.analysis_counts = {}
            self.analysis_blunders = []
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

        return self.get_analysis_payload()

    def reset_analysis_branch(self) -> dict[str, Any]:
        """Snaps back to original game timeline from a virtual branch."""
        restore_ply = self.analysis_anchor_ply if self.analysis_anchor_ply is not None else self.analysis_current_ply
        return self.step_analysis(restore_ply)

    def stop_analysis_mode(self) -> dict[str, Any]:
        """Exits analysis mode and returns to IDLE."""
        self.game_status = "IDLE"
        self.analysis_submode = "review"
        self.analysis_branch_moves = []
        self.analysis_anchor_ply = None
        self.analysis_anchor_coord = None
        return self.get_analysis_payload()

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
        """Starts Guess-the-Move session for a curated Grandmaster masterpiece."""
        game = get_gm_game(game_id)
        if not game:
            return {"error": f"GM game '{game_id}' not found."}

        self.game_status = "ANALYSIS"
        self.analysis_submode = "gm_relive"
        self.analysis_has_advanced = True
        self.analysis_gm_game_id = game_id
        self.analysis_game_moves = list(game.moves)
        self.analysis_current_ply = 0
        self.analysis_gm_score = 0
        self.analysis_gm_guesses = []
        self.analysis_active_board = chess.Board()

        return self.get_analysis_payload()

    def submit_gm_guess(self, uci: str) -> dict[str, Any]:
        """Validates the user's guess against the historical Grandmaster move."""
        if not self.analysis_gm_game_id or self.analysis_current_ply >= len(self.analysis_game_moves):
            return {"error": "No active GM game session."}

        game = get_gm_game(self.analysis_gm_game_id)
        gm_move = self.analysis_game_moves[self.analysis_current_ply]
        ply = self.analysis_current_ply

        if uci.lower() == gm_move.lower():
            points = 100
            commentary = game.annotations.get(ply) if game else "Matched Grandmaster move!"
            self.analysis_gm_score += points
            self.analysis_gm_guesses.append({
                "ply": ply,
                "guess": uci,
                "gm_move": gm_move,
                "match": "exact",
                "points": points,
            })
            if len(uci) >= 4:
                to_c = ord(uci[2]) - ord('a')
                to_r = int(uci[3]) - 1
                self.trigger_arrival_flash(to_c, to_r, is_capture=False, duration=0.8)

            # Advance move
            self.step_analysis(self.analysis_current_ply + 1)
            return {
                "match": "exact",
                "points": points,
                "total_score": self.analysis_gm_score,
                "commentary": commentary,
                "advance": True,
            }
        else:
            self.analysis_gm_guesses.append({
                "ply": ply,
                "guess": uci,
                "gm_move": gm_move,
                "match": "incorrect",
                "points": 0,
            })
            return {
                "match": "incorrect",
                "points": 0,
                "total_score": self.analysis_gm_score,
                "gm_move": gm_move,
                "commentary": f"The Grandmaster played {gm_move}.",
                "advance": False,
            }

    def handle_analysis_move(self, uci: str) -> dict[str, Any]:
        """
        Handles a move played on the board (physical move or web UI action) during ANALYSIS mode.
        If playing the move matching the current game ply, automatically advances to the next ply!
        If playing an alternative move, creates or extends a virtual exploration branch.
        """
        if self.game_status != "ANALYSIS":
            return {"error": "Not in analysis mode"}

        uci = uci.lower().strip()

        # 1. Blunder Drill submode
        if self.analysis_submode == "blunder_drill":
            return self.submit_blunder_attempt(uci)

        # 2. GM Relive submode
        if self.analysis_submode == "gm_relive":
            return self.submit_gm_guess(uci)

        # 3. Game Review submode
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
                self.move_tracker.clear_in_flight_move()
                coach_engine.request_analysis(self.analysis_active_board)
                if len(uci) >= 4:
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

        # Reconstruct the anchor board from the game timeline
        anchor_board = chess.Board()
        target_ply = min(self.analysis_anchor_ply, len(self.analysis_game_moves))
        for idx in range(target_ply):
            try:
                m_str = self.analysis_game_moves[idx].strip()
                if len(m_str) in (4, 5) and m_str[:2].isalnum():
                    anchor_board.push_uci(m_str)
                else:
                    anchor_board.push_san(m_str)
            except Exception:
                pass

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
        if 0 <= self.analysis_current_ply < len(self.analysis_evaluations):
            curr_eval = self.analysis_evaluations[self.analysis_current_ply]

        gm_game = get_gm_game(self.analysis_gm_game_id) if self.analysis_gm_game_id else None

        return {
            "active": self.game_status == "ANALYSIS",
            "submode": self.analysis_submode,
            "is_loading": self.analysis_is_loading,
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
            "gm_score": self.analysis_gm_score,
            "gm_guesses": self.analysis_gm_guesses,
            "fen": self.analysis_active_board.fen(),
        }

    def get_full_state(self, diag_info=None):
        """Constructs a complete serialized snapshot of the full system state."""
        from board_hardware import settings
        is_ai = getattr(lichess_engine, "is_ai_game", False)
        coach_ai_only = settings.get("coach_ai_only", True)
        fair_play_active = coach_ai_only and not is_ai
        coach_hints_enabled = settings.get("coach_hints_enabled", True)
        eval_bar_enabled = settings.get("eval_bar_enabled", True)

        coach_payload = {
            "enabled": bool((coach_hints_enabled or eval_bar_enabled) and not fair_play_active),
            "eval_bar_enabled": bool(eval_bar_enabled and not fair_play_active),
            "coach_hints_enabled": bool(coach_hints_enabled and not fair_play_active),
            "is_ai_game": bool(is_ai),
            "fair_play_active": bool(fair_play_active),
            "evaluation": None,
            "lifted_move_hints": [],
        }
        if diag_info is None:
            diag_info = {
                "status": "OK" if (self.ser or self.virtual_only) else "DISCONNECTED",
                "last_raw_line": "",
                "timeouts": 0,
                "errors": 0,
            }

        return {
            "status": self.game_status,
            "virtual_only": self.virtual_only,
            "physical": self.get_physical_payload(),
            "digital": self.digital_state,
            "clocks": self.clocks,
            "my_color": lichess_engine.my_color,
            "game": lichess_engine.get_game_payload(),
            "coach": coach_payload,
            "gesture": self.gesture_engine.get_state_payload() if hasattr(self, "gesture_engine") else None,
            "analysis": self.get_analysis_payload(),
            "diagnostics": diag_info,
        }

    def get_health_status(self):
        from board_hardware import settings

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
        4. Diagnostic Override: highlighted_square.
        """
        if (
            self.virtual_only
            or not self.strip
            or self.led_test_active
            or self.is_calibrating
        ):
            return

        try:
            from board_hardware import settings
            from app.led_animations import (
                render_analysis_computing,
                render_castle_trace,
                render_move_trace,
            )
            from app.path_interpolator import get_castle_rook_move, interpolate_move_path

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

            # Layer 0: Lifecycle Animation Override (High priority full-board)
            if self.active_animation is not None:
                if self.active_animation.is_active(now):
                    self.active_animation.render(now, frame)
                    for idx, color in enumerate(frame):
                        self.strip.setPixelColor(idx, color)
                    self.strip.show()
                    return
                else:
                    self.active_animation = None
                    if self.frozen_baselines is not None:
                        from board_hardware import settings, clear_baseline_history
                        settings["baselines"] = [list(col) for col in self.frozen_baselines]
                        clear_baseline_history()
                        self.frozen_baselines = None
                        logger.info("Restored frozen baselines and reset drift window after lifecycle animation.")

            # Layer 0.5: Continuous Seeking / Matchmaking Radar Animation
            if self.game_status == "SEEKING":
                from app.led_animations import render_seeking
                render_seeking(now, frame, {"night_mode": night_mode})
                for idx, color in enumerate(frame):
                    self.strip.setPixelColor(idx, color)
                self.strip.show()
                return

            # Layer 1: Setup / Idle Board Validation & Physical Gesture Overlay
            if self.game_status in ["IDLE", "SETUP", "GAME_OVER"]:
                self.setup_result = self.setup_validator.validate(self.physical_state)
                if not self.setup_result.is_setup_ready:
                    # Missing starting pieces
                    for c, r in self.setup_result.missing_white + self.setup_result.missing_black:
                        set_square_leds(c, r, c_setup_missing)
                    # Misplaced pieces
                    for c, r in self.setup_result.misplaced_pieces:
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

                # 0. Live Perimeter Evaluation Bar (File h, Strip 2)
                if eval_bar_enabled and not fair_play_active and getattr(lichess_engine, "board", None):
                    fen = lichess_engine.board.fen()
                    cached_eval = coach_engine.get_cached_evaluation(fen)
                    win_chance = cached_eval.win_chance if cached_eval else 50.0
                    n_white = min(8, max(0, round((win_chance / 100.0) * 8)))
                    # File h corresponds to column/file index 7 (Strip 2, row 7)
                    for r in range(8):
                        eval_col = c_eval_white if r < n_white else c_eval_black
                        set_square_leds(7, r, eval_col)

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

                    target_color = c_opp_to_capture if is_capture else c_opp_to_quiet
                    trace_color = c_capture_trace if is_capture else c_move_trace

                    if is_castling and rook_from and rook_to:
                        # Highlight King from->to and Rook from->to
                        set_square_leds(from_c, from_r, c_opp_from)
                        set_square_leds(to_c, to_r, c_opp_to_quiet)
                        set_square_leds(rook_from[0], rook_from[1], c_opp_from)
                        set_square_leds(rook_to[0], rook_to[1], c_opp_to_quiet)

                        # Choreographed castling trace: King moves 2 squares first, followed by Rook move
                        king_path = interpolate_move_path(from_c, from_r, to_c, to_r)
                        rook_path = interpolate_move_path(rook_from[0], rook_from[1], rook_to[0], rook_to[1])
                        render_castle_trace(king_path, rook_path, now, frame, trace_color=trace_color, blend_arrival=True)
                    else:
                        # Standard Move Trace: Keep start and arrival squares lit
                        set_square_leds(from_c, from_r, c_opp_from)
                        set_square_leds(to_c, to_r, target_color)

                        # Interpolate path and render moving comet pulse with arrival flare
                        path = interpolate_move_path(from_c, from_r, to_c, to_r)
                        render_move_trace(path, now, frame, trace_color=trace_color, blend_arrival=True)

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

                # 3. Lifted Piece & Legal Target Dots (with Coach / Blunder Guard hints)
                if self.move_tracker.lifted_square:
                    l_c, l_r = self.move_tracker.lifted_square
                    set_square_leds(l_c, l_r, c_piece_lifted)
                    coach_hints_enabled = settings.get("coach_hints_enabled", True)
                    coach_active = coach_hints_enabled and not fair_play_active
                    cached_eval = (
                        coach_engine.get_cached_evaluation(lichess_engine.board.fen())
                        if (coach_active and getattr(lichess_engine, "board", None))
                        else None
                    )

                    for t_c, t_r in self.move_tracker.legal_targets:
                        is_cap = (t_c, t_r) in getattr(self.move_tracker, "legal_captures", [])
                        target_col = c_legal_capture if is_cap else c_legal_target

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

                # 6. Active Player Turn Ambient Indicator (Subtle breathing halo on active King)
                if getattr(lichess_engine, "board", None) and not lichess_engine.board.is_check():
                    active_turn = lichess_engine.board.turn
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
            elif self.game_status == "ANALYSIS":
                if getattr(self, "analysis_is_loading", False):
                    render_analysis_computing(now, frame, {"night_mode": night_mode})
                else:
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
                            n_white = min(8, max(0, round((win_chance / 100.0) * 8)))
                            for r in range(8):
                                eval_col = c_eval_white if r < n_white else c_eval_black
                                set_square_leds(7, r, eval_col)

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
                                    if delta_cp <= 15:
                                        classification = "best"
                                    elif delta_cp <= 60:
                                        classification = "good"
                                    elif delta_cp <= 150:
                                        classification = "inaccuracy"
                                    else:
                                        classification = "blunder"

                                if len(curr_move) >= 4:
                                    f_c = ord(curr_move[0]) - ord('a')
                                    f_r = int(curr_move[1]) - 1
                                    t_c = ord(curr_move[2]) - ord('a')
                                    t_r = int(curr_move[3]) - 1

                                    castle_rook = get_castle_rook_move(f_c, f_r, t_c, t_r)

                                    # Rule A: delta_cp <= 60 or classification in ("best", "good")
                                    is_rule_a = (delta_cp <= 60) or (classification in ("best", "good"))

                                    if is_rule_a:
                                        # Best (delta_cp <= 15 or classification == "best"): Mint Emerald
                                        # Good (15 < delta_cp <= 60 or classification == "good"): Cyan Azure
                                        if delta_cp <= 15 or classification == "best":
                                            trace_col = c_mint_emerald
                                        else:
                                            trace_col = c_azure

                                        if castle_rook:
                                            r_from, r_to = castle_rook
                                            set_square_leds(f_c, f_r, trace_col)
                                            set_square_leds(t_c, t_r, trace_col)
                                            set_square_leds(r_from[0], r_from[1], trace_col)
                                            set_square_leds(r_to[0], r_to[1], trace_col)
                                            king_path = interpolate_move_path(f_c, f_r, t_c, t_r)
                                            rook_path = interpolate_move_path(r_from[0], r_from[1], r_to[0], r_to[1])
                                            render_castle_trace(king_path, rook_path, now, frame, trace_color=trace_col, blend_arrival=True)
                                        else:
                                            set_square_leds(f_c, f_r, trace_col)
                                            set_square_leds(t_c, t_r, trace_col)
                                            path = interpolate_move_path(f_c, f_r, t_c, t_r)
                                            render_move_trace(path, now, frame, trace_color=trace_col, blend_arrival=True)
                                        # Clean board: Do NOT suggest or show any alternative moves
                                    else:
                                        # Rule B: delta_cp > 60 or classification in ("inaccuracy", "blunder")
                                        if classification == "inaccuracy" or (delta_cp <= 150 and classification != "blunder"):
                                            mistake_col = c_move_inacc
                                        else:
                                            mistake_col = c_move_blunder

                                        # Animate played move trajectory in mistake color
                                        if castle_rook:
                                            r_from, r_to = castle_rook
                                            set_square_leds(f_c, f_r, mistake_col)
                                            set_square_leds(t_c, t_r, mistake_col)
                                            set_square_leds(r_from[0], r_from[1], mistake_col)
                                            set_square_leds(r_to[0], r_to[1], mistake_col)
                                            king_path = interpolate_move_path(f_c, f_r, t_c, t_r)
                                            rook_path = interpolate_move_path(r_from[0], r_from[1], r_to[0], r_to[1])
                                            render_castle_trace(king_path, rook_path, now, frame, trace_color=mistake_col, blend_arrival=True)
                                        else:
                                            set_square_leds(f_c, f_r, mistake_col)
                                            set_square_leds(t_c, t_r, mistake_col)
                                            path = interpolate_move_path(f_c, f_r, t_c, t_r)
                                            render_move_trace(path, now, frame, trace_color=mistake_col, blend_arrival=True)

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

                    elif self.analysis_submode == "gm_relive":
                        active_turn = self.analysis_active_board.turn
                        k_sq = self.analysis_active_board.king(active_turn)
                        if k_sq is not None:
                            k_c, k_r = chess.square_file(k_sq), chess.square_rank(k_sq)
                            turn_col = c_turn_white if active_turn == chess.WHITE else c_turn_black
                            turn_pulse = math.sin(now * 3.0) * 0.5 + 0.5
                            set_square_leds(k_c, k_r, scale_color(turn_col, 0.25 + 0.25 * turn_pulse))

            # Layer 2.5: Active Arrival Confirmation Flash (snappy exponential decay on arrival square(s))
            for flash_source in (self.arrival_flash, getattr(self.move_tracker, "arrival_flash", None)):
                if flash_source:
                    flash_squares = flash_source.get("squares") or [flash_source["square"]]
                    flash_t0 = flash_source["start_time"]
                    flash_dur = flash_source.get("duration", ANIM_MOVE_CONFIRM_DURATION_S)
                    is_capture = flash_source.get("is_capture", False)
                    elapsed = now - flash_t0
                    if 0 <= elapsed < flash_dur:
                        progress = elapsed / flash_dur
                        intensity = math.exp(-3.5 * progress) * (1.0 - progress)
                        flash_color = COLOR_INT_CAPTURE_CONFIRM if is_capture else COLOR_INT_MOVE_CONFIRM
                        for f_c, f_r in flash_squares:
                            set_square_leds(f_c, f_r, scale_color(flash_color, intensity))
                    else:
                        if self.arrival_flash is flash_source:
                            self.arrival_flash = None
                        if hasattr(self, "move_tracker") and self.move_tracker.arrival_flash is flash_source:
                            self.move_tracker.arrival_flash = None

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

            for idx, color in enumerate(frame):
                self.strip.setPixelColor(idx, color)
            self.strip.show()
        except Exception as e:
            logger.error(f"Error in physical LED update: {e}")

    async def run_led_test(self):
        if not self.strip or self.led_test_active:
            return

        self.led_test_active = True
        from board_hardware import settings, clear_baseline_history
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
        """Forces all physical LEDs off and clears any highlighted square, active animation, custom trace, or arrival flash."""
        self.highlighted_square = None
        self.arrival_flash = None
        if hasattr(self, "move_tracker") and self.move_tracker:
            self.move_tracker.arrival_flash = None
            self.move_tracker.pending_castling_rook = None
        if self.active_animation is not None and self.frozen_baselines is not None:
            from board_hardware import settings, clear_baseline_history
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

    async def update_loop(self, broadcast_callback):
        """Background task to poll hardware/digital board and broadcast state."""
        raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
        stable_count = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
        diag_info = {"status": "NO_HARDWARE", "last_raw_line": "", "timeouts": 0, "errors": 0}

        logger.info("Starting background state update loop.")

        try:
            while True:
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
                            self.move_tracker.sync_game(lichess_engine)
                            move_result = self.move_tracker.process_physical_state(
                                self.physical_state, lichess_engine
                            )
                            if move_result:
                                from_f, from_r, to_f, to_r, promo = move_result
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

                                asyncio.create_task(
                                    _dispatch_move_task(from_f, from_r, to_f, to_r, promo)
                                )

                            # Compute live guardrail synchronization status
                            if getattr(lichess_engine, "board", None):
                                self.guardrail_result = self.setup_validator.validate_game_state(
                                    self.physical_state,
                                    lichess_engine.board,
                                    self.move_tracker,
                                    lichess_engine.my_color,
                                )
                            else:
                                self.guardrail_result = None
                        elif self.game_status == "ANALYSIS":
                            # Check physical starting position setup readiness
                            setup_res = self.setup_validator.validate(self.physical_state)
                            self.setup_result = setup_res

                            # If analysis has been reviewed/progressed (or pieces were moved during analysis)
                            # and the user puts all pieces back into the standard initial starting position:
                            if (
                                getattr(self, "analysis_has_advanced", False)
                                and setup_res.is_setup_ready
                                and getattr(self.move_tracker, "lifted_square", None) is None
                                and getattr(self.move_tracker, "in_flight_move", None) is None
                                and getattr(self.move_tracker, "pending_castling_rook", None) is None
                            ):
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
                                self.move_tracker.reset(self.physical_state)
                                self.guardrail_result = None
                            else:
                                if not setup_res.is_setup_ready:
                                    self.analysis_has_advanced = True

                                # Auto-detect if physical board was restored to anchor position or earlier branch step
                                if self.analysis_anchor_coord is not None:
                                    self._check_analysis_board_restoration()

                                # Physical Move Tracking during ANALYSIS mode
                                class AnalysisEngineAdapter:
                                    def __init__(self, board):
                                        self.board = board
                                        self.my_color = "white" if board.turn == chess.WHITE else "black"
                                        self.game_info = {}

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

                                if getattr(self, "analysis_active_board", None):
                                    self.guardrail_result = self.setup_validator.validate_game_state(
                                        self.physical_state,
                                        self.analysis_active_board,
                                        self.move_tracker,
                                        adapter.my_color,
                                    )
                                else:
                                    self.guardrail_result = None
                        else:
                            self.move_tracker.reset(self.physical_state)
                            self.guardrail_result = None
                            # Physical gesture evaluation during IDLE / GAME_OVER
                            if hasattr(self, "gesture_engine"):
                                self.gesture_engine.evaluate(self.physical_state, self.game_status)

                            # Setup Ready Edge Detection & Animation Triggering
                            if self.game_status in ["IDLE", "SETUP", "GAME_OVER"]:
                                self.setup_result = self.setup_validator.validate(self.physical_state)
                                is_ready = self.setup_result.is_setup_ready

                                if is_ready and not self.prev_setup_ready:
                                    if not (hasattr(self, "gesture_engine") and self.gesture_engine.is_active):
                                        self.trigger_animation(
                                            "BOARD_READY",
                                            {"night_mode": bool(settings.get("night_mode", False))},
                                        )
                                    self.prev_setup_ready = True
                                elif not is_ready and self.prev_setup_ready:
                                    self.prev_setup_ready = False
                                    if self.active_animation and self.active_animation.name in ["BOARD_READY", "SETUP_COMPLETE"]:
                                        self.active_animation = None
                                        if self.frozen_baselines is not None:
                                            from board_hardware import clear_baseline_history
                                            settings["baselines"] = [list(col) for col in self.frozen_baselines]
                                            clear_baseline_history()
                                            self.frozen_baselines = None
                            else:
                                self.prev_setup_ready = False

                        if self.game_status not in ["IDLE", "GAME_OVER"] and hasattr(self, "gesture_engine"):
                            self.gesture_engine.reset()

                    self._update_leds()
                else:
                    diag_info = {
                        "status": "DISCONNECTED" if not self.ser else "NO_GPIO",
                        "last_raw_line": "",
                        "timeouts": 16,
                        "errors": 0,
                    }

                # 2. Digital Board Sync with Lichess Engine or Analysis Board
                if self.game_status == "PLAYING":
                    self.digital_state = lichess_engine.get_board()
                    self.clocks = lichess_engine.clocks
                elif self.game_status == "ANALYSIS":
                    board_grid = [["." for _ in range(8)] for _ in range(8)]
                    for sq in chess.SQUARES:
                        piece = self.analysis_active_board.piece_at(sq)
                        if piece:
                            f = chess.square_file(sq)
                            r = chess.square_rank(sq)
                            board_grid[r][f] = piece.symbol()
                    self.digital_state = board_grid
                    self.clocks = {"white": "∞", "black": "∞"}
                else:
                    self.digital_state = [["." for _ in range(8)] for _ in range(8)]
                    self.clocks = {"white": "?", "black": "?"}

                # 3. Coach Analysis & Payload
                is_ai = getattr(lichess_engine, "is_ai_game", False)
                coach_ai_only = settings.get("coach_ai_only", True)
                fair_play_active = coach_ai_only and not is_ai
                coach_hints_enabled = settings.get("coach_hints_enabled", True)
                eval_bar_enabled = settings.get("eval_bar_enabled", True)

                coach_payload = {
                    "enabled": bool((coach_hints_enabled or eval_bar_enabled) and not fair_play_active),
                    "eval_bar_enabled": bool(eval_bar_enabled and not fair_play_active),
                    "coach_hints_enabled": bool(coach_hints_enabled and not fair_play_active),
                    "is_ai_game": bool(is_ai),
                    "fair_play_active": bool(fair_play_active),
                    "evaluation": None,
                    "lifted_move_hints": [],
                }

                if not fair_play_active and getattr(lichess_engine, "board", None) and self.game_status == "PLAYING":
                    coach_engine.request_analysis(lichess_engine.board)
                    eval_res = coach_engine.get_cached_evaluation(lichess_engine.board.fen())
                    if eval_res:
                        coach_payload["evaluation"] = {
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
                            coach_payload["lifted_move_hints"] = hints

                # 4. Construct unified broadcast payload
                payload = {
                    "status": self.game_status,
                    "virtual_only": self.virtual_only,
                    "physical": self.get_physical_payload(),
                    "digital": self.digital_state,
                    "clocks": self.clocks,
                    "my_color": lichess_engine.my_color,
                    "game": lichess_engine.get_game_payload(),
                    "coach": coach_payload,
                    "gesture": self.gesture_engine.get_state_payload() if hasattr(self, "gesture_engine") else None,
                    "analysis": self.get_analysis_payload(),
                    "diagnostics": diag_info,
                }

                # 4. Broadcast state to all connected WebSocket clients
                await broadcast_callback(payload)

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
        except Exception as e:
            logger.error(f"Error in state update loop: {e}")


# Global singleton state manager
state_manager = BoardStateManager()
