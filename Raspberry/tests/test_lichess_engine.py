import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure parent directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.lichess_engine import (
    LichessEngine,
    format_clock_ms,
    parse_time_control,
)


def test_parse_time_control():
    assert parse_time_control("10+0") == (10, 0)
    assert parse_time_control("3+2") == (3, 2)
    assert parse_time_control("15+10") == (15, 10)
    assert parse_time_control("1+0") == (1, 0)
    assert parse_time_control("5+3") == (5, 3)
    assert parse_time_control("10 min") == (10, 0)
    assert parse_time_control("3 min") == (3, 0)
    assert parse_time_control("15 | 10") == (15, 10)
    assert parse_time_control("3 | 2") == (3, 2)
    assert parse_time_control("") == (10, 0)
    assert parse_time_control(None) == (10, 0)


def test_format_clock_ms():
    assert format_clock_ms(600000) == "10:00"
    assert format_clock_ms(185000) == "3:05"
    assert format_clock_ms(45000) == "45.0s"
    assert format_clock_ms(4560) == "4.5s"
    assert format_clock_ms(None) == "?"
    assert format_clock_ms(-10) == "?"


def test_initial_board_to_grid():
    engine = LichessEngine()
    grid = engine.get_board()

    # 8x8 grid
    assert len(grid) == 8
    assert all(len(row) == 8 for row in grid)

    # Rank 1 (index 0)
    assert grid[0] == ["R", "N", "B", "Q", "K", "B", "N", "R"]
    # Rank 2 (index 1)
    assert grid[1] == ["P"] * 8
    # Rank 3-6 (index 2-5)
    for r in range(2, 6):
        assert grid[r] == ["."] * 8
    # Rank 7 (index 6)
    assert grid[6] == ["p"] * 8
    # Rank 8 (index 7)
    assert grid[7] == ["r", "n", "b", "q", "k", "b", "n", "r"]


def test_apply_moves_and_game_metrics():
    engine = LichessEngine()
    engine._apply_moves("e2e4 e7e5 g1f3")

    assert engine.game_info["turn"] == "black"
    assert engine.game_info["last_move"] == "g1f3"
    assert engine.game_info["is_check"] is False
    assert "b8c6" in engine.game_info["legal_moves"]

    grid = engine.get_board()
    # e4 is rank 4 (index 3), file e (index 4)
    assert grid[3][4] == "P"
    # e2 is now empty (rank 2, index 1, file e index 4)
    assert grid[1][4] == "."


def test_check_and_game_over_detection():
    engine = LichessEngine()
    # Scholar's Mate
    engine._apply_moves("e2e4 e7e5 d1h5 b8c6 f1c4 g8f6 h5f7")

    assert engine.game_info["is_check"] is True
    assert engine.board.is_checkmate() is True
    payload = engine.get_game_payload()
    assert payload["is_check"] is True
    assert payload["is_game_over"] is True


def test_handle_game_full_event():
    engine = LichessEngine()
    engine.username = "RobinPi"
    mock_state_mgr = MagicMock()

    event = {
        "type": "gameFull",
        "id": "testGame123",
        "rated": True,
        "speed": "blitz",
        "white": {"name": "RobinPi", "rating": 1650, "title": None},
        "black": {"name": "GrandmasterX", "rating": 2100, "title": "GM"},
        "state": {
            "moves": "e2e4 c7c5",
            "wtime": 180000,
            "btime": 180000,
            "status": "started",
        },
    }

    engine.current_game_id = "testGame123"
    engine._handle_game_full(event, mock_state_mgr)

    assert engine.my_color == "white"
    assert engine.game_info["opponent"]["username"] == "GrandmasterX"
    assert engine.game_info["opponent"]["rating"] == 2100
    assert engine.game_info["opponent"]["title"] == "GM"
    assert engine.clocks["white"] == "3:00"
    assert engine.clocks["black"] == "3:00"

    # Verify state manager digital board and clocks were synchronized
    assert mock_state_mgr.digital_state[3][4] == "P"  # e4
    assert mock_state_mgr.digital_state[4][2] == "p"  # c5
    assert mock_state_mgr.clocks == {"white": "3:00", "black": "3:00"}


def test_handle_game_full_event_ai_opponent():
    engine = LichessEngine()
    engine.username = "RobinPi"
    mock_state_mgr = MagicMock()

    event = {
        "type": "gameFull",
        "id": "aiGame456",
        "rated": False,
        "speed": "bullet",
        "white": {"name": "RobinPi", "rating": 1650},
        "black": {"aiLevel": 4},
        "state": {
            "moves": "e2e4",
            "wtime": 60000,
            "btime": 60000,
            "status": "started",
        },
    }

    engine.current_game_id = "aiGame456"
    engine._handle_game_full(event, mock_state_mgr)

    assert engine.my_color == "white"
    assert "Stockfish AI Level 4" in engine.game_info["opponent"]["username"]
    assert engine.game_info["opponent"]["title"] == "BOT"


def test_handle_game_state_event():
    engine = LichessEngine()
    engine.username = "RobinPi"
    mock_state_mgr = MagicMock()

    event = {
        "type": "gameState",
        "moves": "e2e4 e7e5 g1f3 b8c6",
        "wtime": 172000,
        "btime": 175000,
        "status": "started",
    }

    engine._handle_game_state(event, mock_state_mgr)

    assert engine.clocks["white"] == "2:52"
    assert engine.clocks["black"] == "2:55"
    assert engine.game_info["last_move"] == "b8c6"
    assert engine.game_info["turn"] == "white"
    assert mock_state_mgr.clocks == {"white": "2:52", "black": "2:55"}


def test_get_game_payload():
    engine = LichessEngine()
    engine.current_game_id = "gameXYZ"
    engine.my_color = "black"
    engine._apply_moves("e2e4")

    payload = engine.get_game_payload()
    assert payload["game_id"] == "gameXYZ"
    assert payload["turn"] == "black"
    assert payload["my_color"] == "black"
    assert payload["last_move"] == "e2e4"
    assert isinstance(payload["legal_moves"], list)
    assert len(payload["legal_moves"]) > 0
    assert payload["is_check"] is False
    assert payload["is_game_over"] is False


def test_seek_routing_under_8_mins_to_ai():
    async def _test():
        engine = LichessEngine()
        mock_state_mgr = MagicMock()

        with patch.object(engine, "challenge_ai", new_callable=AsyncMock) as mock_challenge:
            mock_challenge.return_value = True

            # 3+0 = 180s (< 480s) -> routes to AI
            await engine.seek(mock_state_mgr, time_control="3+0", opponent="auto", ai_level=4)
            mock_challenge.assert_called_once_with(
                mock_state_mgr,
                level=4,
                time_mins=3,
                inc_secs=0,
                color="random",
            )

            mock_challenge.reset_mock()
            # 1+0 = 60s (< 480s) -> routes to AI
            await engine.seek(mock_state_mgr, time_control="1+0", opponent="auto", ai_level=2)
            mock_challenge.assert_called_once_with(
                mock_state_mgr,
                level=2,
                time_mins=1,
                inc_secs=0,
                color="random",
            )
    asyncio.run(_test())


def test_seek_routing_over_8_mins_to_human():
    async def _test():
        engine = LichessEngine()
        mock_state_mgr = MagicMock()

        with patch.object(engine, "challenge_ai", new_callable=AsyncMock) as mock_challenge, \
             patch.object(engine, "_seek_and_stream", new_callable=AsyncMock) as mock_seek_stream:

            # 10+0 = 600s (>= 480s) -> routes to live human seek
            await engine.seek(mock_state_mgr, time_control="10+0", opponent="auto")
            mock_challenge.assert_not_called()
            assert mock_state_mgr.game_status == "SEEKING"
    asyncio.run(_test())


def test_seek_routing_explicit_opponent_mode():
    async def _test():
        engine = LichessEngine()
        mock_state_mgr = MagicMock()

        with patch.object(engine, "challenge_ai", new_callable=AsyncMock) as mock_challenge:
            mock_challenge.return_value = True

            # 10+0 with explicit opponent="ai" -> routes to AI
            await engine.seek(mock_state_mgr, time_control="10+0", opponent="ai", ai_level=5)
            mock_challenge.assert_called_once_with(
                mock_state_mgr,
                level=5,
                time_mins=10,
                inc_secs=0,
                color="random",
            )
    asyncio.run(_test())


def test_seek_with_rating_range():
    async def _test():
        engine = LichessEngine()
        mock_state_mgr = MagicMock()

        with patch.object(engine, "_seek_and_stream", new_callable=AsyncMock) as mock_seek:
            await engine.seek(
                mock_state_mgr,
                time_control="15+10",
                opponent="human",
                rating_range="1400-1800",
            )
            mock_seek.assert_called_once_with(
                mock_state_mgr,
                15,
                10,
                False,
                "random",
                rating_range="1400-1800",
            )
    asyncio.run(_test())


def test_event_stream_task_management():
    async def _test():
        engine = LichessEngine()
        mock_state_mgr = MagicMock()

        with patch.object(engine, "get_account", new_callable=AsyncMock) as mock_get_acct:
            mock_get_acct.return_value = {"authenticated": True, "username": "TestPlayer", "rating": 1500}
            with patch.object(engine, "_listen_event_stream", new_callable=AsyncMock) as mock_listen:
                await engine.start(state_manager=mock_state_mgr)
                assert engine.is_running is True
                assert engine._event_stream_task is not None

                await engine.stop()
                assert engine.is_running is False
    asyncio.run(_test())
