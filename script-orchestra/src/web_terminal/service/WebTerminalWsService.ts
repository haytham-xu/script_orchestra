import { io, Socket } from 'socket.io-client'
import { BACKEND_BASE_URL } from '../../basic/Constants'
import type { WtEvent } from './Model'

const NAMESPACE = '/web-terminal'

export class WebTerminalWsService {
  private socket: Socket | null = null
  private handlers: Array<(e: WtEvent) => void> = []

  connect(): void {
    if (this.socket?.connected) return
    // Derive ws origin the same way claude_bridge does (supports LAN + tunnel)
    const origin = (() => {
      const { protocol, hostname, port } = window.location
      const isDevPort = port !== '' && port !== '80' && port !== '443'
      if (isDevPort) {
        const host = hostname === '127.0.0.1' ? 'localhost' : hostname
        return `${protocol}//${host}:50001`
      }
      return window.location.origin
    })()

    this.socket = io(origin + NAMESPACE, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
    })
    this.socket.on('connect', () => console.log('[WebTerminalWS] connected'))
    this.socket.on('disconnect', (r) => console.log('[WebTerminalWS] disconnected:', r))
    this.socket.on('connect_error', (e) => console.error('[WebTerminalWS] error:', e))
    this.socket.on('wt_event', (e: WtEvent) => {
      this.handlers.forEach((h) => h(e))
    })
  }

  disconnect(): void {
    this.socket?.disconnect()
    this.socket = null
    this.handlers = []
  }

  onEvent(cb: (e: WtEvent) => void): void {
    this.handlers.push(cb)
  }

  offEvent(cb: (e: WtEvent) => void): void {
    this.handlers = this.handlers.filter((h) => h !== cb)
  }

  sendInput(windowId: string, data: string): void {
    this.socket?.emit('wt_input', { window_id: windowId, data })
  }

  sendResize(windowId: string, cols: number, rows: number): void {
    this.socket?.emit('wt_resize', { window_id: windowId, cols, rows })
  }
}
