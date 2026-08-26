/**
 * WebSocket Service for Caffeinate
 */
import { io, Socket } from 'socket.io-client'
import type { CaffeinateLogEntry } from './api'

const getSocketURL = () => {
  const protocol = window.location.protocol
  const hostname = window.location.hostname
  const backendHost = hostname === 'localhost' || hostname === '127.0.0.1'
    ? 'localhost'
    : hostname
  return `${protocol}//${backendHost}:50001`
}

const SOCKET_URL = getSocketURL()
const NAMESPACE = '/caffeinate'

export class CaffeinateWebSocketService {
  private socket: Socket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5

  connect(): void {
    if (this.socket?.connected) {
      return
    }

    this.socket = io(SOCKET_URL + NAMESPACE, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: this.maxReconnectAttempts
    })

    this.socket.on('connect', () => {
      console.log('[CaffeinateWS] Connected')
      this.reconnectAttempts = 0
    })

    this.socket.on('disconnect', (reason) => {
      console.log('[CaffeinateWS] Disconnected:', reason)
    })

    this.socket.on('connect_error', (error) => {
      console.error('[CaffeinateWS] Connection error:', error)
      this.reconnectAttempts++
    })
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
    }
  }

  onLog(callback: (entry: CaffeinateLogEntry) => void): void {
    if (!this.socket) {
      console.error('[CaffeinateWS] Socket not connected')
      return
    }
    this.socket.on('caffeinate_log', (data: CaffeinateLogEntry) => callback(data))
  }

  offLog(): void {
    if (this.socket) {
      this.socket.off('caffeinate_log')
    }
  }

  isConnected(): boolean {
    return this.socket?.connected || false
  }
}

let wsService: CaffeinateWebSocketService | null = null

export function getWebSocketService(): CaffeinateWebSocketService {
  if (!wsService) {
    wsService = new CaffeinateWebSocketService()
  }
  return wsService
}
