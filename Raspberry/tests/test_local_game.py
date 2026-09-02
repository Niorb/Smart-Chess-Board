"""
Raspberry/tests/test_local_game.py

Unit and integration tests for the Cyber-Physical Local Game Engine,
Setup Readiness Arming Gate, and Auto-Starting Local Match on First White Move.
"""

import chess
import pytest
from app.board_state import AnalysisEngineAdapter, BoardStateManager, LocalGameEngine
from app.config import BOARD_COLS, BOARD_ROWS
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def clean_state_manager():
    sm = BoardStateManager()
    sm.strip = None  # Mock hardware LEDs
    sm.ser = None
    sm.h = None
    return sm


@pytest.fixture
def starting_physical_state():
    """Generates standard 32-piece physical starting layout (White=-1 Ranks 1-2, Black=+1 Ranks 7-8)."""
    grid = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
    for c in range(BOARD_COLS):
        grid[c][0] = -1  # White backrank
        grid[c][1] = -1  # White pawns
        grid[c][6] = 1   # Black pawns
        grid[c][7] = 1   # Black backrank
    return grid


class TestLocalGameEngine:
    def test_initialization(self):
        engine = LocalGameEngine()
        assert engine.is_active is False
        assert engine.game_id is None
        assert engine.winner is None
        assert engine.my_color == "white"
        assert engine.is_game_over is False

    def test_start_game(self):
        engine = LocalGameEngine()
        engine.start_game()
        assert engine.is_active is True
        assert engine.game_id is not None
        assert engine.board.fen() == chess.STARTING_FEN
        assert engine.my_color == "white"

    def test_apply_move_turn_alternation(self):
        engine = LocalGameEngine()
        engine.start_game()

        # White plays 1. e4
        assert engine.apply_move("e2e4") is True
        assert engine.board.turn == chess.BLACK
        assert engine.my_color == "black"
        assert len(engine.board.move_stack) == 1

        # Black plays 1... e5
        assert engine.apply_move("e7e5") is True
        assert engine.board.turn == chess.WHITE
        assert engine.my_color == "white"
        assert len(engine.board.move_stack) == 2

    def test_illegal_move_rejection(self):
        engine = LocalGameEngine()
        engine.start_game()

        # Illegal move on turn 1
        assert engine.apply_move("e2e5") is False
        assert len(engine.board.move_stack) == 0

    def test_scholars_mate_detection(self):
        engine = LocalGameEngine()
        engine.start_game()

        assert engine.apply_move("e2e4") is True
        assert engine.apply_move("e7e5") is True
        assert engine.apply_move("d1h5") is True
        assert engine.apply_move("b8c6") is True
        assert engine.apply_move("f1c4") is True
        assert engine.apply_move("g8f6") is True
        assert engine.apply_move("h5f7") is True  # Scholar's Mate!

        assert engine.board.is_checkmate() is True
        assert engine.is_game_over is True
        assert engine.winner == "white"
        assert engine.end_reason == "checkmate"

    def test_resignation(self):
        engine = LocalGameEngine()
        engine.start_game()
        assert engine.apply_move("e2e4") is True

        # Black resigns
        engine.resign(player_color="black")
        assert engine.is_game_over is True
        assert engine.winner == "white"
        assert engine.end_reason == "resignation"

    def test_get_game_payload(self):
        engine = LocalGameEngine()
        engine.start_game(game_id="local_test_123")
        engine.apply_move("e2e4")

        payload = engine.get_game_payload()
        assert payload["game_id"] == "local_test_123"
        assert payload["is_local"] is True
        assert payload["turn"] == "black"
        assert payload["last_move"] == "e2e4"
        assert payload["is_game_over"] is False


class TestSetupReadinessArmingGate:
    def test_partial_setup_does_not_arm(self, clean_state_manager):
        sm = clean_state_manager
        # Incomplete board (e.g. only 16 pawns placed)
        partial_grid = [[0] * BOARD_ROWS for _ in range(BOARD_COLS)]
        for c in range(BOARD_COLS):
            partial_grid[c][1] = -1
            partial_grid[c][6] = 1

        sm.physical_state = partial_grid
        res = sm.setup_validator.validate(partial_grid)
        assert res.is_setup_ready is False

        sm._process_setup_ready_edge(res.is_setup_ready, [])
        assert sm.can_start_local_game is False

    def test_complete_setup_arms_gate(self, clean_state_manager, starting_physical_state):
        sm = clean_state_manager
        sm.physical_state = starting_physical_state
        res = sm.setup_validator.validate(starting_physical_state)
        assert res.is_setup_ready is True

        sm._process_setup_ready_edge(res.is_setup_ready, [])
        assert sm.can_start_local_game is True

    def test_auto_start_on_white_move(self, clean_state_manager, starting_physical_state):
        sm = clean_state_manager
        sm.physical_state = starting_physical_state
        sm._process_setup_ready_edge(True, [])
        assert sm.can_start_local_game is True
        assert sm.game_status == "IDLE"

        # 1. White lifts e2 pawn (from_col=4, from_row=1)
        lifted_state = [col[:] for col in starting_physical_state]
        lifted_state[4][1] = 0
        sm.physical_state = lifted_state

        adapter = AnalysisEngineAdapter(chess.Board())
        move_res = sm.move_tracker.process_physical_state(lifted_state, adapter)
        assert move_res is None
        assert sm.move_tracker.lifted_square == (4, 1)
        assert (4, 3) in sm.move_tracker.legal_targets  # e4 is legal

        # 2. White places pawn on e4 (col=4, row=3)
        placed_state = [col[:] for col in lifted_state]
        placed_state[4][3] = -1
        sm.physical_state = placed_state

        move_res = sm.move_tracker.process_physical_state(placed_state, adapter)
        assert move_res == (5, 2, 5, 4, None)  # 1-indexed (col 5, row 2) -> (col 5, row 4) == e2e4

        # Simulate update_loop handling of the move
        from_f, from_r, to_f, to_r, promo = move_res
        from_sq = f"{chr(ord('a') + from_f - 1)}{from_r}"
        to_sq = f"{chr(ord('a') + to_f - 1)}{to_r}"
        uci = f"{from_sq}{to_sq}{promo or ''}"

        sm.start_local_game()
        sm.local_engine.apply_move(uci)

        assert sm.game_status == "PLAYING"
        assert sm.local_engine.is_active is True
        assert sm.local_engine.board.peek().uci() == "e2e4"
        assert sm.can_start_local_game is False

    def test_game_over_reset_to_idle(self, clean_state_manager, starting_physical_state):
        sm = clean_state_manager
        sm.start_local_game()
        sm.stop_local_game(winner="white", reason="checkmate")
        assert sm.game_status == "GAME_OVER"

        # User restores all 32 pieces to starting positions
        sm.physical_state = starting_physical_state
        res = sm.setup_validator.validate(starting_physical_state)
        assert res.is_setup_ready is True

        # Simulate update_loop transition
        sm.local_engine.reset()
        sm.game_status = "IDLE"
        sm.move_tracker.reset(sm.physical_state)
        sm._process_setup_ready_edge(True, [])

        assert sm.game_status == "IDLE"
        assert sm.can_start_local_game is True


class TestLocalGameApiRoutes:
    def test_start_and_stop_local_game(self, clean_state_manager):
        client = TestClient(app)

        # Start local match
        resp = client.post("/api/game/local/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "local_" in data["game_id"]

        # Make virtual move 1. e4
        move_resp = client.post("/api/game/move", json={"from_square": "e2", "to_square": "e4"})
        assert move_resp.status_code == 200
        assert move_resp.json()["status"] == "success"

        # Make virtual move 1... e5
        move_resp2 = client.post("/api/game/move", json={"from_square": "e7", "to_square": "e5"})
        assert move_resp2.status_code == 200
        assert move_resp2.json()["status"] == "success"

        # Resign local match
        resign_resp = client.post("/api/game/resign")
        assert resign_resp.status_code == 200
        assert resign_resp.json()["status"] == "success"
        assert resign_resp.json()["winner"] == "black"

        # Start second match to test manual stop
        client.post("/api/game/local/start")
        stop_resp = client.post("/api/game/local/stop", json={"winner": "draw", "reason": "agreement"})
        assert stop_resp.status_code == 200
        assert stop_resp.json()["status"] == "success"
