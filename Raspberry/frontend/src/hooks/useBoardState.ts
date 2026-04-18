import { useState, useEffect, useCallback, useRef } from 'react';

export interface BoardState {
  status: 'IDLE' | 'SEEKING' | 'PLAYING' | 'SETUP';
  physical: {
    rows: number;
    cols: number;
    grid: boolean[][];
  };
  digital: string[][];
  my_color: 'white' | 'black' | null;
}

const DEFAULT_STATE: BoardState = {
  status: 'IDLE',
  physical: { rows: 4, cols: 4, grid: [] },
  digital: Array(8).fill(null).map(() => Array(8).fill('.')),
  my_color: null
};

export function useBoardState() {
  const [state, setState] = useState<BoardState>(DEFAULT_STATE);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    // When served from Pi, window.location.hostname is the Pi's IP.
    // In dev, you might want to hardcode the IP.
    const host = window.location.hostname || 'localhost';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${host}:8000/ws/state`;

    console.log(`Connecting to WebSocket: ${wsUrl}`);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket Connected');
      setIsConnected(true);
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
      setTimeout(connect, 3000);
    };

    ws.onerror = (err) => {
      console.error('WebSocket Error', err);
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return { state, isConnected };
}
