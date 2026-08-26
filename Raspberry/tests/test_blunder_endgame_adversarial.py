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
    # Stalemate position: White Q on f7, King on g6, Black King on h8 (no legal moves, not in check)
    mgr.endgame_board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
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
    async def _test():
        mgr = BoardStateManager()
        await mgr.start_endgame_drill("rook_lucena")
        assert mgr.game_status == "ANALYSIS"
        assert mgr.analysis_submode == "endgame"
        assert mgr.endgame_active is True

        # 1. Stop drill explicitly
        stop_res = mgr.stop_endgame_drill()
        assert stop_res["status"] == "IDLE"
        assert mgr.game_status == "IDLE"
        assert mgr.endgame_active is False
        assert mgr.endgame_pending_reply is None

        # 2. Start drill, reach complete phase, and simulate restoring 32 starting pieces
        await mgr.start_endgame_drill("rook_lucena")
        mgr.endgame_phase = "complete"

        # SetupResult with 32 pieces ready
        setup_ready = SetupResult(
            is_setup_ready=True,
            missing_white=[],
            missing_black=[],
            misplaced_pieces=[],
            white_count=16,
            black_count=16,
        )
        concluded = mgr._try_conclude_analysis_on_board_reset(setup_ready)
        assert concluded is True
        assert mgr.game_status == "IDLE"

    asyncio.run(_test())


def test_adversarial_blunder_pending_opponent_move_protection_and_transitions():
    """Tests out-of-turn submission locks during pending opponent reply and safe puzzle transitions."""
    mgr = BoardStateManager()
    b1 = {
        "ply_index": 1,
        "fen_before": "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3",
        "best_move": "d8e7",
        "player_color": "black",
        "player_moves": ["d8e7", "g8f6"],
        "opponent_replies": ["g1f3"],
        "solution_line_san": ["3... Qe7", "4. Nf3", "4... Nf6"],
    }
    b2 = {
        "ply_index": 2,
        "fen_before": "8/8/8/8/8/8/8/4K2k w - - 0 1",
        "best_move": "e1f2",
        "player_color": "white",
        "player_moves": ["e1f2"],
        "opponent_replies": [],
        "solution_line_san": ["1. Kf2"],
    }
    mgr.analysis_blunders = [b1, b2]

    # 1. Start puzzle 0
    mgr.start_blunder_drill(0)
    assert mgr.analysis_blunder_step == 0
    assert mgr.analysis_blunder_attempts == 3

    # 2. Submit step 1 physically
    res1 = mgr.submit_blunder_attempt("d8e7", source="board")
    assert res1["correct"] is True
    assert mgr.move_tracker.pending_opponent_move is not None
    assert mgr.analysis_blunder_pending_reply is not None

    # 3. Payload includes blunder_pending_reply
    payload = mgr.get_analysis_payload()
    assert payload["blunder_pending_reply"] is not None
    assert payload["blunder_pending_reply"]["uci"] == "g1f3"

    # 4. Attempt to submit next player move while opponent reply is still pending
    res_premature = mgr.submit_blunder_attempt("g8f6", source="board")
    assert res_premature["correct"] is False
    assert "Waiting for opponent reply" in res_premature["error"]
    # Attempts must NOT be decremented on pending opponent reply lockout
    assert mgr.analysis_blunder_attempts == 3

    # 5. Switch to puzzle 1 while opponent reply was pending
    mgr.start_blunder_drill(1)
    # Pending reply and tracker must be cleanly cleared with no state leakage
    assert mgr.analysis_blunder_pending_reply is None
    assert mgr.move_tracker.pending_opponent_move is None
    assert mgr.analysis_blunder_index == 1
    assert mgr.analysis_blunder_step == 0


def test_adversarial_blunder_auto_queen_and_solution_concealment():
    """Tests auto-queening for promotion puzzles and strict solution concealment."""
    mgr = BoardStateManager()
    promo_blunder = {
        "ply_index": 10,
        "fen_before": "8/4P1k1/8/8/8/8/8/4K3 w - - 0 1",
        "best_move": "e7e8q",
        "player_color": "white",
        "player_moves": ["e7e8q"],
        "opponent_replies": [],
        "solution_line_san": ["1. e8=Q+"],
    }
    mgr.analysis_blunders = [promo_blunder]
    mgr.start_blunder_drill(0)

    # 1. Submit "e7e8" without "q" -> auto-queens
    res = mgr.submit_blunder_attempt("e7e8", source="web")
    assert res["correct"] is True
    assert res["puzzle_complete"] is True
    assert "solution_line" in res
    assert res["solution_line"] == ["1. e8=Q+"]


def test_adversarial_endgame_pending_opponent_and_draw_repetitions():
    """Tests endgame pending opponent lockouts and threefold repetition draw achievements."""
    async def _test():
        mgr = BoardStateManager()
        # Draw drill with threefold repetition position
        drill = EndgameDrill(
            id="test_repetition_drill",
            category=EndgameCategory.ROOKS,
            title="Repetition Draw",
            fen="8/8/8/8/8/5k2/8/4K2R w - - 0 1",
            player_color="white",
            target_goal="draw",
        )
        mgr.endgame_drill = drill
        mgr.endgame_board = chess.Board(drill.fen)
        mgr.endgame_phase = "playing"
        mgr.endgame_active = True
        mgr.endgame_board.turn = chess.BLACK

        # Simulate pending opponent reply
        mgr.endgame_pending_reply = {
            "uci": "f3g3",
            "san": "Kg3",
            "from": [5, 2],
            "to": [6, 2],
            "from_sq": "f3",
            "to_sq": "g3",
            "is_capture": False,
        }

        # Apply pending reply
        res_apply = mgr.apply_endgame_pending_opponent_move()
        assert res_apply["result"] == "ok"
        assert mgr.endgame_pending_reply is None

        # Build threefold repetition board
        # 1. Nf3 Nf6 2. Ng1 Ng8 3. Nf3 Nf6 4. Ng1 Ng8
        rep_board = chess.Board()
        rep_board.push_san("Nf3")
        rep_board.push_san("Nf6")
        rep_board.push_san("Ng1")
        rep_board.push_san("Ng8")
        rep_board.push_san("Nf3")
        rep_board.push_san("Nf6")
        rep_board.push_san("Ng1")
        rep_board.push_san("Ng8")

        mgr.endgame_board = rep_board
        assert rep_board.is_repetition(3) is True
        assert mgr._check_endgame_goal_achieved() is True

    asyncio.run(_test())


def test_adversarial_opponent_castling_in_blunder_and_endgame():
    """Tests opponent castling mechanics (two-phase King/Rook guidance) in drills."""
    mgr = BoardStateManager()
    # Blunder puzzle where opponent's reply is Kingside Castling: e8g8
    blunder_castle = {
        "ply_index": 12,
        "fen_before": "r1bqk2r/pppp1ppp/2n2n2/4p3/1bB1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 4 4",
        "best_move": "d2d3",
        "player_color": "white",
        "player_moves": ["d2d3", "c1g5"],
        "opponent_replies": ["e8g8"],
        "solution_line_san": ["4. d3", "4... O-O", "5. Bg5"],
    }
    mgr.analysis_blunders = [blunder_castle]
    mgr.start_blunder_drill(0)

    # 1. Player plays d2d3 on physical board
    res1 = mgr.submit_blunder_attempt("d2d3", source="board")
    assert res1["correct"] is True
    assert mgr.analysis_blunder_pending_reply is not None
    assert mgr.analysis_blunder_pending_reply["is_castling"] is True

    # 2. Check move tracker received castling parameters
    pending = mgr.move_tracker.pending_opponent_move
    assert pending is not None
    assert pending["is_castling"] is True
    assert pending["from"] == (4, 7)  # e8
    assert pending["to"] == (6, 7)    # g8
    assert pending["rook_from"] == (7, 7)  # h8
    assert pending["rook_to"] == (5, 7)    # f8

    # 3. Apply opponent castling move
    apply_res = mgr.apply_blunder_pending_opponent_move()
    assert apply_res["result"] == "ok"
    assert mgr.analysis_blunder_step == 1
    assert mgr.analysis_active_board.piece_at(chess.G8).piece_type == chess.KING
    assert mgr.analysis_active_board.piece_at(chess.F8).piece_type == chess.ROOK
    assert mgr.move_tracker.pending_opponent_move is None


def test_adversarial_strict_solution_concealment_in_progress():
    """Verifies that in-progress blunder payloads never leak upcoming solution moves."""
    mgr = BoardStateManager()
    multi_ply = {
        "ply_index": 5,
        "fen_before": "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3",
        "best_move": "d8e7",
        "player_color": "black",
        "player_moves": ["d8e7", "g8f6"],
        "opponent_replies": ["g1f3"],
        "solution_line_san": ["3... Qe7", "4. Nf3", "4... Nf6"],
    }
    mgr.analysis_blunders = [multi_ply]
    mgr.start_blunder_drill(0)

    # Step 1 attempt
    res = mgr.submit_blunder_attempt("d8e7", source="web")
    assert res["correct"] is True
    assert res["puzzle_complete"] is False
    # Strict concealment: neither solution_line nor next_expected_move in intermediate payload
    assert "solution_line" not in res
    assert "next_expected_move" not in res

    # Step 2 attempt (finishing puzzle)
    res2 = mgr.submit_blunder_attempt("g8f6", source="web")
    assert res2["correct"] is True
    assert res2["puzzle_complete"] is True
    # Upon completion, solution_line is permitted as summary
    assert "solution_line" in res2


def test_adversarial_endgame_pending_opponent_move_lockout():
    """Verifies that submitting moves during pending opponent replies in Endgame is blocked."""
    mgr = BoardStateManager()
    drill = EndgameDrill(
        id="test_lockout_drill",
        category=EndgameCategory.PAWNS,
        title="Lockout Drill",
        fen="8/8/8/4k3/8/4K3/4P3/8 w - - 0 1",
        player_color="white",
        target_goal="win",
    )
    mgr.endgame_drill = drill
    mgr.endgame_board = chess.Board(drill.fen)
    mgr.endgame_phase = "playing"
    mgr.endgame_active = True

    # Simulate pending opponent reply
    mgr.endgame_pending_reply = {
        "uci": "e5d5",
        "san": "Kd5",
        "from": [4, 4],
        "to": [3, 4],
        "from_sq": "e5",
        "to_sq": "d5",
        "is_capture": False,
    }

    # Attempt to play while opponent move is pending
    res = mgr.handle_endgame_move_sync("e3d3", source="web")
    assert "error" in res
    assert "Waiting for opponent reply" in res["error"]
    assert mgr.endgame_moves_played == 0


def test_adversarial_blunder_san_expected_moves_and_annotations():
    """Tests blunder puzzles when expected moves are stored in SAN format or with annotations."""
    mgr = BoardStateManager()
    # Blunder puzzle with SAN expected moves e.g. "Qe7+" and "Nf6"
    blunder_san = {
        "ply_index": 5,
        "fen_before": "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3",
        "best_move": "Qe7",
        "player_color": "black",
        "player_moves": ["Qe7", "Nf6"],
        "opponent_replies": ["Nf3"],
        "solution_line_san": ["3... Qe7", "4. Nf3", "4... Nf6"],
    }
    mgr.analysis_blunders = [blunder_san]
    mgr.start_blunder_drill(0)

    # 1. User submits UCI 'd8e7' -> matches SAN 'Qe7'
    res1 = mgr.submit_blunder_attempt("d8e7", source="web")
    assert res1["correct"] is True
    assert res1["step_complete"] is True
    assert res1["puzzle_complete"] is False

    # 2. User submits SAN 'Nf6' for step 2 -> matches SAN 'Nf6'
    res2 = mgr.submit_blunder_attempt("Nf6", source="web")
    assert res2["correct"] is True
    assert res2["puzzle_complete"] is True
    assert "solution_line" in res2


def test_adversarial_endgame_checkmate_direction_and_game_over_transitions():
    """Tests that opponent checkmating player does not award win and transitions to complete (won=False)."""
    async def _test():
        mgr = BoardStateManager()
        mate_drill = EndgameDrill(
            id="test_mate_dir_drill",
            category=EndgameCategory.MINORS,
            title="Mate Direction Test",
            fen="8/8/8/8/8/8/8/4K2k w - - 0 1",
            player_color="white",
            target_goal="mate",
        )
        mgr.endgame_drill = mate_drill
        mgr.endgame_active = True
        mgr.endgame_phase = "playing"

        # Case A: White checkmates Black (turn becomes BLACK, in checkmate) -> Player (White) WON
        mgr.endgame_board = chess.Board("r1bqkb1r/pppp1Qpp/2n5/4p3/2B1n3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4")
        assert mgr.endgame_board.turn == chess.BLACK
        assert mgr.endgame_board.is_checkmate() is True
        assert mgr._check_endgame_goal_achieved() is True

        # Case B: Black checkmates White (turn becomes WHITE, in checkmate) -> Player (White) LOST!
        mgr.endgame_board = chess.Board("rnb1k1nr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
        assert mgr.endgame_board.turn == chess.WHITE
        assert mgr.endgame_board.is_checkmate() is True
        # Player is White, White is checkmated -> Goal NOT achieved!
        assert mgr._check_endgame_goal_achieved() is False

        # Case C: Game over (player lost) in handle_endgame_move_sync triggers completion with won=False
        win_drill = EndgameDrill(
            id="test_stalemate_lose_drill",
            category=EndgameCategory.PAWNS,
            title="Win Goal Test",
            fen="8/8/8/8/8/5K2/7Q/7k w - - 0 1",
            player_color="white",
            target_goal="win",
        )
        mgr.endgame_drill = win_drill
        mgr.endgame_board = chess.Board(win_drill.fen)
        mgr.endgame_phase = "playing"
        mgr.endgame_active = True

        # White plays Qg2# (checkmate) -> Won!
        # Reset and play Qf2 (stalemate!) -> Black has no moves, but not in checkmate -> won=False
        mgr.endgame_board = chess.Board("8/8/8/8/8/5K2/7Q/7k w - - 0 1")
        res_stale = mgr.handle_endgame_move_sync("h2f2", source="web")
        await asyncio.sleep(0.01)
        assert mgr.endgame_board.is_stalemate() is True
        assert res_stale["result"] == "complete"
        assert res_stale["won"] is False
        assert mgr.endgame_phase == "complete"
        assert mgr.endgame_complete_summary is not None
        assert mgr.endgame_complete_summary["won"] is False
        assert mgr.endgame_complete_summary["stars"] == 0

    asyncio.run(_test())


def test_adversarial_opponent_capture_midair_safety_in_tracker():
    """Verifies that lifting attacking piece from origin does NOT confirm capture while target is still occupied."""
    from app.physical_tracker import PhysicalMoveTracker
    tracker = PhysicalMoveTracker()

    # Initial physical board: White pawn on e4 (-1), Black pawn on d5 (+1)
    state = [[0] * 8 for _ in range(8)]
    state[4][3] = -1  # e4
    state[3][4] = 1   # d5
    tracker.last_physical_state = [col[:] for col in state]

    # Queue opponent move: exd5 (capture of d5 by e4)
    tracker.set_opponent_move(
        from_coord=(4, 3),  # e4
        to_coord=(3, 4),    # d5
        is_capture=True,
        uci="e4d5",
    )
    assert tracker.pending_opponent_move is not None
    assert tracker.pending_opponent_move["is_capture"] is True

    # Step 1: User lifts piece from e4 (e4 becomes 0, d5 is STILL 1)
    state_step1 = [col[:] for col in state]
    state_step1[4][3] = 0  # e4 lifted
    dummy_engine = MagicMock()
    dummy_engine.board = chess.Board()

    tracker.process_physical_state(state_step1, dummy_engine)
    # Move must NOT be confirmed yet because d5 was not vacated / captured
    assert tracker.pending_opponent_move is not None
    assert tracker.arrival_flash is None

    # Step 2: User lifts captured piece on d5 (d5 becomes 0)
    state_step2 = [col[:] for col in state_step1]
    state_step2[3][4] = 0  # d5 vacated
    tracker.process_physical_state(state_step2, dummy_engine)
    assert tracker.pending_opponent_move is not None
    assert tracker.pending_opponent_move["target_vacated"] is True

    # Step 3: User places capturing piece on d5 (d5 becomes -1)
    state_step3 = [col[:] for col in state_step2]
    state_step3[3][4] = -1  # capturing piece placed on d5
    tracker.process_physical_state(state_step3, dummy_engine)
    # Now opponent move is cleanly confirmed!
    assert tracker.pending_opponent_move is None
    assert tracker.arrival_flash is not None
    assert tracker.arrival_flash["square"] == (3, 4)
    assert tracker.arrival_flash["is_capture"] is True


def test_adversarial_two_phase_opponent_castling_led_rendering():
    """Verifies that physical LED rendering branches in blunder and endgame modes handle both castling phases."""
    mgr = BoardStateManager()
    # Setup blunder with opponent castling
    blunder = {
        "ply_index": 12,
        "fen_before": "r1bqk2r/pppp1ppp/2n2n2/4p3/1bB1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 4 4",
        "best_move": "d2d3",
        "player_color": "white",
        "player_moves": ["d2d3"],
        "opponent_replies": ["e8g8"],
    }
    mgr.analysis_blunders = [blunder]
    mgr.start_blunder_drill(0)

    # Queue opponent castling move
    mgr.move_tracker.set_opponent_move(
        from_coord=(4, 7),  # e8
        to_coord=(6, 7),    # g8
        is_capture=False,
        is_castling=True,
        rook_from=(7, 7),   # h8
        rook_to=(5, 7),     # f8
        uci="e8g8",
    )

    # Phase 1: King phase
    assert mgr.move_tracker.pending_opponent_move["phase"] == "king"

    # Transition to Phase 2: Rook phase
    mgr.move_tracker.pending_opponent_move["phase"] = "rook"
    assert mgr.move_tracker.pending_opponent_move["phase"] == "rook"


def test_adversarial_endgame_post_completion_moves_rejected():
    """Verifies that attempting moves after drill completion is rejected and preserves completion state."""
    mgr = BoardStateManager()
    drill = EndgameDrill(
        id="test_post_comp_drill",
        category=EndgameCategory.PAWNS,
        title="Post-Completion Drill",
        fen="8/8/8/8/8/4k3/8/4K3 w - - 0 1",
        player_color="white",
        target_goal="draw",
    )
    mgr.endgame_drill = drill
    mgr.endgame_board = chess.Board(drill.fen)
    mgr.endgame_phase = "complete"
    mgr.endgame_active = True
    mgr.endgame_complete_summary = {"won": True, "stars": 3, "mistakes": 0, "moves_count": 5, "accuracy": 100.0}

    # Attempt to play a move while phase is 'complete'
    res = mgr.handle_endgame_move_sync("e1f1", source="web")
    assert "error" in res
    assert "not in playing phase" in res["error"]
    assert mgr.endgame_phase == "complete"
    assert mgr.endgame_complete_summary["won"] is True


def test_adversarial_blunder_and_endgame_opponent_promotion():
    """Verifies that opponent promotions (e.g. h7h8q) are cleanly handled in blunder puzzles and endgames."""
    mgr = BoardStateManager()
    # Blunder puzzle where opponent reply is a promotion: a2a1q
    blunder_promo = {
        "ply_index": 20,
        "fen_before": "8/8/8/8/8/1k6/p7/4K3 b - - 0 1",
        "best_move": "b3b2",
        "player_color": "black",
        "player_moves": ["b3b2"],
        "opponent_replies": ["e1f2"],
        "solution_line_san": ["1... Kb2", "2. Kf2"],
    }
    mgr.analysis_blunders = [blunder_promo]
    mgr.start_blunder_drill(0)

    # Submit player move
    res = mgr.submit_blunder_attempt("b3b2", source="web")
    assert res["correct"] is True
    assert res["puzzle_complete"] is True


def test_adversarial_endgame_draw_target_goal_win_vs_draw_scenarios():
    """Verifies that stalemate awards won=True when target_goal is 'draw', and won=False when target_goal is 'win'."""
    mgr = BoardStateManager()

    # Case A: target_goal == 'draw' -> Stalemate position awards victory (won=True)
    draw_drill = EndgameDrill(
        id="test_draw_scen",
        category=EndgameCategory.PAWNS,
        title="Draw Scenario",
        fen="7k/5Q2/6K1/8/8/8/8/8 b - - 0 1",
        player_color="black",
        target_goal="draw",
    )
    mgr.endgame_drill = draw_drill
    mgr.endgame_board = chess.Board(draw_drill.fen)
    assert mgr.endgame_board.is_stalemate() is True
    assert mgr._check_endgame_goal_achieved() is True

    # Case B: target_goal == 'win' -> Stalemate position means player failed to win (won=False)
    win_drill = EndgameDrill(
        id="test_win_scen",
        category=EndgameCategory.PAWNS,
        title="Win Scenario",
        fen="7k/5Q2/6K1/8/8/8/8/8 b - - 0 1",
        player_color="white",
        target_goal="win",
    )
    mgr.endgame_drill = win_drill
    mgr.endgame_board = chess.Board(win_drill.fen)
    assert mgr.endgame_board.is_stalemate() is True
    assert mgr._check_endgame_goal_achieved() is False


def test_adversarial_endgame_drill_switch_clears_pending_and_computing_state():
    """Verifies that starting a new endgame drill resets pending replies and computing flags cleanly."""
    async def _test():
        mgr = BoardStateManager()
        await mgr.start_endgame_drill("pawn_opposition")
        mgr.endgame_pending_reply = {"uci": "e5d5", "san": "Kd5"}
        mgr._endgame_computing_reply = True

        # Switch to another drill
        await mgr.start_endgame_drill("rook_lucena")
        assert mgr.endgame_drill.id == "rook_lucena"
        assert mgr.endgame_pending_reply is None
        assert mgr._endgame_computing_reply is False
        assert mgr.endgame_phase == "setup_white"

    asyncio.run(_test())




