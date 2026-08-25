"""
app/main.py

FastAPI backend server for the Smart Chess Board.
Provides WebSocket real-time state broadcast, REST endpoints for hardware settings,
Lichess Board API proxying, move execution, and frontend static asset delivery.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from board_hardware import settings
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .board_state import state_manager
from .coach_engine import coach_engine
from .gm_games import get_all_gm_games
from .lichess_engine import lichess_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart-chess-app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting background state manager loop, Lichess engine, and Coach engine...")
    await lichess_engine.start(state_manager)
    await coach_engine.start()
    task = asyncio.create_task(
        state_manager.update_loop(manager.broadcast, manager.client_count)
    )
    yield
    logger.info("Stopping background loop, Lichess engine, and Coach engine...")
    task.cancel()
    await coach_engine.stop()
    await lichess_engine.stop()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Smart Chess Board API", lifespan=lifespan)

# Allow CORS for mobile app, PWA, and external browsers (same-origin appliance; no credentials)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- WebSocket Connection Manager ---
class ConnectionManager:
    """Tracks WebSocket clients with per-connection outgoing queues so a slow or
    stalled client can never block the hardware update loop or other clients."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._queues: dict[WebSocket, asyncio.Queue] = {}
        self._sender_tasks: dict[WebSocket, asyncio.Task] = {}

    def client_count(self) -> int:
        return len(self.active_connections)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._queues[websocket] = queue
        self._sender_tasks[websocket] = asyncio.create_task(self._sender(websocket, queue))

    async def _sender(self, websocket: WebSocket, queue: asyncio.Queue):
        try:
            while True:
                message = await queue.get()
                await websocket.send_json(message)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug(f"WebSocket sender terminated: {e}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self._queues.pop(websocket, None)
        task = self._sender_tasks.pop(websocket, None)
        if task and not task.done():
            task.cancel()

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            queue = self._queues.get(connection)
            if queue is None:
                continue
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.debug("Dropping slow WebSocket client (queue full).")
                self.disconnect(connection)


manager = ConnectionManager()


# --- Pydantic Request Models ---
class ThresholdSettings(BaseModel):
    threshold_positive: int | float | None = None
    threshold_negative: int | float | None = None
    col_mode: str | None = None
    manual_col: int | float | None = None
    scan_delay: int | float | None = None
    mux_settle_ms: int | float | None = None
    mux_settle_us: int | float | None = None
    debounce_threshold: int | float | None = None
    baseline_window_s: int | float | None = None
    disabled_squares: list[list[int]] | None = None
    pieces_mode: str | None = None  # "auto" | "pieces" | "empty"
    coach_hints_enabled: bool | None = None
    eval_bar_enabled: bool | None = None
    clock_bar_enabled: bool | None = None
    coach_ai_only: bool | None = None
    in_loop_calibration: bool | None = None
    led_intensity: int | float | None = None
    night_mode: bool | None = None
    auto_queen_timeout_s: int | float | None = None
    opening_hints_enabled: bool | None = None
    max_sideline_hints: int | None = None


class PromoteRequest(BaseModel):
    piece: str = "q"  # "q" | "n" | "r" | "b"


class SaveDefaultsRequest(ThresholdSettings):
    baselines: list[list[int]] | None = None
    overwrite_template: bool = True


class CalibrateSquareRequest(BaseModel):
    col: int
    row: int
    value: int | float | None = None


class TriggerAnimationRequest(BaseModel):
    name: str
    params: dict | None = None


class TestTraceRequest(BaseModel):
    uci: str | None = None
    from_pos: list[int] | None = None
    to_pos: list[int] | None = None
    is_capture: bool | None = False
    clear: bool | None = False


class SeekRequest(BaseModel):
    time_control: str | None = "10+0"
    increment: int | None = 0
    rated: bool | None = False
    color: str | None = "random"
    opponent: str | None = "auto"
    ai_level: int | None = 3
    rating_range: str | None = None


class MoveRequest(BaseModel):
    from_square: str
    to_square: str
    promotion: str | None = None


class DrawRequest(BaseModel):
    accept: bool = True


class ModeRequest(BaseModel):
    virtual_only: bool


class StartLocalGameRequest(BaseModel):
    fen: str | None = None


class StopLocalGameRequest(BaseModel):
    winner: str | None = None
    reason: str = "resignation"


class StartAnalysisRequest(BaseModel):
    moves_uci: list[str] | None = None
    game_id: str | None = None


class StepAnalysisRequest(BaseModel):
    ply: int


class AnalysisNavRequest(BaseModel):
    direction: str


class StartBlunderDrillRequest(BaseModel):
    index: int = 0


class BlunderAttemptRequest(BaseModel):
    uci: str


class StartGMRequest(BaseModel):
    game_id: str


class StartReplayRecallRequest(BaseModel):
    moves_uci: list[str] | None = None


class AnalysisMoveRequest(BaseModel):
    uci: str


# --- Helper Functions ---
def parse_sq(sq: str) -> tuple[int, int] | None:
    """Parses standard algebraic chess notation (e.g. 'e4') into 1-indexed (file, rank)."""
    sq = sq.strip().lower()
    if len(sq) != 2:
        return None
    file_ch, rank_ch = sq[0], sq[1]
    if file_ch not in "abcdefgh" or rank_ch not in "12345678":
        return None
    return ord(file_ch) - ord("a") + 1, int(rank_ch)


def apply_settings(body: ThresholdSettings) -> None:
    """Applies non-None fields of a settings request onto the shared settings dict."""
    if body.threshold_positive is not None:
        settings["threshold_positive"] = int(body.threshold_positive)
    if body.threshold_negative is not None:
        settings["threshold_negative"] = int(body.threshold_negative)
    if body.col_mode is not None:
        settings["col_mode"] = body.col_mode
    if body.manual_col is not None:
        settings["manual_col"] = int(body.manual_col)
    if body.scan_delay is not None:
        settings["scan_delay"] = int(body.scan_delay)
    if body.mux_settle_us is not None:
        settle_us = min(255, max(0, int(body.mux_settle_us)))
        settings["mux_settle_us"] = settle_us
        settings["mux_settle_ms"] = settle_us / 1000
    elif body.mux_settle_ms is not None:
        raw_val = int(body.mux_settle_ms)
        settle_us = min(255, max(0, raw_val if raw_val > 50 else raw_val * 1000))
        settings["mux_settle_us"] = settle_us
        settings["mux_settle_ms"] = raw_val
    if body.debounce_threshold is not None:
        settings["debounce_threshold"] = int(body.debounce_threshold)
    if body.baseline_window_s is not None:
        settings["baseline_window_s"] = int(body.baseline_window_s)
    if body.disabled_squares is not None:
        settings["disabled_squares"] = body.disabled_squares
    if body.pieces_mode is not None:
        settings["pieces_mode"] = body.pieces_mode
    if body.coach_hints_enabled is not None:
        settings["coach_hints_enabled"] = bool(body.coach_hints_enabled)
    if body.eval_bar_enabled is not None:
        settings["eval_bar_enabled"] = bool(body.eval_bar_enabled)
    if body.clock_bar_enabled is not None:
        settings["clock_bar_enabled"] = bool(body.clock_bar_enabled)
    if body.coach_ai_only is not None:
        settings["coach_ai_only"] = bool(body.coach_ai_only)
    if body.in_loop_calibration is not None:
        settings["in_loop_calibration"] = bool(body.in_loop_calibration)
    if body.led_intensity is not None:
        settings["led_intensity"] = min(100, max(10, int(body.led_intensity)))
    if body.night_mode is not None:
        settings["night_mode"] = bool(body.night_mode)
    if body.opening_hints_enabled is not None:
        settings["opening_hints_enabled"] = bool(body.opening_hints_enabled)


# --- REST API Endpoints ---

@app.get("/api")
async def api_root():
    return {"status": "ok", "message": "Smart Chess Board API is operational"}


@app.get("/api/lichess/account")
async def get_lichess_account():
    """Returns profile and ratings for the authenticated Lichess account."""
    return await lichess_engine.get_account()


@app.get("/api/lichess/games/recent")
async def get_recent_lichess_games(username: str | None = None, max_games: int = 10):
    """Fetches and parses the user's recent finished Lichess games for Analysis mode."""
    games = await lichess_engine.get_user_recent_games(username=username, max_games=max_games)
    return {"status": "success", "games": games}


@app.get("/api/board/physical")
async def get_physical_board():
    """Returns the current sensor state of the physical board."""
    return state_manager.get_physical_payload()


@app.get("/api/board/health")
async def get_board_health():
    """Returns diagnostic health metrics for all subsystems."""
    return state_manager.get_health_status()


@app.get("/api/board/settings")
async def get_board_settings():
    """Returns current calibration settings."""
    return settings


@app.post("/api/board/settings")
async def update_board_settings(body: ThresholdSettings):
    """Updates analog thresholds, scan timings, and active column configurations."""
    from board_hardware import save_settings
    apply_settings(body)
    await asyncio.to_thread(save_settings)
    return {"status": "success", "settings": settings}


@app.post("/api/board/save_defaults")
async def save_board_defaults_route(body: SaveDefaultsRequest | None = None):
    """
    Saves all current stats (baselines, thresholds, settings) to persistent storage
    (board_settings.json) as the defaults for future connections.
    """
    from board_hardware import get_settings_filepath, save_defaults
    if body is not None:
        apply_settings(body)
        if body.baselines is not None and isinstance(body.baselines, list) and len(body.baselines) == 8:
            settings["baselines"] = body.baselines

    await asyncio.to_thread(save_defaults)
    filepath = get_settings_filepath()
    logger.info(f"Explicitly saved board defaults to {filepath}")
    return {
        "status": "success",
        "message": f"Successfully saved current stats (64 baselines & thresholds) to {filepath}",
        "file": filepath,
        "settings": settings,
    }


@app.post("/api/board/calibrate")
async def calibrate_board_route():
    """Triggers sensor matrix baseline recalibration."""
    success = await asyncio.to_thread(state_manager._safe_calibrate)
    if success:
        return {"status": "success", "message": "Calibration completed", "settings": settings}
    else:
        return {"status": "error", "message": "Calibration failed"}


@app.post("/api/board/calibrate_with_pieces")
async def calibrate_board_with_pieces_route():
    """Triggers baseline calibration using empty middle ranks mapped to starting ranks."""
    success = await asyncio.to_thread(state_manager._safe_calibrate_with_pieces)
    if success:
        return {"status": "success", "message": "Calibration with pieces completed", "settings": settings}
    else:
        return {"status": "error", "message": "Calibration failed"}


@app.post("/api/board/calibrate_square")
async def calibrate_square_route(body: CalibrateSquareRequest):
    """Sets the baseline value of a specific square to its current raw analog reading (or given value)."""
    from board_hardware import BOARD_COLS, BOARD_ROWS, save_settings, set_square_baseline
    if 0 <= body.col < BOARD_COLS and 0 <= body.row < BOARD_ROWS:
        if body.value is not None:
            new_baseline = int(body.value)
        else:
            # Fallback to latest raw reading from state_manager
            new_baseline = int(state_manager.raw_analog_values[body.col][body.row])

        set_square_baseline(body.col, body.row, new_baseline)
        await asyncio.to_thread(save_settings)
        return {
            "status": "success",
            "col": body.col,
            "row": body.row,
            "baseline": new_baseline,
            "settings": settings,
        }
    return {"status": "error", "message": "Invalid coordinates"}


@app.post("/api/board/test_leds")
async def test_leds_route():
    """Runs a sequential animation testing all WS2812B LEDs."""
    state_manager._spawn_task(state_manager.run_led_test())
    return {"status": "success", "message": "LED test initiated"}


@app.post("/api/board/clear_leds")
async def clear_leds_route():
    """Turns off all physical LEDs."""
    success = await asyncio.to_thread(state_manager.clear_all_leds)
    if success:
        return {"status": "success", "message": "All LEDs turned off"}
    else:
        return {"status": "error", "message": "Failed to clear LEDs"}


@app.post("/api/leds/trigger_animation")
async def trigger_animation_route(body: TriggerAnimationRequest):
    """
    Triggers a procedural full-board lifecycle animation.
    Supported names: 'GAME_STARTED', 'GAME_WON', 'GAME_LOST', 'GAME_DRAWN', 'SEEKING', 'WAITING_FOR_OPPONENT'.
    """
    success = state_manager.trigger_animation(body.name, body.params)
    if success:
        return {"status": "success", "animation": body.name}
    return {"status": "error", "message": f"Failed to trigger animation '{body.name}'"}


@app.post("/api/leds/test_trace")
async def test_trace_route(body: TestTraceRequest):
    """
    Tests move path interpolation and animated trace between squares.
    Accepts:
      - {"uci": "e2e4", "is_capture": false}
      - {"from_pos": [4, 1], "to_pos": [4, 3], "is_capture": true}
      - {"clear": true}
    """
    from app.path_interpolator import interpolate_move_path, interpolate_uci_move

    if body.clear:
        state_manager.custom_trace_path = None
        state_manager.custom_trace_is_capture = False
        return {"status": "success", "message": "Custom trace cleared"}

    path = []
    if body.uci:
        path = interpolate_uci_move(body.uci)
    elif body.from_pos and body.to_pos and len(body.from_pos) == 2 and len(body.to_pos) == 2:
        try:
            fc, fr = int(body.from_pos[0]), int(body.from_pos[1])
            tc, tr = int(body.to_pos[0]), int(body.to_pos[1])
            if 0 <= fc < 8 and 0 <= fr < 8 and 0 <= tc < 8 and 0 <= tr < 8:
                path = interpolate_move_path(fc, fr, tc, tr)
            else:
                return {"status": "error", "message": "Coordinates must be between 0 and 7"}
        except (ValueError, TypeError):
            return {"status": "error", "message": "Invalid integer coordinates provided"}
    else:
        return {
            "status": "error",
            "message": "Provide 'uci' (e.g. 'e2e4') or 'from_pos' and 'to_pos' [col, row] coordinates",
        }

    state_manager.custom_trace_path = path
    state_manager.custom_trace_is_capture = bool(body.is_capture)
    return {"status": "success", "path": path, "is_capture": state_manager.custom_trace_is_capture}


@app.get("/api/board/digital")
async def get_digital_board():
    """Returns 8x8 piece grid representing the active digital board position."""
    return {"grid": state_manager.digital_state}


# --- Game Matchmaking & Interaction Endpoints ---

@app.post("/api/game/seek")
async def seek_game_route(body: SeekRequest | None = None):
    """Initiates an online matchmaking seek or Stockfish AI challenge on Lichess."""
    if state_manager.game_status == "ANALYSIS":
        state_manager.stop_analysis_mode()
    elif state_manager.game_status not in ["IDLE", "GAME_OVER"]:
        return {"status": "error", "message": f"Cannot seek while status is {state_manager.game_status}"}

    tc = body.time_control if body and body.time_control else "10+0"
    rated = body.rated if body and body.rated is not None else False
    color = body.color if body and body.color else "random"
    opponent = body.opponent if body and body.opponent else "auto"
    ai_level = body.ai_level if body and body.ai_level is not None else 3
    rating_range = body.rating_range if body and body.rating_range else None

    await lichess_engine.seek(
        state_manager,
        time_control=tc,
        rated=rated,
        color=color,
        opponent=opponent,
        ai_level=ai_level,
        rating_range=rating_range,
    )
    return {
        "status": "seeking_initiated",
        "time_control": tc,
        "rated": rated,
        "color": color,
        "opponent": opponent,
        "ai_level": ai_level,
        "rating_range": rating_range,
    }


@app.get("/api/game/last_params")
async def get_last_game_params_route():
    """Returns the stored last game matchmaking parameters from board settings."""
    last_params = settings.get("last_game_params")
    return {"status": "success", "last_game_params": last_params}


@app.post("/api/game/restart_previous")
async def restart_previous_game_route():
    """Restarts a game using the persisted last_game_params (or standard defaults)."""
    if state_manager.game_status == "ANALYSIS":
        state_manager.stop_analysis_mode()
    elif state_manager.game_status not in ["IDLE", "GAME_OVER"]:
        return {"status": "error", "message": f"Cannot restart game while status is {state_manager.game_status}"}

    from board_hardware import get_last_game_params
    params = get_last_game_params()

    await lichess_engine.seek(state_manager, **params)
    return {
        "status": "seeking_initiated",
        "restarted": True,
        "params": params,
    }


@app.post("/api/game/cancel")
async def cancel_game_route():
    """Cancels the active seek or resigns the ongoing game."""
    await lichess_engine.cancel(state_manager)
    return {"status": "cancelled"}


@app.post("/api/game/move")
async def make_move_route(body: MoveRequest):
    """Submits a move to the active Lichess game or active Analysis session."""
    if state_manager.game_status == "ANALYSIS":
        src = parse_sq(body.from_square)
        dst = parse_sq(body.to_square)
        if not src or not dst:
            return {"status": "error", "message": "Invalid square coordinates"}
        from_sq = body.from_square.lower().strip()
        to_sq = body.to_square.lower().strip()
        uci = f"{from_sq}{to_sq}{body.promotion or ''}"
        res = state_manager.handle_analysis_move(uci)
        return {"status": "success", "analysis": res}

    if state_manager.game_status != "PLAYING":
        return {"status": "error", "message": "No active game"}

    src = parse_sq(body.from_square)
    dst = parse_sq(body.to_square)
    if not src or not dst:
        return {"status": "error", "message": "Invalid square coordinates"}

    if hasattr(state_manager, "local_engine") and state_manager.local_engine.is_active:
        from_sq = body.from_square.lower().strip()
        to_sq = body.to_square.lower().strip()
        uci = f"{from_sq}{to_sq}{body.promotion or ''}"
        success = state_manager.local_engine.apply_move(uci)
        if success:
            state_manager.digital_state = state_manager.local_engine.get_board()
            if state_manager.local_engine.is_game_over:
                state_manager._record_last_game_from_local()
                state_manager.game_status = "GAME_OVER"
                if state_manager.local_engine.winner in ("white", "black"):
                    state_manager.trigger_animation("GAME_WON")
                else:
                    state_manager.trigger_animation("GAME_DRAWN")
            return {"status": "success"}
        return {"status": "error", "message": "Illegal move for local match"}

    success = await lichess_engine.make_move(
        src[0], src[1], dst[0], dst[1], promotion=body.promotion
    )
    if success:
        return {"status": "success"}
    else:
        return {"status": "error", "message": "Move was rejected by Lichess"}


@app.post("/api/game/local/start")
async def start_local_game_route(body: StartLocalGameRequest | None = None):
    """Starts a new local two-player game session."""
    fen = body.fen if body else None
    return state_manager.start_local_game(fen=fen)


@app.post("/api/game/local/stop")
async def stop_local_game_route(body: StopLocalGameRequest | None = None):
    """Concludes or resigns the active local two-player game session."""
    winner = body.winner if body else None
    reason = body.reason if body else "resignation"
    return state_manager.stop_local_game(winner=winner, reason=reason)


@app.post("/api/game/promote")
async def promote_piece_route(body: PromoteRequest):
    """Resolves an active pending physical promotion with a chosen piece ('q', 'n', 'r', 'b')."""
    piece = body.piece.lower()
    if piece not in ("q", "n", "r", "b"):
        piece = "q"
    success = state_manager.resolve_pending_promotion(piece)
    if success:
        return {"status": "success", "piece": piece}
    return {"status": "error", "message": "No active pending promotion or promotion rejected."}


@app.get("/api/openings/lookup")
def lookup_opening_route(moves: str = ""):
    """Look up opening ECO classification and candidate book moves for a comma-separated list of UCI moves."""
    from app.openings import lookup_opening_by_moves
    move_list = [m.strip() for m in moves.split(",") if m.strip()]
    info = lookup_opening_by_moves(move_list)
    return info.to_dict()


@app.post("/api/game/resign")
async def resign_game_route():
    """Resigns the active game on Lichess or local session."""
    if state_manager.game_status != "PLAYING":
        return {"status": "error", "message": "No active game to resign"}

    if hasattr(state_manager, "local_engine") and state_manager.local_engine.is_active:
        import chess
        cur_turn = state_manager.local_engine.board.turn
        loser_color = "white" if cur_turn == chess.WHITE else "black"
        winner_color = "black" if loser_color == "white" else "white"
        return state_manager.stop_local_game(winner=winner_color, reason="resignation")

    success = await lichess_engine.resign(state_manager)
    return {"status": "resigned" if success else "error"}


@app.post("/api/lichess/claim-victory")
@app.post("/api/game/claim-victory")
async def claim_victory_route():
    """Claims victory when an opponent disconnects on Lichess."""
    if state_manager.game_status != "PLAYING":
        return {"status": "error", "message": "No active game to claim victory"}

    success = await lichess_engine.claim_victory(state_manager)
    return {"status": "claimed" if success else "error"}


@app.post("/api/game/draw")
async def draw_game_route(body: DrawRequest | None = None):
    """Offers or accepts a draw on Lichess or local session."""
    if state_manager.game_status != "PLAYING":
        return {"status": "error", "message": "No active game to offer draw"}

    if hasattr(state_manager, "local_engine") and state_manager.local_engine.is_active:
        return state_manager.stop_local_game(winner="draw", reason="draw_agreement")

    accept = body.accept if body else True
    success = await lichess_engine.draw(state_manager, accept=accept)
    return {"status": "success" if success else "error"}


@app.post("/api/game/mode")
async def set_game_mode_route(body: ModeRequest):
    """Switches between Hardware-Integrated and Virtual-Only simulation modes."""
    state_manager.virtual_only = body.virtual_only
    if body.virtual_only and state_manager.strip:
        state_manager.clear_all_leds()
    return {"status": "success", "virtual_only": state_manager.virtual_only}


# --- Analysis & Training Mode Endpoints ---

@app.post("/api/analysis/start")
async def start_analysis_route(body: StartAnalysisRequest | None = None):
    """Activates post-game analysis on the last game or custom moves / GM game."""
    moves = body.moves_uci if body else None
    game_id = body.game_id if body else None
    return await state_manager.start_analysis_mode(moves_uci=moves, game_id=game_id)


@app.post("/api/analysis/step")
async def step_analysis_route(body: StepAnalysisRequest):
    """Steps to a specific move index in the game review."""
    return state_manager.step_analysis(body.ply)


@app.post("/api/analysis/nav")
async def navigate_analysis_route(body: AnalysisNavRequest):
    """Keyboard navigation for web-only analysis: back/forward/start/end (branch-aware)."""
    return state_manager.navigate_analysis(body.direction)


@app.post("/api/analysis/branch_reset")
async def reset_analysis_branch_route():
    """Snaps back from a virtual analysis branch to the main game timeline."""
    return state_manager.reset_analysis_branch()


@app.post("/api/analysis/stop")
async def stop_analysis_route():
    """Exits analysis/training mode and returns the board to IDLE."""
    return state_manager.stop_analysis_mode()


@app.get("/api/analysis/state")
async def get_analysis_state_route():
    """Returns the current analysis state, evaluations, and mistake metrics."""
    return state_manager.get_analysis_payload()


@app.get("/api/analysis/gm/games")
async def get_gm_games_route():
    """Returns the library of historical Grandmaster masterpieces."""
    return [g.to_dict() for g in get_all_gm_games()]


@app.post("/api/analysis/gm/start")
async def start_gm_game_route(body: StartGMRequest):
    """Starts a Replay Trainer learn session for a specific GM game."""
    return state_manager.start_gm_game(body.game_id)


@app.post("/api/analysis/replay/recall")
async def start_replay_recall_route(body: StartReplayRecallRequest | None = None):
    """Starts a memory recall session directly (no learn phase) on the last played game."""
    moves = body.moves_uci if body else None
    return await state_manager.start_replay_recall(moves)


@app.post("/api/analysis/blunder_drill/start")
async def start_blunder_drill_route(body: StartBlunderDrillRequest | None = None):
    """Starts interactive Blunder Blitz training on game mistakes."""
    idx = body.index if body else 0
    return state_manager.start_blunder_drill(idx)


@app.post("/api/analysis/blunder_drill/attempt")
async def submit_blunder_attempt_route(body: BlunderAttemptRequest):
    """Evaluates a tactical puzzle attempt in Blunder Blitz mode."""
    return state_manager.submit_blunder_attempt(body.uci)


@app.post("/api/analysis/blunder_drill/hint")
async def toggle_blunder_hint_route():
    """Toggles LED hint on the board for the active blunder challenge."""
    return {"hint_active": state_manager.toggle_blunder_hint()}


@app.post("/api/analysis/move")
async def analysis_move_route(body: AnalysisMoveRequest):
    """Executes a web move in Analysis mode (passive board): auto-advances on game moves or branches on alternatives."""
    res = state_manager.handle_analysis_move(body.uci, source="web")
    return {"status": "success", "result": res}


# --- WebSocket Stream ---

@app.websocket("/ws/state")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        initial_payload = state_manager.get_full_state()
        queue = manager._queues.get(websocket)
        if queue is not None:
            queue.put_nowait(initial_payload)
    except Exception as e:
        logger.debug(f"Error queueing initial state snapshot on websocket connect: {e}")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WebSocket receive loop terminated: {e}")
    finally:
        manager.disconnect(websocket)


# --- Frontend Static Assets Serving ---

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.exists(frontend_path):
    _frontend_real_path = os.path.realpath(frontend_path)

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api") or full_path.startswith("ws"):
            raise HTTPException(status_code=404)

        file_path = os.path.realpath(os.path.join(frontend_path, full_path))
        if full_path and os.path.isfile(file_path) and file_path.startswith(_frontend_real_path + os.sep):
            return FileResponse(file_path)

        return FileResponse(os.path.join(frontend_path, "index.html"))
else:
    logger.warning(f"Frontend build not found at {frontend_path}. Operating in API-only mode.")

    @app.get("/")
    async def api_fallback():
        return {"status": "api-only", "warning": "Frontend assets not built in dist/"}
