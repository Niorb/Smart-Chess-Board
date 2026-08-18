"""
app/setup_validator.py

Board setup verification subsystem for the Smart Chess Board.
Validates starting piece polarities (White=-1 / South on Ranks 1-2,
Black=+1 / North on Ranks 7-8, Empty=0 on Ranks 3-6) and computes missing or misplaced pieces.
"""

from dataclasses import dataclass, field
from typing import Any

from app.config import BOARD_COLS, BOARD_ROWS


@dataclass
class SetupResult:
    """Represents the validation result of the physical chessboard initial setup."""
    is_setup_ready: bool
    missing_white: list[tuple[int, int]] = field(default_factory=list)
    missing_black: list[tuple[int, int]] = field(default_factory=list)
    misplaced_pieces: list[tuple[int, int]] = field(default_factory=list)
    white_count: int = 0
    black_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serializes the setup result for WebSocket broadcasts and REST API responses."""
        return {
            "is_setup_ready": self.is_setup_ready,
            "missing_white": [list(sq) for sq in self.missing_white],
            "missing_black": [list(sq) for sq in self.missing_black],
            "misplaced_pieces": [list(sq) for sq in self.misplaced_pieces],
            "white_count": self.white_count,
            "black_count": self.black_count,
        }


class SetupValidator:
    """
    Validates physical chessboard setup against standard chess starting position.
    
    Coordinate convention:
      - c (column / file): 0..7 representing files a..h
      - r (row / rank): 0..7 representing ranks 1..8
    
    Polarity convention:
      - White pieces: -1 (South magnetic pole) on Ranks 1 and 2 (r in 0, 1)
      - Black pieces: +1 (North magnetic pole) on Ranks 7 and 8 (r in 6, 7)
      - Empty squares: 0 on Ranks 3..6 (r in 2, 3, 4, 5)
    """

    def __init__(self, cols: int = BOARD_COLS, rows: int = BOARD_ROWS):
        self.cols = cols
        self.rows = rows

    def validate(self, physical_state: list[list[int]]) -> SetupResult:
        """
        Validates the 8x8 physical sensor grid.
        
        Args:
            physical_state: 2D list [cols][rows] containing sensor states (-1, 0, 1).
            
        Returns:
            SetupResult with missing/misplaced pieces and readiness status.
        """
        missing_white: list[tuple[int, int]] = []
        missing_black: list[tuple[int, int]] = []
        misplaced_pieces: list[tuple[int, int]] = []
        white_count = 0
        black_count = 0

        for c in range(self.cols):
            for r in range(self.rows):
                val = physical_state[c][r] if c < len(physical_state) and r < len(physical_state[c]) else 0

                if val == -1:
                    white_count += 1
                elif val == 1:
                    black_count += 1

                # Rank 1 & 2 (r = 0, 1): Expected White (-1)
                if r in (0, 1):
                    if val == 0:
                        missing_white.append((c, r))
                    elif val == 1:
                        # Black piece on White starting rank
                        misplaced_pieces.append((c, r))
                        missing_white.append((c, r))

                # Rank 7 & 8 (r = 6, 7): Expected Black (+1)
                elif r in (6, 7):
                    if val == 0:
                        missing_black.append((c, r))
                    elif val == -1:
                        # White piece on Black starting rank
                        misplaced_pieces.append((c, r))
                        missing_black.append((c, r))

                # Ranks 3..6 (r in 2, 3, 4, 5): Expected Empty (0)
                else:
                    if val != 0:
                        misplaced_pieces.append((c, r))

        is_setup_ready = (
            len(missing_white) == 0
            and len(missing_black) == 0
            and len(misplaced_pieces) == 0
        )

        return SetupResult(
            is_setup_ready=is_setup_ready,
            missing_white=missing_white,
            missing_black=missing_black,
            misplaced_pieces=misplaced_pieces,
            white_count=white_count,
            black_count=black_count,
        )
