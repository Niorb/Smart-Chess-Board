const API_BASE = '/api';

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

const DEFAULT_TIMEOUT_MS = 8000;

async function request<T = Record<string, unknown>>(
  path: string,
  init?: RequestInit & { timeoutMs?: number },
): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchInit } = init ?? {};
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...fetchInit,
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (err) {
    if (err instanceof Error && err.name === 'TimeoutError') {
      throw new ApiError(0, `Request to ${path} timed out after ${timeoutMs}ms`);
    }
    throw err;
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.message) detail = String(body.message);
      else if (body?.detail) detail = String(body.detail);
    } catch {
      // non-JSON error body
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

function jsonPost<T = Record<string, unknown>>(
  path: string,
  body?: unknown,
  timeoutMs?: number,
): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    timeoutMs,
  });
}

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

export interface LichessRecentGame {
  id: string;
  url: string;
  user_color: 'white' | 'black';
  user_rating?: number;
  opponent: {
    username: string;
    rating?: number | null;
    title?: string | null;
    is_ai: boolean;
  };
  result: 'win' | 'loss' | 'draw';
  winner: 'white' | 'black' | null;
  end_reason: string;
  created_at?: number;
  speed: string;
  time_control: string;
  rated: boolean;
  opening: {
    name: string;
    eco: string;
  };
  moves_count: number;
  total_plys: number;
  moves_uci: string[];
  moves_san: string;
}

export async function getLichessAccount(): Promise<LichessAccount> {
  return request<LichessAccount>('/lichess/account');
}

export async function getRecentLichessGames(
  maxGames: number = 10,
): Promise<{ status: string; games: LichessRecentGame[] }> {
  return request(`/lichess/games/recent?max_games=${maxGames}`);
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
  return jsonPost('/game/seek', {
    time_control: options?.timeControl ?? '10+0',
    increment: options?.increment ?? 0,
    rated: options?.rated ?? false,
    color: options?.color ?? 'random',
    opponent: options?.opponent ?? 'auto',
    ai_level: options?.aiLevel ?? 3,
    rating_range: options?.ratingRange,
  });
}

export async function cancelGame() {
  return jsonPost('/game/cancel');
}

export async function resignGame() {
  return jsonPost('/game/resign');
}

export async function claimVictory() {
  return jsonPost('/lichess/claim-victory');
}

export async function offerDraw(accept: boolean = true) {
  return jsonPost('/game/draw', { accept });
}

export async function startLocalGame(fen?: string) {
  return jsonPost('/game/local/start', { fen: fen ?? null });
}

export async function stopLocalGame(winner?: string, reason?: string) {
  return jsonPost('/game/local/stop', { winner: winner ?? null, reason: reason ?? 'resignation' });
}

export async function makeMove(fromSquare: string, toSquare: string, promotion?: string) {
  return jsonPost('/game/move', {
    from_square: fromSquare,
    to_square: toSquare,
    promotion: promotion ?? null,
  });
}

export async function setGameMode(virtualOnly: boolean) {
  return jsonPost('/game/mode', { virtual_only: virtualOnly });
}

export async function getBoardSettings(): Promise<BoardSettings> {
  return request('/board/settings', { timeoutMs: 15000 });
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
  clock_bar_enabled?: boolean;
  opening_hints_enabled?: boolean;
  coach_ai_only?: boolean;
  in_loop_calibration?: boolean;
  led_intensity?: number;
  night_mode?: boolean;
  baselines?: number[][];
}

export async function updateBoardSettings(options: BoardSettingsOptions = {}): Promise<SettingsResponse> {
  return jsonPost<SettingsResponse>('/board/settings', options);
}

export async function saveBoardDefaults(options: BoardSettingsOptions = {}): Promise<SettingsResponse> {
  return jsonPost<SettingsResponse>('/board/save_defaults', options, 15000);
}

export async function calibrateBoard(): Promise<SettingsResponse> {
  return jsonPost<SettingsResponse>('/board/calibrate', undefined, 30000);
}

export async function calibrateBoardWithPieces(): Promise<SettingsResponse> {
  return jsonPost<SettingsResponse>('/board/calibrate_with_pieces', undefined, 30000);
}

export async function calibrateSquare(
  col: number,
  row: number,
  value?: number,
): Promise<SettingsResponse & { col?: number; row?: number; baseline?: number }> {
  const body: { col: number; row: number; value?: number } = { col, row };
  if (value !== undefined && value !== null) {
    body.value = value;
  }
  return jsonPost<SettingsResponse & { col?: number; row?: number; baseline?: number }>('/board/calibrate_square', body);
}

export async function testLeds() {
  return jsonPost('/board/test_leds');
}

export async function clearAllLeds() {
  return jsonPost('/board/clear_leds');
}

export async function triggerAnimation(name: string, params?: Record<string, unknown>) {
  return jsonPost('/leds/trigger_animation', { name, params });
}

export async function testMoveTrace(options: {
  uci?: string;
  from_pos?: [number, number];
  to_pos?: [number, number];
  is_capture?: boolean;
  clear?: boolean;
}) {
  return jsonPost('/leds/test_trace', options);
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

export interface BoardSettings {
  baselines: number[][];
  threshold_positive: number;
  threshold_negative: number;
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
  clock_bar_enabled?: boolean;
  opening_hints_enabled?: boolean;
  coach_ai_only?: boolean;
  in_loop_calibration?: boolean;
  led_intensity?: number;
  night_mode?: boolean;
  col_mux_map?: number[];
  last_game_params?: LastGameParams | null;
  last_game_moves?: string[];
  last_game_id?: string | null;
  last_game_my_color?: 'white' | 'black' | null;
}

export interface SettingsResponse {
  status: string;
  message?: string;
  file?: string;
  settings?: BoardSettings;
}

export async function getLastGameParams(): Promise<{ status: string; last_game_params: LastGameParams | null }> {
  return request('/game/last_params');
}

export async function restartPreviousGame() {
  return jsonPost('/game/restart_previous');
}

// --- Post-Game Analysis & Training API ---

export async function startAnalysis(options?: { moves_uci?: string[]; game_id?: string; web_only?: boolean }) {
  return jsonPost('/analysis/start', options || {}, 120000);
}

export async function stepAnalysis(ply: number) {
  return jsonPost('/analysis/step', { ply });
}

export async function navAnalysis(direction: 'back' | 'forward' | 'start' | 'end') {
  return jsonPost('/analysis/nav', { direction });
}

export async function sendAnalysisMove(uci: string) {
  return jsonPost('/analysis/move', { uci });
}

export async function resetAnalysisBranch() {
  return jsonPost('/analysis/branch_reset');
}

export interface EngineLine {
  uci: string[];
  san: string[];
  score_cp: number | null;
  mate: number | null;
}

export async function getEngineLines(fen?: string, numLines = 3) {
  return jsonPost<{ lines: EngineLine[] }>('/analysis/lines', { fen: fen ?? null, num_lines: numLines });
}

export async function stopAnalysis() {
  return jsonPost('/analysis/stop');
}

export async function getGMGames() {
  return request('/analysis/gm/games');
}

export async function startGMGame(gameId: string) {
  return jsonPost('/analysis/gm/start', { game_id: gameId });
}

export async function startReplayRecall(movesUci?: string[]) {
  return jsonPost('/analysis/replay/recall', movesUci ? { moves_uci: movesUci } : {});
}

export interface BlunderAttemptResult {
  correct: boolean;
  step_complete?: boolean;
  puzzle_complete?: boolean;
  message: string;
  player_san?: string;
  opponent_reply_uci?: string | null;
  opponent_reply_san?: string | null;
  current_step?: number;
  total_steps?: number;
  best_move?: string;
  next_expected_move?: string;
  solution_line?: string[];
  active_fen?: string | null;
  attempts_remaining?: number;
}

export async function startBlunderDrill(index: number = 0) {
  return jsonPost('/analysis/blunder_drill/start', { index });
}

export async function submitBlunderAttempt(uci: string) {
  return jsonPost<BlunderAttemptResult>('/analysis/blunder_drill/attempt', { uci });
}

export async function toggleBlunderHint() {
  return jsonPost<{ active: boolean }>('/analysis/blunder_drill/hint');
}

export async function resolvePromotion(piece: 'q' | 'n' | 'r' | 'b' = 'q') {
  return jsonPost<{ status: string; piece: string }>('/game/promote', { piece });
}

export async function lookupOpening(moves: string[] = []) {
  const query = encodeURIComponent(moves.join(','));
  return request(`/openings/lookup?moves=${query}`);
}

// --- Endgame Tablebase Trainer ("Endgame Academy") API ---

export interface EndgameDrillItem {
  id: string;
  title: string;
  category: 'pawns' | 'rooks' | 'minors' | 'queens' | 'custom';
  category_title: string;
  fen: string;
  player_color: 'white' | 'black';
  target_goal: 'win' | 'draw' | 'mate';
  difficulty: number;
  description: string;
  hint: string;
  target_moves_par: number;
  completed: boolean;
  stars: number;
  best_accuracy: number;
  best_moves: number;
  attempts_count: number;
}

export async function getEndgameDrills(): Promise<EndgameDrillItem[]> {
  return request<EndgameDrillItem[]>('/endgame/drills');
}

export async function startEndgameDrill(options?: {
  drill_id?: string;
  custom_fen?: string;
  custom_params?: Record<string, unknown>;
}) {
  return jsonPost('/endgame/start', options || {});
}

export async function stopEndgameDrill() {
  return jsonPost('/endgame/stop');
}

export async function requestEndgameHint() {
  return jsonPost<{ hint_uci?: string; hint_text?: string }>('/endgame/hint');
}

export async function createCustomEndgame(params: {
  fen: string;
  title?: string;
  player_color?: 'white' | 'black';
  target_goal?: 'win' | 'draw' | 'mate';
  difficulty?: number;
  description?: string;
  hint?: string;
}) {
  return jsonPost('/endgame/custom', params);
}

export async function resetEndgameProgress() {
  return jsonPost('/endgame/reset-progress');
}
