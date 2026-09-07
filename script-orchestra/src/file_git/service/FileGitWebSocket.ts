import { io, Socket } from 'socket.io-client'
import { BACKEND_BASE_URL } from '@/basic/Constants'

export interface ProgressEvent {
  repo_id: string
  operation: string
  phase: string
  current: number
  total: number
  percentage: number
  message: string
}

export interface StatusEvent {
  repo_id: string
  status: 'done' | 'error'
  message: string
}

class FileGitWebSocketService {
  private socket: Socket | null = null

  connect(): void {
    if (this.socket?.connected) return
    this.socket = io(BACKEND_BASE_URL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: 5,
    })
    this.socket.on('connect', () => console.log('[FileGitWS] connected'))
    this.socket.on('disconnect', (reason) => console.log('[FileGitWS] disconnected:', reason))
    this.socket.on('connect_error', (err) => console.error('[FileGitWS] error:', err))
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
    }
  }

  onProgress(repoId: string, cb: (e: ProgressEvent) => void): void {
    this.socket?.on(`repo:${repoId}:progress`, cb)
  }

  onStatus(repoId: string, cb: (e: StatusEvent) => void): void {
    this.socket?.on(`repo:${repoId}:status`, cb)
  }

  off(repoId: string): void {
    this.socket?.off(`repo:${repoId}:progress`)
    this.socket?.off(`repo:${repoId}:status`)
  }

  isConnected(): boolean {
    return this.socket?.connected ?? false
  }
}

export const fileGitWS = new FileGitWebSocketService()
