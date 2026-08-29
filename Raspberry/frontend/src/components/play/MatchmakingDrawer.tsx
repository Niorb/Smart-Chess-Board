import React from 'react';
import { 
  Play, 
  RefreshCw, 
  RotateCcw, 
  Bot, 
  Zap, 
  Sliders, 
  ShieldCheck, 
  Sparkles,
  Users
} from 'lucide-react';
import type { LastGameParams } from '../../api';

interface MatchmakingDrawerProps {
  selectedTC: string;
  setSelectedTC: (tc: string) => void;
  isRated: boolean;
  setIsRated: (rated: boolean) => void;
  selectedColor: 'random' | 'white' | 'black';
  setSelectedColor: (c: 'random' | 'white' | 'black') => void;
  opponentMode: 'auto' | 'ai' | 'human';
  setOpponentMode: (m: 'auto' | 'ai' | 'human') => void;
  aiLevel: number;
  setAiLevel: (l: number) => void;
  ratingBoundary: 'any' | '100' | '200' | '300' | '500' | 'custom';
  setRatingBoundary: (b: 'any' | '100' | '200' | '300' | '500' | 'custom') => void;
  customMinRating: string;
  setCustomMinRating: (v: string) => void;
  customMaxRating: string;
  setCustomMaxRating: (v: string) => void;
  lastGameParams: LastGameParams | null;
  loading: boolean;
  isConnected: boolean;
  onSeek: () => void;
  onRestartPrevious: () => void;
}

const TIME_CONTROLS = [
  { id: '1+0', label: '1+0', sub: 'Bullet' },
  { id: '3+0', label: '3+0', sub: 'Blitz' },
  { id: '3+2', label: '3+2', sub: 'Blitz' },
  { id: '5+0', label: '5+0', sub: 'Blitz' },
  { id: '5+3', label: '5+3', sub: 'Blitz' },
  { id: '10+0', label: '10+0', sub: 'Rapid' },
  { id: '15+10', label: '15+10', sub: 'Rapid' },
  { id: '30+0', label: '30+0', sub: 'Classical' },
];

export const MatchmakingDrawer: React.FC<MatchmakingDrawerProps> = ({
  selectedTC,
  setSelectedTC,
  isRated,
  setIsRated,
  selectedColor,
  setSelectedColor,
  opponentMode,
  setOpponentMode,
  aiLevel,
  setAiLevel,
  ratingBoundary,
  setRatingBoundary,
  customMinRating,
  setCustomMinRating,
  customMaxRating,
  setCustomMaxRating,
  lastGameParams,
  loading,
  isConnected,
  onSeek,
  onRestartPrevious,
}) => {
  return (
    <div className="glass-panel rounded-3xl p-4 md:p-5 flex flex-col gap-4 text-left shadow-artisan">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 font-mono flex items-center gap-2">
          <Zap size={14} className="text-amber-400" />
          Matchmaking & Challenge
        </h3>
        {lastGameParams && (
          <button
            onClick={onRestartPrevious}
            disabled={loading || !isConnected}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/40 text-amber-300 text-[10px] font-mono font-bold transition-all"
          >
            <RotateCcw size={12} />
            <span>Rematch Last ({lastGameParams.timeControl})</span>
          </button>
        )}
      </div>

      {/* Time Control Cards Grid */}
      <div className="flex flex-col gap-1.5">
        <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 font-mono">
          Time Control
        </label>
        <div className="grid grid-cols-4 gap-1.5">
          {TIME_CONTROLS.map((tc) => {
            const isSelected = selectedTC === tc.id;
            return (
              <button
                key={tc.id}
                disabled={loading || !isConnected}
                onClick={() => setSelectedTC(tc.id)}
                className={`p-2 rounded-2xl border transition-all flex flex-col items-center justify-center ${
                  isSelected
                    ? 'bg-gradient-to-tr from-amber-600 to-amber-500 border-amber-400 text-slate-950 shadow-amber-glow font-bold'
                    : 'bg-slate-900/80 hover:bg-slate-800/90 border-slate-800 text-slate-300'
                }`}
              >
                <span className="text-xs font-bold font-mono">{tc.label}</span>
                <span className="text-[8px] uppercase tracking-wider opacity-80">{tc.sub}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Opponent Mode & AI Difficulty */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
        {/* Opponent Target */}
        <div className="flex flex-col gap-1.5">
          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 font-mono flex items-center gap-1">
            <Users size={12} className="text-cyan-400" />
            Opponent
          </label>
          <div className="grid grid-cols-3 gap-1">
            {[
              { id: 'auto', label: 'Smart Auto' },
              { id: 'ai', label: 'Stockfish' },
              { id: 'human', label: 'Lichess' },
            ].map((m) => (
              <button
                key={m.id}
                onClick={() => setOpponentMode(m.id as 'auto' | 'ai' | 'human')}
                className={`py-1.5 text-[11px] font-bold rounded-xl border transition-all font-display ${
                  opponentMode === m.id
                    ? 'bg-cyan-500/20 border-cyan-400 text-cyan-200 shadow-cyan-glow'
                    : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {/* AI Skill Level */}
        <div className="flex flex-col gap-1.5">
          <div className="flex justify-between items-center text-[10px] font-bold uppercase tracking-wider text-slate-400 font-mono">
            <span className="flex items-center gap-1">
              <Bot size={12} className="text-violet-400" />
              Stockfish Level
            </span>
            <span className="text-violet-300 font-mono font-bold">Lvl {aiLevel}</span>
          </div>
          <div className="grid grid-cols-4 gap-1">
            {[1, 3, 5, 8].map((lvl) => (
              <button
                key={lvl}
                onClick={() => setAiLevel(lvl)}
                className={`py-1.5 text-[10px] font-mono font-bold rounded-xl border transition-all ${
                  aiLevel === lvl
                    ? 'bg-violet-500/25 border-violet-400 text-violet-200 shadow-sm'
                    : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                {lvl === 1 ? '1 · 800' : lvl === 3 ? '3 · 1400' : lvl === 5 ? '5 · 1900' : '8 · GM'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Side / Piece Color & Rating Boundary */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
        {/* Color Choice */}
        <div className="flex flex-col gap-1.5">
          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 font-mono">
            Play As
          </label>
          <div className="grid grid-cols-3 gap-1">
            {[
              { id: 'random', label: 'Random' },
              { id: 'white', label: 'White' },
              { id: 'black', label: 'Black' },
            ].map((c) => (
              <button
                key={c.id}
                onClick={() => setSelectedColor(c.id as 'random' | 'white' | 'black')}
                className={`py-1.5 text-[11px] font-bold rounded-xl border transition-all font-display ${
                  selectedColor === c.id
                    ? 'bg-amber-500/25 border-amber-400 text-amber-200'
                    : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        {/* Rated vs Casual Toggle */}
        <div className="flex flex-col gap-1.5">
          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 font-mono">
            Game Mode
          </label>
          <div className="grid grid-cols-2 gap-1">
            <button
              onClick={() => setIsRated(true)}
              className={`py-1.5 text-[11px] font-bold rounded-xl border transition-all font-display ${
                isRated
                  ? 'bg-emerald-500/20 border-emerald-400 text-emerald-200 shadow-sm'
                  : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              Rated
            </button>
            <button
              onClick={() => setIsRated(false)}
              className={`py-1.5 text-[11px] font-bold rounded-xl border transition-all font-display ${
                !isRated
                  ? 'bg-slate-800 border-slate-600 text-white shadow-sm'
                  : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              Casual
            </button>
          </div>
        </div>
      </div>

      {/* Opponent Rating Range Selector (When Human Matchmaking) */}
      {opponentMode !== 'ai' && (
        <div className="flex flex-col gap-1.5 pt-1">
          <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 font-mono">
            Rating Bracket Filter
          </label>
          <div className="grid grid-cols-5 gap-1">
            {[
              { id: 'any', label: 'Any' },
              { id: '100', label: '±100' },
              { id: '200', label: '±200' },
              { id: '300', label: '±300' },
              { id: 'custom', label: 'Custom' },
            ].map((rb) => (
              <button
                key={rb.id}
                onClick={() => setRatingBoundary(rb.id as 'any' | '100' | '200' | '300' | '500' | 'custom')}
                className={`py-1 text-[10px] font-mono font-bold rounded-xl border transition-all ${
                  ratingBoundary === rb.id
                    ? 'bg-cyan-500/20 border-cyan-400 text-cyan-200'
                    : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                {rb.label}
              </button>
            ))}
          </div>

          {ratingBoundary === 'custom' && (
            <div className="flex items-center gap-2 mt-1">
              <input
                type="number"
                value={customMinRating}
                onChange={(e) => setCustomMinRating(e.target.value)}
                placeholder="Min"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-2 py-1 text-xs font-mono text-white text-center"
              />
              <span className="text-slate-500 font-mono text-xs">to</span>
              <input
                type="number"
                value={customMaxRating}
                onChange={(e) => setCustomMaxRating(e.target.value)}
                placeholder="Max"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-2 py-1 text-xs font-mono text-white text-center"
              />
            </div>
          )}
        </div>
      )}

      {/* Start Seek CTA Button */}
      <button
        onClick={onSeek}
        disabled={loading || !isConnected}
        className="w-full py-3.5 px-4 rounded-2xl bg-gradient-to-r from-amber-500 via-amber-400 to-amber-500 hover:brightness-110 text-slate-950 font-extrabold font-display text-sm tracking-wide shadow-amber-glow flex items-center justify-center gap-2 transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? (
          <>
            <RefreshCw size={16} className="animate-spin" />
            <span>Connecting...</span>
          </>
        ) : (
          <>
            <Play size={16} className="fill-slate-950" />
            <span>Initiate Match ({selectedTC})</span>
          </>
        )}
      </button>
    </div>
  );
};
