import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Chess } from 'chess.js';
import { Brain } from 'lucide-react';
import { useArtisanTheme } from '../../context/useArtisanTheme';
import { MagneticAuraOverlay } from './MagneticAuraOverlay';
import { LedBezelTwin } from './LedBezelTwin';
import { EvalBar } from './EvalBar';
import {
  PIECE_IMAGES,
  CLASS_TINTS,
  FILES,
  coordToSquareName,
  uciToCoords,
  calculateGlideDuration,
  getCastlingRookMove,
  capturedGhostSquare,
  parseFenPlacement,
  type EngineLineProp,
  type Coord,
  type SetupHighlightsProp,
} from './boardUtils';

export interface WebAnalysisBoardProps {
  fen?: string;
  grid?: string[][];
  legalMoves?: string[];
  inCheck?: boolean;
  lastMoveUci?: string | null;
  lastMoveClass?: string | null;
  suggestMove?: string | null;
  onSuggestionClick?: () => void;
  isBranching?: boolean;
  showEvalBar?: boolean;
  winChance?: number | null;
  scoreCp?: number | null;
  mate?: number | null;
  isComputing?: boolean;
  isLoading?: boolean;
  onMovePlayed?: (uci: string) => void;
  myColor?: 'white' | 'black' | null;
  topLines?: EngineLineProp[] | null;
  showEngineLines?: boolean;
  onLineClick?: (lineIndex: number) => void;
  showHints?: boolean;
  hideHeader?: boolean;
  headerTitle?: React.ReactNode;
  headerRight?: React.ReactNode;
  showOrientationToggle?: boolean;
  showThemeToggle?: boolean;
  topBar?: React.ReactNode;
  bottomBar?: React.ReactNode;
  destQualities?: Map<string, 'best' | 'good' | 'inaccuracy' | 'blunder'>;
  renderSquareOverlay?: (coord: Coord, squareName: string) => React.ReactNode;
  boardOverlay?: React.ReactNode | ((flipped: boolean) => React.ReactNode);
  setupHighlights?: SetupHighlightsProp;
  className?: string;
  disabled?: boolean;
  adcGrid?: number[][];
  baselines?: number[][];
  liftedSquare?: [number, number] | null;
  resignationArmed?: boolean;
  kingLiftElapsed?: number | null;
  activeAnimation?: string | null;
  ledIntensity?: number;
}

interface ActiveGlide {
  id: number;
  piece: string;
  from: Coord;
  to: Coord;
  isKnight: boolean;
  duration: number;
}

export const WebAnalysisBoard: React.FC<WebAnalysisBoardProps> = ({
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
  isComputing = false,
  isLoading = false,
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
  adcGrid,
  baselines,
  liftedSquare,
  resignationArmed,
  kingLiftElapsed,
  activeAnimation,
  ledIntensity,
}) => {
  const { currentTheme, cycleTheme, lens, flipped, toggleOrientation, setFlipped } = useArtisanTheme();
  const legalMoves = useMemo(() => legalMovesProp ?? [], [legalMovesProp]);

  const [manualFlip, setManualFlip] = useState<boolean>(false);
  useEffect(() => {
    if (!manualFlip && myColor) {
      setFlipped(myColor === 'black');
    }
  }, [myColor, manualFlip, setFlipped]);

  const handleOrientationToggle = () => {
    setManualFlip(true);
    toggleOrientation();
  };

  const missingSquaresSet = useMemo(() => {
    if (!setupHighlights?.enabled) return new Set<string>();
    const set = new Set<string>();
    for (const [f, r] of setupHighlights.missingWhite ?? []) set.add(`${f},${r}`);
    for (const [f, r] of setupHighlights.missingBlack ?? []) set.add(`${f},${r}`);
    return set;
  }, [setupHighlights]);

  const misplacedSquaresSet = useMemo(() => {
    if (!setupHighlights?.enabled) return new Set<string>();
    const set = new Set<string>();
    for (const [f, r] of setupHighlights.misplaced ?? []) set.add(`${f},${r}`);
    return set;
  }, [setupHighlights]);

  const grid = useMemo(() => {
    if (gridProp && Array.isArray(gridProp) && gridProp.length === 8) {
      return gridProp.map((row) => row.map((cell) => (cell === '.' ? '' : cell)));
    }
    return parseFenPlacement(fen || 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
  }, [fen, gridProp]);

  const [prevGridState, setPrevGridState] = useState<{ prev: string[][] | null; current: string[][] }>({
    prev: null,
    current: grid,
  });

  if (prevGridState.current !== grid) {
    setPrevGridState({
      prev: prevGridState.current,
      current: grid,
    });
  }

  const whiteToMove = useMemo(() => {
    if (fen) return (fen.split(' ')[1] || 'w') === 'w';
    return true;
  }, [fen]);

  const [selected, setSelected] = useState<Coord | null>(null);
  const [drag, setDrag] = useState<{ from: Coord; piece: string } | null>(null);
  const [ghostSize, setGhostSize] = useState<number>(60);
  const [promotion, setPromotion] = useState<{ from: Coord; to: Coord; color: 'white' | 'black' } | null>(null);

  const boardRef = useRef<HTMLDivElement | null>(null);
  const ghostRef = useRef<HTMLDivElement | null>(null);
  const lastHighlight = useMemo(() => (lastMoveUci ? uciToCoords(lastMoveUci) : null), [lastMoveUci]);
  const lastMoveUciClean = lastMoveUci ?? null;

  // Piece Gliding Animation State & Invariant Lifecycle (Render-Phase Transition)
  const [glideState, setGlideState] = useState<{
    lastMoveUci: string | null;
    glides: ActiveGlide[];
  }>({
    lastMoveUci: null,
    glides: [],
  });

  if (lastMoveUciClean !== glideState.lastMoveUci) {
    if (!lastMoveUciClean || lastMoveUciClean.length < 4) {
      setGlideState({
        lastMoveUci: lastMoveUciClean,
        glides: [],
      });
    } else {
      const coords = uciToCoords(lastMoveUciClean);
      if (!coords) {
        setGlideState({
          lastMoveUci: lastMoveUciClean,
          glides: [],
        });
      } else {
        const { from, to } = coords;
        const piece = grid[to[1]]?.[to[0]] || '';
        if (!piece) {
          setGlideState({
            lastMoveUci: lastMoveUciClean,
            glides: [],
          });
        } else {
          const duration = calculateGlideDuration(from, to);
          const isKnight = piece.toUpperCase() === 'N';
          const glides: ActiveGlide[] = [
            {
              id: Date.now(),
              piece,
              from,
              to,
              isKnight,
              duration,
            },
          ];

          // Handle Simultaneous Castling Glides (King + Rook)
          const rookMove = getCastlingRookMove(from, to, piece);
          if (rookMove) {
            glides.push({
              id: Date.now() + 1,
              piece: rookMove.piece,
              from: rookMove.from,
              to: rookMove.to,
              isKnight: false,
              duration,
            });
          }

          setGlideState({
            lastMoveUci: lastMoveUciClean,
            glides,
          });
        }
      }
    }
  }

  // Timer effect to clear active glides once animation finishes
  useEffect(() => {
    if (glideState.glides.length === 0) return;
    const maxDuration = Math.max(...glideState.glides.map((g) => g.duration), 200);
    const timer = window.setTimeout(() => {
      setGlideState((prev) => (prev.glides.length > 0 ? { ...prev, glides: [] } : prev));
    }, maxDuration);

    return () => {
      clearTimeout(timer);
    };
  }, [glideState.glides]);

  const isTargetOfActiveGlide = (file: number, rank: number): boolean => {
    return glideState.glides.some((g) => g.to[0] === file && g.to[1] === rank);
  };

  const suggestArrow = useMemo(() => {
    if (isBranching) {
      const best = topLines?.[0]?.uci?.[0];
      if (best && best.length >= 4) return uciToCoords(best);
    }
    if (!suggestMove || suggestMove.length < 4) return null;
    return uciToCoords(suggestMove);
  }, [isBranching, topLines, suggestMove]);

  const effectiveLegalMoves = useMemo(() => {
    if (legalMoves && legalMoves.length > 0) return legalMoves;
    try {
      const chess = new Chess(fen || 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
      return chess.moves({ verbose: true }).map((m) => m.from + m.to + (m.promotion || ''));
    } catch {
      return [];
    }
  }, [legalMoves, fen]);

  const targets = useMemo(() => {
    if (!selected) return new Map<string, boolean>();
    const prefix = coordToSquareName(selected);
    const map = new Map<string, boolean>();
    for (const lm of effectiveLegalMoves) {
      if (lm.startsWith(prefix)) {
        map.set(lm.slice(2, 4), lm.length > 4);
      }
    }
    return map;
  }, [selected, effectiveLegalMoves]);

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
    if (effectiveLegalMoves.length > 0 && c) {
      const sqName = coordToSquareName(c);
      return effectiveLegalMoves.some((lm) => lm.startsWith(sqName));
    }
    return whiteToMove ? glyph === glyph.toUpperCase() : glyph === glyph.toLowerCase();
  };

  const tryPlay = (from: Coord, to: Coord): boolean => {
    if (disabled || !onMovePlayed) return false;
    const fromStr = coordToSquareName(from);
    const toStr = coordToSquareName(to);
    const candidates = effectiveLegalMoves.filter((lm) => lm.startsWith(fromStr + toStr));
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
    if (selected && targets.has(coordToSquareName(c))) {
      tryPlay(selected, c);
      return;
    }
    const glyph = pieceAt(c);
    if (!isOwnTurnPiece(glyph, c)) {
      setSelected(null);
      return;
    }
    const wasSelected = !!selected && selected[0] === c[0] && selected[1] === c[1];
    setSelected(c);
    pressRef.current = { coord: c, startX: e.clientX, startY: e.clientY, wasSelected };
    const rect = boardRef.current?.getBoundingClientRect();
    if (rect) setGhostSize(rect.width / 8);
    setDrag({ from: c, piece: glyph });
    requestAnimationFrame(() => positionGhost(e.clientX, e.clientY));
  };

  useEffect(() => {
    if (!drag) return;
    let hasDraggedFar = false;

    const onMove = (e: PointerEvent) => {
      const press = pressRef.current;
      if (!press) return;
      if (Math.abs(e.clientX - press.startX) > 5 || Math.abs(e.clientY - press.startY) > 5) {
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
        if (target && !(target[0] === press.coord[0] && target[1] === press.coord[1]) && tryPlay(press.coord, target)) {
          return;
        }
        setSelected(null);
        return;
      }
      if (press.wasSelected && target && target[0] === press.coord[0] && target[1] === press.coord[1]) {
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

  const lastTint =
    lastMoveClass && CLASS_TINTS[lastMoveClass]
      ? CLASS_TINTS[lastMoveClass]
      : isBranching
      ? 'rgba(139, 92, 246, 0.45)'
      : currentTheme.lastMoveTo;

  const displayEvalBar = lens.evalBar && (showEvalBar ?? (winChance !== undefined || scoreCp !== undefined || mate !== undefined));
  const shouldShowLines = showEngineLines ?? ((topLines ?? []).length > 0 || isBranching);
  const shouldShowHints = showHints ?? lens.hints;

  return (
    <div className={`glass-panel rounded-3xl p-3.5 md:p-5 shadow-artisan w-full ${className || ''}`}>
      {/* Keyframe styles for GPU Piece Gliding */}
      <style>{`
        @keyframes glideLinear {
          0% { transform: translate(var(--glide-start-x), var(--glide-start-y)); }
          100% { transform: translate(0, 0); }
        }
        @keyframes glideKnightHop {
          0% { transform: translate(var(--glide-start-x), var(--glide-start-y)) scale(1); }
          50% { transform: translate(calc(var(--glide-start-x) * 0.5), calc(var(--glide-start-y) * 0.5)) scale(1.15); }
          100% { transform: translate(0, 0) scale(1); }
        }
      `}</style>

      {/* Studio Header Bar */}
      {!hideHeader && (
        <div className="flex items-center justify-between mb-3.5">
          <div className="flex items-center gap-2.5">
            {headerTitle ? (
              typeof headerTitle === 'string' ? (
                <h3 className="text-sm font-bold font-display text-white tracking-wide">{headerTitle}</h3>
              ) : (
                headerTitle
              )
            ) : (
              <h3 className="text-sm font-bold font-display text-white tracking-wide">Artisan Board</h3>
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
                onClick={handleOrientationToggle}
                title="Flip board orientation"
                className="px-2.5 py-1 text-[11px] font-bold font-mono rounded-lg bg-slate-800/90 border border-slate-700/80 text-slate-200 hover:text-amber-400 hover:border-amber-500/50 transition-all active:scale-95"
              >
                {flipped ? 'Black ▼' : 'White ▲'}
              </button>
            )}
            {showThemeToggle !== false && (
              <button
                onClick={cycleTheme}
                title="Cycle Artisan Theme"
                className="px-2.5 py-1 text-[11px] font-bold font-mono rounded-lg bg-slate-800/90 border border-slate-700/80 text-slate-200 hover:text-amber-400 hover:border-amber-500/50 transition-all active:scale-95"
              >
                {currentTheme.label.split(' ')[0]}
              </button>
            )}
            {headerRight}
          </div>
        </div>
      )}

      {topBar && <div className="mb-3">{topBar}</div>}

      {/* Main Board Layout: Generous Chessboard Stage & Eval Bar */}
      <div className="w-full flex flex-col gap-3">
        <div className="w-full flex items-stretch justify-center gap-3">
          {displayEvalBar && (
            <EvalBar
              winChance={winChance}
              scoreCp={scoreCp}
              mate={mate}
              flipped={flipped}
              isComputing={isComputing || isLoading}
            />
          )}

          <div className="relative flex-1 w-full max-w-[700px]">
            {/* Live Stockfish Computing Floating HUD Badge */}
            {(isComputing || isLoading) && (
              <div className="absolute top-2.5 left-2.5 z-[20] flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-950/85 backdrop-blur-md border border-violet-500/50 shadow-[0_0_16px_rgba(139,92,246,0.35)] text-violet-300 text-xs font-mono font-bold animate-in fade-in zoom-in duration-200 pointer-events-none select-none">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500" />
                </span>
                <Brain size={13} className="text-violet-400 animate-pulse" />
                <span className="tracking-wide">Stockfish 17 Computing</span>
                <div className="flex items-center gap-0.5 ml-0.5">
                  <span className="w-1 h-1 bg-violet-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
                  <span className="w-1 h-1 bg-violet-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                  <span className="w-1 h-1 bg-violet-400 rounded-full animate-bounce" />
                </div>
              </div>
            )}

            {/* LED Bezel Twin Perimeter Simulator */}
            {lens.ledBezel && (
              <LedBezelTwin
                lastMoveUci={lastMoveUci}
                inCheck={inCheck}
                activeAnimation={activeAnimation}
                ledIntensity={ledIntensity}
                flipped={flipped}
              />
            )}

            {/* Chessboard Grid */}
            <div
              ref={boardRef}
              className="grid w-full aspect-square rounded-xl overflow-hidden select-none relative"
              style={{
                gridTemplateColumns: 'repeat(8, minmax(0, 1fr))',
                gridTemplateRows: 'repeat(8, minmax(0, 1fr))',
                touchAction: 'none',
                boxShadow: `0 15px 35px -8px rgba(0,0,0,0.8), 0 0 0 8px ${currentTheme.frame}, 0 0 0 9px rgba(255,255,255,0.08)`,
              }}
              onContextMenu={(e) => e.preventDefault()}
            >
              {Array.from({ length: 64 }).map((_, idx) => {
                const rowFromTop = Math.floor(idx / 8);
                const col = idx % 8;
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

                const captured = capturedGhostSquare(prevGridState.prev, grid, lastHighlight, [file, rank], piece);
                const isMissingStarting = missingSquaresSet.has(`${file},${rank}`);
                const isMisplaced = misplacedSquaresSet.has(`${file},${rank}`);
                const isGlidingTarget = isTargetOfActiveGlide(file, rank);

                return (
                  <div
                    key={idx}
                    onPointerDown={(e) => handlePointerDown(e, c)}
                    className="relative flex items-center justify-center transition-colors duration-150"
                    style={{
                      backgroundColor: isDark ? currentTheme.dark : currentTheme.light,
                      cursor: isOwnTurnPiece(piece, c) || isTarget ? 'pointer' : 'default',
                      boxShadow: isCheckedKing ? `inset 0 0 16px 5px ${currentTheme.checkGlow}` : undefined,
                    }}
                  >
                    {(isLastFrom || isLastTo) && (
                      <div className="absolute inset-0 transition-colors duration-200" style={{ backgroundColor: lastTint }} />
                    )}
                    {isSelected && (
                      <div className="absolute inset-0 bg-blue-500/35 border-2 border-blue-400" />
                    )}

                    {isMisplaced && (
                      <div className="absolute inset-0.5 rounded-lg border-2 border-amber-400 bg-amber-500/25 z-[6] pointer-events-none shadow-[0_0_12px_rgba(245,158,11,0.65)] flex items-center justify-center animate-pulse">
                        <div className="w-2.5 h-2.5 rounded-full bg-amber-400 border border-amber-200" />
                      </div>
                    )}
                    {isMissingStarting && (
                      <div className="absolute inset-0.5 rounded-lg border-2 border-dashed border-rose-400 bg-rose-500/20 z-[6] pointer-events-none flex items-center justify-center animate-pulse">
                        <span className="text-[10px] text-rose-300 font-bold">!</span>
                      </div>
                    )}

                    {/* Move Target Indicators */}
                    {isTarget && (
                      <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-[7]">
                        {isTargetCapture || piece ? (
                          <div className="w-full h-full border-4 border-emerald-400/80 rounded-full scale-90 animate-pulse" />
                        ) : (
                          <div
                            className={`w-3.5 h-3.5 rounded-full ${
                              destQualities?.get(squareName) === 'blunder'
                                ? 'bg-rose-500 shadow-[0_0_8px_#f43f5e]'
                                : destQualities?.get(squareName) === 'best'
                                ? 'bg-emerald-400 shadow-[0_0_8px_#34d399]'
                                : 'bg-slate-900/40 border-2 border-white/60'
                            }`}
                          />
                        )}
                      </div>
                    )}

                    {/* Render Piece on Square (Masked during active glide to prevent ghosting) */}
                    {piece && (
                      <div
                        className={`relative w-full h-full flex items-center justify-center z-[5] transition-transform duration-200 ease-out ${
                          isDragOrigin
                            ? 'opacity-25 scale-95'
                            : isGlidingTarget
                            ? 'opacity-0'
                            : 'hover:scale-105'
                        }`}
                      >
                        <img
                          src={PIECE_IMAGES[piece]}
                          alt={piece}
                          draggable={false}
                          className="w-[84%] h-[84%] object-contain filter drop-shadow-[0_4px_6px_rgba(0,0,0,0.45)] pointer-events-none select-none"
                        />
                      </div>
                    )}

                    {/* Captured Piece Fade Ghost */}
                    {captured && (
                      <div className="absolute inset-0 flex items-center justify-center z-[4] pointer-events-none opacity-40 filter grayscale">
                        <img src={PIECE_IMAGES[captured]} alt={captured} className="w-[75%] h-[75%] object-contain" />
                      </div>
                    )}

                    {/* Rank & File Coordinate Labels */}
                    {isLeftEdge && (
                      <span
                        className="absolute top-0.5 left-1 text-[10px] font-bold font-mono pointer-events-none select-none"
                        style={{ color: isDark ? currentTheme.darkText : currentTheme.lightText, opacity: 0.75 }}
                      >
                        {rank + 1}
                      </span>
                    )}
                    {isBottomEdge && (
                      <span
                        className="absolute bottom-0.5 right-1 text-[10px] font-bold font-mono pointer-events-none select-none"
                        style={{ color: isDark ? currentTheme.darkText : currentTheme.lightText, opacity: 0.75 }}
                      >
                        {FILES[file]}
                      </span>
                    )}

                    {/* Custom Square Overlay */}
                    {renderSquareOverlay && renderSquareOverlay(c, squareName)}
                  </div>
                );
              })}

              {/* Distance-Aware Piece Gliding Animation Layer */}
              {glideState.glides.map((anim) => {
                const fromCol = flipped ? 7 - anim.from[0] : anim.from[0];
                const fromRow = flipped ? anim.from[1] : 7 - anim.from[1];
                const toCol = flipped ? 7 - anim.to[0] : anim.to[0];
                const toRow = flipped ? anim.to[1] : 7 - anim.to[1];

                const deltaXPercent = (fromCol - toCol) * 100;
                const deltaYPercent = (fromRow - toRow) * 100;

                return (
                  <div
                    key={anim.id}
                    className="absolute z-[15] pointer-events-none flex items-center justify-center will-change-transform"
                    style={{
                      left: `${toCol * 12.5}%`,
                      top: `${toRow * 12.5}%`,
                      width: '12.5%',
                      height: '12.5%',
                      animation: anim.isKnight
                        ? `glideKnightHop ${anim.duration}ms cubic-bezier(0.25, 1, 0.5, 1) forwards`
                        : `glideLinear ${anim.duration}ms cubic-bezier(0.2, 0, 0.2, 1) forwards`,
                      ['--glide-start-x' as string]: `${deltaXPercent}%`,
                      ['--glide-start-y' as string]: `${deltaYPercent}%`,
                    }}
                  >
                    <img
                      src={PIECE_IMAGES[anim.piece]}
                      alt={anim.piece}
                      draggable={false}
                      className="w-[84%] h-[84%] object-contain filter drop-shadow-[0_6px_10px_rgba(0,0,0,0.5)] pointer-events-none select-none"
                    />
                  </div>
                );
              })}

              {/* Whole-Board Overlays (Physical Sensor Matrix / Magnetic Aura Lens) */}
              {lens.aura && (
                <MagneticAuraOverlay
                  adcGrid={adcGrid}
                  baselines={baselines}
                  liftedSquare={liftedSquare}
                  resignationArmed={resignationArmed}
                  kingLiftElapsed={kingLiftElapsed}
                  flipped={flipped}
                />
              )}

              {boardOverlay && (typeof boardOverlay === 'function' ? boardOverlay(flipped) : boardOverlay)}

              {/* Suggestion Engine Arrow */}
              {suggestArrow && (
                <svg
                  className="absolute inset-0 w-full h-full pointer-events-none z-[10]"
                  viewBox="0 0 800 800"
                  onClick={onSuggestionClick}
                >
                  <defs>
                    <marker
                      id="arrowhead-suggest"
                      markerWidth="6"
                      markerHeight="6"
                      refX="4"
                      refY="3"
                      orient="auto"
                    >
                      <polygon points="0 0, 6 3, 0 6" fill="#10b981" />
                    </marker>
                  </defs>
                  {(() => {
                    const fCol = flipped ? 7 - suggestArrow.from[0] : suggestArrow.from[0];
                    const fRow = flipped ? suggestArrow.from[1] : 7 - suggestArrow.from[1];
                    const tCol = flipped ? 7 - suggestArrow.to[0] : suggestArrow.to[0];
                    const tRow = flipped ? suggestArrow.to[1] : 7 - suggestArrow.to[1];

                    const x1 = fCol * 100 + 50;
                    const y1 = fRow * 100 + 50;
                    const x2 = tCol * 100 + 50;
                    const y2 = tRow * 100 + 50;

                    return (
                      <line
                        x1={x1}
                        y1={y1}
                        x2={x2}
                        y2={y2}
                        stroke="#10b981"
                        strokeWidth="10"
                        strokeLinecap="round"
                        opacity="0.8"
                        markerEnd="url(#arrowhead-suggest)"
                      />
                    );
                  })()}
                </svg>
              )}
            </div>
          </div>
        </div>

        {/* Engine Top Multi-PV Lines Panel Structured Below Board */}
        {shouldShowLines && (
          <div className="w-full flex flex-col gap-2 p-3 rounded-2xl bg-slate-900/80 border border-slate-800 shadow-inner">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 font-mono flex items-center gap-1.5">
                <Brain size={12} className="text-violet-400" />
                Engine Lines (Multi-PV)
              </span>
              {(isComputing || isLoading) && (
                <span className="text-[9px] font-mono text-violet-400 font-bold px-2 py-0.5 rounded-full bg-violet-500/10 border border-violet-500/30 flex items-center gap-1 animate-pulse">
                  <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-ping" />
                  Calculating lines...
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {topLines && topLines.length > 0 ? (
                topLines.map((line, idx) => {
                  const scoreStr =
                    line.mate !== null
                      ? `M${line.mate}`
                      : line.score_cp !== null
                      ? `${line.score_cp >= 0 ? '+' : ''}${(line.score_cp / 100).toFixed(1)}`
                      : '0.0';

                  return (
                    <button
                      key={idx}
                      onClick={() => onLineClick && onLineClick(idx)}
                      className="flex flex-col text-left p-2.5 rounded-xl bg-slate-950/70 hover:bg-slate-800/80 border border-slate-800/80 hover:border-violet-500/40 transition-all text-xs group active:scale-[0.98]"
                    >
                      <div className="flex items-center justify-between text-[11px] font-bold font-mono mb-1">
                        <span className="text-amber-400 group-hover:text-amber-300">Line {idx + 1}</span>
                        <span className="text-emerald-400 font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20">{scoreStr}</span>
                      </div>
                      <span className="text-[10px] text-slate-300 font-mono truncate">
                        {line.san?.join(' ') || line.uci?.join(' ') || '...'}
                      </span>
                    </button>
                  );
                })
              ) : isComputing || isLoading ? (
                // Shimmering Skeleton Rows during computation
                [1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="p-2.5 rounded-xl bg-slate-950/40 border border-slate-800/50 flex flex-col gap-1.5 animate-pulse"
                  >
                    <div className="flex items-center justify-between">
                      <div className="h-3 w-12 bg-slate-800 rounded" />
                      <div className="h-3 w-8 bg-slate-800 rounded" />
                    </div>
                    <div className="h-2.5 w-full bg-slate-800/60 rounded" />
                  </div>
                ))
              ) : (
                <div className="col-span-3 text-center py-2 text-[11px] font-mono text-slate-500">
                  No engine lines available
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {bottomBar && <div className="mt-3">{bottomBar}</div>}

      {/* Usage Hints */}
      {shouldShowHints && (
        <div className="mt-3 flex items-center justify-between text-[10px] text-slate-400 font-mono px-2">
          <span>Click / Drag to play • Arrow keys for move tree</span>
          <span>Theme: {currentTheme.label}</span>
        </div>
      )}

      {/* Floating Drag Ghost */}
      {drag && (
        <div
          ref={ghostRef}
          className="fixed pointer-events-none z-[100] left-0 top-0 will-change-transform"
          style={{ width: `${ghostSize}px`, height: `${ghostSize}px` }}
        >
          <img
            src={PIECE_IMAGES[drag.piece]}
            alt={drag.piece}
            className="w-full h-full object-contain filter drop-shadow-[0_8px_16px_rgba(0,0,0,0.6)] scale-110"
          />
        </div>
      )}

      {/* Promotion Dialog Modal */}
      {promotion && (
        <div className="fixed inset-0 z-[150] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-panel p-6 rounded-3xl max-w-xs w-full flex flex-col items-center gap-4 text-center border-amber-500/40 shadow-artisan-lg animate-in fade-in zoom-in duration-200">
            <h4 className="text-base font-bold font-display text-white">Promote Pawn</h4>
            <div className="grid grid-cols-4 gap-2 w-full">
              {['q', 'r', 'b', 'n'].map((p) => {
                const pieceGlyph = promotion.color === 'white' ? p.toUpperCase() : p;
                return (
                  <button
                    key={p}
                    onClick={() => {
                      const uci = `${coordToSquareName(promotion.from)}${coordToSquareName(promotion.to)}${p}`;
                      setPromotion(null);
                      if (onMovePlayed) onMovePlayed(uci);
                    }}
                    className="p-3 bg-slate-900/80 hover:bg-amber-500/20 border border-slate-700 hover:border-amber-400/80 rounded-2xl flex items-center justify-center transition-all hover:scale-105 active:scale-95"
                  >
                    <img src={PIECE_IMAGES[pieceGlyph]} alt={p} className="w-10 h-10 object-contain drop-shadow" />
                  </button>
                );
              })}
            </div>
            <button
              onClick={() => setPromotion(null)}
              className="text-xs text-slate-400 hover:text-white font-mono"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default WebAnalysisBoard;
