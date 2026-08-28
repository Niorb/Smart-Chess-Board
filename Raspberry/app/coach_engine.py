"""
app/coach_engine.py

Asynchronous Stockfish AI Coach & Blunder Guard Engine for the Smart Chess Board.
Provides real-time non-blocking evaluation, multi-PV scoring, move delta classification,
evaluation caching, automatic engine recovery, and persistent game-analysis caching.
Stockfish is mandatory: evaluation failures surface loudly instead of degrading silently.
"""

import asyncio
import contextlib
import hashlib
import json
import logging
import math
import os
import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

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


class CoachEngineUnavailable(RuntimeError):
    """Raised when Stockfish cannot be launched or fails repeatedly."""


def calculate_win_chance(score_cp: int | None, mate: int | None) -> float:
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
    score_cp: int | None = None
    mate: int | None = None

    def to_dict(self) -> dict[str, Any]:
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
    best_score_cp: int | None
    description: str
    player_color: str = "white"
    opponent_color: str = "black"
    opponent_prev_move_uci: str | None = None
    opponent_prev_move_san: str | None = None
    fen_prior_to_opponent: str | None = None
    solution_pv: list[str] = field(default_factory=list)
    solution_line_san: list[str] = field(default_factory=list)
    opponent_replies: list[str] = field(default_factory=list)
    player_moves: list[str] = field(default_factory=list)
    top_moves: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ply_index": self.ply_index,
            "fen_before": self.fen_before,
            "played_move": self.played_move,
            "classification": self.classification,
            "delta_cp": self.delta_cp,
            "best_move": self.best_move,
            "best_score_cp": self.best_score_cp,
            "description": self.description,
            "player_color": self.player_color,
            "opponent_color": self.opponent_color,
            "opponent_prev_move_uci": self.opponent_prev_move_uci,
            "opponent_prev_move_san": self.opponent_prev_move_san,
            "fen_prior_to_opponent": self.fen_prior_to_opponent,
            "solution_pv": self.solution_pv,
            "solution_line_san": self.solution_line_san,
            "opponent_replies": self.opponent_replies,
            "player_moves": self.player_moves,
            "top_moves": self.top_moves,
        }


@dataclass
class PositionEvaluation:
    fen: str
    score_cp: int | None
    mate: int | None
    win_chance: float           # 0.0 to 100.0%
    best_move: str | None    # UCI e.g. "e2e4"
    top_moves: list[MoveAnalysis] = field(default_factory=list)
    moves_map: dict[str, MoveAnalysis] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fen": self.fen,
            "score_cp": self.score_cp,
            "mate": self.mate,
            "win_chance": round(self.win_chance, 1),
            "best_move": self.best_move,
            "top_moves": [m.to_dict() for m in self.top_moves],
            "moves_map": {uci: m.to_dict() for uci, m in self.moves_map.items()},
        }


# =============================================================================
# PERSISTENT GAME-ANALYSIS CACHE (fast re-analysis across sessions)
# =============================================================================

ANALYSIS_CACHE_ENTRIES = 8


def _analysis_cache_path() -> str:
    try:
        from board_hardware import get_settings_filepath
        settings_dir = os.path.dirname(get_settings_filepath()) or "."
    except Exception:
        settings_dir = "."
    return os.path.join(settings_dir, "analysis_cache.json")


def analysis_cache_key(moves_uci: list[str]) -> str:
    return hashlib.sha1(" ".join(moves_uci).encode("utf-8")).hexdigest()


def load_cached_analysis(key: str) -> dict[str, Any] | None:
    """Returns the cached batch-analysis result for a game move list, if present."""
    path = _analysis_cache_path()
    try:
        with open(path) as f:
            data = json.load(f)
        entry = data.get("entries", {}).get(key)
        if entry and isinstance(entry.get("result"), dict):
            return entry
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"Could not read analysis cache: {e}")
    return None


def save_cached_analysis(key: str, moves_uci: list[str], result: dict[str, Any]) -> None:
    """Persists a completed batch analysis (LRU-capped, atomic write)."""
    path = _analysis_cache_path()
    data: dict[str, Any] = {"version": 1, "order": [], "entries": {}}
    try:
        if os.path.exists(path):
            with open(path) as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and isinstance(loaded.get("entries"), dict):
                data = loaded
                if not isinstance(data.get("order"), list):
                    data["order"] = list(data["entries"].keys())
    except Exception as e:
        logger.debug(f"Rewriting analysis cache after read error: {e}")

    entries = data["entries"]
    if key in data["order"]:
        data["order"].remove(key)
    data["order"].append(key)

    entries[key] = {"moves": list(moves_uci), "saved_at": time.time(), "result": result}
    while len(data["order"]) > ANALYSIS_CACHE_ENTRIES:
        oldest = data["order"].pop(0)
        entries.pop(oldest, None)

    tmp_path = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp_path, "w") as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception as e:
        logger.warning(f"Could not persist analysis cache: {e}")
        with contextlib.suppress(Exception):
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


class CoachEngine:
    """
    Manages background asynchronous Stockfish evaluation and move quality classification.
    Caches position results, never cancels in-flight engine commands, and automatically
    relaunches Stockfish if it dies. Evaluation requires Stockfish: failures raise
    CoachEngineUnavailable instead of silently degrading.
    """

    def __init__(self, stockfish_path: str | None = None):
        self.stockfish_path = stockfish_path or self._discover_stockfish() or ""
        self._engine: chess.engine.UciProtocol | None = None
        self._analysis_task: asyncio.Task | None = None
        self._pending_analysis_fen: str | None = None
        self._engine_lock: asyncio.Lock | None = None
        self._cache: dict[str, PositionEvaluation] = {}
        self._lines_cache: dict[str, list[dict[str, Any]]] = {}
        self._max_cache_entries: int = 128
        self._lines_task: asyncio.Task | None = None
        self._pending_lines_fen: str | None = None
        self._is_running: bool = False
        self._last_unavail_log: float = 0.0

    def _discover_stockfish(self) -> str | None:
        for candidate in STOCKFISH_CANDIDATE_PATHS:
            if candidate and os.path.exists(candidate) and os.path.isfile(candidate):
                logger.info(f"Found Stockfish binary at: {candidate}")
                return candidate
        logger.warning("Stockfish binary not found. Game analysis will be unavailable until it is installed.")
        return None

    @property
    def engine_available(self) -> bool:
        return self._engine is not None or bool(self.stockfish_path)

    async def ensure_engine(self) -> bool:
        """Launches the Stockfish process if not running. Returns True when available."""
        if self._engine is not None:
            return True

        if not self.stockfish_path:
            self.stockfish_path = self._discover_stockfish() or ""

        if not self.stockfish_path:
            return False

        try:
            _transport, protocol = await chess.engine.popen_uci(self.stockfish_path)
            self._engine = protocol
            try:
                # Optimize Stockfish for Raspberry Pi multi-core CPU & transposition table
                await self._engine.configure({"Threads": 3, "Hash": 64})
            except Exception as e:
                logger.debug(f"Could not configure Stockfish threads/hash: {e}")
            logger.info(f"Stockfish UCI engine started successfully ({self.stockfish_path}).")
            return True
        except Exception as e:
            logger.error(f"Could not launch Stockfish ({self.stockfish_path}): {e}")
            self._engine = None
            return False

    async def start(self):
        """Initializes the background UCI Stockfish process."""
        self._is_running = True
        await self.ensure_engine()

    async def _close_engine(self):
        """Terminates a misbehaving engine process so the next call can relaunch it."""
        engine = self._engine
        self._engine = None
        if engine is not None:
            with contextlib.suppress(Exception):
                await engine.quit()

    async def stop(self):
        """Terminates active analysis and closes the Stockfish process."""
        self._is_running = False
        self._pending_analysis_fen = None
        self._pending_lines_fen = None
        if self._analysis_task and not self._analysis_task.done():
            self._analysis_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._analysis_task
        self._analysis_task = None
        if self._lines_task and not self._lines_task.done():
            self._lines_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._lines_task
        self._lines_task = None
        await self._close_engine()
        logger.info("CoachEngine stopped.")

    def get_cached_evaluation(self, fen: str) -> PositionEvaluation | None:
        """Returns cached position evaluation for the given FEN if present."""
        clean_fen = " ".join(fen.split()[:4])
        return self._cache.get(clean_fen)

    def get_cached_lines(self, fen: str) -> list[dict[str, Any]] | None:
        """Returns cached PV lines for the given FEN if present."""
        clean_fen = " ".join(fen.split()[:4])
        return self._lines_cache.get(clean_fen)

    def request_lines(self, board: chess.Board) -> None:
        """Dispatches a non-blocking async computation of the top PV lines.

        Two-stage pipeline: the BEST line is computed and published first so the
        UI can show it right away (~80ms), then the full MultiPV=3 pass replaces it.
        Queues the latest target FEN so rapid moves/steps are never dropped.
        """
        clean_fen = " ".join(board.fen().split()[:4])
        if clean_fen in self._lines_cache:
            return
        self._pending_lines_fen = clean_fen
        task = self._lines_task
        if task is not None and not task.done():
            return
        try:
            self._lines_task = asyncio.create_task(self._lines_runner())
        except RuntimeError:
            return

    async def _lines_runner(self) -> None:
        """Processes pending lines requests without dropping rapid divergence moves."""
        while self._pending_lines_fen:
            target_fen = self._pending_lines_fen
            self._pending_lines_fen = None
            if target_fen in self._lines_cache:
                continue
            try:
                # Stage 1: best line only (fast publish ~80ms)
                quick = await self.compute_top_lines(target_fen, num_lines=1, depth=10, time_limit=0.10)
                if quick:
                    self._store_lines(target_fen, quick)

                # If user moved away while Stage 1 was computing, skip Stage 2 and move to the latest position
                if self._pending_lines_fen and self._pending_lines_fen != target_fen:
                    continue

                # Stage 2: all three lines (~250ms)
                full = await self.compute_top_lines(target_fen, num_lines=3, depth=10, time_limit=0.25)
                if full:
                    self._store_lines(target_fen, full)
            except Exception as e:
                logger.debug(f"PV lines computation failed for {target_fen}: {e}")

    def _store_lines(self, clean_fen: str, lines: list[dict[str, Any]]) -> None:
        if len(self._lines_cache) >= self._max_cache_entries:
            oldest_key = next(iter(self._lines_cache))
            del self._lines_cache[oldest_key]
        self._lines_cache[clean_fen] = lines

    async def compute_top_lines(
        self,
        fen: str,
        num_lines: int = 3,
        depth: int = 10,
        max_plies: int = 12,
        time_limit: float | None = 0.25,
    ) -> list[dict[str, Any]]:
        """Computes the top-N principal variations for a position with Stockfish.

        Returns [{uci: [move_uci...], san: [move_san...], score_cp, mate}] sorted
        best-first from the side-to-move's perspective (score_cp positive = good
        for the side to move). No caching — callers decide what to publish.
        """
        try:
            board = chess.Board(fen)
        except Exception:
            return []

        legal = list(board.legal_moves)
        if not legal:
            return []

        multipv = min(num_lines, len(legal))
        limit = (
            chess.engine.Limit(time=time_limit, depth=depth)
            if time_limit is not None
            else chess.engine.Limit(depth=depth)
        )
        infos = await self._analyse_with_recovery(board, limit, multipv)
        if not isinstance(infos, list):
            infos = [infos]

        lines: list[dict[str, Any]] = []
        for info in infos[:num_lines]:
            pv = info.get("pv", [])
            if not pv:
                continue
            pv = pv[:max_plies]
            uci_list = [m.uci() for m in pv]
            san_board = board.copy(stack=False)
            san_list: list[str] = []
            for m in pv:
                if m not in san_board.legal_moves:
                    break
                san_list.append(san_board.san(m))
                san_board.push(m)

            score_pov = info.get("score")
            score_cp: int | None = None
            mate: int | None = None
            if score_pov is not None:
                pov_score = score_pov.pov(board.turn)
                cp_raw = pov_score.score()
                mate = pov_score.mate()
                # Mate scores map to huge centipawn values so lines sort sensibly
                if cp_raw is not None:
                    score_cp = cp_raw
                else:
                    sign = -1 if (mate or 0) < 0 else 1
                    score_cp = sign * (10000 + abs(mate or 0) * 100)
            lines.append({
                "uci": uci_list,
                "san": san_list,
                "score_cp": score_cp,
                "mate": mate,
            })

        return lines

    async def get_top_lines(
        self,
        fen: str,
        num_lines: int = 3,
        depth: int = 10,
        max_plies: int = 12,
        time_limit: float | None = 0.25,
    ) -> list[dict[str, Any]]:
        """Computes (and caches) the top-N principal variations for a position."""
        clean_fen = " ".join(fen.split()[:4])
        cached = self._lines_cache.get(clean_fen)
        if cached is not None:
            return cached
        lines = await self.compute_top_lines(
            fen, num_lines=num_lines, depth=depth, max_plies=max_plies, time_limit=time_limit
        )
        self._store_lines(clean_fen, lines)
        return lines

    def request_analysis(self, board: chess.Board):
        """Dispatches non-blocking async evaluation for the board position.

        In-flight analyses are NEVER cancelled: cancelling a queued/in-flight UCI
        command corrupts the engine command state. Queues the latest target FEN
        so rapid divergence and navigation moves are always evaluated.
        """
        clean_fen = " ".join(board.fen().split()[:4])
        if clean_fen in self._cache:
            return

        self._pending_analysis_fen = clean_fen
        task = self._analysis_task
        if task is not None and not task.done():
            return

        try:
            self._analysis_task = asyncio.create_task(self._analysis_runner())
        except RuntimeError:
            return

    async def _analysis_runner(self) -> None:
        """Processes pending position analysis requests sequentially."""
        while self._pending_analysis_fen:
            target_fen = self._pending_analysis_fen
            self._pending_analysis_fen = None
            if target_fen in self._cache:
                continue
            try:
                await self.evaluate_position(target_fen)
            except Exception as exc:
                now = time.monotonic()
                if isinstance(exc, CoachEngineUnavailable):
                    if now - self._last_unavail_log > 30.0:
                        self._last_unavail_log = now
                        logger.warning(f"Position analysis skipped: {exc}")
                else:
                    logger.error(f"Background position analysis failed: {exc}")

    async def evaluate_position(self, fen: str) -> PositionEvaluation:
        """Evaluates a position with caching. Requires a working Stockfish engine."""
        clean_fen = " ".join(fen.split()[:4])
        if clean_fen in self._cache:
            return self._cache[clean_fen]

        board = chess.Board(fen)
        result = await self._evaluate_stockfish(board, clean_fen)

        if len(self._cache) >= self._max_cache_entries:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        self._cache[clean_fen] = result
        return result

    async def _analyse_with_recovery(self, board: chess.Board, limit, multipv: int):
        """Runs one multi-PV analyse, relaunching Stockfish once on engine failure."""
        for attempt in (1, 2):
            if not await self.ensure_engine():
                raise CoachEngineUnavailable(
                    "Stockfish binary unavailable. Install stockfish or set STOCKFISH_PATH."
                )
            try:
                if self._engine_lock is None:
                    self._engine_lock = asyncio.Lock()
                async with self._engine_lock:
                    return await self._engine.analyse(board, limit, multipv=multipv)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Stockfish analysis failed (attempt {attempt}): {e}. Relaunching engine.")
                await self._close_engine()
        raise CoachEngineUnavailable("Stockfish analysis failed twice; engine relaunched unsuccessfully.")

    async def _evaluate_stockfish(self, board: chess.Board, clean_fen: str) -> PositionEvaluation:
        """Evaluates position using Stockfish multi-PV analysis."""
        legal = list(board.legal_moves)
        if not legal:
            return PositionEvaluation(
                fen=clean_fen, score_cp=0, mate=None, win_chance=50.0,
                best_move=None, top_moves=[], moves_map={},
            )

        multipv = min(len(legal), 8)
        limit = chess.engine.Limit(time=0.10, depth=12)

        infos = await self._analyse_with_recovery(board, limit, multipv)
        if not isinstance(infos, list):
            infos = [infos]

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

        for info in infos:
            pv = info.get("pv", [])
            if not pv:
                continue
            move = pv[0]
            uci = move.uci()

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

    async def batch_evaluate_game(self, moves_uci: list[str]) -> dict[str, Any]:
        """
        Evaluates an entire sequence of game moves starting from standard FEN.
        Returns positions evaluations, played move classifications, accuracy scores,
        and mistake summaries. Requires Stockfish: raises CoachEngineUnavailable
        when the engine cannot analyze.
        """
        board = chess.Board()
        evaluations: list[dict[str, Any]] = []
        played_analyses: list[dict[str, Any]] = []

        # Evaluate initial starting position
        initial_eval = await self.evaluate_position(board.fen())
        evaluations.append(initial_eval.to_dict())

        white_accuracies: list[float] = []
        black_accuracies: list[float] = []
        counts: dict[str, dict[str, int]] = {
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
        played_analyses: list[dict[str, Any]],
        evaluations: list[dict[str, Any]],
        min_delta: int = 100,
    ) -> list[BlunderChallenge]:
        """Extracts critical mistakes from played moves to form training puzzles."""
        challenges: list[BlunderChallenge] = []
        for idx, played in enumerate(played_analyses):
            ply = played["ply"]
            delta = played.get("delta_cp", 0)
            if delta >= min_delta or played.get("classification") == "blunder":
                pos_eval = evaluations[ply] if ply < len(evaluations) else {}
                best_move = played.get("best_move") or pos_eval.get("best_move") or ""
                if not best_move:
                    continue

                player_color = str(played.get("turn", "white")).lower()
                opponent_color = "black" if player_color == "white" else "white"

                # Previous move from the side we don't play (leading into this puzzle position)
                opp_prev_uci = None
                opp_prev_san = None
                fen_prior = None
                if idx > 0 and idx - 1 < len(played_analyses):
                    prev_item = played_analyses[idx - 1]
                    opp_prev_uci = prev_item.get("uci")
                    opp_prev_san = prev_item.get("san")
                    if idx - 1 < len(evaluations):
                        fen_prior = evaluations[idx - 1].get("fen")

                fen_before = pos_eval.get("fen", "")
                top_moves = pos_eval.get("top_moves", [])

                # Extract PV moves and calculate full solution sequence
                pv_uci: list[str] = []
                if top_moves and "pv" in top_moves[0] and top_moves[0]["pv"]:
                    pv_uci = [str(x) for x in top_moves[0]["pv"]]
                elif best_move:
                    pv_uci = [best_move]

                solution_line_san: list[str] = []
                player_moves: list[str] = []
                opponent_replies: list[str] = []

                if fen_before and pv_uci:
                    try:
                        b = chess.Board(fen_before)
                        for i, uci_str in enumerate(pv_uci):
                            m = chess.Move.from_uci(uci_str)
                            if m in b.legal_moves:
                                san_str = b.san(m)
                                move_num = b.fullmove_number
                                prefix = f"{move_num}." if b.turn == chess.WHITE else f"{move_num}..."
                                solution_line_san.append(f"{prefix} {san_str}")
                                if i % 2 == 0:
                                    player_moves.append(uci_str)
                                else:
                                    opponent_replies.append(uci_str)
                                b.push(m)
                            else:
                                break
                    except Exception as e:
                        logger.debug(f"Error computing solution SAN: {e}")

                if not player_moves and best_move:
                    player_moves = [best_move]

                opp_context = f" after opponent's {opp_prev_san}" if opp_prev_san else ""
                desc = (
                    f"At move {ply // 2 + 1} ({player_color.capitalize()}){opp_context}, "
                    f"{played['san']} was a {played.get('classification', 'mistake')} (lost {delta} cp). "
                    f"Find the grandmaster refutation!"
                )

                challenges.append(
                    BlunderChallenge(
                        ply_index=ply,
                        fen_before=fen_before,
                        played_move=played["uci"],
                        classification=played.get("classification", "blunder"),
                        delta_cp=delta,
                        best_move=best_move,
                        best_score_cp=pos_eval.get("score_cp"),
                        description=desc,
                        player_color=player_color,
                        opponent_color=opponent_color,
                        opponent_prev_move_uci=opp_prev_uci,
                        opponent_prev_move_san=opp_prev_san,
                        fen_prior_to_opponent=fen_prior,
                        solution_pv=pv_uci,
                        solution_line_san=solution_line_san,
                        opponent_replies=opponent_replies,
                        player_moves=player_moves,
                        top_moves=top_moves,
                    )
                )
        return challenges


# Global singleton instance
coach_engine = CoachEngine()
