/**
 * React hook for WebSocket connection and event subscriptions
 * Provides easy integration with React components
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { initData } from '@telegram-apps/sdk-react';
import websocketService from '../services/websocket';

type EventType = 'game_state' | 'crash_history' | 'player_status' | 'balance_update' | 'ping' | 'pong' | 'error' | 'connected' | 'disconnected';

interface GameStateData {
  coefficient: string;
  status: string;
  countdown: number;
  crashed: boolean;
  crash_point?: string;
  last_crash_coefficient?: string;
  time_since_start?: number;
  game_just_crashed?: boolean;
}

interface CrashHistoryData {
  history: string[];
}

interface UseWebSocketOptions {
  autoConnect?: boolean;
  userId?: number;
  events?: EventType[];
}

interface WebSocketState {
  connected: boolean;
  connecting: boolean;
  error: any;
  reconnecting: boolean;
}

interface UseWebSocketReturn {
  // Connection state
  state: WebSocketState;
  
  // Connection methods
  connect: () => Promise<boolean>;
  disconnect: () => void;
  
  // Event subscription
  subscribe: (event: EventType, callback: (data: any) => void) => () => void;
  
  // Utility methods
  isConnected: boolean;
  stats: any;
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    autoConnect = true,
    userId: providedUserId,
    events = []
  } = options;
  
  const [state, setState] = useState<WebSocketState>({
    connected: false,
    connecting: false,
    error: null,
    reconnecting: false
  });
  
  const unsubscribeFunctions = useRef<(() => void)[]>([]);
  const isInitialized = useRef(false);
  
  // Get user ID from Telegram or provided value
  const getUserId = useCallback((): number | null => {
    if (providedUserId) {
      return providedUserId;
    }
    
    try {
      const user = initData.user();
      return user?.id || null;
    } catch {
      return null;
    }
  }, [providedUserId]);
  
  // Get init data for authentication
  const getInitData = useCallback((): string => {
    try {
      return initData.raw() || 'development';
    } catch {
      return 'development';
    }
  }, []);
  
  // Connect to WebSocket
  const connect = useCallback(async (): Promise<boolean> => {
    const userId = getUserId();

    if (!userId) {
      console.warn('⚠️ No user ID available for WebSocket connection');
      return false;
    }
    
    // Check if already connected
    if (websocketService.isWebSocketConnected()) {
      setState(prev => ({ ...prev, connected: true, connecting: false, error: null }));
      return true;
    }
    
    setState(prev => ({ ...prev, connecting: true, error: null }));
    
    try {
      const initDataStr = getInitData();
      const success = await websocketService.connect(userId, initDataStr);
      
      setState(prev => ({
        ...prev,
        connected: success,
        connecting: false,
        error: success ? null : 'Connection failed'
      }));
      
      return success;
    } catch (error) {
      console.error('❌ useWebSocket connect error:', error);
      setState(prev => ({
        ...prev,
        connected: false,
        connecting: false,
        error: error
      }));
      return false;
    }
  }, [getUserId, getInitData]);
  
  // Disconnect from WebSocket
  const disconnect = useCallback((): void => {
    websocketService.disconnect();
    setState(prev => ({
      ...prev,
      connected: false,
      connecting: false,
      reconnecting: false
    }));
  }, []);
  
  // Subscribe to WebSocket events
  const subscribe = useCallback((event: EventType, callback: (data: any) => void): () => void => {
    const unsubscribe = websocketService.subscribe(event, callback);
    unsubscribeFunctions.current.push(unsubscribe);
    return unsubscribe;
  }, []);
  
  // Setup WebSocket event listeners - ONLY ONCE per hook instance
  useEffect(() => {
    // Check if already initialized to prevent duplicate subscriptions
    if (unsubscribeFunctions.current.length > 0) {
      return;
    }
    
    // Subscribe to connection events
    const unsubscribeConnected = websocketService.subscribe('connected', () => {
      setState(prev => ({ ...prev, connected: true, connecting: false, reconnecting: false }));
    });
    
    const unsubscribeDisconnected = websocketService.subscribe('disconnected', () => {
      setState(prev => ({ ...prev, connected: false, reconnecting: true }));
    });
    
    const unsubscribeError = websocketService.subscribe('error', (data) => {
      setState(prev => ({ ...prev, error: data.error, connecting: false }));
    });
    
    unsubscribeFunctions.current = [unsubscribeConnected, unsubscribeDisconnected, unsubscribeError];
    
    return () => {
      // Cleanup all subscriptions
      unsubscribeFunctions.current.forEach(unsub => unsub());
      unsubscribeFunctions.current = [];
    };
  }, []); // Empty dependency array - only run once
  
  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect && !isInitialized.current) {
      isInitialized.current = true;
      connect();
    }
    
    return () => {
      // Cleanup on unmount
      unsubscribeFunctions.current.forEach(unsub => unsub());
      if (!autoConnect) {
        disconnect();
      }
    };
  }, [autoConnect, connect, disconnect]);
  
  return {
    state,
    connect,
    disconnect,
    subscribe,
    isConnected: state.connected,
    stats: websocketService.getStats()
  };
}

/**
 * Hook specifically for game state updates (replaces /current-state polling)
 */
export function useGameState(): {
  gameState: GameStateData | null;
  loading: boolean;
  error: any;
  subscribe: (callback: (data: GameStateData) => void) => () => void;
} {
  const [gameState, setGameState] = useState<GameStateData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<any>(null);
  const { subscribe: wsSubscribe, isConnected } = useWebSocket();
  
  const subscribe = useCallback((callback: (data: GameStateData) => void): () => void => {
    return wsSubscribe('game_state', (data: GameStateData) => {
      setGameState(data);
      setLoading(false);
      setError(null);
      callback(data);
    });
  }, [wsSubscribe]);
  
  
  // Direct subscription via websocketService (fixed approach)
  useEffect(() => {
    if (!isConnected) {
      setLoading(true);
      return;
    }
    
    const unsubscribe = websocketService.subscribe('game_state', (data: GameStateData) => {
      setGameState(data);
      setLoading(false);
      setError(null);
    });
    
    const unsubscribeError = websocketService.subscribe('error', (data) => {
      console.log('❌ useGameState: Error received:', data);
      setError(data.error);
      setLoading(false);
    });
    
    return () => {
      unsubscribe();
      unsubscribeError();
    };
  }, [isConnected]);
  
  return { gameState, loading, error, subscribe };
}

/**
 * Hook for crash history updates (replaces /crash-history polling)
 */
export function useCrashHistory(): {
  history: string[];
  loading: boolean;
  error: any;
  subscribe: (callback: (data: CrashHistoryData) => void) => () => void;
} {
  const [history, setHistory] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<any>(null);
  const { subscribe: wsSubscribe, isConnected } = useWebSocket();
  
  const subscribe = useCallback((callback: (data: CrashHistoryData) => void): () => void => {
    return wsSubscribe('crash_history', (data: CrashHistoryData) => {
      setHistory(data.history || []);
      setLoading(false);
      setError(null);
      callback(data);
    });
  }, [wsSubscribe]);
  
  // Subscribe to crash history on mount - direct approach
  useEffect(() => {
    
    if (!isConnected) {
      setLoading(true);
      return;
    }
    
    const unsubscribe = websocketService.subscribe('crash_history', (data: CrashHistoryData) => {
      setHistory(data.history || []);
      setLoading(false);
      setError(null);
    });
    
    const unsubscribeError = websocketService.subscribe('error', (data) => {
      setError(data.error);
      setLoading(false);
    });
    
    return () => {
      unsubscribe();
      unsubscribeError();
    };
  }, [isConnected]);
  
  return { history, loading, error, subscribe };
}

export default useWebSocket;