import React, { Component, ReactNode } from 'react'
import { withTranslation, WithTranslation } from 'react-i18next'
import MaintenanceScreen from '../MaintenanceScreen/MaintenanceScreen'

interface Props extends WithTranslation {
  children: ReactNode
}

interface State {
  hasError: boolean
  apiDown: boolean
  retryCount: number
  errorMessage?: string
}

class ErrorBoundary extends Component<Props, State> {
  private retryTimer: NodeJS.Timeout | null = null

  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, apiDown: false, retryCount: 0 }
  }

  static getDerivedStateFromError(error: Error): State {
    const isNetworkError = error.message.includes('fetch') || 
                          error.message.includes('Network') ||
                          error.message.includes('Failed to fetch') ||
                          error.message.includes('HTTP error')

    return {
      hasError: true,
      apiDown: isNetworkError,
      retryCount: 0,
      errorMessage: error.message
    }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
    // Можно отправить в мониторинг ошибок
  }

  handleRetry = () => {
    this.setState(prev => ({
      hasError: false,
      apiDown: false,
      retryCount: prev.retryCount + 1,
      errorMessage: undefined
    }))

    if (this.state.retryCount >= 3) {
      this.retryTimer = setTimeout(() => {
        window.location.reload()
      }, 1000)
    }
  }

  componentWillUnmount() {
    if (this.retryTimer) clearTimeout(this.retryTimer)
  }

  render() {
    const { t } = this.props

    if (this.state.hasError) {
      return (
        <div style={{ padding: 20, color: 'white', backgroundColor: '#922', minHeight: '100vh' }}>
          <h1>{t('errors.occurred')}</h1>
          {this.state.apiDown && <p>{t('errors.networkOrApi')}</p>}
          <pre style={{ whiteSpace: 'pre-wrap', marginTop: 10 }}>{this.state.errorMessage}</pre>
          <button 
            onClick={this.handleRetry} 
            style={{ marginTop: 20, padding: '8px 16px', cursor: 'pointer' }}
          >
            {t('errors.tryAgain')}
          </button>
          {/* Если хочешь, можно заменить на MaintenanceScreen или оставить как есть */}
          {/* <MaintenanceScreen onRetry={this.handleRetry} /> */}
        </div>
      )
    }

    return this.props.children
  }
}

export default withTranslation()(ErrorBoundary)
