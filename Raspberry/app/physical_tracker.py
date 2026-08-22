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

from app.config import ANIM_MOVE_CONFIRM_DURATION_S, BOARD_COLS, BOARD_ROWS
from app.path_interpolator import get_castle_rook_move, is_castle_uci

logger = logging.getLogger("smart-chess-app.tracker")


def _sensor_polarity(color: int) -> int:
    """Returns the expected sensor polarity for a piece color (White=-1, Black=+1)."""
    return -1 if color == chess.WHITE else 1


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
        self.legal_captures: list[tuple[int, int]] = []
        self.invalid_placement: tuple[int, int] | None = None
        self.pending_opponent_move: dict[str, Any] | None = None
        self._last_synced_move_uci: str | None = None
        self.in_flight_move: dict[str, Any] | None = None
        self.arrival_flash: dict[str, Any] | None = None
        self.pending_castling_rook: dict[str, Any] | None = None
        self.pending_capture_target: tuple[int, int] | None = None
        self.capture_candidate_attackers: list[tuple[int, int]] = []
        self.last_physical_state: list[list[int]] | None = None

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

    def reset(self, initial_state: list[list[int]] | None = None) -> None:
        """Resets all move tracking states."""
        self.lifted_square = None
        self.legal_targets = []
        self.legal_captures = []
        self.invalid_placement = None
        self.pending_opponent_move = None
        self._last_synced_move_uci = None
        self.in_flight_move = None
        self.arrival_flash = None
        self.pending_castling_rook = None
        self.pending_capture_target = None
        self.capture_candidate_attackers = []
        self.last_physical_state = [row[:] for row in initial_state] if initial_state is not None else None

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
                    is_capture = False
                    is_castling = False
                    rook_coords = None
                    if hasattr(engine.board, "move_stack") and len(engine.board.move_stack) > 0:
                        last_move = engine.board.peek()
                        if last_move.uci() == last_move_uci:
                            m = engine.board.pop()
                            is_capture = bool(engine.board.is_capture(m))
                            is_castling = bool(engine.board.is_castling(m))
                            engine.board.push(m)
                            if is_castling:
                                rook_coords = get_castle_rook_move(from_c, from_r, to_c, to_r)
                    elif is_castle_uci(last_move_uci):
                        is_castling = True
                        rook_coords = get_castle_rook_move(from_c, from_r, to_c, to_r)

                    self.pending_opponent_move = {
                        "uci": last_move_uci,
                        "from": (from_c, from_r),
                        "to": (to_c, to_r),
                        "is_capture": is_capture,
                        "is_castling": is_castling,
                        "rook_from": rook_coords[0] if rook_coords else None,
                        "rook_to": rook_coords[1] if rook_coords else None,
                    }
                    logger.info(
                        f"Opponent move pending physical mirroring: {last_move_uci} "
                        f"({from_c},{from_r} -> {to_c},{to_r}) capture={is_capture} castling={is_castling}"
                    )
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
        # 0. Handle Pending Opponent Move
        # ---------------------------------------------------------------------
        if self.pending_opponent_move is not None:
            opp_from = self.pending_opponent_move["from"]
            opp_to = self.pending_opponent_move["to"]
            from_c, from_r = opp_from
            to_c, to_r = opp_to
            is_castling = bool(self.pending_opponent_move.get("is_castling", False))
            rook_from = self.pending_opponent_move.get("rook_from")
            rook_to = self.pending_opponent_move.get("rook_to")

            if is_castling and rook_from and rook_to:
                r_from_c, r_from_r = rook_from
                r_to_c, r_to_r = rook_to

                king_origin_empty = (physical_state[from_c][from_r] == 0)
                king_target_occupied = (physical_state[to_c][to_r] != 0)
                rook_origin_empty = (physical_state[r_from_c][r_from_r] == 0)
                rook_target_occupied = (physical_state[r_to_c][r_to_r] != 0)

                # Castling complete when BOTH King and Rook have reached their targets
                if king_origin_empty and king_target_occupied and rook_origin_empty and rook_target_occupied:
                    logger.info(f"Physical board confirmed opponent castling move: {self.pending_opponent_move['uci']}")
                    self.arrival_flash = {
                        "square": (to_c, to_r),
                        "start_time": time.time(),
                        "duration": ANIM_MOVE_CONFIRM_DURATION_S,
                        "is_capture": False,
                    }
                    self.pending_opponent_move = None
                    self.invalid_placement = None
            else:
                # Opponent move completed when piece lifted from origin and placed on target
                origin_empty = (physical_state[from_c][from_r] == 0)
                target_occupied = (physical_state[to_c][to_r] != 0)

                if origin_empty and target_occupied:
                    logger.info(f"Physical board confirmed opponent move: {self.pending_opponent_move['uci']}")
                    self.arrival_flash = {
                        "square": (to_c, to_r),
                        "start_time": time.time(),
                        "duration": ANIM_MOVE_CONFIRM_DURATION_S,
                        "is_capture": bool(self.pending_opponent_move.get("is_capture", False)),
                    }
                    self.pending_opponent_move = None
                    self.invalid_placement = None

            return None

        # ---------------------------------------------------------------------
        # 0.5 Handle Player's Pending Castling Rook Movement
        # ---------------------------------------------------------------------
        if self.pending_castling_rook is not None:
            r_from_c, r_from_r = self.pending_castling_rook["from"]
            r_to_c, r_to_r = self.pending_castling_rook["to"]
            rook_origin_empty = (physical_state[r_from_c][r_from_r] == 0)
            rook_target_occupied = (physical_state[r_to_c][r_to_r] != 0)
            elapsed = time.time() - self.pending_castling_rook.get("start_time", 0.0)

            if rook_origin_empty and rook_target_occupied:
                logger.info(f"Physical board confirmed player castling Rook placement: ({r_to_c},{r_to_r})")
                self.arrival_flash = {
                    "square": (r_to_c, r_to_r),
                    "start_time": time.time(),
                    "duration": ANIM_MOVE_CONFIRM_DURATION_S,
                    "is_capture": False,
                }
                self.pending_castling_rook = None
                self.last_physical_state = [row[:] for row in physical_state]
                return None
            elif elapsed > 20.0:
                logger.info("Player pending castling Rook timed out.")
                self.pending_castling_rook = None
            else:
                # Castling Rook is in transit (being lifted / placed).
                # CRITICAL: Suppress all normal piece movement detection until the Rook is placed!
                self.last_physical_state = [row[:] for row in physical_state]
                return None

        # ---------------------------------------------------------------------
        # 1. Handle In-Flight Move Lock
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
        # 2. Handle Player Turn & Piece Lifting
        # ---------------------------------------------------------------------
        my_color = getattr(engine, "my_color", None)
        if my_color is not None:
            engine_turn_color = "white" if board.turn == chess.WHITE else "black"
            if engine_turn_color != my_color:
                # It's opponent's turn. Physical piece lift by player is suppressed.
                self.last_physical_state = [row[:] for row in physical_state]
                return None

        turn_color = board.turn  # chess.WHITE (True) or chess.BLACK (False)

        # Case A: No piece currently lifted -> Detect lift
        if self.lifted_square is None:
            # Subcase A.1: Capture target piece was lifted first
            if self.pending_capture_target is not None:
                cap_c, cap_r = self.pending_capture_target
                cap_sq = chess.square(cap_c, cap_r)

                # If capture target square has become occupied
                if physical_state[cap_c][cap_r] != 0:
                    empty_attackers = [
                        (ac, ar) for ac, ar in self.capture_candidate_attackers
                        if physical_state[ac][ar] == 0
                    ]
                    # 1. Attacker was placed on the target square (Direct capture completion)
                    if len(empty_attackers) == 1:
                        from_c, from_r = empty_attackers[0]
                        sq_from = chess.square(from_c, from_r)
                        sq_to = cap_sq
                        t_c, t_r = cap_c, cap_r

                        self.arrival_flash = {
                            "square": (t_c, t_r),
                            "start_time": time.time(),
                            "duration": ANIM_MOVE_CONFIRM_DURATION_S,
                            "is_capture": True,
                        }

                        promo_moves = [
                            m for m in board.legal_moves
                            if m.from_square == sq_from and m.to_square == sq_to and m.promotion
                        ]
                        promo = "q" if promo_moves else None
                        uci_move = f"{chess.square_name(sq_from)}{chess.square_name(sq_to)}{promo or ''}"
                        self.set_in_flight_move(from_c, from_r, t_c, t_r, uci_move)

                        move_result = (from_c + 1, from_r + 1, t_c + 1, t_r + 1, promo)
                        logger.info(f"Physical capture move completed directly: ({from_c},{from_r}) -> ({t_c},{t_r}) uci={uci_move}")

                        self.lifted_square = None
                        self.legal_targets = []
                        self.legal_captures = []
                        self.pending_capture_target = None
                        self.capture_candidate_attackers = []
                        self.invalid_placement = None
                        self.last_physical_state = [row[:] for row in physical_state]
                        return move_result
                    else:
                        # 2. Opponent piece returned to capture square -> Cancel capture intent
                        logger.info(f"Opponent piece returned to ({cap_c},{cap_r}). Capture intent cancelled.")
                        self.pending_capture_target = None
                        self.capture_candidate_attackers = []
                        self.last_physical_state = [row[:] for row in physical_state]
                        return None

                # If capture target square is still empty: check if candidate friendly attacker was lifted
                for ac, ar in self.capture_candidate_attackers:
                    if physical_state[ac][ar] == 0:
                        sq_att = chess.square(ac, ar)
                        self.lifted_square = (ac, ar)
                        self.invalid_placement = None

                        targets = []
                        captures = []
                        for m in board.legal_moves:
                            if m.from_square == sq_att:
                                t_c = chess.square_file(m.to_square)
                                t_r = chess.square_rank(m.to_square)
                                if (t_c, t_r) not in targets:
                                    targets.append((t_c, t_r))
                                if board.is_capture(m) and (t_c, t_r) not in captures:
                                    captures.append((t_c, t_r))
                        self.legal_targets = targets
                        self.legal_captures = captures
                        logger.info(
                            f"Friendly attacker lifted at ({ac},{ar}) for capture at ({cap_c},{cap_r}) -> targets: {targets}"
                        )
                        self.last_physical_state = [row[:] for row in physical_state]
                        return None

            # Subcase A.2: Detect new lift
            else:
                for c in range(self.cols):
                    for r in range(self.rows):
                        sq = chess.square(c, r)
                        piece = board.piece_at(sq)
                        if piece is None:
                            continue

                        # Detect lift: transition from occupied (!= 0) to empty (== 0)
                        is_lifted = False
                        if self.last_physical_state is not None:
                            is_lifted = (self.last_physical_state[c][r] != 0 and physical_state[c][r] == 0)
                        else:
                            is_lifted = (physical_state[c][r] == 0)

                        if not is_lifted:
                            continue

                        # If friendly piece lifted
                        if piece.color == turn_color:
                            self.lifted_square = (c, r)
                            self.invalid_placement = None

                            # Calculate legal destination squares & captures
                            targets = []
                            captures = []
                            for m in board.legal_moves:
                                if m.from_square == sq:
                                    t_c = chess.square_file(m.to_square)
                                    t_r = chess.square_rank(m.to_square)
                                    if (t_c, t_r) not in targets:
                                        targets.append((t_c, t_r))
                                    if board.is_capture(m) and (t_c, t_r) not in captures:
                                        captures.append((t_c, t_r))
                            self.legal_targets = targets
                            self.legal_captures = captures
                            logger.info(f"Piece lifted at ({c},{r}) -> Legal targets: {targets} (captures: {captures})")
                            self.last_physical_state = [row[:] for row in physical_state]
                            return None

                        # If opponent piece lifted first (Capture Intent)
                        elif piece.color != turn_color:
                            attackers = [
                                (chess.square_file(m.from_square), chess.square_rank(m.from_square))
                                for m in board.legal_moves
                                if m.to_square == sq
                            ]
                            if len(attackers) > 0:
                                self.pending_capture_target = (c, r)
                                self.capture_candidate_attackers = attackers
                                self.invalid_placement = None
                                logger.info(
                                    f"Opponent piece lifted first at ({c},{r})! Initiating capture intent. Candidate attackers: {attackers}"
                                )
                                self.last_physical_state = [row[:] for row in physical_state]
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
                self.legal_captures = []
                self.pending_capture_target = None
                self.capture_candidate_attackers = []
                self.invalid_placement = None
                self.last_physical_state = [row[:] for row in physical_state]
                return None

            # 2. Placed on a legal target square
            for t_c, t_r in self.legal_targets:
                sq_to = chess.square(t_c, t_r)
                existing_piece = board.piece_at(sq_to)

                # For empty square destination, sensor becomes occupied != 0
                # For capture destination, sensor takes on friendly piece polarity or occupied
                target_val = physical_state[t_c][t_r]
                is_placed = False

                if existing_piece is None or (t_c, t_r) == self.pending_capture_target:
                    is_placed = (target_val != 0)
                else:
                    # Capture square where opponent piece was not pre-lifted:
                    # occupied by anything except the opponent piece's own polarity
                    opponent_polarity = _sensor_polarity(existing_piece.color)
                    is_placed = (target_val != 0 and target_val != opponent_polarity)

                if is_placed:
                    is_capture = (existing_piece is not None or (t_c, t_r) == self.pending_capture_target)
                    self.arrival_flash = {
                        "square": (t_c, t_r),
                        "start_time": time.time(),
                        "duration": ANIM_MOVE_CONFIRM_DURATION_S,
                        "is_capture": is_capture,
                    }

                    # Check for castling move to prompt the corresponding Rook movement
                    # (geometric check only: a King moving two files horizontally is castling in standard chess)
                    castle_rook = get_castle_rook_move(from_c, from_r, t_c, t_r)
                    if castle_rook is not None:
                        self.pending_castling_rook = {
                            "from": castle_rook[0],
                            "to": castle_rook[1],
                            "start_time": time.time(),
                        }
                        logger.info(
                            f"Player executed King castling move. Prompting Rook movement: {castle_rook[0]} -> {castle_rook[1]}"
                        )

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
                    self.legal_captures = []
                    self.pending_capture_target = None
                    self.capture_candidate_attackers = []
                    self.invalid_placement = None
                    self.last_physical_state = [row[:] for row in physical_state]
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

        self.last_physical_state = [row[:] for row in physical_state]
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serializes tracker state for WebSocket state payloads."""
        return {
            "lifted_square": list(self.lifted_square) if self.lifted_square else None,
            "legal_targets": [list(sq) for sq in self.legal_targets],
            "legal_captures": [list(sq) for sq in self.legal_captures],
            "pending_capture_target": list(self.pending_capture_target) if self.pending_capture_target else None,
            "capture_candidate_attackers": [list(sq) for sq in self.capture_candidate_attackers],
            "invalid_placement": list(self.invalid_placement) if self.invalid_placement else None,
            "pending_opponent_move": self.pending_opponent_move,
            "pending_castling_rook": (
                {
                    "from": list(self.pending_castling_rook["from"]),
                    "to": list(self.pending_castling_rook["to"]),
                    "start_time": self.pending_castling_rook.get("start_time", 0.0),
                }
                if self.pending_castling_rook
                else None
            ),
            "arrival_flash": (
                {
                    "square": list(self.arrival_flash["square"]),
                    "start_time": self.arrival_flash["start_time"],
                    "duration": self.arrival_flash["duration"],
                    "is_capture": self.arrival_flash["is_capture"],
                }
                if self.arrival_flash
                else None
            ),
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
