/**
 * Claude Bridge — WebSocket client (/claude-bridge namespace).
 *
 * Streams agent events (cb_event) and sends user actions. URL derives from
 * window.location.hostname so it works over LAN / a tunnel without editing code.
 */
import { io, Socket } from 'socket.io-client'
import { backendOrigin } from './origin'

const NAMESPACE = '/claude-bridge'

export interface CbEvent {
  session_id: string
  type:
    | 'assistant_text'
    | 'thinking'
    | 'tool_use'
    | 'tool_result'
    | 'result'
    | 'permission_request'
    | 'error'
    | 'session_status'
    | 'cb_pty_output'
    | 'cb_pty_exit'
  // assistant_text
  text?: string
  // thinking
  thinking?: string
  // tool_use
  id?: string
  name?: string
  input?: Record<string, unknown>
  // tool_result
  tool_use_id?: string
  content?: string
  is_error?: boolean
  // result
  num_turns?: number
  total_cost_usd?: number | null
  duration_ms?: number
  result?: string | null
  // permission_request
  request_id?: string
  tool?: string
  risk?: 'high' | 'normal'
  summary?: string
  // session_status / error
  status?: string
  subtype?: string
  message?: string
  // pty
  pty_id?: string
  data?: string
}

export class ClaudeBridgeWebSocket {
  private socket: Socket | null = null

  connect(token?: string): void {
    if (this.socket?.connected) return
    this.socket = io(backendOrigin() + NAMESPACE, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      auth: token ? { token } : undefined,
    })
    this.socket.on('connect', () => console.log('[ClaudeBridgeWS] connected'))
    this.socket.on('disconnect', (r) => console.log('[ClaudeBridgeWS] disconnected:', r))
    this.socket.on('connect_error', (e) => console.error('[ClaudeBridgeWS] error:', e))
  }

  disconnect(): void {
    this.socket?.disconnect()
    this.socket = null
  }

  onEvent(cb: (e: CbEvent) => void): void {
    this.socket?.on('cb_event', cb)
  }

  sendMessage(sessionId: string, text: string): void {
    this.socket?.emit('cb_user_message', { session_id: sessionId, text })
  }

  respondPermission(sessionId: string, requestId: string, decision: 'allow' | 'deny'): void {
    this.socket?.emit('cb_permission_response', {
      session_id: sessionId,
      request_id: requestId,
      decision,
    })
  }

  interrupt(sessionId: string): void {
    this.socket?.emit('cb_interrupt', { session_id: sessionId })
  }

  setModel(sessionId: string, model: string): void {
    this.socket?.emit('cb_set_model', { session_id: sessionId, model })
  }

  // ---- PTY ----
  sendPtyInput(ptyId: string, data: string): void {
    this.socket?.emit('cb_pty_input', { pty_id: ptyId, data })
  }

  sendPtyResize(ptyId: string, cols: number, rows: number): void {
    this.socket?.emit('cb_pty_resize', { pty_id: ptyId, cols, rows })
  }
}
