import asyncio
import os
import sys

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import chess
from app.board_state import BoardStateManager


def test_start_analysis_mode():
    async def _test():
        mgr = BoardStateManager()
        moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
        payload = await mgr.start_analysis_mode(moves_uci=moves)

        assert payload["active"] is True
        assert payload["submode"] == "review"
        assert payload["total_plys"] == 4
        assert payload["game_moves"] == moves
        assert len(payload["evaluations"]) >= 4
        assert payload["accuracy"]["white"] > 0
        assert payload["accuracy"]["black"] > 0

    asyncio.run(_test())


def test_step_analysis():
    async def _test():
        mgr = BoardStateManager()
        moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
        await mgr.start_analysis_mode(moves_uci=moves)

        # Step to ply 2 (after 1... e5)
        p2 = mgr.step_analysis(2)
        assert p2["current_ply"] == 2
        assert mgr.analysis_active_board.fen() == chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2").fen()

        # Step to ply 4 (after 2... Nc6)
        p4 = mgr.step_analysis(4)
        assert p4["current_ply"] == 4
        assert p4["is_branching"] is False

    asyncio.run(_test())


def test_analysis_branching_and_reset():
    async def _test():
        mgr = BoardStateManager()
        moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
        await mgr.start_analysis_mode(moves_uci=moves)

        # Step to ply 2 (after 1... e5)
        mgr.step_analysis(2)

        # User plays an alternative move: 2. f4 (f2f4) instead of 2. Nf3
        alt_move = chess.Move.from_uci("f2f4")
        assert alt_move in mgr.analysis_active_board.legal_moves

        mgr.analysis_anchor_ply = 2
        mgr.analysis_anchor_coord = (5, 1)  # f2
        mgr.analysis_active_board.push(alt_move)
        mgr.analysis_branch_moves.append("f2f4")

        payload = mgr.get_analysis_payload()
        assert payload["is_branching"] is True
        assert payload["branch_moves"] == ["f2f4"]
        assert payload["anchor_ply"] == 2

        # Reset branch back to game timeline
        reset_payload = mgr.reset_analysis_branch()
        assert reset_payload["is_branching"] is False
        assert reset_payload["current_ply"] == 2
        assert reset_payload["branch_moves"] == []

    asyncio.run(_test())


def test_stop_analysis_mode():
    async def _test():
        mgr = BoardStateManager()
        await mgr.start_analysis_mode(moves_uci=["e2e4", "e7e5"])
        assert mgr.game_status == "ANALYSIS"

        mgr.stop_analysis_mode()
        assert mgr.game_status == "IDLE"

    asyncio.run(_test())
