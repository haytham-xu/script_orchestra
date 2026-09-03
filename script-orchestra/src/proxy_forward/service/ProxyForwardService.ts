import { deleteRequest, getRequest, postRequest, putRequest } from '@/basic/RequestService'
import { PROXY_FORWARD_ENDPOINT } from '@/basic/Constants'
import type {
  ProxyForwardHistoryEntry,
  ProxyForwardSettings,
  ProxyForwardStartPayload,
  ProxyForwardStatus,
} from './Model'

const B = PROXY_FORWARD_ENDPOINT

export async function getStatus(): Promise<ProxyForwardStatus> {
  return await getRequest<ProxyForwardStatus>(`${B}/status`)
}

export async function getNetwork(): Promise<ProxyForwardStatus> {
  return await getRequest<ProxyForwardStatus>(`${B}/network`)
}

export async function startProxy(payload: ProxyForwardStartPayload): Promise<ProxyForwardStatus> {
  return await postRequest(`${B}/start`, {}, payload) as ProxyForwardStatus
}

export async function stopProxy(): Promise<ProxyForwardStatus> {
  return await postRequest(`${B}/stop`) as ProxyForwardStatus
}

export async function getSettings(): Promise<ProxyForwardSettings> {
  return await getRequest<ProxyForwardSettings>(`${B}/settings`)
}

export async function updateSettings(settings: ProxyForwardSettings): Promise<ProxyForwardSettings> {
  return await putRequest<ProxyForwardSettings>(`${B}/settings`, {}, settings)
}

export async function getHistory(limit: number = 200): Promise<ProxyForwardHistoryEntry[]> {
  return await getRequest<ProxyForwardHistoryEntry[]>(`${B}/history`, { limit })
}

export async function clearHistory(): Promise<{ cleared: number; message: string }> {
  return await deleteRequest<{ cleared: number; message: string }>(`${B}/history`)
}
