import asyncio
import os
import sys
from types import SimpleNamespace

import chess

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.board_state as board_state_module
from app.board_state import BoardStateManager
from app.gesture_engine import (
    CenterRoyalGateGesture,
    MemoryReplayGateGesture,
)


def _make_grid():
    grid = [[0] * 8 for _ in range(8)]
    for c in range(8):
        for r in (0, 1, 6, 7):
            grid[c][r] = 1
    return grid


def test_learn_advance_and_reset_gate_enters_recall():
    async def _test():
        mgr = BoardStateManager()
        mgr.start_gm_game("morphy_opera_1858")

        # Learn two plies
        moves = mgr.analysis_game_moves
        assert mgr.handle_replay_move(moves[0])["action"] == "advance"
        assert mgr.handle_replay_move(moves[1])["action"] == "advance"
        assert mgr.replay_learned_ply == 2

        # Simulate full physical board reset to start position (setup ready)
        setup_res = SimpleNamespace(is_setup_ready=True)
        assert mgr._try_conclude_analysis_on_board_reset(setup_res) is True

        # Recall phase entered, scoped exactly to the learned plies
        assert mgr.analysis_submode == "replay_recall"
        assert mgr.replay_learned_ply == 2
        assert mgr.analysis_current_ply == 0
        assert mgr.analysis_active_board.fen().split()[0] == chess.STARTING_BOARD_FEN
        assert mgr.replay_complete is False
        # Entering recall fires the visible "Memory Arm" sweep cue
        assert mgr.active_animation is not None
        assert mgr.active_animation.name == "RECALL_START"

    asyncio.run(_test())


def test_learn_zero_plies_keeps_waiting_on_reset():
    async def _test():
        mgr = BoardStateManager()
        mgr.start_gm_game("morphy_opera_1858")

        setup_res = SimpleNamespace(is_setup_ready=True)
        # Nothing learned yet: gate must neither trigger recall nor exit to IDLE
        assert mgr._try_conclude_analysis_on_board_reset(setup_res) is False
        assert mgr.game_status == "ANALYSIS"
        assert mgr.analysis_submode == "replay_learn"

    asyncio.run(_test())


def test_recall_match_mismatch_and_reveal_flow():
    async def _test():
        mgr = BoardStateManager()
        mgr.start_gm_game("morphy_opera_1858")
        moves = mgr.analysis_game_moves

        # Learn three plies then enter recall via the reset gate
        for uci in moves[:3]:
            assert mgr.handle_replay_move(uci)["action"] == "advance"
        setup_res = SimpleNamespace(is_setup_ready=True)
        assert mgr._try_conclude_analysis_on_board_reset(setup_res) is True

        # Ply 0 correct from memory
        res1 = mgr.handle_replay_move(moves[0])
        assert res1["action"] == "correct"
        assert mgr.analysis_current_ply == 1
        assert mgr.replay_results[-1] == {"ply": 0, "correct": True}
        assert mgr.replay_reveal_uci is None

        # Ply 1 wrong but legal move -> mistake recorded, reveal set, no advance
        expected = moves[1]
        legal_ucis = [m.uci() for m in mgr.analysis_active_board.legal_moves]
        wrong = next(u for u in legal_ucis if u != expected)
        res2 = mgr.handle_replay_move(wrong)
        assert res2["action"] == "incorrect"
        assert res2["reveal_uci"] == expected
        assert mgr.analysis_current_ply == 1
        assert mgr.replay_results[-1] == {"ply": 1, "correct": False}
        assert mgr.replay_mistakes == 1
        assert mgr.analysis_anchor_coord is not None

        # Simulate physical un-play of the wrong piece (restoration snap-back)
        mgr.step_analysis(mgr.analysis_current_ply)
        assert mgr.analysis_anchor_coord is None

        # Follow the revealed correction: advances free of charge, reveal cleared
        res3 = mgr.handle_replay_move(expected)
        assert res3["action"] == "revealed_advance"
        assert mgr.analysis_current_ply == 2
        assert mgr.replay_reveal_uci is None
        assert mgr.replay_mistakes == 1
        # No extra result entry was recorded for the corrected ply
        assert len(mgr.replay_results) == 2

    asyncio.run(_test())


def test_recall_completion_triggers_celebration_and_exit_gate():
    async def _test():
        mgr = BoardStateManager()

        # Direct recall on a short custom game (gesture path with explicit moves)
        payload = await mgr.start_replay_recall(moves_uci=["e2e4", "e7e5"])
        assert payload["submode"] == "replay_recall"
        assert payload["replay"]["phase"] == "recall"
        assert payload["replay"]["learned_ply"] == 2

        assert mgr.handle_replay_move("e2e4")["action"] == "correct"
        assert mgr.replay_complete is False

        res = mgr.handle_replay_move("e7e5")
        assert res["action"] == "correct"
        assert res["complete"] is True
        assert mgr.replay_complete is True
        assert mgr.active_animation is not None
        assert mgr.active_animation.name == "RECALL_COMPLETE"

        # Moves after completion are ignored gracefully
        post = mgr.handle_replay_move("g1f3")
        assert post["action"] == "complete"

        # Restoring the starting position concludes the session to IDLE
        setup_res = SimpleNamespace(is_setup_ready=True)
        assert mgr._try_conclude_analysis_on_board_reset(setup_res) is True
        assert mgr.game_status == "IDLE"
        assert mgr.replay_learned_ply == 0
        assert mgr.analysis_submode == "review"

    asyncio.run(_test())


def test_direct_recall_no_previous_game_stays_idle(monkeypatch):
    async def _test():
        monkeypatch.setattr(
            board_state_module, "settings", {"last_game_moves": [], "night_mode": False}
        )
        monkeypatch.setattr(
            board_state_module.lichess_engine, "last_game_moves", None, raising=False
        )
        monkeypatch.setattr(board_state_module.lichess_engine, "board", None, raising=False)

        mgr = BoardStateManager()
        mgr.last_game_moves = []

        res = await mgr.start_replay_recall()
        assert "error" in res
        assert mgr.game_status == "IDLE"
        assert mgr.analysis_submode == "review"

    asyncio.run(_test())


def test_learn_finished_game_ignores_extra_moves():
    async def _test():
        mgr = BoardStateManager()

        # Inject a short custom learn session
        mgr.game_status = "ANALYSIS"
        mgr.analysis_submode = "replay_learn"
        mgr.analysis_game_moves = ["e2e4", "e7e5"]
        mgr.analysis_current_ply = 0
        mgr.analysis_active_board = chess.Board()
        mgr._reset_replay_session()

        # Play through the entire learn line
        assert mgr.handle_replay_move("e2e4")["action"] == "advance"
        assert mgr.handle_replay_move("e7e5")["action"] == "advance"
        assert mgr.replay_learned_ply == 2

        # Any extra legal move after the game ends must NOT diverge or wedge
        res = mgr.handle_replay_move("g1f3")
        assert res["action"] == "learn_complete"
        assert mgr.analysis_anchor_coord is None
        assert mgr.analysis_branch_moves == []
        assert mgr.analysis_current_ply == 2

    asyncio.run(_test())


def test_memory_replay_gesture_flow_and_disambiguation():
    class MockManager:
        def __init__(self):
            self.flashes = []
            self.recall_started = False
            self.analysis_started = False

        def trigger_arrival_flash(self, c, r, duration=0.6, is_capture=False, extra_squares=None):
            self.flashes.append(((c, r), extra_squares))

        async def start_replay_recall(self):
            self.recall_started = True

        async def start_analysis_mode(self, moves_uci=None, game_id=None):
            self.analysis_started = True

    mock_mgr = MockManager()
    gesture = MemoryReplayGateGesture(state_manager=mock_mgr)
    analysis_gesture = CenterRoyalGateGesture(state_manager=mock_mgr)

    assert gesture.starter_coord == (3, 1)  # d2 starter glow
    assert gesture.name == "memory_replay"

    grid = _make_grid()
    now = 1000.0

    # Lift d2 alone: memory gesture arms...
    grid[3][1] = 0
    assert gesture.evaluate(grid, now) is False
    assert gesture.step == 1
    assert "Lift e2" in (gesture.hint or "")

    # ...while the analysis gesture stays idle (it requires e2 lifted alone first).
    assert analysis_gesture.evaluate(grid, now) is False
    assert analysis_gesture.step == 0

    # Lift e2 while d2 lifted -> step 2
    grid[4][1] = 0
    assert gesture.evaluate(grid, now + 0.5) is False
    assert gesture.step == 2
    assert "Replace d2 and e2" in (gesture.hint or "")

    # Replace both -> completion flash on d2 primary
    grid[3][1] = 1
    grid[4][1] = 1
    assert gesture.evaluate(grid, now + 1.0) is True
    gesture.execute_completion()
    assert len(mock_mgr.flashes) == 1
    assert mock_mgr.flashes[0][0] == (3, 1)
    assert mock_mgr.flashes[0][1] == [(4, 1)]

    # The scheduled recall coroutine runs on a live loop (smoke-test dispatch)
    asyncio.run(asyncio.sleep(0))


def test_recall_completion_enters_setup_validation_led_state():
    """Verify that after replay completion and celebration animation, the board displays setup validation LEDs."""
    from unittest.mock import MagicMock
    from app.led_helpers import COLOR_INT_SETUP_MISPLACED, COLOR_INT_SETUP_MISSING

    async def _test():
        mgr = BoardStateManager()
        mgr.strip = MagicMock()
        mgr.virtual_only = False

        # Start recall session on 2 moves
        await mgr.start_replay_recall(moves_uci=["e2e4", "e7e5"])
        mgr.handle_replay_move("e2e4")
        mgr.handle_replay_move("e7e5")
        assert mgr.replay_complete is True
        assert mgr.active_animation is not None
        assert mgr.active_animation.name == "RECALL_COMPLETE"

        # While animation is active, active_animation renders (Layer 0)
        mgr._update_leds()
        assert mgr.strip.show.called

        # Expire the animation
        mgr.active_animation = None

        # Simulate physical board with e4 (4, 3) and e5 (4, 4) occupied (misplaced)
        # and starting squares e2 (4, 1) and e7 (4, 6) missing
        grid = _make_grid()
        grid[4][1] = 0   # e2 missing
        grid[4][3] = -1  # e4 white pawn misplaced
        grid[4][6] = 0   # e7 missing
        grid[4][4] = 1   # e5 black pawn misplaced
        mgr.physical_state = grid

        mgr.strip.setPixelColor.reset_mock()
        mgr._update_leds()

        call_args = [call[0] for call in mgr.strip.setPixelColor.call_args_list]
        colors_called = [arg[1] for arg in call_args]

        # White starting squares missing should be lit in COLOR_INT_SETUP_MISSING
        assert COLOR_INT_SETUP_MISSING in colors_called
        # Misplaced pieces on e4/e5 should be lit in COLOR_INT_SETUP_MISPLACED
        assert COLOR_INT_SETUP_MISPLACED in colors_called

        # Web-only analysis must suppress setup LEDs
        mgr.analysis_web_only = True
        mgr.strip.setPixelColor.reset_mock()
        mgr._update_leds()
        web_call_args = [call[0] for call in mgr.strip.setPixelColor.call_args_list]
        web_colors = [arg[1] for arg in web_call_args]
        assert COLOR_INT_SETUP_MISSING not in web_colors
        assert COLOR_INT_SETUP_MISPLACED not in web_colors

    asyncio.run(_test())

