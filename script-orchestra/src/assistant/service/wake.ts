/**
 * WebSocket connection to the wake-word namespace on the backend.
 *
 * The backend emits `wake_event` messages with a `type` discriminator:
 *   - status:       running/keyword changed
 *   - wake:         wake word triggered
 *   - transcribing: post-wake transcription started
 *   - transcript:   final text
 *   - cancelled:    utterance too short / silent
 *   - error:        listener error
 */
import { io, Socket } from 'socket.io-client'

export type WakeEvent =
  | { type: 'status'; running: boolean; keyword: string }
  | { type: 'wake'; keyword: string; score: number }
  | { type: 'transcribing' }
  | { type: 'transcript'; text: string; language?: string; duration?: number }
  | { type: 'cancelled'; reason: string }
  | { type: 'error'; message: string }

const getSocketURL = () => {
  const protocol = window.location.protocol
  const hostname = window.location.hostname
  const backendHost = hostname === 'localhost' || hostname === '127.0.0.1'
    ? 'localhost'
    : hostname
  return `${protocol}//${backendHost}:50001`
}

const SOCKET_URL = getSocketURL()
const NAMESPACE = '/wake'

export class WakeWebSocketService {
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
    this.socket.on('connect', () => console.log('[WakeWS] connected'))
    this.socket.on('disconnect', (r) => console.log('[WakeWS] disconnect:', r))
    this.socket.on('connect_error', (e) => console.error('[WakeWS] err:', e))
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
    }
  }

  onEvent(cb: (event: WakeEvent) => void): void {
    if (!this.socket) return
    this.socket.on('wake_event', (data: WakeEvent) => cb(data))
  }

  offEvent(): void {
    this.socket?.off('wake_event')
  }

  isConnected(): boolean {
    return !!this.socket?.connected
  }
}

let wsService: WakeWebSocketService | null = null

export function getWakeWebSocketService(): WakeWebSocketService {
  if (!wsService) wsService = new WakeWebSocketService()
  return wsService
}
