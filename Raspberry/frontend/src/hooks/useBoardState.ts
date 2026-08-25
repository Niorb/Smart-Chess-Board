import { useState, useEffect, useCallback, useRef } from 'react';

interface SetupStatus {
  is_setup_ready: boolean;
  missing_white: [number, number][];
  missing_black: [number, number][];
  misplaced_pieces: [number, number][];
  white_count?: number;
  black_count?: number;
}

interface GuardrailStatus {
  is_synchronized: boolean;
  missing_pieces: [number, number][];
  unexpected_pieces: [number, number][];
  pending_capture?: [number, number] | null;
  candidate_attackers?: [number, number][];
}

interface MoveHint {
  target_square: [number, number];
  uci: string;
  tier: 'best' | 'good' | 'inaccuracy' | 'blunder';
  delta_cp: number;
}

interface AnalysisMoveItem {
  ply: number;
  turn: 'white' | 'black';
  uci: string;
  san: string;
  from: string;
  to: string;
  classification: 'best' | 'good' | 'inaccuracy' | 'blunder';
  delta_cp: number;
  best_move?: string | null;
}

interface BlunderChallenge {
  ply_index: number;
  fen_before: string;
  played_move: string;
  classification: string;
  delta_cp: number;
  best_move: string;
  best_score_cp?: number | null;
  description: string;
  top_moves?: Array<{
    uci: string;
    score_cp?: number | null;
    mate?: number | null;
    win_chance?: number;
  }>;
}

export interface GMGameSummary {
  id: string;
  title: string;
  event: string;
  year: number;
  white: string;
  white_elo?: string | null;
  black: string;
  black_elo?: string | null;
  result: string;
  description: string;
  eco: string;
  opening: string;
  moves_count: number;
  key_plys?: number[];
  annotations?: Record<number, string>;
}

export interface PendingPromotionState {
  from: [number, number];
  to: [number, number];
  color: 'white' | 'black';
  start_time: number;
  timeout_s: number;
  options: {
    q: [number, number];
    n: [number, number];
    r: [number, number];
    b: [number, number];
  };
  is_capture: boolean;
}

export interface BookMoveCandidate {
  uci: string;
  san: string;
  weight: number;
  percentage: number;
  classification: 'mainline' | 'sideline';
  from_coord: [number, number];
  to_coord: [number, number];
}

export interface OpeningPayload {
  eco: string;
  name: string;
  variation: string | null;
  ply: number;
  fen: string;
  out_of_book: boolean;
  novelty_ply: number | null;
  novelty_move: string | null;
  book_moves: BookMoveCandidate[];
}

interface ReplayState {
  phase: 'learn' | 'recall' | null;
  learned_ply: number;
  results: Array<{ ply: number; correct: boolean }>;
  mistakes: number;
  reveal_uci?: string | null;
  complete: boolean;
}

interface AnalysisState {
  active: boolean;
  submode: 'review' | 'blunder_drill' | 'replay_learn' | 'replay_recall';
  is_loading: boolean;
  error?: string | null;
  current_ply: number;
  total_plys: number;
  game_moves: string[];
  evaluations: Array<{
    win_chance?: number;
    score_cp?: number | null;
    mate?: number | null;
    best_move?: string | null;
  }>;
  played_analyses: AnalysisMoveItem[];
  accuracy: {
    white: number;
    black: number;
  };
  counts: {
    white?: Record<string, number>;
    black?: Record<string, number>;
  };
  current_eval?: {
    win_chance?: number;
    score_cp?: number | null;
    mate?: number | null;
    best_move?: string | null;
    top_moves?: Array<{ uci: string; score_cp?: number | null; mate?: number | null }>;
  } | null;
  branch_moves: string[];
  is_branching: boolean;
  anchor_ply?: number | null;
  anchor_coord?: [number, number] | null;
  blunders: BlunderChallenge[];
  blunder_index: number;
  blunder_attempts: number;
  blunder_hint_active: boolean;
  gm_game?: GMGameSummary | null;
  replay: ReplayState;
  fen: string;
  legal_moves?: string[];
  in_check?: boolean;
}

interface GestureItem {
  name: string;
  description: string;
  is_active: boolean;
  step: number;
  hint?: string | null;
  time_remaining?: number;
  starter_coord?: [number, number] | null;
}

interface GestureState {
  is_active: boolean;
  active_gesture?: string | null;
  step: number;
  hint?: string | null;
  time_remaining?: number;
  gestures?: GestureItem[];
}

interface CoachPayload {
  enabled: boolean;
  eval_bar_enabled: boolean;
  coach_hints_enabled: boolean;
  is_ai_game: boolean;
  fair_play_active: boolean;
  evaluation?: {
    score_cp?: number | null;
    mate?: number | null;
    win_chance: number;
    best_move?: string | null;
  } | null;
  lifted_move_hints?: MoveHint[];
}

export interface BoardState {
  status: 'IDLE' | 'SEEKING' | 'PLAYING' | 'SETUP' | 'GAME_OVER' | 'ANALYSIS';
  virtual_only?: boolean;
  gesture?: GestureState;
  analysis?: AnalysisState;
  physical: {
    rows: number;
    cols: number;
    grid: number[][];
    adc?: number[][];
    baselines?: number[][];
    led_test_active?: boolean;
    testing_led_index?: number;
    disabled_squares?: number[][];
    virtual_only?: boolean;
    gesture?: GestureState;
    setup?: SetupStatus;
    guardrail?: GuardrailStatus | null;
    pieces_detected?: boolean;
    detected_starting_count?: number;
    pieces_mode?: 'auto' | 'pieces' | 'empty';
    effective_pieces_mode?: boolean;
    led_intensity?: number;
    night_mode?: boolean;
    lifted_square?: [number, number] | null;
    legal_targets?: [number, number][];
    legal_captures?: [number, number][];
    pending_capture_target?: [number, number] | null;
    capture_candidate_attackers?: [number, number][];
    invalid_placement?: [number, number] | null;
    pending_opponent_move?: {
      uci: string;
      from: [number, number];
      to: [number, number];
    } | null;
    pending_castling_rook?: {
      from: [number, number];
      to: [number, number];
      start_time?: number;
    } | null;
    active_animation?: string | null;
    custom_trace_path?: [number, number][] | null;
    pending_promotion?: PendingPromotionState | null;
    in_flight_move?: {
      uci: string;
      from: [number, number];
      to: [number, number];
      timestamp?: number;
    } | null;
    resignation_armed?: boolean;
    king_lift_elapsed?: number | null;
  };
  digital: string[][];
  my_color: 'white' | 'black' | null;
  clocks?: {
    white: string;
    black: string;
  };
  clocks_raw?: {
    white: number | null;
    black: number | null;
    updated_at: number | null;
    turn: 'white' | 'black' | null;
  };
  coach?: CoachPayload;
  opening?: OpeningPayload | null;
  game?: {
    game_id: string | null;
    type?: string;
    is_local?: boolean;
    rated: boolean;
    speed?: string | null;
    turn: 'white' | 'black';
    my_color: 'white' | 'black' | null;
    white?: {
      username: string;
      rating?: number | null;
      title?: string | null;
    };
    black?: {
      username: string;
      rating?: number | null;
      title?: string | null;
    };
    opponent?: {
      username: string;
      rating: number;
      title?: string | null;
    };
    opponent_gone?: {
      gone: boolean;
      claim_win_in: number;
    } | null;
    last_move?: string | null;
    legal_moves?: string[];
    is_check?: boolean;
    is_game_over?: boolean;
    winner?: 'white' | 'black' | 'draw' | null;
    end_reason?: string | null;
  };
  diagnostics?: {
    status: string;
    last_raw_line: string;
    timeouts: number;
    errors: number;
  };
}

const DEFAULT_STATE: BoardState = {
  status: 'IDLE',
  virtual_only: false,
  physical: { rows: 8, cols: 8, grid: [], led_test_active: false, testing_led_index: -1, virtual_only: false },
  digital: Array(8).fill(null).map(() => Array(8).fill('.')),
  my_color: null,
  clocks: { white: '?', black: '?' },
  game: {
    game_id: null,
    rated: false,
    speed: 'rapid',
    turn: 'white',
    my_color: null,
    opponent: { username: 'Opponent', rating: 1500, title: null },
    last_move: null,
    legal_moves: [],
    is_check: false,
    is_game_over: false,
    winner: null,
    end_reason: null,
  },
  diagnostics: { status: 'UNKNOWN', last_raw_line: '', timeouts: 0, errors: 0 },
};

export function useBoardState() {
  const [state, setState] = useState<BoardState>(DEFAULT_STATE);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const connectRef = useRef<() => void>(() => {});
  const disposedRef = useRef(false);
  const lastPayloadRef = useRef<string | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    if (wsRef.current?.readyState === WebSocket.CONNECTING) return;

    const host = window.location.hostname || 'localhost';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const port = window.location.port === '5173' || !window.location.port ? '8000' : window.location.port;
    const wsUrl = `${protocol}//${host}:${port}/ws/state`;

    if (import.meta.env.DEV) console.log(`Connecting to WebSocket: ${wsUrl}`);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      if (import.meta.env.DEV) console.log('WebSocket Connected');
      setIsConnected(true);
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    ws.onmessage = (event) => {
      // Skip identical consecutive payloads entirely (server heartbeat + JSON
      // string compare is far cheaper than a React re-render of the whole tree)
      if (event.data === lastPayloadRef.current) return;
      try {
        const data = JSON.parse(event.data);
        lastPayloadRef.current = event.data;
        setState((prev) => ({
          ...prev,
          ...data,
          game: {
            ...prev.game,
            ...(data.game || {}),
          },
        }));
      } catch (err) {
        console.error('Failed to parse WebSocket message', err);
      }
    };

    ws.onclose = () => {
      if (disposedRef.current) return;
      setIsConnected(false);
      if (!reconnectTimeoutRef.current) {
        reconnectTimeoutRef.current = window.setTimeout(() => {
          reconnectTimeoutRef.current = null;
          connectRef.current();
        }, 1000);
      }
    };

    ws.onerror = () => {
      try {
        ws.close();
      } catch {
        // already closed
      }
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    disposedRef.current = false;
    lastPayloadRef.current = null;
    connect();
    return () => {
      disposedRef.current = true;
      const ws = wsRef.current;
      if (ws) {
        // Detach handlers first so the async close event cannot schedule a reconnect
        ws.onopen = null;
        ws.onmessage = null;
        ws.onclose = null;
        ws.onerror = null;
        ws.close();
        wsRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };
  }, [connect]);

  return { state, isConnected };
}
