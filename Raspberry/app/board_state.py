import asyncio
import logging
import os
import sys

# Ensure we can import from parent directory
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
POL_INTERVAL = 0.1

from board_hardware import (
    lgpio,
    scan_board,
    apply_debounce,
    BOARD_ROWS,
    BOARD_COLS,
    init_mux_pins,
)
from .chess_engine_async import chess_engine

logger = logging.getLogger("smart-chess-app.state")


class BoardStateManager:
    def __init__(self):
        self.physical_state = [[False] * BOARD_COLS for _ in range(BOARD_ROWS)]
        self.digital_state = [["." for _ in range(8)] for _ in range(8)]
        self.game_status = "IDLE"  # IDLE, SEEKING, PLAYING, SETUP

        # Hardware init
        try:
            self.h = lgpio.gpiochip_open(0)
            init_mux_pins(self.h)
            logger.info("GPIO hardware initialized for app server.")
        except Exception as e:
            logger.error(f"Failed to open GPIO: {e}")
            self.h = None

    def get_physical_payload(self):
        return {"rows": BOARD_ROWS, "cols": BOARD_COLS, "grid": self.physical_state}

    async def update_loop(self, broadcast_callback):
        """Background task to poll hardware/digital board and broadcast state."""
        raw_state = [[False] * BOARD_COLS for _ in range(BOARD_ROWS)]
        stable_count = [[0] * BOARD_COLS for _ in range(BOARD_ROWS)]
        DEBOUNCE_THRESHOLD = 2

        logger.info("Starting background state update loop.")

        try:
            while True:
                # 1. Physical Hardware Scan
                if self.h:
                    await asyncio.to_thread(scan_board, self.h, raw_state)
                    apply_debounce(
                        raw_state, self.physical_state, stable_count, DEBOUNCE_THRESHOLD
                    )

                # 2. Digital Board Scan (only if a game is active)
                if self.game_status == "PLAYING":
                    self.digital_state = await chess_engine.get_board()
                else:
                    # Clear digital board if not playing
                    self.digital_state = [["." for _ in range(8)] for _ in range(8)]

                # 3. Construct full state payload
                payload = {
                    "status": self.game_status,
                    "physical": self.get_physical_payload(),
                    "digital": self.digital_state,
                    "my_color": chess_engine.my_color,
                }

                # 4. Broadcast state to all connected clients
                await broadcast_callback(payload)

                # Poll interval
                await asyncio.sleep(POL_INTERVAL)
        except asyncio.CancelledError:
            logger.info("State update loop cancelled.")
            if self.h and not isinstance(self.h, str):  # don't close mock string
                lgpio.gpiochip_close(self.h)
        except Exception as e:
            logger.error(f"Error in state update loop: {e}")


# Global instance
state_manager = BoardStateManager()
