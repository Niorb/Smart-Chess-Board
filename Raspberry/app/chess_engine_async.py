import asyncio
import logging
import sys
import os
import threading
import queue
import concurrent.futures

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
    read_clocks,
)

logger = logging.getLogger("smart-chess-app.engine")

class ChessEngineAsync:
    def __init__(self):
        self.context = None
        self.page = None
        self.is_running = False
        self.my_color = None
        self._cancel_event = threading.Event()
        
        # Dedicated thread worker queue & thread
        self.task_queue = queue.Queue()
        self.worker_thread = None

    def _run_worker(self):
        """Dedicated thread loop for all Playwright interactions."""
        logger.info("Playwright worker thread started.")
        while True:
            try:
                task = self.task_queue.get()
                if task is None:
                    break
                
                func, args, kwargs, future = task
                try:
                    res = func(*args, **kwargs)
                    future.set_result(res)
                except Exception as e:
                    future.set_exception(e)
                finally:
                    self.task_queue.task_done()
            except Exception as e:
                logger.error(f"Error in Playwright worker loop: {e}")
        logger.info("Playwright worker thread stopped.")

    async def run_on_worker_async(self, func, *args, **kwargs):
        """Run a function on the dedicated worker thread non-blockingly."""
        if not self.worker_thread or not self.worker_thread.is_alive():
            raise RuntimeError("Playwright worker thread is not running.")
        future = concurrent.futures.Future()
        self.task_queue.put((func, args, kwargs, future))
        return await asyncio.wrap_future(future)

    async def start(self):
        if self.is_running:
            return
        
        # Start the worker thread
        self.worker_thread = threading.Thread(target=self._run_worker, name="PlaywrightWorker", daemon=True)
        self.worker_thread.start()
        
        logger.info("Launching Playwright on worker thread...")
        def _launch():
            return launch(headless=True)
            
        self.context, self.page = await self.run_on_worker_async(_launch)
        self.is_running = True

    async def stop(self):
        if not self.is_running:
            return
            
        def _close():
            close(self.context)
            
        try:
            await self.run_on_worker_async(_close)
        except Exception as e:
            logger.error(f"Error closing Playwright context: {e}")
            
        # Stop worker thread
        self.task_queue.put(None)
        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)
            
        self.is_running = False
        self.page = None
        self.context = None
        self.worker_thread = None

    async def check_login(self):
        if not self.is_running:
            await self.start()
            
        def _check():
            return is_logged_in(self.page)
            
        return await self.run_on_worker_async(_check)

    async def seek(self, state_manager, time_control=None):
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

        logger.info(f"Seeking game with time control: {time_control or 'default'}...")
        self._cancel_event.clear()
        state_manager.game_status = "SEEKING"
        
        try:
            def _seek():
                return seek_game(self.page, time_control)
                
            if not await self.run_on_worker_async(_seek):
                logger.error("Failed to initiate seek.")
                state_manager.game_status = "IDLE"
                return False

            # Wait for game on the worker thread
            def _wait():
                return wait_for_game(self.page, cancel_event=self._cancel_event)
                
            game_found = await self.run_on_worker_async(_wait)
            
            if game_found:
                state_manager.game_status = "PLAYING"
                def _detect_color():
                    return detect_my_color(self.page)
                self.my_color = await self.run_on_worker_async(_detect_color)
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
            def _cancel():
                return cancel_search(self.page)
            await self.run_on_worker_async(_cancel)
            state_manager.game_status = "IDLE"
        elif state_manager.game_status == "PLAYING":
            logger.info("Resigning game (Not implemented yet)...")
            state_manager.game_status = "IDLE"

    async def get_board(self):
        """Returns the current 8x8 piece map from chess.com."""
        if not self.is_running or not self.page:
            return [["."]*8 for _ in range(8)]
            
        def _get_board():
            if "/play" in self.page.url:
                 return read_board(self.page)
            return [["."]*8 for _ in range(8)]
            
        return await self.run_on_worker_async(_get_board)

    async def get_clocks(self):
        """Returns the remaining times for both players (white, black) from chess.com."""
        if not self.is_running or not self.page:
            return "?", "?"
            
        def _get_clocks():
            return read_clocks(self.page, self.my_color or "white")
            
        return await self.run_on_worker_async(_get_clocks)

    async def make_move(self, from_file, from_rank, to_file, to_rank):
        """Clicks on the board in chess.com to execute a move."""
        if not self.is_running or not self.page:
            return False
            
        from chesscom_browser import make_move as play_move
        def _make_move():
            return play_move(self.page, from_file, from_rank, to_file, to_rank, self.my_color or "white")
            
        return await self.run_on_worker_async(_make_move)

# Global instance
chess_engine = ChessEngineAsync()
