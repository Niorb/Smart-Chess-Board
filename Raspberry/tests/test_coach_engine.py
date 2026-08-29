"""
Raspberry/tests/test_coach_engine.py

Comprehensive unit and integration test suite for the Stockfish AI Coach,
Blunder Guard, Move Delta Classifier, Engine Recovery, File 'h' Eval Bar,
LED Highlighting, and Fair-Play enforcement.
"""

import asyncio
import os
import sys

import chess
import chess.engine
import pytest

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.coach_engine import (
    CoachEngine,
    CoachEngineUnavailable,
    MoveQuality,
    PositionEvaluation,
    calculate_win_chance,
    classify_move_delta,
)
from app.led_helpers import get_led_indices

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

# =============================================================================
# 3. COACH ENGINE ASYNC EVALUATION & CACHING TESTS
# =============================================================================

class TestCoachEngineAsync:
    def test_evaluate_position_requires_engine(self, fake_stockfish):
        """Evaluation runs through Stockfish; a dead engine raises CoachEngineUnavailable."""

        async def _test():
            engine = CoachEngine(stockfish_path="/usr/games/stockfish")
            await engine.start()
            result = await engine.evaluate_position(chess.STARTING_FEN)
            assert isinstance(result, PositionEvaluation)
            assert result.best_move is not None
            assert len(result.top_moves) > 0
            assert fake_stockfish.calls >= 1
            await engine.stop()

        asyncio.run(_test())

    def test_unavailable_engine_raises(self, fake_stockfish, monkeypatch):
        """When the engine cannot launch, evaluation raises instead of degrading silently."""
        import app.coach_engine as coach_module

        async def failing_popen(path):
            raise OSError("cannot spawn stockfish")

        monkeypatch.setattr(coach_module.chess.engine, "popen_uci", failing_popen)

        async def _test():
            engine = CoachEngine(stockfish_path="/nonexistent/stockfish")
            with pytest.raises(CoachEngineUnavailable):
                await engine.evaluate_position(chess.STARTING_FEN)

        asyncio.run(_test())

    def test_engine_recovery_after_failure(self, fake_stockfish, monkeypatch):
        """A crashed engine is relaunched and the retried analysis succeeds."""

        call_count = {"n": 0}


        async def _test():
            engine = CoachEngine(stockfish_path="/usr/games/stockfish")
            await engine.start()
            original_analyse = fake_stockfish.analyse

            async def crashing_analyse(board, limit, multipv=1):
                if call_count["n"] == 0:
                    call_count["n"] += 1
                    raise RuntimeError("engine died unexpectedly")
                return await original_analyse(board, limit, multipv=multipv)

            fake_stockfish.analyse = crashing_analyse
            result = await engine.evaluate_position(chess.STARTING_FEN)
            assert isinstance(result, PositionEvaluation)
            assert result.best_move is not None
            await engine.stop()

        asyncio.run(_test())

    def test_fen_caching(self, fake_stockfish):
        """Re-evaluating identical FEN retrieves result from cache without re-computing."""
        async def _test():
            engine = CoachEngine(stockfish_path="/usr/games/stockfish")

            eval1 = await engine.evaluate_position(chess.STARTING_FEN)
            calls_after_first = fake_stockfish.calls
            eval2 = await engine.evaluate_position(chess.STARTING_FEN)

            assert fake_stockfish.calls == calls_after_first
            assert eval1.best_move == eval2.best_move
            assert eval1.score_cp == eval2.score_cp

        asyncio.run(_test())

    def test_rapid_requests_do_not_cancel_inflight_analysis(self, fake_stockfish):
        """request_analysis must not cancel running tasks and must process pending FENs sequentially."""
        async def _test():
            board_a = chess.Board()
            board_b = chess.Board()
            board_b.push_san("e4")

            engine = CoachEngine(stockfish_path="/usr/games/stockfish")
            engine.request_analysis(board_a)
            first_task = engine._analysis_task
            assert first_task is not None

            engine.request_analysis(board_b)
            assert engine._analysis_task is first_task

            await first_task
            assert engine.get_cached_evaluation(board_a.fen()) is not None
            assert engine.get_cached_evaluation(board_b.fen()) is not None

        asyncio.run(_test())

    def test_rapid_lines_requests_queues_and_computes(self, fake_stockfish):
        """request_lines must not cancel running tasks and must process pending divergence FENs."""
        async def _test():
            board_a = chess.Board()
            board_b = chess.Board()
            board_b.push_san("e4")

            engine = CoachEngine(stockfish_path="/usr/games/stockfish")
            engine.request_lines(board_a)
            first_task = engine._lines_task
            assert first_task is not None

            engine.request_lines(board_b)
            assert engine._lines_task is first_task

            await first_task
            assert engine.get_cached_lines(board_b.fen()) is not None

        asyncio.run(_test())


# =============================================================================
# 4. FILE 'h' EVAL BAR LED INDEXING TESTS
# =============================================================================

class TestEvalBarLedIndexing:
    def test_eval_bar_file_h_indices(self):
        """Eval bar operates along File 'h' (row 7, ranks 1..8)."""
        h1_leds = get_led_indices(0, 7)  # col 0 (Rank 1), row 7 (File h)
        h8_leds = get_led_indices(7, 7)  # col 7 (Rank 8), row 7 (File h)
        assert h1_leds == (16, 17)
        assert h8_leds == (93, 94)


# =============================================================================
# 5. SETTINGS PERSISTENCE & REST API ENDPOINT TESTS
# =============================================================================

class TestCoachSettingsPersistence:
    def test_settings_manager_coach_fields(self):
        from board_hardware import settings
        assert "coach_hints_enabled" in settings
        assert "eval_bar_enabled" in settings
        assert "coach_ai_only" in settings

    def test_rest_api_update_coach_settings(self):
        from app.main import app
        from fastapi.testclient import TestClient

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


# =============================================================================
# 6. IS_COMPUTING TELEMETRY TESTS
# =============================================================================

class TestCoachEngineIsComputing:
    def test_is_computing_idle_returns_false(self):
        """Idle coach engine should return False for is_computing."""
        engine = CoachEngine(stockfish_path="")
        assert engine.is_computing() is False
        assert engine.is_computing("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1") is False

    def test_is_computing_with_pending_queues(self):
        """Coach engine reports is_computing True when queues or tasks are active."""
        engine = CoachEngine(stockfish_path="")
        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        clean_fen = " ".join(fen.split()[:4])

        engine._pending_analysis_queue.append(clean_fen)
        assert engine.is_computing() is True
        assert engine.is_computing(fen) is True
        assert engine.is_computing("8/8/8/8/8/8/8/8 w - - 0 1") is True

        engine._pending_analysis_queue.clear()
        engine._current_lines_fen = clean_fen
        assert engine.is_computing(fen) is True
        assert engine.is_computing() is True
