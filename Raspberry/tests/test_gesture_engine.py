"""
tests/test_gesture_engine.py

Comprehensive test suite for the Physical Board Gesture Engine, Replay Last Game selection menu,
LED overlay colors, cancellation rules, and REST restart endpoints.
"""

import time
from unittest.mock import MagicMock

from app.gesture_engine import (
    PhysicalGestureEngine,
    RestartPreviousGameGesture,
    ToggleNightModeGesture,
)


def create_starting_board():
    """Generates standard 8x8 chess physical starting grid (-1 White, +1 Black, 0 Empty)."""
    grid = [[0] * 8 for _ in range(8)]
    for c in range(8):
        grid[c][0] = -1
        grid[c][1] = -1
        grid[c][6] = 1
        grid[c][7] = 1
    return grid


class TestRestartPreviousGameGesture:
    def test_initial_state(self):
        gesture = RestartPreviousGameGesture()
        assert gesture.name == "restart_previous_game"
        assert not gesture.is_active
        assert gesture.step == 0
        assert gesture.hint is None
        assert gesture.get_led_overlay(time.time()) == {}

    def test_menu_opens_on_h2_lift(self):
        gesture = RestartPreviousGameGesture()
        board = create_starting_board()
        board[7][1] = 0  # Lift h2

        completed = gesture.evaluate(board, now=100.0)
        assert not completed
        assert gesture.is_active
        assert gesture.step == 1
        assert "Rook toggles AI/Human" in (gesture.hint or "")
        overlay = gesture.get_led_overlay(now=100.0)
        # Menu lights h2 + all four option squares
        assert (7, 1) in overlay  # h2 anchor
        assert (4, 0) in overlay  # e1 King
        assert (5, 0) in overlay  # f1 Bishop
        assert (6, 0) in overlay  # g1 Knight
        assert (7, 0) in overlay  # h1 Rook

    def test_menu_defaults_from_last_params(self):
        from board_hardware import settings

        settings["last_game_params"] = {"time_control": "3+2", "opponent": "ai"}
        gesture = RestartPreviousGameGesture()
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)
        assert gesture.selected_tc == "3+2"
        assert gesture.opponent_mode == "ai"

    def test_king_lift_selects_15_plus_10(self):
        mock_mgr = MagicMock()
        gesture = RestartPreviousGameGesture(state_manager=mock_mgr)
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)

        # Lift king e1
        board[4][0] = 0
        completed = gesture.evaluate(board, now=101.0)
        assert not completed
        assert gesture._held_option == (4, 0)

        # Place king back -> selection confirmed
        board[4][0] = -1
        completed = gesture.evaluate(board, now=102.0)
        assert not completed
        assert gesture.is_active  # menu stays open
        assert gesture.selected_tc == "15+10"
        mock_mgr.trigger_arrival_flash.assert_called_once_with(4, 0, duration=0.6)

    def test_bishop_lift_selects_10_plus_0(self):
        gesture = RestartPreviousGameGesture()
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)

        board[5][0] = 0
        gesture.evaluate(board, now=101.0)
        board[5][0] = -1
        gesture.evaluate(board, now=102.0)
        assert gesture.selected_tc == "10+0"

    def test_knight_lift_selects_3_plus_2(self):
        gesture = RestartPreviousGameGesture()
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)

        board[6][0] = 0
        gesture.evaluate(board, now=101.0)
        board[6][0] = -1
        gesture.evaluate(board, now=102.0)
        assert gesture.selected_tc == "3+2"

    def test_rook_lift_toggles_ai_human_with_visual_feedback(self):
        gesture = RestartPreviousGameGesture()
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)
        mode_before = gesture.opponent_mode

        # Lift rook h1 -> toggle happens instantly at lift time
        board[7][0] = 0
        gesture.evaluate(board, now=101.0)
        assert gesture.opponent_mode != mode_before
        # Overlay color reflects the newly selected mode while held
        overlay_held = gesture.get_led_overlay(now=101.0)
        expected_color = (
            gesture.COLOR_INT_AI_MODE if gesture.opponent_mode == "ai" else gesture.COLOR_INT_HUMAN_MODE
        )
        assert overlay_held[(7, 0)] == expected_color

        # Place rook back -> confirmed, mode retained
        board[7][0] = -1
        gesture.evaluate(board, now=102.0)
        assert gesture.is_active
        assert gesture.opponent_mode != mode_before

        # Lifting again toggles back
        board[7][0] = 0
        gesture.evaluate(board, now=103.0)
        assert gesture.opponent_mode == mode_before

    def test_selection_refreshes_inactivity_timer(self):
        gesture = RestartPreviousGameGesture(timeout=30.0)
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)

        board[4][0] = 0
        gesture.evaluate(board, now=125.0)  # within initial window
        board[4][0] = -1
        gesture.evaluate(board, now=129.0)  # confirmation refreshes timer

        # 20s later (total far beyond initial 30s from open) menu must still be alive
        gesture.evaluate(board, now=149.0)
        assert gesture.is_active
        assert gesture.step == 1

    def test_completion_on_h2_replace_dispatches_seek(self):
        import asyncio
        from unittest.mock import AsyncMock, patch

        async def _test():
            mock_mgr = MagicMock()
            gesture = RestartPreviousGameGesture(state_manager=mock_mgr)
            board = create_starting_board()
            board[7][1] = 0
            gesture.evaluate(board, now=100.0)

            # Pick knight -> 3+2, keep AI mode
            board[6][0] = 0
            gesture.evaluate(board, now=101.0)
            board[6][0] = -1
            gesture.evaluate(board, now=102.0)

            # Knight placement already flashed once; isolate the completion flash
            mock_mgr.trigger_arrival_flash.reset_mock()
            board[7][1] = -1
            completed = gesture.evaluate(board, now=103.0)
            assert completed
            assert gesture.step == 0
            assert not gesture.is_active

            # Completion flashes h2 + knight square
            mock_mgr.trigger_arrival_flash.assert_called_once_with(7, 1, duration=0.6, extra_squares=[(6, 0)])

            with patch(
                "app.lichess_engine.lichess_engine.seek", new_callable=AsyncMock
            ) as mock_seek:
                gesture.execute_completion()
                await asyncio.sleep(0.01)
                mock_seek.assert_awaited_once()
                kwargs = mock_seek.await_args.kwargs
                assert kwargs["time_control"] == "3+2"
                assert kwargs["opponent"] == gesture.opponent_mode

        asyncio.run(_test())

    def test_cancel_when_h2_replaced_while_option_in_hand(self):
        gesture = RestartPreviousGameGesture()
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)

        board[4][0] = 0
        gesture.evaluate(board, now=101.0)

        # Drop h2 while still holding the king -> cancelled + holdoff
        board[7][1] = -1
        completed = gesture.evaluate(board, now=102.0)
        assert not completed
        assert not gesture.is_active

        # King still in hand: holdoff persists
        gesture.evaluate(board, now=103.0)
        assert not gesture.is_active

        # Everything replaced: holdoff clears and gesture can re-arm again
        board[4][0] = -1
        gesture.evaluate(board, now=104.0)
        assert not gesture.is_active
        board[7][1] = 0
        gesture.evaluate(board, now=105.0)
        assert gesture.is_active

    def test_extra_piece_lift_cancels_and_requires_reset(self):
        gesture = RestartPreviousGameGesture()
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)
        assert gesture.step == 1

        # Bump a2 pawn (unrelated starting piece)
        board[0][1] = 0
        gesture.evaluate(board, now=101.0)
        assert gesture.step == 0
        assert not gesture.is_active

        # While any lift remains (a2), re-arm is blocked
        gesture.evaluate(board, now=102.0)
        assert not gesture.is_active

        # Replace a2 (and h2 which was still held) -> holdoff cleared
        board[0][1] = -1
        board[7][1] = -1
        gesture.evaluate(board, now=103.0)
        assert not gesture.is_active
        board[7][1] = 0
        gesture.evaluate(board, now=104.0)
        assert gesture.is_active

    def test_timeout_cancels_after_inactivity(self):
        gesture = RestartPreviousGameGesture(timeout=30.0)
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)
        assert gesture.step == 1

        gesture.evaluate(board, now=131.0)
        assert gesture.step == 0
        assert not gesture.is_active

        # Re-arming blocked until h2 is replaced
        gesture.evaluate(board, now=132.0)
        assert not gesture.is_active
        board[7][1] = -1
        gesture.evaluate(board, now=133.0)
        board[7][1] = 0
        gesture.evaluate(board, now=134.0)
        assert gesture.is_active

    def test_to_dict_exposes_selection(self):
        gesture = RestartPreviousGameGesture()
        board = create_starting_board()
        board[7][1] = 0
        gesture.evaluate(board, now=100.0)

        data = gesture.to_dict(now=100.0)
        assert data["selection"]["time_control"] == gesture.selected_tc
        assert data["selection"]["opponent"] == gesture.opponent_mode


class TestPhysicalGestureEngine:
    def test_engine_lifecycle(self):
        mock_mgr = MagicMock()
        engine = PhysicalGestureEngine(state_manager=mock_mgr)
        assert not engine.is_active
        assert len(engine.gestures) >= 1

        board = create_starting_board()
        board[7][1] = 0
        engine.evaluate(board, game_status="IDLE", now=100.0)
        assert engine.is_active
        assert engine.active_gesture is not None
        assert engine.active_gesture.name == "restart_previous_game"

        # Playing game status resets all gestures
        engine.evaluate(board, game_status="PLAYING", now=101.0)
        assert not engine.is_active

    def test_state_payload(self):
        engine = PhysicalGestureEngine()
        payload = engine.get_state_payload()
        assert "is_active" in payload
        assert "gestures" in payload
        assert isinstance(payload["gestures"], list)


class TestToggleNightModeGesture:
    def test_initial_state(self):
        gesture = ToggleNightModeGesture()
        assert gesture.name == "toggle_night_mode"
        assert not gesture.is_active
        assert gesture.step == 0
        assert gesture.hint is None
        assert gesture.get_led_overlay(time.time()) == {}

    def test_step1_trigger_on_a2_lift(self):
        gesture = ToggleNightModeGesture()
        board = create_starting_board()
        board[0][1] = 0  # Lift a2

        completed = gesture.evaluate(board, now=100.0)
        assert not completed
        assert gesture.is_active
        assert gesture.step == 1
        assert "Lift a1" in (gesture.hint or "")
        overlay = gesture.get_led_overlay(now=100.0)
        assert (0, 1) in overlay  # a2
        assert (0, 0) in overlay  # a1

    def test_step1_visual_feedback_colors(self):
        from board_hardware import settings
        gesture = ToggleNightModeGesture()
        board = create_starting_board()
        board[0][1] = 0

        # When board is in Day Mode (night_mode=False)
        settings["night_mode"] = False
        gesture.evaluate(board, now=100.0)
        overlay_day = gesture.get_led_overlay(now=100.0)
        assert (0, 1) in overlay_day
        assert (0, 0) in overlay_day

        # When board is in Night Mode (night_mode=True)
        settings["night_mode"] = True
        overlay_night = gesture.get_led_overlay(now=100.0)
        assert (0, 1) in overlay_night
        assert (0, 0) in overlay_night
        # Day and Night indicator colors must be distinct
        assert overlay_day[(0, 1)] != overlay_night[(0, 1)]

    def test_step1_premature_replace_cancels(self):
        gesture = ToggleNightModeGesture()
        board = create_starting_board()
        board[0][1] = 0
        gesture.evaluate(board, now=100.0)
        assert gesture.step == 1

        # Replace a2 without lifting a1
        board[0][1] = -1
        completed = gesture.evaluate(board, now=101.0)
        assert not completed
        assert gesture.step == 0
        assert not gesture.is_active

    def test_step2_trigger_on_a1_lift(self):
        gesture = ToggleNightModeGesture()
        board = create_starting_board()
        board[0][1] = 0
        gesture.evaluate(board, now=100.0)

        # Lift a1
        board[0][0] = 0
        completed = gesture.evaluate(board, now=101.0)
        assert not completed
        assert gesture.step == 2
        assert "Replace a1 and a2" in (gesture.hint or "")
        overlay = gesture.get_led_overlay(now=101.0)
        assert (0, 0) in overlay
        assert (0, 1) in overlay

    def test_step2_completion_toggles_night_mode(self):
        from board_hardware import settings
        mock_mgr = MagicMock()
        gesture = ToggleNightModeGesture(state_manager=mock_mgr)

        settings["night_mode"] = False
        board = create_starting_board()
        board[0][1] = 0
        gesture.evaluate(board, now=100.0)
        board[0][0] = 0
        gesture.evaluate(board, now=101.0)

        # Replace both a1 and a2
        board[0][0] = -1
        board[0][1] = -1
        completed = gesture.evaluate(board, now=102.0)
        assert completed
        assert gesture.step == 0
        assert not gesture.is_active

        # Completion execution toggles night_mode
        gesture.execute_completion()
        assert settings["night_mode"] is True
        mock_mgr.trigger_arrival_flash.assert_called_once_with(0, 0, duration=0.6, extra_squares=[(0, 1)])

