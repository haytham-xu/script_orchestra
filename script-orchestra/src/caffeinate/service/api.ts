/**
 * Caffeinate API Service
 */

const getBaseURL = () => {
  const protocol = window.location.protocol
  const hostname = window.location.hostname
  const backendHost = hostname === 'localhost' || hostname === '127.0.0.1'
    ? 'localhost'
    : hostname
  return `${protocol}//${backendHost}:5001/caffeinate/caffeinate`
}

const BASE_URL = getBaseURL()

export interface CaffeinateStatus {
  running: boolean
  interval_seconds: number
  started_at: string | null
  pid: number | null
  log_count: number
}

export interface CaffeinateLogEntry {
  id: number
  timestamp: string
  message: string
}

export async function getStatus(): Promise<CaffeinateStatus> {
  const response = await fetch(`${BASE_URL}/status`)
  if (!response.ok) {
    throw new Error('Failed to fetch caffeinate status')
  }
  return response.json()
}

export async function startCaffeinate(intervalSeconds: number): Promise<CaffeinateStatus> {
  const response = await fetch(`${BASE_URL}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ interval_seconds: intervalSeconds })
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to start caffeinate' }))
    throw new Error(error.message || 'Failed to start caffeinate')
  }
  return response.json()
}

export async function stopCaffeinate(): Promise<CaffeinateStatus> {
  const response = await fetch(`${BASE_URL}/stop`, { method: 'POST' })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to stop caffeinate' }))
    throw new Error(error.message || 'Failed to stop caffeinate')
  }
  return response.json()
}

export async function getLogs(limit: number = 500): Promise<CaffeinateLogEntry[]> {
  const response = await fetch(`${BASE_URL}/logs?limit=${limit}`)
  if (!response.ok) {
    throw new Error('Failed to fetch caffeinate logs')
  }
  return response.json()
}

export async function clearLogs(): Promise<{ message: string; count: number }> {
  const response = await fetch(`${BASE_URL}/logs`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error('Failed to clear caffeinate logs')
  }
  return response.json()
}
