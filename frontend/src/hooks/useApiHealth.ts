import { useState, useEffect, useCallback } from 'react'

interface ApiHealthState {
  isApiDown: boolean
  isChecking: boolean
  lastError: string | null
  retryCount: number
}

export const useApiHealth = () => {
  const [state, setState] = useState<ApiHealthState>({
    isApiDown: false,
    isChecking: false,
    lastError: null,
    retryCount: 0
  })

  const checkApiHealth = useCallback(async (): Promise<boolean> => {
    setState(prev => ({ ...prev, isChecking: true }))
    
    try {
      const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"
      const response = await fetch(`${API_URL}/health`, {
        method: 'GET',
        timeout: 5000 // 5 секунд таймаут
      } as RequestInit)

      if (response.ok) {
        setState(prev => ({ 
          ...prev, 
          isApiDown: false, 
          isChecking: false,
          lastError: null,
          retryCount: 0
        }))
        return true
      } else {
        throw new Error(`API responded with status: ${response.status}`)
      }
    } catch (error) {
      console.error('API Health Check failed:', error)
      setState(prev => ({ 
        ...prev, 
        isApiDown: true, 
        isChecking: false,
        lastError: error instanceof Error ? error.message : 'Unknown error',
        retryCount: prev.retryCount + 1
      }))
      return false
    }
  }, [])

  const retryApiConnection = useCallback(() => {
    checkApiHealth()
  }, [checkApiHealth])

  // Периодическая проверка API каждые 30 секунд если API недоступно
  useEffect(() => {
    let interval: NodeJS.Timeout | null = null
    
    if (state.isApiDown) {
      interval = setInterval(() => {
        checkApiHealth()
      }, 300000) // 5 минут - оптимизировано для production
    }

    return () => {
      if (interval) clearInterval(interval)
    }
  }, [state.isApiDown, checkApiHealth])

  // Проверка при монтировании компонента
  useEffect(() => {
    checkApiHealth()
  }, [checkApiHealth])

  return {
    ...state,
    checkApiHealth,
    retryApiConnection
  }
}

// Глобальный обработчик ошибок API
export const handleApiError = (error: any): boolean => {
  // Проверяем является ли это ошибкой сети/API
  const isNetworkError = 
    error?.message?.includes('fetch') ||
    error?.message?.includes('Network') ||
    error?.message?.includes('Failed to fetch') ||
    error?.name === 'TypeError' ||
    error?.code === 'NETWORK_ERROR' ||
    !navigator.onLine

  const isServerError = error?.response?.status >= 500

  return isNetworkError || isServerError
}

export default useApiHealth