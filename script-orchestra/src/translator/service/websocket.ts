/**
 * WebSocket Service for Translator
 *
 * Subscribes to streaming translation progress on the shared Socket.IO server,
 * '/translator' namespace, event 'translator_progress'. Purely a progress
 * overlay — the authoritative result still arrives via the HTTP response.
 */
import { io, Socket } from 'socket.io-client'

export interface TranslatorProgress {
  job_id: string
  scene: 'zh2en' | 'en2zh'
  phase: 'translating' | 'back_translating' | 'learning_points' | 'done'
  delta?: string   // incremental text chunk (phase 'translating')
  text?: string
}

const getSocketURL = () => {
  const protocol = window.location.protocol
  const hostname = window.location.hostname
  const backendHost = hostname === 'localhost' || hostname === '127.0.0.1' ? 'localhost' : hostname
  return `${protocol}//${backendHost}:50001`
}

const SOCKET_URL = getSocketURL()
const NAMESPACE = '/translator'

export class TranslatorWebSocketService {
  private socket: Socket | null = null

  connect(): void {
    if (this.socket?.connected) return
    this.socket = io(SOCKET_URL + NAMESPACE, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: 5,
    })
    this.socket.on('connect', () => console.log('[TranslatorWS] Connected'))
    this.socket.on('disconnect', (r) => console.log('[TranslatorWS] Disconnected:', r))
    this.socket.on('connect_error', (e) => console.error('[TranslatorWS] Connection error:', e))
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
    }
  }

  onProgress(callback: (p: TranslatorProgress) => void): void {
    if (!this.socket) {
      console.error('[TranslatorWS] Socket not connected. Call connect() first.')
      return
    }
    this.socket.on('translator_progress', (data: TranslatorProgress) => callback(data))
  }

  offProgress(): void {
    if (this.socket) this.socket.off('translator_progress')
  }

  isConnected(): boolean {
    return this.socket?.connected || false
  }
}

// Singleton instance
let wsService: TranslatorWebSocketService | null = null

export function getTranslatorWebSocketService(): TranslatorWebSocketService {
  if (!wsService) wsService = new TranslatorWebSocketService()
  return wsService
}
