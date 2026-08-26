import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Chess } from 'chess.js';
import {
  Sparkles, 
  Trophy, 
  RotateCcw, 
  RefreshCw, 
  CheckCircle2, 
  ChevronLeft, 
  ChevronRight, 
  ChevronDown,
  ChevronUp,
  Layers, 
  Compass, 
  Lightbulb, 
  Flame, 
  TrendingUp,
  Brain,
  Eye,
  Globe,
  ExternalLink,
  Clock,
  PlayCircle,
  GraduationCap,
  Star,
  X
} from 'lucide-react';
import type { BoardState, GMGameSummary } from '../hooks/useBoardState';
import WebAnalysisBoard from './WebAnalysisBoard';
import { 
  startAnalysis, 
  stepAnalysis, 
  navAnalysis,
  sendAnalysisMove,
  resetAnalysisBranch, 
  stopAnalysis, 
  getGMGames, 
  startGMGame, 
  startReplayRecall, 
  startBlunderDrill, 
  submitBlunderAttempt, 
  toggleBlunderHint,
  getRecentLichessGames,
  type LichessRecentGame,
  getEndgameDrills,
  startEndgameDrill,
  stopEndgameDrill,
  requestEndgameHint,
  applyEndgameOpponentMove,
  createCustomEndgame,
  resetEndgameProgress,
  type EndgameDrillItem,
  type BlunderAttemptResult
} from '../api';

interface AnalysisTabProps {
  boardState: BoardState;
}

const AnalysisTab: React.FC<AnalysisTabProps> = ({ boardState }) => {
  const analysis = boardState.analysis;
  type SubMode = 'review' | 'blunder_drill' | 'replay' | 'endgame';
  const serverSubMode: SubMode =
    analysis?.submode === 'blunder_drill'
      ? 'blunder_drill'
      : analysis?.submode === 'endgame'
      ? 'endgame'
      : analysis?.submode?.startsWith('replay')
      ? 'replay'
      : 'review';
  // Local tab navigation with follow-the-server semantics: when the backend
  // submode changes (e.g. drill started via board gesture), the view follows.
  const [uiView, setUiView] = useState<{ server: SubMode; view: SubMode }>({
    server: serverSubMode,
    view: serverSubMode,
  });
  if (uiView.server !== serverSubMode) {
    setUiView({ server: serverSubMode, view: serverSubMode });
  }
  const subMode = uiView.view;
  const setSubMode = (view: SubMode) => setUiView((prev) => ({ ...prev, view }));
  const [gmGamesList, setGmGamesList] = useState<GMGameSummary[]>([]);
  const [selectedGMId, setSelectedGMId] = useState<string>('kasparov_topalov_1999');
  const [, setFeedbackMsg] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);
  const [guessInput, setGuessInput] = useState<string>('');
  const [puzzleResult, setPuzzleResult] = useState<BlunderAttemptResult | null>(null);
  const [showBlunderSolution, setShowBlunderSolution] = useState<boolean>(false);
  const [showEndgameSolution, setShowEndgameSolution] = useState<boolean>(false);
  const [webMoveInput, setWebMoveInput] = useState<string>('');
  const prevOnMainlineRef = useRef<boolean>(true);
  const [webBoardOpen, setWebBoardOpen] = useState<boolean>(false);

  // Endgame Academy State
  const [endgameDrills, setEndgameDrills] = useState<EndgameDrillItem[]>([]);
  const [selectedEndgameCategory, setSelectedEndgameCategory] = useState<string>('all');
  const [isCustomModalOpen, setIsCustomModalOpen] = useState<boolean>(false);
  const [customFenInput, setCustomFenInput] = useState<string>('');
  const [customTitleInput, setCustomTitleInput] = useState<string>('Custom Endgame');
  const [customGoalInput, setCustomGoalInput] = useState<'win' | 'draw' | 'mate'>('win');
  const [customColorInput, setCustomColorInput] = useState<'white' | 'black'>('white');
  const [customDescInput, setCustomDescInput] = useState<string>('');
  const [customHintInput, setCustomHintInput] = useState<string>('');
  const [, setIsLoadingEndgame] = useState<boolean>(false);

  const fetchEndgameDrills = useCallback(async () => {
    try {
      const data = await getEndgameDrills();
      if (Array.isArray(data)) {
        setEndgameDrills(data);
      }
    } catch (err) {
      console.error('Error fetching endgame drills:', err);
    }
  }, []);

  useEffect(() => {
    fetchEndgameDrills();
  }, [fetchEndgameDrills]);

  // Recent Lichess Games State
  const [recentGames, setRecentGames] = useState<LichessRecentGame[]>([]);
  const [isLoadingRecentGames, setIsLoadingRecentGames] = useState<boolean>(false);
  const [isRecentGamesOpen, setIsRecentGamesOpen] = useState<boolean>(true);
  const [selectedGameId, setSelectedGameId] = useState<string | null>(null);

  const fetchRecentGames = useCallback(async () => {
    setIsLoadingRecentGames(true);
    try {
      const res = await getRecentLichessGames(10);
      if (res && Array.isArray(res.games)) {
        setRecentGames(res.games);
      }
    } catch (err) {
      console.error('Error fetching recent Lichess games:', err);
    } finally {
      setIsLoadingRecentGames(false);
    }
  }, []);

  // Fetch recent games on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setIsLoadingRecentGames(true);
      try {
        const res = await getRecentLichessGames(10);
        if (!cancelled && res && Array.isArray(res.games)) {
          setRecentGames(res.games);
        }
      } catch (err) {
        console.error('Error fetching recent Lichess games:', err);
      } finally {
        if (!cancelled) setIsLoadingRecentGames(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Fetch GM games on mount
  useEffect(() => {
    let cancelled = false;
    getGMGames()
      .then((data) => {
        if (!cancelled && Array.isArray(data)) {
          setGmGamesList(data);
        }
      })
      .catch(() => console.error('Error fetching GM games'));
    return () => {
      cancelled = true;
    };
  }, []);

  const currentPly = analysis?.current_ply ?? 0;
  const totalPlys = analysis?.total_plys ?? 0;

  // --- Optimistic UI: apply navigation/moves locally for instant feedback ---
  // The backend remains the source of truth; the server payload simply
  // overwrites this overlay whenever it arrives (typically within ~100 ms).
  const [optimistic, setOptimistic] = useState<{
    fen: string | null;
    lastMoveUci: string | null;
    ply: number | null;
    branching: boolean | null;
    branchMoves: string[] | null;
    legalMoves: string[] | null;
    inCheck: boolean | null;
  }>({
    fen: null, lastMoveUci: null, ply: null,
    branching: null, branchMoves: null, legalMoves: null, inCheck: null,
  });
  const optimisticTimerRef = useRef<number | null>(null);
  // Reconcile the overlay against fresh server data. The overlay is dropped
  // ONLY when the server position has caught up with (or passed) it — dropping
  // it earlier would snap the board back to the pre-move position for a frame
  // until the WebSocket broadcast lands (the classic "move goes back and forth
  // once" glitch).
  const reconcileOptimistic = useCallback((serverFen: string | null) => {
    if (optimisticTimerRef.current) window.clearTimeout(optimisticTimerRef.current);
    optimisticTimerRef.current = null;
    setOptimistic((o) => {
      if (!o.fen || !serverFen) return o; // nothing pending, or no data to compare
      // FENs match modulo move counters → server caught up
      const strip = (f: string) => f.split(' ').slice(0, 4).join(' ');
      if (strip(o.fen) === strip(serverFen)) {
        return { fen: null, lastMoveUci: null, ply: null, branching: null, branchMoves: null, legalMoves: null, inCheck: null };
      }
      return o; // server still behind the optimistic state — keep showing it
    });
  }, []);
  // Hard rollback for rejected moves
  const clearOptimistic = useCallback(() => {
    if (optimisticTimerRef.current) window.clearTimeout(optimisticTimerRef.current);
    optimisticTimerRef.current = null;
    setOptimistic({ fen: null, lastMoveUci: null, ply: null, branching: null, branchMoves: null, legalMoves: null, inCheck: null });
  }, []);
  // When a new WS payload arrives, try reconciling against it
  useEffect(() => {
    if (optimistic.fen !== null && analysis?.fen) {
      reconcileOptimistic(analysis.fen);
    }
  }, [analysis?.fen, optimistic.fen, reconcileOptimistic]);
  // Safety net: never let a stale overlay linger if the WS is slow
  useEffect(() => {
    if (optimistic.fen === null) return;
    const t = window.setTimeout(clearOptimistic, 2500);
    return () => window.clearTimeout(t);
  }, [optimistic.fen, clearOptimistic]);

  /** Applies a UCI move to the given FEN locally with chess.js. */
  const applyUciLocally = useCallback((fen: string, uci: string): {
    fen: string; san: string | null; ok: boolean;
  } => {
    try {
      const g = new Chess(fen);
      const mv = g.move({
        from: uci.slice(0, 2),
        to: uci.slice(2, 4),
        promotion: uci.length > 4 ? uci[4] : undefined,
      });
      if (!mv) return { fen, san: null, ok: false };
      return { fen: g.fen(), san: mv.san, ok: true };
    } catch {
      return { fen, san: null, ok: false };
    }
  }, []);

  /** Rebuilds the position after `ply` mainline moves from the start. */
  const boardAtPly = useCallback((moves: string[], ply: number): string => {
    const g = new Chess();
    for (let i = 0; i < ply && i < moves.length; i++) {
      try { g.move(moves[i]); } catch { break; }
    }
    return g.fen();
  }, []);

  // Merge the optimistic overlay over the server analysis payload
  const effFen = optimistic.fen ?? analysis?.fen ?? '';
  const effLastMove = optimistic.lastMoveUci
    ?? (analysis?.is_branching
      ? analysis?.branch_moves?.[analysis.branch_moves.length - 1] ?? null
      : currentPly > 0 ? analysis?.game_moves?.[currentPly - 1] ?? null : null);
  const effBranching = optimistic.branching ?? !!analysis?.is_branching;
  const playedAnalyses = analysis?.played_analyses ?? [];
  const evaluations = useMemo(() => analysis?.evaluations ?? [], [analysis]);
  const blunders = analysis?.blunders ?? [];
  const activeBlunderIndex = analysis?.blunder_index ?? 0;
  const currentBlunder = blunders[activeBlunderIndex];

  // Replay Trainer state
  const replay = analysis?.replay;
  const replayPhase = replay?.phase ?? null;
  const learnedPly = replay?.learned_ply ?? 0;
  const replayResults = replay?.results ?? [];
  const replayMistakes = replay?.mistakes ?? 0;
  const replayComplete = replay?.complete ?? false;
  const replayReveal = replay?.reveal_uci ?? null;
  const correctRecalls = replayResults.filter((r) => r.correct).length;
  const resultByPly = useMemo(() => {
    const map: Record<number, boolean> = {};
    for (const r of replayResults) map[r.ply] = r.correct;
    return map;
  }, [replayResults]);

  // SVG Evaluation Curve calculations
  const evalPoints = useMemo(() => {
    if (!evaluations.length) return [];
    return evaluations.map((ev, idx) => {
      const winChance = ev.win_chance ?? 50.0;
      // Map win chance (0..100) to SVG Y coordinate (height 140, padded 10..130)
      const y = 130 - (winChance / 100) * 120;
      return { ply: idx, y, winChance, score_cp: ev.score_cp, mate: ev.mate };
    });
  }, [evaluations]);

  const handleStartAnalysis = async () => {
    setFeedbackMsg({ text: 'Analyzing game with Stockfish...', type: 'info' });
    try {
      await startAnalysis();
      setFeedbackMsg({ text: 'Game analysis ready!', type: 'success' });
      setTimeout(() => setFeedbackMsg(null), 3000);
    } catch {
      setFeedbackMsg({ text: 'Failed to start analysis.', type: 'error' });
    }
  };

  // Dedicated webapp-only analysis: runs the same engine but the physical board
  // is never used; opens the interactive web board when done.
  const handleStartWebAnalysis = async (opts?: { moves_uci?: string[] }) => {
    setWebBoardOpen(true);
    setFeedbackMsg({ text: 'Analyzing game with Stockfish (webapp only)...', type: 'info' });
    try {
      await startAnalysis({ ...opts, web_only: true });
      prevOnMainlineRef.current = true;
      setFeedbackMsg({ text: 'Analysis ready — use ← → / h l on the board below.', type: 'success' });
      setTimeout(() => setFeedbackMsg(null), 3500);
    } catch {
      setFeedbackMsg({ text: 'Failed to start analysis.', type: 'error' });
    }
  };

  const handleLoadRecentGame = async (game: LichessRecentGame) => {
    setSelectedGameId(game.id);
    // Loads the selected online match into a webapp-only analysis session
    await handleStartWebAnalysis({ moves_uci: game.moves_uci });
    setFeedbackMsg({
      text: `Match vs ${game.opponent.username} loaded into the web board! (${game.moves_count} moves)`,
      type: 'success',
    });
    setTimeout(() => setFeedbackMsg(null), 3500);
  };

  // Loads the selected online match onto the PHYSICAL board (LED traces,
  // piece-by-piece stepping) instead of the webapp-only sandbox.
  const handleLoadRecentGameOnBoard = async (game: LichessRecentGame) => {
    setSelectedGameId(game.id);
    setWebBoardOpen(false);
    setFeedbackMsg({ text: `Loading match vs ${game.opponent.username} onto the physical board...`, type: 'info' });
    try {
      await startAnalysis({ moves_uci: game.moves_uci });
      setFeedbackMsg({
        text: `Match vs ${game.opponent.username} loaded on the physical board — step with ← → or follow the LED cues.`,
        type: 'success',
      });
    } catch {
      setFeedbackMsg({ text: 'Failed to start board analysis.', type: 'error' });
    }
    setTimeout(() => setFeedbackMsg(null), 4000);
  };

  const handleStep = async (ply: number) => {
    try {
      await stepAnalysis(ply);
    } catch (err) {
      console.error('Error stepping analysis:', err);
    }
  };

  // --- Web-only keyboard navigation (arrows + vim keys) ---
  const handleNav = useCallback(async (direction: 'back' | 'forward' | 'start' | 'end') => {
    if (!analysis?.active || analysis.submode !== 'review') return;
    const gameMoves = analysis.game_moves ?? [];
    const branched = !!analysis.is_branching;

    // --- Optimistic local application (instant visual feedback) ---
    try {
      if (direction === 'back') {
        if (branched) {
          // Un-play one branch move locally
          const anchorPly = analysis.anchor_ply ?? currentPly;
          const rebuilt = boardAtPly(gameMoves, anchorPly);
          const branchMoves = analysis.branch_moves ?? [];
          let f = rebuilt;
          for (let i = 0; i < branchMoves.length - 1; i++) {
            f = applyUciLocally(f, branchMoves[i]).fen;
          }
          setOptimistic((o) => ({
            ...o,
            fen: f,
            lastMoveUci: branchMoves.length > 1 ? branchMoves[branchMoves.length - 2] : null,
            branching: branchMoves.length > 1,
            legalMoves: new Chess(f).moves(),
            inCheck: new Chess(f).inCheck(),
          }));
        } else if (currentPly > 0) {
          const np = currentPly - 1;
          const f = boardAtPly(gameMoves, np);
          setOptimistic((o) => ({
            ...o,
            fen: f,
            ply: np,
            lastMoveUci: np > 0 ? gameMoves[np - 1] : null,
            branching: false,
            legalMoves: new Chess(f).moves(),
            inCheck: new Chess(f).inCheck(),
          }));
        }
      } else if (direction === 'forward' && !branched && currentPly < totalPlys) {
        const res = applyUciLocally(
          optimistic.fen ?? boardAtPly(gameMoves, currentPly),
          gameMoves[currentPly],
        );
        if (res.ok) {
          setOptimistic((o) => ({
            ...o,
            fen: res.fen,
            ply: currentPly + 1,
            lastMoveUci: gameMoves[currentPly],
            branching: false,
            legalMoves: new Chess(res.fen).moves(),
            inCheck: new Chess(res.fen).inCheck(),
          }));
        }
      } else if (direction === 'start' || direction === 'end') {
        const np = direction === 'start' ? 0 : totalPlys;
        const f = boardAtPly(gameMoves, np);
        setOptimistic((o) => ({
          ...o,
          fen: f,
          ply: np,
          lastMoveUci: np > 0 ? gameMoves[np - 1] : null,
          branching: false,
          legalMoves: new Chess(f).moves(),
          inCheck: new Chess(f).inCheck(),
        }));
      }
    } catch {
      // Optimistic application is best-effort only
    }

    // --- Backend dispatch (source of truth; WS payload reconciles) ---
    try {
      const res = await navAnalysis(direction);
      prevOnMainlineRef.current = !!res?.on_mainline;
      const serverFen = (res as { analysis?: { fen?: string } } | null)?.analysis?.fen ?? null;
      reconcileOptimistic(serverFen);
    } catch (err) {
      console.error('Error navigating analysis:', err);
      clearOptimistic();
    }
  }, [analysis, currentPly, totalPlys, optimistic.fen, applyUciLocally, boardAtPly, reconcileOptimistic, clearOptimistic]);

  useEffect(() => {
    if (subMode !== 'review' || !analysis?.active) return;
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
      switch (e.key) {
        case 'ArrowRight':
        case 'l':
          e.preventDefault();
          handleNav('forward');
          break;
        case 'ArrowLeft':
        case 'h':
          e.preventDefault();
          handleNav('back');
          break;
        case 'Home':
        case 'g':
          e.preventDefault();
          handleNav('start');
          break;
        case 'End':
        case 'G':
          e.preventDefault();
          handleNav('end');
          break;
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [subMode, analysis?.active, handleNav]);

  // --- Web move playback (diverge from the main line without the board) ---
  const handleWebMove = useCallback(async (moveText: string) => {
    const mv = moveText.trim();
    if (!mv || !analysis?.active || analysis.submode !== 'review') return;

    // --- Optimistic local application (instant visual feedback) ---
    try {
      const baseFen = optimistic.fen ?? analysis.fen ?? '';
      // Normalize SAN to UCI against the current position
      let uci: string | null = null;
      try {
        uci = new Chess(baseFen).move(mv).lan;
      } catch { /* not legal */ }
      if (!uci && /^[a-h][1-8][a-h][1-8][qrbn]?$/.test(mv)) {
        const probe = applyUciLocally(baseFen, mv);
        if (probe.ok) { uci = mv; }
      }
      if (uci) {
        const res = applyUciLocally(baseFen, uci);
        if (res.ok) {
          setOptimistic((o) => ({
            ...o,
            fen: res.fen,
            lastMoveUci: uci,
            branching: true,
            branchMoves: [...(analysis.branch_moves ?? []), uci!],
            legalMoves: new Chess(res.fen).moves(),
            inCheck: new Chess(res.fen).inCheck(),
          }));
        }
      }
    } catch {
      // best-effort
    }

    // --- Backend dispatch (source of truth; WS payload reconciles) ---
    try {
      const res = await sendAnalysisMove(mv);
      const result = (res as { result?: { action?: string; analysis?: { is_branching?: boolean } } })?.result
        ?? (res as { action?: string; analysis?: { is_branching?: boolean } });
      if (!result || result.action === 'illegal' || result.action === 'error') {
        clearOptimistic();  // roll back the optimistic move
        setFeedbackMsg({ text: `Illegal or unparsable move: "${mv}"`, type: 'error' });
        setTimeout(() => setFeedbackMsg(null), 3000);
        return;
      }
      prevOnMainlineRef.current = !result.analysis?.is_branching;
      setWebMoveInput('');
      reconcileOptimistic((result.analysis as { fen?: string } | null | undefined)?.fen ?? null);
    } catch (err) {
      console.error('Error playing web analysis move:', err);
      clearOptimistic();
    }
  }, [analysis, optimistic.fen, applyUciLocally, reconcileOptimistic, clearOptimistic]);

  // Suggested better move after a suboptimal mainline move (arrow on board).
  // Clicking it steps back and plays the engine's suggestion as a variation,
  // which re-engages Stockfish to evaluate the new line.
  const lastPlayedInfo = currentPly > 0 ? playedAnalyses[currentPly - 1] : null;
  const suggestMove = !analysis?.is_branching &&
    ['inaccuracy', 'mistake', 'blunder'].includes(lastPlayedInfo?.classification ?? '')
    ? lastPlayedInfo?.best_move ?? null
    : null;

  const handleSuggestionClick = useCallback(async () => {
    const info = currentPly > 0 ? playedAnalyses[currentPly - 1] : null;
    if (!info?.best_move) return;
    try {
      await stepAnalysis(currentPly - 1);            // return to the pre-move position
      prevOnMainlineRef.current = false;
      await sendAnalysisMove(info.best_move);        // play suggestion -> branch + fresh eval
      setFeedbackMsg({ text: `Engine suggestion ${info.best_move} played — Stockfish evaluating the new line…`, type: 'info' });
      setTimeout(() => setFeedbackMsg(null), 3200);
    } catch (err) {
      console.error('Error playing suggested move:', err);
    }
  }, [currentPly, playedAnalyses]);

  const handleResetBranch = async () => {
    try {
      await resetAnalysisBranch();
      setFeedbackMsg({ text: 'Restored main game timeline.', type: 'info' });
      setTimeout(() => setFeedbackMsg(null), 2500);
    } catch (err) {
      console.error('Error resetting branch:', err);
    }
  };

  // Follow an engine line: step back to the current position's start, then play
  // the line's first move as a variation (the engine keeps computing down it).
  const handleLineClick = useCallback(async (lineIndex: number) => {
    if (!analysis?.active || analysis.submode !== 'review') return;
    const line = analysis.top_lines?.[lineIndex];
    const firstMove = line?.uci?.[0];
    if (!firstMove || firstMove.length < 4) return;
    try {
      // If we're mid-variation, snap back to the mainline anchor first so the
      // clicked line is played from the position it was computed for.
      if (analysis.is_branching) {
        await resetAnalysisBranch();
      }
      prevOnMainlineRef.current = false;
      await sendAnalysisMove(firstMove);
    } catch (err) {
      console.error('Error following engine line:', err);
    }
  }, [analysis?.active, analysis?.submode, analysis?.is_branching, analysis?.top_lines]);

  const handleStartGM = async (gameId: string) => {
    setSelectedGMId(gameId);
    setFeedbackMsg({ text: 'Loading Grandmaster masterpiece...', type: 'info' });
    try {
      await startGMGame(gameId);
      setFeedbackMsg({ text: 'Learn phase started! Play the highlighted moves on the board.', type: 'success' });
      setTimeout(() => setFeedbackMsg(null), 3500);
    } catch {
      setFeedbackMsg({ text: 'Failed to load GM game.', type: 'error' });
    }
  };

  const handleStartReplayRecall = async () => {
    setFeedbackMsg({ text: 'Starting memory recall of your last game...', type: 'info' });
    try {
      const res = await startReplayRecall();
      const errText = (res as { error?: string })?.error;
      if (errText) {
        setFeedbackMsg({ text: errText, type: 'error' });
        setTimeout(() => setFeedbackMsg(null), 4000);
      } else {
        setFeedbackMsg({ text: 'Memory recall started — replay your last game from memory!', type: 'success' });
        setTimeout(() => setFeedbackMsg(null), 3500);
      }
    } catch {
      setFeedbackMsg({ text: 'Failed to start memory recall.', type: 'error' });
    }
  };

  const handleStartBlunderDrill = async (idx: number) => {
    setPuzzleResult(null);
    setGuessInput('');
    try {
      await startBlunderDrill(idx);
    } catch (err) {
      console.error('Error starting blunder drill:', err);
    }
  };

  const handlePuzzleMove = async (uciOrSan: string) => {
    if (!uciOrSan.trim()) return;
    try {
      const res = await submitBlunderAttempt(uciOrSan.trim());
      setPuzzleResult(res);
      if (res.correct) {
        if (res.puzzle_complete) {
          setFeedbackMsg({ text: `🏆 ${res.message}`, type: 'success' });
        } else {
          setFeedbackMsg({ text: `⚡ ${res.message}`, type: 'info' });
        }
      } else {
        setFeedbackMsg({ text: `❌ ${res.message} (${res.attempts_remaining ?? 0} attempts left)`, type: 'error' });
      }
      setGuessInput('');
    } catch {
      setFeedbackMsg({ text: 'Error submitting puzzle move.', type: 'error' });
    }
  };

  const handleBlunderAttemptSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!guessInput.trim()) return;
    await handlePuzzleMove(guessInput.trim());
  };

  const handleToggleHint = async () => {
    try {
      const res = await toggleBlunderHint();
      setFeedbackMsg({ 
        text: res.active ? '💡 Move origin highlighted in Mint Emerald on the board.' : 'Hint turned off.', 
        type: 'info' 
      });
      setTimeout(() => setFeedbackMsg(null), 3000);
    } catch (err) {
      console.error('Error toggling hint:', err);
    }
  };

  const handleStartEndgame = async (drillId?: string) => {
    setIsLoadingEndgame(true);
    setFeedbackMsg({ text: 'Starting Endgame Tablebase drill...', type: 'info' });
    try {
      await startEndgameDrill({ drill_id: drillId });
      setFeedbackMsg({ text: 'Phase 1: Place White pieces on the board according to their colors.', type: 'success' });
      setTimeout(() => setFeedbackMsg(null), 4000);
      await fetchEndgameDrills();
    } catch (err) {
      setFeedbackMsg({ text: 'Failed to start endgame drill.', type: 'error' });
    } finally {
      setIsLoadingEndgame(false);
    }
  };

  const handleStopEndgame = async () => {
    try {
      await stopEndgameDrill();
      setFeedbackMsg({ text: 'Endgame drill stopped. Board returned to IDLE.', type: 'info' });
      setTimeout(() => setFeedbackMsg(null), 2500);
      await fetchEndgameDrills();
    } catch (err) {
      console.error('Error stopping endgame drill:', err);
    }
  };

  const handleRequestEndgameHint = async () => {
    try {
      const res = await requestEndgameHint();
      if (res.hint_uci) {
        setFeedbackMsg({ text: `💡 Best move hint: ${res.hint_uci} (highlighted on the board)`, type: 'info' });
      } else if (res.hint_text) {
        setFeedbackMsg({ text: `💡 Hint: ${res.hint_text}`, type: 'info' });
      }
      setTimeout(() => setFeedbackMsg(null), 5000);
    } catch (err) {
      console.error('Error requesting endgame hint:', err);
    }
  };

  const handleApplyEndgameOpponentMove = async () => {
    try {
      await applyEndgameOpponentMove();
    } catch (err) {
      console.error('Error applying opponent move:', err);
    }
  };

  const handleCreateCustomEndgame = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customFenInput.trim()) return;
    try {
      await createCustomEndgame({
        fen: customFenInput.trim(),
        title: customTitleInput.trim() || 'Custom Endgame',
        player_color: customColorInput,
        target_goal: customGoalInput,
        description: customDescInput.trim(),
        hint: customHintInput.trim(),
      });
      setIsCustomModalOpen(false);
      setCustomFenInput('');
      setFeedbackMsg({ text: 'Custom endgame started!', type: 'success' });
      setTimeout(() => setFeedbackMsg(null), 3000);
      await fetchEndgameDrills();
    } catch (err) {
      setFeedbackMsg({ text: 'Failed to create custom endgame drill. Check FEN notation.', type: 'error' });
    }
  };

  const handleResetEndgameProgress = async () => {
    if (!window.confirm('Reset all Endgame Academy stars and progress?')) return;
    try {
      await resetEndgameProgress();
      setFeedbackMsg({ text: 'Endgame progress reset.', type: 'info' });
      setTimeout(() => setFeedbackMsg(null), 2500);
      await fetchEndgameDrills();
    } catch (err) {
      console.error('Error resetting endgame progress:', err);
    }
  };

  const getQualityBadge = (tier?: string) => {
    switch (tier) {
      case 'best':
        return <span title="Best Move (Δ ≤ 15 cp)" className="px-2 py-0.5 text-xs font-bold rounded bg-emerald-950/90 text-emerald-300 border border-emerald-500/40 shadow-sm">BEST</span>;
      case 'good':
        return <span title="Good Move (15 < Δ ≤ 60 cp)" className="px-2 py-0.5 text-xs font-bold rounded bg-cyan-950/90 text-cyan-300 border border-cyan-500/40 shadow-sm">GOOD</span>;
      case 'inaccuracy':
        return <span title="Inaccuracy (60 < Δ ≤ 150 cp)" className="px-2 py-0.5 text-xs font-bold rounded bg-amber-950/90 text-amber-300 border border-amber-500/40 shadow-sm">INACC</span>;
      case 'blunder':
        return <span title="Blunder (Δ > 150 cp)" className="px-2 py-0.5 text-xs font-bold rounded bg-rose-950/90 text-rose-300 border border-rose-500/40 shadow-sm">BLUNDER</span>;
      default:
        return <span className="px-2 py-0.5 text-xs font-bold rounded bg-slate-800 text-slate-400">MOVE</span>;
    }
  };

  // Chess.com-style color coding for played moves in notation lists
  const getMoveTileStyle = (tier?: string): string => {
    switch (tier) {
      case 'best':
        return 'bg-emerald-600/80 text-white border-emerald-400/50';
      case 'good':
        return 'bg-teal-500/50 text-teal-100 border-teal-300/40';
      case 'inaccuracy':
        return 'bg-yellow-500/60 text-yellow-950 border-yellow-300/50';
      case 'mistake':
        return 'bg-orange-500/70 text-white border-orange-300/50';
      case 'blunder':
        return 'bg-red-600/80 text-white border-red-400/50';
      default:
        return 'bg-slate-800/80 text-slate-200 border-slate-700';
    }
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Top Banner Navigation */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-xl backdrop-blur flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-violet-600/20 border border-violet-500/30 rounded-xl text-violet-400">
            <Compass className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              Analysis & Training Laboratory
              <span className="px-2 py-0.5 text-xs rounded-full bg-violet-500/20 text-violet-300 border border-violet-500/30">
                Cyber-Physical
              </span>
            </h2>
            <p className="text-xs text-slate-400">
              Interactive post-game review, blunder rehabilitation drills, and memory-training game replays.
            </p>
            {analysis?.error && (
              <div className="mt-3 px-3 py-2 rounded-lg bg-rose-950/70 border border-rose-700/60 text-xs text-rose-300">
                {analysis.error}
              </div>
            )}
          </div>
        </div>

        {/* Submode Selector */}
        <div className="flex items-center bg-slate-950/80 p-1.5 rounded-xl border border-slate-800">
          <button
            onClick={() => setSubMode('review')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
              subMode === 'review'
                ? 'bg-violet-600 text-white shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            Game Review
          </button>
          <button
            onClick={() => {
              setSubMode('blunder_drill');
              if (blunders.length > 0) startBlunderDrill(0);
            }}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
              subMode === 'blunder_drill'
                ? 'bg-rose-600 text-white shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Flame className="w-3.5 h-3.5" />
            Blunder Blitz ({blunders.length})
          </button>
          <button
            onClick={() => setSubMode('replay')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
              subMode === 'replay'
                ? 'bg-amber-600 text-white shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Brain className="w-3.5 h-3.5" />
            Replay Trainer
          </button>
          <button
            onClick={() => {
              setSubMode('endgame');
              fetchEndgameDrills();
            }}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
              subMode === 'endgame'
                ? 'bg-emerald-600 text-white shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <GraduationCap className="w-3.5 h-3.5" />
            Endgame Academy
          </button>
        </div>
      </div>

      {/* SUB-VIEW 1: GAME REVIEW ("The Grandmaster's Lens") */}
      {subMode === 'review' && (
        <div className="space-y-6">
          {/* Webapp-Only Analysis Launcher & Interactive Board */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-xl flex flex-col md:flex-row items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-emerald-600/20 border border-emerald-500/30 rounded-xl text-emerald-400">
                <Brain className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">Analyse in Webapp</h3>
                <p className="text-xs text-slate-400">
                  Same Stockfish engine, fully virtual — navigate with your keyboard, the physical board stays untouched.
                </p>
              </div>
            </div>
            <button
              onClick={() => handleStartWebAnalysis()}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold transition-all shadow-md flex items-center gap-1.5 shrink-0"
            >
              {analysis?.active ? 'Restart in Webapp' : 'Analyse in Webapp'}
            </button>
          </div>

          {/* Interactive web board (keyboard navigation lives here) */}
          {webBoardOpen &&
            (analysis?.active ? (
              (() => {
                const isBranching = effBranching;
                const lastMoveUci = effLastMove;
                // Always-on eval bar data (independent of play-section settings).
                // While in a variation sandbox, current_eval carries the LIVE
                // Stockfish evaluation of the branch position and must take
                // precedence over the mainline evaluation at the anchor ply.
                const posEval = analysis?.evaluations?.[currentPly];
                const liveEval = analysis?.current_eval;
                const evalSource = (isBranching && liveEval ? liveEval : null)
                  ?? posEval
                  ?? liveEval;
                const winChance = evalSource?.win_chance ?? 50;
                const scoreCp = evalSource?.score_cp ?? null;
                const mate = evalSource?.mate ?? null;
                // Classification of the last mainline move (colors the highlight)
                const lastMoveClass = !isBranching && currentPly > 0
                  ? playedAnalyses[currentPly - 1]?.classification ?? null
                  : null;
                return (
                  <WebAnalysisBoard
                    fen={effFen}
                    legalMoves={optimistic.legalMoves ?? analysis?.legal_moves ?? []}
                    inCheck={optimistic.inCheck ?? !!analysis?.in_check}
                    lastMoveUci={lastMoveUci}
                    lastMoveClass={lastMoveClass}
                    isBranching={isBranching}
                    winChance={winChance}
                    scoreCp={scoreCp}
                    mate={mate}
                    onMovePlayed={handleWebMove}
                    onSuggestionClick={handleSuggestionClick}
                    suggestMove={suggestMove}
                    myColor={boardState.my_color === 'black' ? 'black' : 'white'}
                    topLines={analysis?.top_lines ?? null}
                    onLineClick={handleLineClick}
                  />
                );
              })()
            ) : (
              <div className="bg-slate-900/60 border border-dashed border-slate-700 rounded-2xl p-6 text-center text-xs text-slate-400">
                No analysis running yet — click "Analyse in Webapp" to load your last game.
              </div>
            ))}

          {/* Lichess Recent Games Selector (Last 10 Matches) */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
            <div className="p-4 bg-slate-950/60 border-b border-slate-800/80 flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-600/20 border border-blue-500/30 rounded-xl text-blue-400">
                  <Globe className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    Recent Lichess Matches
                    <span className="px-2 py-0.5 text-[10px] rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30">
                      {recentGames.length} Online Games
                    </span>
                  </h3>
                  <p className="text-xs text-slate-400">
                    Select any of your last 10 online matches to load it into the interactive web board (Stockfish review, keyboard navigation).
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={fetchRecentGames}
                  disabled={isLoadingRecentGames}
                  className="p-2 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:border-slate-700 transition-all disabled:opacity-50"
                  title="Refresh Lichess Games"
                >
                  <RefreshCw className={`w-4 h-4 ${isLoadingRecentGames ? 'animate-spin text-blue-400' : ''}`} />
                </button>
                <button
                  onClick={() => setIsRecentGamesOpen(!isRecentGamesOpen)}
                  className="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs font-semibold text-slate-300 hover:text-white hover:border-slate-700 flex items-center gap-1.5 transition-all"
                >
                  {isRecentGamesOpen ? (
                    <>
                      <span>Hide</span>
                      <ChevronUp className="w-3.5 h-3.5" />
                    </>
                  ) : (
                    <>
                      <span>View Games</span>
                      <ChevronDown className="w-3.5 h-3.5" />
                    </>
                  )}
                </button>
              </div>
            </div>

            {isRecentGamesOpen && (
              <div className="p-4">
                {isLoadingRecentGames && recentGames.length === 0 ? (
                  <div className="py-8 text-center text-xs text-slate-400 flex flex-col items-center justify-center gap-2">
                    <RefreshCw className="w-5 h-5 animate-spin text-blue-400" />
                    <span>Fetching your recent matches from Lichess...</span>
                  </div>
                ) : recentGames.length === 0 ? (
                  <div className="py-6 text-center text-xs text-slate-400">
                    No recent games found on this Lichess account. Play an online match or challenge the AI to analyze here!
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-80 overflow-y-auto pr-1">
                    {recentGames.map((game) => {
                      const isSelected = selectedGameId === game.id;
                      const isWin = game.result === 'win';
                      const isLoss = game.result === 'loss';

                      return (
                        <div
                          key={game.id}
                          className={`p-3.5 rounded-xl border transition-all flex flex-col justify-between gap-3 ${
                            isSelected
                              ? 'bg-violet-950/40 border-violet-500/50 shadow-md ring-1 ring-violet-500/30'
                              : 'bg-slate-950/50 border-slate-800/80 hover:border-slate-700 hover:bg-slate-950'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="space-y-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span
                                  className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                                    isWin
                                      ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/30'
                                      : isLoss
                                      ? 'bg-rose-950 text-rose-400 border border-rose-500/30'
                                      : 'bg-amber-950 text-amber-400 border border-amber-500/30'
                                  }`}
                                >
                                  {game.result.toUpperCase()}
                                </span>
                                <span className="text-xs font-bold text-white truncate">
                                  vs {game.opponent.username}
                                  {game.opponent.title && (
                                    <span className="ml-1 text-[10px] px-1 py-0.2 bg-amber-500/20 text-amber-300 rounded font-mono">
                                      {game.opponent.title}
                                    </span>
                                  )}
                                  {game.opponent.rating && (
                                    <span className="ml-1 text-xs text-slate-400 font-normal">
                                      ({game.opponent.rating})
                                    </span>
                                  )}
                                </span>
                              </div>
                              <div className="text-xs text-slate-400 truncate flex items-center gap-1.5">
                                <span>{game.opening.name}</span>
                                {game.opening.eco && (
                                  <span className="text-[10px] px-1 bg-slate-800 rounded text-slate-400 font-mono">
                                    {game.opening.eco}
                                  </span>
                                )}
                              </div>
                            </div>

                            <a
                              href={game.url}
                              target="_blank"
                              rel="noreferrer"
                              className="p-1.5 text-slate-500 hover:text-slate-300 rounded-lg hover:bg-slate-800 transition-all shrink-0"
                              title="Open on Lichess.org"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          </div>

                          <div className="flex items-center justify-between pt-2 border-t border-slate-800/60 text-xs">
                            <div className="flex items-center gap-3 text-slate-400 text-[11px]">
                              <span className="flex items-center gap-1">
                                <Clock className="w-3 h-3 text-slate-500" />
                                {game.time_control}
                              </span>
                              <span className="flex items-center gap-1">
                                <span className={`w-2 h-2 rounded-full ${game.user_color === 'white' ? 'bg-slate-200' : 'bg-slate-700 border border-slate-500'}`} />
                                {game.user_color === 'white' ? 'White' : 'Black'}
                              </span>
                              <span>{game.moves_count} moves</span>
                            </div>

                            <div className="flex items-center gap-1.5">
                              <button
                                onClick={() => handleLoadRecentGameOnBoard(game)}
                                className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-bold text-xs flex items-center gap-1 shadow transition-all hover:scale-105 active:scale-95"
                                title="Start the analysis on the physical board (LED traces & stepping)"
                              >
                                <PlayCircle className="w-3.5 h-3.5" />
                                Analyse on Board
                              </button>
                              <button
                                onClick={() => handleLoadRecentGame(game)}
                                className="px-3 py-1 bg-violet-600 hover:bg-violet-500 text-white rounded-lg font-bold text-xs flex items-center gap-1 shadow transition-all hover:scale-105 active:scale-95"
                              >
                                <PlayCircle className="w-3.5 h-3.5" />
                                Analyse Web
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Accuracy & Mistake Summary Row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-2xl flex items-center justify-between">
              <div>
                <span className="text-xs text-slate-400 uppercase font-semibold tracking-wider">White Accuracy</span>
                <div className="text-2xl font-bold text-white mt-1">{analysis?.accuracy?.white ?? 100.0}%</div>
                <div className="text-xs text-slate-500 mt-0.5">
                  Best: {analysis?.counts?.white?.best ?? 0} | Good: {analysis?.counts?.white?.good ?? 0}
                </div>
              </div>
              <div className="w-12 h-12 rounded-full border-4 border-emerald-500/40 flex items-center justify-center text-xs font-bold text-emerald-400 bg-emerald-500/10">
                {Math.round(analysis?.accuracy?.white ?? 100)}%
              </div>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-2xl flex items-center justify-between">
              <div>
                <span className="text-xs text-slate-400 uppercase font-semibold tracking-wider">Black Accuracy</span>
                <div className="text-2xl font-bold text-white mt-1">{analysis?.accuracy?.black ?? 100.0}%</div>
                <div className="text-xs text-slate-500 mt-0.5">
                  Best: {analysis?.counts?.black?.best ?? 0} | Good: {analysis?.counts?.black?.good ?? 0}
                </div>
              </div>
              <div className="w-12 h-12 rounded-full border-4 border-cyan-500/40 flex items-center justify-center text-xs font-bold text-cyan-400 bg-cyan-500/10">
                {Math.round(analysis?.accuracy?.black ?? 100)}%
              </div>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-2xl flex items-center justify-between">
              <div>
                <span className="text-xs text-slate-400 uppercase font-semibold tracking-wider">Critical Mistakes</span>
                <div className="text-2xl font-bold text-rose-400 mt-1">
                  {(analysis?.counts?.white?.blunder ?? 0) + (analysis?.counts?.black?.blunder ?? 0)} Blunders
                </div>
                <div className="text-xs text-slate-500 mt-0.5">
                  {(analysis?.counts?.white?.inaccuracy ?? 0) + (analysis?.counts?.black?.inaccuracy ?? 0)} Inaccuracies
                </div>
              </div>
              <button
                onClick={handleStartAnalysis}
                className="px-3 py-2 bg-violet-600 hover:bg-violet-500 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all shadow-md"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Re-Analyze
              </button>
            </div>
          </div>

          {/* Interactive SVG Evaluation Flow Graph */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-violet-400" />
                <h3 className="text-sm font-bold text-white">Evaluation Flow & Move Quality Graph</h3>
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-400">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-400 inline-block"></span> Best</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-cyan-400 inline-block"></span> Good</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-400 inline-block"></span> Inacc</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-rose-500 inline-block"></span> Blunder</span>
              </div>
            </div>

            {/* SVG Graph Viewport */}
            <div className="relative w-full h-36 bg-slate-950/80 rounded-xl border border-slate-800/80 overflow-hidden">
              {evalPoints.length > 1 ? (
                <svg className="w-full h-full" viewBox={`0 0 ${Math.max(400, evalPoints.length * 24)} 140`} preserveAspectRatio="none">
                  {/* Center zero-evaluation line */}
                  <line x1="0" y1="70" x2={Math.max(400, evalPoints.length * 24)} y2="70" stroke="#334155" strokeDasharray="3 3" strokeWidth="1" />

                  {/* Shaded Win Area */}
                  <path
                    d={`M 0,70 ${evalPoints.map((p, i) => `L ${i * 24},${p.y}`).join(' ')} L ${(evalPoints.length - 1) * 24},70 Z`}
                    fill="url(#evalGradient)"
                    opacity="0.35"
                  />

                  {/* Gradient definition */}
                  <defs>
                    <linearGradient id="evalGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="#10b981" />
                      <stop offset="50%" stopColor="#38bdf8" />
                      <stop offset="100%" stopColor="#f43f5e" />
                    </linearGradient>
                  </defs>

                  {/* Main Evaluation Line */}
                  <polyline
                    fill="none"
                    stroke="#818cf8"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    points={evalPoints.map((p, i) => `${i * 24},${p.y}`).join(' ')}
                  />

                  {/* Interactive Nodes for each ply */}
                  {evalPoints.map((p, i) => {
                    const played = playedAnalyses[i];
                    const tier = played?.classification || 'good';
                    const nodeColor = tier === 'best' ? '#10b981' : tier === 'good' ? '#06b6d4' : tier === 'inaccuracy' ? '#f59e0b' : '#f43f5e';
                    const isSelected = i === currentPly;

                    return (
                      <g key={i} onClick={() => handleStep(i)} className="cursor-pointer group">
                        {isSelected && (
                          <line x1={i * 24} y1="0" x2={i * 24} y2="140" stroke="#a855f7" strokeWidth="2" strokeDasharray="2 2" />
                        )}
                        <circle
                          cx={i * 24}
                          cy={p.y}
                          r={isSelected ? 6 : (tier === 'blunder' ? 4.5 : 3)}
                          fill={nodeColor}
                          stroke={isSelected ? '#ffffff' : '#0f172a'}
                          strokeWidth={isSelected ? 2 : 1}
                          className="transition-all hover:scale-150"
                        />
                      </g>
                    );
                  })}
                </svg>
              ) : (
                <div className="w-full h-full flex items-center justify-center text-xs text-slate-500">
                  Click "Re-Analyze" or activate the Center Royal Gate on the board to view the live evaluation curve.
                </div>
              )}
            </div>
          </div>

          {/* Virtual Branch Banner */}
          {analysis?.is_branching && (
            <div className="p-4 bg-violet-950/80 border border-violet-500/50 rounded-2xl flex flex-col md:flex-row items-center justify-between gap-3 shadow-lg ring-1 ring-violet-500/30">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-violet-500/20 rounded-xl text-violet-300 border border-violet-500/30">
                  <Layers className="w-5 h-5" />
                </div>
                <div>
                  <div className="text-xs font-bold text-violet-200 flex items-center gap-2">
                    <span>⚡ Off-Game Variation Sandbox Active</span>
                    <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-violet-500/20 text-violet-300 border border-violet-400/30">
                      +{analysis.branch_moves?.length || 1} {analysis.branch_moves?.length === 1 ? 'ply' : 'plies'} diverged
                    </span>
                  </div>
                  <div className="text-xs text-violet-400 mt-0.5">
                    Anchor square {analysis.anchor_coord ? `(${String.fromCharCode(97 + analysis.anchor_coord[0])}${analysis.anchor_coord[1] + 1})` : ''} & 4 corner rooks (a1, h1, a8, h8) are glowing in Royal Violet on the board.
                  </div>
                  {analysis.branch_moves && analysis.branch_moves.length > 0 && (
                    <div className="mt-1 px-2 py-1 bg-slate-950/70 border border-violet-500/30 rounded-lg text-[10px] font-mono text-violet-300">
                      Variation: {analysis.branch_moves.join(' → ')}
                    </div>
                  )}
                </div>
              </div>
              <button
                onClick={handleResetBranch}
                className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all shadow-md shrink-0"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Return to Game Timeline
              </button>
            </div>
          )}

          {/* Step Navigation Controls & Move History List */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Step Controls & Position Details */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 space-y-4">
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Position Navigator</h4>

              {/* Cartographer's Path Opening Information in Analysis */}
              {boardState.opening && boardState.opening.name && (
                <div className="bg-slate-950/80 p-3 rounded-xl border border-slate-800 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Opening Book</span>
                    <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 text-[10px] font-mono font-bold">
                      {boardState.opening.eco}
                    </span>
                  </div>
                  <div className="text-xs font-bold text-white truncate">{boardState.opening.name}</div>
                  {boardState.opening.variation && (
                    <div className="text-[11px] text-slate-400 truncate">{boardState.opening.variation}</div>
                  )}
                  {boardState.opening.out_of_book && (
                    <div className="pt-1 flex items-center gap-1 text-[10px] text-amber-400 font-mono">
                      <span>⚡ Out of book at ply {boardState.opening.novelty_ply ?? boardState.opening.ply}</span>
                    </div>
                  )}
                </div>
              )}

              <div className="flex items-center justify-between bg-slate-950 p-2 rounded-xl border border-slate-800">
                <button
                  onClick={() => handleStep(0)}
                  disabled={currentPly <= 0}
                  className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-30"
                  title="First Move"
                >
                  ⏮
                </button>
                <button
                  onClick={() => handleStep(currentPly - 1)}
                  disabled={currentPly <= 0}
                  className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-30"
                  title="Previous Move"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <span className="text-xs font-bold text-white">
                  Ply {currentPly} / {totalPlys}
                </span>
                <button
                  onClick={() => handleStep(currentPly + 1)}
                  disabled={currentPly >= totalPlys}
                  className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-30"
                  title="Next Move"
                >
                  <ChevronRight className="w-5 h-5" />
                </button>
                <button
                  onClick={() => handleStep(totalPlys)}
                  disabled={currentPly >= totalPlys}
                  className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-30"
                  title="Last Move"
                >
                  ⏭
                </button>
              </div>

              {/* Current Move Assessment */}
              {currentPly > 0 && currentPly <= playedAnalyses.length && (
                <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800/80 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-400">Move Played:</span>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-white">{playedAnalyses[currentPly - 1]?.san}</span>
                      {getQualityBadge(playedAnalyses[currentPly - 1]?.classification)}
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-400">Centipawn Loss:</span>
                    <span className="font-mono text-slate-300">Δ {playedAnalyses[currentPly - 1]?.delta_cp} cp</span>
                  </div>
                  {playedAnalyses[currentPly - 1]?.best_move && (
                    <div className="flex items-center justify-between text-xs pt-1 border-t border-slate-800/50">
                      <span className="text-emerald-400 font-semibold">Engine Best:</span>
                      <span className="font-mono font-bold text-emerald-300">
                        {playedAnalyses[currentPly - 1]?.best_move}
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Top Engine Candidates (click to play a variation from the webapp) */}
              <div className="space-y-2 pt-2">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Top Candidates — click to explore</span>
                <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                  {analysis?.current_eval?.top_moves?.slice(0, 3).map((m: { uci?: string; score_cp?: number | null; mate?: number | null; classification?: string }, idx: number) => (
                    <div
                      key={idx}
                      onClick={() => m.uci && handleWebMove(m.uci)}
                      className="flex items-center justify-between p-2 bg-slate-950/50 rounded-lg text-xs border border-slate-800/60 cursor-pointer hover:border-violet-500/60 hover:bg-slate-900 transition-all"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-slate-500 font-bold">{idx + 1}.</span>
                        <span className="font-mono font-bold text-slate-200">{m.uci}</span>
                        {getQualityBadge(m.classification)}
                      </div>
                      <span className="font-mono text-slate-400">
                        {m.score_cp !== null && m.score_cp !== undefined
                          ? `${m.score_cp > 0 ? '+' : ''}${(m.score_cp / 100).toFixed(1)}`
                          : 'Mate'}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Free-form web move input (SAN or UCI) */}
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleWebMove(webMoveInput);
                  }}
                  className="flex items-center gap-2"
                >
                  <input
                    type="text"
                    placeholder="Play a move: Nf3, exd5, O-O, e2e4..."
                    value={webMoveInput}
                    onChange={(e) => setWebMoveInput(e.target.value)}
                    className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-violet-500 font-mono"
                  />
                  <button
                    type="submit"
                    className="px-3 py-2 bg-violet-600 hover:bg-violet-500 text-white rounded-lg text-xs font-bold transition-all shrink-0"
                  >
                    Play
                  </button>
                </form>

                {/* Keyboard navigation hint */}
                <div className="text-[10px] text-slate-500 leading-relaxed pt-1">
                  <span className="font-mono text-slate-400">← →</span> or{' '}
                  <span className="font-mono text-slate-400">h l</span> step moves ·{' '}
                  <span className="font-mono text-slate-400">Home End</span> or{' '}
                  <span className="font-mono text-slate-400">g G</span> jump start/end ·{' '}
                  <span className="font-mono text-slate-400">←</span> un-plays one variation move
                </div>
              </div>
            </div>

            {/* Move History List */}
            <div className="lg:col-span-2 bg-slate-900/90 border border-slate-800 rounded-2xl p-5 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2 flex-wrap gap-1">
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Game Notation & Evaluation Breakdown</h4>
                  <div className="flex items-center gap-1.5 text-[9px] font-bold">
                    <span className="px-1.5 py-0.5 rounded bg-emerald-600/80 text-white">BEST</span>
                    <span className="px-1.5 py-0.5 rounded bg-teal-500/50 text-teal-100">GOOD</span>
                    <span className="px-1.5 py-0.5 rounded bg-yellow-500/60 text-yellow-950">INACC</span>
                    <span className="px-1.5 py-0.5 rounded bg-orange-500/70 text-white">MISTAKE</span>
                    <span className="px-1.5 py-0.5 rounded bg-red-600/80 text-white">BLUNDER</span>
                  </div>
                </div>
                <div className="max-h-72 overflow-y-auto pr-2 space-y-1">
                  {Array.from({ length: Math.ceil(playedAnalyses.length / 2) }).map((_, moveIdx) => {
                    const whitePly = moveIdx * 2;
                    const blackPly = moveIdx * 2 + 1;
                    const wMove = playedAnalyses[whitePly];
                    const bMove = playedAnalyses[blackPly];

                    return (
                      <div key={moveIdx} className="grid grid-cols-11 gap-2 p-1.5 rounded-lg text-xs hover:bg-slate-800/40 transition-colors">
                        <span className="col-span-1 text-slate-500 font-bold">{moveIdx + 1}.</span>
                        
                        {/* White Move — color-coded by quality */}
                        <div
                          onClick={() => handleStep(whitePly + 1)}
                          className={`col-span-5 flex items-center justify-between p-1.5 rounded-md cursor-pointer transition-colors ${
                            currentPly === whitePly + 1 ? 'ring-2 ring-violet-400/70' : ''
                          }`}
                        >
                          <span className={`w-full text-center text-xs font-bold rounded border px-2 py-1 ${getMoveTileStyle(wMove?.classification)}`}>
                            {wMove?.san || wMove?.uci || '...'}
                          </span>
                        </div>

                        {/* Black Move */}
                        {bMove ? (
                          <div
                            onClick={() => handleStep(blackPly + 1)}
                            className={`col-span-5 flex items-center justify-between p-1.5 rounded-md cursor-pointer transition-colors ${
                              currentPly === blackPly + 1 ? 'ring-2 ring-violet-400/70' : ''
                            }`}
                          >
                            <span className={`w-full text-center text-xs font-bold rounded border px-2 py-1 ${getMoveTileStyle(bMove.classification)}`}>
                              {bMove.san || bMove.uci}
                            </span>
                          </div>
                        ) : (
                          <div className="col-span-5"></div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="pt-4 border-t border-slate-800 flex justify-end">
                <button
                  onClick={stopAnalysis}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold transition-all"
                >
                  Exit Analysis Mode
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SUB-VIEW 2: BLUNDER BLITZ / TACTICAL PUZZLES */}
      {subMode === 'blunder_drill' && (
        <div className="space-y-6">
          {blunders.length > 0 ? (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Blunder selector sidebar */}
              <div className="lg:col-span-4 bg-slate-900/90 border border-slate-800 rounded-2xl p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Mistakes Extracted ({blunders.length})</h4>
                  <span className="text-[11px] text-slate-500 font-mono">Puzzles</span>
                </div>
                <div className="space-y-2 max-h-[560px] overflow-y-auto pr-1">
                  {blunders.map((b, idx) => (
                    <div
                      key={idx}
                      onClick={() => handleStartBlunderDrill(idx)}
                      className={`p-3 rounded-xl border cursor-pointer transition-all ${
                        activeBlunderIndex === idx
                          ? 'bg-rose-950/60 border-rose-500 text-white shadow-md'
                          : 'bg-slate-950/50 border-slate-800 text-slate-400 hover:bg-slate-800'
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs font-bold mb-1">
                        <span className="flex items-center gap-1.5">
                          <span className={b.player_color === 'black' ? 'text-slate-400' : 'text-amber-300'}>
                            {b.player_color === 'black' ? '♚' : '♔'}
                          </span>
                          Puzzle #{idx + 1} (Move {Math.floor(b.ply_index / 2) + 1})
                        </span>
                        {getQualityBadge(b.classification)}
                      </div>
                      <div className="text-xs text-slate-400 line-clamp-2 leading-relaxed">{b.description}</div>
                      {b.opponent_prev_move_san && (
                        <div className="mt-1.5 text-[10px] text-amber-400/80 font-mono">
                          Opponent played: {b.opponent_prev_move_san}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Active Blunder Challenge & Interactive Board */}
              <div className="lg:col-span-8 space-y-4">
                {/* Top Status & Perspective Banner */}
                <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 space-y-4">
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <div className="flex items-center gap-2.5">
                      <Flame className="w-5 h-5 text-rose-400" />
                      <h3 className="text-base font-bold text-white">
                        Tactical Refutation #{activeBlunderIndex + 1}
                      </h3>
                      {currentBlunder?.classification && getQualityBadge(currentBlunder.classification)}
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-1.5 text-xs text-rose-400 font-bold bg-rose-950/50 px-3 py-1 rounded-full border border-rose-500/30">
                        Attempts: {Array.from({ length: analysis?.blunder_attempts ?? 3 }).map(() => '❤️').join('')}
                      </div>
                      <button
                        onClick={handleToggleHint}
                        className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-amber-300 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all border border-amber-500/20"
                      >
                        <Lightbulb className="w-3.5 h-3.5" />
                        {analysis?.blunder_hint_active ? 'Hide Hint' : 'LED Hint'}
                      </button>
                      <button
                        onClick={() => setShowBlunderSolution((prev) => !prev)}
                        className={`px-3 py-1 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all border ${
                          showBlunderSolution
                            ? 'bg-amber-950/60 border-amber-500 text-amber-300'
                            : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700'
                        }`}
                      >
                        <Lightbulb className="w-3.5 h-3.5 text-amber-400" />
                        {showBlunderSolution ? 'Hide Solution' : '💡 Solution'}
                      </button>
                    </div>
                  </div>

                  {/* Perspective & Opponent's Move Info Card */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 bg-slate-950 p-3.5 rounded-xl border border-slate-800">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Your Side:</span>
                      <span className={`text-xs font-bold px-2.5 py-0.5 rounded-md ${
                        currentBlunder?.player_color === 'black'
                          ? 'bg-slate-800 text-slate-200 border border-slate-700'
                          : 'bg-amber-950/50 text-amber-300 border border-amber-500/30'
                      }`}>
                        {currentBlunder?.player_color === 'black' ? '♚ Black to Move' : '♔ White to Move'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Opponent Move:</span>
                      <span className="text-xs font-mono font-bold text-amber-400 bg-amber-950/30 px-2.5 py-0.5 rounded-md border border-amber-500/20">
                        {currentBlunder?.opponent_prev_move_san ? currentBlunder.opponent_prev_move_san : 'Initiating move'}
                      </span>
                    </div>
                  </div>

                  <p className="text-xs text-slate-300 leading-relaxed">
                    {currentBlunder?.description || 'Find the best tactical refutation in this position.'}
                  </p>
                </div>

                {/* Interactive Board & Continuation Box */}
                <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
                  {/* Web Board */}
                  <div className="md:col-span-7 bg-slate-900/90 border border-slate-800 rounded-2xl p-4 flex flex-col items-center">
                    <WebAnalysisBoard
                      fen={analysis?.fen || currentBlunder?.fen_before || 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'}
                      legalMoves={analysis?.legal_moves ?? []}
                      inCheck={!!analysis?.in_check}
                      lastMoveUci={currentBlunder?.opponent_prev_move_uci || undefined}
                      myColor={currentBlunder?.player_color === 'black' ? 'black' : 'white'}
                      onMovePlayed={(uci: string) => { void handlePuzzleMove(uci); }}
                    />
                  </div>

                  {/* Move Continuation & Action Card */}
                  <div className="md:col-span-5 bg-slate-900/90 border border-slate-800 rounded-2xl p-5 flex flex-col justify-between space-y-4">
                    <div className="space-y-3">
                      <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                        <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                        Tactical Sequence
                      </h4>

                      {/* Opponent's defensive reply announcement */}
                      {puzzleResult?.opponent_reply_san && (
                        <div className="p-3 bg-blue-950/40 border border-blue-500/30 rounded-xl space-y-1">
                          <div className="text-[10px] text-blue-300 font-bold uppercase tracking-wider">
                            Opponent Response (Side we don't play):
                          </div>
                          <div className="text-sm font-mono font-bold text-white flex items-center gap-2">
                            <span>{puzzleResult.player_san}</span>
                            <span className="text-slate-500">→</span>
                            <span className="text-blue-400">{puzzleResult.opponent_reply_san}</span>
                          </div>
                        </div>
                      )}

                      {/* Full Grandmaster Solution Line if Solved or Requested */}
                      {(showBlunderSolution || puzzleResult?.puzzle_complete || currentBlunder?.solution_line_san) && (
                        <div className="p-3 bg-emerald-950/30 border border-emerald-500/30 rounded-xl space-y-1.5">
                          <div className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" />
                            Grandmaster Continuation Line:
                          </div>
                          <div className="text-xs font-mono text-emerald-200 leading-relaxed">
                            {(puzzleResult?.solution_line || currentBlunder?.solution_line_san)?.join(' ') || currentBlunder?.best_move}
                          </div>
                        </div>
                      )}

                      {/* Navigation between puzzles */}
                      <div className="flex items-center justify-between pt-2">
                        <button
                          disabled={activeBlunderIndex <= 0}
                          onClick={() => handleStartBlunderDrill(Math.max(0, activeBlunderIndex - 1))}
                          className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300 rounded-xl text-xs font-semibold flex items-center gap-1 transition-all"
                        >
                          <ChevronLeft className="w-4 h-4" /> Prev
                        </button>
                        <span className="text-xs text-slate-400 font-mono">
                          {activeBlunderIndex + 1} / {blunders.length}
                        </span>
                        <button
                          disabled={activeBlunderIndex >= blunders.length - 1}
                          onClick={() => handleStartBlunderDrill(Math.min(blunders.length - 1, activeBlunderIndex + 1))}
                          className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-300 rounded-xl text-xs font-semibold flex items-center gap-1 transition-all"
                        >
                          Next <ChevronRight className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    {/* Move Guess Form */}
                    <form onSubmit={handleBlunderAttemptSubmit} className="space-y-2">
                      <div className="text-[11px] text-slate-400">Play on the board above or type your move:</div>
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          placeholder="e.g. e2e4 or Re8..."
                          value={guessInput}
                          onChange={(e) => setGuessInput(e.target.value)}
                          className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-rose-500"
                        />
                        <button
                          type="submit"
                          className="px-3.5 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-xl text-xs font-bold transition-all shadow-md"
                        >
                          Submit
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-12 text-center space-y-4">
              <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto" />
              <h3 className="text-base font-bold text-white">No Critical Blunders Found!</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                Your last game was played with sharp tactical precision, or analysis has not been run yet.
              </p>
              <button
                onClick={handleStartAnalysis}
                className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white rounded-xl text-xs font-bold"
              >
                Analyze Last Game
              </button>
            </div>
          )}
        </div>
      )}

      {/* SUB-VIEW 3: REPLAY TRAINER (Memory Training) */}
      {subMode === 'replay' && (
        <div className="space-y-6">
          {/* ===== LEARN PHASE ===== */}
          {analysis?.active && replayPhase === 'learn' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Progress & Instructions */}
              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 space-y-4">
                <div className="flex items-center gap-2">
                  <Brain className="w-5 h-5 text-sky-400" />
                  <h3 className="text-base font-bold text-white">Learn Phase</h3>
                </div>
                <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                  <div className="flex items-center justify-between text-xs mb-2">
                    <span className="text-slate-400 uppercase font-bold tracking-wider">Progress</span>
                    <span className="font-mono font-bold text-sky-300">
                      Ply {currentPly} / {totalPlys}
                    </span>
                  </div>
                  <div className="h-2.5 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-sky-500 to-emerald-400 rounded-full transition-all duration-500"
                      style={{ width: `${totalPlys ? (currentPly / totalPlys) * 100 : 0}%` }}
                    />
                  </div>
                  <div className="mt-2 text-[11px] text-slate-500">
                    {learnedPly} {learnedPly === 1 ? 'ply' : 'plies'} memorized so far
                  </div>
                </div>

                <div className="p-3.5 bg-sky-950/50 border border-sky-500/30 rounded-xl space-y-1.5">
                  <div className="text-[10px] uppercase font-bold tracking-wider text-sky-300 flex items-center gap-1.5">
                    <Eye className="w-3.5 h-3.5" /> How it works
                  </div>
                  <ul className="text-xs text-sky-200/90 space-y-1 list-disc list-inside leading-relaxed">
                    <li>The board shows the next move as an azure LED trace — play it physically.</li>
                    <li>Wrong moves flash red and guide you back to the game line.</li>
                    <li>Stop anytime: set <span className="font-bold">all 32 pieces</span> back to the starting position.</li>
                    <li>Memory recall then begins — covering exactly the plies you just played.</li>
                  </ul>
                </div>

                <button
                  onClick={stopAnalysis}
                  className="w-full px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold transition-all"
                >
                  Exit Replay Trainer
                </button>
              </div>

              {/* Game Card & Revealed Move List */}
              <div className="lg:col-span-2 bg-slate-900/90 border border-slate-800 rounded-2xl p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Trophy className="w-5 h-5 text-amber-400" />
                    <div>
                      <h3 className="text-base font-bold text-white">
                        {analysis?.gm_game?.title || 'Grandmaster Masterpiece'}
                      </h3>
                      <div className="text-xs text-slate-400">
                        {analysis?.gm_game?.event} ({analysis?.gm_game?.year}) — {analysis?.gm_game?.white} vs. {analysis?.gm_game?.black}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {analysis?.gm_game?.description}
                  </p>
                </div>

                {analysis?.gm_game?.annotations?.[currentPly] && (
                  <div className="p-3.5 bg-amber-950/40 border border-amber-500/30 rounded-xl text-xs text-amber-300 flex items-start gap-2.5">
                    <Sparkles className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                    <span>{analysis.gm_game.annotations[currentPly]}</span>
                  </div>
                )}

                {/* Move list revealing as played */}
                <div>
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Game Line</h4>
                  <div className="max-h-64 overflow-y-auto pr-2 grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                    {(analysis?.game_moves ?? []).map((uci, idx) => {
                      const played = idx < currentPly;
                      const isNext = idx === currentPly;
                      return (
                        <div
                          key={idx}
                          className={`px-2 py-1.5 rounded-lg text-xs font-mono border transition-all ${
                            isNext
                              ? 'bg-sky-600/30 border-sky-500/60 text-white font-bold animate-pulse'
                              : played
                              ? 'bg-slate-950/70 border-slate-800 text-slate-300'
                              : 'bg-slate-950/30 border-slate-900 text-slate-700'
                          }`}
                        >
                          <span className="text-slate-600 mr-1.5">{idx + 1}.</span>
                          {played || isNext ? uci : '· · ·'}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ===== RECALL PHASE ===== */}
          {analysis?.active && replayPhase === 'recall' && (
            <div className="space-y-6">
              {replayComplete ? (
                /* Victory Summary */
                <div className="bg-slate-900/90 border border-emerald-500/50 rounded-2xl p-8 text-center space-y-4 shadow-xl ring-1 ring-emerald-500/30">
                  <Trophy className="w-14 h-14 text-amber-400 mx-auto" />
                  <h3 className="text-xl font-bold text-white">Recall Complete!</h3>
                  <div className="flex items-center justify-center gap-6">
                    <div className="text-center">
                      <div className="text-3xl font-bold text-emerald-400">{correctRecalls}/{learnedPly}</div>
                      <div className="text-xs text-slate-400 uppercase tracking-wider mt-1">Moves Remembered</div>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold text-rose-400">{replayMistakes}</div>
                      <div className="text-xs text-slate-400 uppercase tracking-wider mt-1">Mistakes</div>
                    </div>
                    <div className="text-center">
                      <div className="text-3xl font-bold text-sky-400">
                        {learnedPly ? Math.round((correctRecalls / learnedPly) * 100) : 0}%
                      </div>
                      <div className="text-xs text-slate-400 uppercase tracking-wider mt-1">Memory Score</div>
                    </div>
                  </div>
                  <p className="text-xs text-slate-400 max-w-md mx-auto">
                    Set all pieces back to the starting position to finish the session, or exit below.
                  </p>
                  <button
                    onClick={stopAnalysis}
                    className="px-5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold transition-all"
                  >
                    Exit Replay Trainer
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  {/* Recall Status */}
                  <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 space-y-4">
                    <div className="flex items-center gap-2">
                      <Brain className="w-5 h-5 text-violet-400" />
                      <h3 className="text-base font-bold text-white">Memory Recall</h3>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                      <div className="flex items-center justify-between text-xs mb-2">
                        <span className="text-slate-400 uppercase font-bold tracking-wider">Target</span>
                        <span className="font-mono font-bold text-violet-300">
                          Ply {currentPly} / {learnedPly}
                        </span>
                      </div>
                      <div className="h-2.5 bg-slate-800 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-violet-500 to-fuchsia-400 rounded-full transition-all duration-500"
                          style={{ width: `${learnedPly ? (currentPly / learnedPly) * 100 : 0}%` }}
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-emerald-950/40 border border-emerald-500/30 rounded-xl p-3 text-center">
                        <div className="text-xl font-bold text-emerald-400">{correctRecalls}</div>
                        <div className="text-[10px] text-slate-400 uppercase tracking-wider">Correct</div>
                      </div>
                      <div className="bg-rose-950/40 border border-rose-500/30 rounded-xl p-3 text-center">
                        <div className="text-xl font-bold text-rose-400">{replayMistakes}</div>
                        <div className="text-[10px] text-slate-400 uppercase tracking-wider">Mistakes</div>
                      </div>
                    </div>

                    {replayReveal && (
                      <div className="p-3 bg-amber-950/50 border border-amber-500/40 rounded-xl text-xs text-amber-300 space-y-1">
                        <div className="font-bold flex items-center gap-1.5">
                          <Lightbulb className="w-3.5 h-3.5" /> Wrong move — correction revealed
                        </div>
                        <div className="text-amber-200/90 leading-relaxed">
                          Take your piece back to its original square, then follow the amber trace on the board.
                        </div>
                      </div>
                    )}

                    <div className="p-3.5 bg-violet-950/50 border border-violet-500/30 rounded-xl">
                      <ul className="text-xs text-violet-200/90 space-y-1 list-disc list-inside leading-relaxed">
                        <li>No hints — replay the line purely from memory.</li>
                        <li>Green flash = correct, red flash = wrong move.</li>
                        <li>The side-to-move King glows on the board.</li>
                      </ul>
                    </div>

                    <button
                      onClick={stopAnalysis}
                      className="w-full px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold transition-all"
                    >
                      Exit Replay Trainer
                    </button>
                  </div>

                  {/* Per-Ply Result Chips (hidden notation!) */}
                  <div className="lg:col-span-2 bg-slate-900/90 border border-slate-800 rounded-2xl p-6 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-base font-bold text-white">Recall Progress</h3>
                      <span className="text-xs text-slate-500">Notation hidden — no peeking!</span>
                    </div>
                    <div className="grid grid-cols-8 sm:grid-cols-12 gap-2">
                      {Array.from({ length: learnedPly }).map((_, ply) => {
                        const res = resultByPly[ply];
                        const isCurrent = ply === currentPly;
                        return (
                          <div
                            key={ply}
                            className={`aspect-square rounded-lg flex items-center justify-center text-[10px] font-bold border transition-all ${
                              res === true
                                ? 'bg-emerald-600/30 border-emerald-500/60 text-emerald-300'
                                : res === false
                                ? 'bg-rose-600/30 border-rose-500/60 text-rose-300'
                                : isCurrent
                                ? 'bg-violet-600/30 border-violet-500/60 text-white animate-pulse'
                                : 'bg-slate-950/50 border-slate-800 text-slate-700'
                            }`}
                          >
                            {res === true ? '✓' : res === false ? '✕' : ply + 1}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ===== PICKER (no active session) ===== */}
          {!analysis?.active && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Curated GM Games Carousel */}
              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 space-y-3">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Historical GM Masterpieces</h4>
                <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                  {gmGamesList.map((g) => (
                    <div
                      key={g.id}
                      onClick={() => handleStartGM(g.id)}
                      className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                        selectedGMId === g.id
                          ? 'bg-amber-950/60 border-amber-500 text-white shadow-md'
                          : 'bg-slate-950/50 border-slate-800 text-slate-400 hover:bg-slate-800'
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs font-bold mb-1">
                        <span>{g.title}</span>
                        <span className="text-amber-400 font-mono">{g.year}</span>
                      </div>
                      <div className="text-xs text-slate-300 font-medium">{g.white} vs. {g.black}</div>
                      <div className="text-xs text-slate-500 mt-1 flex items-center gap-2">
                        <span>{g.opening}</span>
                        <span>•</span>
                        <span>{g.moves_count} moves</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Session Starter Card */}
              <div className="lg:col-span-2 bg-slate-900/90 border border-slate-800 rounded-2xl p-6 space-y-5">
                <div className="flex items-center gap-2">
                  <Brain className="w-5 h-5 text-amber-400" />
                  <h3 className="text-base font-bold text-white">Train Your Chess Memory</h3>
                </div>

                <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                  <div className="text-xs font-bold text-amber-400 uppercase tracking-wider">Two-Phase Training</div>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    <span className="font-semibold text-sky-300">Phase 1 — Learn:</span> pick a famous game and play it
                    move-by-move on the board with LED guidance. Stop whenever you like and set the pieces back.
                    <br />
                    <span className="font-semibold text-violet-300">Phase 2 — Recall:</span> with the board reset and no
                    hints, replay everything you just learned from memory. Green flashes confirm correct moves; red
                    flashes reveal mistakes with the grandmaster continuation.
                  </p>
                </div>

                <div className="flex flex-col sm:flex-row gap-3">
                  <button
                    onClick={() => handleStartGM(selectedGMId)}
                    className="flex-1 px-5 py-3 bg-amber-600 hover:bg-amber-500 text-white rounded-xl text-sm font-bold transition-all shadow-md flex items-center justify-center gap-2"
                  >
                    <PlayCircle className="w-4.5 h-4.5" />
                    Start Learning Selected Game
                  </button>
                  <button
                    onClick={handleStartReplayRecall}
                    className="flex-1 px-5 py-3 bg-violet-600 hover:bg-violet-500 text-white rounded-xl text-sm font-bold transition-all shadow-md flex items-center justify-center gap-2"
                  >
                    <Brain className="w-4.5 h-4.5" />
                    Instant Recall: My Last Game
                  </button>
                </div>

                <div className="p-3.5 bg-slate-950/60 border border-slate-800 rounded-xl text-xs text-slate-400 leading-relaxed">
                  <span className="font-bold text-slate-300">Board gesture:</span> lift the{' '}
                  <span className="font-mono text-amber-300">d2</span> pawn, then{' '}
                  <span className="font-mono text-amber-300">e2</span>, then replace both — instantly starts memory
                  recall of your last played game. (Lift e2 first for normal analysis.)
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* SUB-VIEW 4: ENDGAME ACADEMY ("Theoretical Mastery") */}
      {subMode === 'endgame' && (() => {
        const eg = analysis?.endgame;
        return (
          <div className="space-y-6">
            {/* Active Endgame Drill View */}
            {analysis?.active && analysis.submode === 'endgame' && eg?.drill ? (
              <div className="space-y-6">
                {/* Header Card */}
                <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                        {eg.drill.category_title || eg.drill.category}
                      </span>
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-blue-500/20 text-blue-300 border border-blue-500/30">
                        Goal: {eg.drill.target_goal.toUpperCase()}
                      </span>
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-purple-500/20 text-purple-300 border border-purple-500/30">
                        Playing as {eg.drill.player_color.toUpperCase()}
                      </span>
                    </div>
                    <h3 className="text-xl font-bold text-white flex items-center gap-2">
                      {eg.drill.title}
                    </h3>
                    <p className="text-xs text-slate-400 max-w-2xl">
                      {eg.drill.description}
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleRequestEndgameHint}
                      className="px-3.5 py-2 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all"
                    >
                      <Lightbulb className="w-4 h-4" />
                      Hint
                    </button>
                    <button
                      onClick={() => setShowEndgameSolution((prev) => !prev)}
                      className={`px-3.5 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all border ${
                        showEndgameSolution
                          ? 'bg-amber-950/60 border-amber-500 text-amber-300'
                          : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700'
                      }`}
                    >
                      <Lightbulb className="w-4 h-4 text-amber-400" />
                      {showEndgameSolution ? 'Hide Solution' : '💡 Solution'}
                    </button>
                    <button
                      onClick={handleStopEndgame}
                      className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold transition-all"
                    >
                      Exit Drill
                    </button>
                  </div>
                </div>

                {/* Status Banner & Guidance based on Phase */}
                {eg.phase === 'setup_white' && (
                  <div className="bg-gradient-to-r from-amber-950/40 via-slate-900 to-amber-950/40 border border-amber-500/40 rounded-2xl p-6 shadow-xl space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-3 h-3 rounded-full bg-amber-400 animate-ping" />
                        <h4 className="text-base font-bold text-amber-200">
                          Phase 1 of 2: Place White Pieces
                        </h4>
                      </div>
                      <span className="text-xs font-mono text-amber-300 bg-amber-950/80 px-2.5 py-1 rounded-lg border border-amber-500/30">
                        Target squares illuminated with piece colors
                      </span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">
                      Place all required White pieces on the board. Each piece type glows in its dedicated color.
                      When all White pieces are correctly positioned, a gentle ivory wave will confirm and advance to Black piece setup.
                    </p>

                    {/* Piece Setup Checklist */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                      {eg.setup_status.missing_white.length > 0 ? (
                        eg.setup_status.missing_white.map(([c, r], idx) => (
                          <div key={idx} className="p-3 bg-slate-950/80 border border-amber-500/40 rounded-xl flex items-center justify-between">
                            <span className="text-xs font-medium text-slate-300">White Piece</span>
                            <span className="font-mono text-xs font-bold text-amber-400">{String.fromCharCode(97 + c)}{r + 1}</span>
                          </div>
                        ))
                      ) : (
                        <div className="col-span-full p-3 bg-emerald-950/60 border border-emerald-500/40 rounded-xl text-xs font-bold text-emerald-300 flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          All White pieces in position! Advancing...
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {eg.phase === 'setup_black' && (
                  <div className="bg-gradient-to-r from-emerald-950/40 via-slate-900 to-emerald-950/40 border border-emerald-500/40 rounded-2xl p-6 shadow-xl space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-3 h-3 rounded-full bg-emerald-400 animate-ping" />
                        <h4 className="text-base font-bold text-emerald-200">
                          Phase 2 of 2: Place Black Pieces
                        </h4>
                      </div>
                      <span className="text-xs font-mono text-emerald-300 bg-emerald-950/80 px-2.5 py-1 rounded-lg border border-emerald-500/30">
                        Keep White pieces in place
                      </span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">
                      Now place the Black pieces on their illuminated target squares. When all pieces are correctly detected, the board will flash ready and the drill will begin!
                    </p>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                      {eg.setup_status.missing_black.length > 0 ? (
                        eg.setup_status.missing_black.map(([c, r], idx) => (
                          <div key={idx} className="p-3 bg-slate-950/80 border border-emerald-500/40 rounded-xl flex items-center justify-between">
                            <span className="text-xs font-medium text-slate-300">Black Piece</span>
                            <span className="font-mono text-xs font-bold text-emerald-400">{String.fromCharCode(97 + c)}{r + 1}</span>
                          </div>
                        ))
                      ) : (
                        <div className="col-span-full p-3 bg-emerald-950/60 border border-emerald-500/40 rounded-xl text-xs font-bold text-emerald-300 flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          Board synchronized! Starting drill...
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {eg.phase === 'playing' && (
                  <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                    {/* Interactive Web Board */}
                    <div className="lg:col-span-7 bg-slate-900/90 border border-slate-800 rounded-2xl p-5 flex flex-col items-center justify-between space-y-4">
                      <div className="w-full flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Side:</span>
                          <span className={`text-xs font-bold px-2.5 py-0.5 rounded-md ${
                            eg.drill.player_color === 'black'
                              ? 'bg-slate-800 text-slate-200 border border-slate-700'
                              : 'bg-amber-950/50 text-amber-300 border border-amber-500/30'
                          }`}>
                            {eg.drill.player_color === 'black' ? '♚ You play as Black' : '♔ You play as White'}
                          </span>
                        </div>
                        <span className={`text-xs font-bold px-2.5 py-0.5 rounded-md ${
                          eg.turn === eg.drill.player_color
                            ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-500/40'
                            : 'bg-blue-950/60 text-blue-300 border border-blue-500/40 animate-pulse'
                        }`}>
                          {eg.turn === eg.drill.player_color ? 'Your Turn' : "Opponent's Turn (Black)"}
                        </span>
                      </div>

                      <WebAnalysisBoard
                        fen={analysis?.fen || eg.drill.fen}
                        legalMoves={analysis?.legal_moves ?? []}
                        inCheck={!!analysis?.in_check}
                        lastMoveUci={
                          eg.pending_reply
                            ? `${eg.pending_reply.from_sq}${eg.pending_reply.to_sq}`
                            : boardState.last_move
                            ? `${String.fromCharCode(97 + boardState.last_move[0][0])}${boardState.last_move[0][1] + 1}${String.fromCharCode(97 + boardState.last_move[1][0])}${boardState.last_move[1][1] + 1}`
                            : undefined
                        }
                        myColor={eg.drill.player_color}
                        onMovePlayed={(uci: string) => { void sendAnalysisMove(uci); }}
                      />

                      <div className="text-[11px] text-slate-400 text-center">
                        Play moves on the physical board or drag & drop pieces on the web board above.
                      </div>
                    </div>

                    {/* Live Guidance, Opponent Response, and Solution Column */}
                    <div className="lg:col-span-5 space-y-4">
                      {/* Opponent Reply Status / Action Banner */}
                      {eg.pending_reply && (
                        <div className="p-4 bg-blue-950/50 border border-blue-500/40 rounded-2xl space-y-2 shadow-lg animate-pulse">
                          <div className="text-xs font-bold text-blue-300 uppercase tracking-wider flex items-center justify-between">
                            <span>Opponent Move (Black):</span>
                            <span className="font-mono text-sm font-bold text-white bg-blue-900/60 px-2 py-0.5 rounded border border-blue-400/30">
                              {eg.pending_reply.san}
                            </span>
                          </div>
                          <div className="text-xs text-blue-200/90 leading-relaxed">
                            Move piece from <b className="font-mono text-amber-300 font-bold">{eg.pending_reply.from_sq}</b> to <b className="font-mono text-cyan-300 font-bold">{eg.pending_reply.to_sq}</b> on the physical board.
                          </div>
                          <button
                            onClick={handleApplyEndgameOpponentMove}
                            className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-all shadow-md mt-1"
                          >
                            Apply Move on Board
                          </button>
                        </div>
                      )}

                      {eg.is_computing_reply && (
                        <div className="p-3.5 bg-slate-950 border border-slate-800 rounded-2xl text-xs text-slate-300 flex items-center gap-2.5">
                          <Sparkles className="w-4 h-4 text-amber-400 animate-spin" />
                          Stockfish is calculating Black's defensive reply...
                        </div>
                      )}

                      {/* Theoretical Solution & Technique Card */}
                      {(showEndgameSolution || eg.solution_line?.length) && showEndgameSolution && (
                        <div className="bg-amber-950/30 border border-amber-500/40 rounded-2xl p-5 space-y-3 shadow-lg">
                          <div className="flex items-center gap-2 text-amber-300 text-xs font-bold uppercase tracking-wider">
                            <Lightbulb className="w-4 h-4 text-amber-400" />
                            Theoretical Winning Technique
                          </div>

                          {(eg.solution_line?.length || eg.drill.solution_line?.length) && (
                            <div className="space-y-1">
                              <div className="text-[11px] text-slate-400 font-semibold">Grandmaster Solution Line:</div>
                              <div className="p-2.5 bg-slate-950 rounded-xl border border-slate-800 font-mono text-xs text-amber-200 leading-relaxed max-h-28 overflow-y-auto">
                                {(eg.solution_line ?? eg.drill.solution_line ?? []).join(' ')}
                              </div>
                            </div>
                          )}

                          {(eg.solution_explanation || eg.drill.solution_explanation) && (
                            <div className="text-xs text-slate-300 bg-slate-950 p-3 rounded-xl border border-slate-800 leading-relaxed">
                              {eg.solution_explanation || eg.drill.solution_explanation}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Drill Progress Metrics */}
                      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 space-y-3">
                        <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                          <Flame className="w-3.5 h-3.5 text-amber-400" />
                          Drill Metrics
                        </h4>
                        <div className="grid grid-cols-2 gap-3">
                          <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 text-center">
                            <div className="text-[10px] text-slate-400 uppercase font-semibold">Moves</div>
                            <div className="text-lg font-bold text-white mt-0.5">
                              {eg.moves_played} <span className="text-xs text-slate-500 font-normal">/ {eg.drill.target_moves_par} par</span>
                            </div>
                          </div>
                          <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 text-center">
                            <div className="text-[10px] text-slate-400 uppercase font-semibold">Mistakes</div>
                            <div className="text-lg font-bold text-rose-400 mt-0.5">
                              {eg.mistakes}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Move History */}
                      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 space-y-3">
                        <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                          <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                          Move History ({eg.history.length})
                        </h4>
                        <div className="min-h-[70px] max-h-[120px] overflow-y-auto p-3 bg-slate-950 rounded-xl border border-slate-800 flex flex-wrap gap-1.5 items-start content-start">
                          {eg.history.length > 0 ? (
                            eg.history.map((san, idx) => (
                              <span
                                key={idx}
                                className={`px-2 py-0.5 text-xs font-mono rounded-md border font-bold ${
                                  idx % 2 === 0
                                    ? 'bg-slate-800 text-white border-slate-700'
                                    : 'bg-slate-900 text-slate-400 border-slate-800'
                                }`}
                              >
                                {Math.floor(idx / 2) + 1}{idx % 2 === 0 ? '.' : '...'} {san}
                              </span>
                            ))
                          ) : (
                            <span className="text-xs text-slate-500 italic">Make your first move on the board...</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {eg.phase === 'complete' && eg.complete_summary && (
                  <div className="bg-gradient-to-r from-emerald-950/60 via-slate-900 to-emerald-950/60 border border-emerald-500/50 rounded-2xl p-8 shadow-2xl text-center space-y-6">
                    <div className="inline-flex p-4 bg-emerald-500/20 border border-emerald-500/30 rounded-2xl text-emerald-400">
                      <Trophy className="w-10 h-10" />
                    </div>
                    <div>
                      <h3 className="text-2xl font-black text-white">
                        Theoretical Objective Achieved!
                      </h3>
                      <p className="text-sm text-slate-300 mt-1">
                        {eg.drill.title} mastered.
                      </p>
                    </div>

                    <div className="flex items-center justify-center gap-2">
                      {Array.from({ length: 3 }).map((_, i) => (
                        <Star
                          key={i}
                          className={`w-8 h-8 ${
                            i < (eg.complete_summary?.stars || 0)
                              ? 'text-amber-400 fill-amber-400 drop-shadow-[0_0_8px_rgba(251,191,36,0.5)]'
                              : 'text-slate-700'
                          }`}
                        />
                      ))}
                    </div>

                    <div className="grid grid-cols-3 max-w-md mx-auto gap-3">
                      <div className="p-3 bg-slate-950/80 rounded-xl border border-slate-800">
                        <div className="text-[10px] text-slate-400 uppercase font-semibold">Accuracy</div>
                        <div className="text-lg font-bold text-emerald-400 mt-0.5">
                          {eg.complete_summary.accuracy}%
                        </div>
                      </div>
                      <div className="p-3 bg-slate-950/80 rounded-xl border border-slate-800">
                        <div className="text-[10px] text-slate-400 uppercase font-semibold">Moves</div>
                        <div className="text-lg font-bold text-white mt-0.5">
                          {eg.complete_summary.moves_count}
                        </div>
                      </div>
                      <div className="p-3 bg-slate-950/80 rounded-xl border border-slate-800">
                        <div className="text-[10px] text-slate-400 uppercase font-semibold">Mistakes</div>
                        <div className="text-lg font-bold text-rose-400 mt-0.5">
                          {eg.complete_summary.mistakes}
                        </div>
                      </div>
                    </div>

                    <div className="flex justify-center gap-3 pt-2">
                      <button
                        onClick={() => handleStartEndgame(eg.drill?.id)}
                        className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-sm font-bold shadow-lg transition-all"
                      >
                        Retry Drill
                      </button>
                      <button
                        onClick={handleStopEndgame}
                        className="px-6 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-sm font-bold transition-all"
                      >
                        Back to Academy
                      </button>
                    </div>
                  </div>
                )}

                {/* Physical Piece Color Code Legend */}
                <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-3">
                  <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                    Hardware LED Color Code Legend (Same for White & Black)
                  </h4>
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 text-xs">
                    <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center gap-2">
                      <div className="w-3.5 h-3.5 rounded-full bg-[#FFD700] shadow-[0_0_8px_#FFD700]" />
                      <span className="font-medium text-slate-200">♔ King (Gold)</span>
                    </div>
                    <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center gap-2">
                      <div className="w-3.5 h-3.5 rounded-full bg-[#8C28F0] shadow-[0_0_8px_#8C28F0]" />
                      <span className="font-medium text-slate-200">♕ Queen (Violet)</span>
                    </div>
                    <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center gap-2">
                      <div className="w-3.5 h-3.5 rounded-full bg-[#00A0FF] shadow-[0_0_8px_#00A0FF]" />
                      <span className="font-medium text-slate-200">♖ Rook (Cyan)</span>
                    </div>
                    <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center gap-2">
                      <div className="w-3.5 h-3.5 rounded-full bg-[#DC8C00] shadow-[0_0_8px_#DC8C00]" />
                      <span className="font-medium text-slate-200">♗ Bishop (Amber)</span>
                    </div>
                    <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center gap-2">
                      <div className="w-3.5 h-3.5 rounded-full bg-[#00DC8C] shadow-[0_0_8px_#00DC8C]" />
                      <span className="font-medium text-slate-200">♘ Knight (Mint)</span>
                    </div>
                    <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800 flex items-center gap-2">
                      <div className="w-3.5 h-3.5 rounded-full bg-[#DCDCF0] shadow-[0_0_8px_#DCDCF0]" />
                      <span className="font-medium text-slate-200">♙ Pawn (Pearl)</span>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              /* Curriculum Browser Screen */
              <div className="space-y-6">
                {/* Category Filter Bar & Action Header */}
                <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col md:flex-row items-center justify-between gap-4">
                  <div className="flex items-center gap-2 flex-wrap">
                    {[
                      { id: 'all', label: 'All Drills' },
                      { id: 'pawns', label: 'Pawns' },
                      { id: 'rooks', label: 'Rooks' },
                      { id: 'minors', label: 'Minor Pieces' },
                      { id: 'queens', label: 'Queens' },
                      { id: 'custom', label: 'Custom' },
                    ].map((cat) => (
                      <button
                        key={cat.id}
                        onClick={() => setSelectedEndgameCategory(cat.id)}
                        className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                          selectedEndgameCategory === cat.id
                            ? 'bg-emerald-600 text-white shadow-md'
                            : 'bg-slate-950 border border-slate-800 text-slate-400 hover:text-white'
                        }`}
                      >
                        {cat.label}
                      </button>
                    ))}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setIsCustomModalOpen(true)}
                      className="px-4 py-2 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 rounded-xl text-xs font-bold transition-all shadow-sm flex items-center gap-1.5"
                    >
                      <Layers className="w-4 h-4" />
                      Custom FEN Drill
                    </button>
                    <button
                      onClick={handleResetEndgameProgress}
                      className="px-3 py-2 bg-slate-950 hover:bg-slate-800 text-slate-400 hover:text-rose-400 border border-slate-800 rounded-xl text-xs font-semibold transition-all"
                      title="Reset Progress"
                    >
                      <RotateCcw className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Drills Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                  {endgameDrills
                    .filter((d) => selectedEndgameCategory === 'all' || d.category === selectedEndgameCategory)
                    .map((drill) => (
                      <div
                        key={drill.id}
                        className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl flex flex-col justify-between space-y-4 hover:border-emerald-500/40 transition-all group"
                      >
                        <div className="space-y-2.5">
                          <div className="flex items-center justify-between">
                            <span className="px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                              {drill.category_title}
                            </span>
                            <div className="flex items-center gap-1">
                              {Array.from({ length: 3 }).map((_, i) => (
                                <Star
                                  key={i}
                                  className={`w-3.5 h-3.5 ${
                                    drill.completed && i < drill.stars
                                      ? 'text-amber-400 fill-amber-400'
                                      : 'text-slate-700'
                                  }`}
                                />
                              ))}
                            </div>
                          </div>

                          <h4 className="text-base font-bold text-white group-hover:text-emerald-300 transition-colors">
                            {drill.title}
                          </h4>
                          <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                            {drill.description}
                          </p>
                        </div>

                        <div className="space-y-3 pt-3 border-t border-slate-800/80">
                          <div className="flex items-center justify-between text-xs text-slate-400">
                            <span>Goal: <strong className="text-white font-semibold">{drill.target_goal.toUpperCase()}</strong></span>
                            <span>Par: <strong className="text-white font-semibold">{drill.target_moves_par} moves</strong></span>
                          </div>

                          <button
                            onClick={() => handleStartEndgame(drill.id)}
                            className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold transition-all shadow-md flex items-center justify-center gap-1.5"
                          >
                            <PlayCircle className="w-4 h-4" />
                            Start Drill on Board
                          </button>
                        </div>
                      </div>
                    ))}
                </div>

                {/* Physical Gesture Tip */}
                <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-2xl text-xs text-slate-400 leading-relaxed flex items-center gap-3">
                  <div className="p-2 bg-emerald-600/20 border border-emerald-500/30 rounded-xl text-emerald-400 shrink-0">
                    <GraduationCap className="w-5 h-5" />
                  </div>
                  <div>
                    <span className="font-bold text-slate-200">Autonomous Board Gesture: </span>
                    Lift the <span className="font-mono text-emerald-300 font-bold">c2</span> pawn to open the Endgame Academy directly on the physical board. Select category on rank 1 (a1: Pawns, b1: Rooks, c1: Minors, d1: Queens) and replace c2 to confirm!
                  </div>
                </div>
              </div>
            )}

            {/* Custom FEN Modal */}
            {isCustomModalOpen && (
              <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-bold text-white flex items-center gap-2">
                      <Layers className="w-5 h-5 text-emerald-400" />
                      Create Custom Endgame Drill
                    </h3>
                    <button
                      onClick={() => setIsCustomModalOpen(false)}
                      className="p-1 text-slate-400 hover:text-white rounded-lg"
                    >
                      <X className="w-5 h-5" />
                    </button>
                  </div>

                  <form onSubmit={handleCreateCustomEndgame} className="space-y-3.5 text-xs">
                    <div>
                      <label className="block text-slate-300 font-semibold mb-1">Drill Title</label>
                      <input
                        type="text"
                        value={customTitleInput}
                        onChange={(e) => setCustomTitleInput(e.target.value)}
                        placeholder="e.g. My Pawn Endgame"
                        className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-white focus:outline-none focus:border-emerald-500"
                      />
                    </div>

                    <div>
                      <label className="block text-slate-300 font-semibold mb-1">FEN Position</label>
                      <input
                        type="text"
                        required
                        value={customFenInput}
                        onChange={(e) => setCustomFenInput(e.target.value)}
                        placeholder="8/8/8/4k3/8/8/4P3/4K3 w - - 0 1"
                        className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-white font-mono focus:outline-none focus:border-emerald-500"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-slate-300 font-semibold mb-1">Player Color</label>
                        <select
                          value={customColorInput}
                          onChange={(e) => setCustomColorInput(e.target.value as 'white' | 'black')}
                          className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-white focus:outline-none focus:border-emerald-500"
                        >
                          <option value="white">White</option>
                          <option value="black">Black</option>
                        </select>
                      </div>

                      <div>
                        <label className="block text-slate-300 font-semibold mb-1">Target Goal</label>
                        <select
                          value={customGoalInput}
                          onChange={(e) => setCustomGoalInput(e.target.value as 'win' | 'draw' | 'mate')}
                          className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-white focus:outline-none focus:border-emerald-500"
                        >
                          <option value="win">Win</option>
                          <option value="draw">Draw</option>
                          <option value="mate">Checkmate</option>
                        </select>
                      </div>
                    </div>

                    <div>
                      <label className="block text-slate-300 font-semibold mb-1">Description (Optional)</label>
                      <textarea
                        rows={2}
                        value={customDescInput}
                        onChange={(e) => setCustomDescInput(e.target.value)}
                        placeholder="Key theoretical ideas or objectives..."
                        className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-white focus:outline-none focus:border-emerald-500"
                      />
                    </div>

                    <div>
                      <label className="block text-slate-300 font-semibold mb-1">Theoretical Hint (Optional)</label>
                      <input
                        type="text"
                        value={customHintInput}
                        onChange={(e) => setCustomHintInput(e.target.value)}
                        placeholder="Key hint for the player..."
                        className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-white focus:outline-none focus:border-emerald-500"
                      />
                    </div>

                    <div className="flex justify-end gap-2 pt-2">
                      <button
                        type="button"
                        onClick={() => setIsCustomModalOpen(false)}
                        className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl font-semibold"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-bold shadow-md"
                      >
                        Launch Drill
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
};

export default AnalysisTab;
