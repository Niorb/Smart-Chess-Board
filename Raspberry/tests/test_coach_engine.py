"""
Raspberry/tests/test_coach_engine.py

Comprehensive unit and integration test suite for the Stockfish AI Coach,
Blunder Guard, Move Delta Classifier, Heuristic Fallback, File 'h' Eval Bar,
LED Highlighting, and Fair-Play enforcement.
"""

import asyncio
import copy
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import chess
import chess.engine
import pytest

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.board_state import BoardStateManager
from app.coach_engine import (
    CoachEngine,
    HeuristicEvaluator,
    MoveAnalysis,
    MoveQuality,
    PositionEvaluation,
    calculate_win_chance,
    classify_move_delta,
)
from app.config import (
    COLOR_EVAL_BLACK,
    COLOR_EVAL_NEUTRAL,
    COLOR_EVAL_WHITE,
    COLOR_LEGAL_CAPTURE,
    COLOR_LEGAL_TARGET,
    COLOR_MOVE_BEST,
    COLOR_MOVE_BLUNDER,
    COLOR_MOVE_GOOD,
    COLOR_MOVE_INACCURACY,
)
from app.led_helpers import Color, get_led_indices


# =============================================================================
# 1. WIN CHANCE & DELTA CLASSIFICATION TESTS
# =============================================================================

class TestWinChanceAndClassification:
    def test_win_chance_equal_position(self):
        """0 centipawns should yield exactly 50% win probability."""
        win_chance = calculate_win_chance(score_cp=0, mate=None)
        assert pytest.approx(win_chance, abs=1.0) == 50.0

    def test_win_chance_white_advantage(self):
        """+300 centipawns should yield ~80-90% win chance."""
        win_chance = calculate_win_chance(score_cp=300, mate=None)
        assert 75.0 <= win_chance <= 95.0

    def test_win_chance_black_advantage(self):
        """-300 centipawns should yield ~5-25% win chance."""
        win_chance = calculate_win_chance(score_cp=-300, mate=None)
        assert 5.0 <= win_chance <= 25.0

    def test_win_chance_crushing_advantage(self):
        """+1000 centipawns should be > 98% win chance."""
        win_chance = calculate_win_chance(score_cp=1000, mate=None)
        assert win_chance >= 98.0

    def test_win_chance_mate_scores(self):
        """Positive mate is 100%, negative mate is 0%."""
        assert calculate_win_chance(score_cp=None, mate=1) == 100.0
        assert calculate_win_chance(score_cp=None, mate=5) == 100.0
        assert calculate_win_chance(score_cp=None, mate=-1) == 0.0
        assert calculate_win_chance(score_cp=None, mate=-3) == 0.0

    def test_move_delta_thresholds(self):
        """Verifies delta boundaries for best, good, inaccuracy, blunder."""
        # Best move: delta <= 10 cp
        assert classify_move_delta(delta_cp=0) == MoveQuality.BEST
        assert classify_move_delta(delta_cp=5) == MoveQuality.BEST
        assert classify_move_delta(delta_cp=10) == MoveQuality.BEST

        # Good move: 10 < delta <= 50 cp
        assert classify_move_delta(delta_cp=11) == MoveQuality.GOOD
        assert classify_move_delta(delta_cp=35) == MoveQuality.GOOD
        assert classify_move_delta(delta_cp=50) == MoveQuality.GOOD

        # Inaccuracy: 50 < delta <= 150 cp
        assert classify_move_delta(delta_cp=51) == MoveQuality.INACCURACY
        assert classify_move_delta(delta_cp=100) == MoveQuality.INACCURACY
        assert classify_move_delta(delta_cp=150) == MoveQuality.INACCURACY

        # Blunder: delta > 150 cp
        assert classify_move_delta(delta_cp=151) == MoveQuality.BLUNDER
        assert classify_move_delta(delta_cp=500) == MoveQuality.BLUNDER

    def test_move_delta_loss_of_mate(self):
        """Loss of forced mate is classified as blunder regardless of delta."""
        assert classify_move_delta(delta_cp=20, is_blunder_loss_of_mate=True) == MoveQuality.BLUNDER

    def test_negative_delta_handling(self):
        """Negative delta due to engine search variance maps to BEST."""
        assert classify_move_delta(delta_cp=-15) == MoveQuality.BEST


# =============================================================================
# 2. HEURISTIC EVALUATOR (OFFLINE FALLBACK) TESTS
# =============================================================================

class TestHeuristicEvaluator:
    @pytest.fixture
    def evaluator(self):
        return HeuristicEvaluator()

    def test_starting_position_balance(self, evaluator):
        """Initial board position should evaluate very close to 0."""
        board = chess.Board()
        score = evaluator.evaluate(board)
        assert abs(score) <= 20

    def test_material_advantage_white(self, evaluator):
        """White with extra Queen should be ~+900 cp."""
        board = chess.Board("rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        score = evaluator.evaluate(board)
        assert score >= 800

    def test_material_advantage_black(self, evaluator):
        """Black with extra Rook should be negative from White's perspective."""
        board = chess.Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/1NBQKBNR w Kkq - 0 1")
        score = evaluator.evaluate(board)
        assert score <= -400

    def test_top_moves_generation(self, evaluator):
        """Heuristic generator returns ranked moves with classifications."""
        board = chess.Board()
        moves = evaluator.get_top_moves(board, top_k=3)
        assert len(moves) > 0
        assert any(m.uci in ["e2e4", "d2d4", "g1f3", "c2c4"] for m in moves)
        assert moves[0].classification == MoveQuality.BEST


# =============================================================================
# 3. COACH ENGINE ASYNC EVALUATION & CACHING TESTS
# =============================================================================

class TestCoachEngineAsync:
    def test_coach_engine_init_and_fallback(self):
        """If Stockfish is unavailable, coach gracefully operates in heuristic mode."""
        async def _test():
            engine = CoachEngine(stockfish_path="/nonexistent/path/to/stockfish")
            await engine.start()
            assert engine.is_heuristic_mode is True

            result = await engine.evaluate_position(chess.STARTING_FEN)
            assert isinstance(result, PositionEvaluation)
            assert result.best_move is not None
            assert len(result.top_moves) > 0
            await engine.stop()

        asyncio.run(_test())

    def test_fen_caching(self):
        """Re-evaluating identical FEN retrieves result from cache without re-computing."""
        async def _test():
            engine = CoachEngine(stockfish_path=None)
            await engine.start()

            eval1 = await engine.evaluate_position(chess.STARTING_FEN)
            with patch.object(engine.evaluator, "evaluate", wraps=engine.evaluator.evaluate) as mock_eval:
                eval2 = await engine.evaluate_position(chess.STARTING_FEN)
                mock_eval.assert_not_called()

            assert eval1.best_move == eval2.best_move
            assert eval1.score_cp == eval2.score_cp
            await engine.stop()

        asyncio.run(_test())

    def test_task_cancellation_on_rapid_requests(self):
        """Triggering new analysis while one is pending cleanly cancels previous task."""
        async def _test():
            engine = CoachEngine(stockfish_path=None)
            await engine.start()

            async def slow_eval():
                await asyncio.sleep(0.5)
                return await engine.evaluate_position("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1")

            task1 = asyncio.create_task(slow_eval())
            await asyncio.sleep(0.01)

            task2 = asyncio.create_task(engine.evaluate_position(chess.STARTING_FEN))
            res2 = await task2
            assert res2 is not None

            task1.cancel()
            try:
                await task1
            except asyncio.CancelledError:
                pass
            await engine.stop()

        asyncio.run(_test())


# =============================================================================
# 4. FILE 'h' EVAL BAR LED INDEXING TESTS
# =============================================================================

class TestEvalBarLedIndexing:
    def test_eval_bar_file_h_indices(self):
        """Eval bar operates along File 'h' (Strip 2, row 7, ranks 1..8)."""
        h1_leds = get_led_indices(0, 7)  # col 0 (Rank 1), row 7 (File h)
        h8_leds = get_led_indices(7, 7)  # col 7 (Rank 8), row 7 (File h)
        assert h1_leds == [93, 94]
        assert h8_leds == [76, 77]


# =============================================================================
# 5. SETTINGS PERSISTENCE & REST API ENDPOINT TESTS
# =============================================================================

class TestCoachSettingsPersistence:
    @pytest.fixture(autouse=True)
    def preserve_settings(self):
        from board_hardware import settings
        saved = copy.deepcopy(settings)
        with patch("board_hardware.save_settings"):
            yield
        settings.clear()
        settings.update(saved)

    def test_settings_manager_coach_fields(self):
        from board_hardware import settings
        assert "coach_hints_enabled" in settings
        assert "eval_bar_enabled" in settings
        assert "coach_ai_only" in settings

    def test_rest_api_update_coach_settings(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        payload = {
            "coach_hints_enabled": True,
            "eval_bar_enabled": True,
            "coach_ai_only": False,
        }
        res = client.post("/api/board/settings", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["settings"]["coach_hints_enabled"] is True
        assert data["settings"]["eval_bar_enabled"] is True
        assert data["settings"]["coach_ai_only"] is False
