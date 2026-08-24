"""
app/openings.py

High-Speed Chess Opening & ECO Classification Engine for the Smart Chess Board.
Provides instant ECO code identification (A00-E99), opening/variation classification,
move history tree traversal, novelty detection, candidate book move extraction with
coordinates and mainline/sideline tiering, and optional Polyglot (.bin) book integration.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import chess

try:
    import chess.polyglot
    POLYGLOT_AVAILABLE = True
except ImportError:
    POLYGLOT_AVAILABLE = False

logger = logging.getLogger("smart-chess-app.openings")


@dataclass(slots=True)
class BookMoveCandidate:
    """Represents a candidate opening book move from the current position."""
    uci: str
    san: str
    weight: int
    percentage: float
    classification: str  # 'mainline' | 'sideline'
    from_coord: tuple[int, int]  # (col, row) 0-indexed: col 0..7 (a..h), row 0..7 (1..8)
    to_coord: tuple[int, int]    # (col, row) 0-indexed: col 0..7 (a..h), row 0..7 (1..8)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uci": self.uci,
            "san": self.san,
            "weight": self.weight,
            "percentage": round(self.percentage, 1),
            "classification": self.classification,
            "from_coord": list(self.from_coord),
            "to_coord": list(self.to_coord),
        }


@dataclass(slots=True)
class OpeningInfo:
    """Complete opening classification and candidate moves for a board state."""
    eco: str
    name: str
    variation: str | None
    ply: int
    fen: str
    out_of_book: bool
    novelty_ply: int | None
    novelty_move: str | None
    book_moves: list[BookMoveCandidate]

    def to_dict(self) -> dict[str, Any]:
        return {
            "eco": self.eco,
            "name": self.name,
            "variation": self.variation,
            "ply": self.ply,
            "fen": self.fen,
            "out_of_book": self.out_of_book,
            "novelty_ply": self.novelty_ply,
            "novelty_move": self.novelty_move,
            "book_moves": [bm.to_dict() for bm in self.book_moves],
        }


def _move_to_coords(move: chess.Move) -> tuple[tuple[int, int], tuple[int, int]]:
    """Converts a chess.Move to ((from_col, from_row), (to_col, to_row))."""
    from_c = chess.square_file(move.from_square)
    from_r = chess.square_rank(move.from_square)
    to_c = chess.square_file(move.to_square)
    to_r = chess.square_rank(move.to_square)
    return (from_c, from_r), (to_c, to_r)


class PolyglotBookReader:
    """
    Reader for local Polyglot (.bin) opening books.
    Provides binary indexed candidate move lookups with weights and percentages.
    """
    def __init__(self, book_path: str | None = None):
        self.book_path = book_path or os.environ.get("OPENING_BOOK_PATH") or os.environ.get("POLYGLOT_BOOK_PATH")
        self._reader: Any = None
        self._init_reader()

    def _init_reader(self) -> None:
        if not POLYGLOT_AVAILABLE:
            return

        if not self.book_path:
            candidate_paths = [
                os.path.join(os.path.dirname(__file__), "books", "titans.bin"),
                os.path.join(os.path.dirname(__file__), "books", "gm2600.bin"),
                os.path.join(os.path.dirname(__file__), "books", "Performance.bin"),
                os.path.join(os.path.dirname(__file__), "books", "book.bin"),
                os.path.join(os.path.dirname(__file__), "..", "books", "titans.bin"),
                os.path.join(os.path.dirname(__file__), "..", "books", "gm2600.bin"),
                os.path.join(os.path.dirname(__file__), "..", "books", "Performance.bin"),
                os.path.join(os.path.dirname(__file__), "..", "books", "book.bin"),
                "/usr/share/games/plugins/titans.bin",
                "/usr/share/games/plugins/gm2600.bin",
                "/usr/share/games/plugins/Performance.bin",
                "/usr/share/games/plugins/book.bin",
            ]
            for p in candidate_paths:
                if os.path.exists(p) and os.path.isfile(p):
                    self.book_path = p
                    break

        if self.book_path and os.path.exists(self.book_path):
            try:
                self._reader = chess.polyglot.open_reader(self.book_path)
            except Exception as e:
                logger.warning(f"Failed to open polyglot book {self.book_path}: {e}")
                self._reader = None

    def is_available(self) -> bool:
        return self._reader is not None

    def get_entries(self, board: chess.Board) -> list[Any]:
        if not self._reader:
            return []
        try:
            return list(self._reader.find_all(board))
        except Exception:
            return []

    def get_book_moves(self, board: chess.Board) -> list[BookMoveCandidate]:
        entries = self.get_entries(board)
        if not entries:
            return []
        total_weight = sum(e.weight for e in entries)
        max_weight = max((e.weight for e in entries), default=0)
        candidates: list[BookMoveCandidate] = []
        for e in entries:
            m = e.move
            pct = round((e.weight / total_weight) * 100.0, 1) if total_weight > 0 else round(100.0 / len(entries), 1)
            is_main = (pct >= 25.0) or (e.weight == max_weight and e.weight > 0)
            classif = "mainline" if is_main else "sideline"
            from_coord, to_coord = _move_to_coords(m)
            try:
                san = board.san(m)
            except Exception:
                san = m.uci()
            candidates.append(BookMoveCandidate(
                uci=m.uci(),
                san=san,
                weight=e.weight,
                percentage=pct,
                classification=classif,
                from_coord=from_coord,
                to_coord=to_coord,
            ))
        candidates.sort(key=lambda c: (c.weight, c.percentage), reverse=True)
        return candidates

    def close(self) -> None:
        if self._reader:
            try:
                self._reader.close()
            except Exception:
                pass
            self._reader = None

    def __enter__(self) -> PolyglotBookReader:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


@dataclass
class _OpeningNode:
    eco: str
    name: str
    variation: str | None = None
    ply: int = 0
    children: dict[str, _OpeningNode] = field(default_factory=dict)
    weights: dict[str, int] = field(default_factory=dict)
    classifications: dict[str, str] = field(default_factory=dict)


# Standard opening database covering all ECO families (A00-E99)
OPENING_DEFINITIONS: list[dict[str, Any]] = [
    # --- Volume A: Flank & Irregular Openings (A00-A99) ---
    {"eco": "A00", "name": "Polish Opening", "variation": None, "moves": ["b2b4"], "weight": 15},
    {"eco": "A00", "name": "Grob Opening", "variation": None, "moves": ["g2g4"], "weight": 10},
    {"eco": "A00", "name": "Dunst Opening", "variation": None, "moves": ["b1c3"], "weight": 15},
    {"eco": "A00", "name": "Saragossa Opening", "variation": None, "moves": ["c2c3"], "weight": 10},
    {"eco": "A00", "name": "Mieses Opening", "variation": None, "moves": ["d2d3"], "weight": 10},
    {"eco": "A00", "name": "Van't Kruijs Opening", "variation": None, "moves": ["e2e3"], "weight": 10},
    {"eco": "A00", "name": "Anderssen's Opening", "variation": None, "moves": ["a2a3"], "weight": 10},
    {"eco": "A00", "name": "Hungarian Opening", "variation": None, "moves": ["g2g3"], "weight": 20},
    {"eco": "A01", "name": "Nimzo-Larsen Attack", "variation": None, "moves": ["b2b3"], "weight": 30},
    {"eco": "A01", "name": "Nimzo-Larsen Attack", "variation": "Modern Plan", "moves": ["b2b3", "e7e5", "c1b2", "b8c6"], "weight": 25},
    {"eco": "A02", "name": "Bird's Opening", "variation": None, "moves": ["f2f4"], "weight": 25},
    {"eco": "A02", "name": "Bird's Opening", "variation": "From's Gambit", "moves": ["f2f4", "e7e5", "f4e5", "d7d6"], "weight": 20},
    {"eco": "A03", "name": "Bird's Opening", "variation": "Dutch Variation", "moves": ["f2f4", "d7d5"], "weight": 25},
    {"eco": "A04", "name": "Réti Opening", "variation": None, "moves": ["g1f3"], "weight": 70, "mainline": True},
    {"eco": "A04", "name": "Réti Opening", "variation": "King's Indian Attack", "moves": ["g1f3", "g8f6", "g2g3"], "weight": 50},
    {"eco": "A05", "name": "Réti Opening", "variation": "King's Indian Setup", "moves": ["g1f3", "g8f6", "g2g3", "g7g6", "f1g2", "f8g7", "e1g1", "e8g8"], "weight": 40},
    {"eco": "A06", "name": "Réti Opening", "variation": "Old Indian Attack", "moves": ["g1f3", "d7d5", "b2b3"], "weight": 30},
    {"eco": "A07", "name": "King's Indian Attack", "variation": None, "moves": ["g1f3", "d7d5", "g2g3", "g8f6", "f1g2"], "weight": 45},
    {"eco": "A08", "name": "King's Indian Attack", "variation": "French Variation", "moves": ["g1f3", "d7d5", "g2g3", "c7c5", "f1g2", "b8c6", "e1g1", "e7e6", "d2d3", "g8f6", "b1d2"], "weight": 40},
    {"eco": "A09", "name": "Réti Opening", "variation": "Advance Variation", "moves": ["g1f3", "d7d5", "c2c4", "d5d4"], "weight": 40},
    {"eco": "A09", "name": "Réti Opening", "variation": "Accepted", "moves": ["g1f3", "d7d5", "c2c4", "d5c4"], "weight": 35},

    # English Opening (A10-A39)
    {"eco": "A10", "name": "English Opening", "variation": None, "moves": ["c2c4"], "weight": 80, "mainline": True},
    {"eco": "A10", "name": "English Opening", "variation": "Anglo-Scandinavian", "moves": ["c2c4", "d7d5"], "weight": 20},
    {"eco": "A11", "name": "English Opening", "variation": "Caro-Kann Defensive System", "moves": ["c2c4", "c7c6"], "weight": 45},
    {"eco": "A12", "name": "English Opening", "variation": "Anglo-Slav Defense", "moves": ["c2c4", "c7c6", "g1f3", "d7d5", "b2b3"], "weight": 35},
    {"eco": "A13", "name": "English Opening", "variation": "Agincourt Defense", "moves": ["c2c4", "e7e6"], "weight": 50},
    {"eco": "A14", "name": "English Opening", "variation": "Neo-Catalan", "moves": ["c2c4", "e7e6", "g1f3", "d7d5", "g2g3", "g8f6", "f1g2", "f8e7", "e1g1"], "weight": 40},
    {"eco": "A15", "name": "English Opening", "variation": "Anglo-Indian Defense", "moves": ["c2c4", "g8f6"], "weight": 60, "mainline": True},
    {"eco": "A16", "name": "English Opening", "variation": "Anglo-Grünfeld", "moves": ["c2c4", "g8f6", "b1c3", "d7d5"], "weight": 40},
    {"eco": "A17", "name": "English Opening", "variation": "Nimzo-English", "moves": ["c2c4", "g8f6", "b1c3", "e7e6", "g1f3", "f8b4"], "weight": 40},
    {"eco": "A18", "name": "English Opening", "variation": "Flohr-Mikenas Attack", "moves": ["c2c4", "g8f6", "b1c3", "e7e6", "e2e4"], "weight": 45},
    {"eco": "A20", "name": "English Opening", "variation": "King's English Variation", "moves": ["c2c4", "e7e5"], "weight": 70, "mainline": True},
    {"eco": "A22", "name": "English Opening", "variation": "Two Knights Variation", "moves": ["c2c4", "e7e5", "b1c3", "g8f6"], "weight": 60},
    {"eco": "A25", "name": "English Opening", "variation": "Closed System", "moves": ["c2c4", "e7e5", "b1c3", "b8c6", "g2g3", "g7g6", "f1g2", "f8g7"], "weight": 50},
    {"eco": "A28", "name": "English Opening", "variation": "Four Knights System", "moves": ["c2c4", "e7e5", "b1c3", "b8c6", "g1f3", "g8f6"], "weight": 55},
    {"eco": "A29", "name": "English Opening", "variation": "Four Knights, Kingside Fianchetto", "moves": ["c2c4", "e7e5", "b1c3", "b8c6", "g1f3", "g8f6", "g2g3"], "weight": 50},
    {"eco": "A30", "name": "English Opening", "variation": "Symmetrical Variation", "moves": ["c2c4", "c7c5"], "weight": 65, "mainline": True},
    {"eco": "A34", "name": "English Opening", "variation": "Symmetrical, Three Knights", "moves": ["c2c4", "c7c5", "b1c3", "g8f6", "g1f3"], "weight": 50},
    {"eco": "A36", "name": "English Opening", "variation": "Symmetrical, Ultra-Symmetrical", "moves": ["c2c4", "c7c5", "b1c3", "b8c6", "g2g3", "g7g6", "f1g2", "f8g7"], "weight": 45},

    # Queen's Pawn & Flank Defenses (A40-A99)
    {"eco": "A40", "name": "Queen's Pawn Game", "variation": None, "moves": ["d2d4"], "weight": 95, "mainline": True},
    {"eco": "A40", "name": "Queen's Pawn Game", "variation": "Englund Gambit", "moves": ["d2d4", "e7e5"], "weight": 15},
    {"eco": "A40", "name": "Queen's Pawn Game", "variation": "English Defense", "moves": ["d2d4", "e7e6", "c2c4", "b7b6"], "weight": 25},
    {"eco": "A41", "name": "Queen's Pawn Game", "variation": "Wade Defense", "moves": ["d2d4", "d7d6", "g1f3", "c8g4"], "weight": 25},
    {"eco": "A43", "name": "Old Benoni Defense", "variation": None, "moves": ["d2d4", "c7c5"], "weight": 35},
    {"eco": "A45", "name": "Trompowsky Attack", "variation": None, "moves": ["d2d4", "g8f6", "c1g5"], "weight": 50},
    {"eco": "A46", "name": "Torre Attack", "variation": None, "moves": ["d2d4", "g8f6", "g1f3", "e7e6", "c1g5"], "weight": 40},
    {"eco": "A51", "name": "Budapest Gambit", "variation": None, "moves": ["d2d4", "g8f6", "c2c4", "e7e5"], "weight": 30},
    {"eco": "A53", "name": "Old Indian Defense", "variation": None, "moves": ["d2d4", "g8f6", "c2c4", "d7d6"], "weight": 35},
    {"eco": "A57", "name": "Benko Gambit", "variation": None, "moves": ["d2d4", "g8f6", "c2c4", "c7c5", "d4d5", "b7b5"], "weight": 45},
    {"eco": "A60", "name": "Modern Benoni", "variation": None, "moves": ["d2d4", "g8f6", "c2c4", "c7c5", "d4d5", "e7e6"], "weight": 50},
    {"eco": "A80", "name": "Dutch Defense", "variation": None, "moves": ["d2d4", "f7f5"], "weight": 50},
    {"eco": "A87", "name": "Dutch Defense", "variation": "Leningrad Variation", "moves": ["d2d4", "f7f5", "c2c4", "g8f6", "g2g3", "g7g6", "f1g2", "f8g7", "g1f3", "e8g8", "e1g1", "d7d6"], "weight": 45},
    {"eco": "A96", "name": "Dutch Defense", "variation": "Classical Variation", "moves": ["d2d4", "f7f5", "c2c4", "g8f6", "g2g3", "e7e6", "f1g2", "f8e7", "g1f3", "e8g8", "e1g1", "d7d6"], "weight": 40},

    # --- Volume B: Semi-Open Games (B00-B99) ---
    {"eco": "B00", "name": "King's Pawn Game", "variation": None, "moves": ["e2e4"], "weight": 100, "mainline": True},
    {"eco": "B00", "name": "Nimzowitsch Defense", "variation": None, "moves": ["e2e4", "b8c6"], "weight": 25},
    {"eco": "B00", "name": "Owen's Defense", "variation": None, "moves": ["e2e4", "b7b6"], "weight": 20},
    {"eco": "B01", "name": "Scandinavian Defense", "variation": None, "moves": ["e2e4", "d7d5"], "weight": 55},
    {"eco": "B01", "name": "Scandinavian Defense", "variation": "Mieses-Kotroc Variation", "moves": ["e2e4", "d7d5", "e4d5", "d8d5", "b1c3", "d5a5"], "weight": 50, "mainline": True},
    {"eco": "B01", "name": "Scandinavian Defense", "variation": "Modern Variation", "moves": ["e2e4", "d7d5", "e4d5", "g8f6"], "weight": 45},
    {"eco": "B02", "name": "Alekhine's Defense", "variation": None, "moves": ["e2e4", "g8f6"], "weight": 40},
    {"eco": "B04", "name": "Alekhine's Defense", "variation": "Modern Variation", "moves": ["e2e4", "g8f6", "e4e5", "f6d5", "d2d4", "d7d6", "g1f3"], "weight": 40},
    {"eco": "B06", "name": "Modern Defense", "variation": None, "moves": ["e2e4", "g7g6"], "weight": 45},
    {"eco": "B07", "name": "Pirc Defense", "variation": None, "moves": ["e2e4", "d7d6", "d2d4", "g8f6", "b1c3", "g7g6"], "weight": 50},
    {"eco": "B09", "name": "Pirc Defense", "variation": "Austrian Attack", "moves": ["e2e4", "d7d6", "d2d4", "g8f6", "b1c3", "g7g6", "f2f4", "f8g7", "g1f3", "e8g8"], "weight": 45},

    # Caro-Kann Defense (B10-B19)
    {"eco": "B10", "name": "Caro-Kann Defense", "variation": None, "moves": ["e2e4", "c7c6"], "weight": 75, "mainline": True},
    {"eco": "B12", "name": "Caro-Kann Defense", "variation": "Advance Variation", "moves": ["e2e4", "c7c6", "d2d4", "d7d5", "e4e5", "c8f5"], "weight": 65, "mainline": True},
    {"eco": "B12", "name": "Caro-Kann Defense", "variation": "Advance, Short System", "moves": ["e2e4", "c7c6", "d2d4", "d7d5", "e4e5", "c8f5", "g1f3", "e7e6", "f1e2"], "weight": 55},
    {"eco": "B13", "name": "Caro-Kann Defense", "variation": "Exchange Variation", "moves": ["e2e4", "c7c6", "d2d4", "d7d5", "e4d5", "c6d5", "f1d3"], "weight": 45},
    {"eco": "B13", "name": "Caro-Kann Defense", "variation": "Panov-Botvinnik Attack", "moves": ["e2e4", "c7c6", "d2d4", "d7d5", "e4d5", "c6d5", "c2c4", "g8f6", "b1c3"], "weight": 50},
    {"eco": "B17", "name": "Caro-Kann Defense", "variation": "Steinitz / Modern", "moves": ["e2e4", "c7c6", "d2d4", "d7d5", "b1c3", "d5e4", "c3e4", "b8d7"], "weight": 50},
    {"eco": "B18", "name": "Caro-Kann Defense", "variation": "Classical Variation", "moves": ["e2e4", "c7c6", "d2d4", "d7d5", "b1c3", "d5e4", "c3e4", "c8f5"], "weight": 65, "mainline": True},

    # Sicilian Defense (B20-B99)
    {"eco": "B20", "name": "Sicilian Defense", "variation": None, "moves": ["e2e4", "c7c5"], "weight": 100, "mainline": True},
    {"eco": "B21", "name": "Sicilian Defense", "variation": "Grand Prix Attack", "moves": ["e2e4", "c7c5", "f2f4"], "weight": 35},
    {"eco": "B21", "name": "Sicilian Defense", "variation": "Smith-Morra Gambit", "moves": ["e2e4", "c7c5", "d2d4", "c5d4", "c2c3"], "weight": 35},
    {"eco": "B22", "name": "Sicilian Defense", "variation": "Alapin Variation", "moves": ["e2e4", "c7c5", "c2c3"], "weight": 60, "mainline": True},
    {"eco": "B22", "name": "Sicilian Defense", "variation": "Alapin, 2...d5", "moves": ["e2e4", "c7c5", "c2c3", "d7d5", "e4d5", "d8d5", "d2d4"], "weight": 50},
    {"eco": "B22", "name": "Sicilian Defense", "variation": "Alapin, 2...Nf6", "moves": ["e2e4", "c7c5", "c2c3", "g8f6", "e4e5", "f6d5", "d2d4", "c5d4"], "weight": 50},
    {"eco": "B23", "name": "Sicilian Defense", "variation": "Closed Variation", "moves": ["e2e4", "c7c5", "b1c3"], "weight": 55},
    {"eco": "B27", "name": "Sicilian Defense", "variation": "Open Sicilian", "moves": ["e2e4", "c7c5", "g1f3"], "weight": 85, "mainline": True},
    {"eco": "B30", "name": "Sicilian Defense", "variation": "Rossolimo Variation", "moves": ["e2e4", "c7c5", "g1f3", "b8c6", "f1b5"], "weight": 60, "mainline": True},
    {"eco": "B33", "name": "Sicilian Defense", "variation": "Sveshnikov Variation", "moves": ["e2e4", "c7c5", "g1f3", "b8c6", "d2d4", "c5d4", "f3d4", "g8f6", "b1c3", "e7e5", "d4b5", "d7d6", "c1g5", "a7a6", "b5a3", "b7b5"], "weight": 70, "mainline": True},
    {"eco": "B34", "name": "Sicilian Defense", "variation": "Accelerated Dragon", "moves": ["e2e4", "c7c5", "g1f3", "b8c6", "d2d4", "c5d4", "f3d4", "g7g6"], "weight": 55},
    {"eco": "B40", "name": "Sicilian Defense", "variation": "French Variation", "moves": ["e2e4", "c7c5", "g1f3", "e7e6"], "weight": 65, "mainline": True},
    {"eco": "B41", "name": "Sicilian Defense", "variation": "Kan / Paulsen Variation", "moves": ["e2e4", "c7c5", "g1f3", "e7e6", "d2d4", "c5d4", "f3d4", "a7a6"], "weight": 55},
    {"eco": "B46", "name": "Sicilian Defense", "variation": "Taimanov Variation", "moves": ["e2e4", "c7c5", "g1f3", "e7e6", "d2d4", "c5d4", "f3d4", "b8c6", "b1c3", "a7a6"], "weight": 60, "mainline": True},
    {"eco": "B50", "name": "Sicilian Defense", "variation": "2...d6", "moves": ["e2e4", "c7c5", "g1f3", "d7d6"], "weight": 80, "mainline": True},
    {"eco": "B51", "name": "Sicilian Defense", "variation": "Moscow Variation", "moves": ["e2e4", "c7c5", "g1f3", "d7d6", "f1b5"], "weight": 60},
    {"eco": "B70", "name": "Sicilian Defense", "variation": "Dragon Variation", "moves": ["e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6", "b1c3", "g7g6"], "weight": 70, "mainline": True},
    {"eco": "B75", "name": "Sicilian Defense", "variation": "Dragon, Yugoslav Attack", "moves": ["e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6", "b1c3", "g7g6", "c1e3", "f8g7", "f2f3"], "weight": 65, "mainline": True},
    {"eco": "B80", "name": "Sicilian Defense", "variation": "Scheveningen Variation", "moves": ["e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6", "b1c3", "e7e6"], "weight": 65, "mainline": True},
    {"eco": "B90", "name": "Sicilian Defense", "variation": "Najdorf Variation", "moves": ["e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6", "b1c3", "a7a6"], "weight": 90, "mainline": True},
    {"eco": "B90", "name": "Sicilian Defense", "variation": "Najdorf, English Attack", "moves": ["e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6", "b1c3", "a7a6", "c1e3", "e7e5", "d4b3", "c8e6", "f2f3"], "weight": 70, "mainline": True},
    {"eco": "B94", "name": "Sicilian Defense", "variation": "Najdorf, 6.Bg5", "moves": ["e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6", "b1c3", "a7a6", "c1g5"], "weight": 65, "mainline": True},

    # --- Volume C: Open Games & French Defense (C00-C99) ---
    # French Defense (C00-C19)
    {"eco": "C00", "name": "French Defense", "variation": None, "moves": ["e2e4", "e7e6"], "weight": 80, "mainline": True},
    {"eco": "C01", "name": "French Defense", "variation": "Exchange Variation", "moves": ["e2e4", "e7e6", "d2d4", "d7d5", "e4d5", "e6d5", "f1d3", "f8d6"], "weight": 45},
    {"eco": "C02", "name": "French Defense", "variation": "Advance Variation", "moves": ["e2e4", "e7e6", "d2d4", "d7d5", "e4e5", "c7c5", "c2c3", "b8c6", "g1f3"], "weight": 70, "mainline": True},
    {"eco": "C03", "name": "French Defense", "variation": "Tarrasch Variation", "moves": ["e2e4", "e7e6", "d2d4", "d7d5", "b1d2"], "weight": 65, "mainline": True},
    {"eco": "C11", "name": "French Defense", "variation": "Classical / Steinitz", "moves": ["e2e4", "e7e6", "d2d4", "d7d5", "b1c3", "g8f6", "e4e5", "f6d7", "f2f4", "c7c5", "g1f3", "b8c6"], "weight": 60, "mainline": True},
    {"eco": "C15", "name": "French Defense", "variation": "Winawer Variation", "moves": ["e2e4", "e7e6", "d2d4", "d7d5", "b1c3", "f8b4"], "weight": 70, "mainline": True},
    {"eco": "C16", "name": "French Defense", "variation": "Winawer, Advance Variation", "moves": ["e2e4", "e7e6", "d2d4", "d7d5", "b1c3", "f8b4", "e4e5", "c7c5", "a2a3", "b4c3", "b2c3"], "weight": 65, "mainline": True},

    # Open Games (C20-C99)
    {"eco": "C20", "name": "King's Pawn Game", "variation": "Open Game", "moves": ["e2e4", "e7e5"], "weight": 95, "mainline": True},
    {"eco": "C21", "name": "Center Game", "variation": None, "moves": ["e2e4", "e7e5", "d2d4", "e5d4"], "weight": 35},
    {"eco": "C23", "name": "Bishop's Opening", "variation": None, "moves": ["e2e4", "e7e5", "f1c4"], "weight": 40},
    {"eco": "C25", "name": "Vienna Game", "variation": None, "moves": ["e2e4", "e7e5", "b1c3"], "weight": 50},
    {"eco": "C30", "name": "King's Gambit", "variation": None, "moves": ["e2e4", "e7e5", "f2f4"], "weight": 45},
    {"eco": "C40", "name": "King's Knight Opening", "variation": None, "moves": ["e2e4", "e7e5", "g1f3"], "weight": 90, "mainline": True},
    {"eco": "C41", "name": "Philidor Defense", "variation": None, "moves": ["e2e4", "e7e5", "g1f3", "d7d6"], "weight": 45},
    {"eco": "C42", "name": "Petroff's Defense", "variation": None, "moves": ["e2e4", "e7e5", "g1f3", "g8f6"], "weight": 65, "mainline": True},
    {"eco": "C45", "name": "Scotch Game", "variation": None, "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "d2d4", "e5d4", "f3d4"], "weight": 70, "mainline": True},
    {"eco": "C47", "name": "Four Knights Game", "variation": "Scotch Variation", "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "b1c3", "g8f6", "d2d4", "e5d4", "f3d4"], "weight": 50},
    {"eco": "C48", "name": "Four Knights Game", "variation": "Spanish Variation", "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "b1c3", "g8f6", "f1b5"], "weight": 55, "mainline": True},

    # Italian Game (C50-C59)
    {"eco": "C50", "name": "Italian Game", "variation": None, "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"], "weight": 85, "mainline": True},
    {"eco": "C50", "name": "Italian Game", "variation": "Giuoco Pianissimo", "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "d2d3", "g8f6", "c2c3"], "weight": 70, "mainline": True},
    {"eco": "C51", "name": "Italian Game", "variation": "Evans Gambit", "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "b2b4"], "weight": 45},
    {"eco": "C53", "name": "Italian Game", "variation": "Giuoco Piano", "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "c2c3"], "weight": 75, "mainline": True},
    {"eco": "C55", "name": "Two Knights Defense", "variation": None, "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"], "weight": 75, "mainline": True},
    {"eco": "C57", "name": "Two Knights Defense", "variation": "Fried Liver Attack", "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "f3g5", "d7d5", "e4d5", "f6d5", "g5f7", "e8f7", "d1f3", "f7e6", "b1c3"], "weight": 50},

    # Ruy Lopez (C60-C99)
    {"eco": "C60", "name": "Ruy Lopez", "variation": None, "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"], "weight": 90, "mainline": True},
    {"eco": "C65", "name": "Ruy Lopez", "variation": "Berlin Defense", "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "g8f6"], "weight": 80, "mainline": True},
    {"eco": "C67", "name": "Ruy Lopez", "variation": "Berlin Wall / Endgame", "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "g8f6", "e1g1", "f6e4", "d2d4", "e4d6", "b5c6", "d7c6", "d4e5", "d6f5", "d1d8", "e8d8"], "weight": 70, "mainline": True},
    {"eco": "C68", "name": "Ruy Lopez", "variation": "Exchange Variation", "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5c6", "d7c6"], "weight": 60, "mainline": True},
    {"eco": "C70", "name": "Ruy Lopez", "variation": "Morphy Defense", "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4"], "weight": 85, "mainline": True},
    {"eco": "C80", "name": "Ruy Lopez", "variation": "Open Variation", "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6", "e1g1", "f6e4"], "weight": 65, "mainline": True},
    {"eco": "C84", "name": "Ruy Lopez", "variation": "Closed Variation", "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6", "e1g1", "f8e7"], "weight": 80, "mainline": True},
    {"eco": "C89", "name": "Ruy Lopez", "variation": "Marshall Attack", "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6", "e1g1", "f8e7", "f1e1", "b7b5", "a4b3", "e8g8", "c2c3", "d7d5", "e4d5", "f6d5", "f3e5", "c6e5", "e1e5", "c7c6"], "weight": 65, "mainline": True},

    # --- Volume D: Closed Games & Grünfeld (D00-D99) ---
    {"eco": "D00", "name": "Queen's Pawn Game", "variation": None, "moves": ["d2d4", "d7d5"], "weight": 90, "mainline": True},
    {"eco": "D02", "name": "London System", "variation": None, "moves": ["d2d4", "d7d5", "c1f4"], "weight": 75, "mainline": True},
    {"eco": "D02", "name": "London System", "variation": "2...Nf6", "moves": ["d2d4", "d7d5", "g1f3", "g8f6", "c1f4", "c7c5", "e2e3", "b8c6", "c2c3"], "weight": 70, "mainline": True},
    {"eco": "D06", "name": "Queen's Gambit", "variation": None, "moves": ["d2d4", "d7d5", "c2c4"], "weight": 90, "mainline": True},
    {"eco": "D10", "name": "Slav Defense", "variation": None, "moves": ["d2d4", "d7d5", "c2c4", "c7c6"], "weight": 80, "mainline": True},
    {"eco": "D17", "name": "Slav Defense", "variation": "Classical / Czech", "moves": ["d2d4", "d7d5", "c2c4", "c7c6", "g1f3", "g8f6", "b1c3", "d5c4", "a2a4", "c8f5"], "weight": 65, "mainline": True},
    {"eco": "D20", "name": "Queen's Gambit Accepted", "variation": None, "moves": ["d2d4", "d7d5", "c2c4", "d5c4"], "weight": 60, "mainline": True},
    {"eco": "D30", "name": "Queen's Gambit Declined", "variation": None, "moves": ["d2d4", "d7d5", "c2c4", "e7e6"], "weight": 85, "mainline": True},
    {"eco": "D35", "name": "Queen's Gambit Declined", "variation": "Exchange Variation", "moves": ["d2d4", "d7d5", "c2c4", "e7e6", "b1c3", "g8f6", "c4d5", "e6d5", "c1g5", "c7c6", "e2e3"], "weight": 65, "mainline": True},
    {"eco": "D38", "name": "Queen's Gambit Declined", "variation": "Ragozin Defense", "moves": ["d2d4", "d7d5", "c2c4", "e7e6", "b1c3", "g8f6", "g1f3", "f8b4"], "weight": 65, "mainline": True},
    {"eco": "D43", "name": "Semi-Slav Defense", "variation": None, "moves": ["d2d4", "d7d5", "c2c4", "e7e6", "b1c3", "g8f6", "g1f3", "c7c6"], "weight": 75, "mainline": True},
    {"eco": "D47", "name": "Semi-Slav Defense", "variation": "Meran Variation", "moves": ["d2d4", "d7d5", "c2c4", "e7e6", "b1c3", "g8f6", "g1f3", "c7c6", "e2e3", "b8d7", "f1d3", "d5c4", "f3c4", "b7b5", "d3d3", "c8b7"], "weight": 65, "mainline": True},
    {"eco": "D58", "name": "Queen's Gambit Declined", "variation": "Tartakower Defense", "moves": ["d2d4", "d7d5", "c2c4", "e7e6", "b1c3", "g8f6", "c1g5", "f8e7", "e2e3", "e8g8", "g1f3", "h7h6", "g5h4", "b7b6"], "weight": 60, "mainline": True},
    {"eco": "D70", "name": "Grünfeld Defense", "variation": None, "moves": ["d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "d7d5"], "weight": 75, "mainline": True},
    {"eco": "D85", "name": "Grünfeld Defense", "variation": "Exchange Variation", "moves": ["d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "d7d5", "c4d5", "f6d5", "e2e4", "d5c3", "b2c3", "f8g7"], "weight": 70, "mainline": True},

    # --- Volume E: Indian Defenses (E00-E99) ---
    {"eco": "E00", "name": "Catalan Opening", "variation": None, "moves": ["d2d4", "g8f6", "c2c4", "e7e6", "g2g3", "d7d5", "f1g2"], "weight": 70, "mainline": True},
    {"eco": "E12", "name": "Queen's Indian Defense", "variation": None, "moves": ["d2d4", "g8f6", "c2c4", "e7e6", "g1f3", "b7b6"], "weight": 65, "mainline": True},
    {"eco": "E20", "name": "Nimzo-Indian Defense", "variation": None, "moves": ["d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8b4"], "weight": 80, "mainline": True},
    {"eco": "E32", "name": "Nimzo-Indian Defense", "variation": "Classical / Capablanca", "moves": ["d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8b4", "d1c2"], "weight": 70, "mainline": True},
    {"eco": "E40", "name": "Nimzo-Indian Defense", "variation": "Rubinstein System", "moves": ["d2d4", "g8f6", "c2c4", "e7e6", "b1c3", "f8b4", "e2e3"], "weight": 75, "mainline": True},
    {"eco": "E60", "name": "King's Indian Defense", "variation": None, "moves": ["d2d4", "g8f6", "c2c4", "g7g6"], "weight": 80, "mainline": True},
    {"eco": "E61", "name": "King's Indian Defense", "variation": "3.Nc3", "moves": ["d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7", "e2e4", "d7d6"], "weight": 75, "mainline": True},
    {"eco": "E76", "name": "King's Indian Defense", "variation": "Four Pawns Attack", "moves": ["d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7", "e2e4", "d7d6", "f2f4", "e8g8", "g1f3"], "weight": 55},
    {"eco": "E80", "name": "King's Indian Defense", "variation": "Sämisch Variation", "moves": ["d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7", "e2e4", "d7d6", "f2f3"], "weight": 65, "mainline": True},
    {"eco": "E90", "name": "King's Indian Defense", "variation": "Classical System", "moves": ["d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7", "e2e4", "d7d6", "g1f3", "e8g8", "f1e2", "e7e5"], "weight": 75, "mainline": True},
    {"eco": "E97", "name": "King's Indian Defense", "variation": "Mar del Plata", "moves": ["d2d4", "g8f6", "c2c4", "g7g6", "b1c3", "f8g7", "e2e4", "d7d6", "g1f3", "e8g8", "f1e2", "e7e5", "e1g1", "b8c6", "d4d5", "c6e7"], "weight": 70, "mainline": True},
]


def _build_opening_trie() -> _OpeningNode:
    root = _OpeningNode(eco="A00", name="Starting Position", variation=None, ply=0)
    for defn in OPENING_DEFINITIONS:
        current = root
        moves = defn.get("moves", [])
        for i, mv_uci in enumerate(moves):
            ply_idx = i + 1
            if mv_uci not in current.children:
                current.children[mv_uci] = _OpeningNode(
                    eco=defn["eco"],
                    name=defn["name"],
                    variation=defn.get("variation"),
                    ply=ply_idx,
                )
            child = current.children[mv_uci]
            # Track weight and classification on the edge
            w = defn.get("weight", 50)
            is_main = bool(defn.get("mainline", False))
            current.weights[mv_uci] = max(current.weights.get(mv_uci, 0), w)
            current.classifications[mv_uci] = "mainline" if is_main else "sideline"
            # Update child node info if more specific
            if i == len(moves) - 1:
                child.eco = defn["eco"]
                child.name = defn["name"]
                child.variation = defn.get("variation")
            current = child
    return root


# Global singleton instances
_OPENING_TRIE: _OpeningNode | None = None
_POLYGLOT_READER: PolyglotBookReader | None = None


def get_opening_trie() -> _OpeningNode:
    global _OPENING_TRIE
    if _OPENING_TRIE is None:
        _OPENING_TRIE = _build_opening_trie()
    return _OPENING_TRIE


def get_polyglot_reader() -> PolyglotBookReader:
    global _POLYGLOT_READER
    if _POLYGLOT_READER is None:
        _POLYGLOT_READER = PolyglotBookReader()
    return _POLYGLOT_READER


def get_opening_info(
    board: chess.Board,
    move_history: list[str] | None = None,
) -> OpeningInfo:
    """
    Computes complete opening info, ECO code, variations, and candidate book moves.
    Traverses move history through the opening trie or checks current board state.
    """
    root = get_opening_trie()
    current_node = root
    last_known_node = root

    moves: list[str] = []
    if move_history is not None:
        moves = list(move_history)
    else:
        try:
            moves = [m.uci() for m in board.move_stack]
        except Exception:
            moves = []

    out_of_book = False
    novelty_ply: int | None = None
    novelty_move: str | None = None

    for i, mv in enumerate(moves):
        if not out_of_book and mv in current_node.children:
            current_node = current_node.children[mv]
            last_known_node = current_node
        else:
            if not out_of_book:
                out_of_book = True
                novelty_ply = i + 1
                novelty_move = mv

    # Candidate Book Moves
    book_moves: list[BookMoveCandidate] = []

    # 1. First check Polyglot book if available
    poly_reader = get_polyglot_reader()
    if poly_reader.is_available():
        book_moves = poly_reader.get_book_moves(board)

    # 2. Fall back to embedded trie moves if no polyglot entries found
    if not book_moves and not out_of_book and current_node.children:
        total_w = sum(current_node.weights.get(mv, 50) for mv in current_node.children)
        max_w = max(current_node.weights.values(), default=0)
        temp_board = board.copy()

        for mv_uci, child_node in current_node.children.items():
            try:
                move_obj = chess.Move.from_uci(mv_uci)
                if move_obj not in temp_board.legal_moves:
                    continue
                w = current_node.weights.get(mv_uci, 50)
                pct = round((w / total_w) * 100.0, 1) if total_w > 0 else round(100.0 / len(current_node.children), 1)
                is_main = (pct >= 25.0) or (w == max_w and w > 0) or (current_node.classifications.get(mv_uci) == "mainline")
                classif = "mainline" if is_main else "sideline"
                from_coord, to_coord = _move_to_coords(move_obj)
                try:
                    san = temp_board.san(move_obj)
                except Exception:
                    san = mv_uci
                book_moves.append(BookMoveCandidate(
                    uci=mv_uci,
                    san=san,
                    weight=w,
                    percentage=pct,
                    classification=classif,
                    from_coord=from_coord,
                    to_coord=to_coord,
                ))
            except Exception:
                pass
        book_moves.sort(key=lambda c: (c.weight, c.percentage), reverse=True)

    if not out_of_book and len(book_moves) == 0 and len(moves) > 0:
        out_of_book = True

    return OpeningInfo(
        eco=last_known_node.eco,
        name=last_known_node.name,
        variation=last_known_node.variation,
        ply=len(moves),
        fen=board.fen(),
        out_of_book=out_of_book,
        novelty_ply=novelty_ply,
        novelty_move=novelty_move,
        book_moves=book_moves,
    )


def get_book_moves_for_square(
    board: chess.Board,
    from_col: int,
    from_row: int,
) -> list[BookMoveCandidate]:
    """Filters candidate book moves originating from a given square coordinate (0..7, 0..7)."""
    info = get_opening_info(board)
    return [bm for bm in info.book_moves if bm.from_coord == (from_col, from_row)]


def lookup_opening_by_moves(moves: list[str]) -> OpeningInfo:
    """Helper to simulate board moves from starting position and return OpeningInfo."""
    board = chess.Board()
    for mv in moves:
        try:
            board.push_uci(mv)
        except Exception:
            break
    return get_opening_info(board, move_history=moves)
