"""
app/physical_tracker.py

Physical board move tracker for the Smart Chess Board.
Tracks piece lifting, legal target destinations, invalid piece placements,
synchronization of opponent moves between the Lichess/UCI engine and the physical hardware,
and the Royal Promotion Scepter state machine.
"""

import logging
import time
from typing import Any

import chess

from app.config import (
    ANIM_MOVE_CONFIRM_DURATION_S,
    BOARD_COLS,
    BOARD_ROWS,
    RESIGNATION_ABANDON_DURATION_S,
    RESIGNATION_HOLD_DURATION_S,
)
from app.path_interpolator import get_castle_rook_move, is_castle_uci

logger = logging.getLogger("smart-chess-app.tracker")


def _sensor_polarity(color: int) -> int:
    """Returns the expected sensor polarity for a piece color (White=-1, Black=+1)."""
    return -1 if color == chess.WHITE else 1


def compute_promotion_layout(
    promo_col: int,
    promo_rank: int,
    is_white: bool,
    physical_state: list[list[int]],
) -> dict[str, tuple[int, int]]:
    """
    Computes 4 distinct LED/sensor target coordinates for promotion pieces ['q', 'n', 'r', 'b'].

    Layout Rules:
      - Assigns 4 distinct board coordinates (0-indexed col, row) for ['q', 'n', 'r', 'b'].
      - Target back-rank is rank 7 (Rank 8) for White, rank 0 (Rank 1) for Black.
      - Fallback rank is rank 6 (Rank 7) for White, rank 1 (Rank 2) for Black.
      - Candidate files are searched center-out relative to promo_col:
        [promo_col, promo_col-1, promo_col+1, promo_col-2, promo_col+2, ...].
      - For each file f:
        - If (f, back_rank) is the promotion square itself or occupied
          (physical_state[f][back_rank] != 0) or already used:
          - Fall back to (f, fallback_rank) if it is empty (physical_state[f][fallback_rank] == 0)
            and unallocated!
        - If (f, back_rank) is empty and unallocated, allocate (f, back_rank).
      - Extreme edge case: If still fewer than 4 squares found, scan remaining empty squares
        on the board without failing.

    Args:
        promo_col: 0-indexed column of promotion square (0..7).
        promo_rank: 0-indexed rank of promotion square (0 or 7).
        is_white: True if White is promoting, False for Black.
        physical_state: 8x8 matrix of magnetic sensor values (-1, 0, 1).

    Returns:
        Dictionary mapping piece type ('q', 'n', 'r', 'b') to (col, rank) coordinate tuple.
    """
    back_rank = 7 if is_white else 0
    fallback_rank = 6 if is_white else 1

    candidate_files = [promo_col]
    for d in range(1, 8):
        if promo_col - d >= 0:
            candidate_files.append(promo_col - d)
        if promo_col + d < 8:
            candidate_files.append(promo_col + d)

    allocated_squares: list[tuple[int, int]] = []

    for f in candidate_files:
        if len(allocated_squares) >= 4:
            break

        sq_back = (f, back_rank)
        sq_fallback = (f, fallback_rank)

        is_back_unavailable = (
            sq_back == (promo_col, promo_rank)
            or physical_state[f][back_rank] != 0
            or sq_back in allocated_squares
        )

        if is_back_unavailable:
            if (
                physical_state[f][fallback_rank] == 0
                and sq_fallback not in allocated_squares
                and sq_fallback != (promo_col, promo_rank)
            ):
                allocated_squares.append(sq_fallback)
        else:
            allocated_squares.append(sq_back)

    # Extreme edge case: scan remaining empty squares on board
    if len(allocated_squares) < 4:
        for r in range(8):
            for c in range(8):
                if len(allocated_squares) >= 4:
                    break
                sq = (c, r)
                if (
                    sq != (promo_col, promo_rank)
                    and sq not in allocated_squares
                    and physical_state[c][r] == 0
                ):
                    allocated_squares.append(sq)

    # Safety fallback: if board is extremely full, fill any unallocated coordinate
    if len(allocated_squares) < 4:
        for r in range(8):
            for c in range(8):
                if len(allocated_squares) >= 4:
                    break
                sq = (c, r)
                if sq != (promo_col, promo_rank) and sq not in allocated_squares:
                    allocated_squares.append(sq)

    pieces = ["q", "n", "r", "b"]
    return {piece: allocated_squares[i] for i, piece in enumerate(pieces)}


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
        self.pending_promotion: dict[str, Any] | None = None
        self.king_lift_time: float | None = None
        self.resignation_armed: bool = False
        self.resignation_hold_duration: float = RESIGNATION_HOLD_DURATION_S
        self.resignation_abandon_duration: float = RESIGNATION_ABANDON_DURATION_S
        self.resignation_color: str | None = None
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

    def clear_transients(self) -> None:
        """Clears all transient interactive states (lifted square, invalid placement, pending promotions)."""
        self.lifted_square = None
        self.legal_targets = []
        self.legal_captures = []
        self.invalid_placement = None
        self.pending_capture_target = None
        self.capture_candidate_attackers = []
        self.pending_promotion = None
        self.king_lift_time = None
        self.resignation_armed = False
        self.resignation_color = None

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
        self.pending_promotion = None
        self.king_lift_time = None
        self.resignation_armed = False
        self.resignation_color = None
        self.last_physical_state = [row[:] for row in initial_state] if initial_state is not None else None

    def resolve_promotion(
        self, piece: str
    ) -> tuple[int, int, int, int, str] | None:
        """
        Resolves an active pending promotion externally (e.g. from REST or WebSocket command).

        Args:
            piece: One of 'q', 'r', 'b', 'n' (case-insensitive).

        Returns:
            1-indexed tuple (from_file, from_rank, to_file, to_rank, promo_piece) if promotion
            was active, or None otherwise.
        """
        if self.pending_promotion is None:
            return None

        promo_piece = piece.lower()
        if promo_piece not in ("q", "n", "r", "b"):
            promo_piece = "q"

        from_c, from_r = self.pending_promotion["from"]
        to_c, to_r = self.pending_promotion["to"]
        is_capture = bool(self.pending_promotion.get("is_capture", False))

        self.pending_promotion = None
        self.arrival_flash = {
            "square": (to_c, to_r),
            "start_time": time.time(),
            "duration": ANIM_MOVE_CONFIRM_DURATION_S,
            "is_capture": is_capture,
        }
        sq_from = chess.square(from_c, from_r)
        sq_to = chess.square(to_c, to_r)
        uci_move = f"{chess.square_name(sq_from)}{chess.square_name(sq_to)}{promo_piece}"
        self.set_in_flight_move(from_c, from_r, to_c, to_r, uci_move)

        self.lifted_square = None
        self.legal_targets = []
        self.legal_captures = []
        self.invalid_placement = None

        logger.info(
            f"External promotion resolved with '{promo_piece}': ({from_c},{from_r}) -> ({to_c},{to_r}) uci={uci_move}"
        )
        return (from_c + 1, from_r + 1, to_c + 1, to_r + 1, promo_piece)

    def set_opponent_move(
        self,
        from_coord: tuple[int, int],
        to_coord: tuple[int, int],
        is_capture: bool = False,
        is_castling: bool = False,
        rook_from: tuple[int, int] | None = None,
        rook_to: tuple[int, int] | None = None,
        uci: str = "",
    ) -> None:
        """Explicitly queues a pending opponent move for physical board execution guidance."""
        from_sq = f"{chr(ord('a') + from_coord[0])}{from_coord[1] + 1}"
        to_sq = f"{chr(ord('a') + to_coord[0])}{to_coord[1] + 1}"
        move_uci = uci or f"{from_sq}{to_sq}"
        target_initial_val = 0
        if self.last_physical_state and to_coord[0] < len(self.last_physical_state) and to_coord[1] < len(self.last_physical_state[to_coord[0]]):
            target_initial_val = self.last_physical_state[to_coord[0]][to_coord[1]]

        self.pending_opponent_move = {
            "uci": move_uci,
            "from": from_coord,
            "to": to_coord,
            "is_capture": is_capture,
            "is_castling": is_castling,
            "rook_from": rook_from,
            "rook_to": rook_to,
            "phase": "king" if is_castling else "standard",
            "initial_target_val": target_initial_val,
            "target_vacated": False,
        }
        logger.info(
            f"Opponent move explicitly queued in tracker: {move_uci} "
            f"({from_coord} -> {to_coord}) capture={is_capture}"
        )

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

                    target_initial_val = 0
                    if self.last_physical_state and to_c < len(self.last_physical_state) and to_r < len(self.last_physical_state[to_c]):
                        target_initial_val = self.last_physical_state[to_c][to_r]

                    self.pending_opponent_move = {
                        "uci": last_move_uci,
                        "from": (from_c, from_r),
                        "to": (to_c, to_r),
                        "is_capture": is_capture,
                        "is_castling": is_castling,
                        "rook_from": rook_coords[0] if rook_coords else None,
                        "rook_to": rook_coords[1] if rook_coords else None,
                        "phase": "king" if is_castling else "standard",
                        "initial_target_val": target_initial_val,
                        "target_vacated": False,
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
            is_capture = bool(self.pending_opponent_move.get("is_capture", False))
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

                current_phase = self.pending_opponent_move.get("phase", "king")

                # Both pieces moved (e.g. simultaneous or rook moved first) -> complete
                if king_origin_empty and king_target_occupied and rook_origin_empty and rook_target_occupied:
                    logger.info(f"Physical board confirmed opponent castling complete: {self.pending_opponent_move['uci']}")
                    self.arrival_flash = {
                        "square": (r_to_c, r_to_r),
                        "start_time": time.time(),
                        "duration": ANIM_MOVE_CONFIRM_DURATION_S,
                        "is_capture": False,
                    }
                    self.pending_opponent_move = None
                    self.invalid_placement = None
                elif current_phase == "king":
                    # Phase 1 (King Time): King placed at destination -> advance to Phase 2 (Rook Time)
                    if king_origin_empty and king_target_occupied:
                        logger.info(f"Physical board confirmed opponent castling King placement: ({to_c},{to_r})")
                        self.arrival_flash = {
                            "square": (to_c, to_r),
                            "start_time": time.time(),
                            "duration": ANIM_MOVE_CONFIRM_DURATION_S,
                            "is_capture": False,
                        }
                        self.pending_opponent_move["phase"] = "rook"
                        self.invalid_placement = None
                elif current_phase == "rook":
                    # Phase 2 (Rook Time): Rook placed at destination -> castling complete
                    if rook_origin_empty and rook_target_occupied:
                        logger.info(f"Physical board confirmed opponent castling Rook placement: ({r_to_c},{r_to_r})")
                        self.arrival_flash = {
                            "square": (r_to_c, r_to_r),
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

                if is_capture:
                    if physical_state[to_c][to_r] == 0:
                        self.pending_opponent_move["target_vacated"] = True

                    initial_val = self.pending_opponent_move.get("initial_target_val", 0)
                    polarity_flipped = (
                        initial_val != 0
                        and physical_state[to_c][to_r] != 0
                        and physical_state[to_c][to_r] != initial_val
                    )
                    target_confirmed = (
                        self.pending_opponent_move.get("target_vacated", False)
                        or polarity_flipped
                        or initial_val == 0
                    )
                else:
                    target_confirmed = True

                if origin_empty and target_occupied and target_confirmed:
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
        # 2. Handle Player Turn & Active Pending Promotion
        # ---------------------------------------------------------------------
        my_color = getattr(engine, "my_color", None)
        if my_color is not None:
            engine_turn_color = "white" if board.turn == chess.WHITE else "black"
            if engine_turn_color != my_color:
                # It's opponent's turn. Physical piece lift by player is suppressed.
                self.last_physical_state = [row[:] for row in physical_state]
                return None

        # ---------------------------------------------------------------------
        # 2.5 Royal Promotion Scepter State Machine
        # ---------------------------------------------------------------------
        if self.pending_promotion is not None:
            from_c, from_r = self.pending_promotion["from"]
            to_c, to_r = self.pending_promotion["to"]
            options = self.pending_promotion.get("options", {})
            start_time = self.pending_promotion.get("start_time", 0.0)
            timeout_s = self.pending_promotion.get("timeout_s", 5.0)
            is_capture = bool(self.pending_promotion.get("is_capture", False))

            # 1. Promoting pawn picked up from `to` square (cancelled / returned)
            if physical_state[to_c][to_r] == 0:
                logger.info(
                    f"Promoting pawn lifted from ({to_c},{to_r}). Promotion cancelled, returning control to ({from_c},{from_r})."
                )
                self.pending_promotion = None
                self.lifted_square = (from_c, from_r)
                self.invalid_placement = None

                # Recalculate legal targets & captures for from_sq
                sq_from = chess.square(from_c, from_r)
                targets = []
                captures = []
                for m in board.legal_moves:
                    if m.from_square == sq_from:
                        t_file = chess.square_file(m.to_square)
                        t_rank = chess.square_rank(m.to_square)
                        if (t_file, t_rank) not in targets:
                            targets.append((t_file, t_rank))
                        if board.is_capture(m) and (t_file, t_rank) not in captures:
                            captures.append((t_file, t_rank))
                self.legal_targets = targets
                self.legal_captures = captures
                self.last_physical_state = [row[:] for row in physical_state]
                return None

            # 2. Check physical placement on any of options[piece]
            for piece, (opt_c, opt_r) in options.items():
                if physical_state[opt_c][opt_r] != 0:
                    logger.info(
                        f"Promotion piece '{piece}' physically selected at ({opt_c},{opt_r}) for move ({from_c},{from_r}) -> ({to_c},{to_r})"
                    )
                    self.pending_promotion = None
                    self.arrival_flash = {
                        "square": (to_c, to_r),
                        "start_time": time.time(),
                        "duration": ANIM_MOVE_CONFIRM_DURATION_S,
                        "is_capture": is_capture,
                    }
                    sq_from = chess.square(from_c, from_r)
                    sq_to = chess.square(to_c, to_r)
                    uci_move = f"{chess.square_name(sq_from)}{chess.square_name(sq_to)}{piece}"
                    self.set_in_flight_move(from_c, from_r, to_c, to_r, uci_move)

                    self.lifted_square = None
                    self.legal_targets = []
                    self.legal_captures = []
                    self.invalid_placement = None
                    self.last_physical_state = [row[:] for row in physical_state]
                    return (from_c + 1, from_r + 1, to_c + 1, to_r + 1, piece)

            # 3. Check timeout: auto-queen
            elapsed = time.time() - start_time
            if elapsed >= timeout_s:
                logger.info(
                    f"Promotion timed out after {elapsed:.2f}s (>= {timeout_s}s). Auto-queening."
                )
                self.pending_promotion = None
                self.arrival_flash = {
                    "square": (to_c, to_r),
                    "start_time": time.time(),
                    "duration": ANIM_MOVE_CONFIRM_DURATION_S,
                    "is_capture": is_capture,
                }
                sq_from = chess.square(from_c, from_r)
                sq_to = chess.square(to_c, to_r)
                uci_move = f"{chess.square_name(sq_from)}{chess.square_name(sq_to)}q"
                self.set_in_flight_move(from_c, from_r, to_c, to_r, uci_move)

                self.lifted_square = None
                self.legal_targets = []
                self.legal_captures = []
                self.invalid_placement = None
                self.last_physical_state = [row[:] for row in physical_state]
                return (from_c + 1, from_r + 1, to_c + 1, to_r + 1, "q")

            # 4. Promotion still pending physical selection
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

                        promo_moves = [
                            m for m in board.legal_moves
                            if m.from_square == sq_from and m.to_square == sq_to and m.promotion
                        ]
                        if promo_moves:
                            is_white = (board.turn == chess.WHITE)
                            layout = compute_promotion_layout(t_c, t_r, is_white, physical_state)
                            self.pending_promotion = {
                                "from": (from_c, from_r),
                                "to": (t_c, t_r),
                                "color": "white" if is_white else "black",
                                "start_time": time.time(),
                                "timeout_s": 5.0,
                                "options": layout,
                                "is_capture": True,
                            }
                            logger.info(
                                f"Physical capture pawn promotion initiated: ({from_c},{from_r}) -> ({t_c},{t_r}). "
                                f"Layout options: {layout}"
                            )
                            self.lifted_square = None
                            self.legal_targets = []
                            self.legal_captures = []
                            self.pending_capture_target = None
                            self.capture_candidate_attackers = []
                            self.invalid_placement = None
                            self.last_physical_state = [row[:] for row in physical_state]
                            return None
                        else:
                            self.arrival_flash = {
                                "square": (t_c, t_r),
                                "start_time": time.time(),
                                "duration": ANIM_MOVE_CONFIRM_DURATION_S,
                                "is_capture": True,
                            }
                            promo = None
                            uci_move = f"{chess.square_name(sq_from)}{chess.square_name(sq_to)}"
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

                            if piece.piece_type == chess.KING:
                                self.king_lift_time = time.time()
                                self.resignation_armed = False
                                self.resignation_color = "white" if piece.color == chess.WHITE else "black"
                            else:
                                self.king_lift_time = None
                                self.resignation_armed = False
                                self.resignation_color = None

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

            # Check if King hold arming threshold is reached
            if self.king_lift_time is not None:
                elapsed_hold = time.time() - self.king_lift_time
                if elapsed_hold >= self.resignation_hold_duration and not self.resignation_armed:
                    self.resignation_armed = True
                    logger.info(
                        f"The King's Bow resignation gesture ARMED for {self.resignation_color} "
                        f"(held {elapsed_hold:.1f}s >= {self.resignation_hold_duration}s)."
                    )

            # 1. Returned to starting square -> Check King's Bow resignation or cancel move
            if physical_state[from_c][from_r] != 0:
                if self.resignation_armed and self.king_lift_time is not None:
                    resigning_color = self.resignation_color or ("white" if board.turn == chess.WHITE else "black")
                    elapsed_hold = time.time() - self.king_lift_time
                    logger.info(
                        f"The King's Bow gesture CONFIRMED! Player ({resigning_color}) yielded by placing King back after {elapsed_hold:.1f}s hold."
                    )
                    self.lifted_square = None
                    self.legal_targets = []
                    self.legal_captures = []
                    self.pending_capture_target = None
                    self.capture_candidate_attackers = []
                    self.invalid_placement = None
                    self.king_lift_time = None
                    self.resignation_armed = False
                    self.resignation_color = None
                    self.last_physical_state = [row[:] for row in physical_state]
                    return (0, 0, 0, 0, f"resign_{resigning_color}")

                logger.info(f"Piece returned to ({from_c},{from_r}). Move cancelled.")
                self.lifted_square = None
                self.legal_targets = []
                self.legal_captures = []
                self.pending_capture_target = None
                self.capture_candidate_attackers = []
                self.invalid_placement = None
                self.king_lift_time = None
                self.resignation_armed = False
                self.resignation_color = None
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

                    # Normal move cancels any pending resignation timers
                    self.king_lift_time = None
                    self.resignation_armed = False
                    self.resignation_color = None

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
                    if promo_moves:
                        is_white = (board.turn == chess.WHITE)
                        layout = compute_promotion_layout(t_c, t_r, is_white, physical_state)
                        self.pending_promotion = {
                            "from": (from_c, from_r),
                            "to": (t_c, t_r),
                            "color": "white" if is_white else "black",
                            "start_time": time.time(),
                            "timeout_s": 5.0,
                            "options": layout,
                            "is_capture": is_capture,
                        }
                        logger.info(
                            f"Pawn promotion initiated: ({from_c},{from_r}) -> ({t_c},{t_r}). "
                            f"Layout options: {layout}"
                        )
                        self.lifted_square = None
                        self.legal_targets = []
                        self.legal_captures = []
                        self.pending_capture_target = None
                        self.capture_candidate_attackers = []
                        self.invalid_placement = None
                        self.last_physical_state = [row[:] for row in physical_state]
                        return None

                    # Normal non-promotion move
                    self.arrival_flash = {
                        "square": (t_c, t_r),
                        "start_time": time.time(),
                        "duration": ANIM_MOVE_CONFIRM_DURATION_S,
                        "is_capture": is_capture,
                    }
                    promo = None
                    uci_move = f"{chess.square_name(sq_from)}{chess.square_name(sq_to)}"
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

            # 4. Check King tipped / laid to rest timeout (off board >= 5.0s without illegal placement)
            if self.king_lift_time is not None and not placed_illegally:
                elapsed_abandon = time.time() - self.king_lift_time
                if elapsed_abandon >= self.resignation_abandon_duration:
                    resigning_color = self.resignation_color or ("white" if board.turn == chess.WHITE else "black")
                    logger.info(
                        f"King tipped / laid to rest timeout reached ({elapsed_abandon:.1f}s >= {self.resignation_abandon_duration}s). "
                        f"Resignation CONFIRMED for {resigning_color}."
                    )
                    self.lifted_square = None
                    self.legal_targets = []
                    self.legal_captures = []
                    self.pending_capture_target = None
                    self.capture_candidate_attackers = []
                    self.invalid_placement = None
                    self.king_lift_time = None
                    self.resignation_armed = False
                    self.resignation_color = None
                    self.last_physical_state = [row[:] for row in physical_state]
                    return (0, 0, 0, 0, f"resign_{resigning_color}")

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
            "pending_promotion": (
                {
                    "from": list(self.pending_promotion["from"]),
                    "to": list(self.pending_promotion["to"]),
                    "color": self.pending_promotion["color"],
                    "start_time": self.pending_promotion.get("start_time", 0.0),
                    "timeout_s": self.pending_promotion.get("timeout_s", 5.0),
                    "options": {
                        k: list(v)
                        for k, v in self.pending_promotion.get("options", {}).items()
                    },
                    "is_capture": self.pending_promotion.get("is_capture", False),
                }
                if self.pending_promotion
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
            "resignation_armed": self.resignation_armed,
            "king_lift_elapsed": (
                round(time.time() - self.king_lift_time, 2)
                if self.king_lift_time is not None
                else None
            ),
        }
