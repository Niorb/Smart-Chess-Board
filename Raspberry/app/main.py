"""
app/main.py

FastAPI backend server for the Smart Chess Board.
Provides WebSocket real-time state broadcast, REST endpoints for hardware settings,
Lichess Board API proxying, move execution, and frontend static asset delivery.
"""

import asyncio
from contextlib import asynccontextmanager
import logging
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .board_state import state_manager
from .coach_engine import coach_engine
from .lichess_engine import lichess_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart-chess-app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting background state manager loop, Lichess engine, and Coach engine...")
    await lichess_engine.start(state_manager)
    await coach_engine.start()
    task = asyncio.create_task(state_manager.update_loop(manager.broadcast))
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

# Allow CORS for mobile app, PWA, and external browsers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- WebSocket Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        stale_connections = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                stale_connections.append(connection)
        for dead in stale_connections:
            if dead in self.active_connections:
                self.active_connections.remove(dead)


manager = ConnectionManager()


# --- Pydantic Request Models ---
class ThresholdSettings(BaseModel):
    threshold_positive: int | float | None = None
    threshold_negative: int | float | None = None
    col_mode: str | None = None
    manual_col: int | float | None = None
    scan_delay: int | float | None = None
    mux_settle_ms: int | float | None = None
    debounce_threshold: int | float | None = None
    baseline_window_s: int | float | None = None
    disabled_squares: list[list[int]] | None = None
    pieces_mode: str | None = None  # "auto" | "pieces" | "empty"
    coach_hints_enabled: bool | None = None
    eval_bar_enabled: bool | None = None
    coach_ai_only: bool | None = None
    in_loop_calibration: bool | None = None


class HighlightRequest(BaseModel):
    col: int
    row: int


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


# --- REST API Endpoints ---

@app.get("/api")
async def api_root():
    return {"status": "ok", "message": "Smart Chess Board API is operational"}


@app.get("/api/lichess/account")
async def get_lichess_account():
    """Returns profile and ratings for the authenticated Lichess account."""
    return await lichess_engine.get_account()


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
    from board_hardware import settings
    return settings


@app.post("/api/board/settings")
async def update_board_settings(body: ThresholdSettings):
    """Updates analog thresholds, scan timings, and active column configurations."""
    from board_hardware import save_settings, settings
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
    if body.mux_settle_ms is not None:
        settings["mux_settle_ms"] = int(body.mux_settle_ms)
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
    if body.coach_ai_only is not None:
        settings["coach_ai_only"] = bool(body.coach_ai_only)
    if body.in_loop_calibration is not None:
        settings["in_loop_calibration"] = bool(body.in_loop_calibration)
    await asyncio.to_thread(save_settings)
    return {"status": "success", "settings": settings}


@app.post("/api/board/calibrate")
async def calibrate_board_route():
    """Triggers sensor matrix baseline recalibration."""
    success = await asyncio.to_thread(state_manager._safe_calibrate)
    if success:
        from board_hardware import settings
        return {"status": "success", "message": "Calibration completed", "settings": settings}
    else:
        return {"status": "error", "message": "Calibration failed"}


@app.post("/api/board/calibrate_with_pieces")
async def calibrate_board_with_pieces_route():
    """Triggers baseline calibration using empty middle ranks mapped to starting ranks."""
    success = await asyncio.to_thread(state_manager._safe_calibrate_with_pieces)
    if success:
        from board_hardware import settings
        return {"status": "success", "message": "Calibration with pieces completed", "settings": settings}
    else:
        return {"status": "error", "message": "Calibration failed"}


@app.post("/api/board/highlight")
async def highlight_square_route(body: HighlightRequest):
    """Highlights or toggles an LED indicator on a board square."""
    current = state_manager.highlighted_square
    if current == (body.col, body.row):
        state_manager.highlighted_square = None
    else:
        state_manager.highlighted_square = (body.col, body.row)
    return {"status": "success", "highlighted_square": state_manager.highlighted_square}


@app.post("/api/board/test_leds")
async def test_leds_route():
    """Runs a sequential animation testing all WS2812B LEDs."""
    asyncio.create_task(state_manager.run_led_test())
    return {"status": "success", "message": "LED test initiated"}


@app.post("/api/board/clear_leds")
async def clear_leds_route():
    """Turns off all physical LEDs."""
    success = state_manager.clear_all_leds()
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
    if state_manager.game_status not in ["IDLE", "GAME_OVER"]:
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


@app.post("/api/game/cancel")
async def cancel_game_route():
    """Cancels the active seek or resigns the ongoing game."""
    await lichess_engine.cancel(state_manager)
    return {"status": "cancelled"}


@app.post("/api/game/move")
async def make_move_route(body: MoveRequest):
    """Submits a move to the active Lichess game."""
    if state_manager.game_status != "PLAYING":
        return {"status": "error", "message": "No active game"}

    src = parse_sq(body.from_square)
    dst = parse_sq(body.to_square)
    if not src or not dst:
        return {"status": "error", "message": "Invalid square coordinates"}

    success = await lichess_engine.make_move(
        src[0], src[1], dst[0], dst[1], promotion=body.promotion
    )
    if success:
        return {"status": "success"}
    else:
        return {"status": "error", "message": "Move was rejected by Lichess"}


@app.post("/api/game/resign")
async def resign_game_route():
    """Resigns the active game on Lichess."""
    if state_manager.game_status != "PLAYING":
        return {"status": "error", "message": "No active game to resign"}

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
    """Offers or accepts a draw on Lichess."""
    if state_manager.game_status != "PLAYING":
        return {"status": "error", "message": "No active game to offer draw"}

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


# --- WebSocket Stream ---

@app.websocket("/ws/state")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# --- Frontend Static Assets Serving ---

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.exists(frontend_path):
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api") or full_path.startswith("ws"):
            return None

        file_path = os.path.join(frontend_path, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)

        return FileResponse(os.path.join(frontend_path, "index.html"))
else:
    logger.warning(f"Frontend build not found at {frontend_path}. Operating in API-only mode.")

    @app.get("/")
    async def api_fallback():
        return {"status": "api-only", "warning": "Frontend assets not built in dist/"}
