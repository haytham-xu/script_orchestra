/**
 * WebSocket Client for File-Git Progress Updates
 * Gracefully handles connection failures if WebSocket is not available
 */
import { io, Socket } from 'socket.io-client'
import { BACKEND_BASE_URL } from '@/basic/Constants'

export interface ProgressData {
  repo_id: string
  operation: string  // push, pull, verify, scan
  phase: string      // scanning, uploading, downloading, etc.
  current: number
  total: number
  percentage: number
  message: string
}

export interface StatusData {
  repo_id: string
  status: string  // ready, syncing, error, success
  message: string
}

export interface LogData {
  repo_id: string
  level: string  // info, warning, error
  message: string
  timestamp: string
}

class WebSocketClient {
  private socket: Socket | null = null
  private connected: boolean = false
  private reconnectAttempts: number = 0
  private maxReconnectAttempts: number = 3

  /**
   * Connect to WebSocket server
   */
  connect() {
    if (this.socket) {
      console.log('[WebSocket] Already connected or connecting')
      return
    }

    try {
      console.log('[WebSocket] Connecting to', BACKEND_BASE_URL)

      this.socket = io(BACKEND_BASE_URL, {
        reconnection: true,
        reconnectionDelay: 2000,
        reconnectionAttempts: this.maxReconnectAttempts,
        timeout: 5000
      })

      this.socket.on('connect', () => {
        console.log('[WebSocket] Connected successfully')
        this.connected = true
        this.reconnectAttempts = 0
      })

      this.socket.on('disconnect', (reason) => {
        console.log('[WebSocket] Disconnected:', reason)
        this.connected = false
      })

      this.socket.on('connect_error', (error) => {
        console.warn('[WebSocket] Connection error:', error.message)
        this.reconnectAttempts++

        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
          console.log('[WebSocket] Max reconnect attempts reached, giving up')
          console.log('[WebSocket] Progress updates will be disabled (backend may not have WebSocket enabled)')
          this.disconnect()
        }
      })
    } catch (error) {
      console.warn('[WebSocket] Failed to initialize:', error)
      console.log('[WebSocket] Progress updates will be disabled')
    }
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect() {
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
      this.connected = false
      console.log('[WebSocket] Disconnected')
    }
  }

  /**
   * Check if connected
   */
  isConnected(): boolean {
    return this.connected
  }

  /**
   * Subscribe to progress updates for a specific repository
   */
  onProgress(repoId: string, callback: (data: ProgressData) => void) {
    if (!this.socket) {
      console.warn('[WebSocket] Not connected, cannot subscribe to progress')
      return () => {}
    }

    const eventName = `repo:${repoId}:progress`
    this.socket.on(eventName, callback)

    console.log(`[WebSocket] Subscribed to progress for repo ${repoId}`)

    // Return unsubscribe function
    return () => {
      if (this.socket) {
        this.socket.off(eventName, callback)
        console.log(`[WebSocket] Unsubscribed from progress for repo ${repoId}`)
      }
    }
  }

  /**
   * Subscribe to status updates for a specific repository
   */
  onStatus(repoId: string, callback: (data: StatusData) => void) {
    if (!this.socket) {
      console.warn('[WebSocket] Not connected, cannot subscribe to status')
      return () => {}
    }

    const eventName = `repo:${repoId}:status`
    this.socket.on(eventName, callback)

    console.log(`[WebSocket] Subscribed to status for repo ${repoId}`)

    // Return unsubscribe function
    return () => {
      if (this.socket) {
        this.socket.off(eventName, callback)
        console.log(`[WebSocket] Unsubscribed from status for repo ${repoId}`)
      }
    }
  }

  /**
   * Subscribe to log messages for a specific repository
   */
  onLog(repoId: string, callback: (data: LogData) => void) {
    if (!this.socket) {
      console.warn('[WebSocket] Not connected, cannot subscribe to logs')
      return () => {}
    }

    const eventName = `repo:${repoId}:log`
    this.socket.on(eventName, callback)

    console.log(`[WebSocket] Subscribed to logs for repo ${repoId}`)

    // Return unsubscribe function
    return () => {
      if (this.socket) {
        this.socket.off(eventName, callback)
        console.log(`[WebSocket] Unsubscribed from logs for repo ${repoId}`)
      }
    }
  }

  /**
   * Subscribe to all progress updates (across all repos)
   */
  onAllProgress(callback: (data: ProgressData) => void) {
    if (!this.socket) {
      console.warn('[WebSocket] Not connected, cannot subscribe to all progress')
      return () => {}
    }

    this.socket.on('progress', callback)
    console.log('[WebSocket] Subscribed to all progress updates')

    return () => {
      if (this.socket) {
        this.socket.off('progress', callback)
        console.log('[WebSocket] Unsubscribed from all progress updates')
      }
    }
  }
}

// Global singleton instance
export const wsClient = new WebSocketClient()

// Auto-connect when imported (gracefully fails if backend doesn't support it)
if (typeof window !== 'undefined') {
  // Only in browser environment
  wsClient.connect()
}
