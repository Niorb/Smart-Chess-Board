import { useState, useEffect, useCallback, useRef } from 'react';

export interface BoardState {
  status: 'IDLE' | 'SEEKING' | 'PLAYING' | 'SETUP';
  physical: {
    rows: number;
    cols: number;
    grid: number[][];
    adc?: number[][];
    baselines?: number[][];
    highlighted_square?: [number, number] | null;
    led_test_active?: boolean;
    testing_led_index?: number;
  };
  digital: string[][];
  my_color: 'white' | 'black' | null;
  clocks?: {
    white: string;
    black: string;
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
  physical: { rows: 4, cols: 8, grid: [], led_test_active: false, testing_led_index: -1 },
  digital: Array(8).fill(null).map(() => Array(8).fill('.')),
  my_color: null,
  clocks: { white: '?', black: '?' },
  diagnostics: { status: 'UNKNOWN', last_raw_line: '', timeouts: 0, errors: 0 }
};

export function useBoardState() {
  const [state, setState] = useState<BoardState>(DEFAULT_STATE);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

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
        setState(data);
      } catch (err) {
        console.error('Failed to parse WebSocket message', err);
      }
    };

    ws.onclose = () => {
      console.log('WebSocket Disconnected. Reconnecting in 3s...');
      setIsConnected(false);
      // Use window.setTimeout for Node/Browser compatibility types
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect();
      }, 3000);
    };

    ws.onerror = (err) => {
      console.error('WebSocket Error', err);
      ws.close();
    };

    wsRef.current = ws;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return { state, isConnected };
}
