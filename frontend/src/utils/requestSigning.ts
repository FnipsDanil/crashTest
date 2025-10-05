/**
 * Request signing utilities for HMAC security
 * Provides client-side signing for critical game operations using Web Crypto API
 */

interface GameAction {
  user_id: number
  action: string
  timestamp: number
  params: Record<string, any>
}

class RequestSigner {
  private secretKey: CryptoKey | null = null
  private maxAge: number = 30 // 30 seconds max age

  constructor(secretKeyString: string) {
    this.initializeKey(secretKeyString)
  }

  private async initializeKey(secretKeyString: string): Promise<void> {
    try {
      const encoder = new TextEncoder()
      const keyData = encoder.encode(secretKeyString)
      
      this.secretKey = await crypto.subtle.importKey(
        'raw',
        keyData,
        { name: 'HMAC', hash: 'SHA-256' },
        false,
        ['sign']
      )
    } catch (error) {
      console.error('🚨 Failed to initialize HMAC key:', error)
    }
  }

  /**
   * Generate HMAC signature for game action
   */
  async generateActionSignature(userId: number, action: string, params: Record<string, any>, timestamp?: number): Promise<{ signature: string; timestamp: number }> {
    if (!this.secretKey) {
      throw new Error('HMAC key not initialized')
    }

    if (timestamp === undefined) {
      timestamp = Math.floor(Date.now() / 1000)
    }

    // Create payload for signing
    const payload: GameAction = {
      user_id: userId,
      action: action,
      timestamp: timestamp,
      params: params
    }

    // Convert to JSON string with sorted keys for consistency
    const payloadStr = JSON.stringify(payload, Object.keys(payload).sort())

    try {
      // Generate HMAC signature using Web Crypto API
      const encoder = new TextEncoder()
      const data = encoder.encode(payloadStr)
      const signatureArrayBuffer = await crypto.subtle.sign('HMAC', this.secretKey, data)
      
      // Convert to hex string
      const signature = Array.from(new Uint8Array(signatureArrayBuffer))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('')

      return { signature, timestamp }
    } catch (error) {
      console.error('🚨 Failed to generate HMAC signature:', error)
      throw error
    }
  }

  /**
   * Sign a join request
   */
  async signJoinRequest(userId: number, betAmount: number): Promise<{ signature: string; timestamp: string }> {
    const { signature, timestamp } = await this.generateActionSignature(userId, 'join', { bet_amount: betAmount })
    return { signature, timestamp: timestamp.toString() }
  }

  /**
   * Sign a cashout request
   */
  async signCashoutRequest(userId: number): Promise<{ signature: string; timestamp: string }> {
    const { signature, timestamp } = await this.generateActionSignature(userId, 'cashout', {})
    return { signature, timestamp: timestamp.toString() }
  }
}

// Environment-based configuration
const getSecretKey = (): string | null => {
  // Try to get secret key from environment variables
  const key = import.meta.env.VITE_HMAC_SECRET_KEY
  
  if (!key) {
    console.warn('🔒 HMAC secret key not configured - request signing disabled')
    return null
  }
  
  return key
}

// Export singleton instance
let requestSigner: RequestSigner | null = null

export const getRequestSigner = (): RequestSigner | null => {
  if (!requestSigner) {
    const secretKey = getSecretKey()
    if (secretKey) {
      requestSigner = new RequestSigner(secretKey)
    }
  }
  return requestSigner
}

export const isRequestSigningEnabled = (): boolean => {
  return getRequestSigner() !== null
}