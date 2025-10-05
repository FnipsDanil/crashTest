import React, { createContext, useContext, useState, ReactNode, useCallback } from 'react'
import MaintenanceScreen from '../components/MaintenanceScreen/MaintenanceScreen'
import { handleApiError } from '../hooks/useApiHealth'

interface ErrorContextType {
  showMaintenance: (error?: Error) => void
  hideMaintenance: () => void
  handleError: (error: Error) => void
  isMaintenanceMode: boolean
}

const ErrorContext = createContext<ErrorContextType | undefined>(undefined)

interface ErrorProviderProps {
  children: ReactNode
}

export const ErrorProvider: React.FC<ErrorProviderProps> = ({ children }) => {
  const [isMaintenanceMode, setIsMaintenanceMode] = useState(false)
  const [currentError, setCurrentError] = useState<Error | null>(null)

  const showMaintenance = useCallback((error?: Error) => {
    setCurrentError(error || null)
    setIsMaintenanceMode(true)
  }, [])

  const hideMaintenance = useCallback(() => {
    setCurrentError(null)
    setIsMaintenanceMode(false)
  }, [])

  const handleError = useCallback((error: Error) => {
    console.error('Global error handler:', error)

    // Проверяем нужно ли показывать экран технических работ
    // Только для серьезных сетевых ошибок
    if (handleApiError(error) && (error.message.includes('fetch') || error.message.includes('500'))) {
      showMaintenance(error)
    } else {
      // Для других ошибок просто логируем
      console.error('Non-critical error:', error)
    }
  }, [showMaintenance])

  const retryConnection = useCallback(() => {
    hideMaintenance()
    // Перезагружаем страницу для полного восстановления состояния
    window.location.reload()
  }, [hideMaintenance])

  const contextValue: ErrorContextType = {
    showMaintenance,
    hideMaintenance,
    handleError,
    isMaintenanceMode
  }

  if (isMaintenanceMode) {
    return <MaintenanceScreen onRetry={retryConnection} />
  }

  return (
    <ErrorContext.Provider value={contextValue}>
      {children}
    </ErrorContext.Provider>
  )
}

export const useError = () => {
  const context = useContext(ErrorContext)
  if (context === undefined) {
    throw new Error('useError must be used within an ErrorProvider')
  }
  return context
}