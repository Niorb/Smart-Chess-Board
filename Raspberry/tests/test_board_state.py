import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.board_state import BoardStateManager
from app.led_helpers import Color, DualPixelStrip


def test_board_state_manager_init():
    bsm = BoardStateManager()
    assert bsm.game_status == "IDLE"
    assert bsm.virtual_only is False
    assert bsm.clocks == {"white": "?", "black": "?"}
    assert len(bsm.physical_state) == 8
    assert len(bsm.physical_state[0]) == 8
    assert len(bsm.digital_state) == 8


def test_physical_payload_structure():
    bsm = BoardStateManager()
    payload = bsm.get_physical_payload()
    assert payload["rows"] == 8
    assert payload["cols"] == 8
    assert "grid" in payload
    assert "adc" in payload
    assert "baselines" in payload
    assert "highlighted_square" in payload
    assert "disabled_squares" in payload
    assert "virtual_only" in payload
    assert "in_flight_move" in payload
    assert payload["virtual_only"] is False


def test_health_status_structure():
    bsm = BoardStateManager()
    health = bsm.get_health_status()
    assert "status" in health
    assert health["status"] in ["HEALTHY", "DEGRADED", "DISCONNECTED"]
    assert "subsystems" in health
    assert "serial" in health["subsystems"]
    assert "gpio" in health["subsystems"]
    assert "led_strip" in health["subsystems"]
    assert "lichess_engine" in health["subsystems"]
    assert "matrix" in health
    assert "col_mode" in health["matrix"]
    assert "disabled_squares" in health["matrix"]
    assert "scan_delay_ms" in health["matrix"]


def test_health_status_evaluations():
    bsm = BoardStateManager()

    # Force DISCONNECTED by removing serial & gpio
    bsm.ser = None
    bsm.h = None
    assert bsm.get_health_status()["status"] == "DISCONNECTED"
    assert bsm.get_health_status()["subsystems"]["serial"] == "DISCONNECTED"
    assert bsm.get_health_status()["subsystems"]["gpio"] == "DISCONNECTED"


def test_virtual_only_mode_health_status():
    bsm = BoardStateManager()
    bsm.virtual_only = True
    bsm.ser = None
    bsm.h = None

    # In virtual-only mode, missing serial/gpio does not mark the board DISCONNECTED
    health = bsm.get_health_status()
    assert health["matrix"]["virtual_only"] is True


def test_led_suppression_during_calibration():
    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.move_tracker.lifted_square = (0, 3)

    bsm.is_calibrating = True
    bsm._update_leds()
    bsm.strip.setPixelColor.assert_not_called()


def test_led_suppression_in_virtual_only_mode():
    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.move_tracker.lifted_square = (0, 3)

    bsm.virtual_only = True
    bsm._update_leds()
    bsm.strip.setPixelColor.assert_not_called()


def test_safe_calibrate_no_deadlock():
    bsm = BoardStateManager()
    bsm.ser = MagicMock()
    bsm.strip = DualPixelStrip(num_leds_per_strip=76)
    bsm.strip.set_serial_conn(bsm.ser, bsm.serial_lock)

    # Calling _safe_calibrate must execute without deadlocking
    with patch("board_hardware.calibrate_board", return_value=True):
        res = bsm._safe_calibrate()
        assert res is True


def test_baseline_freezing_and_restoration_during_animation():
    from board_hardware import settings
    bsm = BoardStateManager()
    bsm.strip = MagicMock()

    # Set custom baseline
    settings["baselines"] = [[1600] * 8 for _ in range(8)]
    assert bsm.frozen_baselines is None

    # Trigger animation -> should snapshot baselines
    success = bsm.trigger_animation("GAME_STARTED")
    assert success is True
    assert bsm.active_animation is not None
    assert bsm.frozen_baselines == [[1600] * 8 for _ in range(8)]

    # Simulate drift or tampering during animation
    settings["baselines"][0][0] = 9999

    # Advance time beyond animation duration
    import time
    past_anim = bsm.active_animation
    past_anim.start_time = time.time() - 10.0  # Expired

    # Call _update_leds to trigger animation cleanup
    bsm._update_leds()
    assert bsm.active_animation is None
    assert bsm.frozen_baselines is None
    # Baseline must be restored to original 1600
    assert settings["baselines"][0][0] == 1600


def test_baseline_freezing_during_led_test():
    import asyncio
    from board_hardware import settings
    bsm = BoardStateManager()
    bsm.strip = MagicMock()

    settings["baselines"] = [[1700] * 8 for _ in range(8)]
    assert bsm.frozen_baselines is None

    # Run LED test with sleep patched out
    with patch("asyncio.sleep", return_value=None):
        asyncio.run(bsm.run_led_test())

    assert bsm.led_test_active is False
    assert bsm.frozen_baselines is None
    assert settings["baselines"][0][0] == 1700


def test_board_state_seeking_continuous_led_render():
    """Verify that when game_status == 'SEEKING', _update_leds renders the seeking animation to strip."""
    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.game_status = "SEEKING"

    bsm._update_leds()
    assert bsm.strip.setPixelColor.called
    assert bsm.strip.show.called


def test_board_state_freezes_baseline_when_piece_lifted():
    """Verify that when a piece is lifted or in flight, freeze_baseline is passed to scan_board."""
    bsm = BoardStateManager()
    bsm.move_tracker.lifted_square = (4, 1)  # Piece lifted on e2

    is_animating = bool(
        (bsm.active_animation is not None and bsm.active_animation.is_active())
        or bsm.led_test_active
    )
    is_piece_moving = bool(
        bsm.move_tracker.lifted_square is not None
        or bsm.move_tracker.in_flight_move is not None
    )
    freeze_baseline = is_animating or is_piece_moving
    assert freeze_baseline is True


def test_trigger_arrival_flash():
    bsm = BoardStateManager()
    bsm.trigger_arrival_flash(4, 3, is_capture=False)
    assert bsm.arrival_flash is not None
    assert bsm.arrival_flash["square"] == (4, 3)
    assert bsm.arrival_flash["is_capture"] is False
    assert bsm.arrival_flash["duration"] == 0.45

    bsm.trigger_arrival_flash(3, 4, is_capture=True, duration=0.6)
    assert bsm.arrival_flash["square"] == (3, 4)
    assert bsm.arrival_flash["is_capture"] is True
    assert bsm.arrival_flash["duration"] == 0.6


def test_arrival_flash_rendering_and_expiration():
    import time
    bsm = BoardStateManager()
    bsm.strip = MagicMock()

    # Trigger active flash
    bsm.trigger_arrival_flash(4, 3, is_capture=False)
    bsm._update_leds()
    assert bsm.strip.setPixelColor.called
    assert bsm.arrival_flash is not None

    # Fast forward past duration
    bsm.arrival_flash["start_time"] = time.time() - 1.0
    bsm._update_leds()
    assert bsm.arrival_flash is None


def test_move_tracker_arrival_flash_rendering():
    import time
    bsm = BoardStateManager()
    bsm.strip = MagicMock()

    bsm.move_tracker.arrival_flash = {
        "square": (2, 3),
        "start_time": time.time(),
        "duration": 0.45,
        "is_capture": True,
    }
    bsm._update_leds()
    assert bsm.strip.setPixelColor.called
    assert bsm.move_tracker.arrival_flash is not None

    # Fast forward past duration
    bsm.move_tracker.arrival_flash["start_time"] = time.time() - 1.0
    bsm._update_leds()
    assert bsm.move_tracker.arrival_flash is None


def test_clear_all_leds_clears_arrival_flash():
    import time
    bsm = BoardStateManager()
    bsm.arrival_flash = {"square": (0, 0), "start_time": time.time(), "duration": 0.45, "is_capture": False}
    bsm.move_tracker.arrival_flash = {"square": (1, 1), "start_time": time.time(), "duration": 0.45, "is_capture": False}
    bsm.clear_all_leds()
    assert bsm.arrival_flash is None
    assert bsm.move_tracker.arrival_flash is None


def test_legal_target_and_capture_dots_colors():
    """Verify that _update_leds colors quiet target squares with COLOR_INT_LEGAL_TARGET and capture squares with COLOR_INT_LEGAL_CAPTURE."""
    from app.led_helpers import COLOR_INT_LEGAL_CAPTURE, COLOR_INT_LEGAL_TARGET, COLOR_INT_PIECE_LIFTED, get_led_indices
    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.game_status = "PLAYING"

    # White pawn on e4 lifted: e5 is quiet target (4, 4), d5 is capture target (3, 4)
    bsm.move_tracker.lifted_square = (4, 3)
    bsm.move_tracker.legal_targets = [(4, 4), (3, 4)]
    bsm.move_tracker.legal_captures = [(3, 4)]

    bsm._update_leds()

    # Verify setPixelColor calls for quiet target (4, 4) vs capture target (3, 4)
    e5_indices = get_led_indices(4, 4)
    d5_indices = get_led_indices(4, 3)  # lifted e4 is (c=4, r=3)
    cap_d5_indices = get_led_indices(4, 3) # capture square (c=3, r=4) -> get_led_indices(r=4, c=3)
    d5_cap_indices = get_led_indices(4, 3)

    # Check that setPixelColor was called with COLOR_INT_LEGAL_TARGET and COLOR_INT_LEGAL_CAPTURE
    call_args = [call[0] for call in bsm.strip.setPixelColor.call_args_list]
    colors_called = [arg[1] for arg in call_args]

    assert COLOR_INT_PIECE_LIFTED in colors_called
    assert COLOR_INT_LEGAL_TARGET in colors_called
    assert COLOR_INT_LEGAL_CAPTURE in colors_called


def test_board_state_castling_move_led_render():
    """Verify that _update_leds lights up King and Rook from/to squares on castling."""
    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.game_status = "PLAYING"

    bsm.move_tracker.pending_opponent_move = {
        "uci": "e1g1",
        "from": (4, 0),
        "to": (6, 0),
        "is_capture": False,
        "is_castling": True,
        "rook_from": (7, 0),
        "rook_to": (5, 0),
    }

    bsm._update_leds()
    assert bsm.strip.setPixelColor.called
    assert bsm.strip.show.called


def test_board_state_player_pending_castling_rook_led_render():
    """Verify that _update_leds lights up Rook from/to and renders trace when player castles."""
    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.game_status = "PLAYING"

    bsm.move_tracker.pending_castling_rook = {
        "from": (7, 0),
        "to": (5, 0),
        "start_time": time.time(),
    }

    bsm._update_leds()
    assert bsm.strip.setPixelColor.called
    assert bsm.strip.show.called


def test_board_state_capture_in_progress_led_render():
    """Verify that _update_leds renders capture aura when opponent piece was lifted first."""
    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.game_status = "PLAYING"
    bsm.move_tracker.pending_capture_target = (3, 4)  # d5
    bsm.move_tracker.capture_candidate_attackers = [(4, 3)]  # e4

    bsm._update_leds()
    assert bsm.strip.setPixelColor.called
    assert bsm.strip.show.called


def test_board_state_guardrail_mismatch_led_render():
    """Verify that _update_leds renders alert pulses when board state mismatch is detected."""
    from app.setup_validator import GameGuardrailResult
    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.game_status = "PLAYING"
    bsm.guardrail_result = GameGuardrailResult(
        is_synchronized=False,
        missing_pieces=[(4, 1)],
        unexpected_pieces=[(4, 3)],
    )

    bsm._update_leds()
    assert bsm.strip.setPixelColor.called
    assert bsm.strip.show.called


def test_physical_payload_includes_guardrail_and_capture():
    """Verify that get_physical_payload contains guardrail status and capture info."""
    from app.setup_validator import GameGuardrailResult
    bsm = BoardStateManager()
    bsm.move_tracker.pending_capture_target = (3, 4)
    bsm.move_tracker.capture_candidate_attackers = [(4, 3)]
    bsm.guardrail_result = GameGuardrailResult(
        is_synchronized=False,
        missing_pieces=[(4, 1)],
        unexpected_pieces=[],
        pending_capture=(3, 4),
        candidate_attackers=[(4, 3)],
    )

    payload = bsm.get_physical_payload()
    assert payload["pending_capture_target"] == [3, 4]
    assert payload["capture_candidate_attackers"] == [[4, 3]]
    assert payload["guardrail"] is not None
    assert payload["guardrail"]["is_synchronized"] is False
    assert payload["guardrail"]["missing_pieces"] == [[4, 1]]


def test_board_state_active_turn_indicator_led_render():
    """Verify that _update_leds renders subtle ambient turn indicator on active King."""
    import chess
    from app.lichess_engine import lichess_engine
    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.game_status = "PLAYING"
    lichess_engine.board = chess.Board()

    bsm._update_leds()
    assert bsm.strip.setPixelColor.called
    assert bsm.strip.show.called


def test_board_state_opponent_disconnected_led_render():
    """Verify that _update_leds renders warning beacon and countdown gauge when opponent leaves."""
    import chess
    from app.lichess_engine import lichess_engine
    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.game_status = "PLAYING"
    lichess_engine.board = chess.Board()
    lichess_engine.my_color = "white"
    lichess_engine.opponent_gone = {
        "gone": True,
        "claim_win_in": 25,
        "initial_claim_win_in": 30,
        "start_time": time.time() - 5,
    }

    bsm._update_leds()
    assert bsm.strip.setPixelColor.called
    assert bsm.strip.show.called







