/**
 * Centralized API service for Crash Stars frontend
 * Provides type-safe API calls and error handling
 */

// ❌ УДАЛЕН GameState - используется WebSocket события

// ❌ УДАЛЕН PlayerStatus - используется WebSocket события

export interface UserBalance {
  user_id: number;
  balance: number;
}

// 🚀 КРИТИЧНО: Интерфейсы для сжатых HTTP ответов
export interface CompressedBalance {
  b: string;  // balance as string
}

export interface CompressedCurrentState {
  c: string;   // coefficient
  s: string;   // status (w/p/c)
  cd: number;  // countdown
  cr: number;  // crashed (0/1)
  lc: string;  // last_crash_coefficient
  jc: number;  // game_just_crashed (0/1)
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

export interface LeaderboardResponse {
  leaderboard: LeaderboardEntry[];
}

// API Configuration
class ApiService {
  private baseURL: string;
  private controller: AbortController | null = null;
  private initData: string | null = null;

  constructor() {
    this.baseURL = import.meta.env.VITE_API_URL || "http://localhost:8000";
  }

  /**
   * Set Telegram init_data for authentication
   */
  setInitData(initData: string) {
    this.initData = initData;
  }

  /**
   * Cancel ongoing requests
   */
  cancelRequests() {
    if (this.controller) {
      this.controller.abort();
    }
    this.controller = new AbortController();
  }

  /**
   * Generic fetch wrapper with error handling
   */
  private async fetch<T>(
    endpoint: string, 
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseURL}${endpoint}`;
    
    // Create a new controller for this specific request
    const controller = new AbortController();
    
    // Set default timeout of 8 seconds
    const timeout = setTimeout(() => {
      controller.abort();
    }, 8000);

    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',  // CSRF protection
        ...(options.headers as Record<string, string> || {}),
      };

      // Add Telegram authentication header if available
      if (this.initData) {
        headers['X-Telegram-Init-Data'] = this.initData;
      }

      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers,
      });

      if (!response.ok) {
        const errorText = await response.text();
        let errorMessage: string;
        
        try {
          const errorJson = JSON.parse(errorText);
          errorMessage = errorJson.detail || errorJson.message || response.statusText;
        } catch {
          errorMessage = errorText || response.statusText;
        }
        
        throw new Error(`API Error (${response.status}): ${errorMessage}`);
      }

      return await response.json();
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('Request cancelled or timed out');
      }
      // Fix: Ensure we always throw an Error object, never undefined
      if (error instanceof Error) {
        throw error;
      }
      throw new Error(`Unknown error: ${String(error)}`);
    } finally {
      clearTimeout(timeout);
    }
  }

  // ❌ УДАЛЕН getCurrentState() - заменен на WebSocket события game_state

  async joinGame(userId: number, betAmount: number): Promise<JoinResponse> {
    return this.fetch<JoinResponse>('/api/game/join', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, bet_amount: betAmount }),
    });
  }

  async cashout(userId: number): Promise<CashoutResponse> {
    return this.fetch<CashoutResponse>('/api/game/cashout', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId }),
    });
  }

  // ❌ УДАЛЕН getPlayerStatus() - заменен на WebSocket события player_status

  // Player API methods
  async getUserBalance(userId: number): Promise<UserBalance> {
    // 🚀 КРИТИЧНО: Получаем сжатый ответ и декомпрессируем
    const compressed = await this.fetch<CompressedBalance>(`/balance/${userId}`);
    return {
      user_id: userId,
      balance: parseFloat(compressed.b)
    };
  }

  async getUserStats(userId: number): Promise<UserStats> {
    return this.fetch<UserStats>(`/user-stats/${userId}`);
  }

  async verifyUser(initData: string): Promise<any> {
    return this.fetch('/verify-user', {
      method: 'POST',
      body: JSON.stringify({ init_data: initData }),
    });
  }

  async updateUserData(): Promise<any> {
    return this.fetch('/update-user-data', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  }

  // Leaderboard API methods
  async getLeaderboard(): Promise<LeaderboardResponse> {
    return this.fetch<LeaderboardResponse>('/leaderboard');
  }

  async getPlayerRank(userId: number): Promise<{ rank: number | null; total_players: number }> {
    return this.fetch(`/player-rank/${userId}`);
  }

  // Gift/Store API methods
  async getGifts(): Promise<any> {
    return this.fetch('/gifts');
  }

  async getPaymentRequests(): Promise<any> {
    return this.fetch('/payment-requests');
  }

  async purchaseGift(giftId: string): Promise<any> {
    return this.fetch('/purchase-gift', {
      method: 'POST',
      body: JSON.stringify({ gift_id: giftId }),
    });
  }

  // Payment API methods
  async createInvoice(amount: number, title?: string, description?: string): Promise<any> {
    return this.fetch('/create-invoice', {
      method: 'POST',
      body: JSON.stringify({ 
        amount, 
        title: title || "Пополнение баланса",
        description: description || "Покупка звёзд для игры Crash Stars"
      }),
    });
  }

  async getPaymentStatus(paymentPayload: string): Promise<any> {
    return this.fetch(`/payment-status/${paymentPayload}`);
  }

  // Language API methods
  async getUserLanguage(userId: number): Promise<{ language_code: string }> {
    return this.fetch(`/user-language/${userId}`);
  }

  async setUserLanguage(userId: number, languageCode: string): Promise<{ success: boolean; language_code: string }> {
    return this.fetch(`/user-language/${userId}`, {
      method: 'POST',
      body: JSON.stringify({ language_code: languageCode }),
    });
  }

  // Health check
  async healthCheck(): Promise<{ status: string; service: string }> {
    return this.fetch('/health');
  }

  async healthCheckDb(): Promise<any> {
    return this.fetch('/health/db');
  }

  // 🎯 NEW: Channel subscription bonus methods
  async getChannelBonusStatus(): Promise<{
    enabled: boolean;
    channels?: Record<string, any>;
    default_bonus_amount?: number;
    reason?: string;
  }> {
    // 🔄 FEATURE TOGGLE: Get channel bonus status and config from backend
    try {
      const response = await this.fetch<{
        enabled: boolean;
        channels?: Record<string, any>;
        default_bonus_amount?: number;
        reason?: string;
      }>('/api/player/channel-bonus-status');
      
      return response;
    } catch (error) {
      console.warn('Failed to get channel bonus status:', error);
      // On error, assume disabled to avoid showing broken UI
      return {
        enabled: false,
        reason: 'Network error'
      };
    }
  }

  async isChannelBonusEnabled(): Promise<boolean> {
    const status = await this.getChannelBonusStatus();
    return status.enabled;
  }

  async getUserBonusStatus(): Promise<{
    promo_codes: { available: boolean };
    channel_bonus: { 
      available: boolean; 
      claimed: boolean; 
      enabled: boolean;
      config?: any;
    };
  }> {
    try {
      // 🚀 COMPRESSED: Receive minimal response and decompress
      const compressed = await this.fetch<{
        p: boolean;   // promo_codes available
        c: boolean;   // channel_bonus available
        cc: boolean;  // channel_bonus claimed  
        ce: boolean;  // channel_bonus enabled
        cfg?: any;    // config
      }>('/api/player/user-bonus-status');
      
      // Decompress to standard format
      return {
        promo_codes: { available: compressed.p },
        channel_bonus: { 
          available: compressed.c,
          claimed: compressed.cc,
          enabled: compressed.ce,
          config: compressed.cfg
        }
      };
    } catch (error) {
      return {
        promo_codes: { available: true },
        channel_bonus: { available: false, claimed: false, enabled: false }
      };
    }
  }

  async checkChannelSubscription(channelId: string): Promise<{
    success: boolean;
    error?: string;
    bonus_amount?: number;
    new_balance?: number;
    channel_id?: string;
  }> {
    // 🚀 КРИТИЧНО: Получаем сжатый ответ и декомпрессируем
    const compressed = await this.fetch<{
      s: boolean;  // success
      a?: number;  // amount  
      b?: number;  // balance
      c?: string;  // channel
      e?: string;  // error
    }>('/api/player/check-channel-subscription', {
      method: 'POST',
      body: JSON.stringify({ channel_id: channelId }),
    });

    // Декомпрессируем ответ в стандартный формат
    return {
      success: compressed.s,
      error: compressed.e,
      bonus_amount: compressed.a,
      new_balance: compressed.b,
      channel_id: compressed.c
    };
  }

  async getUserChannelBonuses(): Promise<{
    bonuses: Array<{
      channel_id: string;
      bonus_amount: number;
      claimed_at: string;
      verified_at: string;
    }>;
    total_earned: number;
    channels_count: number;
  }> {
    // 🚀 КРИТИЧНО: Получаем сжатый ответ и декомпрессируем
    const compressed = await this.fetch<{
      b: Array<any>;  // bonuses
      t: number;      // total_earned
      c: number;      // channels_count
    }>('/api/player/channel-bonuses');

    // Декомпрессируем ответ в стандартный формат
    return {
      bonuses: compressed.b,
      total_earned: compressed.t,
      channels_count: compressed.c
    };
  }

  async usePromoCode(promoCode: string): Promise<{
    success: boolean;
    error?: string;
    bonus_amount?: string;
    new_balance?: string;
    promo_code?: string;
    withdrawal_requirement?: string;
  }> {
    // 🚀 КРИТИЧНО: Получаем сжатый ответ и декомпрессируем
    const compressed = await this.fetch<{
      s: boolean;   // success
      a?: string;   // amount (as string for Decimal)
      b?: string;   // balance (as string for Decimal)
      c?: string;   // code
      wr?: string;  // withdrawal_requirement (as string for Decimal)
      e?: string;   // error
    }>('/api/player/use-promo-code', {
      method: 'POST',
      body: JSON.stringify({ promo_code: promoCode }),
    });

    // Декомпрессируем ответ в стандартный формат
    return {
      success: compressed.s,
      error: compressed.e,
      bonus_amount: compressed.a,
      new_balance: compressed.b,
      promo_code: compressed.c,
      withdrawal_requirement: compressed.wr
    };
  }

  async getPromoCodeHistory(): Promise<{
    promo_uses: Array<{
      code: string;
      balance_granted: string;
      withdrawal_requirement?: string;
      used_at: string;
    }>;
    total_earned: string;
    count: number;
  }> {
    // 🚀 КРИТИЧНО: Получаем сжатый ответ и декомпрессируем
    const compressed = await this.fetch<{
      p: Array<any>;  // promo_uses
      t: string;      // total_earned (as string for Decimal)
      c: number;      // count
    }>('/api/player/promo-code-history');

    // Декомпрессируем ответ в стандартный формат
    return {
      promo_uses: compressed.p,
      total_earned: compressed.t,
      count: compressed.c
    };
  }
}

// Export singleton instance
export const apiService = new ApiService();

// Export default instance for convenience
export default apiService;