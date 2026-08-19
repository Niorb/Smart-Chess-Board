import { useState, useEffect, useCallback, useRef } from 'react';

export interface SetupStatus {
  is_setup_ready: boolean;
  missing_white: [number, number][];
  missing_black: [number, number][];
  misplaced_pieces: [number, number][];
  white_count?: number;
  black_count?: number;
}

export interface GuardrailStatus {
  is_synchronized: boolean;
  missing_pieces: [number, number][];
  unexpected_pieces: [number, number][];
  pending_capture?: [number, number] | null;
  candidate_attackers?: [number, number][];
}

export interface MoveHint {
  target_square: [number, number];
  uci: string;
  tier: 'best' | 'good' | 'inaccuracy' | 'blunder';
  delta_cp: number;
}

export interface CoachPayload {
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
  status: 'IDLE' | 'SEEKING' | 'PLAYING' | 'SETUP' | 'GAME_OVER';
  virtual_only?: boolean;
  physical: {
    rows: number;
    cols: number;
    grid: number[][];
    adc?: number[][];
    baselines?: number[][];
    highlighted_square?: [number, number] | null;
    led_test_active?: boolean;
    testing_led_index?: number;
    disabled_squares?: number[][];
    virtual_only?: boolean;
    setup?: SetupStatus;
    guardrail?: GuardrailStatus | null;
    pieces_detected?: boolean;
    detected_starting_count?: number;
    pieces_mode?: 'auto' | 'pieces' | 'empty';
    effective_pieces_mode?: boolean;
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
    in_flight_move?: {
      uci: string;
      from: [number, number];
      to: [number, number];
      timestamp?: number;
    } | null;
  };
  digital: string[][];
  my_color: 'white' | 'black' | null;
  clocks?: {
    white: string;
    black: string;
  };
  coach?: CoachPayload;
  game?: {
    game_id: string | null;
    rated: boolean;
    speed?: string | null;
    turn: 'white' | 'black';
    my_color: 'white' | 'black' | null;
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

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const host = window.location.hostname || 'localhost';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${host}:8000/ws/state`;

    console.log(`Connecting to WebSocket: ${wsUrl}`);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket Connected');
      setIsConnected(true);
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
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
      console.log('WebSocket Disconnected. Reconnecting in 3s...');
      setIsConnected(false);
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connectRef.current();
      }, 3000);
    };

    ws.onerror = (err) => {
      console.error('WebSocket Error', err);
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };
  }, [connect]);

  return { state, isConnected };
}
