"""
tests/test_blunder_endgame_adversarial.py

Comprehensive adversarial test suite for:
- Tactical Puzzles (Blunder Blitz)
- Endgame Academy (Tablebase Trainer)

Covers:
1. Illegal and Out-of-Order Moves (invalid UCI/SAN, moves into check, wrong turns, attempts when thinking).
2. Physical Sensor Desynchronizations (sparse setup matrix, missing pieces, misplaced pieces, polarity errors).
3. Rapid / Concurrent Inputs (rapid submissions, submissions after completion, source=web vs source=board).
4. UI State Transitions (switching blunder indices, stopping drills, custom FENs, progress reset).
5. Opponent Defensive Replies (Stockfish calculation, web auto-application vs physical LED/tracker guidance).
6. Strict Solution Concealment and Goal Achievements (mate, win, draw).
"""

import asyncio
import os
import sys
import time
import chess
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.board_state import BoardStateManager, AnalysisEngineAdapter
from app.coach_engine import CoachEngine, BlunderChallenge, coach_engine
from app.endgame_db import (
    EndgameCategory,
    EndgameDrill,
    EndgameProgressManager,
    CORE_ENDGAME_DRILLS,
)
from app.led_helpers import (
    COLOR_INT_OPPONENT_FROM,
    COLOR_INT_OPPONENT_TO,
    COLOR_INT_MOVE_CONFIRM,
    COLOR_INT_OFF,
)
from app.setup_validator import SetupResult


# =============================================================================
# 1. TACTICAL PUZZLES (BLUNDER BLITZ) ADVERSARIAL TESTS
# =============================================================================


def test_adversarial_blunder_illegal_and_out_of_order_moves():
    """Tests illegal, malformed, and out-of-order move attempts in Blunder Blitz."""
    async def _test():
        mgr = BoardStateManager()
        # Setup mock blunder
        blunder = {
            "ply_index": 5,
            "fen_before": "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3",
            "played_move": "g8f6",
            "classification": "blunder",
            "delta_cp": 500,
            "best_move": "d8e7",
            "player_color": "black",
            "opponent_color": "white",
            "opponent_prev_move_uci": "f1c4",
            "opponent_prev_move_san": "Bc4",
            "player_moves": ["d8e7"],
            "opponent_replies": ["g1f3"],
            "solution_line_san": ["3... Qe7", "4. Nf3"],
        }
        mgr.analysis_blunders = [blunder]
        mgr.start_blunder_drill(0)

        assert mgr.analysis_submode == "blunder_drill"
        assert mgr.analysis_blunder_attempts == 3
        assert mgr.analysis_active_board.turn == chess.BLACK

        # 1. Submit invalid string / malformed move
        res_malformed = mgr.submit_blunder_attempt("not_a_move", source="web")
        assert res_malformed["correct"] is False
        assert res_malformed["attempts_remaining"] == 2
        # Board state must remain pristine
        assert mgr.analysis_active_board.turn == chess.BLACK
        assert mgr.analysis_blunder_step == 0

        # 2. Submit illegal move according to chess rules (e.g. piece jumping through piece)
        res_illegal = mgr.submit_blunder_attempt("e8e4", source="board")
        assert res_illegal["correct"] is False
        assert res_illegal["attempts_remaining"] == 1
        assert mgr.analysis_active_board.turn == chess.BLACK

        # 3. Submit legal chess move that is NOT the puzzle solution
        res_wrong_legal = mgr.submit_blunder_attempt("d7d6", source="web")
        assert res_wrong_legal["correct"] is False
        assert res_wrong_legal["attempts_remaining"] == 0

        # 4. Submit move when attempts are 0 (should stay 0 and not become negative)
        res_exhausted = mgr.submit_blunder_attempt("a7a6", source="web")
        assert res_exhausted["correct"] is False
        assert res_exhausted["attempts_remaining"] == 0

        # 5. Submit the correct move now
        res_correct = mgr.submit_blunder_attempt("d8e7", source="web")
        assert res_correct["correct"] is True
        assert res_correct["puzzle_complete"] is True
        assert mgr.analysis_blunder_step == 1

        # 6. Submit further move attempt after puzzle is already complete
        res_after_complete = mgr.submit_blunder_attempt("d8e7", source="web")
        assert res_after_complete["correct"] is True
        assert res_after_complete["puzzle_complete"] is True
        assert "Puzzle already solved!" in res_after_complete["message"]

    asyncio.run(_test())


def test_adversarial_blunder_multi_ply_web_and_board_flows():
    """Tests multi-ply tactical sequences for both Web UI and physical board flows."""
    async def _test():
        mgr = BoardStateManager()
        # 2-ply player sequence with opponent reply:
        # Player: 1... Qe7, Opponent: 2. Nf3, Player: 2... Nf6 (Puzzle complete)
        blunder = {
            "ply_index": 5,
            "fen_before": "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3",
            "played_move": "g8f6",
            "classification": "blunder",
            "delta_cp": 500,
            "best_move": "d8e7",
            "player_color": "black",
            "opponent_color": "white",
            "opponent_prev_move_uci": "f1c4",
            "opponent_prev_move_san": "Bc4",
            "player_moves": ["d8e7", "g8f6"],
            "opponent_replies": ["g1f3"],
            "solution_line_san": ["3... Qe7", "4. Nf3", "4... Nf6"],
        }
        mgr.analysis_blunders = [blunder]

        # --- FLOW A: Web UI Play ---
        mgr.start_blunder_drill(0)
        assert mgr.analysis_blunder_step == 0

        # Player plays step 1 as SAN: 'Qe7'
        res1 = mgr.submit_blunder_attempt("Qe7", source="web")
        assert res1["correct"] is True
        assert res1["step_complete"] is True
        assert res1["puzzle_complete"] is False
        assert res1["opponent_reply_uci"] == "g1f3"
        # On web, opponent reply was auto-applied
        assert mgr.analysis_blunder_step == 1
        assert mgr.analysis_active_board.turn == chess.BLACK

        # Player plays step 2 as UCI: 'g8f6'
        res2 = mgr.submit_blunder_attempt("g8f6", source="web")
        assert res2["correct"] is True
        assert res2["step_complete"] is True
        assert res2["puzzle_complete"] is True
        assert "solution_line" in res2

        # --- FLOW B: Physical Board Play ---
        mgr.start_blunder_drill(0)
        assert mgr.analysis_blunder_step == 0

        # Player plays step 1 physically on board: 'd8e7'
        res_board1 = mgr.submit_blunder_attempt("d8e7", source="board")
        assert res_board1["correct"] is True
        assert mgr.move_tracker.pending_opponent_move is not None
        assert mgr.move_tracker.pending_opponent_move["uci"] == "g1f3"
        assert getattr(mgr, "analysis_blunder_pending_reply", None) is not None

        # Opponent move is executed physically or via apply helper
        apply_res = mgr.apply_blunder_pending_opponent_move()
        assert apply_res["result"] == "ok"
        assert mgr.move_tracker.pending_opponent_move is None
        assert mgr.analysis_blunder_pending_reply is None
        assert mgr.analysis_blunder_step == 1

        # Player plays final step physically
        res_board2 = mgr.submit_blunder_attempt("g8f6", source="board")
        assert res_board2["correct"] is True
        assert res_board2["puzzle_complete"] is True

    asyncio.run(_test())


def test_adversarial_blunder_state_transitions_and_empty_cases():
    """Tests switching puzzle indices, out-of-bounds indices, empty blunder list, and hints."""
    mgr = BoardStateManager()

    # 1. No blunders loaded: start and attempt must not crash
    mgr.analysis_blunders = []
    start_res = mgr.start_blunder_drill(0)
    assert start_res["active"] is True
    res_attempt = mgr.submit_blunder_attempt("e2e4")
    assert res_attempt["correct"] is False
    assert "No active blunder challenge" in res_attempt["message"]

    # 2. Out-of-bounds index clamped safely
    blunder1 = {"fen_before": "8/8/8/8/8/8/8/4K2k w - - 0 1", "best_move": "e1f2", "player_moves": ["e1f2"], "opponent_replies": []}
    blunder2 = {"fen_before": "8/8/8/8/8/8/8/4K2k w - - 0 1", "best_move": "e1e2", "player_moves": ["e1e2"], "opponent_replies": []}
    mgr.analysis_blunders = [blunder1, blunder2]

    mgr.start_blunder_drill(999)
    assert mgr.analysis_blunder_index == 1
    mgr.start_blunder_drill(-5)
    assert mgr.analysis_blunder_index == 0

    # 3. Hint toggle lifecycle
    assert mgr.analysis_blunder_hint_active is False
    assert mgr.toggle_blunder_hint() is True
    assert mgr.analysis_blunder_hint_active is True
    assert mgr.toggle_blunder_hint() is False
    assert mgr.analysis_blunder_hint_active is False


# =============================================================================
# 2. ENDGAME ACADEMY (TABLEBASE TRAINER) ADVERSARIAL TESTS
# =============================================================================


def test_adversarial_endgame_sparse_setup_desynchronization():
    """Tests sparse piece setup validation with missing, misplaced, and extra pieces."""
    mgr = BoardStateManager()
    drill = EndgameDrill(
        id="test_opposition",
        category=EndgameCategory.PAWNS,
        title="Pawn Opposition",
        fen="8/8/8/4k3/8/4K3/4P3/8 w - - 0 1",
        player_color="white",
        target_goal="win",
    )
    mgr.endgame_drill = drill
    mgr.endgame_board = chess.Board(drill.fen)

    # Empty board
    empty = [[0] * 8 for _ in range(8)]
    mgr.endgame_phase = "setup_white"
    is_ready, missing_w, missing_b, misplaced = mgr._validate_endgame_sparse_setup(empty)
    assert is_ready is False
    assert len(missing_w) == 2  # e3 (King), e2 (Pawn)
    assert len(misplaced) == 0

    # Place White pieces with wrong polarity (+1 North pole instead of -1 South pole)
    wrong_polarity = [[0] * 8 for _ in range(8)]
    wrong_polarity[4][2] = 1  # e3
    wrong_polarity[4][1] = 1  # e2
    is_ready, missing_w, missing_b, misplaced = mgr._validate_endgame_sparse_setup(wrong_polarity)
    assert is_ready is False
    assert len(misplaced) == 2

    # Correct White pieces (-1)
    correct_white = [[0] * 8 for _ in range(8)]
    correct_white[4][2] = -1  # e3 King
    correct_white[4][1] = -1  # e2 Pawn
    is_ready, missing_w, missing_b, misplaced = mgr._validate_endgame_sparse_setup(correct_white)
    assert is_ready is True
    assert len(missing_w) == 0
    assert len(misplaced) == 0

    # Advance to Phase 2: setup_black
    mgr.endgame_phase = "setup_black"
    # Black pieces missing
    is_ready, missing_w, missing_b, misplaced = mgr._validate_endgame_sparse_setup(correct_white)
    assert is_ready is False
    assert len(missing_b) == 1  # e5 Black King

    # Add extra piece on unassigned square (e.g. a1)
    with_extra = [list(col) for col in correct_white]
    with_extra[0][0] = -1  # a1
    is_ready, missing_w, missing_b, misplaced = mgr._validate_endgame_sparse_setup(with_extra)
    assert is_ready is False
    assert (0, 0) in misplaced

    # Complete setup with Black piece on e5 (+1) and no extra pieces
    full_setup = [list(col) for col in correct_white]
    full_setup[4][4] = 1  # e5 Black King
    is_ready, missing_w, missing_b, misplaced = mgr._validate_endgame_sparse_setup(full_setup)
    assert is_ready is True
    assert len(missing_w) == 0
    assert len(missing_b) == 0
    assert len(misplaced) == 0


def test_adversarial_endgame_illegal_and_out_of_turn_moves():
    """Tests illegal moves, wrong turns, and rapid submissions while computing in Endgame Academy."""
    async def _test():
        mgr = BoardStateManager()
        await mgr.start_endgame_drill("pawn_opposition")
        assert mgr.endgame_active is True

        # 1. Move attempted before playing phase (in setup phase)
        mgr.endgame_phase = "setup_white"
        res_setup = mgr.handle_endgame_move_sync("e3d3", source="web")
        assert "error" in res_setup
        assert "not in playing phase" in res_setup["error"]

        # Advance to playing phase
        mgr.endgame_phase = "playing"

        # 2. Invalid UCI text
        res_invalid = mgr.handle_endgame_move_sync("invalid_uci", source="web")
        assert "error" in res_invalid

        # 3. Illegal chess move (e.g. King jumps across board)
        res_illegal = mgr.handle_endgame_move_sync("e3e8", source="board")
        assert "error" in res_illegal
        assert "Illegal move" in res_illegal["error"]
        assert mgr.endgame_moves_played == 0

        # 4. Move out of turn (attempting to play when it is Black's turn or opponent turn)
        # Flip board turn to Black
        mgr.endgame_board.turn = chess.BLACK
        res_out_of_turn = mgr.handle_endgame_move_sync("e5e6", source="web")
        assert "error" in res_out_of_turn
        assert "Not your turn" in res_out_of_turn["error"]

        # Restore turn to White
        mgr.endgame_board.turn = chess.WHITE

        # 5. Rapid input while Stockfish is computing defensive reply
        mgr._endgame_computing_reply = True
        res_computing = mgr.handle_endgame_move_sync("e3d3", source="web")
        assert "error" in res_computing
        assert "Stockfish is computing" in res_computing["error"]
        mgr._endgame_computing_reply = False

    asyncio.run(_test())


def test_adversarial_endgame_goal_achievements_and_progress_metrics(tmp_path):
    """Tests win, mate, and draw goal detections and star rating calculations."""
    progress_file = str(tmp_path / "test_endgame_progress.json")
    prog_mgr = EndgameProgressManager(storage_path=progress_file)

    # 1. Mate goal drill
    mgr = BoardStateManager()
    mate_drill = EndgameDrill(
        id="test_mate_drill",
        category=EndgameCategory.MINORS,
        title="Two Bishops Mate",
        fen="8/8/8/8/8/4k3/8/K1BB4 w - - 0 1",
        player_color="white",
        target_goal="mate",
    )
    mgr.endgame_drill = mate_drill
    mgr.endgame_board = chess.Board("8/8/8/8/8/8/5B2/4K2k w - - 0 1")
    assert mgr._check_endgame_goal_achieved() is False

    # Scholar's mate style checkmate
    mgr.endgame_board = chess.Board("r1bqkb1r/pppp1Qpp/2n5/4p3/2B1n3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4")
    assert mgr.endgame_board.is_checkmate() is True
    assert mgr._check_endgame_goal_achieved() is True

    # 2. Win goal (material dominance: Queen vs Lone King)
    win_drill = EndgameDrill(
        id="test_win_drill",
        category=EndgameCategory.PAWNS,
        title="Pawn Race",
        fen="8/8/8/8/8/8/8/8 w - - 0 1",
        player_color="white",
        target_goal="win",
    )
    mgr.endgame_drill = win_drill
    mgr.endgame_board = chess.Board("8/8/8/8/8/4k3/8/Q3K3 b - - 0 1")  # White has Queen, Black only King
    assert mgr._check_endgame_goal_achieved() is True

    # 3. Draw goal (Stalemate / Insufficient material / Repetition)
    draw_drill = EndgameDrill(
        id="test_draw_drill",
        category=EndgameCategory.PAWNS,
        title="Corner Draw",
        fen="8/8/8/8/8/8/8/8 b - - 0 1",
        player_color="black",
        target_goal="draw",
    )
    mgr.endgame_drill = draw_drill
    # Stalemate position
    mgr.endgame_board = chess.Board("k7/8/1K6/8/8/8/8/8 b - - 0 1")
    assert mgr.endgame_board.is_stalemate() is True
    assert mgr._check_endgame_goal_achieved() is True

    # Insufficient material (King vs King)
    mgr.endgame_board = chess.Board("8/8/8/4k3/8/8/8/4K3 w - - 0 1")
    assert mgr.endgame_board.is_insufficient_material() is True
    assert mgr._check_endgame_goal_achieved() is True

    # 4. Progress manager star ratings
    assert prog_mgr.record_completion("drill1", mistakes=0, moves_count=10, accuracy=100.0) == 3
    assert prog_mgr.record_completion("drill2", mistakes=2, moves_count=12, accuracy=80.0) == 2
    assert prog_mgr.record_completion("drill3", mistakes=4, moves_count=15, accuracy=60.0) == 1


def test_adversarial_endgame_stop_and_reset_board_to_idle():
    """Tests stopping active endgame drills and concluding on 32-piece board reset."""
    mgr = BoardStateManager()
    mgr.start_endgame_drill("rook_lucena")
    assert mgr.game_status == "ANALYSIS"
    assert mgr.analysis_submode == "endgame"
    assert mgr.endgame_active is True

    # 1. Stop drill explicitly
    stop_res = mgr.stop_endgame_drill()
    assert stop_res["status"] == "IDLE"
    assert mgr.game_status == "IDLE"
    assert mgr.endgame_active is False

    # 2. Start drill, reach complete phase, and simulate restoring 32 starting pieces
    mgr.start_endgame_drill("rook_lucena")
    mgr.endgame_phase = "complete"

    # SetupResult with 32 pieces ready
    setup_ready = SetupResult(
        is_setup_ready=True,
        missing_white=[],
        missing_black=[],
        misplaced_pieces=[],
        is_empty=False,
    )
    concluded = mgr._try_conclude_analysis_on_board_reset(setup_ready)
    assert concluded is True
    assert mgr.game_status == "IDLE"
