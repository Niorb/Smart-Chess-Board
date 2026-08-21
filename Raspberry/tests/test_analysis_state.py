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


def test_handle_analysis_move_auto_advance():
    async def _test():
        mgr = BoardStateManager()
        moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
        await mgr.start_analysis_mode(moves_uci=moves)

        assert mgr.analysis_current_ply == 0

        # User plays the first move of the game (1. e4 -> e2e4)
        res1 = mgr.handle_analysis_move("e2e4")
        assert res1["action"] == "advance"
        assert res1["ply"] == 1
        assert mgr.analysis_current_ply == 1

        # User plays the second move of the game (1... e5 -> e7e5)
        res2 = mgr.handle_analysis_move("e7e5")
        assert res2["action"] == "advance"
        assert res2["ply"] == 2
        assert mgr.analysis_current_ply == 2

    asyncio.run(_test())


def test_handle_analysis_move_branch():
    async def _test():
        mgr = BoardStateManager()
        moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
        await mgr.start_analysis_mode(moves_uci=moves)

        # Move 1: e2e4
        mgr.handle_analysis_move("e2e4")
        assert mgr.analysis_current_ply == 1

        # User plays alternative: 1... c5 (c7c5) instead of 1... e5
        res_branch = mgr.handle_analysis_move("c7c5")
        assert res_branch["action"] == "branch"
        assert res_branch["branch_moves"] == ["c7c5"]
        assert mgr.analysis_anchor_ply == 1
        assert mgr.analysis_anchor_coord == (2, 6)  # c7 (file 2, rank 6)

    asyncio.run(_test())


def test_analysis_review_led_rule_a_best():
    """Verify that Best moves (delta <= 15cp) render Mint Emerald trace with no alternatives."""
    from unittest.mock import MagicMock
    from board_hardware import settings
    from app.led_helpers import COLOR_INT_MINT_EMERALD

    orig_nm = settings.get("night_mode", False)
    settings["night_mode"] = False
    try:
        mgr = BoardStateManager()
        mgr.strip = MagicMock()
        mgr.game_status = "ANALYSIS"
        mgr.analysis_submode = "review"
        mgr.analysis_game_moves = ["e2e4", "e7e5"]
        mgr.analysis_current_ply = 0
        mgr.analysis_played_analyses = [
            {"ply": 0, "delta_cp": 5, "classification": "best", "best_move": "e2e4"}
        ]
        mgr.analysis_evaluations = [
            {"win_chance": 50.0, "best_move": "e2e4"}
        ]

        mgr._update_leds()

        assert mgr.strip.setPixelColor.called
        assert mgr.strip.show.called

        call_args = [call[0] for call in mgr.strip.setPixelColor.call_args_list]
        colors_called = [arg[1] for arg in call_args]

        # e4 destination and e2 origin illuminated in Mint Emerald
        assert COLOR_INT_MINT_EMERALD in colors_called
    finally:
        settings["night_mode"] = orig_nm


def test_analysis_review_led_rule_a_good():
    """Verify that Good moves (15 < delta <= 60cp) render Cyan Azure trace."""
    from unittest.mock import MagicMock
    from board_hardware import settings
    from app.led_helpers import COLOR_INT_AZURE

    orig_nm = settings.get("night_mode", False)
    settings["night_mode"] = False
    try:
        mgr = BoardStateManager()
        mgr.strip = MagicMock()
        mgr.game_status = "ANALYSIS"
        mgr.analysis_submode = "review"
        mgr.analysis_game_moves = ["d2d4"]
        mgr.analysis_current_ply = 0
        mgr.analysis_played_analyses = [
            {"ply": 0, "delta_cp": 35, "classification": "good", "best_move": "e2e4"}
        ]
        mgr.analysis_evaluations = [
            {"win_chance": 50.0, "best_move": "e2e4"}
        ]

        mgr._update_leds()

        assert mgr.strip.setPixelColor.called
        assert mgr.strip.show.called

        call_args = [call[0] for call in mgr.strip.setPixelColor.call_args_list]
        colors_called = [arg[1] for arg in call_args]

        assert COLOR_INT_AZURE in colors_called
    finally:
        settings["night_mode"] = orig_nm


def test_analysis_review_led_rule_b_blunder_with_suggestion():
    """Verify that Blunder moves (delta > 150cp) render Rose Red + Emerald Green best move suggestion."""
    from unittest.mock import MagicMock
    from board_hardware import settings
    from app.led_helpers import COLOR_INT_MOVE_BLUNDER

    orig_nm = settings.get("night_mode", False)
    settings["night_mode"] = False
    try:
        mgr = BoardStateManager()
        mgr.strip = MagicMock()
        mgr.game_status = "ANALYSIS"
        mgr.analysis_submode = "review"
        mgr.analysis_game_moves = ["f2f3"]
        mgr.analysis_current_ply = 0
        mgr.analysis_played_analyses = [
            {"ply": 0, "delta_cp": 200, "classification": "blunder", "best_move": "e2e4"}
        ]
        mgr.analysis_evaluations = [
            {"win_chance": 35.0, "best_move": "e2e4"}
        ]

        mgr._update_leds()

        assert mgr.strip.setPixelColor.called
        assert mgr.strip.show.called

        call_args = [call[0] for call in mgr.strip.setPixelColor.call_args_list]
        colors_called = [arg[1] for arg in call_args]

        # Blunder color present
        assert COLOR_INT_MOVE_BLUNDER in colors_called
    finally:
        settings["night_mode"] = orig_nm


def test_analysis_review_led_divergence_beacons():
    """Verify that when diverged from main game, 4 corner rooks and anchor glow in Royal Violet."""
    from unittest.mock import MagicMock
    from board_hardware import settings
    from app.led_helpers import COLOR_INT_ROYAL_VIOLET

    orig_nm = settings.get("night_mode", False)
    settings["night_mode"] = False
    try:
        mgr = BoardStateManager()
        mgr.strip = MagicMock()
        mgr.game_status = "ANALYSIS"
        mgr.analysis_submode = "review"
        mgr.analysis_game_moves = ["e2e4", "e7e5"]
        mgr.analysis_current_ply = 1
        mgr.analysis_anchor_ply = 1
        mgr.analysis_anchor_coord = (2, 6)  # c7
        mgr.analysis_branch_moves = ["c7c5"]

        mgr._update_leds()

        assert mgr.strip.setPixelColor.called
        assert mgr.strip.show.called

        call_args = [call[0] for call in mgr.strip.setPixelColor.call_args_list]
        colors_called = [arg[1] for arg in call_args]

        # Royal Violet anchor is called
        assert COLOR_INT_ROYAL_VIOLET in colors_called
    finally:
        settings["night_mode"] = orig_nm


def test_handle_analysis_move_castling_advances_without_diverging():
    """Verify that playing a castling move in analysis mode cleanly advances without diverging."""
    async def _test():
        mgr = BoardStateManager()
        moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "e1g1", "g8f6"]
        await mgr.start_analysis_mode(moves_uci=moves)

        # Step to ply 6 (White's turn to play e1g1)
        mgr.step_analysis(6)
        assert mgr.analysis_current_ply == 6
        assert mgr.analysis_anchor_coord is None

        # Play White Kingside Castle (e1g1)
        res = mgr.handle_analysis_move("e1g1")
        assert res["action"] == "advance"
        assert res["ply"] == 7
        assert mgr.analysis_current_ply == 7
        assert mgr.analysis_anchor_coord is None
        assert mgr.analysis_anchor_ply is None
        assert len(mgr.analysis_branch_moves) == 0

    asyncio.run(_test())


def test_handle_analysis_move_san_castling_matching():
    """Verify that playing UCI e1g1 matches SAN O-O and advances without creating a branch."""
    async def _test():
        mgr = BoardStateManager()
        moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "O-O", "g8f6"]
        await mgr.start_analysis_mode(moves_uci=moves)

        mgr.step_analysis(6)
        assert mgr.analysis_current_ply == 6

        # UCI e1g1 should match O-O
        res = mgr.handle_analysis_move("e1g1")
        assert res["action"] == "advance"
        assert res["ply"] == 7
        assert mgr.analysis_current_ply == 7
        assert mgr.analysis_anchor_coord is None

    asyncio.run(_test())


def test_physical_castling_suppresses_intermediate_rook_moves():
    """Verify that during physical castling, lifting and placing the Rook is absorbed without rogue moves."""
    from app.physical_tracker import PhysicalMoveTracker

    tracker = PhysicalMoveTracker()
    board = chess.Board("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")

    class MockEngine:
        def __init__(self, b):
            self.board = b
            self.my_color = "white"
            self.game_info = {}

    engine = MockEngine(board)

    # Initial physical state matching board (White pieces on 1-2, Black on 7-8, etc.)
    phys_state = [[0] * 8 for _ in range(8)]
    for c in range(8):
        for r in range(8):
            sq = chess.square(c, r)
            p = board.piece_at(sq)
            if p:
                phys_state[c][r] = -1 if p.color == chess.WHITE else 1

    tracker.reset(phys_state)

    # Step 1: Player lifts King at e1 (4, 0)
    phys_state[4][0] = 0
    res1 = tracker.process_physical_state(phys_state, engine)
    assert res1 is None
    assert tracker.lifted_square == (4, 0)

    # Step 2: Player places King on g1 (6, 0) -> triggers castling detection
    phys_state[6][0] = -1
    res2 = tracker.process_physical_state(phys_state, engine)
    assert res2 == (5, 1, 7, 1, None)  # 1-indexed (e1 -> g1)
    assert tracker.pending_castling_rook == {"from": (7, 0), "to": (5, 0), "start_time": tracker.pending_castling_rook["start_time"]}

    # Update engine board with King move e1g1
    board.push_uci("e1g1")

    # Step 3: Player lifts Rook from h1 (7, 0) while pending_castling_rook is active
    phys_state[7][0] = 0
    res3 = tracker.process_physical_state(phys_state, engine)
    # Must NOT emit a rogue move or branch move!
    assert res3 is None
    assert tracker.pending_castling_rook is not None

    # Step 4: Player places Rook on f1 (5, 0)
    phys_state[5][0] = -1
    res4 = tracker.process_physical_state(phys_state, engine)
    assert res4 is None
    # Castling Rook placement is confirmed, pending_castling_rook is cleared
    assert tracker.pending_castling_rook is None
    assert tracker.arrival_flash is not None
    assert tracker.arrival_flash["square"] == (5, 0)


