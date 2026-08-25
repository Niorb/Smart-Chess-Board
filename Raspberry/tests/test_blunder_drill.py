import asyncio
import os
import sys

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.board_state import BoardStateManager


def test_blunder_drill_flow():
    async def _test():
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

    asyncio.run(_test())


def test_gm_replay_learn_flow():
    async def _test():
        mgr = BoardStateManager()
        payload = mgr.start_gm_game("morphy_opera_1858")
        assert payload["submode"] == "replay_learn"
        assert payload["gm_game"]["title"] == "Morphy's Opera Game"
        assert payload["current_ply"] == 0
        assert payload["replay"]["phase"] == "learn"
        assert payload["replay"]["learned_ply"] == 0

        # Correct first move: e2e4
        res1 = mgr.handle_replay_move("e2e4")
        assert res1["action"] == "advance"
        assert mgr.analysis_current_ply == 1
        assert mgr.replay_learned_ply == 1

        # Incorrect move for ply 1 -> divergence, does not advance
        expected_second = mgr.analysis_game_moves[1]
        wrong = "a7a6" if expected_second != "a7a6" else "b2b3"
        res2 = mgr.handle_replay_move(wrong)
        assert res2["action"] == "incorrect"
        assert res2["gm_move"] == expected_second
        assert mgr.analysis_current_ply == 1
        assert mgr.analysis_anchor_coord is not None
        assert len(mgr.analysis_branch_moves) == 1

    asyncio.run(_test())
