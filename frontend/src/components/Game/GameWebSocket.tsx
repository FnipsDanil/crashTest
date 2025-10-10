/**
 * Game component with WebSocket support - replaces polling
 * Optimized version that uses WebSocket instead of high-frequency HTTP requests
 */

import { useEffect, useState, useRef, useCallback } from "react"
import { Line } from "react-chartjs-2"
import { initData, popup } from '@telegram-apps/sdk-react'
import { useTranslation } from 'react-i18next'
import { useBalance } from '../../contexts/BalanceContextWebSocket'
import { useError } from '../../contexts/ErrorContext'
import { handleApiError } from '../../hooks/useApiHealth'
import { useGameState, useCrashHistory, usePlayerStatus } from '../../hooks/useWebSocketData'
import { useWebSocketContext } from '../../contexts/WebSocketContext'
import { FORCE_RELOAD_TIMESTAMP, VERSION } from "../../ForceReload"
import './Game.css'

const CDN_BASE = 'https://vip.cdn-starcrash.com.ru'
const StarIcon = `${CDN_BASE}/asset/StarsIcon.webp`
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
  Legend,
  ChartData,
  ChartOptions,
} from "chart.js"

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
  Legend
)

type CashoutResponse = {
  cashed_out: boolean
  coefficient: number
  balance?: number
}

export default function GameWebSocket() {
  const { t } = useTranslation()
  const { balance, updateBalance } = useBalance()
  const { handleError } = useError()
  
  // WebSocket connection and data - SINGLETON APPROACH
  const { isConnected: wsConnected, connectionState } = useWebSocketContext()
  const { gameState, loading: gameStateLoading, error: gameStateError } = useGameState()
  const { history: crashHistory, loading: historyLoading } = useCrashHistory()
  const { playerStatus } = usePlayerStatus()
  
  // Get user ID from Telegram
  const [userId, setUserId] = useState<number | null>(null)
  
  useEffect(() => {
    try {
      const user = initData.user()
      if (user?.id) {
        setUserId(user.id)
      } else {
        setUserId(123456) // Fallback for development
      }
    } catch (e) {
      console.warn("Could not get Telegram data, using fallback userId")
      setUserId(123456)
    }
  }, [])

  // Game state from WebSocket
  const [coefficient, setCoefficient] = useState(1)
  const [status, setStatus] = useState<"waiting" | "playing" | "crashed">("waiting")
  const [countdown, setCountdown] = useState(0)
  const [lastRoundCoefficient, setLastRoundCoefficient] = useState(1.0)
  const [currentGameHistory, setCurrentGameHistory] = useState<number[]>([1])
  
  // Player state
  const [betAmount, setBetAmount] = useState<number | string>(10)
  
  // Сброс состояния при переключении вкладок
  useEffect(() => {
    return () => {
      setBetAmount(10)
      setCashoutCoef("")
      setIsInGame(false)
      setPlayerJoined(false)
      setPlayerPlaying(false)
    }
  }, [])
  const [cashoutCoef, setCashoutCoef] = useState("")
  const [isInGame, setIsInGame] = useState(false)
  const [playerJoined, setPlayerJoined] = useState(false)
  const [playerPlaying, setPlayerPlaying] = useState(false)
  const [isAutomode, setIsAutomode] = useState(false)
  const [autoCashout, setAutoCashout] = useState("")
  
  // 🔒 SECURITY: Prevent rapid button clicks
  const [isJoining, setIsJoining] = useState(false)
  const [isCashingOut, setIsCashingOut] = useState(false)
  
  // UI state
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showWinMessage, setShowWinMessage] = useState(false)
  const [showCrashMessage, setShowCrashMessage] = useState(false)
  const [winAmount, setWinAmount] = useState(0)
  const [winMultiplier, setWinMultiplier] = useState(0)
  const [lastWinCoefficient, setLastWinCoefficient] = useState(0)
  const [lastCrashCoefficient, setLastCrashCoefficient] = useState(0)
  const [showResultTooltip, setShowResultTooltip] = useState(false)
  const [resultType, setResultType] = useState<"win" | "crash">("win")
  const [newItems, setNewItems] = useState<Set<number>>(new Set())
  const [resultMessage, setResultMessage] = useState<string | null>(null)
  const previousHistoryRef = useRef<any[]>([]) // Предыдущее состояние для сравнения (используем ref)
  
  // Player status state (removed - now comes from hook)
  // const [playerStatus, setPlayerStatus] = useState<any>(null)
  
  // Refs for timer cleanup
  const timersRef = useRef<NodeJS.Timeout[]>([])
  
  // Helper function to manage timers
  const addTimer = useCallback((callback: () => void, delay: number) => {
    const timer = setTimeout(() => {
      callback()
      // Remove timer from ref
      timersRef.current = timersRef.current.filter(t => t !== timer)
    }, delay)
    timersRef.current.push(timer)
    return timer
  }, [])
  
  // Cleanup function for timers
  useEffect(() => {
    return () => {
      // Clear all timers on unmount
      timersRef.current.forEach(clearTimeout)
      timersRef.current = []
    }
  }, [])
  
  // Process player status updates from hook
  useEffect(() => {
    if (!playerStatus) return
    
    // Update UI state based on player status
    setPlayerJoined(playerStatus.in_game || false)
    setPlayerPlaying(playerStatus.in_game && !playerStatus.cashed_out)
    setIsInGame(playerStatus.in_game || false)
    
    // Handle win/crash messages - просто применяем данные от сервера
    setShowWinMessage(playerStatus.show_win_message || false)
    setShowCrashMessage(playerStatus.show_crash_message || false)
    
    if (playerStatus.show_win_message && playerStatus.win_multiplier) {
      setLastWinCoefficient(parseFloat(playerStatus.win_multiplier))
      setWinMultiplier(parseFloat(playerStatus.win_multiplier))
      setWinAmount(playerStatus.win_amount || 0)
      setResultType("win")
    }
    
    if (playerStatus.show_crash_message) {
      setResultType("crash")
      // Устанавливаем коэффициент краша из текущего коэффициента игры
      if (gameState?.coefficient) {
        setLastCrashCoefficient(parseFloat(gameState.coefficient.toString()))
      }
    }
    
    if (playerStatus.result_message) {
      setResultMessage(playerStatus.result_message)
    } else {
      setResultMessage(null)
    }
  }, [playerStatus])
  
  // Update game state from WebSocket
  useEffect(() => {
    if (gameState) {
      
      // Parse coefficient from string (NO float for money!)
      const rawCoefficient = parseFloat(String(gameState.coefficient || "1.0"))
      const newCoefficient = Math.max(1.0, rawCoefficient) // НИКОГДА не меньше 1.0
      const newStatus = gameState.status as "waiting" | "playing" | "crashed"
      const newCountdown = gameState.countdown || 0
      const crashed = gameState.crashed || false
      
      setCoefficient(newCoefficient)
      setStatus(newStatus)
      setCountdown(newCountdown)
      
      // ОБНОВЛЯЕМ ПОСЛЕДНИЙ КОЭФФИЦИЕНТ ИЗ БЭКЕНДА
      if (gameState.last_crash_coefficient && parseFloat(gameState.last_crash_coefficient) > 1) {
        setLastRoundCoefficient(parseFloat(gameState.last_crash_coefficient))
      }
      
      // Update game history for chart
      if (newStatus === "playing") {
        setCurrentGameHistory((prev) => {
          // Если это первая точка после ожидания и коэффициент близок к 1, начинаем новую игру
          if (status === "waiting" && newCoefficient <= 1.1) {
            return [1, Math.max(1.0, newCoefficient)] // Новая игра - минимум 1.0
          }
          
          // Если коэффициент уменьшился (новая игра началась), сбрасываем историю
          if (prev.length > 0 && newCoefficient < prev[prev.length - 1] && newCoefficient <= 1.1) {
            return [1, Math.max(1.0, newCoefficient)] // Новая игра - минимум 1.0
          }
          
          // Избегаем дублирования одинаковых значений
          if (prev.length > 0 && prev[prev.length - 1] === newCoefficient) {
            return prev
          }
          
          // Иначе добавляем к существующей истории
          const updated = [...prev, Math.max(1.0, newCoefficient)] // НИКОГДА не меньше 1.0
          return updated.length > 1000 ? updated.slice(-500) : updated
        })
      } else if (newStatus === "crashed") {
        // Только сбрасываем статус игры
        setPlayerPlaying(false)
      }
      
      setLoading(false)
      setError(null)
    }
  }, [gameState])
  
  // Handle WebSocket errors
  useEffect(() => {
    if (gameStateError) {
      console.warn('⚠️ WebSocket game state error:', gameStateError)
      setError("WebSocket connection issue")
    }
    
    if (connectionState.error) {
      console.warn('⚠️ WebSocket connection error:', connectionState.error)
    }
  }, [gameStateError, connectionState.error])
  
  // Update crash history display
  useEffect(() => {
    if (crashHistory && crashHistory.length > 0) {
      const newHistory = crashHistory
      const previousHistory = previousHistoryRef.current
      
      // Проверяем, изменились ли данные
      if (JSON.stringify(newHistory) === JSON.stringify(previousHistory)) {
        // Данные не изменились - выходим
        return
      }
      
      // Данные изменились - проверяем, есть ли новые элементы для анимации
      if (previousHistory.length > 0 && newHistory.length > previousHistory.length) {
        // Есть новые элементы - помечаем их для анимации
        const newItemsIndexes = new Set<number>()
        const addedCount = newHistory.length - previousHistory.length
        
        for (let i = 0; i < addedCount; i++) {
          newItemsIndexes.add(i)
        }
        
        setNewItems(newItemsIndexes)
        
        // Убираем анимацию через 1 секунду
        setTimeout(() => {
          setNewItems(new Set())
        }, 1000)
      } else {
        // Данные изменились, но новых элементов нет - очищаем анимации
        setNewItems(new Set())
      }
      
      // Всегда обновляем состояние если данные изменились
      previousHistoryRef.current = newHistory
    }
  }, [crashHistory])
  
  // Bet handling functions
  const handleBetAmountChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const inputValue = e.target.value

    // Разрешаем пустое значение
    if (inputValue === '') {
      setBetAmount('')
      return
    }

    // Разрешаем только цифры, точку и запятую
    if (!/^[\d.,]*$/.test(inputValue)) {
      return
    }

    // Заменяем запятую на точку для парсинга
    const normalizedValue = inputValue.replace(',', '.')

    // Разрешаем частичный ввод (например "12.", "0.")
    if (normalizedValue.endsWith('.') || normalizedValue === '0') {
      setBetAmount(normalizedValue)
      return
    }

    const value = parseFloat(normalizedValue)
    if (isNaN(value)) return

    // Просто устанавливаем значение без ограничений во время ввода
    setBetAmount(normalizedValue)
  }

  const setPresetBet = (amount: number) => {
    const roundedAmount = Math.round(amount * 100) / 100 // Round to 2 decimals
    setBetAmount(roundedAmount)
  }

  // Game actions
  const placeBet = async () => {
    // 🔒 SECURITY: Prevent multiple rapid clicks with stronger protection
    if (isJoining) {
      return
    }
    
    // 🔒 ADDITIONAL PROTECTION: Check if user recently placed a bet
    const lastJoinAttempt = localStorage.getItem(`lastJoin_${userId}`)
    if (lastJoinAttempt) {
      const timeSinceLastJoin = Date.now() - parseInt(lastJoinAttempt)
      if (timeSinceLastJoin < 2000) { // 2 seconds cooldown
        return
      }
    }
    
    if (status !== "waiting") {
      popup.open({
        title: t('game.canOnlyJoinWaiting'),
        message: t('game.canOnlyJoinWaiting'),
        buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
      }).catch(() => {
        console.error('Failed to show popup:', t('game.canOnlyJoinWaiting'))
      })
      return
    }
    
    if (!userId) {
      popup.open({
        title: t('game.userIdError'),
        message: t('game.userIdError'),
        buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
      }).catch(() => {
        console.error('Failed to show popup:', t('game.userIdError'))
      })
      return
    }
    
    const numBetAmount = typeof betAmount === 'string' ? parseFloat(betAmount) || 10 : betAmount
    
    if (balance < numBetAmount) {
      popup.open({
        title: t('game.insufficientFunds', { amount: numBetAmount }),
        message: t('game.insufficientFunds', { amount: numBetAmount }),
        buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
      }).catch(() => {
        console.error('Failed to show popup:', t('game.insufficientFunds', { amount: numBetAmount }))
      })
      return
    }
    
    if (numBetAmount < 10) {
      popup.open({
        title: t('game.minBet'),
        message: t('game.minBet'),
        buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
      }).catch(() => {
        console.error('Failed to show popup:', t('game.minBet'))
      })
      return
    }

    setIsJoining(true) // 🔒 Block further clicks
    
    // 🔒 RECORD join attempt timestamp for additional protection
    localStorage.setItem(`lastJoin_${userId}`, Date.now().toString())
    
    try {
      const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"
      
      // 🔐 Get Telegram init_data for security validation
      const telegramInitData = initData.raw()
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"  // 🔒 CSRF Protection
      }
      
      // Add Telegram auth header if available
      if (telegramInitData) {
        headers["X-Telegram-Init-Data"] = telegramInitData
      }

      // 🔒 SECURITY: Using Telegram authentication only - no client-side signing needed
      
      const res = await fetch(`${API_URL}/join`, {
        method: "POST",
        headers,
        body: JSON.stringify({ user_id: userId, bet_amount: numBetAmount })
      })

      if (!res.ok) {
        const err = await res.json()
        popup.open({
          title: t('game.joinError'),
          message: t('game.joinError') + (err.detail || res.statusText),
          buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
        }).catch(() => {
          console.error('Failed to show popup:', t('game.joinError') + (err.detail || res.statusText))
        })
        return
      }

      const data = await res.json()
      
      
      setPlayerJoined(true)
      // 🚀 OPTIMIZATION: Only update balance via HTTP if WebSocket is not connected
      if (!wsConnected) {
        updateBalance(data.balance)
      }
      
      // ✅ Статус будет обновлен автоматически через updatePlayerStatusAndMessages
    } catch (e) {
      popup.open({
        title: t('game.networkError'),
        message: t('game.networkError'),
        buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
      }).catch(() => {
        console.error('Failed to show popup:', t('game.networkError'))
      })
    } finally {
      setIsJoining(false) // 🔒 Always unblock button
    }
  }

  const handleCashout = async () => {
    if (!playerPlaying || showCrashMessage || showWinMessage || !userId) return
    
    // 🔒 SECURITY: Prevent multiple rapid clicks
    if (isCashingOut) {
      return
    }
    
    setIsCashingOut(true) // 🔒 Block further clicks

    try {
      const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"
      
      // 🔐 Get Telegram init_data for security validation
      const telegramInitData = initData.raw()
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"  // 🔒 CSRF Protection
      }
      
      // Add Telegram auth header if available
      if (telegramInitData) {
        headers["X-Telegram-Init-Data"] = telegramInitData
      }

      // 🔒 SECURITY: Using Telegram authentication only - no client-side signing needed
      
      const res = await fetch(`${API_URL}/cashout`, {
        method: "POST",
        headers,
        body: JSON.stringify({ user_id: userId })
      })

      if (!res.ok) {
        const err = await res.json()
        popup.open({
          title: t('game.cashoutError'),
          message: t('game.cashoutError') + (err.detail || res.statusText),
          buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
        }).catch(() => {
          console.error('Failed to show popup:', t('game.cashoutError') + (err.detail || res.statusText))
        })
        return
      }

      const data = await res.json()
      
      // ✅ Сообщения управляются backend - только обновляем локальный статус
      setPlayerPlaying(false) // Игрок больше не играет в этом раунде
      
      // 🚀 OPTIMIZATION: Only update balance via HTTP if WebSocket is not connected
      if (!wsConnected) {
        updateBalance(data.balance || balance)
      }
      
      // ✅ Статус и сообщения обновятся автоматически через интервал
    } catch (e) {
      popup.open({
        title: t('game.cashoutError'),
        message: t('game.cashoutError') + e,
        buttons: [{ id: 'ok', type: 'default', text: 'OK' }]
      }).catch(() => {
        console.error('Failed to show popup:', t('game.cashoutError') + e)
      })
    } finally {
      setIsCashingOut(false) // 🔒 Always unblock button
    }
  }

  // Connection status indicator
  const getConnectionStatus = () => {
    if (wsConnected) return t('game.wsConnected')
    if (connectionState.connecting) return t('game.wsConnecting')
    if (connectionState.reconnecting) return t('game.wsReconnecting')
    return t('game.wsNoConnection')
  }

  // Loading state
  if (gameStateLoading || loading) {
    return (
      <div className="game-root">
        <div className="game-container">
          <div className="loading-spinner">
            <div className="spinner"></div>
            <p>{t('game.connectingToServer')}</p>
          </div>
        </div>
      </div>
    )
  }

  // Error state
  if (error || gameStateError) {
    return (
      <div className="game-root">
        <div className="game-container">
          <div className="error-message">
            <p>❌ {error || gameStateError}</p>
            <button onClick={() => {
              setError(null)
              setLoading(true)
              window.location.reload()
            }}>
              {t('game.tryAgain')}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Advanced Chart configuration (restored from original)
  const getGraphColor = () => {
    // Красный если игра крашнулась или если показываем крашнувшую игру
    if (showCrashMessage || (status === "waiting" && lastRoundCoefficient > 1)) return "rgba(239, 68, 68, 1)"
    if (showWinMessage) return "rgba(34,197,94,1)" // зелёный
    return "rgba(79, 70, 229, 1)" // индиго
  }

  // Показываем либо текущую игру (если playing), либо последнюю игру (если waiting/crashed)
  const graphData = status === "playing" ? 
    (currentGameHistory.length > 1 ? currentGameHistory : [1, Math.max(1.0, coefficient)]) :
    (currentGameHistory.length > 1 ? currentGameHistory : [1, Math.max(1.0, lastRoundCoefficient)])

  const graphColor = getGraphColor()
  const maxY = graphData.length > 0 ? Math.max(...graphData) : 1.5
  const maxScale = maxY * 1.2

  const chartData: ChartData<"line", number[], number> = {
    labels: graphData.map((_, i) => i + 1),
    datasets: [
      {
        label: t('game.coefficient'),
        data: graphData,
        fill: true,
        borderColor: graphColor,
        backgroundColor: (() => {
          // Create gradient background based on game state
          if (showCrashMessage || (status === "waiting" && lastRoundCoefficient > 1)) {
            return "rgba(239, 68, 68, 0.2)" // Red fade for crash
          }
          if (showWinMessage) {
            return "rgba(34, 197, 94, 0.2)" // Green fade for cashout
          }
          return "rgba(79, 70, 229, 0.2)" // Blue fade for normal play
        })(),
        tension: 0.1,
        pointRadius: 0,
        borderWidth: 4,
        borderJoinStyle: 'round' as const,
        borderCapStyle: 'round' as const,
      },
    ],
  }

  const chartOptions: ChartOptions<"line"> = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 0, easing: "linear" },
    layout: {
      padding: {
        bottom: 40
      }
    },
    plugins: {
      legend: { display: false },
      tooltip: { enabled: false }
    },
    scales: {
      x: { display: false },
      y: {
        min: 1,
        max: maxScale,
        grid: {
          color: "rgba(79, 70, 229, 0.15)",
          lineWidth: 1
        },
        border: {
          color: "rgba(79, 70, 229, 0.3)",
          width: 2
        },
        ticks: {
          color: "rgba(224, 231, 255, 0.9)",
          font: { weight: "bold", size: 12 },
          callback: function(value) {
            return `${Number(value).toFixed(1)}x`
          }
        }
      }
    },
    elements: {
      point: {
        radius: 0,
        hoverRadius: 0
      },
      line: {
        tension: 0.1
      }
    }
  }

  return (
    <div className="game-root">
      <div className="game-container">
        

        {/* Advanced Crash History with Trends */}
        <div className="crash-history-strip">
          <div 
            className="crash-history-container"
            onMouseDown={(e) => {
              // Блокируем вертикальное перетаскивание средней кнопкой мыши
              if (e.button === 1) { // средняя кнопка
                e.preventDefault()
                return false
              }
            }}
            onDragStart={(e) => {
              // Полностью блокируем drag для истории
              e.preventDefault()
              return false
            }}
            style={{ userSelect: 'none' }}
          >
            {(crashHistory || []).slice(0, 15).map((crashCoeff, index) => {
              const isNewItem = newItems.has(index)
              const coeffValue = parseFloat(crashCoeff.toString())
              const prevCoeff = index < crashHistory.length - 1 ? parseFloat(crashHistory[index + 1].toString()) : null
              const coeffDiff = prevCoeff ? coeffValue - prevCoeff : 0
              const absDiff = Math.abs(coeffDiff)
              const showTriangle = absDiff >= 0.7
              const isUpTrend = coeffDiff > 0
              const triangleCount = absDiff >= 2.9 ? 3 : absDiff >= 1.8 ? 2 : 1
              
              return (
                <div 
                  key={`${crashCoeff}-${index}-${isNewItem ? 'new' : 'old'}`}
                  className={`crash-item ${
                    isNewItem ? 'crash-item-new' : (index === 0 ? 'crash-item-first' : 'crash-item-static')
                  } ${
                    coeffValue < 1.5 ? 'crash-low' : coeffValue < 2.0 ? 'crash-medium' : 'crash-high'
                  }`}
                  style={{ 
                    animationDelay: isNewItem ? '0ms' : `${index * 30}ms`
                  }}
                >
                  {showTriangle && (
                    <div className="trend-indicators">
                      {Array.from({ length: triangleCount }, (_, i) => (
                        <div
                          key={i}
                          className={`trend-indicator trend-indicator-${i + 1} ${isUpTrend ? 'trend-up' : 'trend-down'}`}
                        >
                          {isUpTrend ? '▲' : '▼'}
                        </div>
                      ))}
                    </div>
                  )}
                  {coeffValue.toFixed(2)}x
                </div>
              )
            })}
          </div>
        </div>

        {/* Game Chart */}
        <div className="chart-wrapper">
          {graphData.length > 1 && <Line data={chartData} options={chartOptions} />}
          <div className="chart-overlay">
            <div className="coef-overlay">
              x{status === "waiting" ? Number(lastRoundCoefficient).toFixed(2) : Number(coefficient).toFixed(2)}
            </div>
            {(showCrashMessage || showWinMessage) && (
              <div className="message-legend">
                {showWinMessage ? (
                  <div className="cashout-message">
                    ✅ +{Number(winAmount).toFixed(2)}<img src={StarIcon} alt="Star" className="message-star-icon" /> x{Number(winMultiplier).toFixed(2)}
                  </div>
                ) : showCrashMessage ? (
                  <div className="crash-message">{t('game.crash')}</div>
                ) : null}
              </div>
            )}
          </div>
        </div>

        {/* Advanced Betting Controls */}
        {(status === "waiting" || status === "playing") && (
          <div className="bet-controls">
            <div className="bet-input-section">
              <label htmlFor="bet-amount">{t('game.bet')}</label>
              <input
                id="bet-amount"
                type="text"
                inputMode="decimal"
                pattern="[0-9]*\.?[0-9]*"
                max={balance}
                value={betAmount}
                onChange={handleBetAmountChange}
                className="bet-input"
                disabled={playerJoined || playerPlaying}
                placeholder="10"
              />
              <img src={StarIcon} alt="Star" className="bet-currency" />
            </div>
            
            <div className="bet-presets">
              {balance >= 160 && (
                <button
                  className={`bet-preset ${betAmount === Math.round(balance / 16 * 100) / 100 ? 'active' : ''}`}
                  onClick={() => setPresetBet(Math.round(balance / 16 * 100) / 100)}
                  disabled={playerJoined || playerPlaying}
                >
                  1/16
                </button>
              )}
              {balance >= 80 && (
                <button
                  className={`bet-preset ${betAmount === Math.round(balance / 8 * 100) / 100 ? 'active' : ''}`}
                  onClick={() => setPresetBet(Math.round(balance / 8 * 100) / 100)}
                  disabled={playerJoined || playerPlaying}
                >
                  1/8
                </button>
              )}
              {balance >= 40 && (
                <button
                  className={`bet-preset ${betAmount === Math.round(balance / 4 * 100) / 100 ? 'active' : ''}`}
                  onClick={() => setPresetBet(Math.round(balance / 4 * 100) / 100)}
                  disabled={playerJoined || playerPlaying}
                >
                  1/4
                </button>
              )}
              {balance >= 20 && (
                <button
                  className={`bet-preset ${betAmount === Math.round(balance / 2 * 100) / 100 ? 'active' : ''}`}
                  onClick={() => setPresetBet(Math.round(balance / 2 * 100) / 100)}
                  disabled={playerJoined || playerPlaying}
                >
                  1/2
                </button>
              )}
              {balance >= 10 && (
                <button
                  className={`bet-preset ${betAmount === balance ? 'active' : ''}`}
                  onClick={() => setPresetBet(balance)}
                  disabled={playerJoined || playerPlaying}
                >
                  All In
                </button>
              )}
            </div>
          </div>
        )}

        <div className="buttons-wrapper">
          {(() => {
            // Определяем, какую кнопку показать (избегаем моргания)
            if (status === "playing" && playerPlaying && !showCrashMessage && !showWinMessage) {
              return (
                <button 
                  className={`game-btn cashout ${isCashingOut ? 'disabled' : ''}`} 
                  onClick={handleCashout}
                  disabled={isCashingOut}
                >
                  {isCashingOut ? t('game.cashing') : t('game.cashoutStars')} (x{coefficient.toFixed(2)})
                </button>
              )
            }
            
            if (status === "playing" && !playerJoined) {
              return (
                <button className="game-btn start disabled">
                  {t('game.roundAlreadyStarted')}
                </button>
              )
            }
            
            if (status === "waiting" && playerJoined) {
              return (
                <div className="status-message">
                  {t('game.waitingForStart', { countdown: countdown > 0 ? ` (${countdown} ${t('common.seconds_short')})` : '...' })}
                </div>
              )
            }
            
            if (status === "waiting" && !playerJoined && balance < (typeof betAmount === 'string' ? parseFloat(betAmount) || 10 : betAmount)) {
              return (
                <button className="game-btn start disabled">
                  {t('game.insufficientStars')}
                </button>
              )
            }
            
            if (status === "waiting" && !playerJoined && balance >= (typeof betAmount === 'string' ? parseFloat(betAmount) || 10 : betAmount)) {
              return (
                <button 
                  className={`game-btn start ${isJoining ? 'disabled' : ''}`} 
                  onClick={placeBet}
                  disabled={isJoining}
                >
                  {isJoining ? t('game.joining') : t('game.joinRound')} ({Number(betAmount).toFixed(2)}⭐)
                  {countdown > 0 && !isJoining && <div className="countdown-text">{t('game.startIn', { seconds: countdown })}</div>}
                </button>
              )
            }
            
            // Fallback - показываем что-то вместо пустоты
            return (
              <div className="status-message">
                {t('game.waitingForEnd')}
              </div>
            )
          })()}
        </div>

        {/* Result Messages */}

      </div>
    </div>
  )
}