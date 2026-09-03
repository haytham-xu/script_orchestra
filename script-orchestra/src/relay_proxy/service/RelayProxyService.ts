import { deleteRequest, getRequest, postRequest, putRequest } from '@/basic/RequestService'
import { RELAY_PROXY_ENDPOINT } from '@/basic/Constants'
import type {
  RelayProxyHistoryEntry,
  RelayProxyProbeResult,
  RelayProxySettings,
  RelayProxyStatus,
} from './Model'

const B = RELAY_PROXY_ENDPOINT

export async function getStatus(): Promise<RelayProxyStatus> {
  return await getRequest<RelayProxyStatus>(`${B}/status`)
}

export async function startRelay(): Promise<RelayProxyStatus> {
  return await postRequest(`${B}/start`) as RelayProxyStatus
}

export async function stopRelay(): Promise<RelayProxyStatus> {
  return await postRequest(`${B}/stop`) as RelayProxyStatus
}

export async function getSettings(): Promise<RelayProxySettings> {
  return await getRequest<RelayProxySettings>(`${B}/settings`)
}

export async function updateSettings(patch: Partial<RelayProxySettings>): Promise<RelayProxySettings> {
  return await putRequest<RelayProxySettings>(`${B}/settings`, {}, patch)
}

export async function getHistory(limit: number = 200): Promise<RelayProxyHistoryEntry[]> {
  return await getRequest<RelayProxyHistoryEntry[]>(`${B}/history`, { limit })
}

export async function clearHistory(): Promise<{ cleared: number; message: string }> {
  return await deleteRequest<{ cleared: number; message: string }>(`${B}/history`)
}

export async function runDiagnosticsProbe(
  patch: Partial<RelayProxySettings> = {},
): Promise<RelayProxyProbeResult> {
  return await postRequest(`${B}/diagnostics/probe`, {}, patch) as RelayProxyProbeResult
}
