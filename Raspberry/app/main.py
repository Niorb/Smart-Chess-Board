import asyncio
import logging
import os
import sys

# Inject paths immediately so imports in dependencies don't fail with ModuleNotFoundError
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "playwright_chesscom"))
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List

from .board_state import state_manager
from .chess_engine_async import chess_engine

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart-chess-app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background loop
    logger.info("Starting background state manager loop...")
    task = asyncio.create_task(state_manager.update_loop(manager.broadcast))
    yield
    # Cleanup
    logger.info("Stopping background loop and Playwright...")
    task.cancel()
    await chess_engine.stop()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="Smart Chess Board API", lifespan=lifespan)

# Allow all origins for the phone app (PWA/React Native)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- WebSocket Connections Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Handle stale connections
                pass

manager = ConnectionManager()

# --- API Routes ---

@app.get("/api")
async def api_root():
    return {"status": "ok", "message": "Smart Chess Board API is running"}

from pydantic import BaseModel

from typing import Optional

class ThresholdSettings(BaseModel):
    threshold_positive: int
    threshold_negative: int
    col_mode: Optional[str] = None
    manual_col: Optional[int] = None
    scan_delay: Optional[int] = None
    mux_settle_ms: Optional[int] = None
    debounce_threshold: Optional[int] = None
    baseline_window_s: Optional[int] = None
    swap_row_quadrants: Optional[bool] = None
    swap_row_quadrants_left: Optional[bool] = None
    swap_row_quadrants_right: Optional[bool] = None
    disabled_squares: Optional[List[List[int]]] = None

@app.get("/api/board/physical")
async def get_physical_board():
    """Returns the current sensor state of the physical board."""
    return state_manager.get_physical_payload()

@app.get("/api/board/health")
async def get_board_health():
    """Returns detailed diagnostic health status of the board hardware and subsystems."""
    return state_manager.get_health_status()


@app.get("/api/board/settings")
async def get_board_settings():
    """Returns the current board calibration settings."""
    from board_hardware import settings
    return settings

@app.post("/api/board/settings")
async def update_board_settings(body: ThresholdSettings):
    """Updates the positive/negative deviation thresholds and column mode diagnostics."""
    from board_hardware import settings, save_settings, update_row_quadrant_settings
    settings["threshold_positive"] = body.threshold_positive
    settings["threshold_negative"] = body.threshold_negative
    if body.col_mode is not None:
        settings["col_mode"] = body.col_mode
    if body.manual_col is not None:
        settings["manual_col"] = body.manual_col
    if body.scan_delay is not None:
        settings["scan_delay"] = body.scan_delay
    if body.mux_settle_ms is not None:
        settings["mux_settle_ms"] = body.mux_settle_ms
    if body.debounce_threshold is not None:
        settings["debounce_threshold"] = body.debounce_threshold
    if body.baseline_window_s is not None:
        settings["baseline_window_s"] = body.baseline_window_s
    if body.swap_row_quadrants is not None:
        settings["swap_row_quadrants"] = body.swap_row_quadrants
        if body.swap_row_quadrants_left is None:
            update_row_quadrant_settings(swap_left=body.swap_row_quadrants)
        if body.swap_row_quadrants_right is None:
            update_row_quadrant_settings(swap_right=body.swap_row_quadrants)
    if body.swap_row_quadrants_left is not None or body.swap_row_quadrants_right is not None:
        update_row_quadrant_settings(
            swap_left=body.swap_row_quadrants_left,
            swap_right=body.swap_row_quadrants_right
        )
    if body.disabled_squares is not None:
        settings["disabled_squares"] = body.disabled_squares
    await asyncio.to_thread(save_settings)
    return {"status": "success", "settings": settings}

@app.post("/api/board/calibrate")
async def calibrate_board_route():
    """Triggers the sensor matrix calibration to establish new baselines."""
    success = await asyncio.to_thread(state_manager._safe_calibrate)
    if success:
        from board_hardware import settings
        return {"status": "success", "message": "Calibration completed", "settings": settings}
    else:
        return {"status": "error", "message": "Calibration failed"}

class HighlightRequest(BaseModel):
    col: int
    row: int

@app.post("/api/board/highlight")
async def highlight_square_route(body: HighlightRequest):
    """Highlights or toggles a physical square with orange LEDs."""
    current = state_manager.highlighted_square
    if current == (body.col, body.row):
        state_manager.highlighted_square = None
    else:
        state_manager.highlighted_square = (body.col, body.row)
    return {"status": "success", "highlighted_square": state_manager.highlighted_square}

@app.post("/api/board/test_leds")
async def test_leds_route():
    """Triggers a sequential LED test to light up every LED in order."""
    asyncio.create_task(state_manager.run_led_test())
    return {"status": "success", "message": "LED test initiated"}

@app.get("/api/board/digital")
async def get_digital_board():
    """Returns the current state of the board on chess.com."""
    return {"grid": state_manager.digital_state}

class SeekRequest(BaseModel):
    time_control: str = None

@app.post("/api/game/seek")
async def seek_game_route(body: SeekRequest = None):
    """Triggers a search for a new game on chess.com."""
    if state_manager.game_status != "IDLE":
        return {"status": "error", "message": f"Cannot seek while status is {state_manager.game_status}"}
    
    time_control = body.time_control if body else None
    # Run seek in the background
    asyncio.create_task(chess_engine.seek(state_manager, time_control=time_control))
    return {"status": "seeking initiated"}

@app.post("/api/game/cancel")
async def cancel_game_route():
    """Cancels the current search or resigns the active game."""
    await chess_engine.cancel(state_manager)
    return {"status": "cancelled"}

class MoveRequest(BaseModel):
    from_square: str
    to_square: str

@app.post("/api/game/move")
async def make_move_route(body: MoveRequest):
    """Executes a move on chess.com from the webapp."""
    if state_manager.game_status != "PLAYING":
        return {"status": "error", "message": "No active game"}
        
    def parse_sq(sq):
        sq = sq.strip().lower()
        if len(sq) != 2:
            return None
        file_ch, rank_ch = sq[0], sq[1]
        if file_ch not in "abcdefgh" or rank_ch not in "12345678":
            return None
        return ord(file_ch) - ord("a") + 1, int(rank_ch)
        
    src = parse_sq(body.from_square)
    dst = parse_sq(body.to_square)
    if not src or not dst:
        return {"status": "error", "message": "Invalid squares"}
        
    success = await chess_engine.make_move(src[0], src[1], dst[0], dst[1])
    if success:
        return {"status": "success"}
    else:
        return {"status": "error", "message": "Failed to execute move on Chess.com"}

@app.websocket("/ws/state")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep alive and listen
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# --- Static Frontend Serving ---

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.exists(frontend_path):
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # 1. Check if it's an API route (should be handled by other decorators, but for safety)
        if full_path.startswith("api") or full_path.startswith("ws"):
            return None # Should not happen due to route priority

        # 2. Check if the literal file exists in dist
        file_path = os.path.join(frontend_path, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)

        # 3. Fallback to index.html for SPA routing
        return FileResponse(os.path.join(frontend_path, "index.html"))
else:
    logger.warning(f"Frontend build not found at {frontend_path}. API only mode.")
    @app.get("/")
    async def api_fallback():
        return {"status": "api-only", "warning": "Frontend not built"}
