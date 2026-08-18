"""
app/physical_tracker.py

Physical board move tracker for the Smart Chess Board.
Tracks piece lifting, legal target destinations, invalid piece placements,
and synchronization of opponent moves between the Lichess/UCI engine and the physical hardware.
"""

import logging
import time
from typing import Any

import chess

from app.config import BOARD_COLS, BOARD_ROWS

logger = logging.getLogger("smart-chess-app.tracker")


class PhysicalMoveTracker:
    """
    State tracker for physical chess piece manipulations.
    
    Coordinates:
      - from_c, to_c: File index 0..7 (a=0 .. h=7)
      - from_r, to_r: Rank index 0..7 (Rank 1=0 .. Rank 8=7)
    """

    def __init__(self, cols: int = BOARD_COLS, rows: int = BOARD_ROWS):
        self.cols = cols
        self.rows = rows
        self.lifted_square: tuple[int, int] | None = None
        self.legal_targets: list[tuple[int, int]] = []
        self.invalid_placement: tuple[int, int] | None = None
        self.pending_opponent_move: dict[str, Any] | None = None
        self._last_synced_move_uci: str | None = None
        self.in_flight_move: dict[str, Any] | None = None

    def set_in_flight_move(
        self, from_c: int, from_r: int, to_c: int, to_r: int, uci: str
    ) -> None:
        """Sets the currently in-flight move awaiting engine confirmation."""
        self.in_flight_move = {
            "from": (from_c, from_r),
            "to": (to_c, to_r),
            "uci": uci,
            "timestamp": time.time(),
        }

    def clear_in_flight_move(self) -> None:
        """Clears the in-flight move lock."""
        self.in_flight_move = None

    def reset(self) -> None:
        """Resets all move tracking states."""
        self.lifted_square = None
        self.legal_targets = []
        self.invalid_placement = None
        self.pending_opponent_move = None
        self._last_synced_move_uci = None
        self.in_flight_move = None

    def sync_game(self, engine: Any) -> None:
        """
        Detects when opponent makes a move online and sets pending_opponent_move.
        Also clears in-flight moves once reflected in engine.
        
        Args:
            engine: LichessEngine or chess engine instance containing .game_info, .my_color, .board.
        """
        if not engine or not getattr(engine, "board", None):
            return

        game_info = getattr(engine, "game_info", {})
        last_move_uci = game_info.get("last_move")
        my_color = getattr(engine, "my_color", None)
        turn = game_info.get("turn")

        # In-flight move resolution check
        if self.in_flight_move is not None:
            in_flight_uci = self.in_flight_move.get("uci")
            board_last_move_uci = None
            if hasattr(engine.board, "move_stack") and len(engine.board.move_stack) > 0:
                board_last_move_uci = engine.board.peek().uci()

            if (last_move_uci and last_move_uci == in_flight_uci) or (
                board_last_move_uci and board_last_move_uci == in_flight_uci
            ):
                logger.info(f"In-flight move {in_flight_uci} confirmed by engine.")
                self._last_synced_move_uci = in_flight_uci
                self.in_flight_move = None

        if not last_move_uci or len(last_move_uci) < 4:
            return

        # An opponent move has occurred if it's currently the player's turn to move,
        # and the last move on the board hasn't been synced yet.
        is_player_turn = (my_color is not None and turn == my_color)

        if is_player_turn and last_move_uci != self._last_synced_move_uci:
            self._last_synced_move_uci = last_move_uci
            try:
                from_c = ord(last_move_uci[0].lower()) - ord("a")
                from_r = int(last_move_uci[1]) - 1
                to_c = ord(last_move_uci[2].lower()) - ord("a")
                to_r = int(last_move_uci[3]) - 1

                if 0 <= from_c < self.cols and 0 <= from_r < self.rows and 0 <= to_c < self.cols and 0 <= to_r < self.rows:
                    self.pending_opponent_move = {
                        "uci": last_move_uci,
                        "from": (from_c, from_r),
                        "to": (to_c, to_r),
                    }
                    logger.info(f"Opponent move pending physical mirroring: {last_move_uci} ({from_c},{from_r} -> {to_c},{to_r})")
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse last move UCI '{last_move_uci}': {e}")

    def process_physical_state(
        self, physical_state: list[list[int]], engine: Any
    ) -> tuple[int, int, int, int, str | None] | None:
        """
        Evaluates physical board state transitions against the active chess engine position.
        
        Args:
            physical_state: 2D list [cols][rows] of current magnetic sensor states (-1, 0, 1).
            engine: Active chess engine containing .board and .my_color.
            
        Returns:
            Tuple (from_file, from_rank, to_file, to_rank, promotion) in 1-indexed format (1..8)
            if a valid move was executed, or None otherwise.
        """
        if not engine or not getattr(engine, "board", None):
            return None

        # ---------------------------------------------------------------------
        # 0. Handle In-Flight Move Lock
        # ---------------------------------------------------------------------
        if self.in_flight_move is not None:
            elapsed = time.time() - self.in_flight_move.get("timestamp", 0.0)
            if elapsed > 5.0:
                logger.warning(
                    f"In-flight move lock timed out after {elapsed:.1f}s: {self.in_flight_move.get('uci')}. Releasing lock."
                )
                self.in_flight_move = None
            else:
                return None

        board: chess.Board = engine.board

        # ---------------------------------------------------------------------
        # 1. Handle Pending Opponent Move
        # ---------------------------------------------------------------------
        if self.pending_opponent_move is not None:
            opp_from = self.pending_opponent_move["from"]
            opp_to = self.pending_opponent_move["to"]
            from_c, from_r = opp_from
            to_c, to_r = opp_to

            # Opponent move completed when piece lifted from origin and placed on target
            origin_empty = (physical_state[from_c][from_r] == 0)
            target_occupied = (physical_state[to_c][to_r] != 0)

            if origin_empty and target_occupied:
                logger.info(f"Physical board confirmed opponent move: {self.pending_opponent_move['uci']}")
                self.pending_opponent_move = None
                self.invalid_placement = None

            return None

        # ---------------------------------------------------------------------
        # 2. Handle Player Turn & Piece Lifting
        # ---------------------------------------------------------------------
        turn_color = board.turn  # chess.WHITE (True) or chess.BLACK (False)
        expected_polarity = -1 if turn_color == chess.WHITE else 1

        # Case A: No piece currently lifted -> Detect lift
        if self.lifted_square is None:
            for c in range(self.cols):
                for r in range(self.rows):
                    sq = chess.square(c, r)
                    piece = board.piece_at(sq)
                    if piece and piece.color == turn_color:
                        # Piece exists on digital board but sensor reads 0 (lifted)
                        if physical_state[c][r] == 0:
                            self.lifted_square = (c, r)
                            self.invalid_placement = None
                            
                            # Calculate legal destination squares
                            targets: list[tuple[int, int]] = []
                            for m in board.legal_moves:
                                if m.from_square == sq:
                                    t_c = chess.square_file(m.to_square)
                                    t_r = chess.square_rank(m.to_square)
                                    if (t_c, t_r) not in targets:
                                        targets.append((t_c, t_r))
                            self.legal_targets = targets
                            logger.info(f"Piece lifted at ({c},{r}) -> Legal targets: {targets}")
                            return None

        # Case B: Piece is currently lifted -> Detect placement
        else:
            from_c, from_r = self.lifted_square
            sq_from = chess.square(from_c, from_r)

            # 1. Returned to starting square -> Cancel move
            if physical_state[from_c][from_r] != 0:
                logger.info(f"Piece returned to ({from_c},{from_r}). Move cancelled.")
                self.lifted_square = None
                self.legal_targets = []
                self.invalid_placement = None
                return None

            # 2. Placed on a legal target square
            for t_c, t_r in self.legal_targets:
                sq_to = chess.square(t_c, t_r)
                existing_piece = board.piece_at(sq_to)

                # For empty square destination, sensor becomes occupied != 0
                # For capture destination, sensor takes on friendly piece polarity or occupied
                target_val = physical_state[t_c][t_r]
                is_placed = False

                if existing_piece is None:
                    is_placed = (target_val != 0)
                else:
                    # Capture square
                    is_placed = (target_val == expected_polarity or (target_val != 0 and target_val != (-1 if existing_piece.color == chess.WHITE else 1)))

                if is_placed:
                    # Check for pawn promotion
                    promo_moves = [
                        m for m in board.legal_moves
                        if m.from_square == sq_from and m.to_square == sq_to and m.promotion
                    ]
                    promo = "q" if promo_moves else None

                    uci_move = f"{chess.square_name(sq_from)}{chess.square_name(sq_to)}{promo or ''}"
                    self.set_in_flight_move(from_c, from_r, t_c, t_r, uci_move)

                    move_result = (from_c + 1, from_r + 1, t_c + 1, t_r + 1, promo)
                    logger.info(f"Physical move completed: ({from_c},{from_r}) -> ({t_c},{t_r}) promo={promo} uci={uci_move}")

                    self.lifted_square = None
                    self.legal_targets = []
                    self.invalid_placement = None
                    return move_result

            # 3. Placed on an illegal square
            placed_illegally = False
            for c in range(self.cols):
                for r in range(self.rows):
                    if (c, r) == (from_c, from_r) or (c, r) in self.legal_targets:
                        continue

                    sq = chess.square(c, r)
                    piece = board.piece_at(sq)
                    
                    # If previously empty square is now occupied
                    if piece is None and physical_state[c][r] != 0:
                        self.invalid_placement = (c, r)
                        placed_illegally = True
                        break

            if not placed_illegally and self.invalid_placement is not None:
                inv_c, inv_r = self.invalid_placement
                if physical_state[inv_c][inv_r] == 0:
                    self.invalid_placement = None

        return None

    def to_dict(self) -> dict[str, Any]:
        """Serializes tracker state for WebSocket state payloads."""
        return {
            "lifted_square": list(self.lifted_square) if self.lifted_square else None,
            "legal_targets": [list(sq) for sq in self.legal_targets],
            "invalid_placement": list(self.invalid_placement) if self.invalid_placement else None,
            "pending_opponent_move": self.pending_opponent_move,
            "in_flight_move": (
                {
                    "from": list(self.in_flight_move["from"]),
                    "to": list(self.in_flight_move["to"]),
                    "uci": self.in_flight_move["uci"],
                    "timestamp": self.in_flight_move.get("timestamp", 0.0),
                }
                if self.in_flight_move
                else None
            ),
        }
