import React, { useRef, useEffect } from 'react';
import { RotateCcw } from 'lucide-react';

interface MoveItem {
  ply: number;
  san: string;
  uci: string;
  classification?: string;
  score_cp?: number | null;
  mate?: number | null;
}

interface MoveHistoryTreeProps {
  moves: MoveItem[];
  currentPly: number;
  onNavigatePly: (ply: number) => void;
  isBranching?: boolean;
  branchMoves?: string[];
  anchorPly?: number | null;
  onResetBranch?: () => void;
}

const CLASS_BADGES: Record<string, { label: string; color: string }> = {
  best: { label: '!', color: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' },
  good: { label: '✓', color: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30' },
  book: { label: '📖', color: 'bg-slate-700/50 text-slate-300 border-slate-600/30' },
  inaccuracy: { label: '?!', color: 'bg-amber-500/20 text-amber-300 border-amber-500/30' },
  mistake: { label: '?', color: 'bg-orange-500/20 text-orange-300 border-orange-500/30' },
  blunder: { label: '??', color: 'bg-rose-500/25 text-rose-300 border-rose-500/40 font-bold' },
};

export const MoveHistoryTree: React.FC<MoveHistoryTreeProps> = ({
  moves,
  currentPly,
  onNavigatePly,
  isBranching,
  branchMoves = [],
  anchorPly,
  onResetBranch,
}) => {
  const activeRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (activeRef.current) {
      activeRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [currentPly]);

  // Group moves into pairs (White move, Black move)
  const movePairs = [];
  for (let i = 0; i < moves.length; i += 2) {
    movePairs.push({
      moveNum: Math.floor(i / 2) + 1,
      white: moves[i],
      black: moves[i + 1],
    });
  }

  return (
    <div className="flex flex-col gap-2.5 h-full">
      {/* Branching Sandbox Banner */}
      {isBranching && (
        <div className="p-3 rounded-2xl bg-gradient-to-r from-violet-950/80 to-amber-950/80 border border-violet-500/40 shadow-sm flex items-center justify-between gap-2 text-left">
          <div className="flex flex-col">
            <span className="text-[11px] font-bold font-display text-violet-200">
              Variation Branch (Ply {anchorPly ?? 0})
            </span>
            <span className="text-[10px] text-amber-300/90 font-mono">
              +{branchMoves.length} alternate move{branchMoves.length === 1 ? '' : 's'}
            </span>
          </div>
          {onResetBranch && (
            <button
              onClick={onResetBranch}
              className="px-2.5 py-1 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-display font-bold text-[10px] shadow flex items-center gap-1 transition-all"
            >
              <RotateCcw size={11} />
              <span>Back to Game</span>
            </button>
          )}
        </div>
      )}

      {/* Move History Table */}
      <div className="flex-1 overflow-y-auto max-h-[360px] pr-1 space-y-1">
        {movePairs.length === 0 ? (
          <div className="p-6 text-center text-slate-500 text-xs font-mono">
            No moves recorded yet
          </div>
        ) : (
          movePairs.map((pair) => (
            <div
              key={pair.moveNum}
              className="grid grid-cols-12 items-center p-1 rounded-xl hover:bg-slate-900/60 transition-colors text-xs font-mono"
            >
              <span className="col-span-2 text-slate-500 text-right pr-2 select-none">
                {pair.moveNum}.
              </span>

              {/* White Move */}
              <button
                ref={currentPly === pair.white.ply ? activeRef : null}
                onClick={() => onNavigatePly(pair.white.ply)}
                className={`col-span-5 px-2 py-1 rounded-lg text-left flex items-center justify-between transition-all ${
                  currentPly === pair.white.ply
                    ? 'bg-amber-500/25 text-amber-200 border border-amber-400/50 font-bold shadow-sm'
                    : 'text-slate-200 hover:bg-slate-800'
                }`}
              >
                <span>{pair.white.san || pair.white.uci}</span>
                {pair.white.classification && CLASS_BADGES[pair.white.classification] && (
                  <span
                    className={`text-[9px] px-1 py-0.2 rounded border font-bold ${
                      CLASS_BADGES[pair.white.classification].color
                    }`}
                  >
                    {CLASS_BADGES[pair.white.classification].label}
                  </span>
                )}
              </button>

              {/* Black Move */}
              {pair.black ? (
                <button
                  ref={currentPly === pair.black.ply ? activeRef : null}
                  onClick={() => onNavigatePly(pair.black.ply)}
                  className={`col-span-5 px-2 py-1 rounded-lg text-left flex items-center justify-between transition-all ${
                    currentPly === pair.black.ply
                      ? 'bg-amber-500/25 text-amber-200 border border-amber-400/50 font-bold shadow-sm'
                      : 'text-slate-200 hover:bg-slate-800'
                  }`}
                >
                  <span>{pair.black.san || pair.black.uci}</span>
                  {pair.black.classification && CLASS_BADGES[pair.black.classification] && (
                    <span
                      className={`text-[9px] px-1 py-0.2 rounded border font-bold ${
                        CLASS_BADGES[pair.black.classification].color
                      }`}
                    >
                      {CLASS_BADGES[pair.black.classification].label}
                    </span>
                  )}
                </button>
              ) : (
                <div className="col-span-5" />
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
