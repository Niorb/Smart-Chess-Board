import wK from '../../assets/pieces/wK.svg';
import wQ from '../../assets/pieces/wQ.svg';
import wR from '../../assets/pieces/wR.svg';
import wB from '../../assets/pieces/wB.svg';
import wN from '../../assets/pieces/wN.svg';
import wP from '../../assets/pieces/wP.svg';
import bK from '../../assets/pieces/bK.svg';
import bQ from '../../assets/pieces/bQ.svg';
import bR from '../../assets/pieces/bR.svg';
import bB from '../../assets/pieces/bB.svg';
import bN from '../../assets/pieces/bN.svg';
import bP from '../../assets/pieces/bP.svg';

export interface EngineLineProp {
  uci: string[];
  san: string[];
  score_cp: number | null;
  mate: number | null;
}

export type Coord = [number, number]; // [file 0-7, rank 0-7]

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

export const CLASS_TINTS: Record<string, string> = {
  best: 'rgba(16, 185, 129, 0.55)',
  good: 'rgba(6, 182, 212, 0.45)',
  book: 'rgba(148, 163, 184, 0.45)',
  inaccuracy: 'rgba(245, 158, 11, 0.55)',
  mistake: 'rgba(249, 115, 22, 0.58)',
  blunder: 'rgba(244, 63, 94, 0.65)',
};

export const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];

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

export function capturedGhostSquare(
  prevGrid: string[][] | null,
  grid: string[][],
  lastHighlight: { from: Coord; to: Coord } | null,
  sq: Coord,
  pieceNow: string,
): string {
  if (!prevGrid || !lastHighlight) return '';
  if (sq[0] === lastHighlight.to[0] && sq[1] === lastHighlight.to[1]) return '';
  const before = prevGrid[sq[1]]?.[sq[0]] ?? '';
  const after = pieceNow;
  if (!before || after === before) return '';
  const mover = grid[lastHighlight.to[1]]?.[lastHighlight.to[0]] ?? '';
  if (!mover) return '';
  const moverIsWhite = mover === mover.toUpperCase();
  const victimIsWhite = before === before.toUpperCase();
  if (moverIsWhite === victimIsWhite) return '';
  return before;
}
