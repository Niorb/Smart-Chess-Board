import React, { useState, useEffect, useMemo } from 'react';
import {
  Compass,
  Brain,
  History,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  SkipBack,
  SkipForward,
} from 'lucide-react';
import type { BoardState } from '../../hooks/useBoardState';
import WebAnalysisBoard from '../board/WebAnalysisBoard';
import { MoveHistoryTree } from './MoveHistoryTree';
import {
  startAnalysis,
  stepAnalysis,
  navAnalysis,
  sendAnalysisMove,
  resetAnalysisBranch,
  getRecentLichessGames,
  type LichessRecentGame,
} from '../../api';

interface AnalysisTabProps {
  boardState: BoardState;
}

export const AnalysisTab: React.FC<AnalysisTabProps> = ({ boardState }) => {
  const analysis = boardState.analysis;
  const [recentGames, setRecentGames] = useState<LichessRecentGame[]>([]);
  const [isLoadingRecentGames, setIsLoadingRecentGames] = useState<boolean>(false);

  const currentPly = analysis?.current_ply ?? 0;
  const totalPlys = analysis?.total_plys ?? 0;
  const currentFen = analysis?.fen || 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

  // Auto-start web analysis mode on mount if not already in analysis or playing
  useEffect(() => {
    if (!boardState.analysis?.active && boardState.status !== 'PLAYING') {
      startAnalysis({ web_only: true }).catch((err) => {
        console.warn('Auto-start analysis error:', err);
      });
    }
  }, [boardState.analysis?.active, boardState.status]);

  // Fetch recent Lichess games
  useEffect(() => {
    let cancelled = false;
    getRecentLichessGames(10)
      .then((res) => {
        if (!cancelled && res?.games) {
          setRecentGames(res.games);
        }
      })
      .catch((err) => {
        console.warn('Error fetching recent games:', err);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const handleRefreshRecentGames = async () => {
    setIsLoadingRecentGames(true);
    try {
      const res = await getRecentLichessGames(10);
      if (res?.games) {
        setRecentGames(res.games);
      }
    } catch (err) {
      console.warn('Error fetching recent games:', err);
    } finally {
      setIsLoadingRecentGames(false);
    }
  };

  // Compute parsed move list from played_analyses or game_moves
  const parsedMoves = useMemo(() => {
    if (analysis?.played_analyses && analysis.played_analyses.length > 0) {
      return analysis.played_analyses.map((m) => ({
        ply: m.ply,
        san: m.san || m.uci,
        uci: m.uci,
        classification: m.classification,
        delta_cp: m.delta_cp,
      }));
    }
    const movesList = [];
    const gameMoves = analysis?.game_moves || [];
    const evals = analysis?.evaluations || [];
    for (let i = 0; i < gameMoves.length; i++) {
      const evalData = evals[i];
      movesList.push({
        ply: i + 1,
        san: gameMoves[i],
        uci: gameMoves[i],
        score_cp: evalData?.score_cp,
        mate: evalData?.mate,
      });
    }
    return movesList;
  }, [analysis]);

  // Navigation handlers
  const handleNavPly = async (ply: number) => {
    try {
      await stepAnalysis(ply);
    } catch (err) {
      console.error('Error navigating analysis ply:', err);
    }
  };

  const handleNavDirection = async (direction: 'back' | 'forward' | 'start' | 'end') => {
    try {
      await navAnalysis(direction);
    } catch (err) {
      console.error('Error navigating analysis direction:', err);
    }
  };

  const handlePlayAnalysisMove = async (uci: string) => {
    try {
      await sendAnalysisMove(uci);
    } catch (err) {
      console.error('Error sending analysis move:', err);
    }
  };

  const handleResetBranch = async () => {
    try {
      await resetAnalysisBranch();
    } catch (err) {
      console.error('Error resetting analysis branch:', err);
    }
  };

  // Keyboard navigation shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        handleNavDirection('back');
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        handleNavDirection('forward');
      } else if (e.key === 'Home') {
        e.preventDefault();
        handleNavDirection('start');
      } else if (e.key === 'End') {
        e.preventDefault();
        handleNavDirection('end');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const activeEval = analysis?.current_eval || analysis?.evaluations?.[currentPly - 1];

  const isComputing = Boolean(analysis?.is_computing || analysis?.is_loading);

  return (
    <div className="w-full flex flex-col lg:flex-row items-center lg:items-start justify-center gap-6 max-w-7xl mx-auto px-2 sm:px-4">
      {/* Left: Interactive Analysis Board Stage */}
      <div className="w-full max-w-[700px] flex flex-col gap-3 shrink-0">
        <WebAnalysisBoard
          fen={currentFen}
          legalMoves={analysis?.legal_moves || []}
          inCheck={analysis?.in_check}
          lastMoveUci={analysis?.game_moves?.[currentPly - 1] || null}
          isBranching={analysis?.is_branching}
          showEvalBar={true}
          winChance={activeEval?.win_chance}
          scoreCp={activeEval?.score_cp}
          mate={activeEval?.mate}
          isComputing={isComputing}
          isLoading={analysis?.is_loading}
          onMovePlayed={handlePlayAnalysisMove}
          topLines={analysis?.top_lines}
          showEngineLines={true}
          onLineClick={(idx) => {
            const firstMove = analysis?.top_lines?.[idx]?.uci?.[0];
            if (firstMove) handlePlayAnalysisMove(firstMove);
          }}
          headerTitle={
            <span className="text-xs font-bold font-display text-white flex items-center gap-1.5">
              <Compass size={14} className="text-violet-400" />
              The Grandmaster's Lens
            </span>
          }
        />

        {/* Tactical Navigation Deck */}
        <div className="glass-panel rounded-2xl p-2.5 flex items-center justify-between gap-2">
          <div className="flex items-center gap-1">
            <button
              onClick={() => handleNavDirection('start')}
              disabled={currentPly <= 0}
              className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:opacity-30 text-slate-300 transition-all active:scale-95"
              title="First move (Home)"
            >
              <SkipBack size={15} />
            </button>
            <button
              onClick={() => handleNavDirection('back')}
              disabled={currentPly <= 0}
              className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:opacity-30 text-slate-300 transition-all active:scale-95"
              title="Previous move (Left Arrow)"
            >
              <ChevronLeft size={15} />
            </button>
          </div>

          <div className="flex items-center gap-2 font-mono text-xs font-bold text-slate-200">
            <span>Ply {currentPly}</span>
            <span className="text-slate-500">/</span>
            <span className="text-slate-400">{totalPlys}</span>
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={() => handleNavDirection('forward')}
              disabled={currentPly >= totalPlys && !analysis?.is_branching}
              className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:opacity-30 text-slate-300 transition-all active:scale-95"
              title="Next move (Right Arrow)"
            >
              <ChevronRight size={15} />
            </button>
            <button
              onClick={() => handleNavDirection('end')}
              disabled={currentPly >= totalPlys}
              className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:opacity-30 text-slate-300 transition-all active:scale-95"
              title="Latest move (End)"
            >
              <SkipForward size={15} />
            </button>
          </div>
        </div>
      </div>

      {/* Right: Analysis Inspector & Move History */}
      <div className="w-full max-w-[500px] flex flex-col gap-4">
        {/* Live Evaluation & Depth Overview */}
        <div className="glass-panel rounded-3xl p-5 flex flex-col gap-3 text-left shadow-artisan">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 font-mono flex items-center gap-1.5">
              <Brain size={14} className="text-violet-400" />
              Stockfish 17 Engine Telemetry
            </h3>
            {isComputing ? (
              <span className="text-[10px] font-mono font-bold px-2.5 py-0.5 rounded-full bg-violet-500/20 text-violet-300 border border-violet-500/40 flex items-center gap-1.5 animate-pulse">
                <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-ping" />
                Depth: 20 • Computing...
              </span>
            ) : (
              <span className="text-[10px] font-mono font-bold px-2.5 py-0.5 rounded-full bg-violet-500/20 text-violet-300 border border-violet-500/40">
                Depth: 20
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 pt-1">
            <div className="p-3 rounded-2xl bg-slate-900/80 border border-slate-800 flex flex-col">
              <span className="text-[10px] font-mono uppercase text-slate-400">Position Score</span>
              <span className={`text-base font-extrabold font-mono text-emerald-400 mt-0.5 ${isComputing ? 'animate-pulse' : ''}`}>
                {activeEval?.mate !== null && activeEval?.mate !== undefined
                  ? `M${Math.abs(activeEval.mate)}`
                  : activeEval?.score_cp !== null && activeEval?.score_cp !== undefined
                  ? `${activeEval.score_cp >= 0 ? '+' : ''}${(activeEval.score_cp / 100).toFixed(2)}`
                  : isComputing
                  ? 'Calculating...'
                  : '0.00'}
              </span>
            </div>

            <div className="p-3 rounded-2xl bg-slate-900/80 border border-slate-800 flex flex-col">
              <span className="text-[10px] font-mono uppercase text-slate-400">Win Probability</span>
              <span className={`text-base font-extrabold font-mono text-amber-400 mt-0.5 ${isComputing ? 'animate-pulse' : ''}`}>
                {activeEval?.win_chance !== undefined && activeEval?.win_chance !== null
                  ? `${activeEval.win_chance.toFixed(1)}% White`
                  : isComputing
                  ? 'Analyzing...'
                  : '50.0% White'}
              </span>
            </div>
          </div>
        </div>

        {/* Move History Tree Card */}
        <div className="glass-panel rounded-3xl p-5 flex flex-col gap-3 text-left shadow-artisan flex-1">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 font-mono">
              Move Tree &amp; Variations
            </h3>
            <span className="text-[10px] font-mono text-slate-400">
              {parsedMoves.length} moves
            </span>
          </div>

          <MoveHistoryTree
            moves={parsedMoves}
            currentPly={currentPly}
            onNavigatePly={handleNavPly}
            isBranching={analysis?.is_branching}
            branchMoves={analysis?.branch_moves}
            anchorPly={analysis?.anchor_ply}
            onResetBranch={handleResetBranch}
          />
        </div>

        {/* Recent Games Drawer */}
        <div className="glass-panel rounded-3xl p-4 flex flex-col gap-2.5 text-left">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400 font-mono flex items-center gap-1.5">
              <History size={13} className="text-cyan-400" />
              Load Recent Lichess Match
            </span>
            <button
              onClick={handleRefreshRecentGames}
              disabled={isLoadingRecentGames}
              className="text-slate-400 hover:text-white"
            >
              <RefreshCw size={12} className={isLoadingRecentGames ? 'animate-spin' : ''} />
            </button>
          </div>

          <div className="flex flex-col gap-1 max-h-36 overflow-y-auto pr-1">
            {recentGames.map((g) => (
              <button
                key={g.id}
                onClick={async () => {
                  const moves = g.moves_uci || (g as unknown as { moves?: string[] }).moves || [];
                  await startAnalysis({ moves_uci: moves, game_id: g.id, web_only: true });
                }}
                className="p-2 rounded-xl bg-slate-900/60 hover:bg-slate-800/80 border border-slate-800 text-left flex items-center justify-between transition-all"
              >
                <div className="flex flex-col">
                  <span className="text-[11px] font-bold font-display text-white">
                    vs. {g.opponent?.username || 'Opponent'} ({g.speed})
                  </span>
                  <span className="text-[9px] text-slate-400 font-mono">
                    Result: {g.winner ? `${g.winner} won` : 'Draw'} • {g.moves_count || 0} moves
                  </span>
                </div>
                <span className="text-[9px] font-mono text-amber-400 font-bold px-2 py-0.5 rounded bg-amber-400/10">
                  Analyze
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AnalysisTab;
