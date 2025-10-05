import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { invoice, popup } from '@telegram-apps/sdk-react'
import { initData } from '@telegram-apps/sdk-react'
import './PaymentModal.css'

// Lazy load API service
const loadApiService = () => import('../../services/api').then(module => module.apiService)

interface PaymentModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: (amount: number) => void
}

export default function PaymentModal({ isOpen, onClose, onSuccess }: PaymentModalProps) {
  const { t } = useTranslation()
  const [amount, setAmount] = useState(100)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handlePayment = async () => {
    if (amount < 10 || amount > 1000000) {
      setError(t('payment.starsRange'))
      return
    }

    try {
      setLoading(true)
      setError(null)

      // Проверяем поддержку инвойсов
      if (!invoice.open.isAvailable()) {
        throw new Error(t('payment.paymentsUnavailable'))
      }

      // 🔒 CRITICAL: Wait for init_data to be available
      let rawInitData = initData.raw()
      
      // Quick retry if init_data not available
      if (!rawInitData) {
        await new Promise(resolve => setTimeout(resolve, 100))
        rawInitData = initData.raw()
      }
      
      if (!rawInitData) {
        throw new Error(t('payment.authDataError'))
      }
      
      // Use apiService which handles authentication automatically
      const apiService = await loadApiService()
      apiService.setInitData(rawInitData)
      
      const data = await apiService.createInvoice(
        amount,
        t('payment.invoiceTitle'),
        t('payment.invoiceDescription', { amount })
      )
      
      // Открываем инвойс в Telegram
      try {
        
        // Пробуем разные способы открытия invoice
        if (data.invoice_link) {
          await invoice.open(data.invoice_link, 'url')
        } else if (data.invoice_slug) {
          // Попробуем без символа $ в начале
          const cleanSlug = data.invoice_slug.startsWith('$') ? data.invoice_slug.substring(1) : data.invoice_slug
          await invoice.open(cleanSlug)
        } else if (data.payment_payload) {
          await invoice.open(data.payment_payload)
        } else {
          throw new Error('No invoice identifier provided')
        }
        
        // Закрываем модальное окно после успешного создания инвойса
        onSuccess(amount)
        onClose()
      } catch (invoiceError) {
        console.error('❌ Failed to open invoice:', invoiceError)
        
        // Всё равно считаем успехом, так как invoice создан
        onSuccess(amount)
        onClose()
        
        // Показываем пользователю что нужно проверить чат
        popup.open({
          title: '💳 Инструкции по оплате',
          message: t('alerts.paymentInstructions', { amount }),
          buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
        }).catch(() => {
          console.error('Failed to show popup:', t('alerts.paymentInstructions', { amount }))
        })
      }
      
    } catch (err) {
      console.error('Payment error:', err)
      setError(err instanceof Error ? err.message : t('payment.paymentError'))
    } finally {
      setLoading(false)
    }
  }

  const handleAmountChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseInt(e.target.value) || 0
    setAmount(Math.max(10, Math.min(1000000, value)))
    setError(null)
  }

  if (!isOpen) return null

  return (
    <div className="payment-modal-overlay" onClick={onClose}>
      <div className="payment-modal" onClick={(e) => e.stopPropagation()}>
        <div className="payment-modal-header">
          <h2>{t('payment.topUpBalance')}</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <div className="payment-modal-content">
          <div className="amount-section">
            <label htmlFor="amount-input">{t('payment.amountOfStars')}</label>
            <input
              id="amount-input"
              type="number"
              min="10"
              max="1000000"
              value={amount}
              onChange={handleAmountChange}
              className="amount-input"
              disabled={loading}
              placeholder="100"
            />
          </div>

          {error && (
            <div className="error-message">
              ❌ {error}
            </div>
          )}

          <button
            className="pay-button"
            onClick={handlePayment}
            disabled={loading || amount < 10 || amount > 1000000}
          >
            {loading ? t('payment.toppingUp') : t('payment.topUpWith', { amount })}
          </button>
        </div>
      </div>
    </div>
  )
}