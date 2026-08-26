import asyncio
import os
import sys
from types import SimpleNamespace

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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

    from app.led_helpers import COLOR_INT_MINT_EMERALD
    from board_hardware import settings

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

    from app.led_helpers import COLOR_INT_AZURE
    from board_hardware import settings

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

    from app.led_helpers import COLOR_INT_MOVE_BLUNDER
    from board_hardware import settings

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

    from app.led_helpers import COLOR_INT_ROYAL_VIOLET
    from board_hardware import settings

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


def test_analysis_auto_snap_back_on_anchor_restoration():
    """Verify that when the user puts back the anchor position, the board automatically snaps back to the game."""
    async def _test():
        mgr = BoardStateManager()
        moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
        await mgr.start_analysis_mode(moves_uci=moves)

        # Advance to ply 2 (1. e4 e5)
        mgr.step_analysis(2)
        assert mgr.analysis_current_ply == 2

        # User diverges by playing alternative move 2. d4 (d2d4)
        res_branch = mgr.handle_analysis_move("d2d4")
        assert res_branch["action"] == "branch"
        assert mgr.analysis_anchor_ply == 2
        assert mgr.analysis_anchor_coord == (3, 1)  # d2
        assert mgr.analysis_branch_moves == ["d2d4"]

        # Board position at ply 2 (1. e4 e5)
        anchor_b = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")

        # Construct physical state matching anchor_b
        phys_state = [[0] * 8 for _ in range(8)]
        for c in range(8):
            for r in range(8):
                p = anchor_b.piece_at(chess.square(c, r))
                if p:
                    phys_state[c][r] = -1 if p.color == chess.WHITE else 1

        mgr.physical_state = phys_state
        mgr.move_tracker.reset(phys_state)

        # Execute restoration check
        restored = mgr._check_analysis_board_restoration()
        assert restored is True
        assert mgr.analysis_anchor_coord is None
        assert mgr.analysis_anchor_ply is None
        assert mgr.analysis_branch_moves == []
        assert mgr.analysis_current_ply == 2
        assert mgr.analysis_active_board.fen().startswith("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -")

        # Now playing the next game move (2. Nf3 / g1f3) auto-advances
        res_adv = mgr.handle_analysis_move("g1f3")
        assert res_adv["action"] == "advance"
        assert mgr.analysis_current_ply == 3

    asyncio.run(_test())


def test_analysis_step_by_step_branch_undo():
    """Verify that taking back moves along a branch step-by-step updates branch depth until snapping back."""
    async def _test():
        mgr = BoardStateManager()
        moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
        await mgr.start_analysis_mode(moves_uci=moves)

        mgr.step_analysis(2)
        mgr.handle_analysis_move("d2d4")
        mgr.handle_analysis_move("e5d4")
        assert len(mgr.analysis_branch_moves) == 2

        # Step back 1: Position after 2. d4 (1. e4 e5 2. d4)
        board_d4 = chess.Board()
        board_d4.push_uci("e2e4")
        board_d4.push_uci("e7e5")
        board_d4.push_uci("d2d4")
        phys_d4 = [[0] * 8 for _ in range(8)]
        for c in range(8):
            for r in range(8):
                p = board_d4.piece_at(chess.square(c, r))
                if p:
                    phys_d4[c][r] = -1 if p.color == chess.WHITE else 1

        mgr.physical_state = phys_d4
        mgr.move_tracker.reset(phys_d4)

        restored_step = mgr._check_analysis_board_restoration()
        assert restored_step is True
        assert len(mgr.analysis_branch_moves) == 1
        assert mgr.analysis_anchor_coord is not None

        # Step back 2: Position at anchor (1. e4 e5)
        board_anchor = chess.Board()
        board_anchor.push_uci("e2e4")
        board_anchor.push_uci("e7e5")
        phys_anchor = [[0] * 8 for _ in range(8)]
        for c in range(8):
            for r in range(8):
                p = board_anchor.piece_at(chess.square(c, r))
                if p:
                    phys_anchor[c][r] = -1 if p.color == chess.WHITE else 1

        mgr.physical_state = phys_anchor
        mgr.move_tracker.reset(phys_anchor)

        restored_full = mgr._check_analysis_board_restoration()
        assert restored_full is True
        assert mgr.analysis_anchor_coord is None
        assert mgr.analysis_branch_moves == []
        assert mgr.analysis_current_ply == 2

    asyncio.run(_test())


def test_analysis_board_reset_to_starting_position_transitions_to_idle():
    """Verify that when pieces are put back into standard starting position, analysis ends and board returns to IDLE."""
    async def _test():
        from unittest.mock import MagicMock

        mgr = BoardStateManager()
        mgr.strip = MagicMock()
        moves = ["e2e4", "e7e5", "g1f3", "b8c6"]
        await mgr.start_analysis_mode(moves_uci=moves)

        # Advance to end of analysis / ply 4
        mgr.step_analysis(4)
        assert mgr.game_status == "ANALYSIS"
        assert mgr.analysis_has_advanced is True

        # Construct initial standard starting board state (32 pieces)
        start_board = chess.Board()
        phys_start = [[0] * 8 for _ in range(8)]
        for c in range(8):
            for r in range(8):
                p = start_board.piece_at(chess.square(c, r))
                if p:
                    phys_start[c][r] = -1 if p.color == chess.WHITE else 1

        # Simulate a wedged move tracker: free-form piece restoration during
        # analysis leaves stale transients (illegal placements never clear
        # lifted_square). A complete 32-piece layout must still conclude analysis.
        mgr.physical_state = phys_start
        mgr.move_tracker.reset(phys_start)
        mgr.move_tracker.lifted_square = (4, 3)
        mgr.move_tracker.invalid_placement = (4, 1)
        mgr.move_tracker.set_in_flight_move(0, 0, 0, 1, "a1a2")

        # Validate board setup readiness
        setup_res = mgr.setup_validator.validate(mgr.physical_state)
        assert setup_res.is_setup_ready is True

        # Trigger transition logic (the same call the update loop makes)
        concluded = mgr._try_conclude_analysis_on_board_reset(setup_res)

        assert concluded is True
        assert mgr.game_status == "IDLE"
        assert mgr.prev_setup_ready is True
        assert mgr.active_animation is not None
        assert mgr.active_animation.name == "BOARD_READY"

        # Wedged tracker transients were discarded on conclusion
        assert mgr.move_tracker.lifted_square is None
        assert mgr.move_tracker.in_flight_move is None
        assert mgr.move_tracker.invalid_placement is None

        # Gesture engine is active and ready to evaluate in IDLE state
        mgr.gesture_engine.evaluate(mgr.physical_state, mgr.game_status)
        assert mgr.gesture_engine is not None

    asyncio.run(_test())


def test_analysis_board_reset_blocked_while_loading():
    """The reset-to-IDLE transition must not fire while Stockfish batch analysis is still loading."""
    async def _test():
        from unittest.mock import MagicMock

        mgr = BoardStateManager()
        mgr.strip = MagicMock()
        await mgr.start_analysis_mode(moves_uci=["e2e4", "e7e5"])
        mgr.step_analysis(2)
        mgr.analysis_is_loading = True

        start_board = chess.Board()
        phys_start = [[0] * 8 for _ in range(8)]
        for c in range(8):
            for r in range(8):
                p = start_board.piece_at(chess.square(c, r))
                if p:
                    phys_start[c][r] = -1 if p.color == chess.WHITE else 1
        mgr.physical_state = phys_start
        mgr.move_tracker.reset(phys_start)

        setup_res = mgr.setup_validator.validate(mgr.physical_state)
        assert mgr._try_conclude_analysis_on_board_reset(setup_res) is False
        assert mgr.game_status == "ANALYSIS"

    asyncio.run(_test())


def test_analysis_board_reset_requires_review_progress():
    """A full starting layout alone must not exit analysis before the user reviewed anything."""
    async def _test():
        from unittest.mock import MagicMock

        mgr = BoardStateManager()
        mgr.strip = MagicMock()
        await mgr.start_analysis_mode(moves_uci=["e2e4", "e7e5"])
        assert mgr.analysis_has_advanced is False

        start_board = chess.Board()
        phys_start = [[0] * 8 for _ in range(8)]
        for c in range(8):
            for r in range(8):
                p = start_board.piece_at(chess.square(c, r))
                if p:
                    phys_start[c][r] = -1 if p.color == chess.WHITE else 1
        mgr.physical_state = phys_start
        mgr.move_tracker.reset(phys_start)

        setup_res = mgr.setup_validator.validate(mgr.physical_state)
        assert mgr._try_conclude_analysis_on_board_reset(setup_res) is False
        assert mgr.game_status == "ANALYSIS"

    asyncio.run(_test())


def test_start_analysis_mode_resolution_hierarchy():
    """
    Verify BoardStateManager.start_analysis_mode() resolution hierarchy when moves_uci is None:
    1) state_manager.last_game_moves
    2) lichess_engine.last_game_moves
    3) lichess_engine.board.move_stack
    4) settings['last_game_moves']
    5) Italian Game fallback (12 plies)
    """
    async def _test():
        from unittest.mock import AsyncMock, patch

        import app.board_state as bs_module
        import chess
        from board_hardware import settings

        italian_default = [
            "e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5",
            "c2c3", "g8f6", "d2d4", "e5d4", "c3d4", "c5b4",
        ]

        with patch("app.coach_engine.coach_engine.batch_evaluate_game", new_callable=AsyncMock) as mock_batch:
            mock_batch.return_value = {
                "evaluations": [],
                "played_analyses": [],
                "white_accuracy": 95.0,
                "black_accuracy": 90.0,
                "counts": {},
                "blunders": [],
            }

            # Scenario A: Explicit moves_uci provided
            mgr = BoardStateManager()
            await mgr.start_analysis_mode(moves_uci=["d2d4", "d7d5"])
            assert mgr.analysis_game_moves == ["d2d4", "d7d5"]

            # Scenario B: Resolved from mgr.last_game_moves
            mgr = BoardStateManager()
            mgr.last_game_moves = ["c2c4", "e7e5"]
            await mgr.start_analysis_mode()
            assert mgr.analysis_game_moves == ["c2c4", "e7e5"]

            # Scenario C: Resolved from lichess_engine.last_game_moves
            mgr = BoardStateManager()
            mgr.last_game_moves = None
            bs_module.lichess_engine.last_game_moves = ["e2e4", "c7c5", "g1f3"]
            await mgr.start_analysis_mode()
            assert mgr.analysis_game_moves == ["e2e4", "c7c5", "g1f3"]
            bs_module.lichess_engine.last_game_moves = []

            # Scenario D: Resolved from lichess_engine.board.move_stack
            mgr = BoardStateManager()
            mgr.last_game_moves = None
            bs_module.lichess_engine.last_game_moves = []
            test_board = chess.Board()
            test_board.push_uci("g1f3")
            test_board.push_uci("d7d5")
            bs_module.lichess_engine.board = test_board
            await mgr.start_analysis_mode()
            assert mgr.analysis_game_moves == ["g1f3", "d7d5"]
            bs_module.lichess_engine.board = chess.Board()

            # Scenario E: Resolved from settings['last_game_moves']
            mgr = BoardStateManager()
            mgr.last_game_moves = None
            bs_module.lichess_engine.last_game_moves = []
            bs_module.lichess_engine.board = chess.Board()
            settings["last_game_moves"] = ["e2e4", "e7e6", "d2d4", "d7d5"]
            await mgr.start_analysis_mode()
            assert mgr.analysis_game_moves == ["e2e4", "e7e6", "d2d4", "d7d5"]
            settings["last_game_moves"] = None

            # Scenario F: Total fallback to Italian Game
            mgr = BoardStateManager()
            mgr.last_game_moves = None
            bs_module.lichess_engine.last_game_moves = []
            bs_module.lichess_engine.board = chess.Board()
            settings["last_game_moves"] = None
            await mgr.start_analysis_mode()
            assert mgr.analysis_game_moves == italian_default

    asyncio.run(_test())


def test_update_leds_analysis_loading_vs_review_transition():
    """
    Verify _update_leds behavior in ANALYSIS state:
    1. analysis_is_loading == True: Renders render_analysis_computing animation.
    2. analysis_is_loading == False: Transitions to review mode move rendering & eval bar.
    """
    from unittest.mock import MagicMock, patch

    from app.led_helpers import COLOR_INT_MINT_EMERALD

    mgr = BoardStateManager()
    mgr.strip = MagicMock()
    mgr.game_status = "ANALYSIS"
    mgr.analysis_submode = "review"
    mgr.analysis_game_moves = ["e2e4", "e7e5"]
    mgr.analysis_current_ply = 0
    mgr.analysis_played_analyses = [
        {"ply": 0, "delta_cp": 5, "classification": "best", "best_move": "e2e4"}
    ]
    mgr.analysis_evaluations = [{"win_chance": 50.0, "best_move": "e2e4"}]

    # Phase 1: Loading == True -> Calls render_analysis_computing
    mgr.analysis_is_loading = True
    with patch("app.board_state.render_analysis_computing") as mock_computing:
        mgr._update_leds()
        mock_computing.assert_called_once()
        assert mgr.strip.show.called

    # Phase 2: Loading == False -> Renders Best Move review trace in Mint Emerald
    mgr.analysis_is_loading = False
    mgr.strip.reset_mock()
    mgr._update_leds()

    assert mgr.strip.setPixelColor.called
    assert mgr.strip.show.called
    colors_called = [call[0][1] for call in mgr.strip.setPixelColor.call_args_list]
    assert COLOR_INT_MINT_EMERALD in colors_called







def test_analysis_return_home_guide_renders_on_last_branch_move():
    """While branching, a gold halo marks the last branch move's arrival square
    and a dim gold dot its origin; popping the branch moves the guide back."""
    from unittest.mock import MagicMock

    from app.led_animations import scale_color
    from app.led_helpers import COLOR_INT_RETURN_HOME, get_led_indices
    from board_hardware import settings

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
        mgr.analysis_branch_moves = ["c7c5", "c5c4"]

        def _gold_values(mgr_obj):
            mgr_obj.strip.reset_mock()
            mgr_obj._update_leds()
            lit = {}
            for c in mgr_obj.strip.setPixelColor.call_args_list:
                if c.args[1] != 0:
                    lit[c.args[0]] = c.args[1]
            return lit

        # Guide targets the LAST branch move c5c4: origin c5 (file 2, rank 4), to c4 (file 2, rank 3)
        lit = _gold_values(mgr)
        to_indices = get_led_indices(3, 2)
        origin_indices = get_led_indices(4, 2)
        for idx in to_indices:
            assert idx in lit and scale_color(COLOR_INT_RETURN_HOME, 0.55) <= lit[idx] <= COLOR_INT_RETURN_HOME
        for idx in origin_indices:
            assert lit.get(idx) == scale_color(COLOR_INT_RETURN_HOME, 0.35)

        # Un-play one branch move: guide steps back to c7c5. Its origin c7 IS the
        # anchor square, so the dot is suppressed and the violet anchor stays visible.
        mgr.analysis_branch_moves = ["c7c5"]
        lit = _gold_values(mgr)
        for idx in get_led_indices(4, 2):
            assert idx in lit
        assert lit.get(origin_indices[0]) != scale_color(COLOR_INT_RETURN_HOME, 0.35)

        # Branch fully cleared: no return-home gold anywhere
        mgr.analysis_branch_moves = []
        lit = _gold_values(mgr)
        assert COLOR_INT_RETURN_HOME not in set(lit.values())
    finally:
        settings["night_mode"] = orig_nm


def test_navigate_analysis_back_pops_branch_one_move_at_a_time():
    async def _test():
        mgr = BoardStateManager()
        moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]
        await mgr.start_analysis_mode(moves_uci=moves)
        mgr.step_analysis(5)

        # Diverge two moves from the web (black to move first)
        mgr.handle_analysis_move("g8f6", source="web")
        mgr.handle_analysis_move("g2g3", source="web")
        assert mgr.analysis_branch_moves == ["g8f6", "g2g3"]
        fen_branched = mgr.analysis_active_board.fen()

        # Back #1: pops only the last branch move (g2g3)
        res = mgr.navigate_analysis("back")
        assert res["action"] == "branch_back"
        assert res["on_mainline"] is False
        assert res["branch_depth"] == 1
        assert mgr.analysis_branch_moves == ["g8f6"]
        b = chess.Board()
        for m in moves + ["g8f6"]:
            b.push_uci(m)
        assert mgr.analysis_active_board.fen() == b.fen()

        # Back #2: last branch move popped -> back on mainline at anchor ply
        res = mgr.navigate_analysis("back")
        assert res["action"] == "branch_back"
        assert res["on_mainline"] is True
        assert mgr.analysis_anchor_coord is None
        assert mgr.analysis_current_ply == 5
        b = chess.Board()
        for m in moves:
            b.push_uci(m)
        assert mgr.analysis_active_board.fen() == b.fen()

        # Back #3: plain mainline step back (Bc4 un-played)
        res = mgr.navigate_analysis("back")
        assert res["action"] == "step"
        assert res["on_mainline"] is True
        assert mgr.analysis_current_ply == 4

    asyncio.run(_test())


def test_navigate_analysis_forward_noop_while_branched():
    async def _test():
        mgr = BoardStateManager()
        await mgr.start_analysis_mode(moves_uci=["e2e4", "e7e5"])
        mgr.step_analysis(1)
        mgr.handle_analysis_move("g8f6", source="web")

        res = mgr.navigate_analysis("forward")
        assert res["action"] == "noop"
        assert len(mgr.analysis_branch_moves) == 1

    asyncio.run(_test())


def test_navigate_analysis_start_end_exit_branch():
    async def _test():
        mgr = BoardStateManager()
        moves = ["e2e4", "e7e5", "g1f3"]
        await mgr.start_analysis_mode(moves_uci=moves)
        mgr.step_analysis(3)
        mgr.handle_analysis_move("b8c6", source="web")

        res = mgr.navigate_analysis("end")
        assert res["on_mainline"] is True
        assert mgr.analysis_current_ply == 3
        assert mgr.analysis_branch_moves == []

        mgr.handle_analysis_move("g8f6", source="web")  # branch again at end
        res = mgr.navigate_analysis("start")
        assert res["on_mainline"] is True
        assert mgr.analysis_current_ply == 0
        assert mgr.analysis_active_board.fen().split()[0] == chess.STARTING_BOARD_FEN

    asyncio.run(_test())


def test_web_moves_are_board_passive():
    async def _test():
        mgr = BoardStateManager()
        await mgr.start_analysis_mode(moves_uci=["e2e4", "e7e5"])

        # No arrival flash may be armed by web moves
        before = mgr.arrival_flash
        res = mgr.handle_analysis_move("e2e4", source="web")
        assert res["action"] == "advance"
        assert mgr.arrival_flash is before

        res = mgr.handle_analysis_move("e7e5", source="web")
        assert res["action"] == "advance"

        # White to move: d2d4 is legal but off the stored line -> branch
        res = mgr.handle_analysis_move("d2d4", source="web")
        assert res["action"] == "branch"
        assert mgr.arrival_flash is before

    asyncio.run(_test())


def test_web_move_accepts_san_input():
    async def _test():
        # Mainline whose final ply is white castling (stored as UCI e1g1)
        moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "e1g1"]
        mgr = BoardStateManager()
        await mgr.start_analysis_mode(moves_uci=moves)
        mgr.step_analysis(2)  # position after 1.e4 e5, white to move

        # SAN knight move advances the mainline (expected ply is g1f3)
        res = mgr.handle_analysis_move("Nf3", source="web")
        assert res["action"] == "advance"
        assert mgr.analysis_current_ply == 3

        # SAN alternative creates a branch (Nh6 is not the stored b8c6 line)
        res = mgr.handle_analysis_move("Nh6", source="web")
        assert res["action"] == "branch"

        # Castling SAN advances the mainline when it matches the stored UCI move
        mgr.navigate_analysis("back")  # un-play Nh6, back on mainline
        mgr.step_analysis(6)  # before white castles
        res = mgr.handle_analysis_move("O-O", source="web")
        assert res["action"] == "advance"
        assert mgr.analysis_current_ply == 7

    asyncio.run(_test())


def test_web_only_session_ignores_physical_board_reset_gate():
    async def _test():
        mgr = BoardStateManager()
        # Simulate the physical board sitting at the full starting position
        for c in range(8):
            mgr.physical_state[c][1] = 1
            mgr.physical_state[c][6] = 1
            mgr.physical_state[c][0] = 1
            mgr.physical_state[c][7] = 1

        await mgr.start_analysis_mode(moves_uci=["e2e4", "e7e5"], source="web")
        assert mgr.analysis_web_only is True

        # Advance a ply (web navigation) -> has_advanced becomes True
        res = await mgr.start_analysis_mode(moves_uci=["e2e4", "e7e5"], source="web")
        assert res["active"] is True
        mgr.handle_analysis_move("e2e4", source="web")
        assert mgr.analysis_has_advanced is True

        # The board-reset gate must NOT conclude a web-only session
        setup_res = SimpleNamespace(is_setup_ready=True)
        assert mgr._try_conclude_analysis_on_board_reset(setup_res) is False
        assert mgr.game_status == "ANALYSIS"

        # Board-sourced sessions still conclude as before
        await mgr.start_analysis_mode(moves_uci=["e2e4", "e7e5"], source="board")
        assert mgr.analysis_web_only is False
        mgr.step_analysis(1)
        assert mgr._try_conclude_analysis_on_board_reset(setup_res) is True
        assert mgr.game_status == "IDLE"

    asyncio.run(_test())


def test_stop_analysis_clears_web_only_flag():
    async def _test():
        mgr = BoardStateManager()
        await mgr.start_analysis_mode(moves_uci=["e2e4"], source="web")
        assert mgr.analysis_web_only is True
        mgr.stop_analysis_mode()
        assert mgr.analysis_web_only is False

    asyncio.run(_test())


def test_analysis_payload_exposes_legal_moves_and_check():
    async def _test():
        mgr = BoardStateManager()
        await mgr.start_analysis_mode(moves_uci=["e2e4", "e7e5", "g1f3"])
        mgr.step_analysis(0)  # start position, white to move

        payload = mgr.get_analysis_payload()
        assert "e2e4" in payload["legal_moves"]
        assert "g1f3" in payload["legal_moves"]
        assert "e7e5" not in payload["legal_moves"]  # black move while white to move
        assert payload["in_check"] is False

        mgr.step_analysis(2)  # after 1.e4 e5
        assert "g1f3" in mgr.get_analysis_payload()["legal_moves"]

    asyncio.run(_test())


def test_analysis_payload_reports_check():
    async def _test():
        mgr = BoardStateManager()
        # Fool's mate setup: after these moves black king is NOT in check yet,
        # so step into a position where the side to move is checked.
        await mgr.start_analysis_mode(
            moves_uci=["f2f3", "e7e5", "g2g4", "d8h4"]
        )
        mgr.step_analysis(3)  # after 1.f3 e5 2.g4 -> black to move, not in check
        assert mgr.get_analysis_payload()["in_check"] is False

        mgr.step_analysis(4)  # after Qh4# white to move and in check
        payload = mgr.get_analysis_payload()
        assert payload["in_check"] is True

    asyncio.run(_test())


def test_branch_position_serves_live_engine_evaluation(monkeypatch):
    async def _test():
        import app.board_state as board_state_module
        from app.coach_engine import PositionEvaluation

        mgr = BoardStateManager()
        await mgr.start_analysis_mode(moves_uci=["e2e4", "e7e5"])
        mgr.step_analysis(2)

        # Diverge into a sandbox; no engine data yet
        res = mgr.handle_analysis_move("b1c3", source="web")
        assert res["action"] == "branch"
        assert mgr.analysis_branch_moves == ["b1c3"]

        # Stockfish caches an evaluation of the branch position -> payload serves it
        branch_fen = mgr.analysis_active_board.fen()
        cached = PositionEvaluation(
            fen=branch_fen, score_cp=40, mate=None, win_chance=57.0,
            best_move="g1f3", top_moves=[],
        )
        monkeypatch.setattr(
            board_state_module.coach_engine,
            "get_cached_evaluation",
            lambda fen: cached if " ".join(fen.split()[:4]) in branch_fen else None,
        )
        payload = mgr.get_analysis_payload()
        assert payload["is_branching"] is True
        assert payload["current_eval"] is not None
        assert payload["current_eval"]["best_move"] == "g1f3"
        assert payload["current_eval"]["score_cp"] == 40

    asyncio.run(_test())


def test_branch_step_back_reengages_engine(monkeypatch):
    async def _test():
        import app.board_state as board_state_module

        calls = {"n": 0}
        real_req = board_state_module.coach_engine.request_analysis
        monkeypatch.setattr(
            board_state_module.coach_engine,
            "request_analysis",
            lambda board: calls.__setitem__("n", calls["n"] + 1),
        )

        mgr = BoardStateManager()
        await mgr.start_analysis_mode(moves_uci=["e2e4", "e7e5"])
        mgr.step_analysis(2)
        mgr.handle_analysis_move("f1c4", source="web")
        mgr.handle_analysis_move("g1f3", source="web")

        # Un-play one move: still branched -> engine re-engaged on the line
        calls["n"] = 0
        res = mgr.navigate_analysis("back")
        assert res["action"] == "branch_back"
        assert res["on_mainline"] is False
        assert calls["n"] == 1

        # Un-play the final move: back on mainline, no extra engine dispatch needed
        calls["n"] = 0
        res = mgr.navigate_analysis("back")
        assert res["on_mainline"] is True
        assert calls["n"] == 0

    asyncio.run(_test())
