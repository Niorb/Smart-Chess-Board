import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
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
  PlayCircle
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
  type LichessRecentGame
} from '../api';

interface AnalysisTabProps {
  boardState: BoardState;
}

const AnalysisTab: React.FC<AnalysisTabProps> = ({ boardState }) => {
  const analysis = boardState.analysis;
  type SubMode = 'review' | 'blunder_drill' | 'replay';
  const serverSubMode: SubMode =
    analysis?.submode === 'blunder_drill'
      ? 'blunder_drill'
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
  const [feedbackMsg, setFeedbackMsg] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);
  const [guessInput, setGuessInput] = useState<string>('');
  const [webMoveInput, setWebMoveInput] = useState<string>('');
  const [onMainlineToast, setOnMainlineToast] = useState<boolean>(false);
  const prevOnMainlineRef = useRef<boolean>(true);
  const toastTimerRef = useRef<number | null>(null);
  const [webBoardOpen, setWebBoardOpen] = useState<boolean>(false);

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
  const handleStartWebAnalysis = async () => {
    setWebBoardOpen(true);
    if (analysis?.active && analysis.submode === 'review') {
      // Analysis already running: just reveal the board.
      return;
    }
    setFeedbackMsg({ text: 'Analyzing game with Stockfish (webapp only)...', type: 'info' });
    try {
      await startAnalysis();
      setFeedbackMsg({ text: 'Analysis ready — use ← → / h l on the board below.', type: 'success' });
      setTimeout(() => setFeedbackMsg(null), 3500);
    } catch {
      setFeedbackMsg({ text: 'Failed to start analysis.', type: 'error' });
    }
  };

  const handleLoadRecentGame = async (game: LichessRecentGame) => {
    setSelectedGameId(game.id);
    setFeedbackMsg({
      text: `Loading & analyzing match vs ${game.opponent.username} (${game.opening.name})...`,
      type: 'info',
    });
    try {
      await startAnalysis({ moves_uci: game.moves_uci });
      setFeedbackMsg({
        text: `Analysis ready for match vs ${game.opponent.username}! (${game.moves_count} moves)`,
        type: 'success',
      });
      setTimeout(() => setFeedbackMsg(null), 3500);
    } catch {
      setFeedbackMsg({ text: 'Failed to load game for analysis.', type: 'error' });
    }
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
    try {
      const res = await navAnalysis(direction);
      const onMainline = !!res?.on_mainline;
      if (onMainline && !prevOnMainlineRef.current) {
        setOnMainlineToast(true);
        if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current);
        toastTimerRef.current = window.setTimeout(() => setOnMainlineToast(false), 2500);
      }
      prevOnMainlineRef.current = onMainline;
    } catch (err) {
      console.error('Error navigating analysis:', err);
    }
  }, [analysis?.active, analysis?.submode]);

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
    try {
      const res = await sendAnalysisMove(mv);
      const result = (res as { result?: { action?: string; analysis?: { is_branching?: boolean } } })?.result
        ?? (res as { action?: string; analysis?: { is_branching?: boolean } });
      if (!result || result.action === 'illegal' || result.action === 'error') {
        setFeedbackMsg({ text: `Illegal or unparsable move: "${mv}"`, type: 'error' });
        setTimeout(() => setFeedbackMsg(null), 3000);
        return;
      }
      prevOnMainlineRef.current = !result.analysis?.is_branching;
      setWebMoveInput('');
      if (result.action === 'branch') {
        setFeedbackMsg({ text: '⚡ Variation sandbox active — ← / h steps back one move.', type: 'info' });
        setTimeout(() => setFeedbackMsg(null), 3000);
      }
    } catch (err) {
      console.error('Error playing web analysis move:', err);
    }
  }, [analysis?.active, analysis?.submode]);

  const handleResetBranch = async () => {
    try {
      await resetAnalysisBranch();
      setFeedbackMsg({ text: 'Restored main game timeline.', type: 'info' });
      setTimeout(() => setFeedbackMsg(null), 2500);
    } catch (err) {
      console.error('Error resetting branch:', err);
    }
  };

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

  const handleBlunderAttemptSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!guessInput.trim()) return;
    try {
      const res = await submitBlunderAttempt(guessInput.trim());
      if (res.correct) {
        setFeedbackMsg({ text: `🏆 ${res.message}`, type: 'success' });
      } else {
        setFeedbackMsg({ text: `❌ ${res.message} (${res.attempts_remaining} attempts left)`, type: 'error' });
      }
      setGuessInput('');
    } catch {
      setFeedbackMsg({ text: 'Error submitting blunder attempt.', type: 'error' });
    }
  };

  const handleToggleHint = async () => {
    try {
      const res = await toggleBlunderHint();
      setFeedbackMsg({ 
        text: res.hint_active ? '💡 Move origin highlighted in Mint Emerald on the board.' : 'Hint turned off.', 
        type: 'info' 
      });
      setTimeout(() => setFeedbackMsg(null), 3000);
    } catch (err) {
      console.error('Error toggling hint:', err);
    }
  };

  const getQualityBadge = (tier?: string) => {
    switch (tier) {
      case 'best':
        return <span title="Best Move (Δ ≤ 15 cp) — Animated in Mint Emerald" className="px-2 py-0.5 text-xs font-bold rounded bg-emerald-950/90 text-emerald-300 border border-emerald-500/40 shadow-sm">BEST</span>;
      case 'good':
        return <span title="Good Move (15 < Δ ≤ 60 cp) — Animated in Cyan Azure" className="px-2 py-0.5 text-xs font-bold rounded bg-cyan-950/90 text-cyan-300 border border-cyan-500/40 shadow-sm">GOOD</span>;
      case 'inaccuracy':
        return <span title="Inaccuracy (60 < Δ ≤ 150 cp) — Animated in Warm Amber" className="px-2 py-0.5 text-xs font-bold rounded bg-amber-950/90 text-amber-300 border border-amber-500/40 shadow-sm">INACC</span>;
      case 'blunder':
        return <span title="Blunder (Δ > 150 cp) — Animated in Laser Crimson" className="px-2 py-0.5 text-xs font-bold rounded bg-rose-950/90 text-rose-300 border border-rose-500/40 shadow-sm">BLUNDER</span>;
      default:
        return <span className="px-2 py-0.5 text-xs font-bold rounded bg-slate-800 text-slate-400">MOVE</span>;
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
        </div>
      </div>

      {/* Feedback Toast Banner */}
      {feedbackMsg && (
        <div className={`p-3.5 rounded-xl border flex items-center justify-between text-xs font-medium animate-fadeIn ${
          feedbackMsg.type === 'success'
            ? 'bg-emerald-950/80 border-emerald-500/40 text-emerald-300'
            : feedbackMsg.type === 'error'
            ? 'bg-rose-950/80 border-rose-500/40 text-rose-300'
            : 'bg-violet-950/80 border-violet-500/40 text-violet-300'
        }`}>
          <span>{feedbackMsg.text}</span>
          <button onClick={() => setFeedbackMsg(null)} className="opacity-60 hover:opacity-100">✕</button>
        </div>
      )}

      {/* Back-on-Mainline Confirmation Toast */}
      {onMainlineToast && (
        <div className="p-3.5 rounded-xl bg-emerald-600/90 border border-emerald-400/60 text-white text-xs font-bold flex items-center gap-2 shadow-lg animate-fadeIn">
          <CheckCircle2 className="w-4 h-4" />
          Back on the main game line
        </div>
      )}

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
              onClick={handleStartWebAnalysis}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all shadow-md flex items-center gap-1.5 shrink-0 ${
                analysis?.active
                  ? 'bg-slate-800 hover:bg-slate-700 text-slate-200'
                  : 'bg-emerald-600 hover:bg-emerald-500 text-white'
              }`}
            >
              {analysis?.active ? 'Show Web Board' : 'Analyse in Webapp'}
            </button>
          </div>

          {/* Interactive web board (keyboard navigation lives here) */}
          {webBoardOpen &&
            (analysis?.active ? (
              (() => {
                const isBranching = !!analysis?.is_branching;
                const lastMoveUci = isBranching
                  ? analysis?.branch_moves?.[analysis.branch_moves.length - 1] ?? null
                  : currentPly > 0
                  ? analysis?.game_moves?.[currentPly - 1] ?? null
                  : null;
                return (
                  <WebAnalysisBoard
                    fen={analysis?.fen ?? ''}
                    lastMoveUci={lastMoveUci}
                    isBranching={isBranching}
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
                    Select any of your last 10 online matches to load into full Stockfish review and physical board playback.
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

                            <button
                              onClick={() => handleLoadRecentGame(game)}
                              className="px-3 py-1 bg-violet-600 hover:bg-violet-500 text-white rounded-lg font-bold text-xs flex items-center gap-1 shadow transition-all hover:scale-105 active:scale-95"
                            >
                              <PlayCircle className="w-3.5 h-3.5" />
                              Analyze
                            </button>
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
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Game Notation & Evaluation Breakdown</h4>
                <div className="max-h-72 overflow-y-auto pr-2 space-y-1">
                  {Array.from({ length: Math.ceil(playedAnalyses.length / 2) }).map((_, moveIdx) => {
                    const whitePly = moveIdx * 2;
                    const blackPly = moveIdx * 2 + 1;
                    const wMove = playedAnalyses[whitePly];
                    const bMove = playedAnalyses[blackPly];

                    return (
                      <div key={moveIdx} className="grid grid-cols-11 gap-2 p-1.5 rounded-lg text-xs hover:bg-slate-800/40 transition-colors">
                        <span className="col-span-1 text-slate-500 font-bold">{moveIdx + 1}.</span>
                        
                        {/* White Move */}
                        <div
                          onClick={() => handleStep(whitePly + 1)}
                          className={`col-span-5 flex items-center justify-between p-1.5 rounded-md cursor-pointer transition-colors ${
                            currentPly === whitePly + 1 ? 'bg-violet-600/30 border border-violet-500/50 text-white font-bold' : 'text-slate-300 hover:bg-slate-800'
                          }`}
                        >
                          <span>{wMove?.san || wMove?.uci}</span>
                          {wMove && getQualityBadge(wMove.classification)}
                        </div>

                        {/* Black Move */}
                        {bMove ? (
                          <div
                            onClick={() => handleStep(blackPly + 1)}
                            className={`col-span-5 flex items-center justify-between p-1.5 rounded-md cursor-pointer transition-colors ${
                              currentPly === blackPly + 1 ? 'bg-violet-600/30 border border-violet-500/50 text-white font-bold' : 'text-slate-300 hover:bg-slate-800'
                            }`}
                          >
                            <span>{bMove.san || bMove.uci}</span>
                            {getQualityBadge(bMove.classification)}
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

      {/* SUB-VIEW 2: BLUNDER BLITZ DRILL */}
      {subMode === 'blunder_drill' && (
        <div className="space-y-6">
          {blunders.length > 0 ? (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Blunder selector sidebar */}
              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 space-y-3">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Mistakes Extracted ({blunders.length})</h4>
                <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                  {blunders.map((b, idx) => (
                    <div
                      key={idx}
                      onClick={() => startBlunderDrill(idx)}
                      className={`p-3 rounded-xl border cursor-pointer transition-all ${
                        activeBlunderIndex === idx
                          ? 'bg-rose-950/60 border-rose-500 text-white shadow-md'
                          : 'bg-slate-950/50 border-slate-800 text-slate-400 hover:bg-slate-800'
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs font-bold mb-1">
                        <span>Puzzle #{idx + 1} (Move {Math.floor(b.ply_index / 2) + 1})</span>
                        {getQualityBadge(b.classification)}
                      </div>
                      <div className="text-xs text-slate-400 line-clamp-1">{b.description}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Active Blunder Challenge Card */}
              <div className="lg:col-span-2 bg-slate-900/90 border border-slate-800 rounded-2xl p-6 flex flex-col justify-between space-y-6">
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <Flame className="w-5 h-5 text-rose-400" />
                      <h3 className="text-base font-bold text-white">
                        Blunder Rehabilitation #{activeBlunderIndex + 1}
                      </h3>
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-rose-400 font-bold bg-rose-950/50 px-3 py-1 rounded-full border border-rose-500/30">
                      Attempts: {Array.from({ length: analysis?.blunder_attempts ?? 3 }).map(() => '❤️').join('')}
                    </div>
                  </div>

                  <p className="text-sm text-slate-300 bg-slate-950 p-4 rounded-xl border border-slate-800 leading-relaxed">
                    {currentBlunder?.description || 'Find the best tactical refutation in this position.'}
                  </p>

                  <div className="mt-4 flex items-center gap-3">
                    <button
                      onClick={handleToggleHint}
                      className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-amber-300 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all border border-amber-500/20"
                    >
                      <Lightbulb className="w-4 h-4" />
                      {analysis?.blunder_hint_active ? 'Hide LED Hint' : 'Show LED Hint on Board'}
                    </button>
                  </div>
                </div>

                {/* Move Guess Form */}
                <form onSubmit={handleBlunderAttemptSubmit} className="flex items-center gap-3">
                  <input
                    type="text"
                    placeholder="Enter algebraic move (e.g. e2e4 or Re8)..."
                    value={guessInput}
                    onChange={(e) => setGuessInput(e.target.value)}
                    className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-rose-500"
                  />
                  <button
                    type="submit"
                    className="px-5 py-2.5 bg-rose-600 hover:bg-rose-500 text-white rounded-xl text-sm font-bold transition-all shadow-md"
                  >
                    Submit Move
                  </button>
                </form>
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
    </div>
  );
};

export default AnalysisTab;
