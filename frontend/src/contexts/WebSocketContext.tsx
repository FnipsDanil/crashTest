/**
 * Singleton WebSocket Context - eliminates multiple connection issues
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import websocketService from '../services/websocket'
import { initData } from '@telegram-apps/sdk-react'

// Import EventType from the websocket service to ensure consistency
type EventType = 'game_state' | 'crash_history' | 'player_status' | 'balance_update' | 'ping' | 'pong' | 'error' | 'connected' | 'disconnected' | 'subscribed' | 'unsubscribed';

interface WebSocketContextType {
  isConnected: boolean
  subscribe: (event: EventType, callback: (data: any) => void) => () => void
  connectionState: {
    connecting: boolean
    reconnecting: boolean
    error: string | null
  }
}

const WebSocketContext = createContext<WebSocketContextType | null>(null)

interface WebSocketProviderProps {
  children: ReactNode
}

export function WebSocketProvider({ children }: WebSocketProviderProps) {
  const [isConnected, setIsConnected] = useState(false)
  const [connectionState, setConnectionState] = useState({
    connecting: false,
    reconnecting: false,
    error: null as string | null
  })
  
  // Track page visibility for smart connection management
  const [disconnectTimer, setDisconnectTimer] = useState<NodeJS.Timeout | null>(null)

  // Initialize WebSocket connection ONCE
  useEffect(() => {
    let mounted = true

    const initConnection = async () => {
      try {
        // Get user ID
        let userId: number | null = null
        try {
          const user = initData.user()
          userId = user?.id || 123456
        } catch {
          userId = 123456
        }

        if (!userId) return

        setConnectionState(prev => ({ ...prev, connecting: true }))
        
        const initDataStr = initData.raw() || 'development'
        const success = await websocketService.connect(userId, initDataStr)
        
        if (mounted) {
          setIsConnected(success)
          setConnectionState({
            connecting: false,
            reconnecting: false,
            error: success ? null : 'Connection failed'
          })
        }
      } catch (error) {
        if (mounted) {
          setConnectionState({
            connecting: false,
            reconnecting: false,
            error: error instanceof Error ? error.message : String(error)
          })
        }
      }
    }

    // Setup connection event listeners ONCE
    const unsubscribeConnected = websocketService.subscribe('connected', () => {
      if (mounted) {
        setIsConnected(true)
        setConnectionState(prev => ({ ...prev, connected: true, connecting: false, reconnecting: false }))
      }
    })
    
    const unsubscribeDisconnected = websocketService.subscribe('disconnected', () => {
      if (mounted) {
        setIsConnected(false)
        setConnectionState(prev => ({ ...prev, connected: false, reconnecting: true }))
      }
    })
    
    const unsubscribeError = websocketService.subscribe('error', (data) => {
      if (mounted) {
        setConnectionState(prev => ({ ...prev, error: data.error || 'WebSocket error', connecting: false }))
      }
    })

    // Initialize connection
    initConnection()

    return () => {
      mounted = false
      unsubscribeConnected()
      unsubscribeDisconnected()
      unsubscribeError()
    }
  }, []) // Empty deps - run ONCE

  // Handle page visibility changes with smart disconnect logic
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) {
        // Page hidden - set timer to disconnect after 10 seconds
        const timer = setTimeout(() => {
          websocketService.disconnect()
          setIsConnected(false)
        }, 10000) // 10 seconds delay
        
        setDisconnectTimer(timer)
      } else {
        // Page visible - cancel disconnect timer and reconnect if needed
        if (disconnectTimer) {
          clearTimeout(disconnectTimer)
          setDisconnectTimer(null)
        }
        
        // Check if we actually need to reconnect 
        const needsReconnect = !websocketService.isWebSocketConnected() || !isConnected
        if (needsReconnect) {
          setConnectionState(prev => ({ ...prev, reconnecting: true }))
          
          // Get user data and reconnect
          const reconnect = async () => {
            try {
              let userId: number | null = null
              try {
                const user = initData.user()
                userId = user?.id || 123456
              } catch {
                userId = 123456
              }

              if (userId) {
                const initDataStr = initData.raw() || 'development'
                const success = await websocketService.connect(userId, initDataStr)
                
                setIsConnected(success)
                setConnectionState({
                  connecting: false,
                  reconnecting: false,
                  error: success ? null : 'Reconnection failed'
                })
                
                // Hooks will automatically re-subscribe when isConnected becomes true
              }
            } catch (error) {
              setConnectionState({
                connecting: false,
                reconnecting: false,
                error: error instanceof Error ? error.message : String(error)
              })
            }
          }
          
          reconnect()
        }
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      if (disconnectTimer) {
        clearTimeout(disconnectTimer)
      }
    }
  }, [disconnectTimer, isConnected])

  // Stable subscribe function
  const subscribe = (event: EventType, callback: (data: any) => void) => {
    return websocketService.subscribe(event, callback)
  }

  const contextValue: WebSocketContextType = {
    isConnected,
    subscribe,
    connectionState
  }

  return (
    <WebSocketContext.Provider value={contextValue}>
      {children}
    </WebSocketContext.Provider>
  )
}

export function useWebSocketContext() {
  const context = useContext(WebSocketContext)
  if (!context) {
    throw new Error('useWebSocketContext must be used within WebSocketProvider')
  }
  return context
}