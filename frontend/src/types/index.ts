/**
 * Central type definitions for Crash Stars frontend
 */

// Telegram Types
export interface TelegramUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  language_code?: string;
}

export interface TelegramInitData {
  user?: TelegramUser;
  auth_date?: string;
  hash?: string;
  query_id?: string;
  start_param?: string;
}

// Game Types
export interface GameConfig {
  growth_rate: number;
  tick_ms: number;
  max_coefficient: number;
  waiting_time: number;
  join_time: number;
  crash_ranges: {
    min: number;
    max: number;
    probability: number;
  }[];
}

// ❌ УДАЛЕН GameState - используется WebSocket события (см. hooks/useWebSocketData.ts)

export interface PlayerState {
  userId: number;
  balance: number;
  betAmount: number;
  isPlaying: boolean;
  hasJoined: boolean;
  playerJoined: boolean;
  playerPlaying: boolean;
  cashedOut: boolean;
  winAmount: number;
  winMultiplier: number;
}

// ❌ УДАЛЕН PlayerStatus - используется WebSocket события (см. hooks/useWebSocketData.ts)

// UI State Types
export interface GameUIState {
  showWinMessage: boolean;
  showCrashMessage: boolean;
  showJoinModal: boolean;
  showPaymentModal: boolean;
  countdown: number;
  currentGameHistory: number[];
  lastRoundCoefficient: number;
}

// Statistics Types
export interface UserStats {
  user_id: number;
  total_games: number;
  games_won: number;
  games_lost: number;
  total_wagered: number;
  total_won: number;
  wagered_balance: number;
  best_multiplier: number;
  avg_multiplier: number;
}

export interface LeaderboardEntry {
  rank: number;
  is_current_user: boolean;  // 🔒 SECURITY: Replace telegram_id with is_current_user flag
  first_name?: string;
  last_name?: string;
  username?: string;
  total_won: number;
  total_games: number;
  games_won: number;
  best_multiplier: number;
  avg_multiplier: number;
}

// Store/Gift Types
export interface TelegramGift {
  id: string;
  name: string;
  description: string;
  price: number;
  telegram_gift_id: string;
  business_gift_id?: string;
  emoji: string;
  image_url?: string;
  is_unique: boolean;
}

export interface PaymentRequest {
  id: number;
  gift_name: string;
  price: string;
  status: 'pending' | 'approved' | 'completed' | 'canceled';
  cancel_reason?: 'no_message' | 'price_changed' | 'suspect_act' | null;
  created_at: string | null;
  approved_at: string | null;
  completed_at: string | null;
  gift: {
    emoji: string;
    is_unique: boolean;
  };
}

// Payment Types
export interface PaymentInvoice {
  payment_payload: string;
  message_id?: number;
  invoice_link?: string;
  invoice_slug?: string;
}

export interface PaymentStatus {
  payload: string;
  status: 'pending' | 'completed' | 'failed';
  amount: number;
  created_at: number;
  completed_at?: number;
  new_balance?: number;
}

// API Response Types
export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface UserBalance {
  user_id: number;
  balance: number;
}

export interface JoinResponse {
  joined: boolean;
  balance: number;
}

export interface CashoutResponse {
  cashed_out: boolean;
  coefficient: number;
  win_amount: number;
  balance: number;
}

export interface LeaderboardResponse {
  leaderboard: LeaderboardEntry[];
}

// Form Types
export interface JoinGameRequest {
  user_id: number;
  bet_amount: number;
}

export interface CashoutRequest {
  user_id: number;
}

export interface CreateInvoiceRequest {
  init_data: string;
  amount: number;
  title?: string;
  description?: string;
}

export interface PurchaseGiftRequest {
  init_data: string;
  gift_id: string;
}

// Error Types
export interface ApiError {
  message: string;
  status?: number;
  code?: string;
}

// App State Types
export interface AppState {
  // User state
  user: TelegramUser | null;
  userId: number | null;
  balance: number;
  isAuthenticated: boolean;
  
  // Game state - теперь управляется через WebSocket
  // gameState удален - используется WebSocket события
  // playerState удален - используется WebSocket события  
  gameUIState: GameUIState;
  
  // UI state
  isLoading: boolean;
  error: string | null;
  
  // Settings
  language: string;
  soundEnabled: boolean;
  
  // Actions
  setUser: (user: TelegramUser | null) => void;
  setBalance: (balance: number) => void;
  // setGameState удален - управляется через WebSocket
  // setPlayerState удален - управляется через WebSocket
  setUIState: (state: Partial<GameUIState>) => void;
  setError: (error: string | null) => void;
  setLoading: (loading: boolean) => void;
  reset: () => void;
}

// Chart Types (for game visualization)
export interface ChartDataPoint {
  x: number;
  y: number;
}

export interface ChartConfig {
  responsive: boolean;
  maintainAspectRatio: boolean;
  animation: {
    duration: number;
    easing: string;
  };
  elements: {
    point: {
      radius: number;
    };
    line: {
      tension: number;
    };
  };
  scales: {
    x: {
      type: string;
      display: boolean;
    };
    y: {
      type: string;
      beginAtZero: boolean;
      min: number;
    };
  };
  plugins: {
    legend: {
      display: boolean;
    };
    tooltip: {
      enabled: boolean;
    };
  };
}

// Export commonly used type unions
export type GameStatus = 'waiting' | 'playing' | 'crashed';
export type PaymentStatusType = 'pending' | 'completed' | 'failed';
export type Language = 'ru' | 'en';