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

        # Verify extracted puzzle metadata
        blunder0 = mgr.analysis_blunders[0]
        assert "player_color" in blunder0
        assert "opponent_color" in blunder0
        assert blunder0["player_color"] != blunder0["opponent_color"]

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
        best_move = blunder0["best_move"]
        res_correct = mgr.submit_blunder_attempt(best_move)
        assert res_correct["correct"] is True
        assert "step_complete" in res_correct
        assert "puzzle_complete" in res_correct

    asyncio.run(_test())


def test_puzzle_opponent_moves_and_continuation():
    """Tests that puzzles provide opponent setup move and execute opponent replies."""
    from app.coach_engine import coach_engine

    played_analyses = [
        {"ply": 0, "turn": "white", "uci": "e2e4", "san": "e4", "delta_cp": 0, "classification": "best"},
        {"ply": 1, "turn": "black", "uci": "e7e5", "san": "e5", "delta_cp": 0, "classification": "best"},
        {"ply": 2, "turn": "white", "uci": "d1h5", "san": "Qh5", "delta_cp": 0, "classification": "good"},
        {"ply": 3, "turn": "black", "uci": "b8c6", "san": "Nc6", "delta_cp": 0, "classification": "best"},
        {"ply": 4, "turn": "white", "uci": "f1c4", "san": "Bc4", "delta_cp": 0, "classification": "best"},
        {"ply": 5, "turn": "black", "uci": "g8f6", "san": "Nf6", "delta_cp": 500, "classification": "blunder", "best_move": "d8e7"},
    ]
    evaluations = [
        {"fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"},
        {"fen": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"},
        {"fen": "rnbqkbnr/pppp1ppp/8/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR b KQkq - 1 2"},
        {"fen": "r1bqkbnr/pppp1ppp/2n5/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR w KQkq - 2 3"},
        {"fen": "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"},
        {
            "fen": "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4",
            "score_cp": 500,
            "best_move": "d8e7",
            "top_moves": [{"pv": ["d8e7", "g1f3", "g8f6"], "score_cp": 0}],
        },
    ]

    puzzles = coach_engine.extract_blunders(played_analyses, evaluations)
    assert len(puzzles) >= 1
    p = puzzles[0]
    # The side we play is Black (who made the blunder and needs to find the refutation)
    assert p.player_color == "black"
    # The side we don't play is White
    assert p.opponent_color == "white"
    # The opponent's move leading into this puzzle was Bc4
    assert p.opponent_prev_move_san == "Bc4"
    assert p.opponent_prev_move_uci == "f1c4"
    assert len(p.player_moves) >= 1
    assert len(p.opponent_replies) >= 1
    # Opponent reply from the side we don't play is g1f3
    assert p.opponent_replies[0] == "g1f3"


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
