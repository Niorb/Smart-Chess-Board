"""
tests/test_setup_validator.py

Unit tests for the setup validator subsystem:
- Correct initial setup (White -1 on ranks 1-2, Black +1 on ranks 7-8, Empty 0 on ranks 3-6)
- Missing white piece detection
- Missing black piece detection
- Misplaced piece detection (wrong polarity / piece on empty squares)
"""

import os
import sys

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.setup_validator import SetupValidator, SetupResult


def test_empty_board_setup():
    validator = SetupValidator()
    empty_state = [[0] * 8 for _ in range(8)]
    result = validator.validate(empty_state)

    assert result.is_setup_ready is False
    assert len(result.missing_white) == 16  # 2 ranks x 8 files
    assert len(result.missing_black) == 16  # 2 ranks x 8 files
    assert len(result.misplaced_pieces) == 0
    assert result.white_count == 0
    assert result.black_count == 0


def test_perfect_initial_setup():
    validator = SetupValidator()
    state = [[0] * 8 for _ in range(8)]
    # White on ranks 1 & 2 (r=0, 1)
    for c in range(8):
        state[c][0] = -1
        state[c][1] = -1
    # Black on ranks 7 & 8 (r=6, 7)
    for c in range(8):
        state[c][6] = 1
        state[c][7] = 1

    result = validator.validate(state)
    assert result.is_setup_ready is True
    assert len(result.missing_white) == 0
    assert len(result.missing_black) == 0
    assert len(result.misplaced_pieces) == 0
    assert result.white_count == 16
    assert result.black_count == 16


def test_missing_single_piece():
    validator = SetupValidator()
    state = [[0] * 8 for _ in range(8)]
    for c in range(8):
        state[c][0] = -1
        state[c][1] = -1
        state[c][6] = 1
        state[c][7] = 1

    # Remove White King on e1 (c=4, r=0)
    state[4][0] = 0

    result = validator.validate(state)
    assert result.is_setup_ready is False
    assert (4, 0) in result.missing_white
    assert len(result.missing_white) == 1
    assert len(result.missing_black) == 0


def test_inverted_polarity_piece():
    validator = SetupValidator()
    state = [[0] * 8 for _ in range(8)]
    for c in range(8):
        state[c][0] = -1
        state[c][1] = -1
        state[c][6] = 1
        state[c][7] = 1

    # Black piece (+1) accidentally placed on White starting square e1 (c=4, r=0)
    state[4][0] = 1

    result = validator.validate(state)
    assert result.is_setup_ready is False
    assert (4, 0) in result.missing_white
    assert (4, 0) in result.misplaced_pieces


def test_misplaced_piece_on_middle_rank():
    validator = SetupValidator()
    state = [[0] * 8 for _ in range(8)]
    for c in range(8):
        state[c][0] = -1
        state[c][1] = -1
        state[c][6] = 1
        state[c][7] = 1

    # Extra piece on e4 (c=4, r=3)
    state[4][3] = -1

    result = validator.validate(state)
    assert result.is_setup_ready is False
    assert (4, 3) in result.misplaced_pieces


def test_result_serialization():
    validator = SetupValidator()
    state = [[0] * 8 for _ in range(8)]
    result = validator.validate(state)
    d = result.to_dict()
    assert "is_setup_ready" in d
    assert "missing_white" in d
    assert "missing_black" in d
    assert "misplaced_pieces" in d
    assert "white_count" in d
    assert "black_count" in d


def test_guardrail_synchronized_game_state():
    import chess
    validator = SetupValidator()
    board = chess.Board()
    state = [[0] * 8 for _ in range(8)]
    # Populate starting positions
    for c in range(8):
        state[c][0] = -1
        state[c][1] = -1
        state[c][6] = 1
        state[c][7] = 1

    guardrail = validator.validate_game_state(state, board)
    assert guardrail.is_synchronized is True
    assert len(guardrail.missing_pieces) == 0
    assert len(guardrail.unexpected_pieces) == 0


def test_guardrail_detects_missing_and_unexpected_pieces():
    import chess
    validator = SetupValidator()
    board = chess.Board()
    state = [[0] * 8 for _ in range(8)]
    for c in range(8):
        state[c][0] = -1
        state[c][1] = -1
        state[c][6] = 1
        state[c][7] = 1

    # e2 pawn missing
    state[4][1] = 0
    # unexpected piece on e4
    state[4][3] = -1

    guardrail = validator.validate_game_state(state, board)
    assert guardrail.is_synchronized is False
    assert (4, 1) in guardrail.missing_pieces
    assert (4, 3) in guardrail.unexpected_pieces


def test_guardrail_exempts_transient_lift_and_captures():
    import chess
    from unittest.mock import MagicMock
    validator = SetupValidator()
    board = chess.Board()
    state = [[0] * 8 for _ in range(8)]
    for c in range(8):
        state[c][0] = -1
        state[c][1] = -1
        state[c][6] = 1
        state[c][7] = 1

    tracker = MagicMock()
    tracker.lifted_square = (4, 1)  # e2 pawn lifted
    tracker.legal_captures = [(3, 4)]
    tracker.in_flight_move = None
    tracker.pending_opponent_move = None
    tracker.pending_castling_rook = None
    tracker.pending_capture_target = None
    tracker.capture_candidate_attackers = []

    state[4][1] = 0  # physically lifted

    guardrail = validator.validate_game_state(state, board, tracker=tracker)
    assert guardrail.is_synchronized is True
    assert (4, 1) not in guardrail.missing_pieces


def test_guardrail_exempts_capture_target_lifted_first():
    import chess
    from unittest.mock import MagicMock
    validator = SetupValidator()
    board = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    state = [[0] * 8 for _ in range(8)]
    for c in range(8):
        state[c][0] = -1
        state[c][1] = -1 if c != 4 else 0
        state[c][6] = 1 if c != 3 else 0
        state[c][7] = 1
    state[4][3] = -1  # e4 White pawn
    # Opponent d5 pawn (c=3, r=4) is physically lifted first: state[3][4] == 0
    state[3][4] = 0

    tracker = MagicMock()
    tracker.lifted_square = None
    tracker.legal_captures = []
    tracker.in_flight_move = None
    tracker.pending_opponent_move = None
    tracker.pending_castling_rook = None
    tracker.pending_capture_target = (3, 4)  # d5 lifted
    tracker.capture_candidate_attackers = [(4, 3)]

    guardrail = validator.validate_game_state(state, board, tracker=tracker)
    assert guardrail.is_synchronized is True
    assert guardrail.pending_capture == (3, 4)
    assert (3, 4) not in guardrail.missing_pieces
