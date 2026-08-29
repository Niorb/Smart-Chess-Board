import React from 'react';
import { Clock } from 'lucide-react';

interface ClockWidgetProps {
  timeStr: string;
  playerLabel: string;
  rating?: number | string;
  title?: string;
  isTurn: boolean;
  color: 'white' | 'black';
}

export const ClockWidget: React.FC<ClockWidgetProps> = ({
  timeStr,
  playerLabel,
  rating,
  title,
  isTurn,
  color,
}) => {
  return (
    <div
      className={`flex items-center justify-between p-3 rounded-2xl border transition-all duration-300 ${
        isTurn
          ? color === 'white'
            ? 'bg-amber-500/15 border-amber-500/60 shadow-amber-glow'
            : 'bg-cyan-500/15 border-cyan-500/60 shadow-cyan-glow'
          : 'bg-slate-900/70 border-slate-800/80 text-slate-400'
      }`}
    >
      {/* Player Identity */}
      <div className="flex items-center gap-2.5">
        <div
          className={`w-4 h-4 rounded-full border shadow-sm ${
            color === 'white' ? 'bg-slate-100 border-slate-300' : 'bg-slate-950 border-slate-700'
          }`}
        />
        <div className="flex flex-col text-left">
          <span className="text-xs font-bold text-white font-display flex items-center gap-1.5">
            {playerLabel}
            {title && (
              <span className="text-[9px] bg-amber-500/20 text-amber-300 px-1 py-0.2 rounded font-mono font-bold">
                {title}
              </span>
            )}
          </span>
          {rating && (
            <span className="text-[10px] text-slate-400 font-mono">
              Rating: {rating}
            </span>
          )}
        </div>
      </div>

      {/* Clock Readout */}
      <div className="flex items-center gap-2">
        <div
          className={`px-3 py-1 rounded-xl border font-mono font-extrabold text-base md:text-lg tracking-tight transition-all ${
            isTurn
              ? color === 'white'
                ? 'bg-amber-500/25 border-amber-400 text-amber-200 animate-pulse shadow-sm'
                : 'bg-cyan-500/25 border-cyan-400 text-cyan-200 animate-pulse shadow-sm'
              : 'bg-slate-950/80 border-slate-800 text-slate-300'
          }`}
        >
          {timeStr}
        </div>
      </div>
    </div>
  );
};
