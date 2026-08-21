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

export async function claimVictory() {
  const response = await fetch(`${API_BASE}/lichess/claim-victory`, {
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

export interface BoardSettingsOptions {
  threshold_positive?: number | null;
  threshold_negative?: number | null;
  col_mode?: 'auto' | 'manual';
  manual_col?: number;
  scan_delay?: number;
  mux_settle_ms?: number;
  mux_settle_us?: number;
  debounce_threshold?: number;
  baseline_window_s?: number;
  disabled_squares?: number[][];
  pieces_mode?: 'auto' | 'pieces' | 'empty';
  coach_hints_enabled?: boolean;
  eval_bar_enabled?: boolean;
  coach_ai_only?: boolean;
  in_loop_calibration?: boolean;
  led_intensity?: number;
  night_mode?: boolean;
  baselines?: number[][];
}

export async function updateBoardSettings(
  positiveOrOptions?: number | BoardSettingsOptions | null,
  negative?: number | null,
  colMode?: 'auto' | 'manual',
  manualCol?: number,
  scanDelay?: number,
  muxSettleMs?: number,
  debounceThreshold?: number,
  baselineWindowS?: number,
  disabledSquares?: number[][],
  piecesMode?: 'auto' | 'pieces' | 'empty',
  coachHintsEnabled?: boolean,
  evalBarEnabled?: boolean,
  coachAiOnly?: boolean,
  inLoopCalibration?: boolean,
  ledIntensity?: number,
  nightMode?: boolean
) {
  let body: Record<string, unknown> = {};
  if (positiveOrOptions && typeof positiveOrOptions === 'object') {
    body = { ...positiveOrOptions };
  } else {
    if (positiveOrOptions !== undefined && positiveOrOptions !== null && !isNaN(positiveOrOptions)) body.threshold_positive = positiveOrOptions;
    if (negative !== undefined && negative !== null && !isNaN(negative)) body.threshold_negative = negative;
    if (colMode !== undefined && colMode !== null) body.col_mode = colMode;
    if (manualCol !== undefined && manualCol !== null) body.manual_col = manualCol;
    if (scanDelay !== undefined && scanDelay !== null) body.scan_delay = scanDelay;
    if (muxSettleMs !== undefined && muxSettleMs !== null) {
      body.mux_settle_ms = muxSettleMs;
      body.mux_settle_us = muxSettleMs > 50 ? muxSettleMs : muxSettleMs * 1000;
    }
    if (debounceThreshold !== undefined && debounceThreshold !== null) body.debounce_threshold = debounceThreshold;
    if (baselineWindowS !== undefined && baselineWindowS !== null) body.baseline_window_s = baselineWindowS;
    if (disabledSquares !== undefined && disabledSquares !== null) body.disabled_squares = disabledSquares;
    if (piecesMode !== undefined && piecesMode !== null) body.pieces_mode = piecesMode;
    if (coachHintsEnabled !== undefined) body.coach_hints_enabled = coachHintsEnabled;
    if (evalBarEnabled !== undefined) body.eval_bar_enabled = evalBarEnabled;
    if (coachAiOnly !== undefined) body.coach_ai_only = coachAiOnly;
    if (inLoopCalibration !== undefined) body.in_loop_calibration = inLoopCalibration;
    if (ledIntensity !== undefined && ledIntensity !== null && !isNaN(ledIntensity)) body.led_intensity = ledIntensity;
    if (nightMode !== undefined) body.night_mode = nightMode;
  }

  const response = await fetch(`${API_BASE}/board/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return response.json();
}

export async function saveBoardDefaults(options?: {
  positive?: number | null;
  negative?: number | null;
  colMode?: 'auto' | 'manual';
  manualCol?: number;
  scanDelay?: number;
  muxSettleMs?: number;
  debounceThreshold?: number;
  baselineWindowS?: number;
  disabledSquares?: number[][];
  piecesMode?: 'auto' | 'pieces' | 'empty';
  coachHintsEnabled?: boolean;
  evalBarEnabled?: boolean;
  coachAiOnly?: boolean;
  inLoopCalibration?: boolean;
  ledIntensity?: number;
  nightMode?: boolean;
  baselines?: number[][];
}) {
  const body: Record<string, unknown> = {};
  if (options?.positive !== undefined && options?.positive !== null && !isNaN(options.positive)) body.threshold_positive = options.positive;
  if (options?.negative !== undefined && options?.negative !== null && !isNaN(options.negative)) body.threshold_negative = options.negative;
  if (options?.colMode !== undefined && options?.colMode !== null) body.col_mode = options.colMode;
  if (options?.manualCol !== undefined && options?.manualCol !== null) body.manual_col = options.manualCol;
  if (options?.scanDelay !== undefined && options?.scanDelay !== null) body.scan_delay = options.scanDelay;
  if (options?.muxSettleMs !== undefined && options?.muxSettleMs !== null) body.mux_settle_ms = options.muxSettleMs;
  if (options?.debounceThreshold !== undefined && options?.debounceThreshold !== null) body.debounce_threshold = options.debounceThreshold;
  if (options?.baselineWindowS !== undefined && options?.baselineWindowS !== null) body.baseline_window_s = options.baselineWindowS;
  if (options?.disabledSquares !== undefined && options?.disabledSquares !== null) body.disabled_squares = options.disabledSquares;
  if (options?.piecesMode !== undefined && options?.piecesMode !== null) body.pieces_mode = options.piecesMode;
  if (options?.coachHintsEnabled !== undefined) body.coach_hints_enabled = options.coachHintsEnabled;
  if (options?.evalBarEnabled !== undefined) body.eval_bar_enabled = options.evalBarEnabled;
  if (options?.coachAiOnly !== undefined) body.coach_ai_only = options.coachAiOnly;
  if (options?.inLoopCalibration !== undefined) body.in_loop_calibration = options.inLoopCalibration;
  if (options?.ledIntensity !== undefined && options?.ledIntensity !== null && !isNaN(options.ledIntensity)) body.led_intensity = options.ledIntensity;
  if (options?.nightMode !== undefined) body.night_mode = options.nightMode;
  if (options?.baselines !== undefined && options?.baselines !== null) body.baselines = options.baselines;

  const response = await fetch(`${API_BASE}/board/save_defaults`, {
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

export async function calibrateSquare(col: number, row: number, value?: number) {
  const body: { col: number; row: number; value?: number } = { col, row };
  if (value !== undefined && value !== null) {
    body.value = value;
  }
  const response = await fetch(`${API_BASE}/board/calibrate_square`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
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
  is_capture?: boolean;
  clear?: boolean;
}) {
  const response = await fetch(`${API_BASE}/leds/test_trace`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options),
  });
  return response.json();
}

export interface LastGameParams {
  time_control?: string;
  increment?: number;
  rated?: boolean;
  color?: string;
  opponent?: 'auto' | 'ai' | 'human';
  ai_level?: number;
  rating_range?: string | null;
}

export async function getLastGameParams(): Promise<{ status: string; last_game_params: LastGameParams | null }> {
  const response = await fetch(`${API_BASE}/game/last_params`);
  return response.json();
}

export async function restartPreviousGame() {
  const response = await fetch(`${API_BASE}/game/restart_previous`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return response.json();
}

// --- Post-Game Analysis & Training API ---

export async function startAnalysis(options?: { moves_uci?: string[]; game_id?: string }) {
  const response = await fetch(`${API_BASE}/analysis/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options || {}),
  });
  return response.json();
}

export async function stepAnalysis(ply: number) {
  const response = await fetch(`${API_BASE}/analysis/step`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ply }),
  });
  return response.json();
}

export async function resetAnalysisBranch() {
  const response = await fetch(`${API_BASE}/analysis/branch_reset`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return response.json();
}

export async function stopAnalysis() {
  const response = await fetch(`${API_BASE}/analysis/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return response.json();
}

export async function getAnalysisState() {
  const response = await fetch(`${API_BASE}/analysis/state`);
  return response.json();
}

export async function getGMGames() {
  const response = await fetch(`${API_BASE}/analysis/gm/games`);
  return response.json();
}

export async function startGMGame(gameId: string) {
  const response = await fetch(`${API_BASE}/analysis/gm/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ game_id: gameId }),
  });
  return response.json();
}

export async function submitGMGuess(uci: string) {
  const response = await fetch(`${API_BASE}/analysis/gm/guess`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uci }),
  });
  return response.json();
}

export async function startBlunderDrill(index: number = 0) {
  const response = await fetch(`${API_BASE}/analysis/blunder_drill/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ index }),
  });
  return response.json();
}

export async function submitBlunderAttempt(uci: string) {
  const response = await fetch(`${API_BASE}/analysis/blunder_drill/attempt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uci }),
  });
  return response.json();
}

export async function toggleBlunderHint() {
  const response = await fetch(`${API_BASE}/analysis/blunder_drill/hint`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return response.json();
}

