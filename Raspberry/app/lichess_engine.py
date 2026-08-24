"""
app/lichess_engine.py

Lichess Board API async integration for the Smart Chess Board.
Handles OAuth authentication, matchmaking seeks (human & Stockfish AI),
real-time NDJSON game streams, move validation/execution, clock synchronization,
and resignation/draw offers.
"""

import asyncio
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Any

import chess
import httpx
from dotenv import load_dotenv

# Multi-path .env loading
env_candidates = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
    os.path.expanduser("~/.env"),
    os.path.expanduser("~/chess_git/Raspberry/.env"),
    os.path.join(os.getcwd(), ".env"),
]
for p in env_candidates:
    if os.path.exists(p):
        load_dotenv(p)

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


class _SharedClientProxy:
    """Delegates requests to the pooled engine client, injecting per-call headers/timeout."""

    def __init__(self, client: "httpx.AsyncClient", headers: dict, timeout):
        self._client = client
        self._headers = headers
        self._timeout = timeout

    async def get(self, url: str, **kwargs):
        kwargs.setdefault("headers", self._headers)
        kwargs.setdefault("timeout", self._timeout)
        return await self._client.get(url, **kwargs)

    async def post(self, url: str, **kwargs):
        kwargs.setdefault("headers", self._headers)
        kwargs.setdefault("timeout", self._timeout)
        return await self._client.post(url, **kwargs)

    def stream(self, method: str, url: str, **kwargs):
        kwargs.setdefault("headers", self._headers)
        kwargs.setdefault("timeout", self._timeout)
        return self._client.stream(method, url, **kwargs)


class LichessEngine:
    def __init__(self):
        self.token = os.environ.get("LICHESS_API_TOKEN", "").strip()
        self.client: httpx.AsyncClient | None = None
        self.is_running: bool = False
        self.username: str | None = None
        self.my_color: str | None = None  # 'white' | 'black' | None
        self.current_game_id: str | None = None
        # Games explicitly initiated by this server session (seek/challenge_ai).
        # The event stream must never auto-join anything else.
        self._session_games: set[str] = set()
        self.board: chess.Board = chess.Board()
        self.clocks: dict[str, str] = {"white": "?", "black": "?"}
        self.raw_clocks_ms: dict[str, int | float | None] = {"white": None, "black": None}
        self.initial_clocks_ms: dict[str, int | None] = {"white": None, "black": None}
        self.clocks_updated_at: float | None = None
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
        self.opponent_gone: dict[str, Any] | None = None
        self.last_game_moves: list[str] = []
        self.last_game_id: str | None = None
        self.last_game_info: dict[str, Any] = {}
        self.last_game_my_color: str | None = None
        self._last_move_cache: tuple[int, bool] = (-1, False)
        self._auto_claim_task: asyncio.Task | None = None
        self._seek_task: asyncio.Task | None = None
        self._stream_task: asyncio.Task | None = None
        self._event_stream_task: asyncio.Task | None = None
        self._cancel_event = asyncio.Event()

    @property
    def is_ai_game(self) -> bool:
        """Returns True if the current active game is against Stockfish AI."""
        opp = self.game_info.get("opponent", {})
        username = (opp.get("username") or "").lower()
        title = opp.get("title")
        return bool(title == "BOT" or "stockfish" in username or "ai level" in username or username.startswith("ai"))

    def _get_headers(self) -> dict[str, str]:
        token = os.environ.get("LICHESS_API_TOKEN", self.token).strip()
        headers = {
            "User-Agent": "SmartChessBoard/1.0 (Python/httpx)",
            "Accept": "application/json",
        }
        if token and not token.startswith("lip_your"):
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @asynccontextmanager
    async def _request_client(self, headers: dict, timeout):
        """Yields a request proxy over the pooled client (falls back to a temp client offline)."""
        client = self.client
        owns = False
        if client is None or client.is_closed:
            client = httpx.AsyncClient(
                base_url=LICHESS_BASE_URL,
                timeout=httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0),
                http2=True,
            )
            owns = True
        try:
            yield _SharedClientProxy(client, headers, timeout)
        finally:
            if owns:
                await client.aclose()


    def _save_settings_off_loop(self, save_fn) -> None:
        """Persists settings without blocking the event loop when one is running."""
        try:
            asyncio.get_running_loop().run_in_executor(None, save_fn)
        except RuntimeError:
            save_fn()

    async def start(self, state_manager=None):
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
        self._cancel_event.clear()
        logger.info("Lichess engine initialized.")

        try:
            account = await self.get_account()
            if account.get("authenticated"):
                self.username = account.get("username")
                logger.info(f"Authenticated with Lichess as '{self.username}' (Rating: {account.get('rating')}).")

                # Start global event listener (/api/stream/event)
                if state_manager and (not self._event_stream_task or self._event_stream_task.done()):
                    self._event_stream_task = asyncio.create_task(
                        self._listen_event_stream(state_manager)
                    )
            else:
                logger.warning("Lichess token not set or unauthenticated. Running in offline/guest mode.")
        except Exception as e:
            logger.warning(f"Could not verify Lichess account on startup: {e}")

    async def stop(self):
        """Cancels background tasks and closes HTTP client session."""
        if not self.is_running:
            return

        self._cancel_event.set()
        tasks = [
            t
            for t in (
                self._auto_claim_task,
                self._seek_task,
                self._stream_task,
                self._event_stream_task,
            )
            if t and not t.done()
        ]
        for t in tasks:
            t.cancel()
        self._auto_claim_task = None
        self.opponent_gone = None
        # Await cancellations so no request is still using the client when it closes
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._seek_task = None
        self._stream_task = None
        self._event_stream_task = None

        if self.client and not self.client.is_closed:
            await self.client.aclose()

        self.is_running = False
        self.client = None
        self.current_game_id = None
        logger.info("Lichess engine stopped.")

    async def _listen_event_stream(self, state_manager):
        """Persistent listener for GET /api/stream/event capturing gameStart / incoming challenges."""
        while self.is_running and not self._cancel_event.is_set():
            try:
                headers = self._get_headers()
                headers["Accept"] = "application/x-ndjson"
                async with self._request_client(headers, None) as client, client.stream(
                    "GET", "/api/stream/event"
                ) as response:
                        if response.status_code != 200:
                            logger.debug(f"Event stream HTTP {response.status_code}, retrying in 5s...")
                            await asyncio.sleep(5)
                            continue
                        logger.info("Lichess event stream (/api/stream/event) connected.")
                        async for line in response.aiter_lines():
                            if not self.is_running or self._cancel_event.is_set():
                                return
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                event = json.loads(line)
                            except json.JSONDecodeError:
                                continue

                            event_type = event.get("type")
                            if event_type == "gameStart":
                                self._handle_game_start_event(event.get("game", {}), state_manager)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Event stream reconnecting: {e}")
                await asyncio.sleep(3)

    def _handle_game_start_event(self, game_info: dict[str, Any], state_manager) -> bool:
        """
        Joins a game announced by the event stream when it belongs to this session.

        Two acceptance paths:
        - The game id was registered by this session (seek()/challenge_ai()).
        - OR the board is actively SEEKING: while a human seek is open, any new
          gameStart can only be our own seek being accepted. This is a required
          fallback because the seek stream itself does not always deliver the
          matched game id.

        Otherwise the event is ignored, preventing auto-resume of stale/foreign
        games on startup (status is IDLE then).
        """
        game_id = game_info.get("id") or game_info.get("gameId")
        if not game_id or game_id == self.current_game_id:
            return False

        actively_seeking = bool(state_manager and getattr(state_manager, "game_status", None) == "SEEKING")
        if game_id not in self._session_games and not actively_seeking:
            logger.info(
                f"Lichess event stream: ignoring gameStart for game {game_id} "
                "(not initiated by this session)."
            )
            return False

        if actively_seeking:
            logger.info(
                f"Lichess event stream: accepting gameStart for game {game_id} "
                "while a seek is active (seek-stream fallback)."
            )
        else:
            logger.info(f"Lichess event stream: joining session-initiated game {game_id}")

        self._session_games.add(game_id)
        self.current_game_id = game_id
        if state_manager:
            state_manager.game_status = "PLAYING"

        # A match was found — the open seek stream is now redundant.
        if self._seek_task and not self._seek_task.done():
            logger.info("Cancelling redundant seek stream after match.")
            self._seek_task.cancel()
        self._seek_task = None

        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
        self._stream_task = asyncio.create_task(self.stream_game(game_id, state_manager))
        return True

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
            async with self._request_client(headers, 5.0) as client:
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

    async def get_user_recent_games(self, username: str | None = None, max_games: int = 10) -> list[dict[str, Any]]:
        """
        Fetches and parses the user's recent finished games from GET /api/games/user/{username}.
        Extracts UCI moves, opponent details, result, date, opening, and speed for Analysis mode.
        """
        if not username:
            if not self.username:
                acct = await self.get_account()
                username = acct.get("username")
            else:
                username = self.username

        if not username or username in ("Guest", "Unauthorized", "Offline"):
            logger.warning(f"Cannot fetch recent games: user not authenticated or username '{username}' invalid.")
            return []

        headers = self._get_headers()
        headers["Accept"] = "application/x-ndjson"

        params = {
            "max": max(1, min(50, max_games)),
            "moves": "true",
            "tags": "true",
            "opening": "true",
            "clocks": "false",
            "evals": "false",
            "ongoing": "false",
            "finished": "true",
        }

        games: list[dict[str, Any]] = []

        try:
            async with self._request_client(headers, 12.0) as client:
                res = await client.get(f"/api/games/user/{username}", params=params)
                if res.status_code != 200:
                    logger.warning(f"Lichess recent games API returned status {res.status_code}: {res.text}")
                    return []

                # Response is NDJSON (newline-delimited JSON)
                for line in res.text.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                        game_id = raw.get("id", "")
                        players = raw.get("players", {})
                        white_info = players.get("white", {})
                        black_info = players.get("black", {})

                        white_user = (
                            white_info.get("user", {}).get("name")
                            or white_info.get("name")
                            or ("AI Level " + str(white_info.get("aiLevel")) if "aiLevel" in white_info else "White")
                        )
                        black_user = (
                            black_info.get("user", {}).get("name")
                            or black_info.get("name")
                            or ("AI Level " + str(black_info.get("aiLevel")) if "aiLevel" in black_info else "Black")
                        )

                        # Determine user's color
                        user_is_white = bool(white_user.lower() == username.lower())
                        user_color = "white" if user_is_white else "black"
                        opponent_info = black_info if user_is_white else white_info
                        opp_user = black_user if user_is_white else white_user

                        # Winner and user result
                        winner = raw.get("winner")  # "white", "black", None (draw)
                        if winner == user_color:
                            result = "win"
                        elif winner is None:
                            result = "draw"
                        else:
                            result = "loss"

                        # Parse moves to UCI format
                        moves_str = raw.get("moves", "")
                        moves_uci = []
                        if moves_str:
                            board = chess.Board()
                            for san_or_uci in moves_str.strip().split():
                                try:
                                    # Try SAN first
                                    m = board.parse_san(san_or_uci)
                                    moves_uci.append(m.uci())
                                    board.push(m)
                                except Exception:
                                    try:
                                        # Fallback to UCI
                                        m = chess.Move.from_uci(san_or_uci)
                                        if m in board.legal_moves:
                                            moves_uci.append(m.uci())
                                            board.push(m)
                                    except Exception:
                                        break

                        # Opening
                        opening_data = raw.get("opening", {})

                        # Time control
                        clock_data = raw.get("clock", {})
                        if clock_data:
                            init_min = clock_data.get("initial", 600) // 60
                            inc_sec = clock_data.get("increment", 0)
                            time_ctrl = f"{init_min}+{inc_sec}"
                        else:
                            time_ctrl = raw.get("speed", "standard").capitalize()

                        created_at = raw.get("createdAt")

                        games.append({
                            "id": game_id,
                            "url": f"https://lichess.org/{game_id}",
                            "user_color": user_color,
                            "user_rating": (white_info if user_is_white else black_info).get("rating"),
                            "opponent": {
                                "username": opp_user,
                                "rating": opponent_info.get("rating"),
                                "title": opponent_info.get("user", {}).get("title"),
                                "is_ai": "aiLevel" in opponent_info,
                            },
                            "result": result,
                            "winner": winner,
                            "end_reason": raw.get("status", "unknown"),
                            "created_at": created_at,
                            "speed": raw.get("speed", "rapid"),
                            "time_control": time_ctrl,
                            "rated": raw.get("rated", False),
                            "opening": {
                                "name": opening_data.get("name", "Standard Chess"),
                                "eco": opening_data.get("eco", ""),
                            },
                            "moves_count": len(moves_uci) // 2 + (len(moves_uci) % 2),
                            "total_plys": len(moves_uci),
                            "moves_uci": moves_uci,
                            "moves_san": moves_str[:120] + ("..." if len(moves_str) > 120 else ""),
                        })
                    except Exception as parse_err:
                        logger.warning(f"Error parsing Lichess game entry: {parse_err}")
                        continue
        except Exception as e:
            logger.error(f"Error fetching recent Lichess games: {e}")

        return games

    async def challenge_ai(
        self,
        state_manager,
        level: int = 3,
        time_mins: int = 10,
        inc_secs: int = 0,
        color: str = "random",
    ) -> bool:
        """Creates an immediate match against Stockfish AI on Lichess."""
        if not self.is_running or not self.client:
            await self.start()

        level = max(1, min(8, int(level)))
        total_seconds = time_mins * 60
        logger.info(
            f"Challenging Stockfish AI Level {level} ({time_mins}m+{inc_secs}s, color={color})..."
        )

        self._cancel_event.clear()
        state_manager.game_status = "SEEKING"

        # Persist AI matchmaking parameters for restart gesture & last game recall
        try:
            from board_hardware import save_settings, settings
            settings["last_game_params"] = {
                "time_control": f"{time_mins}+{inc_secs}",
                "increment": inc_secs,
                "rated": False,
                "color": color,
                "opponent": "ai",
                "ai_level": level,
                "rating_range": None,
            }
            self._save_settings_off_loop(save_settings)
        except Exception as e:
            logger.warning(f"Could not persist last_game_params in challenge_ai(): {e}")

        form_data: dict[str, Any] = {
            "level": str(level),
            "color": color,
        }
        if total_seconds > 0:
            form_data["clock.limit"] = str(total_seconds)
            form_data["clock.increment"] = str(inc_secs)

        headers = self._get_headers()
        try:
            async with self._request_client(headers, 10.0) as client:
                res = await client.post("/api/challenge/ai", data=form_data)
                if res.status_code in [200, 201]:
                    data = res.json()
                    game_id = data.get("id") or data.get("gameId") or data.get("challenge", {}).get("id")
                    if not game_id:
                        logger.error(f"No game ID returned in AI challenge response: {data}")
                        state_manager.game_status = "IDLE"
                        return False

                    logger.info(f"AI Match started! Game ID: {game_id}")
                    self._session_games.add(game_id)
                    self.current_game_id = game_id
                    state_manager.game_status = "PLAYING"
                    if self._stream_task and not self._stream_task.done():
                        self._stream_task.cancel()
                    self._stream_task = asyncio.create_task(
                        self.stream_game(game_id, state_manager)
                    )
                    return True
                else:
                    logger.error(f"Failed to challenge AI: HTTP {res.status_code} - {res.text}")
                    state_manager.game_status = "IDLE"
                    return False
        except Exception as e:
            logger.error(f"Error challenging AI: {e}")
            state_manager.game_status = "IDLE"
            return False

    async def seek(
        self,
        state_manager,
        time_control: str = "10+0",
        rated: bool = False,
        color: str = "random",
        opponent: str = "auto",
        ai_level: int = 3,
        rating_range: str | None = None,
    ) -> bool:
        """Initiates a matchmaking search or AI challenge on Lichess."""
        if not self.is_running or not self.client:
            await self.start()

        time_mins, inc_secs = parse_time_control(time_control)
        estimated_duration_s = time_mins * 60 + inc_secs * 40

        # Automatic Routing: < 8 mins or opponent == "ai" plays against Stockfish AI
        should_play_ai = (opponent == "ai") or (opponent == "auto" and estimated_duration_s < 480)

        if should_play_ai:
            logger.info(
                f"Routing to Stockfish AI level {ai_level} (Estimated duration: {estimated_duration_s}s, opponent='{opponent}')"
            )
            return await self.challenge_ai(
                state_manager,
                level=ai_level,
                time_mins=time_mins,
                inc_secs=inc_secs,
                color=color,
            )

        logger.info(
            f"Seeking live human match: {time_mins}m+{inc_secs}s, rated={rated}, color={color}, ratingRange={rating_range}"
        )

        self._cancel_event.clear()
        state_manager.game_status = "SEEKING"

        # Persist human/auto matchmaking parameters for restart gesture & last game recall
        try:
            from board_hardware import save_settings, settings
            settings["last_game_params"] = {
                "time_control": time_control,
                "increment": inc_secs,
                "rated": bool(rated),
                "color": color,
                "opponent": opponent,
                "ai_level": ai_level,
                "rating_range": rating_range,
            }
            self._save_settings_off_loop(save_settings)
        except Exception as e:
            logger.warning(f"Could not persist last_game_params in seek(): {e}")

        if self._seek_task and not self._seek_task.done():
            self._seek_task.cancel()

        self._seek_task = asyncio.create_task(
            self._seek_and_stream(state_manager, time_mins, inc_secs, rated, color, rating_range=rating_range)
        )
        return True

    async def _seek_and_stream(
        self,
        state_manager,
        time_mins: int,
        inc_secs: int,
        rated: bool,
        color: str,
        rating_range: str | None = None,
    ):
        """Streams the human matchmaking seek response and connects to game stream once matched."""
        form_data = {
            "time": str(time_mins),
            "increment": str(inc_secs),
            "rated": "true" if rated else "false",
            "color": color,
        }
        if rating_range and "-" in str(rating_range):
            form_data["ratingRange"] = str(rating_range).strip()

        headers = self._get_headers()
        headers["Accept"] = "application/x-ndjson"

        try:
            async with self._request_client(headers, None) as client, client.stream(
                "POST", "/api/board/seek", data=form_data
            ) as response:
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
                            logger.debug(f"Seek stream: unparseable line: {line[:200]}")
                            continue

                        event_type = event.get("type")
                        logger.debug(f"Seek stream event: type={event_type}")

                        # Extract game ID
                        game_id = event.get("id") or event.get("gameId") or event.get("game", {}).get("id")
                        if not game_id and event_type == "gameStart":
                            game_id = event.get("game", {}).get("id")

                        if game_id:
                            logger.info(f"Match found! Game ID: {game_id}")
                            self._session_games.add(game_id)
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
            if state_manager and state_manager.game_status == "SEEKING":
                state_manager.game_status = "IDLE"
        except Exception as e:
            logger.error(f"Error during seek streaming: {e}")
            if state_manager and state_manager.game_status == "SEEKING":
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
            async with self._request_client(headers, None) as client, client.stream(
                "GET", f"/api/board/game/stream/{game_id}"
            ) as response:
                if response.status_code != 200:
                    logger.error(f"Failed to stream game {game_id}: HTTP {response.status_code}")
                    if self.current_game_id == game_id and state_manager:
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
                        gone = bool(event.get("gone", False))
                        claim_win = event.get("claimWinInSeconds", 0)
                        logger.info(f"Opponent gone: {gone}, claim win in {claim_win}s")
                        self._handle_opponent_gone(gone, claim_win, state_manager)

        except asyncio.CancelledError:
            logger.info(f"Game stream {game_id} cancelled.")
        except Exception as e:
            logger.error(f"Error in game stream {game_id}: {e}")
        finally:
            logger.info(f"Game stream {game_id} finished.")
            if self._auto_claim_task and not self._auto_claim_task.done():
                self._auto_claim_task.cancel()
                self._auto_claim_task = None
            self.opponent_gone = None
            if self.current_game_id == game_id:
                if self.board and self.board.move_stack:
                    self._record_last_game(state_manager)
                if state_manager and state_manager.game_status == "PLAYING":
                    state_manager.game_status = "IDLE"

    def _record_last_game(self, state_manager=None) -> None:
        """Records the moves and metadata of the most recently finished game for analysis."""
        if not (self.board and self.board.move_stack):
            return

        moves = [m.uci() for m in self.board.move_stack]
        self.last_game_moves = list(moves)
        self.last_game_id = self.current_game_id
        self.last_game_info = dict(self.game_info)
        self.last_game_my_color = self.my_color

        if state_manager:
            state_manager.last_game_moves = list(moves)
            state_manager.last_game_id = self.current_game_id
            state_manager.last_game_metadata = dict(self.game_info)

        try:
            from board_hardware import save_settings, settings
            settings["last_game_moves"] = list(moves)
            settings["last_game_id"] = self.current_game_id
            settings["last_game_my_color"] = self.my_color
            self._save_settings_off_loop(save_settings)
        except Exception as e:
            logger.warning(f"Could not persist last_game_moves to settings: {e}")

    def _handle_opponent_gone(self, gone: bool, claim_win_in: int | float, state_manager):
        """Tracks opponent disconnection and schedules automated victory claiming."""
        if self._auto_claim_task and not self._auto_claim_task.done():
            self._auto_claim_task.cancel()
            self._auto_claim_task = None

        if gone:
            initial_win_in = max(1, int(claim_win_in)) if claim_win_in > 0 else 30
            if self.opponent_gone and self.opponent_gone.get("gone") and "initial_claim_win_in" in self.opponent_gone:
                initial_win_in = self.opponent_gone["initial_claim_win_in"]
                t0 = self.opponent_gone.get("start_time", time.time())
            else:
                t0 = time.time()

            self.opponent_gone = {
                "gone": True,
                "claim_win_in": max(0, int(claim_win_in)),
                "initial_claim_win_in": initial_win_in,
                "start_time": t0,
            }
            if claim_win_in <= 0:
                logger.info("Opponent gone timer expired. Dispatching immediate victory claim...")
                self._auto_claim_task = asyncio.create_task(self.claim_victory(state_manager))
            else:
                logger.info(f"Scheduling automated victory claim in {claim_win_in}s...")
                async def _delayed_claim():
                    try:
                        await asyncio.sleep(claim_win_in)
                        logger.info(f"Auto-claim timer elapsed ({claim_win_in}s). Claiming victory for {self.current_game_id}...")
                        await self.claim_victory(state_manager)
                    except asyncio.CancelledError:
                        pass
                    except Exception as err:
                        logger.error(f"Error in auto-claim task: {err}")

                self._auto_claim_task = asyncio.create_task(_delayed_claim())
        else:
            self.opponent_gone = None

    def _trigger_end_animation(self, state_manager, winner: str | None):
        """Triggers appropriate victory, defeat, or draw animation upon game termination."""
        if not state_manager or not hasattr(state_manager, "trigger_animation"):
            return
        if winner:
            if self.my_color and winner.lower() == self.my_color.lower():
                state_manager.trigger_animation("GAME_WON")
            else:
                state_manager.trigger_animation("GAME_LOST")
        else:
            state_manager.trigger_animation("GAME_DRAWN")

    def _handle_game_full(self, event: dict[str, Any], state_manager):
        """Handles initial game snapshot event."""
        white_info = event.get("white", {})
        black_info = event.get("black", {})

        my_user = (self.username or "").lower()
        white_user = (white_info.get("name") or white_info.get("id") or "").lower()
        black_user = (black_info.get("name") or black_info.get("id") or "").lower()

        # Check AI indicator if applicable
        if white_info.get("aiLevel"):
            self.my_color = "black"
        elif black_info.get("aiLevel") or my_user and my_user == white_user:
            self.my_color = "white"
        elif my_user and my_user == black_user:
            self.my_color = "black"
        else:
            self.my_color = "white"  # Default fallback

        opp_info = black_info if self.my_color == "white" else white_info
        if opp_info.get("aiLevel"):
            opponent = {
                "username": f"Stockfish AI Level {opp_info.get('aiLevel')}",
                "rating": 1500,
                "title": "BOT",
            }
        else:
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
        self.initial_clocks_ms = {"white": wtime, "black": btime}
        self.clocks_updated_at = time.time()
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
            self._record_last_game(state_manager)
            state_manager.game_status = "IDLE"
            self._trigger_end_animation(state_manager, state_data.get("winner"))
        else:
            if state_manager:
                state_manager.game_status = "PLAYING"
            if state_manager and hasattr(state_manager, "move_tracker") and state_manager.move_tracker:
                state_manager.move_tracker.reset(getattr(state_manager, "physical_state", None))
            if state_manager and hasattr(state_manager, "trigger_animation"):
                state_manager.trigger_animation("GAME_STARTED", {"my_color": self.my_color})

    def _handle_game_state(self, event: dict[str, Any], state_manager):
        """Handles differential move/clock updates."""
        moves_str = event.get("moves", "")
        self._apply_moves(moves_str)

        wtime = event.get("wtime")
        btime = event.get("btime")
        self.raw_clocks_ms = {"white": wtime, "black": btime}
        self.clocks_updated_at = time.time()
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
            self._record_last_game(state_manager)
            state_manager.game_status = "IDLE"
            self._trigger_end_animation(state_manager, winner)

    def _apply_moves(self, moves_str: str):
        """Reconstructs internal chess.Board from space-separated UCI move sequence."""
        self.board = chess.Board()
        self._last_move_cache = (0, False)
        if moves_str:
            for uci in moves_str.strip().split():
                try:
                    move = chess.Move.from_uci(uci)
                    if move in self.board.legal_moves:
                        self._last_move_cache = (len(self.board.move_stack) + 1, self.board.is_capture(move))
                        self.board.push(move)
                    else:
                        logger.warning(f"Move {uci} not legal in reconstructed position; pushing anyway to stay in sync.")
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

        return {
            "game_id": self.current_game_id,
            "rated": self.game_info.get("rated", False),
            "speed": self.game_info.get("speed"),
            "turn": "white" if self.board.turn == chess.WHITE else "black",
            "my_color": self.my_color,
            "opponent": self.game_info.get("opponent", {}),
            "opponent_gone": self.opponent_gone,
            "last_move": last_move_uci,
            "last_move_is_capture": last_move_is_capture,
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
            async with self._request_client(headers, 5.0) as client:
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

    async def claim_victory(self, state_manager=None) -> bool:
        """Claims victory on an abandoned game via POST /api/board/game/{game_id}/claim-victory."""
        if self._auto_claim_task and not self._auto_claim_task.done() and asyncio.current_task() != self._auto_claim_task:
            self._auto_claim_task.cancel()
            self._auto_claim_task = None

        if not self.current_game_id:
            logger.warning("No active game ID to claim victory.")
            return False

        headers = self._get_headers()
        try:
            async with self._request_client(headers, 5.0) as client:
                res = await client.post(f"/api/board/game/{self.current_game_id}/claim-victory")
                if res.status_code in [200, 201]:
                    logger.info(f"Victory claimed successfully for game {self.current_game_id}!")
                    self.game_info["is_game_over"] = True
                    self.game_info["winner"] = self.my_color
                    self.game_info["end_reason"] = "opponent_left"
                    self._record_last_game(state_manager)
                    self.opponent_gone = None
                    if self._auto_claim_task and not self._auto_claim_task.done():
                        self._auto_claim_task.cancel()
                        self._auto_claim_task = None
                    if state_manager:
                        state_manager.game_status = "IDLE"
                        if hasattr(state_manager, "trigger_animation"):
                            state_manager.trigger_animation("GAME_WON")
                    return True
                else:
                    logger.warning(f"Failed to claim victory: HTTP {res.status_code} - {res.text}")
                    return False
        except Exception as e:
            logger.error(f"Error claiming victory: {e}")
            return False

    async def resign(self, state_manager) -> bool:
        """Resigns the active game via POST /api/board/game/{game_id}/resign."""
        if self._auto_claim_task and not self._auto_claim_task.done():
            self._auto_claim_task.cancel()
            self._auto_claim_task = None
        self.opponent_gone = None

        if not self.current_game_id:
            return False

        headers = self._get_headers()
        try:
            async with self._request_client(headers, 5.0) as client:
                res = await client.post(f"/api/board/game/{self.current_game_id}/resign")
                if res.status_code == 200:
                    self.game_info["is_game_over"] = True
                    self.game_info["winner"] = "black" if self.my_color == "white" else "white"
                    self.game_info["end_reason"] = "resign"
                    self._record_last_game(state_manager)
                    state_manager.game_status = "IDLE"
                    if state_manager and hasattr(state_manager, "trigger_animation"):
                        state_manager.trigger_animation("GAME_LOST")
                    return True
                logger.warning(f"Failed to resign game: HTTP {res.status_code} - {res.text}")
                return False
        except Exception as e:
            logger.error(f"Error resigning game: {e}")
            return False

    async def abort(self, state_manager) -> bool:
        """Aborts the active game via POST /api/board/game/{game_id}/abort."""
        if self._auto_claim_task and not self._auto_claim_task.done():
            self._auto_claim_task.cancel()
            self._auto_claim_task = None
        self.opponent_gone = None

        if not self.current_game_id:
            return False

        headers = self._get_headers()
        try:
            async with self._request_client(headers, 5.0) as client:
                res = await client.post(f"/api/board/game/{self.current_game_id}/abort")
                if res.status_code == 200:
                    self.game_info["is_game_over"] = True
                    self.game_info["end_reason"] = "abort"
                    self._record_last_game(state_manager)
                    state_manager.game_status = "IDLE"
                    return True
                logger.warning(f"Failed to abort game: HTTP {res.status_code} - {res.text}")
                return False
        except Exception as e:
            logger.error(f"Error aborting game: {e}")
            return False

    async def draw(self, state_manager, accept: bool = True) -> bool:
        """Offers or accepts a draw via POST /api/board/game/{game_id}/draw/{yes/no}."""
        if not self.current_game_id:
            return False

        action = "yes" if accept else "no"
        headers = self._get_headers()
        try:
            async with self._request_client(headers, 5.0) as client:
                res = await client.post(f"/api/board/game/{self.current_game_id}/draw/{action}")
                return res.status_code == 200
        except Exception as e:
            logger.error(f"Error offering/accepting draw: {e}")
            return False

    async def cancel(self, state_manager):
        """Cancels an active seek or resigns an ongoing game."""
        if self._auto_claim_task and not self._auto_claim_task.done():
            self._auto_claim_task.cancel()
            self._auto_claim_task = None
        self.opponent_gone = None

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
