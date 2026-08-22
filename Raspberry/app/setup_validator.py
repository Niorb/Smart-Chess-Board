"""
app/setup_validator.py

Board setup verification subsystem for the Smart Chess Board.
Validates starting piece polarities (White=-1 / South on Ranks 1-2,
Black=+1 / North on Ranks 7-8, Empty=0 on Ranks 3-6) and computes missing or misplaced pieces.
"""

from dataclasses import dataclass, field
from typing import Any

import chess

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


@dataclass
class GameGuardrailResult:
    """Represents the live in-game synchronization state between digital and physical chessboards."""
    is_synchronized: bool
    missing_pieces: list[tuple[int, int]] = field(default_factory=list)
    unexpected_pieces: list[tuple[int, int]] = field(default_factory=list)
    pending_capture: tuple[int, int] | None = None
    candidate_attackers: list[tuple[int, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serializes the guardrail result for WebSocket state payloads."""
        return {
            "is_synchronized": self.is_synchronized,
            "missing_pieces": [list(sq) for sq in self.missing_pieces],
            "unexpected_pieces": [list(sq) for sq in self.unexpected_pieces],
            "pending_capture": list(self.pending_capture) if self.pending_capture else None,
            "candidate_attackers": [list(sq) for sq in self.candidate_attackers],
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

    def validate_game_state(
        self,
        physical_state: list[list[int]],
        board: Any,
        tracker: Any | None = None,
    ) -> GameGuardrailResult:
        """
        Validates the physical 8x8 sensor matrix against the active chess.Board,
        intelligently ignoring valid transient move, capture, castling, and opponent mirror states.

        Args:
            physical_state: 2D list [cols][rows] of sensor readings (-1, 0, 1).
            board: Active chess.Board object.
            tracker: Optional PhysicalMoveTracker instance containing transient move locks.

        Returns:
            GameGuardrailResult indicating synchronization status and any anomalous squares.
        """
        if not board or not hasattr(board, "piece_at"):
            return GameGuardrailResult(is_synchronized=True)

        missing_pieces: list[tuple[int, int]] = []
        unexpected_pieces: list[tuple[int, int]] = []

        # Squares exempted from standard presence checks due to active transient transitions
        exempt_squares: set[tuple[int, int]] = set()

        pending_cap: tuple[int, int] | None = None
        cand_attackers: list[tuple[int, int]] = []

        if tracker is not None:
            # 1. In-flight move lock exemption
            if getattr(tracker, "in_flight_move", None):
                f_c, f_r = tracker.in_flight_move["from"]
                t_c, t_r = tracker.in_flight_move["to"]
                exempt_squares.add((f_c, f_r))
                exempt_squares.add((t_c, t_r))

            # 2. Opponent move pending physical mirroring
            if getattr(tracker, "pending_opponent_move", None):
                opp_from = tracker.pending_opponent_move["from"]
                opp_to = tracker.pending_opponent_move["to"]
                exempt_squares.add(opp_from)
                exempt_squares.add(opp_to)
                if tracker.pending_opponent_move.get("is_castling"):
                    r_from = tracker.pending_opponent_move.get("rook_from")
                    r_to = tracker.pending_opponent_move.get("rook_to")
                    if r_from:
                        exempt_squares.add(r_from)
                    if r_to:
                        exempt_squares.add(r_to)

            # 3. Player's pending castling Rook placement
            if getattr(tracker, "pending_castling_rook", None):
                r_from = tracker.pending_castling_rook["from"]
                r_to = tracker.pending_castling_rook["to"]
                exempt_squares.add(r_from)
                exempt_squares.add(r_to)

            # 4. Friendly piece currently lifted
            if getattr(tracker, "lifted_square", None):
                exempt_squares.add(tracker.lifted_square)
                # If player is making a capture, the target square may be temporarily empty or occupied
                if getattr(tracker, "legal_captures", None):
                    for cap_sq in tracker.legal_captures:
                        exempt_squares.add(cap_sq)

            # 5. Capture-in-progress where opponent piece was lifted first
            if getattr(tracker, "pending_capture_target", None):
                pending_cap = tracker.pending_capture_target
                cand_attackers = getattr(tracker, "capture_candidate_attackers", [])
                exempt_squares.add(pending_cap)

        for c in range(self.cols):
            for r in range(self.rows):
                if (c, r) in exempt_squares:
                    continue

                sq = chess.square(c, r)
                piece = board.piece_at(sq)
                val = physical_state[c][r] if c < len(physical_state) and r < len(physical_state[c]) else 0

                if piece is not None:
                    # Expected occupied: if physically empty, it is missing
                    if val == 0:
                        missing_pieces.append((c, r))
                else:
                    # Expected empty: if physically occupied, it is unexpected
                    if val != 0:
                        unexpected_pieces.append((c, r))

        is_sync = (len(missing_pieces) == 0 and len(unexpected_pieces) == 0)

        return GameGuardrailResult(
            is_synchronized=is_sync,
            missing_pieces=missing_pieces,
            unexpected_pieces=unexpected_pieces,
            pending_capture=pending_cap,
            candidate_attackers=cand_attackers,
        )
