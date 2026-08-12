import asyncio
import logging
import os
import sys

from playwright_chesscom.chesscom_browser import (
    cancel_search,
    close,
    detect_my_color,
    is_logged_in,
    launch,
    make_move as play_move,
    read_board,
    read_clocks,
    seek_game,
    wait_for_game,
)

logger = logging.getLogger("smart-chess-app.engine")


class ChessEngineAsync:
    def __init__(self):
        self.context = None
        self.page = None
        self.is_running = False
        self.my_color = None
        self._cancel_event = asyncio.Event()

    async def start(self):
        if self.is_running:
            return

        logger.info("Launching Playwright asynchronously...")
        self.context, self.page = await launch(headless=True)
        self.is_running = True

    async def stop(self):
        if not self.is_running:
            return

        try:
            await close(self.context)
        except Exception as e:
            logger.error(f"Error closing Playwright context: {e}")

        self.is_running = False
        self.page = None
        self.context = None

    async def check_login(self):
        if not self.is_running or not self.page:
            await self.start()

        return await is_logged_in(self.page)

    async def seek(self, state_manager, time_control=None):
        """
        Initiates a game search asynchronously.
        """
        if not self.is_running:
            await self.start()

        logged_in = await self.check_login()
        if not logged_in:
            logger.error("Not logged in to chess.com.")
            state_manager.game_status = "IDLE"
            return False

        logger.info(f"Seeking game with time control: {time_control or 'default'}...")
        self._cancel_event.clear()
        state_manager.game_status = "SEEKING"

        try:
            if not await seek_game(self.page, time_control):
                logger.error("Failed to initiate seek.")
                state_manager.game_status = "IDLE"
                return False

            game_found = await wait_for_game(self.page, cancel_event=self._cancel_event)

            if game_found:
                state_manager.game_status = "PLAYING"
                self.my_color = await detect_my_color(self.page)
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
            if self.page:
                await cancel_search(self.page)
            state_manager.game_status = "IDLE"
        elif state_manager.game_status == "PLAYING":
            logger.info("Resigning game (Not implemented yet)...")
            state_manager.game_status = "IDLE"

    async def get_board(self):
        """Returns the current 8x8 piece map from chess.com."""
        if not self.is_running or not self.page:
            return [["."] * 8 for _ in range(8)]

        if self.page is not None and "/play" in self.page.url:
            return await read_board(self.page)
        return [["."] * 8 for _ in range(8)]

    async def get_clocks(self):
        """Returns the remaining times for both players (white, black) from chess.com."""
        if not self.is_running or not self.page:
            return "?", "?"

        return await read_clocks(self.page, self.my_color or "white")

    async def make_move(self, from_file, from_rank, to_file, to_rank):
        """Clicks on the board in chess.com to execute a move."""
        if not self.is_running or not self.page:
            return False

        return await play_move(self.page, from_file, from_rank, to_file, to_rank, self.my_color or "white")


# Global instance
chess_engine = ChessEngineAsync()
