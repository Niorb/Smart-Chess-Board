import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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

@app.get("/api/board/physical")
async def get_physical_board():
    """Returns the current sensor state of the physical board."""
    return state_manager.get_physical_payload()

@app.get("/api/board/digital")
async def get_digital_board():
    """Returns the current state of the board on chess.com."""
    return {"grid": state_manager.digital_state}

@app.post("/api/game/seek")
async def seek_game_route():
    """Triggers a search for a new game on chess.com."""
    if state_manager.game_status != "IDLE":
        return {"status": "error", "message": f"Cannot seek while status is {state_manager.game_status}"}
    
    # Run seek in the background
    asyncio.create_task(chess_engine.seek(state_manager))
    return {"status": "seeking initiated"}

@app.post("/api/game/cancel")
async def cancel_game_route():
    """Cancels the current search or resigns the active game."""
    await chess_engine.cancel(state_manager)
    return {"status": "cancelled"}

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
