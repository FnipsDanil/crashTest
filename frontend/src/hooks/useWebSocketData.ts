/**
 * Simplified WebSocket data hooks using singleton context
 */

import { useState, useEffect } from 'react'
import { useWebSocketContext } from '../contexts/WebSocketContext'

interface GameStateData {
  coefficient: string;
  status: string;
  countdown: number;
  crashed: boolean;
  crash_point?: string | null;  // 🔒 SECURITY: null during game, string after crash
  last_crash_coefficient?: string;
  // 🚨 REMOVED: time_since_start for anti-timing attack protection
  // time_since_start?: number;
  game_just_crashed?: boolean;
}

interface CrashHistoryData {
  history: string[];
}

/**
 * Hook for game state - no more re-render loops
 */
export function useGameState() {
  const { isConnected, subscribe } = useWebSocketContext()
  const [gameState, setGameState] = useState<GameStateData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<any>(null)

  useEffect(() => {
    if (!isConnected) {
      setLoading(true)
      return
    }

    //console.log('🎮 useGameState: Setting up stable subscription')
    
    const unsubscribe = subscribe('game_state', (data: GameStateData) => {
      //console.log('🎮 useGameState: Data received')
      setGameState(data)
      setLoading(false)
      setError(null)
    })

    const unsubscribeError = subscribe('error', (data: any) => {
      setError(data.error)
      setLoading(false)
    })

    return () => {
      unsubscribe()
      unsubscribeError()
    }
  }, [isConnected, subscribe]) // Stable dependencies

  return { gameState, loading, error }
}

/**
 * Hook for crash history - no more re-render loops
 * 🚀 INSTANT LOADING: Uses localStorage cache for immediate display
 */
export function useCrashHistory() {
  const { isConnected, subscribe } = useWebSocketContext()
  const [history, setHistory] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<any>(null)

  // 🚀 Load cached history immediately on mount
  useEffect(() => {
    try {
      const cachedHistory = localStorage.getItem('crash_history_cache')
      if (cachedHistory) {
        const parsed = JSON.parse(cachedHistory)
        if (Array.isArray(parsed) && parsed.length > 0) {
          //console.log('📈 Loaded cached crash history:', parsed.length, 'items')
          setHistory(parsed)
          setLoading(false) // Show cached data immediately
        }
      }
    } catch (e) {
      console.warn('Failed to load cached crash history:', e)
    }
  }, [])

  useEffect(() => {
    if (!isConnected) {
      // Don't set loading to true if we have cached data
      if (history.length === 0) {
        setLoading(true)
      }
      return
    }

    //console.log('📈 useCrashHistory: Setting up stable subscription')
    
    const unsubscribe = subscribe('crash_history', (data: CrashHistoryData) => {
      //console.log('📈 useCrashHistory: Data received')
      const newHistory = data.history || []
      setHistory(newHistory)
      setLoading(false)
      setError(null)
      
      // 🚀 Cache in localStorage for instant loading next time
      try {
        if (newHistory.length > 0) {
          localStorage.setItem('crash_history_cache', JSON.stringify(newHistory))
        }
      } catch (e) {
        console.warn('Failed to cache crash history:', e)
      }
    })

    const unsubscribeError = subscribe('error', (data: any) => {
      setError(data.error)
      setLoading(false)
    })

    return () => {
      unsubscribe()
      unsubscribeError()
    }
  }, [isConnected, subscribe]) // Stable dependencies

  return { history, loading, error }
}

/**
 * Hook for player status - no more re-render loops
 */
export function usePlayerStatus() {
  const { isConnected, subscribe } = useWebSocketContext()
  const [playerStatus, setPlayerStatus] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!isConnected) {
      setLoading(true)
      return
    }

    const unsubscribe = subscribe('player_status', (data: any) => {
      setPlayerStatus(data)
      setLoading(false)
    })

    return () => {
      unsubscribe()
    }
  }, [isConnected, subscribe])

  return { playerStatus, loading }
}