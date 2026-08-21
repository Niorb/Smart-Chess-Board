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


def test_get_game_payload_includes_last_move_is_capture():
    """
    Verify get_game_payload() includes 'last_move_is_capture'
    for initial state, quiet moves, standard piece captures, and en passant.
    """
    engine = LichessEngine()
    engine.current_game_id = "testCaptureGame"
    engine.my_color = "white"

    # 1. Initial position (no moves)
    payload_initial = engine.get_game_payload()
    assert "last_move_is_capture" in payload_initial
    assert payload_initial["last_move_is_capture"] is False
    assert payload_initial["last_move"] is None

    # 2. Quiet move: 1. e4
    engine._apply_moves("e2e4")
    payload_quiet = engine.get_game_payload()
    assert payload_quiet["last_move"] == "e2e4"
    assert payload_quiet["last_move_is_capture"] is False

    # 3. Standard piece capture: 1. e4 d5 2. exd5
    engine._apply_moves("e2e4 d7d5 e4d5")
    payload_capture = engine.get_game_payload()
    assert payload_capture["last_move"] == "e4d5"
    assert payload_capture["last_move_is_capture"] is True

    # 4. Another quiet move after capture: 1. e4 d5 2. exd5 Nf6
    engine._apply_moves("e2e4 d7d5 e4d5 g8f6")
    payload_quiet_2 = engine.get_game_payload()
    assert payload_quiet_2["last_move"] == "g8f6"
    assert payload_quiet_2["last_move_is_capture"] is False

    # 5. En passant capture: 1. e4 a6 2. e5 d5 3. exd6
    engine._apply_moves("e2e4 a7a6 e4e5 d7d5 e5d6")
    payload_ep = engine.get_game_payload()
    assert payload_ep["last_move"] == "e5d6"
    assert payload_ep["last_move_is_capture"] is True


def test_handle_opponent_gone_immediate_claim():
    """Verify opponentGone with claimWinInSeconds <= 0 triggers immediate victory claim."""
    async def _test():
        engine = LichessEngine()
        engine.current_game_id = "testOpponentGone1"
        engine.my_color = "white"
        mock_state_mgr = MagicMock()
        mock_state_mgr.game_status = "PLAYING"

        with patch.object(engine, "claim_victory", new_callable=AsyncMock) as mock_claim:
            mock_claim.return_value = True

            engine._handle_opponent_gone(True, 0, mock_state_mgr)

            assert engine.opponent_gone["gone"] is True
            assert engine.opponent_gone["claim_win_in"] == 0
            assert engine._auto_claim_task is not None

            await asyncio.sleep(0.01)
            mock_claim.assert_called_once_with(mock_state_mgr)
    asyncio.run(_test())


def test_handle_opponent_gone_scheduled_delayed_claim():
    """Verify opponentGone with claimWinInSeconds > 0 schedules a delayed task."""
    async def _test():
        engine = LichessEngine()
        engine.current_game_id = "testOpponentGone2"
        engine.my_color = "white"
        mock_state_mgr = MagicMock()
        mock_state_mgr.game_status = "PLAYING"

        with patch.object(engine, "claim_victory", new_callable=AsyncMock) as mock_claim, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_claim.return_value = True

            engine._handle_opponent_gone(True, 15, mock_state_mgr)

            assert engine.opponent_gone["gone"] is True
            assert engine.opponent_gone["claim_win_in"] == 15
            assert engine._auto_claim_task is not None

            await engine._auto_claim_task

            mock_sleep.assert_called_with(15)
            mock_claim.assert_called_once_with(mock_state_mgr)
    asyncio.run(_test())


def test_opponent_reconnection_cancels_auto_claim_task():
    """Verify opponent returning (gone=False) cancels pending auto-claim task and clears state."""
    async def _test():
        engine = LichessEngine()
        engine.current_game_id = "testOpponentReconnect"
        engine.my_color = "white"
        mock_state_mgr = MagicMock()
        mock_state_mgr.game_status = "PLAYING"

        with patch.object(engine, "claim_victory", new_callable=AsyncMock) as mock_claim:
            # 1. Opponent disconnects (scheduled for 20s)
            engine._handle_opponent_gone(True, 20, mock_state_mgr)
            claim_task = engine._auto_claim_task
            assert claim_task is not None
            assert engine.opponent_gone["gone"] is True
            assert engine.opponent_gone["claim_win_in"] == 20

            # 2. Opponent reconnects before timer expires
            engine._handle_opponent_gone(False, 0, mock_state_mgr)

            await asyncio.sleep(0.01)
            assert claim_task.cancelled() or claim_task.done() or (hasattr(claim_task, "cancelling") and claim_task.cancelling() > 0)
            assert engine.opponent_gone is None
            mock_claim.assert_not_called()
    asyncio.run(_test())


def test_claim_victory_http_success_and_state_updates():
    """Verify claim_victory makes POST request, sets game over, winner, idle status, and animation."""
    async def _test():
        engine = LichessEngine()
        engine.current_game_id = "claimGame123"
        engine.my_color = "white"
        mock_state_mgr = MagicMock()
        mock_state_mgr.game_status = "PLAYING"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp

            result = await engine.claim_victory(mock_state_mgr)

            assert result is True
            mock_post.assert_called_once_with("/api/board/game/claimGame123/claim-victory")
            assert engine.game_info["is_game_over"] is True
            assert engine.game_info["winner"] == "white"
            assert mock_state_mgr.game_status == "IDLE"
            mock_state_mgr.trigger_animation.assert_called_once_with("GAME_WON")
    asyncio.run(_test())


def test_claim_victory_http_failure():
    """Verify claim_victory returns False on API rejection or network error."""
    async def _test():
        engine = LichessEngine()
        engine.current_game_id = "claimFailGame"
        engine.my_color = "black"
        mock_state_mgr = MagicMock()
        mock_state_mgr.game_status = "PLAYING"

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Cannot claim victory yet"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp

            result = await engine.claim_victory(mock_state_mgr)

            assert result is False
            assert engine.game_info["is_game_over"] is False
    asyncio.run(_test())


def test_get_game_payload_includes_opponent_gone():
    """Verify get_game_payload includes opponent_gone in initial and disconnected states."""
    engine = LichessEngine()
    engine.current_game_id = "testPayloadGame"
    engine.my_color = "white"

    # 1. Normal state: opponent_gone is None
    payload_normal = engine.get_game_payload()
    assert "opponent_gone" in payload_normal
    assert payload_normal["opponent_gone"] is None

    # 2. Opponent disconnected state
    engine.opponent_gone = {"gone": True, "claim_win_in": 10}
    payload_gone = engine.get_game_payload()
    assert payload_gone["opponent_gone"] == {"gone": True, "claim_win_in": 10}

    # 3. Opponent reconnected state
    engine.opponent_gone = None
    payload_back = engine.get_game_payload()
    assert payload_back["opponent_gone"] is None


def test_auto_claim_task_cancelled_on_stop_cancel_resign_abort():
    """Verify auto claim task is cleanly cancelled across engine lifecycle operations."""
    async def _test():
        engine = LichessEngine()
        engine.current_game_id = "testCleanupGame"
        mock_state_mgr = MagicMock()

        # 1. Test cancellation on stop()
        engine.is_running = True
        t1 = asyncio.create_task(asyncio.sleep(100))
        engine._auto_claim_task = t1
        await engine.stop()
        assert engine._auto_claim_task is None
        assert t1.cancelled() or t1.done() or (hasattr(t1, "cancelling") and t1.cancelling() > 0)

        # 2. Test cancellation on cancel()
        mock_state_mgr.game_status = "PLAYING"
        t2 = asyncio.create_task(asyncio.sleep(100))
        engine._auto_claim_task = t2
        with patch.object(engine, "resign", new_callable=AsyncMock):
            await engine.cancel(mock_state_mgr)
            assert engine._auto_claim_task is None
            assert t2.cancelled() or t2.done() or (hasattr(t2, "cancelling") and t2.cancelling() > 0)

        # 3. Test cancellation on resign()
        engine.current_game_id = "testCleanupGame"
        t3 = asyncio.create_task(asyncio.sleep(100))
        engine._auto_claim_task = t3
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            await engine.resign(mock_state_mgr)
            assert engine._auto_claim_task is None
            assert t3.cancelled() or t3.done() or (hasattr(t3, "cancelling") and t3.cancelling() > 0)

        # 4. Test cancellation on abort()
        engine.current_game_id = "testCleanupGame"
        t4 = asyncio.create_task(asyncio.sleep(100))
        engine._auto_claim_task = t4
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            await engine.abort(mock_state_mgr)
            assert engine._auto_claim_task is None
            assert t4.cancelled() or t4.done() or (hasattr(t4, "cancelling") and t4.cancelling() > 0)
    asyncio.run(_test())


def test_get_user_recent_games_parsing():
    """Verify that get_user_recent_games correctly parses NDJSON stream into structured game summaries."""
    import json

    async def _test():
        engine = LichessEngine()
        engine.username = "RobiDeli"

        ndjson_data = "\n".join([
            json.dumps({
                "id": "game1",
                "rated": True,
                "speed": "blitz",
                "status": "mate",
                "winner": "white",
                "createdAt": 1718000000000,
                "players": {
                    "white": {"user": {"name": "RobiDeli", "id": "robideli"}, "rating": 1520},
                    "black": {"user": {"name": "Opponent1", "id": "opponent1", "title": "FM"}, "rating": 1580}
                },
                "opening": {"name": "Sicilian Defense: Accelerated Dragon", "eco": "B35"},
                "clock": {"initial": 180, "increment": 2},
                "moves": "e4 c5 Nf3 Nc6 d4 cxd4 Nxd4 g6"
            }),
            json.dumps({
                "id": "game2",
                "rated": False,
                "speed": "rapid",
                "status": "resign",
                "winner": "white",
                "createdAt": 1717900000000,
                "players": {
                    "white": {"aiLevel": 5},
                    "black": {"user": {"name": "RobiDeli", "id": "robideli"}, "rating": 1500}
                },
                "opening": {"name": "Queen's Gambit Declined", "eco": "D30"},
                "clock": {"initial": 600, "increment": 0},
                "moves": "d4 d5 c4 e6"
            })
        ])

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MagicMock(status_code=200, text=ndjson_data)
            games = await engine.get_user_recent_games(username="RobiDeli", max_games=10)

            assert len(games) == 2

            # Game 1 verification
            g1 = games[0]
            assert g1["id"] == "game1"
            assert g1["user_color"] == "white"
            assert g1["result"] == "win"
            assert g1["opponent"]["username"] == "Opponent1"
            assert g1["opponent"]["title"] == "FM"
            assert g1["opponent"]["rating"] == 1580
            assert g1["time_control"] == "3+2"
            assert g1["opening"]["name"] == "Sicilian Defense: Accelerated Dragon"
            assert g1["moves_uci"] == ["e2e4", "c7c5", "g1f3", "b8c6", "d2d4", "c5d4", "f3d4", "g7g6"]
            assert g1["total_plys"] == 8

            # Game 2 verification
            g2 = games[1]
            assert g2["id"] == "game2"
            assert g2["user_color"] == "black"
            assert g2["result"] == "loss"
            assert g2["opponent"]["username"] == "AI Level 5"
            assert g2["opponent"]["is_ai"] is True
            assert g2["time_control"] == "10+0"
            assert g2["moves_uci"] == ["d2d4", "d7d5", "c2c4", "e7e6"]
            assert g2["total_plys"] == 4

    asyncio.run(_test())


