/**
 * WebSocket Service for Clipboard Share
 *
 * Handles real-time clipboard updates via Socket.IO
 */
import { io, Socket } from 'socket.io-client'
import type { ClipboardItem } from './api'

// Dynamically determine the WebSocket URL based on current hostname
const getSocketURL = () => {
  const protocol = window.location.protocol
  const hostname = window.location.hostname
  const backendHost = hostname === 'localhost' || hostname === '127.0.0.1'
    ? 'localhost'
    : hostname
  return `${protocol}//${backendHost}:5001`
}

const SOCKET_URL = getSocketURL()
const NAMESPACE = '/clipboard'

export class ClipboardWebSocketService {
  private socket: Socket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5

  /**
   * Connect to the WebSocket server
   */
  connect(): void {
    if (this.socket?.connected) {
      console.log('[ClipboardWS] Already connected')
      return
    }

    console.log('[ClipboardWS] Connecting to', SOCKET_URL + NAMESPACE)

    this.socket = io(SOCKET_URL + NAMESPACE, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: this.maxReconnectAttempts
    })

    this.socket.on('connect', () => {
      console.log('[ClipboardWS] Connected')
      this.reconnectAttempts = 0
    })

    this.socket.on('disconnect', (reason) => {
      console.log('[ClipboardWS] Disconnected:', reason)
    })

    this.socket.on('connect_error', (error) => {
      console.error('[ClipboardWS] Connection error:', error)
      this.reconnectAttempts++
    })
  }

  /**
   * Disconnect from the WebSocket server
   */
  disconnect(): void {
    if (this.socket) {
      console.log('[ClipboardWS] Disconnecting')
      this.socket.disconnect()
      this.socket = null
    }
  }

  /**
   * Subscribe to clipboard updates
   */
  onClipboardUpdate(callback: (item: ClipboardItem) => void): void {
    if (!this.socket) {
      console.error('[ClipboardWS] Socket not connected. Call connect() first.')
      return
    }

    this.socket.on('clipboard_update', (data: ClipboardItem) => {
      console.log('[ClipboardWS] Received update:', data.id)
      callback(data)
    })
  }

  /**
   * Remove clipboard update listener
   */
  offClipboardUpdate(): void {
    if (this.socket) {
      this.socket.off('clipboard_update')
    }
  }

  /**
   * Check if connected
   */
  isConnected(): boolean {
    return this.socket?.connected || false
  }

  /**
   * Send ping to check connection
   */
  ping(): void {
    if (this.socket) {
      this.socket.emit('ping')
      this.socket.once('pong', (data) => {
        console.log('[ClipboardWS] Pong received:', data)
      })
    }
  }
}

// Singleton instance
let wsService: ClipboardWebSocketService | null = null

export function getWebSocketService(): ClipboardWebSocketService {
  if (!wsService) {
    wsService = new ClipboardWebSocketService()
  }
  return wsService
}
