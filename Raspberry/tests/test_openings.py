"""
tests/test_openings.py

Unit tests for Opening Classifier & Candidate Book Move Engine (app/openings.py).
Tests ECO classification, variation detection, candidate move extraction,
mainline/sideline categorization, square-specific lookups, novelty detection,
and serialization integrity.
"""

import chess
from app.openings import (
    get_book_moves_for_square,
    get_opening_info,
    lookup_opening_by_moves,
)


def test_starting_position_opening_info():
    board = chess.Board()
    info = get_opening_info(board)
    assert info.eco == "A00"
    assert info.name == "Starting Position"
    assert info.variation is None
    assert info.ply == 0
    assert not info.out_of_book
    assert info.novelty_ply is None
    assert len(info.book_moves) > 0

    # e4 and d4 should be candidate book moves with mainline classification
    move_ucis = [bm.uci for bm in info.book_moves]
    assert "e2e4" in move_ucis
    assert "d2d4" in move_ucis

    e4_cand = next(bm for bm in info.book_moves if bm.uci == "e2e4")
    assert e4_cand.classification == "mainline"
    assert e4_cand.from_coord == (4, 1)  # e2 -> col 4, row 1
    assert e4_cand.to_coord == (4, 3)    # e4 -> col 4, row 3


def test_sicilian_defense_classification():
    # 1. e4 c5 -> Sicilian Defense (B20)
    info = lookup_opening_by_moves(["e2e4", "c7c5"])
    assert info.eco == "B20"
    assert info.name == "Sicilian Defense"
    assert info.variation is None
    assert info.ply == 2
    assert not info.out_of_book


def test_sicilian_najdorf_english_attack():
    # 1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 6. Be3 e5 7. Nb3 Be6 8. f3
    moves = [
        "e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4",
        "f3d4", "g8f6", "b1c3", "a7a6", "c1e3", "e7e5",
        "d4b3", "c8e6", "f2f3"
    ]
    info = lookup_opening_by_moves(moves)
    assert info.eco == "B90"
    assert info.name == "Sicilian Defense"
    assert info.variation == "Najdorf, English Attack"
    assert info.ply == 15
    assert not info.out_of_book


def test_italian_game_classification():
    # 1. e4 e5 2. Nf3 Nc6 3. Bc4
    moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]
    info = lookup_opening_by_moves(moves)
    assert info.eco == "C50"
    assert info.name == "Italian Game"
    assert info.ply == 5


def test_ruy_lopez_berlin_defense():
    # 1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6
    moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "g8f6"]
    info = lookup_opening_by_moves(moves)
    assert info.eco == "C65"
    assert info.name == "Ruy Lopez"
    assert info.variation == "Berlin Defense"


def test_french_defense_advance_variation():
    # 1. e4 e6 2. d4 d5 3. e5 c5 4. c3 Nc6 5. Nf3
    moves = ["e2e4", "e7e6", "d2d4", "d7d5", "e4e5", "c7c5", "c2c3", "b8c6", "g1f3"]
    info = lookup_opening_by_moves(moves)
    assert info.eco == "C02"
    assert info.name == "French Defense"
    assert info.variation == "Advance Variation"


def test_caro_kann_advance_variation():
    # 1. e4 c6 2. d4 d5 3. e5 Bf5
    moves = ["e2e4", "c7c6", "d2d4", "d7d5", "e4e5", "c8f5"]
    info = lookup_opening_by_moves(moves)
    assert info.eco == "B12"
    assert info.name == "Caro-Kann Defense"
    assert info.variation == "Advance Variation"


def test_kings_indian_defense_mar_del_plata():
    # 1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6 5. Nf3 O-O 6. Be2 e5 7. O-O Nc6 8. d5 Ne7
    moves = [
        "d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7",
        "e2e4", "d7d6", "g1f3", "e8g8", "f1e2", "e7e5",
        "e1g1", "b8c6", "d4d5", "c6e7"
    ]
    info = lookup_opening_by_moves(moves)
    assert info.eco == "E97"
    assert info.name == "King's Indian Defense"
    assert info.variation == "Mar del Plata"


def test_get_book_moves_for_square():
    board = chess.Board()
    # Lift White King's pawn at e2 (col 4, row 1)
    e2_moves = get_book_moves_for_square(board, 4, 1)
    assert len(e2_moves) >= 1
    assert any(bm.uci == "e2e4" for bm in e2_moves)

    # Lift Queen's Knight at b1 (col 1, row 0)
    b1_moves = get_book_moves_for_square(board, 1, 0)
    assert any(bm.uci == "b1c3" for bm in b1_moves)


def test_novelty_detection():
    # 1. e4 e5 2. Nf3 a6 (Rare/uncharted novelty on move 2)
    moves = ["e2e4", "e7e5", "g1f3", "a7a6"]
    info = lookup_opening_by_moves(moves)
    assert info.out_of_book
    assert info.novelty_ply == 4
    assert info.novelty_move == "a7a6"
    assert info.eco == "C40"  # Last known was King's Knight Opening


def test_opening_info_to_dict():
    info = lookup_opening_by_moves(["e2e4", "c7c5"])
    d = info.to_dict()
    assert d["eco"] == "B20"
    assert d["name"] == "Sicilian Defense"
    assert d["ply"] == 2
    assert isinstance(d["book_moves"], list)
    if d["book_moves"]:
        bm = d["book_moves"][0]
        assert "uci" in bm
        assert "san" in bm
        assert "from_coord" in bm
        assert "to_coord" in bm
        assert "classification" in bm
