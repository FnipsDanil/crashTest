/**
 * WebSocket service for real-time game updates
 * Replaces high-frequency HTTP polling with efficient WebSocket connections
 */

export interface WebSocketMessage {
  type: string;
  timestamp: number;
  data?: any;
  event?: string;
  message?: string;
}

export interface GameStateData {
  coefficient: string;
  status: string;
  countdown: number;
  crashed: boolean;
  crash_point?: string;
  last_crash_coefficient?: string;
  time_since_start?: number;
  game_just_crashed?: boolean;
}

export interface CrashHistoryData {
  history: string[];
}

export interface PlayerStatusData {
  // Define based on your player status structure
  [key: string]: any;
}

type EventCallback = (data: any) => void;
type EventType = 'game_state' | 'crash_history' | 'player_status' | 'balance_update' | 'ping' | 'pong' | 'error' | 'connected' | 'disconnected' | 'subscribed' | 'unsubscribed';

interface EventSubscription {
  event: EventType;
  callback: EventCallback;
}

class WebSocketService {
  private ws: WebSocket | null = null;
  private url: string;
  private userId: number | null = null;
  private initData: string = '';
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000; // Start with 1 second
  private isConnected = false;
  private eventSubscriptions: EventSubscription[] = [];
  private reconnectTimer: NodeJS.Timeout | null = null;
  private pingInterval: NodeJS.Timeout | null = null;
  
  constructor() {
    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    this.url = API_URL.replace('http', 'ws').replace('https', 'wss');
  }
  
  /**
   * Connect to WebSocket server
   */
  async connect(userId: number, initData: string = ''): Promise<boolean> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return true;
    }
    
    this.userId = userId;
    this.initData = initData;
    
    try {
      const wsUrl = `${this.url}/ws/${userId}?init_data=${encodeURIComponent(initData)}`;
      
      this.ws = new WebSocket(wsUrl);
      
      this.ws.onopen = this.handleOpen.bind(this);
      this.ws.onmessage = this.handleMessage.bind(this);
      this.ws.onerror = this.handleError.bind(this);
      this.ws.onclose = this.handleClose.bind(this);
      
      // Wait for connection to open
      return new Promise((resolve) => {
        if (!this.ws) {
          resolve(false);
          return;
        }
        
        const timeout = setTimeout(() => {
          resolve(false);
        }, 5000); // 5 second timeout
        
        this.ws.onopen = () => {
          clearTimeout(timeout);
          this.handleOpen();
          resolve(true);
        };
        
        this.ws.onerror = () => {
          clearTimeout(timeout);
          resolve(false);
        };
      });
      
    } catch (error) {
      console.error('❌ WebSocket connection failed:', error);
      return false;
    }
  }
  
  /**
   * Disconnect from WebSocket server
   */
  disconnect(): void {
    this.isConnected = false;
    
    // Clear timers
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
    
    // Close WebSocket
    if (this.ws) {
      this.ws.onclose = null; // Prevent reconnection
      this.ws.close();
      this.ws = null;
    }
    
    // Notify subscribers
    this.notifySubscribers('disconnected', {});
  }
  
  /**
   * Subscribe to WebSocket events
   */
  subscribe(event: EventType, callback: EventCallback): () => void {
    const subscription: EventSubscription = { event, callback };
    this.eventSubscriptions.push(subscription);
    
    // Only log important subscriptions, not spam events
    
    // Send subscription to server if connected
    if (this.isConnected && event !== 'connected' && event !== 'disconnected' && event !== 'error') {
      this.send({
        type: 'subscribe',
        event: event
      });
    }
    
    // Return unsubscribe function
    return () => {
      const index = this.eventSubscriptions.indexOf(subscription);
      if (index > -1) {
        this.eventSubscriptions.splice(index, 1);
        
        // Only log important unsubscriptions, not spam events
        
        // Send unsubscribe to server if connected
        if (this.isConnected && event !== 'connected' && event !== 'disconnected' && event !== 'error') {
          this.send({
            type: 'unsubscribe',
            event: event
          });
        }
      }
    };
  }
  
  /**
   * Send message to server
   */
  send(message: any): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('⚠️ WebSocket not connected, cannot send message');
      return false;
    }
    
    try {
      this.ws.send(JSON.stringify(message));
      return true;
    } catch (error) {
      console.error('❌ Failed to send WebSocket message:', error);
      return false;
    }
  }
  
  /**
   * Handle WebSocket open event
   */
  private handleOpen(): void {
    this.isConnected = true;
    this.reconnectAttempts = 0;
    this.reconnectDelay = 1000;
    
    // Start ping interval
    this.pingInterval = setInterval(() => {
      this.send({ type: 'ping', timestamp: Date.now() });
    }, 30000); // Ping every 30 seconds
    
    // Notify subscribers
    this.notifySubscribers('connected', {});
  }
  
  /**
   * 🚀 УЛЬТРА-КРИТИЧНО: Декодирование бинарного game_state
   */
  private decodeBinaryGameState(binaryData: string): any {
    try {
      // Декодируем из base64
      const buffer = atob(binaryData);
      const bytes = new Uint8Array(buffer.length);
      for (let i = 0; i < buffer.length; i++) {
        bytes[i] = buffer.charCodeAt(i);
      }
      
      // Проверяем минимальную длину
      if (bytes.length < 7) {
        throw new Error(`Binary data too short: ${bytes.length} bytes`);
      }
      
      // Распаковываем бинарные данные
      const view = new DataView(bytes.buffer);
      
      const msgType = view.getUint8(0);  // Должно быть 1 для game_state
      if (msgType !== 1) {
        throw new Error(`Invalid binary message type: ${msgType}`);
      }
      
      const status = view.getUint8(1);
      const flags = view.getUint8(2);
      const coefInt = view.getUint16(3, false);  // Big endian (false = big endian)
      const lastCoefInt = view.getUint16(5, false);  // ИСПРАВЛЕНО: правильные индексы 3,4 и 5,6
      
      // Декодируем статус
      const statusMap = ['waiting', 'playing', 'crashed'];
      const statusStr = statusMap[status] || 'waiting';
      
      // Декодируем флаги
      const crashed = Boolean(flags & 1);         // bit 0
      const gameJustCrashed = Boolean(flags & 2); // bit 1
      const hasCountdown = Boolean(flags & 4);    // bit 2
      
      // Конвертируем коэффициенты обратно в float
      const coefficient = (coefInt / 100).toFixed(2);
      const lastCrashCoeff = (lastCoefInt / 100).toFixed(2);
      
      // Countdown опционален, проверяем флаг
      let countdown = 0;
      if (hasCountdown && bytes.length > 7) {
        countdown = view.getUint8(7);
      }
      
      return {
        coefficient: coefficient,
        status: statusStr,
        countdown: countdown,
        crashed: crashed,
        crash_point: null,  // Не передается в бинарном формате
        last_crash_coefficient: lastCrashCoeff,
        game_just_crashed: gameJustCrashed
      };
      
    } catch (error) {
      console.error('❌ Binary decoding failed:', error);
      return null;
    }
  }

  /**
   * 🚀 КРИТИЧНО: Декодирование бинарного crash_history
   */
  private decodeBinaryCrashHistory(binaryData: string): string[] {
    try {
      // Декодируем из base64
      const buffer = atob(binaryData);
      const bytes = new Uint8Array(buffer.length);
      for (let i = 0; i < buffer.length; i++) {
        bytes[i] = buffer.charCodeAt(i);
      }
      
      // Проверяем минимальную длину
      if (bytes.length < 3) {
        throw new Error(`Binary crash history too short: ${bytes.length} bytes`);
      }
      
      // Распаковываем бинарные данные
      const view = new DataView(bytes.buffer);
      
      const msgType = view.getUint8(0);  // Должно быть 2 для crash_history
      if (msgType !== 2) {
        throw new Error(`Invalid binary crash history type: ${msgType}`);
      }
      
      // Декодируем коэффициенты
      const coefficients: string[] = [];
      const numCoeffs = (bytes.length - 1) / 2;  // -1 для типа, /2 для uint16
      
      for (let i = 0; i < numCoeffs; i++) {
        const offset = 1 + i * 2;  // 1 байт тип + i * 2 байта uint16
        const coeffInt = view.getUint16(offset, false);  // Big endian
        const coefficient = (coeffInt / 100).toFixed(2);
        coefficients.push(coefficient);
      }
      
      return coefficients;
      
    } catch (error) {
      console.error('❌ Binary crash history decoding failed:', error);
      return [];
    }
  }

  /**
   * 🚀 КРИТИЧНО: Декомпрессия сжатых сообщений для экономии трафика
   */
  private decompressMessage(compressedData: any): WebSocketMessage {
    // 🚀 УЛЬТРА-КРИТИЧНО: Проверяем бинарные сообщения
    if (compressedData.b) {
      const decodedData = this.decodeBinaryGameState(compressedData.b);
      if (decodedData) {
        return {
          type: 'game_state',
          timestamp: Date.now(),
          data: decodedData
        };
      }
    }
    
    const type = compressedData.t;
    const timestamp = compressedData.ts || Date.now();
    const data = compressedData.d || {};
    
    // КРИТИЧНО: Проверяем наличие обязательных полей
    if (!type) {
      console.error('❌ Missing message type in compressed data:', compressedData);
      return {
        type: 'error',
        timestamp: Date.now(),
        data: { error: 'Invalid message format' }
      };
    }

    // Маппинг сжатых типов обратно в полные
    const typeMap: Record<string, string> = {
      'gs': 'game_state',
      'ps': 'player_status', 
      'bu': 'balance_update',
      'ch': 'crash_history',
      'chb': 'crash_history'  // crash_history_binary -> crash_history
    };

    const fullType = typeMap[type] || type;

    // Декомпрессия данных в зависимости от типа
    let decompressedData: any = data;

    if (type === 'gs') {
      // Декомпрессия game_state
      decompressedData = {
        coefficient: data.c || "1.0",
        status: data.s === 'w' ? 'waiting' : data.s === 'p' ? 'playing' : data.s === 'c' ? 'crashed' : 'waiting',
        countdown: data.cd || 0,
        crashed: Boolean(data.cr),
        crash_point: data.cp || null,
        last_crash_coefficient: data.lc || "1.0",
        game_just_crashed: Boolean(data.jc)
      };
    } else if (type === 'ps') {
      // Декомпрессия player_status
      decompressedData = {
        in_game: Boolean(data.ig),
        cashed_out: Boolean(data.co),
        show_win_message: Boolean(data.sw),
        show_crash_message: Boolean(data.sc),
        win_amount: data.wa || "0",
        win_multiplier: data.wm || "0"
      };
    } else if (type === 'bu') {
      // Декомпрессия balance_update
      decompressedData = {
        user_id: data.u !== undefined ? data.u : 0,  // ИСПРАВЛЕНО: правильная проверка user_id
        balance: data.b || "0",
        reason: data.r || "",
        timestamp: timestamp
      };
    } else if (type === 'ch') {
      // Декомпрессия crash_history (обычная)
      decompressedData = {
        history: data || []
      };
    } else if (type === 'chb') {
      // 🚀 КРИТИЧНО: Декомпрессия бинарной crash_history
      const decodedHistory = this.decodeBinaryCrashHistory(data);
      decompressedData = {
        history: decodedHistory
      };
    }

    return {
      type: fullType,
      timestamp: timestamp,
      data: decompressedData
    };
  }

  /**
   * Handle WebSocket message
   */
  private handleMessage(event: MessageEvent): void {
    try {
      const rawMessage = JSON.parse(event.data);
      
      // 🚀 КРИТИЧНО: Проверяем, сжатое ли это сообщение
      let message: WebSocketMessage;
      if (rawMessage.t || rawMessage.b) {
        // Сжатое сообщение (с полем t или бинарное с полем b) - декомпрессируем
        message = this.decompressMessage(rawMessage);
      } else {
        // Обычное сообщение - используем как есть
        message = rawMessage as WebSocketMessage;
      }
      
      // Only log important messages, not ping/pong spam
      
      // Handle ping/pong
      if (message.type === 'ping') {
        this.send({ type: 'pong', timestamp: Date.now() });
        return;
      }
      
      // Handle subscription confirmations from backend
      if (message.type === 'subscribed') {
        return;
      }
      
      if (message.type === 'unsubscribed') {
        return;
      }
      
      // Notify subscribers
      this.notifySubscribers(message.type as EventType, message.data || message);
      
    } catch (error) {
      console.error('❌ Failed to parse WebSocket message:', error, 'Raw data:', event.data);
    }
  }
  
  /**
   * Handle WebSocket error
   */
  private handleError(event: Event): void {
    console.error('❌ WebSocket error:', event);
    this.notifySubscribers('error', { error: event });
  }
  
  /**
   * Handle WebSocket close
   */
  private handleClose(event: CloseEvent): void {
    this.isConnected = false;
    
    // Clear ping interval
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
    
    // Notify subscribers
    this.notifySubscribers('disconnected', { code: event.code, reason: event.reason });
    
    // Attempt reconnection if not intentional close
    if (event.code !== 1000 && event.code !== 1001 && this.reconnectAttempts < this.maxReconnectAttempts) {
      this.attemptReconnect();
    }
  }
  
  /**
   * Attempt to reconnect with exponential backoff
   */
  private attemptReconnect(): void {
    if (this.reconnectTimer) {
      return; // Already attempting reconnect
    }
    
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // Exponential backoff
    
    this.reconnectTimer = setTimeout(async () => {
      this.reconnectTimer = null;
      
      if (this.userId !== null) {
        const success = await this.connect(this.userId, this.initData);
        if (!success && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.attemptReconnect();
        }
      }
    }, delay);
  }
  
  /**
   * Notify event subscribers
   */
  private notifySubscribers(eventType: EventType, data: any): void {
    const subscribers = this.eventSubscriptions.filter(sub => sub.event === eventType);
    
    // Only log for important events, not spam
    
    for (const subscriber of subscribers) {
      try {
        subscriber.callback(data);
      } catch (error) {
        console.error(`❌ Error in ${eventType} subscriber:`, error || 'Unknown error');
        // Prevent undefined errors from propagating
        if (error === undefined) {
          console.warn('⚠️ Subscriber threw undefined error, this may indicate a bug');
        }
      }
    }
  }
  
  /**
   * Get connection status
   */
  isWebSocketConnected(): boolean {
    return this.isConnected && this.ws?.readyState === WebSocket.OPEN;
  }
  
  /**
   * Get connection statistics
   */
  getStats(): any {
    return {
      connected: this.isConnected,
      readyState: this.ws?.readyState,
      reconnectAttempts: this.reconnectAttempts,
      subscriptions: this.eventSubscriptions.length,
      url: this.url,
      userId: this.userId
    };
  }
}

// Export singleton instance
export const websocketService = new WebSocketService();
export default websocketService;