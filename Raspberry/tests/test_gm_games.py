"""
tests/test_gm_games.py

Unit tests for curated historical Grandmaster games library.
"""

import pytest
import chess
from app.gm_games import get_all_gm_games, get_gm_game


def test_get_all_gm_games():
    games = get_all_gm_games()
    assert len(games) >= 6
    ids = [g.id for g in games]
    assert "kasparov_topalov_1999" in ids
    assert "tal_botvinnik_1960" in ids
    assert "fischer_byrne_1956" in ids
    assert "morphy_opera_1858" in ids
    assert "anderssen_immortal_1851" in ids
    assert "carlsen_anand_2013" in ids


def test_get_gm_game_valid():
    game = get_gm_game("kasparov_topalov_1999")
    assert game is not None
    assert game.white == "Garry Kasparov"
    assert game.black == "Veselin Topalov"
    assert game.year == 1999
    assert len(game.moves) > 40
    assert len(game.key_plys) > 0


def test_get_gm_game_invalid():
    game = get_gm_game("nonexistent_game_id")
    assert game is None


def test_gm_games_move_validity():
    """Verify that all moves in every GM game are strictly legal standard chess moves."""
    games = get_all_gm_games()
    for game in games:
        board = chess.Board()
        for idx, uci in enumerate(game.moves):
            move = chess.Move.from_uci(uci)
            assert move in board.legal_moves, f"Illegal move {uci} at ply {idx} in {game.id}"
            board.push(move)
