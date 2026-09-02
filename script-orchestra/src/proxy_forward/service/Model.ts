export interface ProxyForwardStatus {
  running: boolean
  listen_host: string
  listen_port: number | null
  target_host: string
  target_port: number | null
  started_at: string | null
  active_connections: number
  total_connections: number
  lan_ip: string | null
  lan_ips: string[]
  last_error: string | null
}

export interface ProxyForwardStartPayload {
  listen_host: string
  listen_port: number
  target_host: string
  target_port: number
}

export interface ProxyForwardSettings {
  listen_host: string
  listen_port: number
  target_host: string
  target_port: number
}
