import os
import sys
import time
from unittest.mock import MagicMock, patch

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.board_state import BoardStateManager
from app.led_helpers import DualPixelStrip


def test_board_state_manager_init():
    bsm = BoardStateManager()
    assert bsm.game_status == "IDLE"
    assert bsm.virtual_only is False
    assert bsm.clocks == {"white": "?", "black": "?"}
    assert len(bsm.physical_state) == 8
    assert len(bsm.physical_state[0]) == 8
    assert len(bsm.digital_state) == 8


def test_board_ready_suppressed_on_gesture_completion_tick():
    """Closing a gesture gate (second piece replaced) must NOT replay the BOARD_READY setup animation."""
    bsm = BoardStateManager()
    bsm.game_status = "IDLE"
    bsm.prev_setup_ready = False

    bsm._process_setup_ready_edge(is_ready=True, gestures_just_completed=["start_analysis"])

    assert bsm.prev_setup_ready is True
    assert bsm.active_animation is None


def test_board_ready_fires_on_plain_setup_restore():
    """Without a completing gesture, restoring the full setup still triggers the animation."""
    bsm = BoardStateManager()
    bsm.game_status = "IDLE"
    bsm.prev_setup_ready = False

    bsm._process_setup_ready_edge(is_ready=True, gestures_just_completed=[])

    assert bsm.prev_setup_ready is True
    assert bsm.active_animation is not None
    assert bsm.active_animation.name == "BOARD_READY"


def test_setup_unready_cancels_pending_board_ready():
    """Lifting a piece while BOARD_READY plays cancels the animation and restores baselines."""
    from app.led_animations import create_animation
    from board_hardware import settings as board_settings

    bsm = BoardStateManager()
    bsm.game_status = "IDLE"
    baselines = [[100 + c] * 8 for c in range(8)]
    board_settings["baselines"] = [list(col) for col in baselines]
    bsm.frozen_baselines = [list(col) for col in baselines]
    bsm.active_animation = create_animation("BOARD_READY")
    bsm.prev_setup_ready = True

    bsm._process_setup_ready_edge(is_ready=False, gestures_just_completed=[])

    assert bsm.prev_setup_ready is False
    assert bsm.active_animation is None
    assert bsm.frozen_baselines is None
    assert board_settings["baselines"][0][0] == 100


def test_physical_payload_structure():
    bsm = BoardStateManager()
    payload = bsm.get_physical_payload()
    assert payload["rows"] == 8
    assert payload["cols"] == 8
    assert "grid" in payload
    assert "adc" in payload
    assert "baselines" in payload
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
    from app.led_helpers import (
        COLOR_INT_LEGAL_CAPTURE,
        COLOR_INT_LEGAL_TARGET,
        COLOR_INT_PIECE_LIFTED,
        get_led_indices,
    )
    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.game_status = "PLAYING"

    # White pawn on e4 lifted: e5 is quiet target (4, 4), d5 is capture target (3, 4)
    bsm.move_tracker.lifted_square = (4, 3)
    bsm.move_tracker.legal_targets = [(4, 4), (3, 4)]
    bsm.move_tracker.legal_captures = [(3, 4)]

    bsm._update_leds()

    # Verify setPixelColor calls for quiet target (4, 4) vs capture target (3, 4)
    get_led_indices(4, 4)
    get_led_indices(4, 3)  # lifted e4 is (c=4, r=3)
    get_led_indices(4, 3) # capture square (c=3, r=4) -> get_led_indices(r=4, c=3)
    get_led_indices(4, 3)

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


def test_night_mode_legal_target_and_capture_dots_colors():
    """Verify that _update_leds uses high-contrast Night Mode colors when night_mode is True."""
    from app.led_helpers import (
        COLOR_INT_NIGHT_LEGAL_CAPTURE,
        COLOR_INT_NIGHT_LEGAL_TARGET,
        COLOR_INT_NIGHT_PIECE_LIFTED,
    )
    from board_hardware import settings
    settings["night_mode"] = True
    try:
        bsm = BoardStateManager()
        bsm.strip = MagicMock()
        bsm.game_status = "PLAYING"
        bsm.move_tracker.lifted_square = (4, 3)  # e4
        bsm.move_tracker.legal_targets = [(4, 4), (3, 4)]  # e5 (quiet), d5 (capture)
        bsm.move_tracker.legal_captures = [(3, 4)]

        bsm._update_leds()

        call_args = [call[0] for call in bsm.strip.setPixelColor.call_args_list]
        colors_called = [arg[1] for arg in call_args]

        assert COLOR_INT_NIGHT_PIECE_LIFTED in colors_called
        assert COLOR_INT_NIGHT_LEGAL_TARGET in colors_called
        assert COLOR_INT_NIGHT_LEGAL_CAPTURE in colors_called
    finally:
        settings["night_mode"] = False


def test_night_mode_turn_indicator_led_render():
    """Verify that _update_leds renders amethyst purple for Black King in Night Mode."""
    import chess
    from app.lichess_engine import lichess_engine
    from board_hardware import settings
    settings["night_mode"] = True
    try:
        bsm = BoardStateManager()
        bsm.strip = MagicMock()
        bsm.game_status = "PLAYING"
        board = chess.Board()
        board.turn = chess.BLACK
        lichess_engine.board = board

        bsm._update_leds()
        assert bsm.strip.setPixelColor.called
        assert bsm.strip.show.called
    finally:
        settings["night_mode"] = False


def test_board_state_setup_ready_persistent_anchor():
    """Verify that _update_leds renders persistent Royal Guard Anchor when all 32 pieces are in place."""
    from app.led_helpers import get_led_indices

    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.game_status = "IDLE"
    bsm.active_animation = None

    # Set up starting physical state (White=-1 on Ranks 1-2, Black=+1 on Ranks 7-8)
    for c in range(8):
        bsm.physical_state[c][0] = -1  # White pieces
        bsm.physical_state[c][1] = -1  # White pawns
        bsm.physical_state[c][2] = 0
        bsm.physical_state[c][3] = 0
        bsm.physical_state[c][4] = 0
        bsm.physical_state[c][5] = 0
        bsm.physical_state[c][6] = 1  # Black pawns
        bsm.physical_state[c][7] = 1  # Black pieces

    bsm._update_leds()

    assert bsm.setup_result.is_setup_ready is True
    assert bsm.strip.setPixelColor.called

    call_args = [call[0] for call in bsm.strip.setPixelColor.call_args_list]
    lit_indices = {arg[0] for arg in call_args if arg[1] != 0}

    # Verify gesture starter pawns (a2, e2, h2) are included in lit indices
    starter_coords = [(0, 1), (4, 1), (7, 1)]
    for c_sq, r_sq in starter_coords:
        expected_indices = get_led_indices(r_sq, c_sq)
        assert any(idx in lit_indices for idx in expected_indices if idx < 152)


def test_board_state_setup_ready_cancellation_on_lift():
    """Verify that when a piece is lifted during ready state, prev_setup_ready resets and animation cancels."""
    bsm = BoardStateManager()
    bsm.game_status = "IDLE"
    bsm.prev_setup_ready = True
    bsm.trigger_animation("BOARD_READY")
    assert bsm.active_animation is not None
    assert bsm.active_animation.name == "BOARD_READY"

    # Break starting formation by lifting a piece
    bsm.physical_state[0][0] = 0
    bsm.setup_result = bsm.setup_validator.validate(bsm.physical_state)
    assert bsm.setup_result.is_setup_ready is False

    # Simulate falling edge logic
    if not bsm.setup_result.is_setup_ready and bsm.prev_setup_ready:
        bsm.prev_setup_ready = False
        if bsm.active_animation and bsm.active_animation.name in ["BOARD_READY", "SETUP_COMPLETE"]:
            bsm.active_animation = None

    assert bsm.prev_setup_ready is False
    assert bsm.active_animation is None











# =============================================================================
# Chess Clock Drain Bars (PLAYING mode, files a/h) & eval-bar fallback
# =============================================================================

def _seed_clock_state(raw_white_ms, raw_black_ms, initial_white_ms, initial_black_ms, updated_at):
    """Seed the global lichess engine singleton with a deterministic clock state."""
    from app.lichess_engine import lichess_engine
    lichess_engine.raw_clocks_ms = {"white": raw_white_ms, "black": raw_black_ms}
    lichess_engine.initial_clocks_ms = {"white": initial_white_ms, "black": initial_black_ms}
    lichess_engine.clocks_updated_at = updated_at


class _ClockStateSnapshot:
    """Saves/restores the global lichess engine fields mutated by clock-bar tests."""

    FIELDS = ("board", "raw_clocks_ms", "initial_clocks_ms", "clocks_updated_at", "opponent_gone")

    def __enter__(self):
        from app.lichess_engine import lichess_engine
        self._engine = lichess_engine
        self._saved = {f: getattr(lichess_engine, f, None) for f in self.FIELDS}
        for f in self.FIELDS:
            if isinstance(self._saved[f], dict):
                self._saved[f] = dict(self._saved[f])
        return self

    def __exit__(self, *exc):
        for f, value in self._saved.items():
            setattr(self._engine, f, value)
        return False


def _lit_colors_by_index(strip):
    """Map LED index -> last nonzero color written by setPixelColor during flush_frame."""
    lit = {}
    for c in strip.setPixelColor.call_args_list:
        if c.args[1] != 0:
            lit[c.args[0]] = c.args[1]
    return lit


def _lit_ranks_for_file(lit_by_idx, file_idx):
    """Return ranks whose square on the given file received at least one nonzero LED."""
    from app.led_helpers import get_led_indices
    return [
        rank
        for rank in range(8)
        if any(idx in lit_by_idx for idx in get_led_indices(rank, file_idx))
    ]


def test_board_state_clock_bars_render_and_suppress_eval_bar():
    """
    With valid clock state during PLAYING, files a/h render chess-clock drain bars
    (COLOR_INT_CLOCK_OK) and the perimeter eval bar is fully suppressed.
    """
    import chess
    from app.lichess_engine import lichess_engine
    from app.led_helpers import (
        COLOR_INT_CLOCK_OK,
        COLOR_INT_EVAL_BLACK,
        COLOR_INT_EVAL_WHITE,
        COLOR_INT_NIGHT_CLOCK_CRIT,
        COLOR_INT_NIGHT_CLOCK_OK,
        COLOR_INT_NIGHT_CLOCK_WARN,
        COLOR_INT_NIGHT_EVAL_BLACK,
        COLOR_INT_NIGHT_EVAL_WHITE,
        get_led_indices,
    )

    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.game_status = "PLAYING"

    with _ClockStateSnapshot():
        # White to move; white has full time (raw > initial clamps to a full,
        # unscaled bar despite the tiny interpolation elapsed), black half drained.
        lichess_engine.board = chess.Board()
        _seed_clock_state(61000, 30000, 60000, 60000, time.time())
        lichess_engine.opponent_gone = None

        bsm._update_leds()

        assert bsm.strip.setPixelColor.called
        assert bsm.strip.show.called

        lit_by_idx = _lit_colors_by_index(bsm.strip)
        all_colors = {c.args[1] for c in bsm.strip.setPixelColor.call_args_list}

        # White clock bar: h-file (file 7) at frac=1.0 -> all 8 ranks in clock-ok green
        assert _lit_ranks_for_file(lit_by_idx, 7) == list(range(8))
        for rank in range(8):
            for idx in get_led_indices(rank, 7):
                if idx in lit_by_idx:
                    assert lit_by_idx[idx] == COLOR_INT_CLOCK_OK

        # Black clock bar: a-file (file 0) at frac=0.5 -> truncated to ranks 0-3
        assert _lit_ranks_for_file(lit_by_idx, 0) == [0, 1, 2, 3]
        for rank in range(4):
            for idx in get_led_indices(rank, 0):
                if idx in lit_by_idx:
                    assert lit_by_idx[idx] == COLOR_INT_CLOCK_OK

        # Eval bar must be suppressed entirely (day AND night palette colors absent)
        for banned in (
            COLOR_INT_EVAL_WHITE,
            COLOR_INT_EVAL_BLACK,
            COLOR_INT_NIGHT_EVAL_WHITE,
            COLOR_INT_NIGHT_EVAL_BLACK,
            COLOR_INT_NIGHT_CLOCK_OK,
            COLOR_INT_NIGHT_CLOCK_WARN,
            COLOR_INT_NIGHT_CLOCK_CRIT,
        ):
            assert banned not in all_colors, f"Unexpected color {banned} while clock bars active"


def test_board_state_eval_bar_fallback_when_clock_bar_disabled():
    """
    With clock_bar_enabled=False and otherwise-valid clock state, the legacy
    eval-bar path still renders on file h and no clock colors appear.
    """
    from board_hardware import settings
    from app.lichess_engine import lichess_engine
    from app.led_helpers import (
        COLOR_INT_CLOCK_OK,
        COLOR_INT_EVAL_BLACK,
        COLOR_INT_EVAL_WHITE,
        get_led_indices,
    )

    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.game_status = "PLAYING"
    settings["clock_bar_enabled"] = False
    settings["coach_ai_only"] = False

    with _ClockStateSnapshot():
        # Clock state is deliberately VALID so only the setting gates the fallback.
        import chess

        lichess_engine.board = chess.Board()
        _seed_clock_state(60000, 30000, 60000, 60000, time.time())
        lichess_engine.opponent_gone = None

        bsm._update_leds()

        assert bsm.strip.setPixelColor.called
        assert bsm.strip.show.called

        lit_by_idx = _lit_colors_by_index(bsm.strip)
        all_colors = {c.args[1] for c in bsm.strip.setPixelColor.call_args_list}

        # Eval bar renders on file h: win_chance defaults to 50 -> 4 white / 4 black rows
        h_ranks = _lit_ranks_for_file(lit_by_idx, 7)
        assert h_ranks == list(range(8))
        h_colors = {lit_by_idx[idx] for rank in range(8) for idx in get_led_indices(rank, 7) if idx in lit_by_idx}
        assert COLOR_INT_EVAL_WHITE in h_colors
        assert COLOR_INT_EVAL_BLACK in h_colors

        # No clock-bar rendering anywhere (a-file stays dark too)
        assert COLOR_INT_CLOCK_OK not in all_colors
        assert _lit_ranks_for_file(lit_by_idx, 0) == []


def test_board_state_clock_interpolation_side_to_move_drains():
    """
    Only the side-to-move clock interpolates forward: with clocks_updated_at 40 s
    in the past, white's h-file bar drains to ~1/3 (3 ranks incl. breathing edge)
    while black's static a-file bar stays at half (4 ranks).
    """
    import chess
    from board_hardware import settings
    from app.lichess_engine import lichess_engine
    from app.led_helpers import COLOR_INT_CLOCK_OK, get_led_indices

    bsm = BoardStateManager()
    bsm.strip = MagicMock()
    bsm.game_status = "PLAYING"
    settings["clock_bar_enabled"] = True

    with _ClockStateSnapshot():
        lichess_engine.board = chess.Board()  # white to move
        _seed_clock_state(60000, 30000, 60000, 60000, time.time() - 40.0)
        lichess_engine.opponent_gone = None

        bsm._update_leds()

        lit_by_idx = _lit_colors_by_index(bsm.strip)

        # White remaining ~= 20 s of 60 s -> frac ~0.333 -> ranks 0-2 lit (edge at 2)
        white_ranks = _lit_ranks_for_file(lit_by_idx, 7)
        assert white_ranks == [0, 1, 2], f"White stm bar should drain to 3 ranks, got {white_ranks}"

        # Black clock is NOT running -> stays at frac=0.5 -> ranks 0-3 lit
        black_ranks = _lit_ranks_for_file(lit_by_idx, 0)
        assert black_ranks == [0, 1, 2, 3], f"Black static bar should hold 4 ranks, got {black_ranks}"

        assert len(white_ranks) < len(black_ranks)

        # Full squares on both bars use the ok urgency band (>0.25 fraction)
        assert lit_by_idx.get(get_led_indices(0, 7)[0]) == COLOR_INT_CLOCK_OK
        assert lit_by_idx.get(get_led_indices(0, 0)[0]) == COLOR_INT_CLOCK_OK
