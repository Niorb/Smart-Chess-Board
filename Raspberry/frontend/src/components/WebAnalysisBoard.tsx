import React, { useMemo } from 'react';

interface WebAnalysisBoardProps {
  fen: string;
  /** UCI of the most recent move to highlight (mainline or branch), e.g. "g1f3". */
  lastMoveUci?: string | null;
  /** True while the position is off the main game line (variation sandbox). */
  isBranching?: boolean;
}

const PIECE_GLYPHS: Record<string, string> = {
  K: '\u2654', Q: '\u2655', R: '\u2656', B: '\u2657', N: '\u2658', P: '\u2659',
  k: '\u265A', q: '\u265B', r: '\u265C', b: '\u265D', n: '\u265E', p: '\u265F',
};

function parseFenPlacement(fen: string): string[][] {
  const rows = (fen.split(' ')[0] || '').split('/');
  const grid: string[][] = [];
  for (const row of rows) {
    const cells: string[] = [];
    for (const ch of row) {
      if (/\d/.test(ch)) {
        for (let i = 0; i < parseInt(ch, 10); i++) cells.push('');
      } else {
        cells.push(ch);
      }
    }
    grid.push(cells.slice(0, 8));
  }
  return grid.slice(0, 8);
}

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];

/**
 * Interactive read-only web board for keyboard-driven analysis.
 * Purely virtual: renders the analysis engine position and highlights the
 * latest move; all interaction happens through the keyboard / candidate chips.
 */
const WebAnalysisBoard: React.FC<WebAnalysisBoardProps> = ({ fen, lastMoveUci, isBranching }) => {
  const grid = useMemo(() => parseFenPlacement(fen), [fen]);

  const highlight = useMemo(() => {
    if (!lastMoveUci || lastMoveUci.length < 4) return null;
    const f = FILES.indexOf(lastMoveUci[0]);
    const r = parseInt(lastMoveUci[1], 10) - 1;
    const t_f = FILES.indexOf(lastMoveUci[2]);
    const t_r = parseInt(lastMoveUci[3], 10) - 1;
    if ([f, r, t_f, t_r].some((v) => v < 0 || v > 7)) return null;
    return { from: [f, r] as [number, number], to: [t_f, t_r] as [number, number] };
  }, [lastMoveUci]);

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-xl">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-white">Analysis Board</h3>
        <span
          className={`px-2 py-0.5 text-[10px] font-bold rounded-full border ${
            isBranching
              ? 'bg-violet-500/20 text-violet-300 border-violet-500/40'
              : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
          }`}
        >
          {isBranching ? 'VARIATION SANDBOX' : 'MAIN GAME LINE'}
        </span>
      </div>

      <div className="mx-auto" style={{ maxWidth: '480px' }}>
        {/* Rank labels row wrapper */}
        <div className="relative">
          <div className="grid grid-cols-8 aspect-square w-full rounded-lg overflow-hidden ring-1 ring-slate-700">
            {Array.from({ length: 64 }).map((_, idx) => {
              // Render from rank 8 (top) to rank 1, file a..h left->right
              const rowFromTop = Math.floor(idx / 8); // 0..7
              const file = idx % 8;
              const rank = 7 - rowFromTop; // 7 = rank 8
              const piece = grid[rank]?.[file] ?? '';
              const isDark = (file + rank) % 2 === 1;
              const isFrom = highlight && highlight.from[0] === file && highlight.from[1] === rank;
              const isTo = highlight && highlight.to[0] === file && highlight.to[1] === rank;

              let bg = isDark ? 'bg-slate-700/70' : 'bg-slate-500/50';
              if (isTo) bg = 'bg-emerald-600/70';
              else if (isFrom) bg = isBranching ? 'bg-violet-600/70' : 'bg-sky-600/60';

              return (
                <div key={idx} className={`relative flex items-center justify-center ${bg}`}>
                  {/* Coordinate labels on edge squares */}
                  {file === 0 && (
                    <span className="absolute top-0.5 left-1 text-[9px] font-bold text-white/40">
                      {rank + 1}
                    </span>
                  )}
                  {rank === 0 && (
                    <span className="absolute bottom-0.5 right-1 text-[9px] font-bold text-white/40">
                      {FILES[file]}
                    </span>
                  )}
                  {piece && (
                    <span
                      className={`leading-none select-none ${
                        piece === piece.toUpperCase() ? 'text-white' : 'text-slate-950'
                      }`}
                      style={{ fontSize: 'clamp(20px, 5.2vw, 42px)', textShadow: '0 1px 3px rgba(0,0,0,0.55)' }}
                    >
                      {PIECE_GLYPHS[piece]}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="mt-3 text-center text-[10px] text-slate-500 leading-relaxed">
        <span className="font-mono text-slate-400">&larr; &rarr;</span> /{' '}
        <span className="font-mono text-slate-400">h l</span> step ·{' '}
        <span className="font-mono text-slate-400">Home End</span> /{' '}
        <span className="font-mono text-slate-400">g G</span> jump · click a Top Candidate
        or type a move to explore a variation
      </div>
    </div>
  );
};

export default WebAnalysisBoard;
