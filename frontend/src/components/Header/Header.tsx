import { useEffect, useState } from 'react'
import { initData } from '@telegram-apps/sdk-react'
import PaymentModal from '../PaymentModal/PaymentModal'
import { useBalance } from '../../contexts/BalanceContextWebSocket'
import './Header.css'

const CDN_BASE = 'https://vip.cdn-starcrash.com.ru'
const StarIcon = `${CDN_BASE}/asset/StarsIcon.webp`

export default function Header() {
  const { balance, addToBalance, refreshBalance } = useBalance()
  const [loading, setLoading] = useState(false)
  const [user, setUser] = useState<any>(null)
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false)

  useEffect(() => {
    // Get Telegram user data
    try {
      const telegramUser = initData.user()
      setUser(telegramUser)
    } catch (error) {
      console.warn('Could not get Telegram user data:', error)
    }
  }, [])

  const handleAddBalance = async () => {
    setIsPaymentModalOpen(true)
  }

  const handlePaymentSuccess = (amount: number) => {
    // Immediately update balance without waiting for server
    addToBalance(amount)
    // Also refresh from server to ensure accuracy after a short delay
    setTimeout(refreshBalance, 1000)
  }



  const displayName = user?.first_name
    ? `${user.first_name}${user.last_name ? ' ' + user.last_name : ''}`
    : user?.username || 'User'
  const avatarUrl = user?.photo_url

  return (
    <>
      <header className="app-header">
        <div className="user-section">
          <div className="user-avatar-container">
            {avatarUrl ? (
              <img src={avatarUrl} alt="Avatar" className="user-avatar-small" />
            ) : (
              <div className="user-avatar-placeholder-small">
                {displayName.charAt(0).toUpperCase()}
              </div>
            )}
          </div>
          <span className="user-name-compact">{displayName}</span>
        </div>

        <div className="balance-section">
          <img src={StarIcon} alt="Star" className="star-icon" />
          <span className="balance-amount-compact">
            {Math.floor(balance)}<span className="balance-decimals">.{((balance % 1) * 100).toFixed(0).padStart(2, '0')}</span>
          </span>
          <button 
            className="add-balance-btn-compact" 
            onClick={handleAddBalance}
            disabled={loading}
          >
            {loading ? '...' : '+'}
          </button>
        </div>
      </header>

      <PaymentModal
        isOpen={isPaymentModalOpen}
        onClose={() => setIsPaymentModalOpen(false)}
        onSuccess={handlePaymentSuccess}
      />
    </>
  )
}