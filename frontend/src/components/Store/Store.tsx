import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { initData, popup } from '@telegram-apps/sdk-react'
import { useBalance } from '../../contexts/BalanceContextWebSocket'
import './Store.css'

interface TelegramGift {
  id: string
  name: string
  description: string
  price: number
  ton_price?: number
  telegram_gift_id: string
  business_gift_id?: string
  emoji: string
  image_url?: string
  is_unique: boolean
}

type GiftTab = 'regular' | 'unique'

interface UserStats {
  wagered_balance: number
}

export default function Store() {
  const { t } = useTranslation()
  const [gifts, setGifts] = useState<TelegramGift[]>([])
  // 🚀 OPTIMIZATION: Use balance from context instead of direct HTTP requests
  const { balance, updateBalance } = useBalance()
  const [loading, setLoading] = useState(true)
  const [purchasing, setPurchasing] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<GiftTab>('regular')
  const [userStats, setUserStats] = useState<UserStats | null>(null)

  // Helper function for precise calculations
  const calculateRequiredWagered = (price: number): number => {
    return price / 2  // Exactly 50% of gift price
  }

  const calculateMissingWagered = (price: number, current: number): number => {
    const required = calculateRequiredWagered(price)
    return Math.max(0, required - current)
  }

  useEffect(() => {
    const loadData = async () => {
      const timeout = setTimeout(() => {
        console.error('Store loading timeout - forcing stop')
        setLoading(false)
      }, 10000) // 10 second timeout
      
      try {
        await loadGifts()
        await loadUserStats()
        // 🚀 OPTIMIZATION: Balance now comes from context - no need to load it here
      } catch (error) {
        console.error('Error loading store data:', error)
      } finally {
        clearTimeout(timeout)
        setLoading(false)
      }
    }
    loadData()
  }, [])

  const loadGifts = async () => {
    try {
      const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"
      
      const headers: Record<string, string> = {
        "Content-Type": "application/json"
      }
      
      // Add Telegram auth header with retry logic like Profile
      let telegramInitData = initData.raw()
      let retries = 0
      while (!telegramInitData && retries < 3) {
        console.log(`Store loadGifts: Retry ${retries + 1} for init_data`)
        await new Promise(resolve => setTimeout(resolve, 200 * (retries + 1)))
        telegramInitData = initData.raw()
        retries++
      }
      
      if (telegramInitData) {
        headers["X-Telegram-Init-Data"] = telegramInitData
      } else {
        console.warn('Store loadGifts: No init_data available - proceeding without auth')
      }
      
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 5000) // 5 second timeout
      
      const res = await fetch(`${API_URL}/gifts`, {
        headers,
        signal: controller.signal
      })
      
      clearTimeout(timeoutId)
      
      if (res.ok) {
        const data = await res.json()
        setGifts(data.gifts || [])
      } else {
        console.warn('Failed to load gifts:', res.status, res.statusText)
        setGifts([])
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.warn('Store loadGifts: Request timed out')
      } else {
        console.error('Failed to load gifts:', error)
      }
      setGifts([]) // Set empty array on error
    }
  }

  const loadUserStats = async () => {
    try {
      const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"
      
      const headers: Record<string, string> = {
        "Content-Type": "application/json"
      }
      
      // Add Telegram auth header with retry logic
      let telegramInitData = initData.raw()
      let retries = 0
      while (!telegramInitData && retries < 3) {
        console.log(`Store loadUserStats: Retry ${retries + 1} for init_data`)
        await new Promise(resolve => setTimeout(resolve, 200 * (retries + 1)))
        telegramInitData = initData.raw()
        retries++
      }
      
      if (!telegramInitData) {
        console.warn('Store loadUserStats: No init_data available - cannot get user stats')
        setUserStats({ wagered_balance: 0 })
        return
      }
      
      headers["X-Telegram-Init-Data"] = telegramInitData
      
      // Extract user ID from init data
      const urlParams = new URLSearchParams(telegramInitData)
      const userDataStr = urlParams.get('user')
      if (!userDataStr) {
        console.warn('Store loadUserStats: No user data in init_data')
        setUserStats({ wagered_balance: 0 })
        return
      }
      
      const userData = JSON.parse(userDataStr)
      const userId = userData.id
      
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 5000)
      
      const res = await fetch(`${API_URL}/user-stats/${userId}`, {
        headers,
        signal: controller.signal
      })
      
      clearTimeout(timeoutId)
      
      if (res.ok) {
        const data = await res.json()

        setUserStats({
          wagered_balance: parseFloat(data.wagered_balance) || 0
        })
      } else {
        console.warn('Failed to load user stats:', res.status, res.statusText)
        setUserStats({ wagered_balance: 0 })
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.warn('Store loadUserStats: Request timed out')
      } else {
        console.error('Failed to load user stats:', error)
      }
      setUserStats({ wagered_balance: 0 })
    }
  }

  // 🚀 OPTIMIZATION: Removed loadBalance - now using BalanceContext

  // Фильтрация подарков по активной вкладке
  const filteredGifts = gifts.filter(gift => 
    activeTab === 'unique' ? gift.is_unique : !gift.is_unique
  )

  const purchaseGift = async (giftId: string) => {
    // Check if this is a unique gift
    const gift = gifts.find(g => g.id === giftId)
    
    if (!gift) {
      popup.open({
        title: '❌ Подарок не найден',
        message: 'Gift not found',
        buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
      }).catch(() => {
        console.error('Failed to show popup: Gift not found')
      })
      return
    }
    
    if (gift.is_unique === true) {
      const giftBot = import.meta.env.VITE_GIFT_BOT_USERNAME || 'CrashStars'
      const confirmed = await popup.open({
        title: '⚠️ Важное предупреждение',
        message: t('store.importantWarning', { giftBot }),
        buttons: [
          { id: 'cancel', type: 'cancel' },
          { id: 'confirm', type: 'default', text: 'Подтвердить' }
        ]
      }).catch(() => null)
      
      if (confirmed !== 'confirm') {
        return
      }
    }
    
    if (gift.is_unique !== true) {
      // Confirmation for regular gifts
      const confirmed = await popup.open({
        title: '🎁 Подтверждение покупки',
        message: t('store.regularGiftConfirm', { price: gift.price }),
        buttons: [
          { id: 'cancel', type: 'cancel' },
          { id: 'confirm', type: 'default', text: 'Купить' }
        ]
      }).catch(() => null)
      
      if (confirmed !== 'confirm') {
        return
      }
    }
    
    setPurchasing(giftId)
    
    try {
      const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"
      
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        // 🛡️ Add idempotency key for duplicate request protection
        "X-Idempotency-Key": `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
      }
      
      // Add Telegram auth header with retry logic
      let telegramInitData = initData.raw()
      let retries = 0
      while (!telegramInitData && retries < 3) {
        console.log(`Store purchaseGift: Retry ${retries + 1} for init_data`)
        await new Promise(resolve => setTimeout(resolve, 200 * (retries + 1)))
        telegramInitData = initData.raw()
        retries++
      }
      
      if (!telegramInitData) {
        console.error('Store purchaseGift: No init_data available after retries')
        popup.open({
          title: '❌ Ошибка авторизации',
          message: t('store.authDataFailed'),
          buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
        }).catch(() => {
          console.error('Failed to show popup:', t('store.authDataFailed'))
        })
        return
      }
      
      headers["X-Telegram-Init-Data"] = telegramInitData
      
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 5000) // 5 second timeout
      
      const res = await fetch(`${API_URL}/purchase-gift`, {
        method: 'POST',
        headers,
        signal: controller.signal,
        body: JSON.stringify({ gift_id: giftId })
      })
      
      clearTimeout(timeoutId)
      
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}))
        throw new Error(errorData.error || `Purchase failed: ${res.status} ${res.statusText}`)
      }
      
      const data = await res.json()

      if (data.success) {
        // Open bot chat for unique gifts
        if (gift?.is_unique) {
          const giftBot = import.meta.env.VITE_GIFT_BOT_USERNAME || 'CrashStars'
          window.open(`https://t.me/${giftBot}`, '_blank')
          popup.open({
            title: '🎁 Подарок куплен!',
            message: t('store.giftPurchaseSuccess', { message: data.message }),
            buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
          }).catch(() => {
            console.error('Failed to show popup:', t('store.giftPurchaseSuccess', { message: data.message }))
          })
        } else {
          popup.open({
            title: '🎁 Подарок куплен!',
            message: t('store.giftPurchaseSuccess', { message: data.message || t('store.giftSentFallback', { name: data.gift_sent.name }) }),
            buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
          }).catch(() => {
            console.error('Failed to show popup:', t('store.giftPurchaseSuccess', { message: data.message || t('store.giftSentFallback', { name: data.gift_sent.name }) }))
          })
        }
        // 🚀 OPTIMIZATION: Don't update balance manually - WebSocket will send balance_update event
        // updateBalance(data.new_balance) // Removed to prevent double balance update
      } else {
        // Handle specific error messages from backend
        const errorMsg = data.error || data.message || t('store.purchaseError')
        
        // Handle promo code balance restriction
        if (errorMsg.includes('promo_balance_locked|')) {
          const parts = errorMsg.split('|')
          if (parts.length === 4) {
            const available = parts[1]
            const locked = parts[2] 
            const required = parts[3]
            popup.open({
              title: '🔒 Баланс заблокирован',
              message: t('store.promoBalanceLocked', { available, locked, required }),
              buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
            }).catch(() => {
              console.error('Failed to show popup:', t('store.promoBalanceLocked', { available, locked, required }))
            })
          } else {
            popup.open({
              title: '❌ Ошибка покупки',
              message: errorMsg,
              buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
            }).catch(() => {
              console.error('Failed to show popup:', errorMsg)
            })
          }
        } else if (errorMsg.includes('дневной лимит') || errorMsg.includes('daily limit')) {
          // Extract the limit number from the error message
          const match = errorMsg.match(/(\d+)\s*(?:шт\.|pcs)/);
          const limit = match ? match[1] : '5';
          popup.open({
            title: '⏰ Дневной лимит',
            message: t('store.dailyLimitMessage', { limit }),
            buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
          }).catch(() => {
            console.error('Failed to show popup:', t('store.dailyLimitMessage', { limit }))
          })
        } else if (errorMsg.includes('отыграть баланс') || errorMsg.includes('wager balance')) {
          popup.open({
            title: '🎯 Требуется отыгрыш',
            message: errorMsg,
            buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
          }).catch(() => {
            console.error('Failed to show popup:', errorMsg)
          })
        } else {
          popup.open({
            title: '❌ Ошибка покупки',
            message: errorMsg,
            buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
          }).catch(() => {
            console.error('Failed to show popup:', errorMsg)
          })
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.warn('Store purchaseGift: Request timed out')
        popup.open({
          title: '⏰ Тайм-аут запроса',
          message: t('store.requestTimeout'),
          buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
        }).catch(() => {
          console.error('Failed to show popup:', t('store.requestTimeout'))
        })
      } else {
        console.error('Purchase failed:', error)
        // Show specific error message for different error types
        if (error instanceof Error) {
          if (error.message.includes('promo_balance_locked|')) {
            const parts = error.message.split('|')
            if (parts.length === 4) {
              const available = parts[1]
              const locked = parts[2] 
              const required = parts[3]
              popup.open({
                title: '🔒 Баланс заблокирован',
                message: t('store.promoBalanceLocked', { available, locked, required }),
                buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
              }).catch(() => {
                console.error('Failed to show popup:', t('store.promoBalanceLocked', { available, locked, required }))
              })
            } else {
              popup.open({
                title: '❌ Ошибка покупки',
                message: error.message,
                buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
              }).catch(() => {
                console.error('Failed to show popup:', error.message)
              })
            }
          } else if (error.message.includes('отыграть баланс') || error.message.includes('wager balance')) {
            popup.open({
              title: '🎯 Требуется отыгрыш',
              message: error.message,
              buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
            }).catch(() => {
              console.error('Failed to show popup:', error.message)
            })
          } else if (error.message.includes('дневной лимит') || error.message.includes('daily limit')) {
            // Extract the limit number from the error message
            const match = error.message.match(/(\d+)\s*(?:шт\.|pcs)/);
            const limit = match ? match[1] : '5';
            popup.open({
              title: '⏰ Дневной лимит',
              message: t('store.dailyLimitMessage', { limit }),
              buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
            }).catch(() => {
              console.error('Failed to show popup:', t('store.dailyLimitMessage', { limit }))
            })
          } else {
            popup.open({
              title: '❌ Ошибка покупки',
              message: t('store.purchaseError'),
              buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
            }).catch(() => {
              console.error('Failed to show popup:', t('store.purchaseError'))
            })
          }
        } else {
          popup.open({
            title: '❌ Ошибка покупки',
            message: t('store.purchaseError'),
            buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
          }).catch(() => {
            console.error('Failed to show popup:', t('store.purchaseError'))
          })
        }
      }
    } finally {
      setPurchasing(null)
    }
  }

  if (loading) {
    return (
      <div className="store-container">
        <div className="loading-spinner">
          <div className="spinner"></div>
          <p>{t('store.loadingGiftsText')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="store-container">
      {/* Вкладки */}
      <div className="store-tabs">
        <button 
          className={`tab-button ${activeTab === 'regular' ? 'active' : ''}`}
          onClick={() => setActiveTab('regular')}
        >
          {t('store.regularTitle')}
        </button>
        <button 
          className={`tab-button ${activeTab === 'unique' ? 'active' : ''}`}
          onClick={() => setActiveTab('unique')}
        >
          {t('store.uniqueTitle')}
        </button>
      </div>

      <div className="withdrawal-info">
        {activeTab === 'regular' && (
          <p className="regular-gifts-warning">
            {t('store.regularWarning')}
          </p>
        )}
        <p>
          {/* {activeTab === 'unique' ? 
            // '⭐ Уникальные подарки выводятся в течение 24 часов' : 
            // '🎁 Выберите подарок для вывода в Telegram'
          } */}
        </p>
        <p className="wagered-balance-info">
          {t('store.wageredBalanceText', { balance: userStats?.wagered_balance ? Number(userStats.wagered_balance).toFixed(2) : '0.00' })}<br/>
          {t('store.need50percentText')}
        </p>
      </div>

      <div className="gifts-grid">
        {filteredGifts.map((gift) => (
          <div key={gift.id} className={`gift-card ${gift.is_unique ? 'unique' : ''}`}>
            <div className="gift-name">{gift.name}</div>
            <div className="gift-image-container">
              {gift.image_url ? (
                <img 
                  src={gift.image_url} 
                  alt={gift.name}
                  className="gift-image"
                  onError={(e) => {
                    // Fallback к эмодзи если изображение не загрузилось
                    e.currentTarget.style.display = 'none';
                    const nextSibling = e.currentTarget.nextElementSibling as HTMLElement;
                    if (nextSibling) {
                      nextSibling.style.display = 'block';
                    }
                  }}
                />
              ) : null}
              <div className="gift-emoji" style={{ display: gift.image_url ? 'none' : 'block' }}>
                {gift.emoji}
              </div>
            </div>
            <button
              className={`gift-price-btn ${
                balance < gift.price || 
                (userStats && userStats.wagered_balance < calculateRequiredWagered(gift.price)) 
                  ? 'disabled' : ''
              }`}
              onClick={() => purchaseGift(gift.id)}
              disabled={
                purchasing === gift.id || 
                balance < gift.price ||
                (userStats ? userStats.wagered_balance < calculateRequiredWagered(gift.price) : false)
              }
            >
              {purchasing === gift.id ? (
                <span>{t('store.sending')}</span>
              ) : balance < gift.price ? (
                <span>{t('store.buy', { price: gift.price })}</span>
              ) : (userStats && userStats.wagered_balance < calculateRequiredWagered(gift.price)) ? (
                <span>{t('store.needToWager', { amount: calculateMissingWagered(gift.price, userStats!.wagered_balance).toFixed(2) })}</span>
              ) : (
                <span>{t('store.buy', { price: gift.price })}</span>
              )}
            </button>
          </div>
        ))}
      </div>

      <div className="store-info">
        <p>{t('store.giftsSentText')}</p>
      </div>
    </div>
  )
}