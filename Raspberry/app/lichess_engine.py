"""
app/lichess_engine.py

Lichess Board API async integration for the Smart Chess Board.
Handles OAuth authentication, matchmaking seeks, real-time NDJSON game streams,
move validation/execution, clock synchronization, and resignation/draw offers.
"""

import asyncio
import json
import logging
import os
import re
from typing import Any

import chess
from dotenv import load_dotenv
import httpx

# Load environment variables from .env in Raspberry root or project root
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

logger = logging.getLogger("smart-chess-app.lichess")

LICHESS_BASE_URL = "https://lichess.org"


def format_clock_ms(ms: int | float | None) -> str:
    """Format millisecond clock value into M:SS or S.s representation."""
    if ms is None or ms < 0:
        return "?"
    total_seconds = int(ms // 1000)
    mins = total_seconds // 60
    secs = total_seconds % 60
    if mins > 0:
        return f"{mins}:{secs:02d}"
    tenths = int((ms % 1000) // 100)
    return f"{secs}.{tenths}s"


def parse_time_control(time_control_str: str | None) -> tuple[int, int]:
    """
    Parse various time control strings into (time_in_minutes, increment_in_seconds).
    Examples:
      '10+0'   -> (10, 0)
      '3+2'    -> (3, 2)
      '15+10'  -> (15, 10)
      '10 min' -> (10, 0)
      '15 | 10'-> (15, 10)
    """
    if not time_control_str:
        return 10, 0

    tc = str(time_control_str).strip().lower()

    # Format: "10+0" or "3+2"
    if "+" in tc:
        parts = tc.split("+")
        try:
            return max(0, int(parts[0].strip())), max(0, int(parts[1].strip()))
        except ValueError:
            pass

    # Format: "15 | 10"
    if "|" in tc:
        parts = tc.split("|")
        try:
            return max(0, int(parts[0].strip())), max(0, int(parts[1].strip()))
        except ValueError:
            pass

    # Format: "10 min", "3 min", "1 min", "30 min"
    if "min" in tc:
        clean_num = re.sub(r"[^\d]", "", tc)
        try:
            return max(0, int(clean_num)), 0
        except ValueError:
            pass

    # Pure integer assumed to be minutes
    try:
        return max(0, int(tc)), 0
    except ValueError:
        return 10, 0


class LichessEngine:
    def __init__(self):
        self.token = os.environ.get("LICHESS_API_TOKEN", "").strip()
        self.client: httpx.AsyncClient | None = None
        self.is_running: bool = False
        self.username: str | None = None
        self.my_color: str | None = None  # 'white' | 'black' | None
        self.current_game_id: str | None = None
        self.board: chess.Board = chess.Board()
        self.clocks: dict[str, str] = {"white": "?", "black": "?"}
        self.raw_clocks_ms: dict[str, int | float | None] = {"white": None, "black": None}
        self.game_info: dict[str, Any] = {
            "game_id": None,
            "rated": False,
            "speed": None,
            "turn": "white",
            "my_color": None,
            "opponent": {"username": "?", "rating": 0, "title": None},
            "last_move": None,
            "legal_moves": [],
            "is_check": False,
            "is_game_over": False,
            "winner": None,
            "end_reason": None,
        }
        self._seek_task: asyncio.Task | None = None
        self._stream_task: asyncio.Task | None = None
        self._cancel_event = asyncio.Event()

    def _get_headers(self) -> dict[str, str]:
        token = os.environ.get("LICHESS_API_TOKEN", self.token).strip()
        headers = {
            "User-Agent": "SmartChessBoard/1.0 (Python/httpx)",
            "Accept": "application/json",
        }
        if token and not token.startswith("lip_your"):
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def start(self):
        """Initializes the HTTP client and fetches authenticated account details."""
        if self.is_running and self.client and not self.client.is_closed:
            return

        self.token = os.environ.get("LICHESS_API_TOKEN", self.token).strip()
        self.client = httpx.AsyncClient(
            base_url=LICHESS_BASE_URL,
            headers=self._get_headers(),
            timeout=httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0),
            http2=True,
        )
        self.is_running = True
        logger.info("Lichess engine initialized.")

        # Attempt to retrieve account info
        try:
            account = await self.get_account()
            if account.get("authenticated"):
                self.username = account.get("username")
                logger.info(f"Authenticated with Lichess as '{self.username}' (Rating: {account.get('rating')}).")
            else:
                logger.warning("Lichess token not set or unauthenticated. Running in offline/guest mode.")
        except Exception as e:
            logger.warning(f"Could not verify Lichess account on startup: {e}")

    async def stop(self):
        """Cancels background tasks and closes HTTP client session."""
        if not self.is_running:
            return

        self._cancel_event.set()
        if self._seek_task and not self._seek_task.done():
            self._seek_task.cancel()
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()

        if self.client and not self.client.is_closed:
            await self.client.aclose()

        self.is_running = False
        self.client = None
        self.current_game_id = None
        logger.info("Lichess engine stopped.")

    async def get_account(self) -> dict[str, Any]:
        """Queries GET /api/account to return user profile and perfs."""
        token = os.environ.get("LICHESS_API_TOKEN", self.token).strip()
        if not token or token.startswith("lip_your"):
            return {
                "username": "Guest",
                "rating": 0,
                "title": None,
                "online": False,
                "authenticated": False,
                "error": "No valid token configured. Add token to Raspberry/.env",
            }

        headers = self._get_headers()
        try:
            async with httpx.AsyncClient(base_url=LICHESS_BASE_URL, headers=headers, timeout=5.0) as client:
                res = await client.get("/api/account")
                if res.status_code == 200:
                    data = res.json()
                    self.username = data.get("username")
                    perfs = data.get("perfs", {})
                    rapid_rating = perfs.get("rapid", {}).get("rating", 1500)
                    blitz_rating = perfs.get("blitz", {}).get("rating", 1500)
                    bullet_rating = perfs.get("bullet", {}).get("rating", 1500)
                    return {
                        "username": self.username,
                        "rating": rapid_rating,
                        "perfs": {
                            "rapid": rapid_rating,
                            "blitz": blitz_rating,
                            "bullet": bullet_rating,
                        },
                        "title": data.get("title"),
                        "online": not data.get("disabled", False),
                        "authenticated": True,
                    }
                else:
                    return {
                        "username": "Unauthorized",
                        "rating": 0,
                        "title": None,
                        "online": False,
                        "authenticated": False,
                        "error": f"Lichess API returned HTTP {res.status_code}: {res.text}",
                    }
        except Exception as e:
            logger.error(f"Error checking Lichess account: {e}")
            return {
                "username": "Offline",
                "rating": 0,
                "title": None,
                "online": False,
                "authenticated": False,
                "error": str(e),
            }

    async def seek(
        self,
        state_manager,
        time_control: str = "10+0",
        rated: bool = False,
        color: str = "random",
    ) -> bool:
        """Initiates a matchmaking search on Lichess."""
        if not self.is_running or not self.client:
            await self.start()

        time_mins, inc_secs = parse_time_control(time_control)
        logger.info(
            f"Seeking Lichess match: {time_mins}m+{inc_secs}s, rated={rated}, color={color}"
        )

        self._cancel_event.clear()
        state_manager.game_status = "SEEKING"

        if self._seek_task and not self._seek_task.done():
            self._seek_task.cancel()

        self._seek_task = asyncio.create_task(
            self._seek_and_stream(state_manager, time_mins, inc_secs, rated, color)
        )
        return True

    async def _seek_and_stream(
        self,
        state_manager,
        time_mins: int,
        inc_secs: int,
        rated: bool,
        color: str,
    ):
        """Streams the seek response and connects to game stream once matched."""
        form_data = {
            "time": str(time_mins),
            "increment": str(inc_secs),
            "rated": "true" if rated else "false",
            "color": color,
        }

        headers = self._get_headers()
        headers["Accept"] = "application/x-ndjson"

        try:
            async with httpx.AsyncClient(
                base_url=LICHESS_BASE_URL, headers=headers, timeout=None
            ) as client:
                async with client.stream("POST", "/api/board/seek", data=form_data) as response:
                    if response.status_code != 200:
                        err_text = await response.aread()
                        logger.error(f"Lichess seek failed (HTTP {response.status_code}): {err_text.decode('utf-8')}")
                        state_manager.game_status = "IDLE"
                        return

                    logger.info("Seek active on Lichess. Waiting for match...")
                    async for line in response.aiter_lines():
                        if self._cancel_event.is_set():
                            logger.info("Seek cancelled by user.")
                            state_manager.game_status = "IDLE"
                            return

                        line = line.strip()
                        if not line:
                            continue

                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Extract game ID
                        game_id = event.get("id") or event.get("gameId") or event.get("game", {}).get("id")
                        if not game_id and event.get("type") == "gameStart":
                            game_id = event.get("game", {}).get("id")

                        if game_id:
                            logger.info(f"Match found! Game ID: {game_id}")
                            self.current_game_id = game_id
                            state_manager.game_status = "PLAYING"
                            if self._stream_task and not self._stream_task.done():
                                self._stream_task.cancel()
                            self._stream_task = asyncio.create_task(
                                self.stream_game(game_id, state_manager)
                            )
                            return
        except asyncio.CancelledError:
            logger.info("Seek task cancelled.")
            state_manager.game_status = "IDLE"
        except Exception as e:
            logger.error(f"Error during seek streaming: {e}")
            state_manager.game_status = "IDLE"

    async def stream_game(self, game_id: str, state_manager):
        """Streams game state events from GET /api/board/game/stream/{game_id}."""
        self.current_game_id = game_id
        headers = self._get_headers()
        headers["Accept"] = "application/x-ndjson"

        # Ensure username is available for color resolution
        if not self.username:
            acct = await self.get_account()
            self.username = acct.get("username")

        try:
            async with httpx.AsyncClient(
                base_url=LICHESS_BASE_URL, headers=headers, timeout=None
            ) as client:
                async with client.stream(
                    "GET", f"/api/board/game/stream/{game_id}"
                ) as response:
                    if response.status_code != 200:
                        logger.error(f"Failed to stream game {game_id}: HTTP {response.status_code}")
                        state_manager.game_status = "IDLE"
                        return

                    logger.info(f"Streaming live game {game_id}...")
                    async for line in response.aiter_lines():
                        if self._cancel_event.is_set():
                            break

                        line = line.strip()
                        if not line:
                            continue

                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        event_type = event.get("type")
                        if event_type == "gameFull":
                            self._handle_game_full(event, state_manager)
                        elif event_type == "gameState":
                            self._handle_game_state(event, state_manager)
                        elif event_type == "chatLine":
                            logger.info(f"[Chat] {event.get('username')}: {event.get('text')}")
                        elif event_type == "opponentGone":
                            gone = event.get("gone", False)
                            claim_win = event.get("claimWinInSeconds", 0)
                            logger.info(f"Opponent gone: {gone}, claim win in {claim_win}s")

        except asyncio.CancelledError:
            logger.info(f"Game stream {game_id} cancelled.")
        except Exception as e:
            logger.error(f"Error in game stream {game_id}: {e}")
        finally:
            logger.info(f"Game stream {game_id} finished.")
            if state_manager.game_status == "PLAYING":
                state_manager.game_status = "IDLE"

    def _handle_game_full(self, event: dict[str, Any], state_manager):
        """Handles initial game snapshot event."""
        white_info = event.get("white", {})
        black_info = event.get("black", {})

        my_user = (self.username or "").lower()
        white_user = (white_info.get("name") or white_info.get("id") or "").lower()
        black_user = (black_info.get("name") or black_info.get("id") or "").lower()

        if my_user and my_user == white_user:
            self.my_color = "white"
        elif my_user and my_user == black_user:
            self.my_color = "black"
        else:
            self.my_color = "white"  # Default fallback

        opp_info = black_info if self.my_color == "white" else white_info
        opponent = {
            "username": opp_info.get("name") or opp_info.get("id", "Opponent"),
            "rating": opp_info.get("rating", 1500),
            "title": opp_info.get("title"),
        }

        self.game_info["game_id"] = self.current_game_id
        self.game_info["rated"] = event.get("rated", False)
        self.game_info["speed"] = event.get("speed", "rapid")
        self.game_info["my_color"] = self.my_color
        self.game_info["opponent"] = opponent
        self.game_info["is_game_over"] = False
        self.game_info["winner"] = None
        self.game_info["end_reason"] = None

        state_data = event.get("state", {})
        self._apply_moves(state_data.get("moves", ""))

        wtime = state_data.get("wtime")
        btime = state_data.get("btime")
        self.raw_clocks_ms = {"white": wtime, "black": btime}
        self.clocks = {
            "white": format_clock_ms(wtime),
            "black": format_clock_ms(btime),
        }

        # Update state_manager
        state_manager.digital_state = self.get_board()
        state_manager.clocks = self.clocks

        # Check for immediate end status
        status = state_data.get("status")
        if status and status != "started":
            self.game_info["is_game_over"] = True
            self.game_info["winner"] = state_data.get("winner")
            self.game_info["end_reason"] = status
            state_manager.game_status = "IDLE"

    def _handle_game_state(self, event: dict[str, Any], state_manager):
        """Handles differential move/clock updates."""
        moves_str = event.get("moves", "")
        self._apply_moves(moves_str)

        wtime = event.get("wtime")
        btime = event.get("btime")
        self.raw_clocks_ms = {"white": wtime, "black": btime}
        self.clocks = {
            "white": format_clock_ms(wtime),
            "black": format_clock_ms(btime),
        }

        state_manager.digital_state = self.get_board()
        state_manager.clocks = self.clocks

        status = event.get("status")
        winner = event.get("winner")

        if (status and status != "started") or winner:
            self.game_info["is_game_over"] = True
            self.game_info["winner"] = winner
            self.game_info["end_reason"] = status
            state_manager.game_status = "IDLE"

    def _apply_moves(self, moves_str: str):
        """Reconstructs internal chess.Board from space-separated UCI move sequence."""
        self.board = chess.Board()
        if moves_str:
            for uci in moves_str.strip().split():
                try:
                    move = chess.Move.from_uci(uci)
                    if move in self.board.legal_moves or self.board.is_legal(move):
                        self.board.push(move)
                    else:
                        self.board.push_uci(uci)
                except Exception as e:
                    logger.warning(f"Could not push move {uci}: {e}")

        # Update cached game metrics
        self.game_info["turn"] = "white" if self.board.turn == chess.WHITE else "black"
        self.game_info["is_check"] = self.board.is_check()
        self.game_info["legal_moves"] = [m.uci() for m in self.board.legal_moves]
        self.game_info["last_move"] = (
            self.board.peek().uci() if self.board.move_stack else None
        )

    def get_board(self) -> list[list[str]]:
        """
        Returns 8x8 piece grid matching the frontend and hardware coordinates:
        grid[rank_idx][file_idx] where rank_idx 0..7 = Rank 1..8 and file_idx 0..7 = File a..h.
        """
        grid = [["." for _ in range(8)] for _ in range(8)]
        for rank_idx in range(8):
            for file_idx in range(8):
                sq = chess.square(file_idx, rank_idx)
                piece = self.board.piece_at(sq)
                grid[rank_idx][file_idx] = piece.symbol() if piece else "."
        return grid

    def get_game_payload(self) -> dict[str, Any]:
        """Returns structured metadata for WebSockets and API endpoints."""
        last_move_uci = self.board.peek().uci() if self.board.move_stack else None
        return {
            "game_id": self.current_game_id,
            "rated": self.game_info.get("rated", False),
            "speed": self.game_info.get("speed"),
            "turn": "white" if self.board.turn == chess.WHITE else "black",
            "my_color": self.my_color,
            "opponent": self.game_info.get("opponent", {}),
            "last_move": last_move_uci,
            "legal_moves": [m.uci() for m in self.board.legal_moves],
            "is_check": self.board.is_check(),
            "is_game_over": self.board.is_game_over() or self.game_info.get("is_game_over", False),
            "winner": self.game_info.get("winner"),
            "end_reason": self.game_info.get("end_reason"),
        }

    async def make_move(
        self,
        from_file: int,
        from_rank: int,
        to_file: int,
        to_rank: int,
        promotion: str | None = None,
    ) -> bool:
        """
        Executes a move given 1-indexed coordinates (1-8, 1-8).
        Example: from (5, 2) to (5, 4) -> 'e2e4'.
        """
        from_sq = f"{chr(ord('a') + from_file - 1)}{from_rank}"
        to_sq = f"{chr(ord('a') + to_file - 1)}{to_rank}"
        uci_move = f"{from_sq}{to_sq}"
        if promotion:
            uci_move += promotion.lower()

        return await self.make_move_uci(uci_move)

    async def make_move_uci(self, uci_move: str) -> bool:
        """Sends POST /api/board/game/{game_id}/move/{uci_move} to Lichess."""
        if not self.current_game_id:
            logger.error("No active game ID to make move.")
            return False

        headers = self._get_headers()
        try:
            async with httpx.AsyncClient(base_url=LICHESS_BASE_URL, headers=headers, timeout=5.0) as client:
                res = await client.post(f"/api/board/game/{self.current_game_id}/move/{uci_move}")
                if res.status_code == 200 and res.json().get("ok", True):
                    logger.info(f"Move {uci_move} accepted by Lichess.")
                    return True
                else:
                    logger.error(f"Move {uci_move} rejected by Lichess: {res.text}")
                    return False
        except Exception as e:
            logger.error(f"Error making move {uci_move}: {e}")
            return False

    async def resign(self, state_manager) -> bool:
        """Resigns the active game via POST /api/board/game/{game_id}/resign."""
        if not self.current_game_id:
            return False

        headers = self._get_headers()
        try:
            async with httpx.AsyncClient(base_url=LICHESS_BASE_URL, headers=headers, timeout=5.0) as client:
                res = await client.post(f"/api/board/game/{self.current_game_id}/resign")
                state_manager.game_status = "IDLE"
                return res.status_code == 200
        except Exception as e:
            logger.error(f"Error resigning game: {e}")
            state_manager.game_status = "IDLE"
            return False

    async def abort(self, state_manager) -> bool:
        """Aborts the active game via POST /api/board/game/{game_id}/abort."""
        if not self.current_game_id:
            return False

        headers = self._get_headers()
        try:
            async with httpx.AsyncClient(base_url=LICHESS_BASE_URL, headers=headers, timeout=5.0) as client:
                res = await client.post(f"/api/board/game/{self.current_game_id}/abort")
                state_manager.game_status = "IDLE"
                return res.status_code == 200
        except Exception as e:
            logger.error(f"Error aborting game: {e}")
            state_manager.game_status = "IDLE"
            return False

    async def draw(self, state_manager, accept: bool = True) -> bool:
        """Offers or accepts a draw via POST /api/board/game/{game_id}/draw/{yes/no}."""
        if not self.current_game_id:
            return False

        action = "yes" if accept else "no"
        headers = self._get_headers()
        try:
            async with httpx.AsyncClient(base_url=LICHESS_BASE_URL, headers=headers, timeout=5.0) as client:
                res = await client.post(f"/api/board/game/{self.current_game_id}/draw/{action}")
                return res.status_code == 200
        except Exception as e:
            logger.error(f"Error offering/accepting draw: {e}")
            return False

    async def cancel(self, state_manager):
        """Cancels an active seek or resigns an ongoing game."""
        if state_manager.game_status == "SEEKING":
            logger.info("Cancelling active Lichess seek...")
            self._cancel_event.set()
            if self._seek_task and not self._seek_task.done():
                self._seek_task.cancel()
            state_manager.game_status = "IDLE"
        elif state_manager.game_status == "PLAYING":
            logger.info("Resigning active Lichess game...")
            await self.resign(state_manager)


# Global singleton instance
lichess_engine = LichessEngine()
