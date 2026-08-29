import React, { useMemo } from 'react';

interface LedBezelTwinProps {
  lastMoveUci?: string | null;
  inCheck?: boolean;
  activeAnimation?: string | null;
  ledIntensity?: number;
  flipped?: boolean;
}

export const LedBezelTwin: React.FC<LedBezelTwinProps> = ({
  lastMoveUci,
  inCheck,
  activeAnimation,
  ledIntensity = 100,
  flipped = false,
}) => {
  const intensity = Math.max(0.1, Math.min(1, ledIntensity / 100));

  const activeSegments = useMemo(() => {
    if (!lastMoveUci || lastMoveUci.length < 4) return { files: new Set<number>(), ranks: new Set<number>() };
    const f1 = lastMoveUci.charCodeAt(0) - 97;
    const r1 = parseInt(lastMoveUci[1], 10) - 1;
    const f2 = lastMoveUci.charCodeAt(2) - 97;
    const r2 = parseInt(lastMoveUci[3], 10) - 1;

    return {
      files: new Set([f1, f2]),
      ranks: new Set([r1, r2]),
    };
  }, [lastMoveUci]);

  return (
    <div
      className="absolute -inset-2.5 pointer-events-none rounded-xl z-[4] transition-all duration-300"
      style={{
        boxShadow: inCheck
          ? `0 0 25px 6px rgba(244, 63, 94, ${intensity * 0.85}), inset 0 0 15px 3px rgba(244, 63, 94, ${intensity * 0.6})`
          : activeAnimation
          ? `0 0 30px 8px rgba(139, 92, 246, ${intensity * 0.8}), inset 0 0 20px 4px rgba(6, 182, 212, ${intensity * 0.5})`
          : `0 0 20px 4px rgba(245, 158, 11, ${intensity * 0.35})`,
      }}
    >
      {/* 8 Top & Bottom Bezel Micro-LEDs */}
      <div className="absolute top-0 inset-x-3 flex justify-between">
        {Array.from({ length: 8 }).map((_, i) => {
          const file = flipped ? 7 - i : i;
          const isActive = activeSegments.files.has(file);
          return (
            <div
              key={`top-led-${i}`}
              className={`w-1.5 h-1.5 rounded-full transition-all duration-200 ${
                inCheck
                  ? 'bg-rose-500 shadow-[0_0_8px_#f43f5e] animate-pulse'
                  : isActive
                  ? 'bg-amber-400 shadow-[0_0_10px_#fbbf24] scale-125'
                  : 'bg-slate-700/60'
              }`}
              style={{ opacity: intensity }}
            />
          );
        })}
      </div>

      <div className="absolute bottom-0 inset-x-3 flex justify-between">
        {Array.from({ length: 8 }).map((_, i) => {
          const file = flipped ? 7 - i : i;
          const isActive = activeSegments.files.has(file);
          return (
            <div
              key={`bot-led-${i}`}
              className={`w-1.5 h-1.5 rounded-full transition-all duration-200 ${
                inCheck
                  ? 'bg-rose-500 shadow-[0_0_8px_#f43f5e] animate-pulse'
                  : isActive
                  ? 'bg-amber-400 shadow-[0_0_10px_#fbbf24] scale-125'
                  : 'bg-slate-700/60'
              }`}
              style={{ opacity: intensity }}
            />
          );
        })}
      </div>

      {/* 8 Left & Right Bezel Micro-LEDs */}
      <div className="absolute inset-y-3 left-0 flex flex-col justify-between">
        {Array.from({ length: 8 }).map((_, i) => {
          const rank = flipped ? i : 7 - i;
          const isActive = activeSegments.ranks.has(rank);
          return (
            <div
              key={`left-led-${i}`}
              className={`w-1.5 h-1.5 rounded-full transition-all duration-200 ${
                inCheck
                  ? 'bg-rose-500 shadow-[0_0_8px_#f43f5e] animate-pulse'
                  : isActive
                  ? 'bg-amber-400 shadow-[0_0_10px_#fbbf24] scale-125'
                  : 'bg-slate-700/60'
              }`}
              style={{ opacity: intensity }}
            />
          );
        })}
      </div>

      <div className="absolute inset-y-3 right-0 flex flex-col justify-between">
        {Array.from({ length: 8 }).map((_, i) => {
          const rank = flipped ? i : 7 - i;
          const isActive = activeSegments.ranks.has(rank);
          return (
            <div
              key={`right-led-${i}`}
              className={`w-1.5 h-1.5 rounded-full transition-all duration-200 ${
                inCheck
                  ? 'bg-rose-500 shadow-[0_0_8px_#f43f5e] animate-pulse'
                  : isActive
                  ? 'bg-amber-400 shadow-[0_0_10px_#fbbf24] scale-125'
                  : 'bg-slate-700/60'
              }`}
              style={{ opacity: intensity }}
            />
          );
        })}
      </div>
    </div>
  );
};
