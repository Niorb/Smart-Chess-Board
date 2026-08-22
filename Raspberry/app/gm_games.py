"""
app/gm_games.py

Curated library of historical Grandmaster masterpieces for the "Master Game Time Machine" mode.
Includes game metadata, move sequences, key decision plys, and educational annotations.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GMGame:
    id: str
    title: str
    event: str
    year: int
    white: str
    white_elo: str | None
    black: str
    black_elo: str | None
    result: str
    description: str
    eco: str
    opening: str
    moves: list[str]  # UCI format e.g. ["e2e4", "e7e5", ...]
    key_plys: list[int] = field(default_factory=list)  # Ply indices (0-based) where user is quizzed
    annotations: dict[int, str] = field(default_factory=dict)  # Ply index -> commentary text

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "event": self.event,
            "year": self.year,
            "white": self.white,
            "white_elo": self.white_elo,
            "black": self.black,
            "black_elo": self.black_elo,
            "result": self.result,
            "description": self.description,
            "eco": self.eco,
            "opening": self.opening,
            "moves_count": len(self.moves),
            "key_plys": self.key_plys,
            "annotations": self.annotations,
        }


GM_GAMES_DATABASE: list[GMGame] = [
    GMGame(
        id="kasparov_topalov_1999",
        title="Kasparov's Immortal",
        event="Hoogovens Wijk aan Zee",
        year=1999,
        white="Garry Kasparov",
        white_elo="2812",
        black="Veselin Topalov",
        black_elo="2700",
        result="1-0",
        description="Considered by many the greatest game of chess ever played, featuring Kasparov's legendary 24. Rxd4!! rook sacrifice that initiated an unrelenting King hunt across the entire board.",
        eco="B07",
        opening="Pirc Defence",
        moves=[
            "e2e4", "d7d6", "d2d4", "g8f6", "b1c3", "g7g6", "c1e3", "f8g7", "d1d2", "c7c6",
            "f2f3", "b7b5", "g1e2", "b8d7", "e3h6", "g7h6", "d2h6", "c8b7", "a2a3", "e7e5",
            "e1c1", "d8e7", "c1b1", "a7a6", "e2c1", "e8c8", "c1b3", "e5d4", "d1d4", "c6c5",
            "d4d1", "d7b6", "g2g3", "c8b8", "b3a5", "b7a8", "f1h3", "d6d5", "h6f4", "b8a7",
            "h1e1", "d5d4", "c3d5", "b6d5", "e4d5", "e7d6", "d1d4", "c5d4", "e1e7", "a7b6",
            "f4d4", "b6a5", "b2b4", "a5a4", "d4c3", "d6d5", "e7a7", "a8b7", "a7b7", "d5c4",
            "c3f6", "a4a3", "f6a6", "a3b4", "c2c3", "b4c3", "a6a1", "c3d2", "a1b2", "d2d1",
            "h3f1", "d8d2", "b7d7", "d2d7", "f1c4", "b5c4", "b2h8",
        ],
        key_plys=[46, 48, 50, 52, 56],  # 24. Rxd4!!, 25. Re7+!!, 26. Qxd4+, 27. b4+, 29. Ra7!
        annotations={
            0: "Kasparov opens with 1. e4 in round 4 at Wijk aan Zee 1999.",
            46: "Move 24. White plays the astonishing 24. Rxd4!! sacrificing the rook to shatter Black's central fortress!",
            48: "Move 25. 25. Re7+!! A second consecutive rook sacrifice drawing the Black King into the open ocean.",
            52: "Move 27. 27. b4+! King is forced deeper into White's territory onto a4.",
            60: "Move 31. 31. Rxb7! Deflecting the Black Queen from the defense of the King.",
            76: "Final move of the recorded king hunt — Topalov resigns. A majestic chase concluded.",
        },
    ),
    GMGame(
        id="tal_botvinnik_1960",
        title="Tal's Hurricane Attack",
        event="World Championship Match (Game 6)",
        year=1960,
        white="Mikhail Botvinnik",
        white_elo="GM",
        black="Mikhail Tal",
        black_elo="GM",
        result="0-1",
        description="The Magician of Riga unleashes chaos against the methodical World Champion Botvinnik with the shocking 21... Nf4!! sacrifice, igniting a whirlwind tactical storm.",
        eco="E69",
        opening="King's Indian Defence",
        moves=[
            "c2c4", "g8f6", "g1f3", "g7g6", "g2g3", "f8g7", "f1g2", "e8g8", "d2d4", "d7d6",
            "b1c3", "b8d7", "e1g1", "e7e5", "e2e4", "c7c6", "h2h3", "d8b6", "d4d5", "c6d5",
            "c4d5", "d7c5", "f3e1", "c8d7", "e1d3", "c5d3", "d1d3", "f8c8", "a1b1", "f6h5",
            "c1e3", "b6b4", "d3e2", "c8c4", "f1c1", "a8c8", "g2f1", "f7f5", "e4f5", "d7f5",
            "b1a1", "h5f4", "g3f4", "e5f4", "e3a7", "g7e5", "f2f3", "c4d4", "c1d1", "c8c3",
            "b2c3", "b4c3", "a1c1", "c3a3", "a7d4", "e5d4", "g1h1", "d4e3", "c1c7", "a3b4",
            "c7e7", "b4c3", "e7d7", "f5d7", "d1b1", "d7f5", "b1b3", "c3c5", "e2b2", "c5d5",
            "b3b7", "e3d4", "b2d2", "d5f3", "f1g2", "f3e3", "d2d1", "d4e5", "d1e1", "e3g3",
        ],
        key_plys=[41, 45, 51, 63],  # 21... Nf4!!, 23... Be5, 26... c8c3!, 32... Bd7
        annotations={
            0: "Botvinnik opens with 1. c4 in Moscow for Game 6 of the 1960 World Championship.",
            41: "Move 21. Black shocks the chess world with 21... Nf4!! sacrificing the Knight directly into White's Kingside.",
            45: "Move 23... Be5! Refusing to recapture immediately, Tal prioritizes maximum board dynamic pressure.",
            51: "Move 26... R8xc3! An exchange sacrifice blowing open the long diagonal.",
            79: "Black's connected passed pawns and dominant bishops seal the victory.",        },
    ),
    GMGame(
        id="fischer_byrne_1956",
        title="The Game of the Century",
        event="Rosenwald Memorial Tournament",
        year=1956,
        white="Donald Byrne",
        white_elo="IM",
        black="Bobby Fischer",
        black_elo="13-yr-old",
        result="0-1",
        description="At just 13 years old, future World Champion Bobby Fischer uncorked the breathtaking 17... Be6!! Queen sacrifice against Donald Byrne, creating an eternal masterpiece of coordination.",
        eco="D92",
        opening="Grünfeld Defence",
        moves=[
            "g1f3", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7", "d2d4", "e8g8", "c1f4", "d7d5",
            "d1b3", "d5c4", "b3c4", "c7c6", "e2e4", "b8d7", "a1d1", "d7b6", "c4c5", "c8g4",
            "f4g5", "b6a4", "c5a3", "a4c3", "b2c3", "f6e4", "g5e7", "d8b6", "f1c4", "e4c3",
            "e7c5", "f8e8", "e1f1", "g4e6", "c5b6", "e6c4", "f1g1", "c3e2", "g1f1", "e2d4",
            "f1g1", "d4e2", "g1f1", "e2c3", "f1g1", "a7b6", "a3b4", "a8a4", "b4b6", "c3d1",
            "h2h3", "a4a2", "g1h2", "d1f2", "h1e1", "e8e1", "b6d8", "g7f8", "f3e1", "c4d5",
            "e1f3", "f2e4", "d8b8", "b7b5", "h3h4", "h7h5", "f3e5", "g8g7", "h2g1", "f8c5",
            "g1f1", "e4g3", "f1e1", "c5b4", "e1d1", "d5b3", "d1c1", "g3e2", "c1b1", "e2c3",
            "b1c1", "a2c2",
        ],
        key_plys=[23, 27, 33, 35, 41],  # 12... Na4!, 14... Nxc3!, 17... Be6!!, 18... Bxc4+, 21... axb6
        annotations={
            0: "Donald Byrne vs 13-year-old Bobby Fischer at the Marshall Chess Club in NYC.",
            23: "Move 12. Black plays 12... Na4! attacking the White Queen and exploiting pin on c3.",
            33: "Move 17. 17... Be6!! Fischer leaves his Queen completely undefended in an immortal combination!",
            35: "Move 18. 18... Bxc4+ White grabs the Queen, but Black's windmilling minor pieces dominate the board.",
            81: "41... Rc2# Checkmate! The minor piece windmill delivers pure poetry.",
        },
    ),
    GMGame(
        id="morphy_opera_1858",
        title="Morphy's Opera Game",
        event="Paris Opera House",
        year=1858,
        white="Paul Morphy",
        white_elo="Master",
        black="Duke of Brunswick & Count Isouard",
        black_elo="Consultants",
        result="1-0",
        description="Played in an opera box during a performance of Bellini's Norma, Morphy demonstrates the absolute perfection of rapid piece development, open lines, and an unstoppable mating net.",
        eco="C41",
        opening="Philidor Defence",
        moves=[
            "e2e4", "e7e5", "g1f3", "d7d6", "d2d4", "c8g4", "d4e5", "g4f3", "d1f3", "d6e5",
            "f1c4", "g8f6", "f3b3", "d8e7", "b1c3", "c7c6", "c1g5", "b7b5", "c3b5", "c6b5",
            "c4b5", "b8d7", "e1c1", "a8d8", "d1d7", "d8d7", "h1d1", "e7e6", "b5d7", "f6d7",
            "b3b8", "d7b8", "d1d8",
        ],
        key_plys=[16, 20, 24, 28, 30],  # 9. Bg5!, 11. Nxb5!, 13. Rxd7!, 15. Bxd7+, 16. Qb8+!!
        annotations={
            0: "Paul Morphy takes the White pieces at the Italian Opera House in Paris.",
            16: "Move 9. 9. Bg5! Pins the Knight and prevents Black from castling.",
            20: "Move 11. 11. Nxb5! Morphy sacrifices a piece to rip open lines against the uncastled King.",
            24: "Move 13. 13. Rxd7! Exchanging defense down to the bone.",
            30: "Move 16. 16. Qb8+!! A glorious Queen deflection sacrifice followed by 17. Rd8# checkmate!",
        },
    ),
    GMGame(
        id="anderssen_immortal_1851",
        title="The Immortal Game",
        event="London Chess Tournament Casual",
        year=1851,
        white="Adolf Anderssen",
        white_elo="Master",
        black="Lionel Kieseritzky",
        black_elo="Master",
        result="1-0",
        description="Anderssen gives up a bishop, both rooks, and his queen to execute a flawless checkmate with his three remaining minor pieces—the epitome of 19th-century Romantic chess.",
        eco="C33",
        opening="King's Gambit Accepted",
        moves=[
            "e2e4", "e7e5", "f2f4", "e5f4", "f1c4", "d8h4", "e1f1", "b7b5", "c4b5", "g8f6",
            "g1f3", "h4h6", "d2d3", "f6h5", "f3h4", "h6g5", "h4f5", "c7c6", "g2g4", "h5f6",
            "h1g1", "c6b5", "h2h4", "g5g6", "h4h5", "g6g5", "d1f3", "f6g8", "c1f4", "g5f6",
            "b1c3", "f8c5", "c3d5", "f6b2", "f4d6", "c5g1", "e4e5", "b2a1", "f1e2", "b8a6",
            "f5g7", "e8d8", "f3f6", "g8f6", "d6e7",
        ],
        key_plys=[36, 40, 42, 44],  # 19. e5!, 21. Nxg7+, 22. Qf6+!!, 23. Be7#
        annotations={
            0: "Adolf Anderssen vs Lionel Kieseritzky at the Simpson's-in-the-Strand in London 1851.",
            36: "Move 19. 19. e5! Cutting off Black's Queen from the defense of g7 and e7.",
            40: "Move 21. 21. Nxg7+ Kd8 King is forced into the mating corner.",
            42: "Move 22. 22. Qf6+!! Queen sacrifice forcing Black's knight to recapture.",
            44: "23. Be7# Checkmate! All 3 remaining minor pieces deliver the coup de grâce.",
        },
    ),
    GMGame(
        id="carlsen_anand_2013",
        title="Carlsen's Python Squeeze",
        event="World Championship Match (Game 9)",
        year=2013,
        white="Viswanathan Anand",
        white_elo="2775",
        black="Magnus Carlsen",
        black_elo="2870",
        result="0-1",
        description="The modern era's defining masterpiece: Anand launches an all-out kingside assault, but Carlsen defends with laser precision before pushing his b-pawn to queen in 28 moves.",
        eco="E25",
        opening="Nimzo-Indian Defence",
        moves=[
            "d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8b4", "f2f3", "d7d5", "a2a3", "b4c3",
            "b2c3", "c7c5", "c4d5", "e6d5", "e2e3", "c5c4", "g1e2", "b8c6", "g2g4", "e8g8",
            "f1g2", "c6a5", "e1g1", "a5b3", "a1a2", "b7b5", "e2g3", "a7a5", "g4g5", "f6e8",
            "e3e4", "b3c1", "d1c1", "a8a6", "e4e5", "e8c7", "f3f4", "b5b4", "a3b4", "a5b4",
            "a2a6", "c7a6", "f4f5", "b4b3", "c1f4", "a6c7", "f5f6", "g7g6", "f4h4", "c7e8",
            "h4h6", "b3b2", "f1f4", "b2b1q", "g3f1", "b1e1",
        ],
        key_plys=[35, 41, 47, 51],  # 18... Nxc1, 21... b4!, 24... b3!, 26... b1=Q+!
        annotations={
            0: "World Chess Championship 2013, Chennai - Game 9.",
            35: "Move 18. Black eliminates White's dangerous dark-squared bishop with 18... Nxc1.",
            43: "Move 22. 22... b3! Carlsen's passed b-pawn becomes an unstoppable juggernaut.",
            53: "Move 27... b1=Q+! Carlsen promotes on b1 with check, forcing Anand's resignation after 28. Nf1 Qe1.",
            55: "28... Qe1 - White cannot stop checkmate or defend against Black's two queens.",
        },
    ),
]


def get_all_gm_games() -> list[GMGame]:
    """Returns list of all available GM historical games."""
    return GM_GAMES_DATABASE


def get_gm_game(game_id: str) -> GMGame | None:
    """Finds a GM game by ID."""
    for game in GM_GAMES_DATABASE:
        if game.id == game_id:
            return game
    return None
