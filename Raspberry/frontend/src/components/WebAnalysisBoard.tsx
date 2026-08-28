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

export interface EngineLineProp {
  uci: string[];
  san: string[];
  score_cp: number | null;
  mate: number | null;
}

export type Coord = [number, number]; // [file 0-7, rank 0-7]

export interface WebAnalysisBoardProps {
  fen?: string;
  grid?: string[][];
  /** Legal moves for the current position (UCI), provided by the backend. */
  legalMoves?: string[];
  /** True when the side to move is in check. */
  inCheck?: boolean;
  /** UCI of the most recent move to highlight (mainline or branch). */
  lastMoveUci?: string | null;
  /** Classification of the last MAINLINE move (colors the highlight tint). */
  lastMoveClass?: string | null;
  /** UCI of the engine's suggested better move (drawn as a clickable arrow). */
  suggestMove?: string | null;
  /** Invoked when the user clicks the suggestion arrow. */
  onSuggestionClick?: () => void;
  /** True while the position is off the main game line (variation sandbox). */
  isBranching?: boolean;
  /** Live evaluation for the eval bar. */
  showEvalBar?: boolean;
  winChance?: number | null;
  scoreCp?: number | null;
  mate?: number | null;
  /** Called with the full UCI (incl. promotion suffix) when a move is played. */
  onMovePlayed?: (uci: string) => void;
  /** Color the user played in the analyzed game — board auto-orients to it. */
  myColor?: 'white' | 'black' | null;
  /** Top engine PV lines for the position (chess.com-style panel). */
  topLines?: EngineLineProp[] | null;
  showEngineLines?: boolean;
  /** Invoked with a line index when a user clicks an engine line to follow it. */
  onLineClick?: (lineIndex: number) => void;
  /** Show the keyboard/usage hints under the board */
  showHints?: boolean;
  /** Hide the default header (or replace with custom title/header) */
  hideHeader?: boolean;
  headerTitle?: React.ReactNode;
  headerRight?: React.ReactNode;
  showOrientationToggle?: boolean;
  showThemeToggle?: boolean;
  topBar?: React.ReactNode;
  /** Move quality tiers for target square dots */
  destQualities?: Map<string, 'best' | 'good' | 'inaccuracy' | 'blunder'>;
  /** Custom overlay renderer per square */
  renderSquareOverlay?: (coord: Coord, squareName: string) => React.ReactNode;
  /** Whole-board overlay, e.g. physical sensor matrix */
  boardOverlay?: React.ReactNode | ((flipped: boolean) => React.ReactNode);
  /** Physical board setup highlights (missing starting squares white, misplaced pieces amber/yellow) */
  setupHighlights?: SetupHighlightsProp;
  className?: string;
  disabled?: boolean;
}

export interface SetupHighlightsProp {
  missingWhite?: Array<[number, number]>;
  missingBlack?: Array<[number, number]>;
  misplaced?: Array<[number, number]>;
  enabled?: boolean;
}

export const PIECE_IMAGES: Record<string, string> = {
  K: wK, Q: wQ, R: wR, B: wB, N: wN, P: wP,
  k: bK, q: bQ, r: bR, b: bB, n: bN, p: bP,
};

/** Chess.com-style classification tint for the last-move highlight. */
export const CLASS_TINTS: Record<string, string> = {
  best: 'rgba(16, 185, 129, 0.55)',       // emerald
  good: 'rgba(52, 211, 153, 0.45)',       // light emerald
  book: 'rgba(148, 163, 184, 0.45)',      // gray
  inaccuracy: 'rgba(250, 204, 21, 0.55)', // yellow
  mistake: 'rgba(249, 115, 22, 0.58)',    // orange
  blunder: 'rgba(239, 68, 68, 0.6)',      // red
};

export const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];

export interface BoardTheme {
  name: string;
  label: string;
  light: string;
  dark: string;
  frame: string;
}

export const THEMES: BoardTheme[] = [
  { name: 'green', label: 'Green', light: '#EBECD0', dark: '#739552', frame: '#3d4a2e' },
  { name: 'wood', label: 'Wood', light: '#F0D9B5', dark: '#B58863', frame: '#6b4a2f' },
  { name: 'slate', label: 'Slate', light: '#4B5872', dark: '#323C52', frame: '#1e293b' },
];

export const THEME_STORAGE_KEY = 'webboard-theme';
/** Animation tuning: base glide time plus extra per-square travelled. */
export const MOVE_ANIM_BASE_MS = 150;
export const MOVE_ANIM_PER_SQUARE_MS = 26;
export const MOVE_ANIM_MAX_MS = 280;

export function digitalGridToFen(digital: string[][], turn: 'white' | 'black' = 'white'): string {
  if (!digital || !Array.isArray(digital) || digital.length < 8) {
    return 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
  }
  const ranks: string[] = [];
  for (let r = 7; r >= 0; r--) {
    let emptyCount = 0;
    let rankStr = '';
    for (let f = 0; f < 8; f++) {
      const p = digital[r]?.[f];
      if (!p || p === '.') {
        emptyCount++;
      } else {
        if (emptyCount > 0) {
          rankStr += emptyCount.toString();
          emptyCount = 0;
        }
        rankStr += p;
      }
    }
    if (emptyCount > 0) {
      rankStr += emptyCount.toString();
    }
    ranks.push(rankStr || '8');
  }
  const activeColor = turn === 'black' ? 'b' : 'w';
  return `${ranks.join('/')} ${activeColor} - - 0 1`;
}

export function parseFenPlacement(fen: string): string[][] {
  // FEN ranks arrive 8 -> 1; index so that grid[0] = RANK 1 row (consistent
  // with Coord semantics where rank 0 == chess rank 1).
  const rows = (fen.split(' ')[0] || '').split('/').reverse();
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

export function coordToSquareName(c: Coord): string {
  return `${FILES[c[0]]}${c[1] + 1}`;
}

export function uciToCoords(uci: string): { from: Coord; to: Coord } | null {
  if (!uci || uci.length < 4) return null;
  const f = FILES.indexOf(uci[0]);
  const r = parseInt(uci[1], 10) - 1;
  const tf = FILES.indexOf(uci[2]);
  const tr = parseInt(uci[3], 10) - 1;
  if ([f, r, tf, tr].some((v) => v < 0 || v > 7)) return null;
  return { from: [f, r], to: [tf, tr] };
}

/**
 * Glyph of a captured piece that used to sit on `sq`, if the latest move
 * captured there (used to render the fade-out ghost). Returns '' when none.
 */
export function capturedGhostSquare(
  prevGrid: string[][] | null,
  grid: string[][],
  lastHighlight: { from: Coord; to: Coord } | null,
  sq: Coord,
  pieceNow: string,
): string {
  if (!prevGrid || !lastHighlight) return '';
  // Only squares that are NOT the arrival square (that one animates the mover)
  if (sq[0] === lastHighlight.to[0] && sq[1] === lastHighlight.to[1]) return '';
  const before = prevGrid[sq[1]]?.[sq[0]] ?? '';
  const after = pieceNow;
  if (!before || after === before) return '';
  // The victim must be of the opposite color of the moving piece.
  const mover = grid[lastHighlight.to[1]]?.[lastHighlight.to[0]] ?? '';
  if (!mover) return '';
  const moverIsWhite = mover === mover.toUpperCase();
  const victimIsWhite = before === before.toUpperCase();
  if (moverIsWhite === victimIsWhite) return '';
  return before;
}

/**
 * Interactive lichess-style analysis & play board: SVG pieces, themed squares,
 * drag & drop + click-to-move (pointer events, mouse and touch), legal-move
 * dots/capture rings, check glow, promotion picker, smooth move animation,
 * and an evaluation bar.
 */
const WebAnalysisBoard: React.FC<WebAnalysisBoardProps> = ({
  fen,
  grid: gridProp,
  legalMoves: legalMovesProp,
  inCheck,
  lastMoveUci,
  lastMoveClass,
  isBranching,
  showEvalBar,
  winChance,
  scoreCp,
  mate,
  onMovePlayed,
  myColor,
  suggestMove,
  onSuggestionClick,
  topLines,
  showEngineLines,
  onLineClick,
  showHints,
  hideHeader,
  headerTitle,
  headerRight,
  showOrientationToggle,
  showThemeToggle,
  topBar,
  bottomBar,
  destQualities,
  renderSquareOverlay,
  boardOverlay,
  setupHighlights,
  className,
  disabled,
}) => {
  const legalMoves = useMemo(() => legalMovesProp ?? [], [legalMovesProp]);

  const missingSquaresSet = useMemo(() => {
    if (!setupHighlights?.enabled) return new Set<string>();
    const set = new Set<string>();
    for (const [f, r] of setupHighlights.missingWhite ?? []) {
      set.add(`${f},${r}`);
    }
    for (const [f, r] of setupHighlights.missingBlack ?? []) {
      set.add(`${f},${r}`);
    }
    return set;
  }, [setupHighlights]);

  const misplacedSquaresSet = useMemo(() => {
    if (!setupHighlights?.enabled) return new Set<string>();
    const set = new Set<string>();
    for (const [f, r] of setupHighlights.misplaced ?? []) {
      set.add(`${f},${r}`);
    }
    return set;
  }, [setupHighlights]);

  const grid = useMemo(() => {
    if (gridProp && Array.isArray(gridProp) && gridProp.length === 8) {
      return gridProp.map((row) => row.map((cell) => (cell === '.' ? '' : cell)));
    }
    return parseFenPlacement(fen || 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
  }, [fen, gridProp]);

  const whiteToMove = useMemo(() => {
    if (fen) {
      return (fen.split(' ')[1] || 'w') === 'w';
    }
    return true;
  }, [fen]);

  // Previous placement grid, used to animate capture fade-outs
  const prevGridRef = useRef<string[][] | null>(null);
  useEffect(() => {
    return () => {
      prevGridRef.current = null;
    };
  }, []);
  const prevGrid = prevGridRef.current;
  useEffect(() => {
    // Update after paint so the current render still sees the old board
    prevGridRef.current = grid;
  }, [grid]);

  // Board orientation: auto-follows the user's color; a manual flip overrides.
  const [flipped, setFlipped] = useState<boolean>(myColor === 'black');
  const [manualFlip, setManualFlip] = useState<boolean>(false);
  useEffect(() => {
    if (!manualFlip) setFlipped(myColor === 'black');
  }, [myColor, manualFlip]);
  const toggleOrientation = () => {
    setManualFlip(true);
    setFlipped((f) => !f);
  };

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
  // Only {from, piece} live in state (one render per grab, NOT per mousemove);
  // the ghost follows the pointer via direct DOM writes for buttery smoothness.
  const [drag, setDrag] = useState<{ from: Coord; piece: string } | null>(null);
  const [promotion, setPromotion] = useState<{ from: Coord; to: Coord; color: 'white' | 'black' } | null>(null);

  const boardRef = useRef<HTMLDivElement | null>(null);
  const ghostRef = useRef<HTMLDivElement | null>(null);
  const pressRef = useRef<{ coord: Coord; startX: number; startY: number; wasSelected: boolean } | null>(null);
  const ghostSizeRef = useRef<number>(60);

  useEffect(() => {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, THEMES[themeIdx].name);
    } catch {
      /* ignore */
    }
  }, [themeIdx]);

  const lastHighlight = useMemo(() => (lastMoveUci ? uciToCoords(lastMoveUci) : null), [lastMoveUci]);

  // Castling rook animation: derived once per position change
  const rookAnimBase = useMemo(() => {
    if (!lastHighlight || !lastMoveUci || lastMoveUci.length < 4) return null;
    const kFrom = lastHighlight.from;
    const kTo = lastHighlight.to;
    const dFile = kTo[0] - kFrom[0];
    if (Math.abs(dFile) !== 2) return null; // not a castling king move
    const rFrom: Coord = [dFile > 0 ? 7 : 0, kFrom[1]];
    const rTo: Coord = [dFile > 0 ? 5 : 3, kTo[1]];
    const glyph = grid[rTo[1]]?.[rTo[0]] ?? '';
    if (!glyph || glyph.toUpperCase() !== 'R') return null;
    return { from: rFrom, to: rTo, glyph };
  }, [lastHighlight, lastMoveUci, grid]);

  // Suggested better-move arrow
  const suggestArrow = useMemo(() => {
    if (isBranching) {
      const best = topLines?.[0]?.uci?.[0];
      if (best && best.length >= 4) return uciToCoords(best);
    }
    if (!suggestMove || suggestMove.length < 4) return null;
    return uciToCoords(suggestMove);
  }, [isBranching, topLines, suggestMove]);

  // Squares the selected piece may travel to
  const targets = useMemo(() => {
    if (!selected) return new Map<string, boolean>();
    const prefix = coordToSquareName(selected);
    const map = new Map<string, boolean>();
    for (const lm of legalMoves) {
      if (lm.startsWith(prefix)) {
        map.set(lm.slice(2, 4), lm.length > 4); // capture or promotion
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

  const isOwnTurnPiece = (glyph: string, c?: Coord): boolean => {
    if (!glyph || disabled) return false;
    if (legalMoves.length > 0 && c) {
      const sqName = coordToSquareName(c);
      return legalMoves.some((lm) => lm.startsWith(sqName));
    }
    return whiteToMove ? glyph === glyph.toUpperCase() : glyph === glyph.toLowerCase();
  };

  const tryPlay = (from: Coord, to: Coord): boolean => {
    if (disabled || !onMovePlayed) return false;
    const fromStr = coordToSquareName(from);
    const toStr = coordToSquareName(to);
    const candidates = legalMoves.filter((lm) => lm.startsWith(fromStr + toStr));
    if (candidates.length === 0) return false;
    if (candidates[0].length > 4) {
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
    const col = Math.floor((clientX - rect.left) / sq);
    const rowFromTop = Math.floor((clientY - rect.top) / sq);
    if (col < 0 || col > 7 || rowFromTop < 0 || rowFromTop > 7) return null;
    const rank = flipped ? rowFromTop : 7 - rowFromTop;
    const file = flipped ? 7 - col : col;
    if (file < 0 || file > 7 || rank < 0 || rank > 7) return null;
    return [file, rank];
  };

  const positionGhost = (clientX: number, clientY: number) => {
    const el = ghostRef.current;
    if (!el || !boardRef.current) return;
    const sq = boardRef.current.getBoundingClientRect().width / 8;
    el.style.transform = `translate(${clientX - sq / 2}px, ${clientY - sq / 2}px)`;
  };

  const handlePointerDown = (e: React.PointerEvent, c: Coord) => {
    if (promotion || disabled) return;

    // Complete a click-click move onto a highlighted target
    if (selected && targets.has(coordToSquareName(c))) {
      tryPlay(selected, c);
      return;
    }

    const glyph = pieceAt(c);
    if (!isOwnTurnPiece(glyph, c)) {
      setSelected(null);
      return;
    }

    // Select (and prepare a potential drag)
    const wasSelected = !!selected && selected[0] === c[0] && selected[1] === c[1];
    setSelected(c);
    pressRef.current = { coord: c, startX: e.clientX, startY: e.clientY, wasSelected };
    const rect = boardRef.current?.getBoundingClientRect();
    if (rect) ghostSizeRef.current = rect.width / 8;
    setDrag({ from: c, piece: glyph });
    // Position the ghost immediately at the grab point
    requestAnimationFrame(() => positionGhost(e.clientX, e.clientY));
  };

  // Global pointer tracking while a piece is held
  useEffect(() => {
    if (!drag) return;
    let hasDraggedFar = false;

    const onMove = (e: PointerEvent) => {
      const press = pressRef.current;
      if (!press) return;
      if (
        Math.abs(e.clientX - press.startX) > 5 ||
        Math.abs(e.clientY - press.startY) > 5
      ) {
        hasDraggedFar = true;
      }
      if (hasDraggedFar) {
        positionGhost(e.clientX, e.clientY);
      }
    };

    const onUp = (e: PointerEvent) => {
      const press = pressRef.current;
      pressRef.current = null;
      setDrag(null);
      if (!press) return;

      const target = squareFromPoint(e.clientX, e.clientY);

      if (hasDraggedFar) {
        // Drag release: play if dropped on a legal square, otherwise snap back.
        if (
          target &&
          !(target[0] === press.coord[0] && target[1] === press.coord[1]) &&
          tryPlay(press.coord, target)
        ) {
          return;
        }
        setSelected(null);
        return;
      }

      // Plain click: second click on the same selected piece toggles it off.
      if (press.wasSelected && target &&
        target[0] === press.coord[0] && target[1] === press.coord[1]) {
        setSelected(null);
      }
    };

    window.addEventListener('pointermove', onMove, { passive: true });
    window.addEventListener('pointerup', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drag !== null, selected, legalMoves, disabled]);

  const cycleTheme = () => setThemeIdx((i) => (i + 1) % THEMES.length);

  // Last-move highlight tint color-coded by move classification (chess.com style)
  const lastTint =
    lastMoveClass && CLASS_TINTS[lastMoveClass]
      ? CLASS_TINTS[lastMoveClass]
      : isBranching
      ? 'rgba(139, 92, 246, 0.45)'
      : 'rgba(255, 213, 79, 0.42)';

  // Eval bar geometry
  const shouldShowEvalBar = showEvalBar ?? (winChance !== undefined || scoreCp !== undefined || mate !== undefined);
  const wc = Math.max(2, Math.min(98, winChance ?? 50));
  let evalText = '0.0';
  if (mate !== null && mate !== undefined) {
    evalText = `M${Math.abs(mate)}`;
  } else if (scoreCp !== null && scoreCp !== undefined) {
    evalText = `${scoreCp >= 0 ? '+' : ''}${(scoreCp / 100).toFixed(1)}`;
  }

  const shouldShowLines = showEngineLines ?? ((topLines ?? []).length > 0 || isBranching);
  const shouldShowHints = showHints ?? true;

  return (
    <div className={`bg-slate-900/90 border border-slate-800 rounded-2xl p-3 md:p-4 shadow-xl ${className || ''}`}>
      {/* Header if not hidden */}
      {!hideHeader && (
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            {headerTitle ? (
              typeof headerTitle === 'string' ? (
                <h3 className="text-sm font-bold text-white">{headerTitle}</h3>
              ) : (
                headerTitle
              )
            ) : (
              <h3 className="text-sm font-bold text-white">Analysis Board</h3>
            )}
            {isBranching !== undefined && (
              <span
                className={`px-2 py-0.5 text-[10px] font-bold rounded-full border ${
                  isBranching
                    ? 'bg-violet-500/20 text-violet-300 border-violet-500/40'
                    : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                }`}
              >
                {isBranching ? 'VARIATION SANDBOX' : 'MAIN GAME LINE'}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {showOrientationToggle !== false && (
              <button
                onClick={toggleOrientation}
                title="Flip board orientation"
                className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:border-slate-500 transition-all"
              >
                {flipped ? 'Black ▼' : 'White ▲'}
              </button>
            )}
            {showThemeToggle !== false && (
              <button
                onClick={cycleTheme}
                title="Change board theme"
                className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-slate-800 border border-slate-700 text-slate-300 hover:text-white hover:border-slate-500 transition-all"
              >
                {theme.label}
              </button>
            )}
            {headerRight}
          </div>
        </div>
      )}

      {/* Top Bar (e.g. Opponent Header Bar in Play section) */}
      {topBar && (
        <div className="mb-3">
          {topBar}
        </div>
      )}

      {/* Eval bar + board + engine lines panel */}
      <div className="mx-auto flex items-stretch justify-center gap-2" style={{ maxWidth: shouldShowLines ? '860px' : '560px' }}>
        {/* Evaluation bar (oriented with the board) */}
        {shouldShowEvalBar && (
          <div className="relative self-stretch w-5 rounded-full overflow-hidden bg-slate-800 ring-1 ring-slate-700 shadow-inner flex-shrink-0">
            <div
              className={`absolute inset-x-0 bg-gradient-to-t from-slate-100 to-white transition-[height] duration-300 ease-out ${
                flipped ? 'top-0' : 'bottom-0'
              }`}
              style={{ height: `${wc}%` }}
            />
            <div
              className="absolute inset-x-0 h-px bg-violet-400/70"
              style={flipped ? { top: `${wc}%` } : { bottom: `${wc}%` }}
            />
            <div
              className="absolute inset-x-0 text-center text-[9px] font-mono font-bold pointer-events-none"
              style={{
                ...(flipped ? { top: `calc(${wc}% + 2px)` } : { bottom: `calc(${wc}% + 2px)` }),
                color: wc > 45 ? '#0f172a' : '#e2e8f0',
                transform: wc > 92 || wc < 8 ? (flipped ? 'translateY(14px)' : 'translateY(-14px)') : 'none',
              }}
            >
              {evalText}
            </div>
          </div>
        )}

        {/* Board */}
        <div className="relative flex-1 max-w-full">
          <div
            ref={boardRef}
            className="grid w-full aspect-square rounded-md overflow-hidden select-none relative"
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
            const col = idx % 8;
            // Orientation: white view shows rank 8 at top; flipped shows rank 1 at top
            const rank = flipped ? rowFromTop : 7 - rowFromTop;
            const file = flipped ? 7 - col : col;
            const c: Coord = [file, rank];
            const squareName = FILES[file] + (rank + 1);
            const piece = pieceAt(c);
            const isDark = (file + rank) % 2 === 0;

            const isLastFrom = lastHighlight && lastHighlight.from[0] === file && lastHighlight.from[1] === rank;
            const isLastTo = lastHighlight && lastHighlight.to[0] === file && lastHighlight.to[1] === rank;
            const isSelected = !!selected && selected[0] === file && selected[1] === rank;
            const isTarget = selected !== null && targets.has(squareName);
            const isTargetCapture = isTarget && targets.get(squareName) === true;
            const isCheckedKing = !!checkedKingSquare && checkedKingSquare[0] === file && checkedKingSquare[1] === rank;
            const isDragOrigin = !!drag && drag.from[0] === file && drag.from[1] === rank;

            const isLeftEdge = col === 0;
            const isBottomEdge = rowFromTop === 7;

            // Castling: when the last move is a king's two-square move, its
            // rook glides alongside instead of teleporting.
            const rookAnim =
              rookAnimBase &&
              file === rookAnimBase.to[0] &&
              rank === rookAnimBase.to[1]
                ? rookAnimBase
                : null;

            // Captured piece that used to occupy this square (fade-out ghost).
            const captured = capturedGhostSquare(
              prevGrid,
              grid,
              lastHighlight,
              [file, rank],
              piece,
            );

            const isMissingStarting = missingSquaresSet.has(`${file},${rank}`);
            const isMisplaced = misplacedSquaresSet.has(`${file},${rank}`);

            return (
              <div
                key={idx}
                onPointerDown={(e) => handlePointerDown(e, c)}
                className="relative flex items-center justify-center"
                style={{
                  backgroundColor: isDark ? theme.dark : theme.light,
                  cursor: isOwnTurnPiece(piece, c) || isTarget ? 'pointer' : 'default',
                  boxShadow: isCheckedKing
                    ? 'inset 0 0 12px 4px rgba(255, 40, 40, 0.75)'
                    : undefined,
                }}
              >
                {/* Last move tint, color-coded by classification */}
                {(isLastFrom || isLastTo) && (
                  <div className="absolute inset-0 transition-colors duration-200" style={{ backgroundColor: lastTint }} />
                )}
                {/* Selected square halo */}
                {isSelected && (
                  <div className="absolute inset-0" style={{ backgroundColor: 'rgba(59, 130, 246, 0.35)' }} />
                )}

                {/* Physical setup: Misplaced piece warning highlight (amber/yellow glow) */}
                {isMisplaced && (
                  <div
                    className="absolute inset-0.5 rounded-lg border-2 border-amber-400 bg-amber-500/25 z-[6] pointer-events-none shadow-[0_0_12px_rgba(245,158,11,0.65)] flex items-center justify-center animate-pulse"
                    title="Misplaced piece — return to starting square or remove"
                  >
                    <div className="w-2.5 h-2.5 rounded-full bg-amber-400 border border-amber-200 shadow-[0_0_6px_#f59e0b]" />
                  </div>
                )}

                {/* Physical setup: Missing starting piece highlight (pure white glow) */}
                {isMissingStarting && (
                  <div
                    className="absolute inset-0.5 rounded-lg border-2 border-white/90 bg-white/20 z-[6] pointer-events-none shadow-[0_0_12px_rgba(255,255,255,0.7)] flex items-center justify-center animate-pulse"
                    title="Missing starting piece — place piece here"
                  >
                    <div className="w-2.5 h-2.5 rounded-full bg-white border border-slate-200 shadow-[0_0_6px_#fff]" />
                  </div>
                )}

                {/* Coordinate labels along board edges */}
                {isLeftEdge && (
                  <span
                    className="absolute top-0.5 left-1 text-[9px] font-bold z-10 pointer-events-none select-none"
                    style={{ color: isDark ? theme.light : theme.dark, opacity: 0.85 }}
                  >
                    {rank + 1}
                  </span>
                )}
                {isBottomEdge && (
                  <span
                    className="absolute bottom-0.5 right-1 text-[9px] font-bold z-10 pointer-events-none select-none"
                    style={{ color: isDark ? theme.light : theme.dark, opacity: 0.85 }}
                  >
                    {FILES[file]}
                  </span>
                )}

                {/* Custom Square Overlay (e.g. Guardrail badges, Capture swords) */}
                {renderSquareOverlay && renderSquareOverlay(c, squareName)}

                {/* Smoothly animated arriving piece */}
                {piece && isLastTo && lastHighlight && !isDragOrigin && (
                  <MovingPiece
                    key={`${lastMoveUci}-${fen?.length ?? 0}`}
                    src={PIECE_IMAGES[piece]}
                    from={lastHighlight.from}
                    to={[file, rank]}
                    flipped={flipped}
                    glyph={piece}
                  />
                )}

                {/* Castling rook glides alongside the king */}
                {piece && rookAnim && lastHighlight && !isDragOrigin && (
                  <MovingPiece
                    key={`rook-${lastMoveUci}-${fen?.length ?? 0}`}
                    src={PIECE_IMAGES[piece]}
                    from={rookAnim.from}
                    to={[file, rank]}
                    flipped={flipped}
                    glyph={piece}
                  />
                )}

                {/* Fading ghost of a captured piece */}
                {captured && !isDragOrigin && (
                  <CapturedGhost
                    key={`cap-${lastMoveUci}-${file}${rank}`}
                    src={PIECE_IMAGES[captured]}
                  />
                )}

                {/* Static piece */}
                {piece && !isLastTo && !rookAnim && !isDragOrigin && (
                  <img
                    src={PIECE_IMAGES[piece]}
                    alt={piece}
                    draggable={false}
                    className="relative z-[5] pointer-events-none select-none"
                    style={{ width: '88%', height: '88%', filter: 'drop-shadow(0 2px 3px rgba(0,0,0,0.4))' }}
                  />
                )}
                {piece && isDragOrigin && (
                  <img
                    src={PIECE_IMAGES[piece]}
                    alt=""
                    draggable={false}
                    className="absolute inset-0 m-auto opacity-30 pointer-events-none select-none"
                    style={{ width: '88%', height: '88%' }}
                  />
                )}

                {/* Legal move indicators (with Move Quality tier support) */}
                {isTarget && !isTargetCapture && (
                  <div
                    className={`absolute rounded-full z-[6] pointer-events-none ${
                      destQualities?.get(squareName) === 'good'
                        ? 'bg-cyan-400/90 shadow-[0_0_8px_rgba(34,211,238,0.9)]'
                        : destQualities?.get(squareName) === 'inaccuracy'
                        ? 'bg-amber-400/90 shadow-[0_0_8px_rgba(251,191,36,0.9)]'
                        : destQualities?.get(squareName) === 'blunder'
                        ? 'bg-rose-500/90 shadow-[0_0_8px_rgba(244,63,94,0.9)]'
                        : destQualities?.get(squareName) === 'best'
                        ? 'bg-emerald-400/90 shadow-[0_0_8px_rgba(52,211,153,0.9)]'
                        : 'bg-slate-900/30'
                    }`}
                    style={{ width: '30%', height: '30%' }}
                  />
                )}
                {isTarget && isTargetCapture && (
                  <div
                    className={`absolute inset-[6%] rounded-full z-[6] pointer-events-none ${
                      destQualities?.get(squareName) === 'good'
                        ? 'border-cyan-400/90 shadow-[0_0_8px_rgba(34,211,238,0.5)]'
                        : destQualities?.get(squareName) === 'inaccuracy'
                        ? 'border-amber-400/90 shadow-[0_0_8px_rgba(251,191,36,0.5)]'
                        : destQualities?.get(squareName) === 'blunder'
                        ? 'border-rose-500/90 shadow-[0_0_8px_rgba(244,63,94,0.5)]'
                        : destQualities?.get(squareName) === 'best'
                        ? 'border-emerald-400/90 shadow-[0_0_8px_rgba(52,211,153,0.5)]'
                        : 'border-slate-900/35'
                    }`}
                    style={{ borderStyle: 'solid', borderWidth: 'calc(min(4vw, 5px))' }}
                  />
                )}
              </div>
            );
          })}

          {/* Whole-board overlay (e.g. physical sensor matrix when active) */}
          {boardOverlay && (
            <div className="absolute inset-0 z-20 pointer-events-auto">
              {typeof boardOverlay === 'function' ? boardOverlay(flipped) : boardOverlay}
            </div>
          )}
          </div>

          {/* Suggested better-move arrow (clickable) */}
          {suggestArrow && (
            <svg
              className="absolute inset-0 z-[7] w-full h-full"
              viewBox="0 0 8 8"
              style={{ overflow: 'visible', pointerEvents: 'none' }}
            >
              {(() => {
                const screenCol = (f: number) => (flipped ? 7 - f : f);
                const screenRow = (r: number) => (flipped ? r : 7 - r);
                const x1 = screenCol(suggestArrow.from[0]) + 0.5;
                const y1 = screenRow(suggestArrow.from[1]) + 0.5;
                const x2 = screenCol(suggestArrow.to[0]) + 0.5;
                const y2 = screenRow(suggestArrow.to[1]) + 0.5;
                const dx = x2 - x1;
                const dy = y2 - y1;
                const len = Math.hypot(dx, dy) || 1;
                const ux = dx / len;
                const uy = dy / len;
                // Shorten the shaft so it starts/ends inside the squares
                const sx = x1 + ux * 0.3;
                const sy = y1 + uy * 0.3;
                const hx = x2 - ux * 0.38;
                const hy = y2 - uy * 0.38;
                const px = -uy;
                const py = ux;
                const headW = 0.22;
                return (
                  <g
                    style={{ pointerEvents: 'stroke', cursor: 'pointer' }}
                    onClick={() => onSuggestionClick?.()}
                  >
                    <line
                      x1={sx} y1={sy} x2={hx} y2={hy}
                      stroke="rgba(16, 185, 129, 0.85)"
                      strokeWidth={0.17}
                      strokeLinecap="round"
                    />
                    <polygon
                      points={`${x2},${y2} ${hx + px * headW},${hy + py * headW} ${hx - px * headW},${hy - py * headW}`}
                      fill="rgba(16, 185, 129, 0.85)"
                    />
                    {/* Fat invisible hit area for easy clicking */}
                    <line
                      x1={x1} y1={y1} x2={x2} y2={y2}
                      stroke="transparent"
                      strokeWidth={0.6}
                    />
                  </g>
                );
              })()}
            </svg>
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
                {['q', 'r', 'b', 'n'].map((p) => {
                  const glyphKey = promotion.color === 'white' ? p.toUpperCase() : p;
                  const uci = `${coordToSquareName(promotion.from)}${coordToSquareName(promotion.to)}${p}`;
                  return (
                    <button
                      key={p}
                      onClick={() => {
                        onMovePlayed?.(uci);
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

        {/* Engine lines panel (chess.com-style, right of the board) */}
        {shouldShowLines && (
          <div
            className="self-stretch w-[190px] shrink-0 bg-slate-950/80 border border-slate-800 rounded-xl p-2 flex flex-col gap-1 overflow-y-auto"
            data-testid="engine-lines"
          >
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500 px-1 pb-1">
              Engine Lines
            </div>
            {(topLines ?? []).length === 0 && (
              <div className="text-[10px] text-slate-600 px-1 py-2">Computing…</div>
            )}
            {(topLines ?? []).map((line, i) => {
              const evalLabel =
                line.mate !== null && line.mate !== undefined
                  ? `M${Math.abs(line.mate)}`
                  : `${(line.score_cp ?? 0) >= 0 ? '+' : ''}${((line.score_cp ?? 0) / 100).toFixed(1)}`;
              const isBest = i === 0;
              return (
                <button
                  key={`${line.uci.join('')}-${i}`}
                  onClick={() => onLineClick?.(i)}
                  title={`Follow this line (${evalLabel})`}
                  className={`w-full text-left rounded-lg px-2 py-1.5 border transition-all hover:scale-[1.02] active:scale-[0.98] ${
                    isBest
                      ? 'bg-emerald-500/10 border-emerald-500/30 hover:bg-emerald-500/20'
                      : 'bg-slate-900/70 border-slate-700/50 hover:bg-slate-800'
                  }`}
                >
                  <div className="flex items-center justify-between gap-1">
                    <span
                      className={`text-[10px] font-mono font-bold ${
                        isBest ? 'text-emerald-300' : 'text-slate-400'
                      }`}
                    >
                      #{i + 1} {evalLabel}
                    </span>
                    <span className="text-[9px] text-slate-600">
                      {line.san.length ? `${Math.ceil(line.san.length / 2)} moves` : ''}
                    </span>
                  </div>
                  <div className="text-[11px] font-mono text-slate-200 truncate">
                    {line.san.join(' ') || line.uci.join(' ')}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Bottom Bar (e.g. Player Footer Bar in Play section) */}
      {bottomBar && (
        <div className="mt-3">
          {bottomBar}
        </div>
      )}

      {/* Floating dragged piece (positioned via direct DOM writes — no re-renders) */}
      {drag && (
        <div
          ref={ghostRef}
          className="fixed left-0 top-0 z-50 pointer-events-none"
          style={{ width: ghostSizeRef.current, height: ghostSizeRef.current }}
        >
          <img
            src={PIECE_IMAGES[drag.piece]}
            alt=""
            draggable={false}
            className="block w-full h-full select-none"
            style={{ filter: 'drop-shadow(0 6px 10px rgba(0,0,0,0.5))' }}
          />
        </div>
      )}

      {shouldShowHints && (
        <div className="mt-3 text-center text-[10px] text-slate-500 leading-relaxed">
          Drag a piece or click piece then square ·{' '}
          <span className="font-mono text-slate-400">&larr; &rarr;</span> /{' '}
          <span className="font-mono text-slate-400">h l</span> step ·{' '}
          <span className="font-mono text-slate-400">Home End</span> /{' '}
          <span className="font-mono text-slate-400">g G</span> jump
        </div>
      )}
    </div>
  );
};

/**
 * Piece that slides in from its origin square on mount — smooth, distance-aware
 * glide with a subtle pick-up scale and a gentle hop for knights.
 */
export const MovingPiece: React.FC<{
  src: string;
  from: Coord;
  to: Coord;
  flipped?: boolean;
  /** Glyph of the mover ('n'/'N' ⇒ arcing knight hop). */
  glyph?: string;
}> = ({ src, from, to, flipped, glyph }) => {
  const ref = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Screen-space square deltas accounting for board orientation
    const screenCol = (f: number) => (flipped ? 7 - f : f);
    const screenRow = (r: number) => (flipped ? r : 7 - r);
    const dCol = screenCol(from[0]) - screenCol(to[0]);
    const dRow = screenRow(from[1]) - screenRow(to[1]);
    const dist = Math.max(Math.abs(dCol), Math.abs(dRow));
    // Longer moves get proportionally more time, clamped so it stays snappy
    const dur = Math.min(MOVE_ANIM_BASE_MS + dist * MOVE_ANIM_PER_SQUARE_MS, MOVE_ANIM_MAX_MS);
    const isKnight = glyph === 'n' || glyph === 'N';

    el.style.transition = 'none';
    el.style.transform = `translate(${dCol * 100}%, ${dRow * 100}%)`;
    const raf = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        el.style.transition = [
          `transform ${dur}ms cubic-bezier(0.2, 0.9, 0.3, 1)`,
          'filter 120ms ease',
        ].join(', ');
        el.style.transform = 'translate(0, 0)';
        if (isKnight) {
          // Knight hops: lift up mid-flight then settle down at arrival
          el.animate(
            [
              { offset: 0, translate: '0 0' },
              { offset: 0.5, translate: '0 -22%' },
              { offset: 1, translate: '0 0' },
            ],
            { duration: dur, easing: 'ease-in-out', composite: 'add' },
          );
        }
      });
    });
    return () => cancelAnimationFrame(raf);
    // Primitive deps only: array props get new identities on every parent
    // render, which would replay the slide forever.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [from[0], from[1], to[0], to[1], flipped, glyph]);

  return (
    <img
      ref={ref}
      src={src}
      alt=""
      draggable={false}
      className="relative z-[5] pointer-events-none will-change-transform select-none"
      style={{
        width: '88%',
        height: '88%',
        filter: 'drop-shadow(0 4px 7px rgba(0,0,0,0.45))',
      }}
    />
  );
};

/**
 * Fading ghost of a captured piece that shrinks away when the position changes.
 */
export const CapturedGhost: React.FC<{ src: string }> = ({ src }) => {
  const ref = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.animate(
      [
        { opacity: 1, transform: 'scale(1)' },
        { opacity: 0, transform: 'scale(0.55)' },
      ],
      { duration: 180, easing: 'ease-out', fill: 'forwards' },
    );
  }, []);

  return (
    <img
      ref={ref}
      src={src}
      alt=""
      draggable={false}
      className="absolute inset-0 m-auto z-[4] pointer-events-none will-change-transform select-none"
      style={{ width: '88%', height: '88%', filter: 'drop-shadow(0 2px 3px rgba(0,0,0,0.4))' }}
    />
  );
};

export default WebAnalysisBoard;
