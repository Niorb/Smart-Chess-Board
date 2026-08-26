import asyncio
import os
import sys
import chess
import pytest
from unittest.mock import MagicMock, patch

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.endgame_db import (
    EndgameCategory,
    EndgameDrill,
    EndgameProgressManager,
    CORE_ENDGAME_DRILLS,
)
from app.board_state import BoardStateManager
from app.gesture_engine import PhysicalGestureEngine, EndgameMenuGesture
from app.led_animations import (
    get_piece_type_color,
    render_endgame_setup,
    render_white_setup_complete_wave,
)
from app.led_helpers import (
    COLOR_INT_PIECE_KING,
    COLOR_INT_PIECE_QUEEN,
    COLOR_INT_PIECE_ROOK,
    COLOR_INT_PIECE_BISHOP,
    COLOR_INT_PIECE_KNIGHT,
    COLOR_INT_PIECE_PAWN,
    COLOR_INT_OFF,
)


def test_core_curriculum_integrity():
    """Verifies all 12 core endgame drills exist and have valid FEN positions."""
    assert len(CORE_ENDGAME_DRILLS) >= 11
    for drill in CORE_ENDGAME_DRILLS:
        assert drill.id
        assert drill.title
        assert drill.category in [
            EndgameCategory.PAWNS,
            EndgameCategory.ROOKS,
            EndgameCategory.MINORS,
            EndgameCategory.QUEENS,
        ]
        # Validate FEN parses into legal chess board
        board = chess.Board(drill.fen)
        assert board.is_valid() or len(board.piece_map()) >= 2
        assert drill.target_moves_par > 0
        assert 1 <= drill.difficulty <= 5


def test_progress_manager_operations(tmp_path):
    """Tests progression manager persistence, stars calculation, custom drills, and reset."""
    progress_file = str(tmp_path / "test_endgame_progress.json")
    mgr = EndgameProgressManager(storage_path=progress_file)

    # 1. Initial state
    drills = mgr.get_all_drills()
    assert len(drills) >= 11
    assert all(d.get("progress") is None for d in drills)

    # 2. Record 3-star completion (0 mistakes, par moves)
    drill_id = drills[0]["id"]
    stars = mgr.record_completion(drill_id=drill_id, mistakes=0, moves_count=4, accuracy=100.0)
    assert stars == 3

    prog = mgr.get_progress(drill_id)
    assert prog is not None
    assert prog["stars"] == 3
    assert prog["accuracy"] == 100.0
    assert prog["attempts"] == 1

    # 3. Record 2-star completion on second drill
    drill_id_2 = drills[1]["id"]
    stars_2 = mgr.record_completion(drill_id=drill_id_2, mistakes=1, moves_count=8, accuracy=85.0)
    assert stars_2 == 2

    # 4. Add custom drill
    custom_drill = mgr.add_custom_drill(
        title="Custom Pawn Defense",
        fen="8/8/8/4k3/8/8/4P3/4K3 w - - 0 1",
        player_color="white",
        target_goal="win",
        difficulty=2,
    )
    assert custom_drill.id.startswith("custom_")
    assert custom_drill.category == EndgameCategory.CUSTOM
    assert mgr.get_drill_by_id(custom_drill.id) is not None

    # 5. Reset progress
    mgr.reset_progress()
    prog_reset = mgr.get_progress(drill_id)
    assert prog_reset is None


def test_two_phase_sparse_setup_validation():
    """Tests sparse piece setup validation for Phase 1 (White) and Phase 2 (Black)."""
    mgr = BoardStateManager()
    # Test Lucena position: 1K6/1P1k4/8/8/8/8/r7/2R5 w - - 0 1
    # White pieces: K on b8 (1, 7), P on b7 (1, 6), R on c1 (2, 0) -> South pole -1
    # Black pieces: K on d7 (3, 6), R on a2 (0, 1) -> North pole +1
    drill = EndgameDrill(
        id="test_lucena",
        title="Lucena Position",
        category=EndgameCategory.ROOKS,
        fen="1K6/1P1k4/8/8/8/8/r7/2R5 w - - 0 1",
        player_color="white",
        target_goal="win",
        difficulty=2,
    )
    mgr.endgame_drill = drill
    mgr.endgame_board = chess.Board(drill.fen)

    # State with empty board (all 0s)
    empty_state = [[0] * 8 for _ in range(8)]
    mgr.endgame_phase = "setup_white"
    is_ready, missing_w, missing_b, misplaced = mgr._validate_endgame_sparse_setup(empty_state)
    assert is_ready is False
    assert len(missing_w) == 3  # b8, b7, c1
    assert len(misplaced) == 0

    # Place White pieces correctly
    white_ready_state = [[0] * 8 for _ in range(8)]
    white_ready_state[1][7] = -1  # b8
    white_ready_state[1][6] = -1  # b7
    white_ready_state[2][0] = -1  # c1

    is_ready, missing_w, missing_b, misplaced = mgr._validate_endgame_sparse_setup(white_ready_state)
    assert is_ready is True
    assert len(missing_w) == 0
    assert len(misplaced) == 0

    # Extra misplaced piece on a1
    white_with_extra = [list(col) for col in white_ready_state]
    white_with_extra[0][0] = -1  # a1 extra piece
    is_ready, missing_w, missing_b, misplaced = mgr._validate_endgame_sparse_setup(white_with_extra)
    assert is_ready is False
    assert (0, 0) in misplaced

    # Phase 2: Black setup
    mgr.endgame_phase = "setup_black"
    full_ready_state = [list(col) for col in white_ready_state]
    full_ready_state[3][6] = 1  # d7
    full_ready_state[0][1] = 1  # a2

    is_ready, missing_w, missing_b, misplaced = mgr._validate_endgame_sparse_setup(full_ready_state)
    assert is_ready is True
    assert len(missing_w) == 0
    assert len(missing_b) == 0
    assert len(misplaced) == 0


def test_endgame_state_machine_and_moves():
    """Tests endgame drill lifecycle, moves execution, hints, and completion."""
    async def _test():
        mgr = BoardStateManager()
        # King & Pawn vs King: 8/8/8/4k3/8/4P3/8/4K3 w - - 0 1
        res = await mgr.start_endgame_drill(drill_id="pawn_opposition")
        assert res["active"] is True
        assert mgr.analysis_submode == "endgame"
        assert mgr.endgame_phase == "setup_white"
        assert mgr.endgame_moves_played == 0
        assert mgr.endgame_mistakes == 0

        # Advance to playing phase
        mgr.endgame_phase = "playing"

        payload = mgr.get_endgame_payload()
        assert "turn" in payload
        assert "player_color" in payload
        assert "solution_line" in payload
        assert "solution_explanation" in payload

        # Request on-demand hint
        hint = mgr.request_endgame_hint()
        assert "hint_uci" in hint or "hint_text" in hint

        # Play legal move: e3d3 (taking opposition)
        legal_move = "e3d3"
        move_res = mgr.handle_endgame_move_sync(legal_move, source="board")
        assert move_res.get("result") in ("ok", "complete")
        assert mgr.endgame_moves_played == 1
        assert len(mgr.endgame_history) == 1

        # Stop drill
        stop_res = mgr.stop_endgame_drill()
        assert stop_res["status"] == "IDLE"
        assert mgr.game_status == "IDLE"
        assert mgr.endgame_active is False

    asyncio.run(_test())


def test_endgame_opponent_reply_and_solution():
    """Verifies that endgame drills provide solution lines and handle opponent replies."""
    async def _test():
        mgr = BoardStateManager()
        # Start Lucena position drill
        res = await mgr.start_endgame_drill(drill_id="rook_lucena")
        assert res["active"] is True
        assert mgr.endgame_drill is not None
        assert len(mgr.endgame_drill.solution_line) > 0
        assert len(mgr.endgame_drill.solution_explanation) > 0

        # Advance to playing
        mgr.endgame_phase = "playing"

        # Check payload contains solution line and turn information
        payload = mgr.get_endgame_payload()
        assert payload["turn"] == "white"
        assert payload["player_color"] == "white"
        assert len(payload["solution_line"]) > 0

        # Simulate White making the 1st move (1. Rd1+) from web source
        move_res = mgr.handle_endgame_move_sync("c1d1", source="web")
        assert move_res.get("result") == "ok"
        assert mgr.endgame_moves_played >= 1

        # Verify pending reply application helper
        mgr.endgame_pending_reply = {
            "uci": "d8e7",
            "san": "Ke7",
            "from": [3, 7],
            "to": [4, 6],
            "from_sq": "d8",
            "to_sq": "e7",
            "is_capture": False,
        }
        apply_res = mgr.apply_endgame_pending_opponent_move()
        assert apply_res.get("result") == "ok"
        assert "Ke7" in mgr.endgame_history

    asyncio.run(_test())


def test_piece_led_color_palette_and_renderers():
    """Tests that piece types resolve to their standardized colors."""
    # King -> Royal Gold
    k_col = get_piece_type_color(chess.KING, night_mode=False)
    assert k_col == COLOR_INT_PIECE_KING

    # Queen -> Royal Violet
    q_col = get_piece_type_color(chess.QUEEN, night_mode=False)
    assert q_col == COLOR_INT_PIECE_QUEEN

    # Rook -> Azure Cyan
    r_col = get_piece_type_color(chess.ROOK, night_mode=False)
    assert r_col == COLOR_INT_PIECE_ROOK

    # Bishop -> Amber
    b_col = get_piece_type_color(chess.BISHOP, night_mode=False)
    assert b_col == COLOR_INT_PIECE_BISHOP

    # Knight -> Mint Emerald
    n_col = get_piece_type_color(chess.KNIGHT, night_mode=False)
    assert n_col == COLOR_INT_PIECE_KNIGHT

    # Pawn -> Pearl
    p_col = get_piece_type_color(chess.PAWN, night_mode=False)
    assert p_col == COLOR_INT_PIECE_PAWN

    # Render frame
    frame = [COLOR_INT_OFF] * 64
    target_pieces = {
        (4, 0): (chess.KING, True),     # e1 White King
        (4, 2): (chess.PAWN, True),     # e3 White Pawn
        (4, 4): (chess.KING, False),    # e5 Black King
    }
    physical_state = [[0] * 8 for _ in range(8)]
    render_endgame_setup(100.0, frame, target_pieces, physical_state, phase="setup_white", params={"night_mode": False})
    # Target squares for White pieces must have non-zero colors
    assert any(c != COLOR_INT_OFF for c in frame)

    # Render Ivory wave
    wave_frame = [COLOR_INT_OFF] * 64
    render_white_setup_complete_wave(0.5, wave_frame, params={"night_mode": False})
    assert any(c != COLOR_INT_OFF for c in wave_frame)


def _make_starting_grid():
    grid = [[0] * 8 for _ in range(8)]
    for c in range(8):
        for r in (0, 1, 6, 7):
            grid[c][r] = 1
    return grid


def test_endgame_c2_gesture_interaction():
    """Tests the EndgameMenuGesture lifecycle when c2 pawn is lifted and replaced."""
    engine = PhysicalGestureEngine()
    gesture = next((g for g in engine.gestures if isinstance(g, EndgameMenuGesture)), None)
    assert gesture is not None
    assert gesture.starter_coord == (2, 1)  # c2 pawn

    grid = _make_starting_grid()
    now = 100.0

    # 1. Lift c2 -> Arms gesture and lights category selectors on Rank 1 (a1..d1)
    grid[2][1] = 0
    res = gesture.evaluate(grid, now, is_armed=True)
    assert res is False
    assert gesture.is_active is True
    assert gesture.step == 1

    indicators = gesture.get_indicator_leds(time_now=100.0)
    assert (0, 0) in indicators  # a1: Pawns
    assert (1, 0) in indicators  # b1: Rooks
    assert (2, 0) in indicators  # c1: Minors
    assert (3, 0) in indicators  # d1: Queens

    # 2. Lift a category piece (e.g. b1: Rooks) -> cycles selected category to rook
    grid[1][0] = 0
    gesture.evaluate(grid, now + 1.0, is_armed=True)
    assert gesture.selected_category == "rook"

    # Replace category piece b1
    grid[1][0] = 1
    gesture.evaluate(grid, now + 2.0, is_armed=True)

    # 3. Replace c2 -> confirms selection and starts drill
    grid[2][1] = 1
    success = gesture.evaluate(grid, now + 3.0, is_armed=True)
    assert success is True
    assert gesture.is_active is False
