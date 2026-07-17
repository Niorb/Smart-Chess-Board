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
  positive: number,
  negative: number,
  rowMode?: 'auto' | 'manual',
  manualRow?: number,
  scanDelay?: number,
  muxSettleMs?: number,
  debounceThreshold?: number,
  baselineWindowS?: number,
  disabledSquares?: number[][]
) {
  const response = await fetch(`${API_BASE}/board/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      threshold_positive: positive,
      threshold_negative: negative,
      row_mode: rowMode,
      manual_row: manualRow,
      scan_delay: scanDelay,
      mux_settle_ms: muxSettleMs,
      debounce_threshold: debounceThreshold,
      baseline_window_s: baselineWindowS,
      disabled_squares: disabledSquares,
    }),
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

export async function highlightSquare(row: number, col: number) {
  const response = await fetch(`${API_BASE}/board/highlight`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ row, col }),
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
