import React, { useEffect, useMemo, useRef, useState } from 'react';
import wK from '../assets/pieces/wK.svg';
import wQ from '../assets/pieces/wQ.svg';
import wR from '../assets/pieces/wR.svg';
import wB from '../assets/pieces/wB.svg';
import wN from '../assets/pieces/wN.svg';
import wP from '../assets/pieces/wP.svg';
import bK from '../assets/pieces/bK.svg';
import bQ from '../assets/pieces/bQ.svg';
import bR from '../assets/pieces/bR.svg';
import bB from '../assets/pieces/bB.svg';
import bN from '../assets/pieces/bN.svg';
import bP from '../assets/pieces/bP.svg';

interface WebAnalysisBoardProps {
  fen: string;
  /** Legal moves for the current position (UCI), provided by the backend. */
  legalMoves: string[];
  /** True when the side to move is in check. */
  inCheck?: boolean;
  /** UCI of the most recent move to highlight (mainline or branch). */
  lastMoveUci?: string | null;
  /** True while the position is off the main game line (variation sandbox). */
  isBranching?: boolean;
  /** Called with the full UCI (incl. promotion suffix) when a move is played. */
  onMovePlayed: (uci: string) => void;
}

const PIECE_IMAGES: Record<string, string> = {
  K: wK, Q: wQ, R: wR, B: wB, N: wN, P: wP,
  k: bK, q: bQ, r: bR, b: bB, n: bN, p: bP,
};

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];

type Coord = [number, number]; // [file 0-7, rank 0-7]

interface Theme {
  name: string;
  label: string;
  light: string;
  dark: string;
  frame: string;
}

const THEMES: Theme[] = [
  { name: 'green', label: 'Green', light: '#EBECD0', dark: '#739552', frame: '#3d4a2e' },
  { name: 'wood', label: 'Wood', light: '#F0D9B5', dark: '#B58863', frame: '#6b4a2f' },
  { name: 'slate', label: 'Slate', light: '#4B5872', dark: '#323C52', frame: '#1e293b' },
];

const THEME_STORAGE_KEY = 'webboard-theme';

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

function coordToSquareName(c: Coord): string {
  return `${FILES[c[0]]}${c[1] + 1}`;
}

function uciToCoords(uci: string): { from: Coord; to: Coord } | null {
  if (!uci || uci.length < 4) return null;
  const f = FILES.indexOf(uci[0]);
  const r = parseInt(uci[1], 10) - 1;
  const tf = FILES.indexOf(uci[2]);
  const tr = parseInt(uci[3], 10) - 1;
  if ([f, r, tf, tr].some((v) => v < 0 || v > 7)) return null;
  return { from: [f, r], to: [tf, tr] };
}

/**
 * Interactive lichess-style analysis board: SVG pieces, themed squares,
 * drag & drop + click-to-move (pointer events, mouse and touch), legal-move
 * dots/capture rings, check glow, and a promotion picker.
 * Fully virtual: moves are dispatched through the web-only analysis endpoint.
 */
const WebAnalysisBoard: React.FC<WebAnalysisBoardProps> = ({
  fen,
  legalMoves,
  inCheck,
  lastMoveUci,
  isBranching,
  onMovePlayed,
}) => {
  const grid = useMemo(() => parseFenPlacement(fen), [fen]);
  const whiteToMove = (fen.split(' ')[1] || 'w') === 'w';

  const [themeIdx, setThemeIdx] = useState<number>(() => {
    try {
      const saved = localStorage.getItem(THEME_STORAGE_KEY);
      const idx = THEMES.findIndex((t) => t.name === saved);
      return idx >= 0 ? idx : 0;
    } catch {
      return 0;
    }
  });
  const theme = THEMES[themeIdx];

  const [selected, setSelected] = useState<Coord | null>(null);
  const [drag, setDrag] = useState<{ from: Coord; piece: string; x: number; y: number; moved: boolean } | null>(null);
  const [promotion, setPromotion] = useState<{ from: Coord; to: Coord; color: 'white' | 'black' } | null>(null);

  const boardRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, THEMES[themeIdx].name);
    } catch {
      /* ignore */
    }
  }, [themeIdx]);

  const lastHighlight = useMemo(() => (lastMoveUci ? uciToCoords(lastMoveUci) : null), [lastMoveUci]);

  // Squares the selected piece may travel to
  const targets = useMemo(() => {
    if (!selected) return new Map<string, boolean>();
    const prefix = coordToSquareName(selected);
    const map = new Map<string, boolean>();
    for (const lm of legalMoves) {
      if (lm.startsWith(prefix)) {
        map.set(lm.slice(2, 4), lm.length > 4); // capture?
      }
    }
    return map;
  }, [selected, legalMoves]);

  // King square of the side to move (for the check glow)
  const checkedKingSquare = useMemo(() => {
    if (!inCheck) return null;
    const kingGlyph = whiteToMove ? 'K' : 'k';
    for (let r = 0; r < 8; r++) {
      for (let f = 0; f < 8; f++) {
        if (grid[r]?.[f] === kingGlyph) return [f, r] as Coord;
      }
    }
    return null;
  }, [inCheck, whiteToMove, grid]);

  const pieceAt = (c: Coord): string => grid[c[1]]?.[c[0]] ?? '';

  const isOwnTurnPiece = (glyph: string): boolean =>
    !!glyph && (whiteToMove ? glyph === glyph.toUpperCase() : glyph === glyph.toLowerCase());

  const tryPlay = (from: Coord, to: Coord) => {
    const fromStr = coordToSquareName(from);
    const toStr = coordToSquareName(to);
    const candidates = legalMoves.filter((lm) => lm.startsWith(fromStr + toStr));
    if (candidates.length === 0) return false;
    if (candidates[0].length > 4) {
      // Promotion required -> open the picker
      const glyph = pieceAt(from);
      setPromotion({
        from,
        to,
        color: glyph && glyph === glyph.toUpperCase() ? 'white' : 'black',
      });
      setSelected(null);
      return true;
    }
    onMovePlayed(candidates[0]);
    setSelected(null);
    return true;
  };

  const squareFromPoint = (clientX: number, clientY: number): Coord | null => {
    const rect = boardRef.current?.getBoundingClientRect();
    if (!rect) return null;
    const sq = rect.width / 8;
    const f = Math.floor((clientX - rect.left) / sq);
    const rowFromTop = Math.floor((clientY - rect.top) / sq);
    const r = 7 - rowFromTop;
    if (f < 0 || f > 7 || r < 0 || r > 7 || rowFromTop < 0 || rowFromTop > 7) return null;
    return [f, r];
  };

  const handlePointerDown = (e: React.PointerEvent, c: Coord) => {
    if (promotion) return;

    // Complete a click-click move onto a highlighted target
    if (selected && targets.has(coordToSquareName(c))) {
      tryPlay(selected, c);
      return;
    }

    const glyph = pieceAt(c);
    if (!isOwnTurnPiece(glyph)) {
      setSelected(null);
      return;
    }

    // Select (and prepare a potential drag)
    setSelected(c);
    setDrag({ from: c, piece: glyph, x: e.clientX, y: e.clientY, moved: false });
  };

  // Global pointer tracking while a piece is held
  useEffect(() => {
    if (!drag) return;
    const onMove = (e: PointerEvent) => {
      setDrag((d) => (d ? { ...d, x: e.clientX, y: e.clientY, moved: true } : d));
    };
    const onUp = (e: PointerEvent) => {
      const target = squareFromPoint(e.clientX, e.clientY);
      const origin = drag.from;
      const wasDragged =
        Math.abs(e.clientX - drag.x) > 4 || Math.abs(e.clientY - drag.y) > 4 || drag.moved;
      setDrag(null);
      if (target && wasDragged && !(target[0] === origin[0] && target[1] === origin[1])) {
        if (!tryPlay(origin, target)) {
          setSelected(null); // illegal drop: snap back & deselect
        }
      } else if (!wasDragged && selected && target &&
        target[0] === origin[0] && target[1] === origin[1]) {
        // Simple click on the already-selected piece toggles it off
        setSelected(null);
      }
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drag, selected, legalMoves]);

  const cycleTheme = () => setThemeIdx((i) => (i + 1) % THEMES.length);

  // Board geometry for the floating drag ghost
  const boardRect = boardRef.current?.getBoundingClientRect();
  const squarePx = boardRect ? boardRect.width / 8 : 60;

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-white">Analysis Board</h3>
        <div className="flex items-center gap-2">
          <span
            className={`px-2 py-0.5 text-[10px] font-bold rounded-full border ${
              isBranching
                ? 'bg-violet-500/20 text-violet-300 border-violet-500/40'
                : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
            }`}
          >
            {isBranching ? 'VARIATION SANDBOX' : 'MAIN GAME LINE'}
          </span>
          <button
            onClick={cycleTheme}
            title="Change board theme"
            className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:border-slate-500 transition-all"
          >
            {theme.label}
          </button>
        </div>
      </div>

      {/* Board */}
      <div className="mx-auto relative" style={{ maxWidth: '520px' }}>
        <div
          ref={boardRef}
          className="grid w-full aspect-square rounded-md overflow-hidden select-none"
          style={{
            gridTemplateColumns: 'repeat(8, minmax(0, 1fr))',
            gridTemplateRows: 'repeat(8, minmax(0, 1fr))',
            touchAction: 'none',
            boxShadow: `0 10px 30px -8px rgba(0,0,0,0.65), 0 0 0 6px ${theme.frame}, 0 0 0 7px rgba(255,255,255,0.06)`,
          }}
          onContextMenu={(e) => e.preventDefault()}
        >
          {Array.from({ length: 64 }).map((_, idx) => {
            const rowFromTop = Math.floor(idx / 8); // 0..7 top->bottom
            const file = idx % 8;
            const rank = 7 - rowFromTop;
            const c: Coord = [file, rank];
            const squareName = FILES[file] + (rank + 1);
            const piece = pieceAt(c);
            const isDark = (file + rank) % 2 === 1;

            const isLastFrom = lastHighlight && lastHighlight.from[0] === file && lastHighlight.from[1] === rank;
            const isLastTo = lastHighlight && lastHighlight.to[0] === file && lastHighlight.to[1] === rank;
            const isSelected = !!selected && selected[0] === file && selected[1] === rank;
            const isTarget = selected !== null && targets.has(squareName);
            const isTargetCapture = isTarget && targets.get(squareName) === true;
            const isCheckedKing = !!checkedKingSquare && checkedKingSquare[0] === file && checkedKingSquare[1] === rank;
            const isDragOrigin = !!drag && drag.from[0] === file && drag.from[1] === rank;

            return (
              <div
                key={idx}
                onPointerDown={(e) => handlePointerDown(e, c)}
                className="relative flex items-center justify-center"
                style={{
                  backgroundColor: isDark ? theme.dark : theme.light,
                  cursor: isOwnTurnPiece(piece) || isTarget ? 'pointer' : 'default',
                  boxShadow: isCheckedKing
                    ? 'inset 0 0 12px 4px rgba(255, 40, 40, 0.75)'
                    : undefined,
                }}
              >
                {/* Last move tint (under everything else) */}
                {(isLastFrom || isLastTo) && (
                  <div className="absolute inset-0" style={{ backgroundColor: 'rgba(255, 213, 79, 0.42)' }} />
                )}
                {/* Selected square halo */}
                {isSelected && (
                  <div className="absolute inset-0" style={{ backgroundColor: 'rgba(59, 130, 246, 0.35)' }} />
                )}

                {/* Coordinate labels */}
                {file === 0 && (
                  <span
                    className="absolute top-0.5 left-1 text-[9px] font-bold z-10 pointer-events-none"
                    style={{ color: isDark ? theme.light : theme.dark, opacity: 0.85 }}
                  >
                    {rank + 1}
                  </span>
                )}
                {rank === 0 && (
                  <span
                    className="absolute bottom-0.5 right-1 text-[9px] font-bold z-10 pointer-events-none"
                    style={{ color: isDark ? theme.light : theme.dark, opacity: 0.85 }}
                  >
                    {FILES[file]}
                  </span>
                )}

                {/* Piece (dimmed while being dragged away) */}
                {piece && !isDragOrigin && (
                  <img
                    src={PIECE_IMAGES[piece]}
                    alt={piece}
                    draggable={false}
                    className="relative z-[5] pointer-events-none"
                    style={{ width: '88%', height: '88%', filter: 'drop-shadow(0 2px 3px rgba(0,0,0,0.4))' }}
                  />
                )}
                {piece && isDragOrigin && (
                  <img
                    src={PIECE_IMAGES[piece]}
                    alt=""
                    draggable={false}
                    className="absolute inset-0 m-auto opacity-30 pointer-events-none"
                    style={{ width: '88%', height: '88%' }}
                  />
                )}

                {/* Legal move indicators */}
                {isTarget && !isTargetCapture && (
                  <div
                    className="absolute rounded-full z-[6] pointer-events-none"
                    style={{ width: '30%', height: '30%', backgroundColor: 'rgba(15, 23, 42, 0.28)' }}
                  />
                )}
                {isTarget && isTargetCapture && (
                  <div
                    className="absolute inset-[6%] rounded-full z-[6] pointer-events-none"
                    style={{ border: 'calc(min(4vw, 5px)) solid rgba(15, 23, 42, 0.32)' }}
                  />
                )}
              </div>
            );
          })}
        </div>

        {/* Floating dragged piece */}
        {drag && drag.moved && boardRect && (
          <img
            src={PIECE_IMAGES[drag.piece]}
            alt=""
            draggable={false}
            className="fixed z-50 pointer-events-none"
            style={{
              width: squarePx * 0.92,
              height: squarePx * 0.92,
              left: drag.x - squarePx * 0.46,
              top: drag.y - squarePx * 0.46,
              filter: 'drop-shadow(0 6px 10px rgba(0,0,0,0.5))',
            }}
          />
        )}

        {/* Promotion picker */}
        {promotion && (
          <div
            className="absolute inset-0 z-40 bg-slate-950/50 backdrop-blur-[1px]"
            onClick={() => setPromotion(null)}
          >
            <div
              className="absolute bg-slate-900 border border-slate-600 rounded-xl shadow-2xl overflow-hidden"
              style={{
                left: `${(promotion.to[0] / 8) * 100}%`,
                top: promotion.color === 'white' ? 0 : 'auto',
                bottom: promotion.color === 'black' ? 0 : 'auto',
                width: '12.5%',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {(promotion.color === 'white' ? ['q', 'r', 'b', 'n'] : ['q', 'r', 'b', 'n']).map((p) => {
                const glyphKey = promotion.color === 'white' ? p.toUpperCase() : p;
                const uci = `${coordToSquareName(promotion.from)}${coordToSquareName(promotion.to)}${p}`;
                return (
                  <button
                    key={p}
                    onClick={() => {
                      onMovePlayed(uci);
                      setPromotion(null);
                    }}
                    className="w-full aspect-square flex items-center justify-center hover:bg-violet-600/40 transition-colors"
                    title={`Promote to ${p.toUpperCase()}`}
                  >
                    <img src={PIECE_IMAGES[glyphKey]} alt={p} className="w-[80%] h-[80%]" draggable={false} />
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <div className="mt-3 text-center text-[10px] text-slate-500 leading-relaxed">
        Drag a piece or click piece then square ·{' '}
        <span className="font-mono text-slate-400">&larr; &rarr;</span> /{' '}
        <span className="font-mono text-slate-400">h l</span> step ·{' '}
        <span className="font-mono text-slate-400">Home End</span> /{' '}
        <span className="font-mono text-slate-400">g G</span> jump
      </div>
    </div>
  );
};

export default WebAnalysisBoard;
