import { useEffect } from 'react'
import { initData, init, swipeBehavior, viewport } from '@telegram-apps/sdk-react'
import Header from './components/Header/Header'
import { BalanceProvider } from './contexts/BalanceContextWebSocket'
import { ErrorProvider } from './contexts/ErrorContext'
import { WebSocketProvider } from './contexts/WebSocketContext'
import ErrorBoundary from './components/ErrorBoundary/ErrorBoundary'
import { useTranslation } from 'react-i18next'
import IndexPage from './routes/ReactRouter'

import './App.css'

function AppContent() {
  const { i18n } = useTranslation()

  useEffect(() => {
    const initializeLanguage = async () => {
      try {
        if (initData.raw()) {
          const user = initData.user()
          const rawData = initData.raw()

          // 🔒 CRITICAL: Set init_data for API authentication first
          if (rawData && user?.id) {
            const { apiService } = await import('./services/api')
            apiService.setInitData(rawData)
            
            try {
              // 🎯 NEW: Load language from database with priority logic
              const languageResponse = await apiService.getUserLanguage(user.id)
              const dbLanguage = languageResponse.language_code
              
              if (dbLanguage && ['ru', 'en'].includes(dbLanguage)) {
                i18n.changeLanguage(dbLanguage)
              } else {
                throw new Error('No valid language in database')
              }
            } catch (dbError) {
              // Fallback 1: localStorage first (user's manual choice has priority)
              const storedLang = localStorage.getItem('i18nextLng')
              if (storedLang && ['ru', 'en'].includes(storedLang)) {
                i18n.changeLanguage(storedLang)
                
                // Save to database for future use
                try {
                  await apiService.setUserLanguage(user.id, storedLang)
                } catch (saveError) {
                  // Silent fail - not critical
                }
              } else if (user?.language_code) {
                // Fallback 2: Telegram language (only if no localStorage)
                const telegramLang = user.language_code.toLowerCase()
                const supportedLang = ['ru', 'en'].includes(telegramLang) ? telegramLang : 'en'
                i18n.changeLanguage(supportedLang)
              } else {
                // Fallback 3: default 'en'
                i18n.changeLanguage('en')
              }
            }
            
            // 🎯 Verify user and create in database on app entry
            try {
              const result = await apiService.verifyUser(rawData)
              if (!result.valid) {
                console.error("User verification failed:", result.error)
              }
            } catch (error) {
              console.error("Error verifying user:", error)
            }
          } else {
            // No user or rawData - fallback to localStorage/default
            const storedLang = localStorage.getItem('i18nextLng') || 'en'
            const finalLang = ['ru', 'en'].includes(storedLang) ? storedLang : 'en'
            i18n.changeLanguage(finalLang)
          }
        } else {
          // No init data - fallback to localStorage/default
          const storedLang = localStorage.getItem('i18nextLng') || 'en'
          const finalLang = ['ru', 'en'].includes(storedLang) ? storedLang : 'en'
          i18n.changeLanguage(finalLang)
        }
      } catch (error) {
        console.error("Error during language initialization:", error)
        // Ultimate fallback - try to use Telegram language first, then 'en'
        try {
          const user = initData.user()
          if (user?.language_code) {
            const telegramLang = user.language_code.toLowerCase()
            const supportedLang = ['ru', 'en'].includes(telegramLang) ? telegramLang : 'en'
            i18n.changeLanguage(supportedLang)
          } else {
            i18n.changeLanguage('en')
          }
        } catch {
          i18n.changeLanguage('en') // Final fallback
        }
      }
    }

    initializeLanguage()
  }, [i18n])

  return (
    <div className="app-container">
      <Header />
      <main className="app-main">
        <IndexPage />
      </main>
    </div>
  )
}

export default function App() {
  // Initialize Telegram SDK v3.x
  useEffect(() => {
    try {
      init()
      
      // Additional swipe behavior configuration as fallback
      setTimeout(() => {
        if (swipeBehavior.mount.isAvailable() && !swipeBehavior.isMounted()) {
          swipeBehavior.mount()
        }
        if (swipeBehavior.disableVertical.isAvailable()) {
          swipeBehavior.disableVertical()
        }
      }, 100)
      
    } catch (error) {
      console.warn('Failed to initialize Telegram SDK:', error)
    }
  }, [])

  return (
    <ErrorBoundary>
      <ErrorProvider>
        <WebSocketProvider>
          <BalanceProvider>
            <AppContent />
          </BalanceProvider>
        </WebSocketProvider>
      </ErrorProvider>
    </ErrorBoundary>
  )
}