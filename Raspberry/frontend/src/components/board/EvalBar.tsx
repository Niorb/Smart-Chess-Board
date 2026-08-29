import React from 'react';

interface EvalBarProps {
  winChance?: number | null;
  scoreCp?: number | null;
  mate?: number | null;
  flipped?: boolean;
  className?: string;
  isComputing?: boolean;
}

export const EvalBar: React.FC<EvalBarProps> = ({
  winChance = 50,
  scoreCp,
  mate,
  flipped = false,
  className = '',
  isComputing = false,
}) => {
  const wc = Math.max(3, Math.min(97, winChance ?? 50));

  let evalLabel = '0.0';
  if (mate !== null && mate !== undefined) {
    evalLabel = `M${Math.abs(mate)}`;
  } else if (scoreCp !== null && scoreCp !== undefined) {
    evalLabel = `${scoreCp >= 0 ? '+' : ''}${(scoreCp / 100).toFixed(1)}`;
  }

  return (
    <div
      className={`relative w-5 md:w-6 self-stretch rounded-full overflow-hidden bg-slate-900 border border-slate-700/80 shadow-inner flex flex-col items-center justify-between py-1.5 shrink-0 transition-all duration-300 ${
        isComputing ? 'ring-1 ring-violet-500/50 shadow-[0_0_12px_rgba(139,92,246,0.3)]' : ''
      } ${className}`}
      title={`Live Win Chance: ${wc.toFixed(1)}% | Eval: ${evalLabel}${isComputing ? ' (Stockfish computing...)' : ''}`}
    >
      {/* Fluid White Evaluation Height Fill */}
      <div
        className={`absolute inset-x-0 bg-gradient-to-t from-slate-200 to-white transition-all duration-500 ease-out shadow-[0_0_12px_rgba(255,255,255,0.4)] ${
          flipped ? 'top-0' : 'bottom-0'
        }`}
        style={{ height: `${wc}%` }}
      />

      {/* Center 50% Win-Line Marker with Energy Sweep when Computing */}
      <div
        className={`absolute inset-x-0 h-0.5 z-[2] transition-all duration-300 ${
          isComputing
            ? 'bg-gradient-to-r from-amber-400 via-violet-300 to-cyan-400 shadow-[0_0_8px_#a855f7] animate-pulse'
            : 'bg-amber-400/80'
        }`}
        style={flipped ? { top: `${wc}%` } : { bottom: `${wc}%` }}
      />

      {/* Energy Sweep Gradient Overlay when Computing */}
      {isComputing && (
        <div
          className="absolute inset-0 pointer-events-none z-[3] opacity-40 bg-gradient-to-b from-transparent via-violet-400/30 to-transparent animate-pulse"
          style={{ animationDuration: '1.2s' }}
        />
      )}

      {/* Floating Eval Metric Text */}
      <div
        className="absolute inset-x-0 text-center text-[9px] font-mono font-extrabold z-[4] pointer-events-none select-none"
        style={{
          ...(flipped ? { top: `calc(${wc}% + 3px)` } : { bottom: `calc(${wc}% + 3px)` }),
          color: wc > 48 ? '#0f172a' : '#f8fafc',
          transform: wc > 90 || wc < 10 ? (flipped ? 'translateY(16px)' : 'translateY(-16px)') : 'none',
        }}
      >
        {evalLabel}
      </div>
    </div>
  );
};
