"""
app/board_state.py

State manager for the Smart Chess Board.
Maintains physical sensor matrix, virtual-only simulation state, layered WS2812B LED frame rendering,
setup verification, move tracking, and real-time synchronization with the Lichess engine.
"""

import asyncio
import datetime
import logging
import os
import sys
import threading
import time

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
    BAUD_RATE,
    NUM_LEDS,
    SERIAL_PORT,
)
from app.led_helpers import (
    COLOR_INT_CHECK,
    COLOR_INT_HIGHLIGHT,
    COLOR_INT_ILLEGAL,
    COLOR_INT_LEGAL_TARGET,
    COLOR_INT_MOVE_TRACE,
    COLOR_INT_OFF,
    COLOR_INT_OPPONENT_FROM,
    COLOR_INT_OPPONENT_TO,
    COLOR_INT_PIECE_LIFTED,
    COLOR_INT_SETUP_MISPLACED,
    COLOR_INT_SETUP_MISSING,
    Color,
    all_leds_off,
    get_led_indices,
    init_strip,
)
from app.lichess_engine import lichess_engine
from app.physical_tracker import PhysicalMoveTracker
from app.setup_validator import SetupResult, SetupValidator
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
        self.game_status = "IDLE"  # IDLE, SEEKING, PLAYING, GAME_OVER, SETUP
        self.virtual_only: bool = False
        self.clocks = {"white": "?", "black": "?"}
        self.highlighted_square = None
        self.led_test_active = False
        self.testing_led_index = -1
        self.is_calibrating: bool = False
        self.active_animation = None  # LifecycleAnimation | None
        self.custom_trace_path = None  # list[tuple[int, int]] | None

        # Setup verification and move tracking subsystems
        self.setup_validator = SetupValidator()
        self.move_tracker = PhysicalMoveTracker()
        self.setup_result: SetupResult = self.setup_validator.validate(self.physical_state)

        # Hardware initialization (Serial for board + lgpio for MUX)
        try:
            self.h = lgpio.gpiochip_open(0)
            init_mux_pins(self.h)
            if serial:
                self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1.0)
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

    def trigger_animation(self, name: str, params: dict | None = None) -> bool:
        """
        Triggers a procedural full-board lifecycle animation.
        Supported names: 'GAME_STARTED', 'GAME_WON', 'GAME_LOST', 'GAME_DRAWN'.
        """
        try:
            from app.led_animations import create_animation
            anim = create_animation(name, params)
            self.active_animation = anim
            logger.info(f"Triggered LED lifecycle animation: {name} (duration={anim.duration}s)")
            return True
        except Exception as e:
            logger.error(f"Failed to trigger animation '{name}': {e}")
            return False

    def _safe_scan(self, raw_state):
        with self.serial_lock:
            return scan_board(self.h, self.ser, raw_state)

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
            "lifted_square": list(self.move_tracker.lifted_square) if self.move_tracker.lifted_square else None,
            "legal_targets": [list(sq) for sq in self.move_tracker.legal_targets],
            "invalid_placement": list(self.move_tracker.invalid_placement) if self.move_tracker.invalid_placement else None,
            "pending_opponent_move": self.move_tracker.pending_opponent_move,
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
            from app.led_animations import render_move_trace
            from app.path_interpolator import interpolate_move_path

            now = time.time()
            col_mode = settings.get("col_mode", "auto")
            manual_col = settings.get("manual_col", 0)

            frame = [COLOR_INT_OFF] * NUM_LEDS

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

            # Layer 1: Setup / Idle Board Validation
            if self.game_status in ["IDLE", "SETUP"]:
                self.setup_result = self.setup_validator.validate(self.physical_state)
                if not self.setup_result.is_setup_ready:
                    # Dim white for missing starting pieces
                    for c, r in self.setup_result.missing_white + self.setup_result.missing_black:
                        set_square_leds(c, r, COLOR_INT_SETUP_MISSING)
                    # Red for misplaced pieces
                    for c, r in self.setup_result.misplaced_pieces:
                        set_square_leds(c, r, COLOR_INT_SETUP_MISPLACED)
                # When setup is ready, all LEDs remain off

            # Layer 2: Playing State Highlights
            elif self.game_status == "PLAYING":
                # 1. Opponent Move Indication & Animated Trace
                if self.move_tracker.pending_opponent_move:
                    opp_from = self.move_tracker.pending_opponent_move["from"]
                    opp_to = self.move_tracker.pending_opponent_move["to"]
                    from_c, from_r = opp_from
                    to_c, to_r = opp_to

                    # Interpolate path and render moving comet pulse
                    path = interpolate_move_path(from_c, from_r, to_c, to_r)
                    render_move_trace(path, now, frame, COLOR_INT_MOVE_TRACE)

                    # Keep start and arrival squares continuously lit
                    set_square_leds(from_c, from_r, COLOR_INT_OPPONENT_FROM)
                    set_square_leds(to_c, to_r, COLOR_INT_OPPONENT_TO)

                # 2. King in Check Indicator
                if getattr(lichess_engine, "board", None) and lichess_engine.board.is_check():
                    king_sq = lichess_engine.board.king(lichess_engine.board.turn)
                    if king_sq is not None:
                        k_c = chess.square_file(king_sq)
                        k_r = chess.square_rank(king_sq)
                        set_square_leds(k_c, k_r, COLOR_INT_CHECK)

                # 3. Lifted Piece & Legal Target Dots
                if self.move_tracker.lifted_square:
                    l_c, l_r = self.move_tracker.lifted_square
                    set_square_leds(l_c, l_r, COLOR_INT_PIECE_LIFTED)
                    for t_c, t_r in self.move_tracker.legal_targets:
                        set_square_leds(t_c, t_r, COLOR_INT_LEGAL_TARGET)

                # 4. Invalid Placement Indicator
                if self.move_tracker.invalid_placement:
                    inv_c, inv_r = self.move_tracker.invalid_placement
                    set_square_leds(inv_c, inv_r, COLOR_INT_ILLEGAL)

            # Layer 3: Custom Diagnostic Trace Override
            if self.custom_trace_path and len(self.custom_trace_path) >= 2:
                t_from_c, t_from_r = self.custom_trace_path[0]
                t_to_c, t_to_r = self.custom_trace_path[-1]
                render_move_trace(self.custom_trace_path, now, frame, COLOR_INT_MOVE_TRACE)
                set_square_leds(t_from_c, t_from_r, COLOR_INT_OPPONENT_FROM)
                set_square_leds(t_to_c, t_to_r, COLOR_INT_OPPONENT_TO)

            # Layer 4: Diagnostic override (highest individual square priority)
            if self.highlighted_square:
                h_c, h_r = self.highlighted_square
                set_square_leds(h_c, h_r, COLOR_INT_HIGHLIGHT)

            for idx, color in enumerate(frame):
                self.strip.setPixelColor(idx, color)
            self.strip.show()
        except Exception as e:
            logger.error(f"Error in physical LED update: {e}")

    async def run_led_test(self):
        if not self.strip or self.led_test_active:
            return

        self.led_test_active = True
        logger.info("Starting sequential LED strip test...")
        try:
            for idx in range(NUM_LEDS):
                self.strip.setPixelColor(idx, Color(0, 0, 0))
            self.strip.show()
            await asyncio.sleep(0.2)

            for idx in range(NUM_LEDS):
                self.testing_led_index = idx
                self.strip.setPixelColor(idx, Color(255, 80, 0))  # Orange
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
            logger.info("Sequential LED strip test completed.")

    def clear_all_leds(self):
        """Forces all physical LEDs off and clears any highlighted square, active animation, or custom trace."""
        self.highlighted_square = None
        self.active_animation = None
        self.custom_trace_path = None
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
                    raw_matrix, scan_diag = await asyncio.to_thread(self._safe_scan, raw_state)
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
                    else:
                        self.move_tracker.reset()

                    self._update_leds()
                else:
                    diag_info = {
                        "status": "DISCONNECTED" if not self.ser else "NO_GPIO",
                        "last_raw_line": "",
                        "timeouts": 16,
                        "errors": 0,
                    }

                # 2. Digital Board Sync with Lichess Engine
                if self.game_status == "PLAYING":
                    self.digital_state = lichess_engine.get_board()
                    self.clocks = lichess_engine.clocks
                else:
                    self.digital_state = [["." for _ in range(8)] for _ in range(8)]
                    self.clocks = {"white": "?", "black": "?"}

                # 3. Construct unified broadcast payload
                payload = {
                    "status": self.game_status,
                    "virtual_only": self.virtual_only,
                    "physical": self.get_physical_payload(),
                    "digital": self.digital_state,
                    "clocks": self.clocks,
                    "my_color": lichess_engine.my_color,
                    "game": lichess_engine.get_game_payload(),
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
