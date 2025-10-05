import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { initData } from '@telegram-apps/sdk-react'
import './Leaderboard.css'

interface LeaderboardPlayer {
  rank: number
  is_current_user: boolean  // 🔒 SECURITY: Replace telegram_id with is_current_user flag
  first_name?: string
  last_name?: string
  username?: string
  total_won: number
  total_games: number
  games_won: number
  best_multiplier: number
  avg_multiplier: number
}

interface PlayerRank {
  rank: number | null
  total_players: number
}

interface PlayerStats extends LeaderboardPlayer {}

export default function Leaderboard() {
  const { t } = useTranslation()
  const [leaderboard, setLeaderboard] = useState<LeaderboardPlayer[]>([])
  const [playerRank, setPlayerRank] = useState<PlayerRank | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedPlayer, setSelectedPlayer] = useState<PlayerStats | null>(null)
  const [currentUserId, setCurrentUserId] = useState<number | null>(null)

  useEffect(() => {
    const loadData = async () => {
      try {
        let user = initData.user()
        let retries = 0
        while (!user?.id && retries < 3) {
          await new Promise(res => setTimeout(res, 200 * (retries + 1)))
          user = initData.user()
          retries++
        }

        if (!user?.id) {
          // Загрузить из кеша, если user отсутствует
          useCachedData()
          return
        }

        setCurrentUserId(user.id)

        await loadLeaderboard()
        await loadPlayerRank(user.id)

      } catch (e) {
        console.warn(t('console.leaderboardLoadError'), e)
        // При ошибках — тоже кешируем
        useCachedData()
      } finally {
        setLoading(false) // Обязательно отключаем loading только в конце
      }
    }

    loadData()
  }, [])

  const useCachedData = () => {
    try {
      const cachedLeaderboard = localStorage.getItem('cachedLeaderboard')
      const cachedPlayerRank = localStorage.getItem('cachedPlayerRank')

      if (cachedLeaderboard) {
        setLeaderboard(JSON.parse(cachedLeaderboard))
      } else {
        setLeaderboard([]) // Обязательно чтобы не оставался undefined
      }

      if (cachedPlayerRank) {
        setPlayerRank(JSON.parse(cachedPlayerRank))
      } else {
        setPlayerRank(null)
      }
    } catch (e) {
      console.warn(t('console.leaderboardLoadError'), e)
      setPlayerRank(null)
    }
  }

  const loadLeaderboard = async () => {
    try {
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }

      let raw = initData.raw()
      let retries = 0
      while (!raw && retries < 3) {
        await new Promise(res => setTimeout(res, 200 * (retries + 1)))
        raw = initData.raw()
        retries++
      }

      if (raw) headers['X-Telegram-Init-Data'] = raw

      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 5000)

      const res = await fetch(`${API_URL}/leaderboard`, {
        headers,
        signal: controller.signal
      })

      clearTimeout(timeout)

      if (res.ok) {
        const data = await res.json()
        setLeaderboard(data.leaderboard || [])
        localStorage.setItem('cachedLeaderboard', JSON.stringify(data.leaderboard || []))
      } else {
        setLeaderboard([]) // При ошибке сбрасываем данные
      }
    } catch (e) {
      console.warn(t('console.leaderboardLoadError'), e)
      setLeaderboard([])
    }
  }

  const loadPlayerRank = async (userId: number) => {
    try {
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }

      let raw = initData.raw()
      let retries = 0
      while (!raw && retries < 3) {
        await new Promise(res => setTimeout(res, 200 * (retries + 1)))
        raw = initData.raw()
        retries++
      }

      if (raw) headers['X-Telegram-Init-Data'] = raw

      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 5000)

      const res = await fetch(`${API_URL}/player-rank/${userId}`, {
        headers,
        signal: controller.signal
      })

      clearTimeout(timeout)

      if (res.ok) {
        const data = await res.json()
        setPlayerRank(data)
        localStorage.setItem('cachedPlayerRank', JSON.stringify(data))
      } else {
        setPlayerRank(null) // При ошибке сбрасываем данные
      }
    } catch {
      setPlayerRank(null) // При ошибке сбрасываем данные
    }
  }

  const handlePlayerClick = (player: LeaderboardPlayer) => {
    setSelectedPlayer(player)
  }

  const getDisplayName = (player: LeaderboardPlayer | PlayerStats) => {
    if (player.is_current_user) {
      const user = initData.user()
      return user?.first_name || user?.username || t('common.you')
    }
    return player.first_name || player.username || t('common.player')
  }

  const getRankEmoji = (rank: number) => {
    return rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : `${rank}.`
  }

  const getRankDisplay = (rank: number) => `#${rank}`

  if (loading) {
    return (
      <div className="leaderboard-container">
        <div className="loading-spinner">
          <div className="spinner" />
          <p>{t('leaderboard.loadingLeaderboard')}</p>
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="leaderboard-container">
        {playerRank && (
          <div className="player-rank-info">
            <div className="rank-card">
              <span className="rank-label">{t('leaderboard.yourPlace')}</span>
              <span className="rank-value">
                {playerRank.rank ? `${playerRank.rank} из ${playerRank.total_players}` : t('leaderboard.notInLeaderboard')}
              </span>
            </div>
          </div>
        )}

        <div className="leaderboard-list">
          {leaderboard.length === 0 ? (
            <div className="empty-leaderboard">
              <p>{t('leaderboard.emptyLeaderboard')}</p>
            </div>
          ) : (
            leaderboard.map((player, index) => (
              <div
                key={`player-${player.rank}-${index}`}  // 🔒 SECURITY: Use rank+index instead of telegram_id
                className={`leaderboard-item ${player.is_current_user ? 'current-player' : ''}`}
                onClick={() => handlePlayerClick(player)}
              >
                <div className="player-rank">{getRankEmoji(player.rank)}</div>
                <div className="player-info">
                  <div className="player-name">{getDisplayName(player)}</div>
                  <div className="player-stats">
                    <span className="stat">⭐ {player.total_won}</span>
                    <span className="stat">🎮 {player.total_games}</span>
                  </div>
                </div>
                <div className="player-rank-display">
                  {getRankDisplay(player.rank)}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {selectedPlayer && (
        <div className="player-stats-modal" onClick={() => setSelectedPlayer(null)}>
          <div className="player-stats-content" onClick={e => e.stopPropagation()}>
            <div className="stats-header">
              <h3>{getDisplayName(selectedPlayer)}</h3>
              <button className="close-btn" onClick={() => setSelectedPlayer(null)}>×</button>
            </div>
            <div className="stats-grid">
              <div className="stat-item">
                <span className="stat-label">{t('leaderboard.gamesPlayed')}</span>
                <span className="stat-value">{selectedPlayer.total_games}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">{t('leaderboard.totalWin')}</span>
                <span className="stat-value">{selectedPlayer.total_won} ⭐</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">{t('leaderboard.bestMultiplier')}</span>
                <span className="stat-value">{Number(selectedPlayer.best_multiplier).toFixed(2)}x</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">{t('leaderboard.avgMultiplier')}</span>
                <span className="stat-value">{Number(selectedPlayer.avg_multiplier).toFixed(2)}x</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
