import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { initData } from '@telegram-apps/sdk-react'
import './LanguageSwitcher.css'

export default function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const [isChanging, setIsChanging] = useState(false)

  const currentLang = i18n.language

  const changeLanguage = async (lng: string) => {
    if (isChanging || lng === currentLang) return
    
    setIsChanging(true)
    
    try {
      // Change language immediately for UI responsiveness
      i18n.changeLanguage(lng)
      
      // Try to save to database if user is available
      const user = initData.user()
      const rawData = initData.raw()
      
      if (user?.id && rawData) {
        const { apiService } = await import('../../services/api')
        apiService.setInitData(rawData)
        
        try {
          await apiService.setUserLanguage(user.id, lng)
        } catch (error) {
          console.warn('⚠️ Could not save language to database:', error)
          // Language is still changed in UI, so this is not critical
        }
      } else {
        console.warn('⚠️ No user data available, language saved only locally')
      }
    } catch (error) {
      console.error('❌ Error changing language:', error)
      // Revert language change on error
      i18n.changeLanguage(currentLang)
    } finally {
      setIsChanging(false)
    }
  }

  return (
    <div className="lang-switcher">
      {['ru', 'en'].map((lng) => (
        <button
          key={lng}
          onClick={() => changeLanguage(lng)}
          className={`lang-btn ${currentLang === lng ? 'active' : ''} ${isChanging ? 'changing' : ''}`}
          disabled={isChanging}
        >
          {isChanging && lng === currentLang ? '⏳' : lng.toUpperCase()}
        </button>
      ))}
    </div>
  )
}
