import { useState, useEffect } from "react"
import { useTranslation } from 'react-i18next'
import { initData, popup } from '@telegram-apps/sdk-react'
import PaymentModal from '../PaymentModal/PaymentModal'
import GiftRequests from '../GiftRequests/GiftRequests'
import { useBalance } from '../../contexts/BalanceContextWebSocket'

interface TelegramUser {
  id: number
  first_name?: string
  last_name?: string
  username?: string
  photo_url?: string
}

interface UserStats {
  total_games: number
  games_won: number
  games_lost: number
  total_wagered: number
  total_won: number
  best_multiplier: number
  avg_multiplier: number
}

export default function Profile() {
  const { t } = useTranslation()
  const [user, setUser] = useState<TelegramUser | null>(null)
  // 🚀 OPTIMIZATION: Use balance from context instead of direct HTTP requests
  const { balance, updateBalance } = useBalance()
  const [stats, setStats] = useState<UserStats | null>(null)
  const [referralCode, setReferralCode] = useState("")
  const [referralsCount, setReferralsCount] = useState(0)
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false)
  const [showGiftRequests, setShowGiftRequests] = useState(false)
  const [showChannelBonus, setShowChannelBonus] = useState(false)
  const [refundAmount, setRefundAmount] = useState(100)
  const [isRefunding, setIsRefunding] = useState(false)
  
  // 🎯 NEW: Channel subscription bonus state
  const [channelBonus, setChannelBonus] = useState({
    available: true,
    claimed: false,
    loading: false,
    error: '',
    featureEnabled: true,  // FORCE ENABLE FOR TEST
    config: null as any     // Store configuration from PostgreSQL
  })
  
  // 🎯 NEW: Promo code state
  const [promoCode, setPromoCode] = useState({
    inputValue: '',
    loading: false,
    error: '',
    history: [] as any[]
  })
  
  useEffect(() => {
    // Получаем данные пользователя из Telegram SDK
    const timeout = setTimeout(() => {
      console.error('Profile loading timeout - Telegram data not available')
      // No fallback user data in production
    }, 5000) // 5 second timeout for user initialization
    
    const initializeProfile = async () => {
      try {
      // 🔄 RETRY LOGIC: Wait for Telegram SDK to be ready (like in Leaderboard.tsx)
      let user = initData.user()
      let retries = 0
      while (!user?.id && retries < 3) {
        console.log(`Profile: Retry ${retries + 1} for initData.user()`)
        await new Promise(resolve => setTimeout(resolve, 200 * (retries + 1)))
        user = initData.user()
        retries++
      }
      
      if (user) {
        clearTimeout(timeout)
        setUser({
          id: user.id,
          first_name: user.first_name,
          last_name: user.last_name,
          username: user.username,
          photo_url: user.photo_url
        })
        
        // Генерируем реферальный код на основе ID
        setReferralCode(`CRASH${user.id}`)
        
        // 🚀 OPTIMIZATION: Load only stats - balance comes from context
        fetchStats(user.id)
        } else {
          clearTimeout(timeout)
          console.warn('No user data available from Telegram SDK')
          // No fallback user data in production
        }
      } catch (e) {
        clearTimeout(timeout)
        console.warn(t('console.telegramDataError'), e)
        // No fallback user data in production
      }
      
      // Already checked in separate useEffect
    }
    
    // Call async initialization
    initializeProfile()
  }, [])

  // 🔄 SEPARATE useEffect to check all bonus statuses on startup
  useEffect(() => {
    checkAllBonusStatuses()
  }, [])
  
  // 🚀 COMPRESSED: Get all bonus statuses in one request on app startup
  const checkAllBonusStatuses = async () => {
    try {
      const { apiService } = await import('../../services/api')
      
      // 🔒 SECURITY: Set init_data for authentication
      const telegramInitData = initData.raw()
      if (telegramInitData) {
        apiService.setInitData(telegramInitData)
      }
      
      const bonusStatus = await apiService.getUserBonusStatus()
      
      // Update channel bonus status
      setChannelBonus(prev => ({ 
        ...prev, 
        available: bonusStatus.channel_bonus.available,
        claimed: bonusStatus.channel_bonus.claimed,
        featureEnabled: bonusStatus.channel_bonus.enabled,
        config: bonusStatus.channel_bonus.config
      }))
      
    } catch (e) {
      // On error, disable features to avoid broken UI
      setChannelBonus(prev => ({ 
        ...prev, 
        available: false,
        claimed: false,
        featureEnabled: false,
        config: null 
      }))
    }
  }
  
  // 🚀 OPTIMIZATION: Removed fetchBalance - now using BalanceContext

  const fetchStats = async (userId: number) => {
    try {
      const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"
      
      const headers: Record<string, string> = {
        "Content-Type": "application/json"
      }
      
      // Add Telegram auth header with retry logic
      let telegramInitData = initData.raw()
      let retries = 0
      while (!telegramInitData && retries < 3) {
        console.log(`Profile fetchStats: Retry ${retries + 1} for init_data`)
        await new Promise(resolve => setTimeout(resolve, 200 * (retries + 1)))
        telegramInitData = initData.raw()
        retries++
      }
      
      if (telegramInitData) {
        headers["X-Telegram-Init-Data"] = telegramInitData
      } else {
        console.warn('Profile fetchStats: No init_data available - proceeding without auth')
      }
      
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 5000) // 5 second timeout
      
      const res = await fetch(`${API_URL}/user-stats/${userId}`, {
        headers,
        signal: controller.signal
      })
      
      clearTimeout(timeoutId)
      
      if (res.ok) {
        const data = await res.json()
        setStats({
          total_games: data.total_games,
          games_won: data.games_won,
          games_lost: data.games_lost,
          total_wagered: data.total_wagered,
          total_won: data.total_won,
          best_multiplier: data.best_multiplier,
          avg_multiplier: data.avg_multiplier
        })
      } else {
        console.warn('Failed to fetch stats:', res.status, res.statusText)
      }
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') {
        console.warn('Profile fetchStats: Request timed out')
      } else {
        console.error(t('console.statisticsError'), e)
      }
    }
  }
  
  const copyReferralLink = async () => {
    const link = `https://t.me/your_bot?start=${referralCode}`
    try {
      await navigator.clipboard.writeText(link)
      popup.open({
        title: '📋 Ссылка скопирована',
        message: t('alerts.linkCopied'),
        buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
      }).catch(() => {
        console.error('Failed to show popup:', t('alerts.linkCopied'))
      })
    } catch (e) {
      popup.open({
        title: '📋 Реферальная ссылка',
        message: t('alerts.referralLinkAlert', { link }),
        buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
      }).catch(() => {
        console.error('Failed to show popup:', t('alerts.referralLinkAlert', { link }))
      })
    }
  }

  const handlePaymentSuccess = (amount: number) => {
    popup.open({
      title: '💳 Платеж создан',
      message: t('alerts.paymentCreated', { amount }),
      buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
    }).catch(() => {
      console.error('Failed to show popup:', t('alerts.paymentCreated', { amount }))
    })
    // 🚀 OPTIMIZATION: Refresh balance and stats after refund - balance now comes from context  
    setTimeout(() => {
      if (user) {
        updateBalance() // Refresh balance from context
        fetchStats(user.id)
      }
    }, 3000)
  }

  const handleRefund = async () => {
    if (!user || refundAmount < 1 || refundAmount > balance) {
      popup.open({
        title: '❌ Неверная сумма',
        message: t('alerts.invalidAmount'),
        buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
      }).catch(() => {
        console.error('Failed to show popup:', t('alerts.invalidAmount'))
      })
      return
    }

    try {
      setIsRefunding(true)
      const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"
      const res = await fetch(`${API_URL}/refund-balance/${user.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: user.id, amount: refundAmount })
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Refund error')
      }

      const data = await res.json()
      // 🚀 OPTIMIZATION: Update balance through context instead of direct setState
      updateBalance(data.new_balance)
      popup.open({
        title: '✅ Возврат выполнен',
        message: t('alerts.refundSuccess', { amount: refundAmount, balance: data.new_balance }),
        buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
      }).catch(() => {
        console.error('Failed to show popup:', t('alerts.refundSuccess', { amount: refundAmount, balance: data.new_balance }))
      })
      setRefundAmount(100)
    } catch (e) {
      console.error(t('console.refundError'), e)
      popup.open({
        title: '❌ Ошибка возврата',
        message: t('alerts.refundError', { error: e instanceof Error ? e.message : t('errors.unknown') }),
        buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
      }).catch(() => {
        console.error('Failed to show popup:', t('alerts.refundError', { error: e instanceof Error ? e.message : t('errors.unknown') }))
      })
    } finally {
      setIsRefunding(false)
    }
  }

  // 🎯 NEW: Channel subscription bonus handler
  const checkChannelSubscription = async () => {
    if (!user) return
    
    setChannelBonus(prev => ({ ...prev, loading: true, error: '' }))
    
    try {
      // 🚀 КРИТИЧНО: Используем API service для сжатых данных и автоматической аутентификации
      const { apiService } = await import('../../services/api')
      
      // 🔒 SECURITY: Set init_data for authentication (temporary fix until global auth works)
      const telegramInitData = initData.raw()
      if (telegramInitData) {
        apiService.setInitData(telegramInitData)
      }
      
      // Get first available channel from PostgreSQL config
      const firstChannel = channelBonus.config?.channels ? Object.keys(channelBonus.config.channels)[0] : "@your_channel"
      console.log('🔍 DEBUG: Using channel:', firstChannel)
      
      const result = await apiService.checkChannelSubscription(firstChannel)
      
      if (result.success) {
        // Bonus granted successfully
        setChannelBonus(prev => ({
          ...prev,
          available: false,
          claimed: true,
          loading: false,
          error: ''
        }))
        
        // Update balance and stats
        updateBalance()
        if (user) {
          fetchStats(user.id)
        }
        
        // ✅ ИСПОЛЬЗУЕМ: Telegram popup для успешного бонуса
        popup.open({
          title: '🎉 Бонус получен!',
          message: t('alerts.channelBonusSuccess', { amount: result.bonus_amount }),
          buttons: [{ id: 'ok', type: 'default', text: 'Отлично!' }]
        }).catch(() => {
          console.error('Failed to show popup:', `🎉 ${t('alerts.channelBonusSuccess', { amount: result.bonus_amount })}`)
        })
      } else {
        // Bonus denied (not subscribed, already claimed, etc.)
        const error = result.error || 'Unknown error'
        setChannelBonus(prev => ({
          ...prev,
          loading: false,
          error: error
        }))
        
        if (error === 'Bonus already claimed for this channel') {
          setChannelBonus(prev => ({
            ...prev,
            available: false,
            claimed: true
          }))
        }
        
        // Handle specific error messages with translations
        let errorMessage = error
        if (error.includes('user_not_found')) {
          errorMessage = t('alerts.userNotFound')
        } else if (error.includes('not_subscribed') || error.includes('Not subscribed to channel')) {
          errorMessage = t('alerts.notSubscribed')
        } else if (error.includes('Bonus already claimed')) {
          errorMessage = t('alerts.bonusAlreadyClaimed')
        } else {
          errorMessage = t('alerts.channelBonusError', { error })
        }
        
        // ✅ ИСПОЛЬЗУЕМ: Telegram popup для ошибок channel bonus
        popup.open({
          title: '❌ Ошибка бонуса',
          message: errorMessage,
          buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
        }).catch(() => {
          console.error('Failed to show popup:', `❌ ${errorMessage}`)
        })
      }
    } catch (e) {
      console.error('Channel subscription check error:', e)
      
      const errorMessage = e instanceof Error ? e.message : t('errors.unknown')
      setChannelBonus(prev => ({
        ...prev,
        loading: false,
        error: errorMessage
      }))
      
      // Handle specific error messages with translations
      let displayError = errorMessage
      if (errorMessage.includes('user_not_found')) {
        displayError = t('alerts.userNotFound')
      } else if (errorMessage.includes('not_subscribed')) {
        displayError = t('alerts.notSubscribed')
      } else if (errorMessage.includes('Bonus already claimed')) {
        displayError = t('alerts.bonusAlreadyClaimed')
      } else {
        displayError = t('alerts.channelBonusError', { error: errorMessage })
      }
      
      // ✅ ИСПОЛЬЗУЕМ: Telegram popup для ошибок channel bonus (catch блок)
      popup.open({
        title: '❌ Ошибка бонуса',
        message: displayError,
        buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
      }).catch(() => {
        console.error('Failed to show popup:', `❌ ${displayError}`)
      })
    }
  }

  // 🎯 NEW: Promo code usage handler
  const usePromoCode = async () => {
    if (!user || !promoCode.inputValue.trim()) return
    
    setPromoCode(prev => ({ ...prev, loading: true, error: '' }))
    
    try {
      // 🚀 КРИТИЧНО: Используем API service для автоматической аутентификации
      const { apiService } = await import('../../services/api')
      
      // 🔒 SECURITY: Set init_data for authentication
      const telegramInitData = initData.raw()
      if (telegramInitData) {
        apiService.setInitData(telegramInitData)
      } else {
        throw new Error('Telegram authentication data not available')
      }
      
      const result = await apiService.usePromoCode(promoCode.inputValue.trim())
      
      if (result.success) {
        // Promo code used successfully
        setPromoCode(prev => ({
          ...prev,
          inputValue: '',
          loading: false,
          error: ''
        }))
        
        // Update balance and stats
        updateBalance()
        if (user) {
          fetchStats(user.id)
        }
        
        const withdrawalMsg = result.withdrawal_requirement 
          ? t('profile.promoCodeWithdrawal', { amount: result.withdrawal_requirement })
          : ''
        
        // ✅ ИСПОЛЬЗУЕМ: Telegram popup для успешной активации
        popup.open({
          title: '🎉 Промокод активирован!',
          message: t('profile.promoCodeSuccess', { amount: result.bonus_amount, withdrawal: withdrawalMsg }),
          buttons: [{ id: 'ok', type: 'default', text: 'Отлично!' }]
        }).catch(() => {
          console.error('Failed to show popup:', `🎉 ${t('profile.promoCodeSuccess', { amount: result.bonus_amount, withdrawal: withdrawalMsg })}`)
        })
      } else {
        // Promo code denied
        const error = result.error || 'Unknown error'
        setPromoCode(prev => ({
          ...prev,
          loading: false,
          error: error
        }))
        
        // Handle specific error messages with translations
        let errorMessage = error
        if (error.includes('not found')) {
          errorMessage = t('profile.promoCodeNotFound')
        } else if (error.includes('already used')) {
          errorMessage = t('profile.promoCodeAlreadyUsed')
        } else if (error.includes('expired')) {
          errorMessage = t('profile.promoCodeExpired')
        } else if (error.includes('no uses left')) {
          errorMessage = t('profile.promoCodeExhausted')
        } else if (error.includes('Invalid promo code format')) {
          errorMessage = t('profile.promoCodeInvalidFormat')
        }
        
        // ✅ ИСПРАВЛЕНИЕ: Используем Telegram popup вместо alert
        setTimeout(() => {
          popup.open({
            title: '❌ Ошибка промокода',
            message: errorMessage,
            buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
          }).catch(() => {
            console.error('Failed to show popup:', `❌ ${errorMessage}`)
          })
        }, 50)
      }
    } catch (e) {
      console.error('Promo code usage error:', e)
      
      const errorMessage = e instanceof Error ? e.message : 'Unknown error'
      setPromoCode(prev => ({
        ...prev,
        loading: false,
        error: errorMessage
      }))
      
      // ✅ ИСПРАВЛЕНИЕ: Используем Telegram popup вместо alert
      setTimeout(() => {
        popup.open({
          title: '❌ Ошибка промокода',
          message: t('profile.promoCodeError', { error: errorMessage }),
          buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
        }).catch(() => {
          console.error('Failed to show popup:', `❌ ${t('profile.promoCodeError', { error: errorMessage })}`)
        })
      }, 50)
    }
  }

  if (!user) {
    return (
      <div className="profile-container">
        <div className="loading-spinner">
          <div className="spinner"></div>
          <p>{t('profile.loadingProfile')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="profile-container">

      <div className="profile-sections">
        <div className="section">
          <h3>{t('profile.statisticsTitle')}</h3>
          <div className="stats-grid">
            <div className="stat-item">
              <span className="stat-label">{t('profile.gamesPlayedLabel')}</span>
              <span className="stat-value">{stats?.total_games ?? '-'}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">{t('profile.totalWinLabel')}</span>
              <span className="stat-value">{stats?.total_won ? `${stats.total_won} ⭐` : '-'}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">{t('profile.bestMultiplierLabel')}</span>
              <span className="stat-value">{stats?.best_multiplier ? `${Number(stats.best_multiplier).toFixed(2)}x` : '-'}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">{t('profile.avgMultiplierLabel')}</span>
              <span className="stat-value">{stats?.avg_multiplier ? `${Number(stats.avg_multiplier).toFixed(2)}x` : '-'}</span>
            </div>
          </div>
        </div>

        <div className="section">
          <div className="section-header">
            <h3 
              onClick={() => setShowGiftRequests(!showGiftRequests)}
              className={`section-header-toggle ${showGiftRequests ? 'expanded' : ''}`}  
            >
              {t('profile.giftsTitle')}
              <span className="toggle-arrow">►</span>
            </h3>
          </div>
          <GiftRequests isOpen={showGiftRequests} />
        </div>

        <div className="section">
          <div className="section-header">
            <h3 
              onClick={() => setShowChannelBonus(!showChannelBonus)}
              className={`section-header-toggle ${showChannelBonus ? 'expanded' : ''}`}  
            >
              {t('profile.bonusesTitle')}
              <span className="toggle-arrow">►</span>
            </h3>
          </div>
          {showChannelBonus && (
            <div className="bonus-content">
              {channelBonus.featureEnabled && channelBonus.available && !channelBonus.claimed && (
                <div className="bonus-section">
                  <p 
                    className="bonus-description"
                    dangerouslySetInnerHTML={{
                      __html: t('profile.bonusDescription', { amount: channelBonus.config?.default_bonus_amount || 5 })
                    }}
                  />
                  <button 
                    className="game-btn start bonus-button"
                    onClick={checkChannelSubscription}
                    disabled={channelBonus.loading}
                  >
                    {channelBonus.loading ? t('profile.checkingBonus') : t('profile.getBonusButton')}
                  </button>
                </div>
              )}
              
              <div className="bonus-section">
                <h4>{t('profile.promoCodeTitle')}</h4>
                <div className="promo-code-input-section">
                  <input
                    type="text"
                    placeholder={t('profile.promoCodePlaceholder')}
                    value={promoCode.inputValue}
                    onChange={(e) => setPromoCode(prev => ({ ...prev, inputValue: e.target.value.toUpperCase(), error: '' }))}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !promoCode.loading && promoCode.inputValue.trim()) {
                        usePromoCode()
                      }
                    }}
                    className="promo-code-input"
                    maxLength={50}
                    disabled={promoCode.loading}
                  />
                  <button 
                    className="game-btn start promo-button"
                    onClick={usePromoCode}
                    disabled={promoCode.loading || !promoCode.inputValue.trim()}
                  >
                    {promoCode.loading ? t('profile.promoCodeActivating') : t('profile.promoCodeActivate')}
                  </button>
                </div>
                {promoCode.error && (
                  <p className="promo-error">{promoCode.error}</p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* <div className="section">
          <h3>👥 Реферальная программа</h3>
          <div className="referral-section">
            <p className="referral-description">
              Приглашайте друзей и получайте 10% с их выигрышей!
            </p>
            <div className="referral-stats">
              <div className="referral-stat">
                <span>Приглашено друзей</span>
                <span className="referral-count">{referralsCount}</span>
              </div>
              <div className="referral-stat">
                <span>Заработано</span>
                <span className="referral-earnings">0 ⭐</span>
              </div>
            </div>
            <div className="referral-code-section">
              <p>Ваш реферальный код:</p>
              <div className="referral-code">{referralCode}</div>
              <button className="copy-button" onClick={copyReferralLink}>
                📋 Скопировать ссылку
              </button>
            </div>
          </div>
        </div> */}

        {/*<div className="section test-section">
          <h3>{t('profile.testingTitle')}</h3>
          <div className="test-controls">
            <p>{t('profile.refundStarsLabel')}</p>
            <div className="refund-controls">
              <input
                type="number"
                min="1"
                max={balance}
                value={refundAmount}
                onChange={(e) => setRefundAmount(Math.max(1, Math.min(balance, parseInt(e.target.value) || 1)))}
                className="refund-input"
                disabled={isRefunding}
              />
              <button
                className="refund-button"
                onClick={handleRefund}
                disabled={isRefunding || refundAmount < 1 || refundAmount > balance || balance === 0}
              >
                {isRefunding ? t('profile.refunding') : t('profile.refund', { amount: refundAmount })}
              </button>
            </div>
            <p className="test-note">
              {t('profile.testingNoteText')}
            </p>
          </div>
        </div>*/}
      </div>

      <PaymentModal
        isOpen={isPaymentModalOpen}
        onClose={() => setIsPaymentModalOpen(false)}
        onSuccess={handlePaymentSuccess}
      />
    </div>
  )
}