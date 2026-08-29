import React from 'react';
import { PlayCircle, Crown } from 'lucide-react';
import type { GMGameSummary } from '../../hooks/useBoardState';

interface GMGameSelectorProps {
  gmGamesList: GMGameSummary[];
  selectedGMId: string;
  onSelectGMId: (id: string) => void;
  onStartGMGame: (id: string) => void;
  loading: boolean;
}

export const GMGameSelector: React.FC<GMGameSelectorProps> = ({
  gmGamesList,
  selectedGMId,
  onSelectGMId,
  onStartGMGame,
  loading,
}) => {
  return (
    <div className="glass-panel rounded-3xl p-5 flex flex-col gap-4 text-left shadow-artisan">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-xl bg-amber-500/20 text-amber-300 border border-amber-500/40">
            <Crown size={18} />
          </div>
          <div>
            <h3 className="text-sm font-bold font-display text-white">Historical Grandmaster Library</h3>
            <p className="text-[11px] text-slate-400 font-sans">Step through immortal games with physical LED lighting</p>
          </div>
        </div>
        <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-slate-900 text-slate-400 border border-slate-800">
          {gmGamesList.length} Classics
        </span>
      </div>

      {/* GM Games Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 max-h-[380px] overflow-y-auto pr-1">
        {gmGamesList.map((g) => {
          const isSelected = selectedGMId === g.id;
          return (
            <div
              key={g.id}
              onClick={() => onSelectGMId(g.id)}
              className={`p-3 rounded-2xl border transition-all cursor-pointer flex flex-col justify-between gap-2 ${
                isSelected
                  ? 'bg-gradient-to-r from-amber-500/20 to-amber-600/10 border-amber-500/50 shadow-amber-glow'
                  : 'bg-slate-900/60 hover:bg-slate-800/80 border-slate-800'
              }`}
            >
              <div className="flex flex-col text-left">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold font-display text-white">{g.title}</span>
                  <span className="text-[10px] font-mono text-amber-400 font-bold">{g.year}</span>
                </div>
                <span className="text-[11px] text-slate-300 font-sans mt-0.5">
                  {g.white} vs. {g.black}
                </span>
                <span className="text-[10px] text-slate-400 font-mono mt-0.5">
                  Result: <strong className="text-white">{g.result}</strong> • {g.moves_count || 0} moves
                </span>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-slate-800/60">
                <span className="text-[9px] font-mono text-slate-400 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                  {g.eco || 'Classic'}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onStartGMGame(g.id);
                  }}
                  disabled={loading}
                  className="px-2.5 py-1 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-display font-bold text-[10px] shadow flex items-center gap-1 transition-all active:scale-95"
                >
                  <PlayCircle size={12} />
                  <span>Replay on Board</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
