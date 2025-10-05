import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { initData } from '@telegram-apps/sdk-react'
import type { PaymentRequest } from '../../types'
import './GiftRequests.css'

// Lazy load API service
const loadApiService = () => import('../../services/api').then(module => module.apiService)

interface GiftRequestsProps {
  isOpen: boolean
}

export default function GiftRequests({ isOpen }: GiftRequestsProps) {
  const { t } = useTranslation()
  const [requests, setRequests] = useState<PaymentRequest[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (isOpen) {
      loadPaymentRequests()
    }
  }, [isOpen])

  const loadPaymentRequests = async () => {
    try {
      setLoading(true)
      
      // Get init_data for authentication
      let rawInitData = initData.raw()
      if (!rawInitData) {
        await new Promise(resolve => setTimeout(resolve, 100))
        rawInitData = initData.raw()
      }
      
      if (!rawInitData) {
        console.error('🚨 GiftRequests: No init_data available')
        return
      }
      
      // Use apiService properly
      const apiService = await loadApiService()
      apiService.setInitData(rawInitData)
      
      const data = await apiService.getPaymentRequests()
      
      if (data.success) {
        setRequests(data.payment_requests || [])
      } else {
        console.error('Failed to load payment requests:', data.error)
      }
    } catch (error) {
      console.error('Error loading payment requests:', error)
    } finally {
      setLoading(false)
    }
  }

  const getStatusText = (status: PaymentRequest['status']) => {
    switch (status) {
      case 'pending':
        return t('gifts.processing')
      case 'approved':
        return t('gifts.sending')
      case 'completed':
        return t('gifts.sent')
      case 'canceled':
        return t('gifts.rejected')
      default:
        return status
    }
  }

  const getCancelReasonText = (reason: PaymentRequest['cancel_reason']) => {
    switch (reason) {
      case 'no_message':
        return t('gifts.cancelReasons.no_message')
      case 'price_changed':
        return t('gifts.cancelReasons.price_changed')
      case 'suspect_act':
        return t('gifts.cancelReasons.suspect_act')
      default:
        return null
    }
  }

  const getStatusClass = (status: PaymentRequest['status']) => {
    switch (status) {
      case 'pending':
        return 'status-pending'
      case 'approved':
        return 'status-approved'
      case 'completed':
        return 'status-completed'
      case 'canceled':
        return 'status-canceled'
      default:
        return 'status-default'
    }
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return null
    
    const date = new Date(dateString)
    return date.toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  if (!isOpen) return null

  return (
    <div className="gift-requests">
      {/* <div className="gift-requests-header">
        <p className="gift-requests-subtitle">История запросов на вывод</p>
      </div> */}

      {loading ? (
        <div className="gift-requests-loading">
          <div className="loading-spinner">
            <div className="spinner"></div>
            <p>{t('common.loading')}</p>
          </div>
        </div>
      ) : requests.length === 0 ? (
        <div className="gift-requests-empty">
          <div className="empty-icon">📭</div>
          <p>{t('gifts.noRequests')}</p>
          <span className="empty-hint">{t('gifts.buyUniqueGifts')}</span>
        </div>
      ) : (
        <div className="gift-requests-list">
          {requests.map((request) => (
            <div key={request.id} className="gift-request-card">
              <div className="gift-request-main">
                <div className="gift-request-icon">
                  {request.gift.emoji}
                </div>
                <div className="gift-request-info">
                  <div className="gift-request-name">
                    {request.gift_name}
                    {/* {request.gift.is_unique && <span className="unique-badge">⭐</span>} */}
                  </div>
                  <div className="gift-request-price">
                    ⭐ {request.price}
                  </div>
                </div>
                <div className={`gift-request-status ${getStatusClass(request.status)}`}>
                  {getStatusText(request.status)}
                </div>
              </div>
              
              <div className="gift-request-dates">
                <div className="gift-request-date">
                  <span className="date-label">{t('gifts.created')}</span>
                  <span className="date-value">
                    {formatDate(request.created_at)}
                  </span>
                </div>
                
                {request.status === 'completed' && request.completed_at && (
                  <div className="gift-request-date">
                    <span className="date-label">{t('gifts.sentAt')}</span>
                    <span className="date-value">
                      {formatDate(request.completed_at)}
                    </span>
                  </div>
                )}
                
                {request.status === 'canceled' && (
                  <div className="gift-request-support">
                    {getCancelReasonText(request.cancel_reason) ? (
                      <span className="cancel-reason-text">
                        ❌ {getCancelReasonText(request.cancel_reason)}
                      </span>
                    ) : (
                      <span className="support-text">
                        {t('gifts.contactSupport')}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}