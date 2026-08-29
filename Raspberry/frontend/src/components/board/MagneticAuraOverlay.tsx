import React, { useMemo } from 'react';

interface MagneticAuraOverlayProps {
  adcGrid?: number[][];
  baselines?: number[][];
  liftedSquare?: [number, number] | null;
  resignationArmed?: boolean;
  kingLiftElapsed?: number | null;
  flipped?: boolean;
  threshold?: number;
}

export const MagneticAuraOverlay: React.FC<MagneticAuraOverlayProps> = ({
  adcGrid,
  baselines,
  liftedSquare,
  resignationArmed,
  kingLiftElapsed,
  flipped = false,
  threshold = 200,
}) => {
  // Compute delta flux intensity (0..1) for each square
  const fluxMap = useMemo(() => {
    const map = Array(8).fill(0).map(() => Array(8).fill(0));
    if (!adcGrid || adcGrid.length < 8) return map;
    for (let r = 0; r < 8; r++) {
      for (let c = 0; c < 8; c++) {
        const raw = adcGrid[r]?.[c] ?? 0;
        const base = baselines?.[r]?.[c] ?? 0;
        const delta = Math.abs(raw - base);
        if (delta > 20) {
          map[r][c] = Math.min(1, delta / (threshold * 2.5));
        }
      }
    }
    return map;
  }, [adcGrid, baselines, threshold]);

  return (
    <div className="absolute inset-0 pointer-events-none z-[8] overflow-hidden rounded-md">
      {/* 8x8 Flux Aura Contours */}
      <svg className="w-full h-full" viewBox="0 0 800 800">
        <defs>
          <radialGradient id="flux-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(245, 158, 11, 0.45)" />
            <stop offset="60%" stopColor="rgba(245, 158, 11, 0.15)" />
            <stop offset="100%" stopColor="rgba(245, 158, 11, 0)" />
          </radialGradient>
          <radialGradient id="lift-pulse" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(6, 182, 212, 0.7)" />
            <stop offset="50%" stopColor="rgba(6, 182, 212, 0.25)" />
            <stop offset="100%" stopColor="rgba(6, 182, 212, 0)" />
          </radialGradient>
          <radialGradient id="resign-pulse" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(244, 63, 94, 0.8)" />
            <stop offset="60%" stopColor="rgba(244, 63, 94, 0.3)" />
            <stop offset="100%" stopColor="rgba(244, 63, 94, 0)" />
          </radialGradient>
        </defs>

        {fluxMap.map((row, r) =>
          row.map((intensity, c) => {
            if (intensity <= 0.05) return null;
            const screenCol = flipped ? 7 - c : c;
            const screenRow = flipped ? r : 7 - r;
            const cx = screenCol * 100 + 50;
            const cy = screenRow * 100 + 50;
            const radius = 35 + intensity * 35;

            return (
              <g key={`flux-${r}-${c}`}>
                <circle
                  cx={cx}
                  cy={cy}
                  r={radius}
                  fill="url(#flux-glow)"
                  opacity={intensity * 0.85}
                />
                <circle
                  cx={cx}
                  cy={cy}
                  r={radius * 0.7}
                  fill="none"
                  stroke="rgba(245, 158, 11, 0.35)"
                  strokeWidth="1.5"
                  strokeDasharray="4,3"
                />
              </g>
            );
          })
        )}

        {/* Lifted Piece Wave / Magnetic Release Ripple */}
        {liftedSquare && (
          (() => {
            const [c, r] = liftedSquare;
            const screenCol = flipped ? 7 - c : c;
            const screenRow = flipped ? r : 7 - r;
            const cx = screenCol * 100 + 50;
            const cy = screenRow * 100 + 50;
            const isResigning = !!resignationArmed;

            return (
              <g key="lift-ripple">
                <circle
                  cx={cx}
                  cy={cy}
                  r="45"
                  fill={isResigning ? "url(#resign-pulse)" : "url(#lift-pulse)"}
                  className="animate-ping origin-center"
                  style={{ animationDuration: '1.8s' }}
                />
                <circle
                  cx={cx}
                  cy={cy}
                  r="38"
                  fill="none"
                  stroke={isResigning ? "#f43f5e" : "#06b6d4"}
                  strokeWidth="2.5"
                  className="animate-pulse"
                />
                {kingLiftElapsed !== null && kingLiftElapsed !== undefined && kingLiftElapsed > 0 && (
                  <text
                    x={cx}
                    y={cy + 4}
                    textAnchor="middle"
                    fill="#fff"
                    fontSize="22"
                    fontWeight="bold"
                    fontFamily="JetBrains Mono"
                  >
                    {kingLiftElapsed.toFixed(1)}s
                  </text>
                )}
              </g>
            );
          })()
        )}
      </svg>
    </div>
  );
};
