import asyncio
import logging
import sys
import os
import threading

# Ensure we can import from the parent and the playwright directory
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "playwright_chesscom"))
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from chesscom_browser import (
    launch,
    close,
    is_logged_in,
    seek_game,
    wait_for_game,
    cancel_search,
    read_board,
    detect_my_color,
)

logger = logging.getLogger("smart-chess-app.engine")

class ChessEngineAsync:
    def __init__(self):
        self.context = None
        self.page = None
        self.is_running = False
        self.my_color = None
        self._cancel_event = threading.Event()

    async def start(self):
        if self.is_running:
            return
        logger.info("Launching Playwright...")
        self.context, self.page = await asyncio.to_thread(launch, headless=True)
        self.is_running = True

    async def stop(self):
        if not self.is_running:
            return
        await asyncio.to_thread(close, self.context)
        self.is_running = False
        self.page = None
        self.context = None

    async def check_login(self):
        if not self.is_running:
            await self.start()
        return await asyncio.to_thread(is_logged_in, self.page)

    async def seek(self, state_manager):
        """
        Initiates a game search. Blocks until a game is found or fails.
        """
        if not self.is_running:
            await self.start()

        logged_in = await self.check_login()
        if not logged_in:
            logger.error("Not logged in to chess.com.")
            state_manager.game_status = "IDLE"
            return False

        logger.info("Seeking game...")
        self._cancel_event.clear()
        state_manager.game_status = "SEEKING"
        
        try:
            if not await asyncio.to_thread(seek_game, self.page):
                logger.error("Failed to initiate seek.")
                state_manager.game_status = "IDLE"
                return False

            # Use thread-safe event for cancellation
            game_found = await asyncio.to_thread(wait_for_game, self.page, cancel_event=self._cancel_event)
            
            if game_found:
                state_manager.game_status = "PLAYING"
                self.my_color = await asyncio.to_thread(detect_my_color, self.page)
                logger.info(f"Game started! Playing as {self.my_color}.")
                return True
            else:
                state_manager.game_status = "IDLE"
                logger.info("Game search stopped (timeout or manual cancel).")
                return False
        except Exception as e:
            logger.error(f"Error during seek: {e}")
            state_manager.game_status = "IDLE"
            return False

    async def cancel(self, state_manager):
        """Cancels seeking or resigns game."""
        if not self.is_running:
            return

        if state_manager.game_status == "SEEKING":
            logger.info("Cancelling search...")
            self._cancel_event.set()
            await asyncio.to_thread(cancel_search, self.page)
            state_manager.game_status = "IDLE"
        elif state_manager.game_status == "PLAYING":
            logger.info("Resigning game (Not implemented yet)...")
            # TODO: Implement resign_game in chesscom_browser.py
            state_manager.game_status = "IDLE"

    async def get_board(self):
        """Returns the current 8x8 piece map from chess.com."""
        if not self.is_running:
            return [["."]*8 for _ in range(8)]
        # Read board if page is on a game URL
        if "/play" in self.page.url:
             return await asyncio.to_thread(read_board, self.page)
        return [["."]*8 for _ in range(8)]

# Global instance
chess_engine = ChessEngineAsync()
