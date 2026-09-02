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

from app.physical_tracker import PhysicalMoveTracker, compute_promotion_layout


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


def test_piece_lift_distinguishes_legal_captures_from_quiet_moves(initial_physical_state, mock_engine):
    """Verify that when a piece is lifted, capture targets are populated in legal_captures."""
    tracker = PhysicalMoveTracker()

    # Position: 1. e4 d5 (White turn) -> e4 pawn can move to e5 (quiet) or capture d5 (capture)
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
    # Quiet move to e5: in legal_targets, NOT in legal_captures
    assert (4, 4) in tracker.legal_targets
    assert (4, 4) not in tracker.legal_captures
    # Capture on d5: in BOTH legal_targets and legal_captures
    assert (3, 4) in tracker.legal_targets
    assert (3, 4) in tracker.legal_captures

    # Return pawn to e4 -> clears legal_targets and legal_captures
    state[4][3] = -1
    tracker.process_physical_state(state, mock_engine)
    assert tracker.lifted_square is None
    assert len(tracker.legal_targets) == 0
    assert len(tracker.legal_captures) == 0


def test_sync_game_opponent_castling_detection(mock_engine):
    """Verify sync_game correctly detects opponent castling moves (e.g. e8g8)."""
    tracker = PhysicalMoveTracker()
    mock_engine.my_color = "white"

    # Setup board for Black Kingside castle: 1. e4 e5 2. Nf3 Nf6 3. Bc4 Bc5 4. O-O O-O
    mock_engine.board = chess.Board()
    mock_engine.board.push_san("e4")
    mock_engine.board.push_san("e5")
    mock_engine.board.push_san("Nf3")
    mock_engine.board.push_san("Nf6")
    mock_engine.board.push_san("Bc4")
    mock_engine.board.push_san("Bc5")
    mock_engine.board.push_san("O-O")
    mock_engine.board.push_san("O-O")  # Black castles Kingside (e8g8)
    mock_engine.game_info["last_move"] = "e8g8"
    mock_engine.game_info["turn"] = "white"

    tracker.sync_game(mock_engine)
    assert tracker.pending_opponent_move is not None
    assert tracker.pending_opponent_move["uci"] == "e8g8"
    assert tracker.pending_opponent_move["from"] == (4, 7)  # e8
    assert tracker.pending_opponent_move["to"] == (6, 7)    # g8
    assert tracker.pending_opponent_move["is_castling"] is True
    assert tracker.pending_opponent_move["rook_from"] == (7, 7)  # h8
    assert tracker.pending_opponent_move["rook_to"] == (5, 7)    # f8
    assert tracker.pending_opponent_move["phase"] == "king"


def test_opponent_castling_physical_mirror_requires_king_and_rook(mock_engine):
    """Verify that opponent castling progresses in 2 distinct phases: King step first, then Rook step."""
    tracker = PhysicalMoveTracker()
    mock_engine.my_color = "white"

    mock_engine.board = chess.Board()
    mock_engine.board.push_san("e4")
    mock_engine.board.push_san("e5")
    mock_engine.board.push_san("Nf3")
    mock_engine.board.push_san("Nf6")
    mock_engine.board.push_san("Bc4")
    mock_engine.board.push_san("Bc5")
    mock_engine.board.push_san("O-O")
    mock_engine.board.push_san("O-O")
    mock_engine.game_info["last_move"] = "e8g8"
    mock_engine.game_info["turn"] = "white"

    tracker.sync_game(mock_engine)
    assert tracker.pending_opponent_move["phase"] == "king"

    # Initial physical board state with pieces on e8 and h8
    state = [[0] * 8 for _ in range(8)]
    state[4][7] = 1  # Black King on e8
    state[7][7] = 1  # Black Rook on h8

    # Step 1: Human moves King only (e8 -> g8)
    state[4][7] = 0  # e8 lifted
    state[6][7] = 1  # g8 placed
    res = tracker.process_physical_state(state, mock_engine)
    assert res is None
    # Pending move must advance to Phase 2 (Rook time) with King arrival flash
    assert tracker.pending_opponent_move is not None
    assert tracker.pending_opponent_move["phase"] == "rook"
    assert tracker.arrival_flash is not None
    assert tracker.arrival_flash["square"] == (6, 7)

    # Step 2: Human moves Rook (h8 -> f8)
    state[7][7] = 0  # h8 lifted
    state[5][7] = 1  # f8 placed
    res2 = tracker.process_physical_state(state, mock_engine)
    assert res2 is None
    # Now both King and Rook are placed -> pending move is cleared and Rook arrival flash triggered!
    assert tracker.pending_opponent_move is None
    assert tracker.arrival_flash is not None
    assert tracker.arrival_flash["square"] == (5, 7)


def test_player_castling_triggers_pending_rook_and_placement_confirms(mock_engine):
    """Verify that when a player castles (moves King 2 squares), pending_castling_rook is created and confirmed on Rook placement."""
    tracker = PhysicalMoveTracker()
    mock_engine.my_color = "white"

    # Setup board for White Kingside castle: 1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5
    mock_engine.board = chess.Board()
    mock_engine.board.push_san("e4")
    mock_engine.board.push_san("e5")
    mock_engine.board.push_san("Nf3")
    mock_engine.board.push_san("Nc6")
    mock_engine.board.push_san("Bc4")
    mock_engine.board.push_san("Bc5")
    mock_engine.game_info["turn"] = "white"

    # Initial physical board state matching active chess position
    state = [[0] * 8 for _ in range(8)]
    for c in range(8):
        for r in range(8):
            piece = mock_engine.board.piece_at(chess.square(c, r))
            if piece:
                state[c][r] = -1 if piece.color == chess.WHITE else 1

    # Step 1: Lift White King from e1
    state[4][0] = 0
    tracker.process_physical_state(state, mock_engine)
    assert tracker.lifted_square == (4, 0)
    assert (6, 0) in tracker.legal_targets  # g1 is legal target for O-O

    # Step 2: Place White King on g1 (King 2-square castling move completed)
    state[6][0] = -1
    res = tracker.process_physical_state(state, mock_engine)
    # Move result (e1g1) returned to engine
    assert res == (5, 1, 7, 1, None)
    # Immediate arrival flash on g1
    assert tracker.arrival_flash is not None
    assert tracker.arrival_flash["square"] == (6, 0)
    # pending_castling_rook prompted for Rook (h1 -> f1)
    assert tracker.pending_castling_rook is not None
    assert tracker.pending_castling_rook["from"] == (7, 0)  # h1
    assert tracker.pending_castling_rook["to"] == (5, 0)    # f1

    # Step 3: Move Rook from h1 to f1
    state[7][0] = 0   # h1 lifted
    state[5][0] = -1  # f1 placed
    tracker.process_physical_state(state, mock_engine)
    # Pending Rook prompt cleared and arrival flash on f1
    assert tracker.pending_castling_rook is None
    assert tracker.arrival_flash is not None
    assert tracker.arrival_flash["square"] == (5, 0)


def test_no_phantom_lift_at_game_start_with_static_zero_square(initial_physical_state, mock_engine):
    """Verify that a square reading 0 at game start does NOT trigger a phantom piece lift."""
    tracker = PhysicalMoveTracker()

    # Board state at start of game has e2 (4, 1) and f1 (5, 0) reading 0 (e.g. uncalibrated or weak sensor)
    start_state = [row[:] for row in initial_physical_state]
    start_state[4][1] = 0  # e2 is 0
    start_state[5][0] = 0  # f1 is 0

    # Reset tracker with the live initial physical state (as done when entering PLAYING state)
    tracker.reset(start_state)

    # First and subsequent poll cycles without physical piece movement
    res = tracker.process_physical_state(start_state, mock_engine)
    assert res is None
    assert tracker.lifted_square is None
    assert len(tracker.legal_targets) == 0

    # Second cycle
    res2 = tracker.process_physical_state(start_state, mock_engine)
    assert res2 is None
    assert tracker.lifted_square is None


def test_lift_only_triggered_on_active_transition(initial_physical_state, mock_engine):
    """Verify that a piece lift is only detected when a square transitions from occupied (!= 0) to empty (0)."""
    tracker = PhysicalMoveTracker()
    tracker.reset(initial_physical_state)

    # Initial state: all starting pieces occupied
    tracker.process_physical_state(initial_physical_state, mock_engine)
    assert tracker.lifted_square is None

    # Player physically lifts e2 pawn (transitions from -1 to 0)
    lifted_state = [row[:] for row in initial_physical_state]
    lifted_state[4][1] = 0

    tracker.process_physical_state(lifted_state, mock_engine)
    assert tracker.lifted_square == (4, 1)
    assert (4, 2) in tracker.legal_targets
    assert (4, 3) in tracker.legal_targets


def test_piece_lift_suppressed_when_not_player_turn(initial_physical_state, mock_engine):
    """Verify that when it is opponent's turn (e.g. user plays Black), piece lift detection is suppressed."""
    tracker = PhysicalMoveTracker()
    mock_engine.my_color = "black"  # User is playing Black, White's turn (board.turn == WHITE)

    # Even if White's e2 pawn transitions to 0, player cannot move White's piece
    lifted_state = [row[:] for row in initial_physical_state]
    lifted_state[4][1] = 0

    res = tracker.process_physical_state(lifted_state, mock_engine)
    assert res is None
    assert tracker.lifted_square is None
    assert len(tracker.legal_targets) == 0


def test_capture_target_lifted_first_initiates_capture_intent(initial_physical_state, mock_engine):
    """Test lifting opponent's piece first sets pending_capture_target and candidate attackers."""
    tracker = PhysicalMoveTracker()
    tracker.reset(initial_physical_state)

    # Setup board position with e4 and d5 pawns
    mock_engine.board = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    mock_engine.my_color = "white"

    state = [row[:] for row in initial_physical_state]
    state[4][1] = 0  # e2 empty
    state[4][3] = -1 # e4 occupied by White
    state[3][6] = 0  # d7 empty
    state[3][4] = 1  # d5 occupied by Black
    tracker.last_physical_state = [row[:] for row in state]

    # Player lifts Black d5 pawn (transitions 1 -> 0)
    lifted_d5 = [row[:] for row in state]
    lifted_d5[3][4] = 0

    res = tracker.process_physical_state(lifted_d5, mock_engine)
    assert res is None
    assert tracker.pending_capture_target == (3, 4)
    assert (4, 3) in tracker.capture_candidate_attackers

    # Returning opponent piece cancels capture intent
    res_cancel = tracker.process_physical_state(state, mock_engine)
    assert res_cancel is None
    assert tracker.pending_capture_target is None
    assert len(tracker.capture_candidate_attackers) == 0


def test_capture_target_lifted_first_then_attacker_lifted_and_placed(initial_physical_state, mock_engine):
    """Test complete capture sequence: lift opponent piece -> lift friendly attacker -> place on target square."""
    tracker = PhysicalMoveTracker()
    tracker.reset(initial_physical_state)

    mock_engine.board = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    mock_engine.my_color = "white"

    state = [row[:] for row in initial_physical_state]
    state[4][1] = 0  # e2 empty
    state[4][3] = -1 # e4 White
    state[3][6] = 0  # d7 empty
    state[3][4] = 1  # d5 Black
    tracker.last_physical_state = [row[:] for row in state]

    # Step 1: Lift Black d5 pawn
    lifted_d5 = [row[:] for row in state]
    lifted_d5[3][4] = 0
    tracker.process_physical_state(lifted_d5, mock_engine)
    assert tracker.pending_capture_target == (3, 4)

    # Step 2: Lift White e4 attacker
    lifted_both = [row[:] for row in lifted_d5]
    lifted_both[4][3] = 0
    tracker.process_physical_state(lifted_both, mock_engine)
    assert tracker.lifted_square == (4, 3)
    assert (3, 4) in tracker.legal_targets
    assert (3, 4) in tracker.legal_captures

    # Step 3: Place White pawn on d5 target
    placed_d5 = [row[:] for row in lifted_both]
    placed_d5[3][4] = -1 # White pawn on d5
    move_res = tracker.process_physical_state(placed_d5, mock_engine)
    assert move_res == (5, 4, 4, 5, None)  # 1-indexed: e4 (5,4) -> d5 (4,5)
    assert tracker.arrival_flash is not None
    assert tracker.arrival_flash["is_capture"] is True
    assert tracker.arrival_flash["square"] == (3, 4)


def test_capture_target_lifted_first_direct_placement(initial_physical_state, mock_engine):
    """Test fast single-cycle capture where attacker is directly placed on pre-lifted capture target."""
    tracker = PhysicalMoveTracker()
    tracker.reset(initial_physical_state)

    mock_engine.board = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    mock_engine.my_color = "white"

    state = [row[:] for row in initial_physical_state]
    state[4][1] = 0  # e2 empty
    state[4][3] = -1 # e4 White
    state[3][6] = 0  # d7 empty
    state[3][4] = 1  # d5 Black
    tracker.last_physical_state = [row[:] for row in state]

    # Step 1: Lift Black d5 pawn
    lifted_d5 = [row[:] for row in state]
    lifted_d5[3][4] = 0
    tracker.process_physical_state(lifted_d5, mock_engine)
    assert tracker.pending_capture_target == (3, 4)

    # Step 2: Direct swap: e4 becomes 0 and d5 becomes -1 in one cycle
    swapped = [row[:] for row in lifted_d5]
    swapped[4][3] = 0
    swapped[3][4] = -1
    move_res = tracker.process_physical_state(swapped, mock_engine)
    assert move_res == (5, 4, 4, 5, None)
    assert tracker.in_flight_move is not None
    assert tracker.in_flight_move["uci"] == "e4d5"


# =============================================================================
# Royal Promotion Scepter & compute_promotion_layout Unit Tests
# =============================================================================

def test_compute_promotion_layout_standard_white_e8():
    """Verify standard White promotion at e8 allocates options center-out with fallback for promo square."""
    state = [[0] * 8 for _ in range(8)]
    state[4][7] = -1  # White pawn on e8

    layout = compute_promotion_layout(promo_col=4, promo_rank=7, is_white=True, physical_state=state)

    assert set(layout.keys()) == {"q", "n", "r", "b"}
    # All allocated coordinates must be unique
    allocated = list(layout.values())
    assert len(set(allocated)) == 4
    # Promotion square (4, 7) itself must NOT be in options
    assert (4, 7) not in allocated

    assert layout["q"] == (4, 6)
    assert layout["n"] == (3, 7)
    assert layout["r"] == (5, 7)
    assert layout["b"] == (2, 7)


def test_compute_promotion_layout_standard_black_d1():
    """Verify standard Black promotion at d1 targets rank 0 with rank 1 fallback."""
    state = [[0] * 8 for _ in range(8)]
    state[3][0] = 1  # Black pawn on d1

    layout = compute_promotion_layout(promo_col=3, promo_rank=0, is_white=False, physical_state=state)

    assert set(layout.keys()) == {"q", "n", "r", "b"}
    allocated = list(layout.values())
    assert len(set(allocated)) == 4
    assert (3, 0) not in allocated

    assert layout["q"] == (3, 1)
    assert layout["n"] == (2, 0)
    assert layout["r"] == (4, 0)
    assert layout["b"] == (1, 0)


def test_compute_promotion_layout_occupied_back_rank_forces_fallback():
    """Verify that occupied back-rank squares force fallback to rank 6 (Rank 7) on the same file."""
    state = [[0] * 8 for _ in range(8)]
    state[4][7] = -1  # White pawn on e8
    state[3][7] = 1   # Occupied d8
    state[5][7] = 1   # Occupied f8

    layout = compute_promotion_layout(promo_col=4, promo_rank=7, is_white=True, physical_state=state)

    assert layout["q"] == (4, 6)  # e8 fallback to e7
    assert layout["n"] == (3, 6)  # d8 occupied -> fallback to d7 (3, 6)
    assert layout["r"] == (5, 6)  # f8 occupied -> fallback to f7 (5, 6)
    assert layout["b"] == (2, 7)  # c8 empty -> (2, 7)


def test_compute_promotion_layout_corners():
    """Verify corner promotions on a8 and h8."""
    state = [[0] * 8 for _ in range(8)]

    # a8 promotion (col 0, rank 7)
    state[0][7] = -1
    layout_a8 = compute_promotion_layout(promo_col=0, promo_rank=7, is_white=True, physical_state=state)
    assert layout_a8["q"] == (0, 6)
    assert layout_a8["n"] == (1, 7)
    assert layout_a8["r"] == (2, 7)
    assert layout_a8["b"] == (3, 7)

    # h8 promotion (col 7, rank 7)
    state[7][7] = -1
    layout_h8 = compute_promotion_layout(promo_col=7, promo_rank=7, is_white=True, physical_state=state)
    assert layout_h8["q"] == (7, 6)
    assert layout_h8["n"] == (6, 7)
    assert layout_h8["r"] == (5, 7)
    assert layout_h8["b"] == (4, 7)


def test_compute_promotion_layout_extreme_crowded_board():
    """Verify layout generation does not fail even when all back-rank and fallback rank squares are occupied."""
    state = [[1] * 8 for _ in range(8)]
    # Clear promo square and 4 random squares elsewhere on board
    state[4][7] = -1  # promo sq
    state[0][3] = 0
    state[1][3] = 0
    state[2][3] = 0
    state[3][3] = 0

    layout = compute_promotion_layout(promo_col=4, promo_rank=7, is_white=True, physical_state=state)
    assert len(set(layout.values())) == 4
    assert (4, 7) not in layout.values()


def test_promotion_detection_initiates_pending_promotion():
    """Verify reaching 8th rank creates pending_promotion and returns None."""
    tracker = PhysicalMoveTracker()
    engine = MagicMock()
    engine.board = chess.Board("8/4P3/8/8/8/8/8/4K2k w - - 0 1")
    engine.my_color = "white"

    state = [[0] * 8 for _ in range(8)]
    state[4][6] = -1  # e7 White pawn
    state[4][0] = -1  # e1 King
    state[7][0] = 1   # h1 King
    tracker.last_physical_state = [row[:] for row in state]

    # 1. Lift e7 pawn
    lifted = [row[:] for row in state]
    lifted[4][6] = 0
    tracker.process_physical_state(lifted, engine)
    assert tracker.lifted_square == (4, 6)

    # 2. Place on e8 (col 4, rank 7)
    placed_e8 = [row[:] for row in lifted]
    placed_e8[4][7] = -1
    res = tracker.process_physical_state(placed_e8, engine)

    assert res is None  # Promotion is pending piece selection
    assert tracker.pending_promotion is not None
    assert tracker.pending_promotion["from"] == (4, 6)
    assert tracker.pending_promotion["to"] == (4, 7)
    assert tracker.pending_promotion["color"] == "white"
    assert "q" in tracker.pending_promotion["options"]
    assert "n" in tracker.pending_promotion["options"]


def test_promotion_physical_selection_knight():
    """Verify placing piece on Knight slot confirms Knight underpromotion."""
    tracker = PhysicalMoveTracker()
    engine = MagicMock()
    engine.board = chess.Board("8/4P3/8/8/8/8/8/4K2k w - - 0 1")
    engine.my_color = "white"

    state = [[0] * 8 for _ in range(8)]
    state[4][6] = -1  # e7 White pawn
    tracker.last_physical_state = [row[:] for row in state]

    # Lift e7 and place on e8
    lifted = [row[:] for row in state]
    lifted[4][6] = 0
    tracker.process_physical_state(lifted, engine)

    placed_e8 = [row[:] for row in lifted]
    placed_e8[4][7] = -1
    tracker.process_physical_state(placed_e8, engine)

    assert tracker.pending_promotion is not None
    knight_sq = tracker.pending_promotion["options"]["n"]  # (3, 7) -> d8

    # Place a piece on Knight slot (3, 7)
    selected = [row[:] for row in placed_e8]
    selected[knight_sq[0]][knight_sq[1]] = -1
    move_res = tracker.process_physical_state(selected, engine)

    # Must return 1-indexed tuple with promo='n'
    assert move_res == (5, 7, 5, 8, "n")
    assert tracker.pending_promotion is None
    assert tracker.in_flight_move is not None
    assert tracker.in_flight_move["uci"] == "e7e8n"


def test_promotion_auto_queen_timeout():
    """Verify auto-queen triggers after timeout_s expires."""
    tracker = PhysicalMoveTracker()
    engine = MagicMock()
    engine.board = chess.Board("8/4P3/8/8/8/8/8/4K2k w - - 0 1")
    engine.my_color = "white"

    state = [[0] * 8 for _ in range(8)]
    state[4][6] = -1
    tracker.last_physical_state = [row[:] for row in state]

    lifted = [row[:] for row in state]
    lifted[4][6] = 0
    tracker.process_physical_state(lifted, engine)

    placed_e8 = [row[:] for row in lifted]
    placed_e8[4][7] = -1
    tracker.process_physical_state(placed_e8, engine)

    # Artificially expire the start_time
    tracker.pending_promotion["start_time"] = time.time() - 10.0
    tracker.pending_promotion["timeout_s"] = 5.0

    move_res = tracker.process_physical_state(placed_e8, engine)
    assert move_res == (5, 7, 5, 8, "q")
    assert tracker.pending_promotion is None
    assert tracker.in_flight_move["uci"] == "e7e8q"


def test_promotion_cancelled_when_pawn_lifted_back():
    """Verify lifting promoting pawn off promotion square cancels promotion and restores lifted state."""
    tracker = PhysicalMoveTracker()
    engine = MagicMock()
    engine.board = chess.Board("8/4P3/8/8/8/8/8/4K2k w - - 0 1")
    engine.my_color = "white"

    state = [[0] * 8 for _ in range(8)]
    state[4][6] = -1
    tracker.last_physical_state = [row[:] for row in state]

    lifted = [row[:] for row in state]
    lifted[4][6] = 0
    tracker.process_physical_state(lifted, engine)

    placed_e8 = [row[:] for row in lifted]
    placed_e8[4][7] = -1
    tracker.process_physical_state(placed_e8, engine)
    assert tracker.pending_promotion is not None

    # Lift pawn off e8 again
    pawn_lifted_again = [row[:] for row in placed_e8]
    pawn_lifted_again[4][7] = 0
    res = tracker.process_physical_state(pawn_lifted_again, engine)

    assert res is None
    assert tracker.pending_promotion is None
    assert tracker.lifted_square == (4, 6)
    assert (4, 7) in tracker.legal_targets


def test_resolve_promotion_external():
    """Verify external resolve_promotion call (e.g. from Web UI / REST API)."""
    tracker = PhysicalMoveTracker()
    tracker.pending_promotion = {
        "from": (4, 6),
        "to": (4, 7),
        "color": "white",
        "start_time": time.time(),
        "timeout_s": 5.0,
        "options": {"q": (4, 6), "n": (3, 7), "r": (5, 7), "b": (2, 7)},
        "is_capture": False,
    }

    res = tracker.resolve_promotion("r")
    assert res == (5, 7, 5, 8, "r")
    assert tracker.pending_promotion is None
    assert tracker.in_flight_move["uci"] == "e7e8r"


def test_rook_move_matching_castle_coordinates_does_not_trigger_castling(mock_engine):
    """
    Verify that moving a Rook from e1 to c1 (4,0 -> 2,0) or e1 to g1 (4,0 -> 6,0)
    does NOT trigger castling detection or set pending_castling_rook.
    """
    tracker = PhysicalMoveTracker()
    mock_engine.my_color = "white"

    # Set up board with King on b1, Rook on e1, empty rank 1 between a1-f1
    mock_engine.board = chess.Board(fen="4k3/8/8/8/8/8/8/1K2R2R w - - 0 1")
    mock_engine.game_info["turn"] = "white"

    state = [[0] * 8 for _ in range(8)]
    for c in range(8):
        for r in range(8):
            p = mock_engine.board.piece_at(chess.square(c, r))
            if p:
                state[c][r] = -1 if p.color == chess.WHITE else 1

    # Lift Rook on e1 (4, 0)
    state[4][0] = 0
    tracker.process_physical_state(state, mock_engine)
    assert tracker.lifted_square == (4, 0)
    assert (2, 0) in tracker.legal_targets  # c1 is a legal target for Rook

    # Place Rook on c1 (2, 0) - matches coordinates (4, 0) -> (2, 0)
    state[2][0] = -1
    res = tracker.process_physical_state(state, mock_engine)

    assert res == (5, 1, 3, 1, None)  # e1c1 move confirmed
    # CRITICAL INVARIANT: pending_castling_rook MUST be None because the piece moved was a Rook, NOT a King!
    assert tracker.pending_castling_rook is None


def test_sync_game_opponent_rook_move_not_castling(mock_engine):
    """Verify sync_game marks is_castling == False when opponent moves a Rook matching castle coordinates."""
    tracker = PhysicalMoveTracker()
    mock_engine.my_color = "white"

    # Board with Black King on b8, Black Rook on e8 (4, 7)
    mock_engine.board = chess.Board(fen="1k2r2r/8/8/8/8/8/8/4K3 b - - 0 1")
    mock_engine.board.push_san("Re8-c8")  # Rook moves e8c8
    mock_engine.game_info["last_move"] = "e8c8"
    mock_engine.game_info["turn"] = "white"

    tracker.sync_game(mock_engine)
    assert tracker.pending_opponent_move is not None
    assert tracker.pending_opponent_move["uci"] == "e8c8"
    assert tracker.pending_opponent_move["is_castling"] is False
    assert tracker.pending_opponent_move["rook_from"] is None
    assert tracker.pending_opponent_move["rook_to"] is None
    assert tracker.pending_opponent_move["phase"] == "standard"






