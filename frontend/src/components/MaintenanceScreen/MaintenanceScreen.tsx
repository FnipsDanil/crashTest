import React from 'react'
import { useTranslation } from 'react-i18next'
import './MaintenanceScreen.css'

interface MaintenanceScreenProps {
  onRetry?: () => void
}

export const MaintenanceScreen: React.FC<MaintenanceScreenProps> = ({ onRetry }) => {
  const { t } = useTranslation()

  return (
    <div className="maintenance-screen">
      <div className="maintenance-container">
        <div className="maintenance-icon">🔧</div>
        <h1 className="maintenance-title">{t('maintenance.title')}</h1>
        <p className="maintenance-message">
          {t('maintenance.message')}
        </p>
        {onRetry && (
          <button className="maintenance-retry-btn" onClick={onRetry}>
            {t('maintenance.retry')}
          </button>
        )}
        <div className="maintenance-footer">
          <p>{t('maintenance.footer')}</p>
        </div>
      </div>
    </div>
  )
}

export default MaintenanceScreen