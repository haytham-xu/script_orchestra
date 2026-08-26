/**
 * WebSocket service for Browser Agent — subscribes to download progress
 * on the /browser_agent namespace. Mirrors the caffeinate pattern.
 */
import { io, Socket } from 'socket.io-client'
import type { ProgressEvent } from './Model'

const getSocketURL = () => {
  const protocol = window.location.protocol
  const hostname = window.location.hostname
  const backendHost = hostname === 'localhost' || hostname === '127.0.0.1'
    ? 'localhost'
    : hostname
  return `${protocol}//${backendHost}:50001`
}

const SOCKET_URL = getSocketURL()
const NAMESPACE = '/browser_agent'

export class BrowserAgentWebSocketService {
  private socket: Socket | null = null

  connect(): void {
    if (this.socket?.connected) return
    this.socket = io(SOCKET_URL + NAMESPACE, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 5,
    })
    this.socket.on('connect', () => console.log('[browser_agent] ws connected'))
    this.socket.on('disconnect', () => console.log('[browser_agent] ws disconnected'))
  }

  onProgress(cb: (e: ProgressEvent) => void): void {
    this.socket?.on('browser_agent_progress', (data: ProgressEvent) => cb(data))
  }

  disconnect(): void {
    this.socket?.disconnect()
    this.socket = null
  }
}

let wsService: BrowserAgentWebSocketService | null = null
export function getWebSocketService(): BrowserAgentWebSocketService {
  return (wsService ??= new BrowserAgentWebSocketService())
}
