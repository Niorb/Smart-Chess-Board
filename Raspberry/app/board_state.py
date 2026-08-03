import asyncio
import logging
import os
import sys
import threading

# Ensure we can import from parent directory
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import serial
import lgpio
from board_hardware import scan_board, apply_debounce, BOARD_ROWS, BOARD_COLS, init_mux_pins
from playwright_chesscom.chesscom_config import SERIAL_PORT, BAUD_RATE
from .chess_engine_async import chess_engine

POL_INTERVAL = 0.1
logger = logging.getLogger("smart-chess-app.state")


class BoardStateManager:
    def __init__(self):
        self.serial_lock = threading.Lock()
        self.physical_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
        self.raw_analog_values = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
        self.digital_state = [["." for _ in range(8)] for _ in range(8)]
        self.game_status = "IDLE"  # IDLE, SEEKING, PLAYING, SETUP
        self.clocks = {"white": "?", "black": "?"}
        self.highlighted_square = None
        self.led_test_active = False
        self.testing_led_index = -1

        # Hardware init (Serial for board + lgpio for MUX)
        try:
            self.h = lgpio.gpiochip_open(0)
            init_mux_pins(self.h)
            self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1.0)
            logger.info(f"Hybrid board hardware initialized (MUX: lgpio, ADC: {SERIAL_PORT}).")
        except Exception as e:
            logger.error(f"Hardware init failed: {e}")
            self.h = None
            self.ser = None

        # LED strip initialization
        try:
            from playwright_chesscom.led_helpers import init_strip
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

    def _safe_scan(self, raw_state):
        with self.serial_lock:
            return scan_board(self.h, self.ser, raw_state)

    def _safe_calibrate(self):
        with self.serial_lock:
            from board_hardware import calibrate_board
            return calibrate_board(self.h, self.ser)

    async def handle_webapp_connected(self):
        """
        Triggered when a connection to the webapp is detected.
        Sets upper and lower thresholds to ±1000 for 5 seconds to prevent false piece detections,
        runs sensor recalibration, and restores original thresholds afterwards.
        """
        if not hasattr(self, "_recalibrate_lock") or self._recalibrate_lock is None:
            self._recalibrate_lock = asyncio.Lock()

        if self._recalibrate_lock.locked():
            logger.info("Recalibration already in progress for a webapp connection.")
            return

        async with self._recalibrate_lock:
            from board_hardware import settings, save_settings
            orig_pos = settings.get("threshold_positive", 150)
            orig_neg = settings.get("threshold_negative", 150)

            logger.info(f"Webapp connection detected! Setting thresholds to ±1000 for 5s (original: +{orig_pos}/-{orig_neg}).")
            settings["threshold_positive"] = 1000
            settings["threshold_negative"] = 1000

            try:
                # Execute sensor matrix recalibration
                await asyncio.to_thread(self._safe_calibrate)
                # Hold ±1000 threshold window for 5 seconds total (2s calibration + 3s remaining)
                await asyncio.sleep(3.0)
            except Exception as e:
                logger.error(f"Error during webapp connection recalibration: {e}")
            finally:
                settings["threshold_positive"] = orig_pos
                settings["threshold_negative"] = orig_neg
                await asyncio.to_thread(save_settings)
                logger.info(f"Recalibration window completed. Restored thresholds to +{orig_pos} / -{orig_neg}.")

    def get_physical_payload(self):
        from board_hardware import settings
        return {
            "rows": BOARD_ROWS, 
            "cols": BOARD_COLS, 
            "grid": self.physical_state,
            "adc": self.raw_analog_values,
            "baselines": settings.get("baselines"),
            "highlighted_square": self.highlighted_square,
            "led_test_active": self.led_test_active,
            "testing_led_index": self.testing_led_index,
            "disabled_squares": settings.get("disabled_squares", [])
        }

    def get_health_status(self):
        import datetime
        from board_hardware import settings

        serial_status = "CONNECTED" if (self.ser is not None and getattr(self.ser, "is_open", True)) else "DISCONNECTED"
        gpio_status = "CONNECTED" if self.h is not None else "DISCONNECTED"
        led_status = "CONNECTED" if self.strip is not None else "DISCONNECTED"
        engine_status = "CONNECTED" if getattr(chess_engine, "is_running", False) else "DISCONNECTED"

        col_mode = settings.get("col_mode", "auto")
        disabled_squares = settings.get("disabled_squares", [])
        scan_delay_ms = settings.get("scan_delay", 100 if col_mode == "manual" else 10)

        subsystems = {
            "serial": serial_status,
            "gpio": gpio_status,
            "led_strip": led_status,
            "chess_engine": engine_status,
        }

        matrix = {
            "col_mode": col_mode,
            "disabled_squares": disabled_squares,
            "scan_delay_ms": scan_delay_ms,
        }

        if serial_status == "DISCONNECTED" or gpio_status == "DISCONNECTED":
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
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "subsystems": subsystems,
            "matrix": matrix,
        }




    def _update_leds(self):
        if not self.strip or self.led_test_active:
            return
            
        try:
            from playwright_chesscom.led_helpers import get_led_indices
            from playwright_chesscom.chesscom_config import NUM_LEDS
            from rpi_ws281x import Color
            from board_hardware import settings
            
            col_mode = settings.get("col_mode", "auto")
            manual_col = settings.get("manual_col", 0)
            
            frame = [Color(0, 0, 0)] * NUM_LEDS
            
            for c in range(BOARD_COLS):  # c is file index (0..7)
                if col_mode == "manual" and c != manual_col:
                    continue
                for r in range(BOARD_ROWS):  # r is rank index (0..7)
                    if self.highlighted_square == (c, r):
                        # Orange color for highlighting
                        color = Color(255, 80, 0)
                    else:
                        val = self.physical_state[c][r]
                        if val == 1:
                            color = Color(255, 0, 0)    # Red for North
                        elif val == -1:
                            color = Color(0, 255, 0)    # Green for South
                        else:
                            continue
                            
                    for idx in get_led_indices(r, c):
                        if 0 <= idx < NUM_LEDS:
                            frame[idx] = color
                            
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
            from rpi_ws281x import Color
            from playwright_chesscom.chesscom_config import NUM_LEDS
            
            # Turn off all first
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

    async def update_loop(self, broadcast_callback):
        """Background task to poll hardware/digital board and broadcast state."""
        raw_state = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
        stable_count = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
        diag_info = {"status": "NO_HARDWARE", "last_raw_line": "", "timeouts": 16, "errors": 0}

        logger.info("Starting background state update loop.")

        try:
            while True:
                # 1. Physical Hardware Scan
                if self.ser and self.h:
                    raw_matrix, scan_diag = await asyncio.to_thread(self._safe_scan, raw_state)
                    self.raw_analog_values = raw_matrix
                    diag_info = scan_diag
                    from board_hardware import settings
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
                    self._update_leds()
                else:
                    diag_info = {
                        "status": "DISCONNECTED" if not self.ser else "NO_GPIO",
                        "last_raw_line": "",
                        "timeouts": 16,
                        "errors": 0
                    }

                # 2. Digital Board Scan (only if a game is active)
                if self.game_status == "PLAYING":
                    self.digital_state = await chess_engine.get_board()
                    try:
                        white_time, black_time = await chess_engine.get_clocks()
                        self.clocks = {"white": white_time, "black": black_time}
                    except Exception as e:
                        logger.error(f"Error reading clocks: {e}")
                else:
                    # Clear digital board if not playing
                    self.digital_state = [["." for _ in range(8)] for _ in range(8)]
                    self.clocks = {"white": "?", "black": "?"}

                # 3. Construct full state payload
                payload = {
                    "status": self.game_status,
                    "physical": self.get_physical_payload(),
                    "digital": self.digital_state,
                    "clocks": self.clocks,
                    "my_color": chess_engine.my_color,
                    "diagnostics": diag_info
                }

                # 4. Broadcast state to all connected clients
                await broadcast_callback(payload)

                # Poll interval (read dynamically from settings)
                from board_hardware import settings
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
                    from playwright_chesscom.led_helpers import all_leds_off
                    all_leds_off(self.strip)
                except Exception as e:
                    logger.error(f"Error turning off LEDs on exit: {e}")
        except Exception as e:
            logger.error(f"Error in state update loop: {e}")


# Global instance
state_manager = BoardStateManager()
