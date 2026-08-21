"""
tests/test_blunder_drill.py

Unit tests for Blunder Blitz drill and GM Relive guess-the-move features.
"""

import pytest
import chess
from app.board_state import BoardStateManager


@pytest.mark.asyncio
async def test_blunder_drill_flow():
    mgr = BoardStateManager()
    # Mock a game with a blunder: 1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7#
    moves = ["e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6", "h5f7"]
    await mgr.start_analysis_mode(moves_uci=moves)

    assert len(mgr.analysis_blunders) > 0

    # Start blunder drill
    payload = mgr.start_blunder_drill(0)
    assert payload["submode"] == "blunder_drill"
    assert payload["blunder_attempts"] == 3

    # Incorrect attempt
    res_wrong = mgr.submit_blunder_attempt("a7a6")
    assert res_wrong["correct"] is False
    assert res_wrong["attempts_remaining"] == 2

    # Toggle hint
    assert mgr.toggle_blunder_hint() is True
    assert mgr.toggle_blunder_hint() is False

    # Correct attempt
    best_move = mgr.analysis_blunders[0]["best_move"]
    res_correct = mgr.submit_blunder_attempt(best_move)
    assert res_correct["correct"] is True


@pytest.mark.asyncio
async def test_gm_relive_flow():
    mgr = BoardStateManager()
    payload = mgr.start_gm_game("morphy_opera_1858")
    assert payload["submode"] == "gm_relive"
    assert payload["gm_game"]["title"] == "Morphy's Opera Game"
    assert payload["current_ply"] == 0

    # Correct first move: e2e4
    res1 = mgr.submit_gm_guess("e2e4")
    assert res1["match"] == "exact"
    assert res1["points"] == 100
    assert mgr.analysis_current_ply == 1

    # Incorrect guess for move 2
    res2 = mgr.submit_gm_guess("a7a6")
    assert res2["match"] == "incorrect"
    assert res2["points"] == 0
    assert mgr.analysis_current_ply == 1  # Does not advance on incorrect guess
