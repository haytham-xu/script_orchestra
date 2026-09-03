export interface RelayProxyListenerSettings {
  enabled: boolean
  bind_host: string
  bind_port: number | null
}

export interface RelayProxySettings {
  mode: 'upstream_proxy' | 'direct'
  listeners: {
    http: RelayProxyListenerSettings
    socks5: RelayProxyListenerSettings
  }
  upstream: {
    protocol: 'http' | 'socks5'
    host: string
    port: number | null
  }
  access: {
    allowed_client_cidrs: string[]
  }
  limits: {
    max_connections: number
    connect_timeout_seconds: number
    idle_timeout_seconds: number
    max_header_bytes: number
    history_limit: number
  }
}

export interface RelayProxyHistoryEntry {
  id: number
  timestamp: string
  level: string
  event: string
  message: string
}

export interface RelayProxyStatus {
  running: boolean
  mode: 'upstream_proxy' | 'direct'
  listeners_runtime: Record<string, { enabled: boolean; bind_host: string; bind_port: number | null }>
  active_connections: number
  total_connections: number
  started_at: string | null
  last_error: string | null
  history_count: number
  lan_ip: string | null
  lan_ips: string[]
}

export interface RelayProxyProbeCheck {
  name: string
  ok: boolean
  skipped: boolean
  detail: string
}

export interface RelayProxyProbeResult {
  ok: boolean
  timestamp: string
  mode: 'upstream_proxy' | 'direct'
  checks: RelayProxyProbeCheck[]
}
