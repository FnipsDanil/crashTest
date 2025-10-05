/// <reference types="vite/client" />

interface TelegramUser {
  id: number
  first_name?: string
  last_name?: string
  username?: string
  photo_url?: string
  language_code?: string
}

interface TelegramWebApp {
  initDataUnsafe?: {
    user?: TelegramUser
    query_id?: string
    auth_date?: number
    hash?: string
  }
  ready?: () => void
  expand?: () => void
  disableVerticalSwipes?: () => void
  isVerticalSwipesEnabled?: boolean
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp
    }
  }
}

export {}
