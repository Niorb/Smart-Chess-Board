const API_BASE = `http://${window.location.hostname || 'localhost'}:8000/api`;

export interface LichessAccount {
  username: string;
  rating: number;
  title?: string | null;
  online: boolean;
  authenticated: boolean;
  perfs?: {
    rapid?: number;
    blitz?: number;
    bullet?: number;
  };
  error?: string;
}

export async function getLichessAccount(): Promise<LichessAccount> {
  const response = await fetch(`${API_BASE}/lichess/account`);
  return response.json();
}

export async function seekGame(options?: {
  timeControl?: string;
  increment?: number;
  rated?: boolean;
  color?: string;
  opponent?: 'auto' | 'ai' | 'human';
  aiLevel?: number;
  ratingRange?: string;
}) {
  const response = await fetch(`${API_BASE}/game/seek`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      time_control: options?.timeControl ?? '10+0',
      increment: options?.increment ?? 0,
      rated: options?.rated ?? false,
      color: options?.color ?? 'random',
      opponent: options?.opponent ?? 'auto',
      ai_level: options?.aiLevel ?? 3,
      rating_range: options?.ratingRange,
    }),
  });
  return response.json();
}

export async function cancelGame() {
  const response = await fetch(`${API_BASE}/game/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return response.json();
}

export async function resignGame() {
  const response = await fetch(`${API_BASE}/game/resign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return response.json();
}

export async function offerDraw(accept: boolean = true) {
  const response = await fetch(`${API_BASE}/game/draw`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ accept }),
  });
  return response.json();
}

export async function makeMove(fromSquare: string, toSquare: string, promotion?: string) {
  const response = await fetch(`${API_BASE}/game/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from_square: fromSquare,
      to_square: toSquare,
      promotion: promotion ?? null,
    }),
  });
  return response.json();
}

export async function setGameMode(virtualOnly: boolean) {
  const response = await fetch(`${API_BASE}/game/mode`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ virtual_only: virtualOnly }),
  });
  return response.json();
}

export async function getBoardSettings() {
  const response = await fetch(`${API_BASE}/board/settings`);
  return response.json();
}

export async function updateBoardSettings(
  positive?: number | null,
  negative?: number | null,
  colMode?: 'auto' | 'manual',
  manualCol?: number,
  scanDelay?: number,
  muxSettleMs?: number,
  debounceThreshold?: number,
  baselineWindowS?: number,
  disabledSquares?: number[][],
  piecesMode?: 'auto' | 'pieces' | 'empty'
) {
  const body: Record<string, unknown> = {};
  if (positive !== undefined && positive !== null && !isNaN(positive)) body.threshold_positive = positive;
  if (negative !== undefined && negative !== null && !isNaN(negative)) body.threshold_negative = negative;
  if (colMode !== undefined && colMode !== null) body.col_mode = colMode;
  if (manualCol !== undefined && manualCol !== null) body.manual_col = manualCol;
  if (scanDelay !== undefined && scanDelay !== null) body.scan_delay = scanDelay;
  if (muxSettleMs !== undefined && muxSettleMs !== null) body.mux_settle_ms = muxSettleMs;
  if (debounceThreshold !== undefined && debounceThreshold !== null) body.debounce_threshold = debounceThreshold;
  if (baselineWindowS !== undefined && baselineWindowS !== null) body.baseline_window_s = baselineWindowS;
  if (disabledSquares !== undefined && disabledSquares !== null) body.disabled_squares = disabledSquares;
  if (piecesMode !== undefined && piecesMode !== null) body.pieces_mode = piecesMode;

  const response = await fetch(`${API_BASE}/board/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return response.json();
}

export async function calibrateBoard() {
  const response = await fetch(`${API_BASE}/board/calibrate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return response.json();
}

export async function calibrateBoardWithPieces() {
  const response = await fetch(`${API_BASE}/board/calibrate_with_pieces`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return response.json();
}

export async function highlightSquare(col: number, row: number) {
  const response = await fetch(`${API_BASE}/board/highlight`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ col, row }),
  });
  return response.json();
}

export async function testLeds() {
  const response = await fetch(`${API_BASE}/board/test_leds`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return response.json();
}

export async function clearAllLeds() {
  const response = await fetch(`${API_BASE}/board/clear_leds`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return response.json();
}

export async function triggerAnimation(name: string, params?: Record<string, unknown>) {
  const response = await fetch(`${API_BASE}/leds/trigger_animation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, params }),
  });
  return response.json();
}

export async function testMoveTrace(options: {
  uci?: string;
  from_pos?: [number, number];
  to_pos?: [number, number];
  clear?: boolean;
}) {
  const response = await fetch(`${API_BASE}/leds/test_trace`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options),
  });
  return response.json();
}

