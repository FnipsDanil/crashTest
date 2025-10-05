/**
 * Balance Context with WebSocket support
 * Reduces polling frequency and uses WebSocket updates when available
 */

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react'
import { initData } from '@telegram-apps/sdk-react'
import { handleApiError } from '../hooks/useApiHealth'
import { useWebSocketContext } from './WebSocketContext' // ✅ ИСПРАВЛЕНО: используем единый WebSocket контекст

interface BalanceContextType {
  balance: number
  updateBalance: (newBalance?: number) => void
  addToBalance: (amount: number) => void
  refreshBalance: () => Promise<void>
  loading: boolean
  lastUpdated: number
  wsConnected: boolean
}

const BalanceContext = createContext<BalanceContextType | undefined>(undefined)

export const useBalance = () => {
  const context = useContext(BalanceContext)
  if (!context) {
    throw new Error('useBalance must be used within a BalanceProvider')
  }
  return context
}

interface BalanceProviderProps {
  children: ReactNode
}

export const BalanceProvider = ({ children }: BalanceProviderProps) => {
  const [balance, setBalance] = useState<number>(0)
  const [loading, setLoading] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<number>(0)
  
  // 🚀 OPTIMIZATION: Request deduplication to prevent concurrent balance fetches
  const [pendingRequest, setPendingRequest] = useState<Promise<void> | null>(null)
  
  // ✅ ИСПРАВЛЕНО: используем единый WebSocket контекст вместо создания второго подключения
  const { isConnected: wsConnected, subscribe } = useWebSocketContext()

  const loadBalance = async () => {
    // 🚀 OPTIMIZATION: Return existing request if already in progress
    if (pendingRequest) {
      return pendingRequest
    }

    const request = (async () => {
      try {
        setLoading(true)
        const telegramUser = initData.user()
        if (!telegramUser) return

        const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"
        
        const headers: Record<string, string> = {
          "Content-Type": "application/json"
        }
        
        // Add Telegram auth header
        const telegramInitData = initData.raw()
        if (telegramInitData) {
          headers["X-Telegram-Init-Data"] = telegramInitData
        }
        
        const response = await fetch(`${API_URL}/balance/${telegramUser.id}`, {
          headers
        })
        
        if (response.ok) {
          const data = await response.json()
          // 🚀 КРИТИЧНО: Обрабатываем сжатый format backend ответа
          const balanceValue = data.b ? parseFloat(data.b) : data.balance
          setBalance(balanceValue)
          setLastUpdated(Date.now())
        } else {
          console.warn('Failed to load balance:', response.status)
        }
      } catch (error) {
        console.error('Error loading balance:', error)
        if (handleApiError(error)) {
          // Handle API error appropriately
        }
      } finally {
        setLoading(false)
        setPendingRequest(null) // Clear pending request
      }
    })()

    setPendingRequest(request)
    return request
  }

  const updateBalance = useCallback((newBalance?: number) => {
    if (newBalance !== undefined) {
      setBalance(newBalance)
      setLastUpdated(Date.now())
    } else {
      // 🚀 OPTIMIZATION: Only make HTTP request if WebSocket is not available
      if (!wsConnected) {
        loadBalance()
      }
    }
  }, [wsConnected])

  const addToBalance = useCallback((amount: number) => {
    setBalance(prev => {
      const newBalance = prev + amount
      setLastUpdated(Date.now())
      return newBalance
    })
  }, [])

  const refreshBalance = useCallback(async () => {
    // 🚀 OPTIMIZATION: Only make HTTP request if WebSocket is not available
    if (!wsConnected) {
      await loadBalance()
    }
  }, [wsConnected])

  // Subscribe to WebSocket balance updates
  useEffect(() => {
    if (wsConnected) {
      const unsubscribe = subscribe('balance_update', (data: { balance: string, user_id: number }) => {
        
        // Verify this update is for the current user
        try {
          const telegramUser = initData.user()
          if (telegramUser && telegramUser.id === data.user_id) {
            setBalance(parseFloat(data.balance))
            setLastUpdated(Date.now())
          }
        } catch (e) {
          // Skip balance update if user verification fails for security
          console.warn('Balance update skipped - user verification failed:', e)
        }
      })

      return unsubscribe
    }
  }, [wsConnected, subscribe])

  // Initial balance load and SMART polling - NO HTTP when WebSocket works
  useEffect(() => {
    // Load balance initially - ALWAYS needed for proper initialization
    loadBalance()
    
    // 🚀 MAJOR OPTIMIZATION: No periodic HTTP polling when WebSocket is active
    let balanceInterval: NodeJS.Timeout | null = null
    
    if (!wsConnected) {
      // Only use HTTP polling as fallback when WebSocket is completely unavailable
      const refreshInterval = 10000 // 15 seconds fallback when no WebSocket
      balanceInterval = setInterval(() => {
        const timeSinceUpdate = Date.now() - lastUpdated
        if (timeSinceUpdate > 5000) { // 10 seconds threshold
          loadBalance()
        }
      }, refreshInterval)
    }
    
    return () => {
      if (balanceInterval) {
        clearInterval(balanceInterval)
      }
    }
  }, [wsConnected, lastUpdated])

  // Handle WebSocket reconnection - NO automatic HTTP request
  useEffect(() => {
    if (wsConnected) {
      // 🚀 OPTIMIZATION: Don't make HTTP request on reconnect - balance_update events will sync
      // The WebSocket will send immediate data and balance_update events will handle the rest
    }
  }, [wsConnected])

  // ✅ REMOVED: Duplicate visibilitychange handler - WebSocketContext handles this centrally

  const contextValue: BalanceContextType = {
    balance,
    updateBalance,
    addToBalance,
    refreshBalance,
    loading,
    lastUpdated,
    wsConnected
  }

  return (
    <BalanceContext.Provider value={contextValue}>
      {children}
    </BalanceContext.Provider>
  )
}