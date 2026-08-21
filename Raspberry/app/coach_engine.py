"""
app/coach_engine.py

Asynchronous Stockfish AI Coach & Blunder Guard Engine for the Smart Chess Board.
Provides real-time non-blocking evaluation, multi-PV scoring, move delta classification,
evaluation caching, and cancellation on board position transitions.
Includes graceful heuristic fallback when Stockfish binary is absent.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
import logging
import math
import os
import shutil
from typing import Any, Dict, List, Optional

import chess
import chess.engine

logger = logging.getLogger("smart-chess-app.coach")

STOCKFISH_CANDIDATE_PATHS = [
    os.environ.get("STOCKFISH_PATH", ""),
    shutil.which("stockfish") or "",
    "/usr/games/stockfish",
    "/usr/bin/stockfish",
    "/usr/local/bin/stockfish",
    "/opt/homebrew/bin/stockfish",
]


class MoveQuality(str, Enum):
    BEST = "best"
    GOOD = "good"
    INACCURACY = "inaccuracy"
    BLUNDER = "blunder"


# Move quality delta thresholds in centipawns
TIER_BEST_MAX_LOSS = 10        # delta <= 10 cp -> BEST
TIER_GOOD_MAX_LOSS = 50        # 10 < delta <= 50 cp -> GOOD
TIER_INACCURACY_MAX_LOSS = 150 # 50 < delta <= 150 cp -> INACCURACY
                               # delta > 150 cp -> BLUNDER


def calculate_win_chance(score_cp: Optional[int], mate: Optional[int]) -> float:
    """
    Calculates non-linear win probability (0.0 to 100.0%) from White's perspective.
    Uses standard Lichess logistic winning probability formula.
    """
    if mate is not None:
        return 100.0 if mate > 0 else 0.0
    if score_cp is None:
        return 50.0
    # Logistic winning probability: 100 / (1 + 10^(-cp / 400))
    try:
        prob = 100.0 / (1.0 + math.pow(10.0, -score_cp / 400.0))
        return max(0.0, min(100.0, prob))
    except OverflowError:
        return 100.0 if score_cp > 0 else 0.0


def classify_move_delta(delta_cp: int, is_blunder_loss_of_mate: bool = False) -> MoveQuality:
    """Classifies centipawn loss delta into a MoveQuality tier."""
    if is_blunder_loss_of_mate:
        return MoveQuality.BLUNDER
    if delta_cp <= TIER_BEST_MAX_LOSS:
        return MoveQuality.BEST
    elif delta_cp <= TIER_GOOD_MAX_LOSS:
        return MoveQuality.GOOD
    elif delta_cp <= TIER_INACCURACY_MAX_LOSS:
        return MoveQuality.INACCURACY
    else:
        return MoveQuality.BLUNDER


@dataclass
class MoveAnalysis:
    uci: str
    from_sq: str
    to_sq: str
    classification: MoveQuality
    delta_cp: int
    score_cp: Optional[int] = None
    mate: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uci": self.uci,
            "from": self.from_sq,
            "to": self.to_sq,
            "classification": self.classification.value,
            "delta_cp": self.delta_cp,
            "score_cp": self.score_cp,
            "mate": self.mate,
        }


@dataclass
class BlunderChallenge:
    ply_index: int
    fen_before: str
    played_move: str
    classification: str
    delta_cp: int
    best_move: str
    best_score_cp: Optional[int]
    description: str
    top_moves: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ply_index": self.ply_index,
            "fen_before": self.fen_before,
            "played_move": self.played_move,
            "classification": self.classification,
            "delta_cp": self.delta_cp,
            "best_move": self.best_move,
            "best_score_cp": self.best_score_cp,
            "description": self.description,
            "top_moves": self.top_moves,
        }


@dataclass
class PositionEvaluation:
    fen: str
    score_cp: Optional[int]
    mate: Optional[int]
    win_chance: float           # 0.0 to 100.0%
    best_move: Optional[str]    # UCI e.g. "e2e4"
    top_moves: List[MoveAnalysis] = field(default_factory=list)
    moves_map: Dict[str, MoveAnalysis] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fen": self.fen,
            "score_cp": self.score_cp,
            "mate": self.mate,
            "win_chance": round(self.win_chance, 1),
            "best_move": self.best_move,
            "top_moves": [m.to_dict() for m in self.top_moves],
            "moves_map": {uci: m.to_dict() for uci, m in self.moves_map.items()},
        }


class HeuristicEvaluator:
    """Lightweight static evaluation engine used for offline fallback and fast tests."""
    PIECE_VALUES = {
        chess.PAWN: 100,
        chess.KNIGHT: 320,
        chess.BISHOP: 330,
        chess.ROOK: 500,
        chess.QUEEN: 900,
        chess.KING: 0,
    }

    def evaluate(self, board: chess.Board) -> int:
        """Returns centipawn evaluation from White's perspective."""
        if board.is_checkmate():
            return -10000 if board.turn == chess.WHITE else 10000
        if board.is_stalemate() or board.is_insufficient_material():
            return 0

        score = 0
        for sq, piece in board.piece_map().items():
            val = self.PIECE_VALUES.get(piece.piece_type, 0)
            file_idx = chess.square_file(sq)
            rank_idx = chess.square_rank(sq)
            center_bonus = 0
            if file_idx in [3, 4] and rank_idx in [3, 4]:
                center_bonus = 20
            elif file_idx in [2, 5] and rank_idx in [2, 5]:
                center_bonus = 10

            total_val = val + center_bonus
            if piece.color == chess.WHITE:
                score += total_val
            else:
                score -= total_val

        return score

    def get_top_moves(self, board: chess.Board, top_k: int = 5) -> List[MoveAnalysis]:
        """Generates ranked moves with heuristic scores and quality classifications."""
        legal = list(board.legal_moves)
        if not legal:
            return []

        scored_moves = []
        for move in legal:
            board.push(move)
            w_score = self.evaluate(board)
            board.pop()

            pov_score = w_score if board.turn == chess.WHITE else -w_score
            scored_moves.append((move, pov_score, w_score))

        scored_moves.sort(key=lambda x: x[1], reverse=True)
        best_pov = scored_moves[0][1]

        results = []
        for move, pov_score, w_score in scored_moves:
            delta = max(0, best_pov - pov_score)
            classification = classify_move_delta(delta)
            results.append(
                MoveAnalysis(
                    uci=move.uci(),
                    from_sq=chess.square_name(move.from_square),
                    to_sq=chess.square_name(move.to_square),
                    classification=classification,
                    delta_cp=delta,
                    score_cp=w_score,
                    mate=None,
                )
            )

        return results


class CoachEngine:
    """
    Manages background asynchronous Stockfish evaluation and move quality classification.
    Caches position results and cancels stale analysis on position changes.
    """

    def __init__(self, stockfish_path: Optional[str] = None):
        self.stockfish_path = stockfish_path or self._discover_stockfish()
        self._engine: Optional[chess.engine.UciProtocol] = None
        self._transport = None
        self._analysis_task: Optional[asyncio.Task] = None
        self._cache: Dict[str, PositionEvaluation] = {}
        self._max_cache_entries: int = 128
        self._is_running: bool = False
        self.is_heuristic_mode: bool = self.stockfish_path is None
        self.evaluator = HeuristicEvaluator()

    def _discover_stockfish(self) -> Optional[str]:
        for candidate in STOCKFISH_CANDIDATE_PATHS:
            if candidate and os.path.exists(candidate) and os.path.isfile(candidate):
                logger.info(f"Found Stockfish binary at: {candidate}")
                return candidate
        logger.info("Stockfish binary not found. Running CoachEngine in heuristic mode.")
        return None

    async def start(self):
        """Initializes the background UCI Stockfish process if available."""
        if self._is_running:
            return
        self._is_running = True

        if self.stockfish_path and not self._engine:
            try:
                transport, protocol = await chess.engine.popen_uci(self.stockfish_path)
                self._transport = transport
                self._engine = protocol
                self.is_heuristic_mode = False
                try:
                    # Optimize Stockfish for Raspberry Pi multi-core CPU & transposition table
                    await self._engine.configure({"Threads": 3, "Hash": 64})
                except Exception as e:
                    logger.debug(f"Could not configure Stockfish threads/hash: {e}")
                logger.info(f"Stockfish UCI engine started successfully ({self.stockfish_path}).")
            except Exception as e:
                logger.warning(f"Could not launch Stockfish ({self.stockfish_path}): {e}. Using heuristic fallback.")
                self._engine = None
                self.is_heuristic_mode = True
        else:
            self.is_heuristic_mode = True

    async def stop(self):
        """Terminates active analysis and closes the Stockfish process."""
        self._is_running = False
        if self._analysis_task and not self._analysis_task.done():
            self._analysis_task.cancel()
            try:
                await self._analysis_task
            except asyncio.CancelledError:
                pass

        if self._engine:
            try:
                await self._engine.quit()
            except Exception as e:
                logger.debug(f"Error quitting Stockfish: {e}")
            self._engine = None
            self._transport = None
        logger.info("CoachEngine stopped.")

    def get_cached_evaluation(self, fen: str) -> Optional[PositionEvaluation]:
        """Returns cached position evaluation for the given FEN if present."""
        clean_fen = " ".join(fen.split()[:4])
        return self._cache.get(clean_fen)

    async def evaluate_position(self, fen: str) -> PositionEvaluation:
        """Evaluates position with caching and cancellation."""
        clean_fen = " ".join(fen.split()[:4])
        if clean_fen in self._cache:
            return self._cache[clean_fen]

        board = chess.Board(fen)
        if not self._engine or self.is_heuristic_mode:
            result = self._evaluate_heuristic(board, clean_fen)
        else:
            result = await self._evaluate_stockfish(board, clean_fen)

        if len(self._cache) >= self._max_cache_entries:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        self._cache[clean_fen] = result
        return result

    def request_analysis(self, board: chess.Board):
        """Dispatches non-blocking async evaluation task for the board position."""
        clean_fen = " ".join(board.fen().split()[:4])
        if clean_fen in self._cache:
            return

        if self._analysis_task and not self._analysis_task.done():
            self._analysis_task.cancel()

        self._analysis_task = asyncio.create_task(self.evaluate_position(board.fen()))

    def _evaluate_heuristic(self, board: chess.Board, clean_fen: str) -> PositionEvaluation:
        """Evaluates position using static heuristic."""
        score_cp = self.evaluator.evaluate(board)
        win_chance = calculate_win_chance(score_cp, mate=None)
        top_moves = self.evaluator.get_top_moves(board, top_k=8)
        moves_map = {m.uci: m for m in top_moves}
        best_move = top_moves[0].uci if top_moves else None

        return PositionEvaluation(
            fen=clean_fen,
            score_cp=score_cp,
            mate=None,
            win_chance=win_chance,
            best_move=best_move,
            top_moves=top_moves,
            moves_map=moves_map,
        )

    async def _evaluate_stockfish(self, board: chess.Board, clean_fen: str) -> PositionEvaluation:
        """Evaluates position using Stockfish multi-PV analysis."""
        legal = list(board.legal_moves)
        if not legal:
            return self._evaluate_heuristic(board, clean_fen)

        multipv = min(len(legal), 8)
        limit = chess.engine.Limit(time=0.10, depth=12)

        try:
            infos = await self._engine.analyse(board, limit, multipv=multipv)
            if not isinstance(infos, list):
                infos = [infos]
        except Exception as e:
            logger.warning(f"Stockfish analysis failed: {e}. Falling back to heuristic.")
            return self._evaluate_heuristic(board, clean_fen)

        best_info = infos[0] if infos else {}
        best_score_pov = best_info.get("score")
        best_pv = best_info.get("pv", [])
        best_move = best_pv[0].uci() if best_pv else None

        if best_score_pov:
            score_white = best_score_pov.white()
            score_cp = score_white.score()
            mate = score_white.mate()
            win_chance = calculate_win_chance(score_cp, mate)
            best_pov_cp = best_score_pov.pov(board.turn).score(mate_score=10000) or 0
        else:
            score_cp = 0
            mate = None
            win_chance = 50.0
            best_pov_cp = 0

        top_moves = []
        moves_map = {}
        analyzed_ucis = set()

        for info in infos:
            pv = info.get("pv", [])
            if not pv:
                continue
            move = pv[0]
            uci = move.uci()
            analyzed_ucis.add(uci)

            move_score_pov = info.get("score")
            if move_score_pov:
                m_white = move_score_pov.white()
                m_score_cp = m_white.score()
                m_mate = m_white.mate()
                m_pov_cp = move_score_pov.pov(board.turn).score(mate_score=10000) or 0
                delta = max(0, best_pov_cp - m_pov_cp)
            else:
                m_score_cp = score_cp
                m_mate = mate
                delta = 0

            classification = classify_move_delta(delta)
            analysis = MoveAnalysis(
                uci=uci,
                from_sq=chess.square_name(move.from_square),
                to_sq=chess.square_name(move.to_square),
                classification=classification,
                delta_cp=delta,
                score_cp=m_score_cp,
                mate=m_mate,
            )
            top_moves.append(analysis)
            moves_map[uci] = analysis

        # Populate unanalyzed legal moves with blunder defaults
        for legal_move in legal:
            uci = legal_move.uci()
            if uci not in moves_map:
                analysis = MoveAnalysis(
                    uci=uci,
                    from_sq=chess.square_name(legal_move.from_square),
                    to_sq=chess.square_name(legal_move.to_square),
                    classification=MoveQuality.BLUNDER,
                    delta_cp=300,
                    score_cp=None,
                    mate=None,
                )
                moves_map[uci] = analysis

        return PositionEvaluation(
            fen=clean_fen,
            score_cp=score_cp,
            mate=mate,
            win_chance=win_chance,
            best_move=best_move,
            top_moves=top_moves,
            moves_map=moves_map,
        )

    async def batch_evaluate_game(self, moves_uci: List[str]) -> Dict[str, Any]:
        """
        Evaluates an entire sequence of game moves starting from standard FEN.
        Returns positions evaluations, played move classifications, accuracy scores, and mistake summaries.
        """
        board = chess.Board()
        evaluations: List[Dict[str, Any]] = []
        played_analyses: List[Dict[str, Any]] = []

        # Evaluate initial starting position
        initial_eval = await self.evaluate_position(board.fen())
        evaluations.append(initial_eval.to_dict())

        white_accuracies: List[float] = []
        black_accuracies: List[float] = []
        counts: Dict[str, Dict[str, int]] = {
            "white": {"best": 0, "good": 0, "inaccuracy": 0, "blunder": 0},
            "black": {"best": 0, "good": 0, "inaccuracy": 0, "blunder": 0},
        }

        for idx, uci in enumerate(moves_uci):
            try:
                move = chess.Move.from_uci(uci)
                if move not in board.legal_moves:
                    logger.warning(f"Illegal move {uci} at ply {idx} during batch analysis.")
                    break
            except Exception:
                logger.warning(f"Invalid UCI string {uci} at ply {idx}.")
                break

            prev_eval = evaluations[-1]
            turn = "white" if board.turn == chess.WHITE else "black"

            # Check played move analysis in the previous position
            moves_map = prev_eval.get("moves_map", {})
            move_info = moves_map.get(uci)
            if not move_info:
                board.push(move)
                after_eval = await self.evaluate_position(board.fen())
                board.pop()
                best_score = prev_eval.get("score_cp") or 0
                after_score = after_eval.score_cp or 0
                delta = max(0, (best_score - after_score) if turn == "white" else (after_score - best_score))
                classification = classify_move_delta(delta).value
                move_info = {
                    "uci": uci,
                    "from": chess.square_name(move.from_square),
                    "to": chess.square_name(move.to_square),
                    "classification": classification,
                    "delta_cp": delta,
                    "score_cp": after_score,
                }

            classification = move_info.get("classification", "good")
            if classification in counts[turn]:
                counts[turn][classification] += 1

            # Accuracy calculation
            delta_cp = move_info.get("delta_cp", 0)
            move_acc = max(0.0, min(100.0, 100.0 * math.exp(-0.004 * delta_cp)))
            if turn == "white":
                white_accuracies.append(move_acc)
            else:
                black_accuracies.append(move_acc)

            played_analyses.append({
                "ply": idx,
                "turn": turn,
                "uci": uci,
                "san": board.san(move),
                "from": move_info.get("from", ""),
                "to": move_info.get("to", ""),
                "classification": classification,
                "delta_cp": delta_cp,
                "best_move": prev_eval.get("best_move"),
            })

            board.push(move)
            pos_eval = await self.evaluate_position(board.fen())
            evaluations.append(pos_eval.to_dict())

        white_acc = round(sum(white_accuracies) / len(white_accuracies), 1) if white_accuracies else 100.0
        black_acc = round(sum(black_accuracies) / len(black_accuracies), 1) if black_accuracies else 100.0

        blunders = self.extract_blunders(played_analyses, evaluations)

        return {
            "evaluations": evaluations,
            "played_analyses": played_analyses,
            "white_accuracy": white_acc,
            "black_accuracy": black_acc,
            "counts": counts,
            "blunders": [b.to_dict() for b in blunders],
            "total_plys": len(played_analyses),
        }

    def extract_blunders(
        self,
        played_analyses: List[Dict[str, Any]],
        evaluations: List[Dict[str, Any]],
        min_delta: int = 100,
    ) -> List[BlunderChallenge]:
        """Extracts critical mistakes from played moves to form training puzzles."""
        challenges: List[BlunderChallenge] = []
        for played in played_analyses:
            ply = played["ply"]
            delta = played.get("delta_cp", 0)
            if delta >= min_delta or played.get("classification") == "blunder":
                pos_eval = evaluations[ply] if ply < len(evaluations) else {}
                best_move = played.get("best_move") or pos_eval.get("best_move") or ""
                if not best_move:
                    continue

                desc = f"At move {ply // 2 + 1} ({played['turn'].capitalize()}), {played['san']} lost {delta} centipawns. Find the better move!"
                challenges.append(
                    BlunderChallenge(
                        ply_index=ply,
                        fen_before=pos_eval.get("fen", ""),
                        played_move=played["uci"],
                        classification=played.get("classification", "blunder"),
                        delta_cp=delta,
                        best_move=best_move,
                        best_score_cp=pos_eval.get("score_cp"),
                        description=desc,
                        top_moves=pos_eval.get("top_moves", []),
                    )
                )
        return challenges


# Global singleton instance
coach_engine = CoachEngine()
