"""
conftest.py - Global pytest configuration and test harness isolation.

Strictly protects the physical board configuration file (board_settings.json)
from being overwritten or modified during test execution by sandboxing
BOARD_SETTINGS_PATH in a temporary directory for all test runs.
"""

import copy
import os
import tempfile

import chess
import pytest


class FakeStockfishProtocol:
    """
    Deterministic in-process stand-in for the Stockfish UCI protocol.

    Returns multi-PV info dicts built with real chess.engine score types so all
    production parsing code paths run unchanged. Scores decay by alphabetical
    move order, producing stable best moves, varied classifications, and
    guaranteed blunder-tier tail moves for drill tests.
    """

    def __init__(self):
        self.calls = 0
        self.closed = False
        self.score_ladder_cp = [25, 5, -10, -35, -70, -120, -190, -280]

    async def configure(self, options):
        pass

    async def quit(self):
        self.closed = True

    async def analyse(self, board, limit, multipv=1):
        self.calls += 1
        legal = sorted(board.legal_moves, key=lambda m: m.uci())
        infos = []
        turn = board.turn
        for i in range(min(multipv, len(legal))):
            cp = self.score_ladder_cp[i % len(self.score_ladder_cp)]
            infos.append({
                "pv": [legal[i]],
                "score": chess.engine.PovScore(chess.engine.Cp(cp), turn),
                "depth": 12,
            })
        return infos


@pytest.fixture(autouse=True)
def fake_stockfish(monkeypatch):
    """
    Replaces Stockfish process launching with the deterministic fake protocol for
    every test, making the coach/analysis suite fast and binary-independent while
    exercising the real evaluation code paths.
    """
    from app import coach_engine as coach_module

    protocol = FakeStockfishProtocol()

    async def fake_popen_uci(path):
        return (object(), protocol)

    monkeypatch.setattr(chess.engine, "popen_uci", fake_popen_uci)
    monkeypatch.setattr(
        coach_module.CoachEngine,
        "_discover_stockfish",
        lambda self: "/usr/games/stockfish",
    )

    # Reset the global singleton between tests
    coach_module.coach_engine._engine = None
    coach_module.coach_engine._analysis_task = None
    coach_module.coach_engine._pending_analysis_fen = None
    coach_module.coach_engine._lines_task = None
    coach_module.coach_engine._pending_lines_fen = None
    coach_module.coach_engine._cache.clear()
    coach_module.coach_engine._lines_cache.clear()
    yield protocol
    # Ensure no background task leaks into the next test
    for task in (coach_module.coach_engine._analysis_task, coach_module.coach_engine._lines_task):
        if task and not task.done():
            task.cancel()


@pytest.fixture(autouse=True, scope="session")
def isolate_board_settings_file_globally():
    """
    Redirects BOARD_SETTINGS_PATH to an isolated temporary file for the entire test session.
    Guarantees that no test run can EVER touch or overwrite the real board_settings.json.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_settings_file = os.path.join(tmpdir, "board_settings_test.json")
        old_env = os.environ.get("BOARD_SETTINGS_PATH")
        os.environ["BOARD_SETTINGS_PATH"] = temp_settings_file
        try:
            yield temp_settings_file
        finally:
            if old_env is not None:
                os.environ["BOARD_SETTINGS_PATH"] = old_env
            else:
                os.environ.pop("BOARD_SETTINGS_PATH", None)


@pytest.fixture(autouse=True)
def isolate_board_settings_dict_per_test():
    """
    Snapshots the global board_hardware.settings dictionary before each test
    and cleanly restores factory defaults or snapshot state after each test.
    """
    try:
        from board_hardware import get_default_settings, settings
        # Start each test with clean default settings
        clean_defaults = get_default_settings()
        settings.clear()
        settings.update(clean_defaults)
        saved_settings = copy.deepcopy(clean_defaults)
    except ImportError:
        saved_settings = None

    yield

    if saved_settings is not None:
        try:
            from board_hardware import settings
            settings.clear()
            settings.update(saved_settings)
        except ImportError:
            pass
