import React, { useState } from 'react';
import { 
  Flame, 
  Lightbulb, 
  CheckCircle2, 
  AlertTriangle, 
  Eye, 
  Play, 
  ArrowRight,
  Sparkles
} from 'lucide-react';
import type { BlunderAttemptResult } from '../../api';

interface BlunderDrillCardProps {
  drillState?: {
    is_active?: boolean;
    title?: string;
    description?: string;
    fen?: string;
    best_move?: string;
    best_san?: string;
    hint_level?: number;
    hint_text?: string;
    solved?: boolean;
  } | null;
  onStartDrill: (gameId?: string) => void;
  onSubmitAttempt: (uci: string) => Promise<BlunderAttemptResult | null>;
  onToggleHint: () => void;
  onApplyOpponentMove: () => void;
  loading: boolean;
}

export const BlunderDrillCard: React.FC<BlunderDrillCardProps> = ({
  drillState,
  onStartDrill,
  onSubmitAttempt,
  onToggleHint,
  onApplyOpponentMove,
  loading,
}) => {
  const [guessInput, setGuessInput] = useState('');
  const [attemptResult, setAttemptResult] = useState<BlunderAttemptResult | null>(null);
  const [showSolution, setShowSolution] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!guessInput.trim()) return;
    const res = await onSubmitAttempt(guessInput.trim());
    if (res) {
      setAttemptResult(res);
      setGuessInput('');
    }
  };

  return (
    <div className="glass-panel rounded-3xl p-5 flex flex-col gap-4 text-left shadow-artisan">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-xl bg-rose-500/20 text-rose-300 border border-rose-500/40">
            <Flame size={18} />
          </div>
          <div>
            <h3 className="text-sm font-bold font-display text-white">Blunder Drill Master</h3>
            <p className="text-[11px] text-slate-400 font-sans">Turn your past mistakes into tactical breakthroughs</p>
          </div>
        </div>
        <button
          onClick={() => {
            setShowSolution(false);
            setAttemptResult(null);
            onStartDrill();
          }}
          disabled={loading}
          className="px-3 py-1.5 rounded-xl bg-gradient-to-r from-rose-600 to-rose-500 hover:brightness-110 text-white text-xs font-bold font-display shadow-rose-glow flex items-center gap-1.5 transition-all"
        >
          <Sparkles size={13} />
          <span>New Blunder Drill</span>
        </button>
      </div>

      {drillState && drillState.is_active ? (
        <div className="flex flex-col gap-3 p-4 rounded-2xl bg-slate-900/80 border border-slate-800">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold font-display text-amber-300">
              {drillState.title || 'Blunder Position'}
            </span>
            {drillState.solved && (
              <span className="flex items-center gap-1 text-[10px] font-mono font-bold text-emerald-400 bg-emerald-500/20 px-2 py-0.5 rounded-full border border-emerald-500/30">
                <CheckCircle2 size={12} />
                SOLVED!
              </span>
            )}
          </div>

          <p className="text-xs text-slate-300 font-sans leading-relaxed">
            {drillState.description || 'Find the refutation to punish the position!'}
          </p>

          {/* Hint Readout */}
          {drillState.hint_text && (
            <div className="p-3 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-200 text-xs flex items-start gap-2 animate-fadeIn">
              <Lightbulb size={16} className="text-amber-400 shrink-0 mt-0.5" />
              <span>{drillState.hint_text}</span>
            </div>
          )}

          {/* Result Feedback Banner */}
          {attemptResult && (
            <div
              className={`p-3 rounded-xl border text-xs flex items-start gap-2 ${
                attemptResult.correct
                  ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-200 shadow-emerald-glow'
                  : 'bg-rose-500/20 border-rose-500/40 text-rose-200 shadow-rose-glow'
              }`}
            >
              {attemptResult.correct ? (
                <CheckCircle2 size={16} className="text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <AlertTriangle size={16} className="text-rose-400 shrink-0 mt-0.5" />
              )}
              <div className="flex flex-col">
                <span className="font-bold">{attemptResult.correct ? 'Brilliant! Correct Move!' : 'Incorrect Move'}</span>
                <span className="opacity-90">{attemptResult.message}</span>
              </div>
            </div>
          )}

          {/* Move Input & Interactive Actions */}
          {!drillState.solved ? (
            <form onSubmit={handleSubmit} className="flex gap-2 pt-1">
              <input
                type="text"
                value={guessInput}
                onChange={(e) => setGuessInput(e.target.value)}
                placeholder="Enter move (UCI or SAN, e.g. e2e4 or Nf3)"
                className="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-amber-400"
              />
              <button
                type="submit"
                disabled={loading || !guessInput.trim()}
                className="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-display font-bold text-xs shadow flex items-center gap-1 transition-all disabled:opacity-50"
              >
                <span>Submit</span>
                <ArrowRight size={14} />
              </button>
            </form>
          ) : (
            <button
              onClick={onApplyOpponentMove}
              className="w-full py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-display font-bold text-xs shadow-md flex items-center justify-center gap-1.5 transition-all"
            >
              <Play size={14} />
              <span>Continue Opponent Line</span>
            </button>
          )}

          {/* Solution & Hint Controls */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-800">
            <button
              onClick={onToggleHint}
              className="text-xs text-amber-400 hover:text-amber-300 font-mono font-bold flex items-center gap-1"
            >
              <Lightbulb size={13} />
              <span>{drillState.hint_text ? 'More Hints' : 'Get Hint'}</span>
            </button>

            <button
              onClick={() => setShowSolution(!showSolution)}
              className="text-xs text-slate-400 hover:text-white font-mono flex items-center gap-1"
            >
              <Eye size={13} />
              <span>{showSolution ? 'Hide Solution' : 'Reveal Solution'}</span>
            </button>
          </div>

          {showSolution && drillState.best_san && (
            <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-cyan-300">
              Optimal Refutation: <strong className="text-white">{drillState.best_san}</strong> ({drillState.best_move})
            </div>
          )}
        </div>
      ) : (
        <div className="p-6 rounded-2xl bg-slate-900/40 border border-slate-800/80 flex flex-col items-center gap-3 text-center">
          <p className="text-xs text-slate-400 font-sans max-w-sm">
            Load an automated blunder drill extracted from your recent games or click 'New Blunder Drill' to practice tactical refutations.
          </p>
        </div>
      )}
    </div>
  );
};
