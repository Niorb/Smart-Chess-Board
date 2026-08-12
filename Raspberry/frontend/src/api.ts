const API_BASE = `http://${window.location.hostname || 'localhost'}:8000/api`;

export async function seekGame(timeControl?: string) {
  const response = await fetch(`${API_BASE}/game/seek`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ time_control: timeControl }),
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
  disabledSquares?: number[][]
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

export async function makeMove(fromSquare: string, toSquare: string) {
  const response = await fetch(`${API_BASE}/game/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from_square: fromSquare, to_square: toSquare }),
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
