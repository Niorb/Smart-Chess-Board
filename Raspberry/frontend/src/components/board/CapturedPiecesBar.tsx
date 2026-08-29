import React, { useMemo } from 'react';
import { PIECE_IMAGES } from './boardUtils';

interface CapturedPiecesBarProps {
  fen: string;
  myColor?: 'white' | 'black' | null;
  flipped?: boolean;
}

const PIECE_VALUES: Record<string, number> = {
  p: 1, n: 3, b: 3, r: 5, q: 9, k: 0,
};

export const CapturedPiecesBar: React.FC<CapturedPiecesBarProps> = ({ fen }) => {
  const { whiteLost, blackLost, advantage } = useMemo(() => {
    const fullSet: Record<string, number> = {
      P: 8, N: 2, B: 2, R: 2, Q: 1, K: 1,
      p: 8, n: 2, b: 2, r: 2, q: 1, k: 1,
    };
    const placement = fen.split(' ')[0] || '';
    for (const ch of placement) {
      if (fullSet[ch] !== undefined) {
        fullSet[ch]--;
      }
    }
    const wLost: string[] = [];
    const bLost: string[] = [];
    let wVal = 0;
    let bVal = 0;

    for (const [p, count] of Object.entries(fullSet)) {
      if (count > 0) {
        const isWhite = p === p.toUpperCase();
        for (let i = 0; i < count; i++) {
          if (isWhite) {
            wLost.push(p);
            bVal += PIECE_VALUES[p.toLowerCase()] || 0;
          } else {
            bLost.push(p);
            wVal += PIECE_VALUES[p.toLowerCase()] || 0;
          }
        }
      }
    }

    wLost.sort((a, b) => (PIECE_VALUES[b.toLowerCase()] || 0) - (PIECE_VALUES[a.toLowerCase()] || 0));
    bLost.sort((a, b) => (PIECE_VALUES[b.toLowerCase()] || 0) - (PIECE_VALUES[a.toLowerCase()] || 0));

    return {
      whiteLost: wLost,
      blackLost: bLost,
      advantage: wVal - bVal,
    };
  }, [fen]);

  return (
    <div className="flex items-center justify-between text-xs px-2.5 py-1 bg-slate-900/60 rounded-xl border border-slate-800/80">
      {/* White Captures (Black pieces taken by white) */}
      <div className="flex items-center gap-1.5 min-h-[22px]">
        <div className="flex items-center -space-x-1.5 overflow-hidden">
          {blackLost.map((p, i) => (
            <img
              key={`w-cap-${p}-${i}`}
              src={PIECE_IMAGES[p]}
              alt={p}
              className="w-4 h-4 object-contain filter drop-shadow"
            />
          ))}
        </div>
        {advantage > 0 && (
          <span className="text-[10px] font-mono font-bold text-amber-400 bg-amber-400/15 px-1.5 py-0.5 rounded">
            +{advantage}
          </span>
        )}
      </div>

      {/* Black Captures (White pieces taken by black) */}
      <div className="flex items-center gap-1.5 min-h-[22px]">
        {advantage < 0 && (
          <span className="text-[10px] font-mono font-bold text-slate-300 bg-slate-700/50 px-1.5 py-0.5 rounded">
            +{Math.abs(advantage)}
          </span>
        )}
        <div className="flex items-center -space-x-1.5 overflow-hidden">
          {whiteLost.map((p, i) => (
            <img
              key={`b-cap-${p}-${i}`}
              src={PIECE_IMAGES[p]}
              alt={p}
              className="w-4 h-4 object-contain filter drop-shadow"
            />
          ))}
        </div>
      </div>
    </div>
  );
};
