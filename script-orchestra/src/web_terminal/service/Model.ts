export interface TerminalWindow {
  window_id: string
  title: string
  cwd: string
  created_at: number
  last_active: number
  pty_alive: boolean
}

export interface WtEvent {
  window_id: string
  event: 'wt_output' | 'wt_exit'
  data?: string
}
