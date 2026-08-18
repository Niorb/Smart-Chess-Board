"""
tests/test_physical_tracker.py

Unit tests for PhysicalMoveTracker:
- Detecting friendly piece lift and calculating legal moves
- Cancelling move when piece is returned to start square
- Completing a legal move (e2 -> e4)
- Detecting illegal placement
- Handling opponent moves and physical mirroring
- Capture detection in sync_game (standard and en passant)
- In-flight move locking and safety timeouts
"""

import os
import sys
import time
from unittest.mock import MagicMock

import chess
import pytest

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.physical_tracker import PhysicalMoveTracker


@pytest.fixture
def initial_physical_state():
    state = [[0] * 8 for _ in range(8)]
    for c in range(8):
        state[c][0] = -1
        state[c][1] = -1
        state[c][6] = 1
        state[c][7] = 1
    return state


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.board = chess.Board()
    engine.my_color = "white"
    engine.game_info = {
        "turn": "white",
        "last_move": None,
        "legal_moves": [m.uci() for m in engine.board.legal_moves],
    }
    return engine


def test_tracker_init():
    tracker = PhysicalMoveTracker()
    assert tracker.lifted_square is None
    assert len(tracker.legal_targets) == 0
    assert tracker.invalid_placement is None
    assert tracker.pending_opponent_move is None


def test_lift_friendly_piece(initial_physical_state, mock_engine):
    tracker = PhysicalMoveTracker()

    # Lift e2 pawn (c=4, r=1)
    state = [row[:] for row in initial_physical_state]
    state[4][1] = 0

    res = tracker.process_physical_state(state, mock_engine)
    assert res is None  # Move not complete yet
    assert tracker.lifted_square == (4, 1)  # e2
    # e2 pawn has legal targets e3 (4, 2) and e4 (4, 3)
    assert (4, 2) in tracker.legal_targets
    assert (4, 3) in tracker.legal_targets


def test_cancel_move_on_return(initial_physical_state, mock_engine):
    tracker = PhysicalMoveTracker()

    # 1. Lift e2
    state = [row[:] for row in initial_physical_state]
    state[4][1] = 0
    tracker.process_physical_state(state, mock_engine)
    assert tracker.lifted_square == (4, 1)

    # 2. Put e2 back
    state[4][1] = -1
    res = tracker.process_physical_state(state, mock_engine)
    assert res is None
    assert tracker.lifted_square is None
    assert len(tracker.legal_targets) == 0


def test_complete_legal_move(initial_physical_state, mock_engine):
    tracker = PhysicalMoveTracker()

    # 1. Lift e2
    state = [row[:] for row in initial_physical_state]
    state[4][1] = 0
    tracker.process_physical_state(state, mock_engine)

    # 2. Place on e4 (c=4, r=3)
    state[4][3] = -1
    res = tracker.process_physical_state(state, mock_engine)

    # Returns 1-indexed (from_f, from_r, to_f, to_r, promo)
    # e2 (5, 2) -> e4 (5, 4)
    assert res == (5, 2, 5, 4, None)
    assert tracker.lifted_square is None
    assert len(tracker.legal_targets) == 0


def test_illegal_move_placement(initial_physical_state, mock_engine):
    tracker = PhysicalMoveTracker()

    # 1. Lift e2
    state = [row[:] for row in initial_physical_state]
    state[4][1] = 0
    tracker.process_physical_state(state, mock_engine)

    # 2. Place on illegal square e5 (c=4, r=4)
    state[4][4] = -1
    res = tracker.process_physical_state(state, mock_engine)

    assert res is None  # Move not dispatched
    assert tracker.invalid_placement == (4, 4)


def test_opponent_move_sync_and_mirror(initial_physical_state, mock_engine):
    tracker = PhysicalMoveTracker()

    # Player played e2e4. Engine now has Black move e7e5.
    mock_engine.board.push_san("e4")
    mock_engine.board.push_san("e5")
    mock_engine.game_info["last_move"] = "e7e5"
    mock_engine.game_info["turn"] = "white"

    # Sync game detects opponent move
    tracker.sync_game(mock_engine)
    assert tracker.pending_opponent_move is not None
    assert tracker.pending_opponent_move["uci"] == "e7e5"
    assert tracker.pending_opponent_move["from"] == (4, 6)  # e7
    assert tracker.pending_opponent_move["to"] == (4, 4)    # e5

    # Player physically mirrors the opponent move on the board
    state = [row[:] for row in initial_physical_state]
    state[4][1] = 0  # e2 already empty from e4 move
    state[4][3] = -1 # e4 occupied
    state[4][6] = 0  # e7 lifted
    state[4][4] = 1  # e5 placed

    res = tracker.process_physical_state(state, mock_engine)
    assert res is None
    # Pending opponent move should now be cleared!
    assert tracker.pending_opponent_move is None


def test_sync_game_quiet_move_is_capture_false(mock_engine):
    """Verify sync_game marks is_capture == False on quiet moves."""
    tracker = PhysicalMoveTracker()
    mock_engine.my_color = "white"

    # White played e4, Black played e5 (quiet move)
    mock_engine.board = chess.Board()
    mock_engine.board.push_san("e4")
    mock_engine.board.push_san("e5")
    mock_engine.game_info["last_move"] = "e7e5"
    mock_engine.game_info["turn"] = "white"

    tracker.sync_game(mock_engine)
    assert tracker.pending_opponent_move is not None
    assert tracker.pending_opponent_move["uci"] == "e7e5"
    assert tracker.pending_opponent_move.get("is_capture") is False


def test_sync_game_piece_capture_is_capture_true(mock_engine):
    """Verify sync_game marks is_capture == True on standard piece captures."""
    tracker = PhysicalMoveTracker()
    mock_engine.my_color = "white"

    # Moves: 1. e4 d5 2. exd5 (White) Qxd5 (Black capture)
    mock_engine.board = chess.Board()
    mock_engine.board.push_san("e4")
    mock_engine.board.push_san("d5")
    mock_engine.board.push_san("exd5")
    mock_engine.board.push_san("Qxd5")
    mock_engine.game_info["last_move"] = "d8d5"
    mock_engine.game_info["turn"] = "white"

    tracker.sync_game(mock_engine)
    assert tracker.pending_opponent_move is not None
    assert tracker.pending_opponent_move["uci"] == "d8d5"
    assert tracker.pending_opponent_move.get("is_capture") is True


def test_sync_game_en_passant_is_capture_true(mock_engine):
    """Verify sync_game marks is_capture == True on en passant captures."""
    tracker = PhysicalMoveTracker()
    mock_engine.my_color = "white"

    # Moves: 1. a3 d5 2. b4 d4 3. c4 dxc3 (Black en passant)
    mock_engine.board = chess.Board()
    mock_engine.board.push_san("a3")
    mock_engine.board.push_san("d5")
    mock_engine.board.push_san("b4")
    mock_engine.board.push_san("d4")
    mock_engine.board.push_san("c4")
    mock_engine.board.push_san("dxc3")  # Black en passant
    mock_engine.game_info["last_move"] = "d4c3"
    mock_engine.game_info["turn"] = "white"

    tracker.sync_game(mock_engine)
    assert tracker.pending_opponent_move is not None
    assert tracker.pending_opponent_move["uci"] == "d4c3"
    assert tracker.pending_opponent_move.get("is_capture") is True


def test_in_flight_move_locking_and_sync(initial_physical_state, mock_engine):
    tracker = PhysicalMoveTracker()

    # 1. Lift e2
    state = [row[:] for row in initial_physical_state]
    state[4][1] = 0
    tracker.process_physical_state(state, mock_engine)

    # 2. Place on e4 (e2e4)
    state[4][3] = -1
    res = tracker.process_physical_state(state, mock_engine)
    assert res == (5, 2, 5, 4, None)

    # Tracker should now be in IN-FLIGHT state
    assert tracker.in_flight_move is not None
    assert tracker.in_flight_move["uci"] == "e2e4"
    assert tracker.in_flight_move["from"] == (4, 1)
    assert tracker.in_flight_move["to"] == (4, 3)

    # 3. Next 10ms scan loop while network request is in-flight:
    # Sensor still has e2 empty and e4 occupied, but mock_engine.board hasn't updated yet!
    res_subsequent = tracker.process_physical_state(state, mock_engine)
    # MUST return None and NOT re-lift e2!
    assert res_subsequent is None
    assert tracker.lifted_square is None
    assert len(tracker.legal_targets) == 0

    # 4. Engine receives confirmation and updates
    mock_engine.board.push_san("e4")
    mock_engine.game_info["last_move"] = "e2e4"
    mock_engine.game_info["turn"] = "black"

    tracker.sync_game(mock_engine)
    # In-flight lock should now be cleared
    assert tracker.in_flight_move is None


def test_in_flight_move_safety_timeout(initial_physical_state, mock_engine):
    tracker = PhysicalMoveTracker()

    # Manually set an in-flight move with an old timestamp (> 5s ago)
    tracker.set_in_flight_move(4, 1, 4, 3, "e2e4")
    tracker.in_flight_move["timestamp"] = time.time() - 6.0

    state = [row[:] for row in initial_physical_state]
    # In-flight lock should time out and release
    tracker.process_physical_state(state, mock_engine)
    assert tracker.in_flight_move is None


def test_tracker_to_dict_and_reset(initial_physical_state, mock_engine):
    tracker = PhysicalMoveTracker()
    tracker.set_in_flight_move(4, 1, 4, 3, "e2e4")
    payload = tracker.to_dict()
    assert payload["in_flight_move"] is not None
    assert payload["in_flight_move"]["uci"] == "e2e4"

    tracker.reset()
    assert tracker.in_flight_move is None
    assert tracker.to_dict()["in_flight_move"] is None


def test_player_quiet_move_triggers_arrival_flash(initial_physical_state, mock_engine):
    tracker = PhysicalMoveTracker()

    # 1. Lift e2 (c=4, r=1)
    state = [row[:] for row in initial_physical_state]
    state[4][1] = 0
    tracker.process_physical_state(state, mock_engine)

    # 2. Place on e4 (c=4, r=3)
    state[4][3] = -1
    tracker.process_physical_state(state, mock_engine)

    assert tracker.arrival_flash is not None
    assert tracker.arrival_flash["square"] == (4, 3)
    assert tracker.arrival_flash["is_capture"] is False
    assert tracker.arrival_flash["duration"] == 0.45
    assert abs(tracker.arrival_flash["start_time"] - time.time()) < 1.0


def test_player_capture_move_triggers_arrival_flash(initial_physical_state, mock_engine):
    tracker = PhysicalMoveTracker()

    # Setup board: 1. e4 d5 2. exd5 (White pawn on e4 captures Black pawn on d5)
    mock_engine.board.push_san("e4")
    mock_engine.board.push_san("d5")
    mock_engine.game_info["turn"] = "white"

    state = [row[:] for row in initial_physical_state]
    state[4][1] = 0   # e2 empty
    state[4][3] = -1  # e4 White pawn
    state[3][6] = 0   # d7 empty
    state[3][4] = 1   # d5 Black pawn

    # Lift e4 pawn
    state[4][3] = 0
    tracker.process_physical_state(state, mock_engine)
    assert tracker.lifted_square == (4, 3)
    assert (3, 4) in tracker.legal_targets

    # Place on d5 (capture)
    state[3][4] = -1
    tracker.process_physical_state(state, mock_engine)

    assert tracker.arrival_flash is not None
    assert tracker.arrival_flash["square"] == (3, 4)
    assert tracker.arrival_flash["is_capture"] is True


def test_opponent_move_mirror_triggers_arrival_flash(initial_physical_state, mock_engine):
    tracker = PhysicalMoveTracker()

    # Opponent played e7e5
    mock_engine.board.push_san("e4")
    mock_engine.board.push_san("e5")
    mock_engine.game_info["last_move"] = "e7e5"
    mock_engine.game_info["turn"] = "white"

    tracker.sync_game(mock_engine)

    state = [row[:] for row in initial_physical_state]
    state[4][1] = 0  # e2 empty
    state[4][3] = -1 # e4 occupied
    state[4][6] = 0  # e7 lifted
    state[4][4] = 1  # e5 placed

    tracker.process_physical_state(state, mock_engine)

    assert tracker.pending_opponent_move is None
    assert tracker.arrival_flash is not None
    assert tracker.arrival_flash["square"] == (4, 4)
    assert tracker.arrival_flash["is_capture"] is False


def test_tracker_reset_clears_arrival_flash():
    tracker = PhysicalMoveTracker()
    tracker.arrival_flash = {
        "square": (4, 3),
        "start_time": time.time(),
        "duration": 0.45,
        "is_capture": False,
    }
    tracker.reset()
    assert tracker.arrival_flash is None

