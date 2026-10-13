import { CLIPBOARD_SHARE_ENDPOINT } from '@/basic/Constants'
import { getRequest, postRequest, deleteRequest } from '@/basic/RequestService'
import axios from 'axios'

const CLIPBOARD = `${CLIPBOARD_SHARE_ENDPOINT}/clipboard`
const SERVER = `${CLIPBOARD_SHARE_ENDPOINT}/server`

// On LAN: window.location is http://192.168.x.x:5001 — use relative URLs so
// Vite proxies /clipboard-share/* to 127.0.0.1:50001.
// On localhost: use RequestService (direct to 127.0.0.1:50001).
const isLocalhost = () => {
  const h = window.location.hostname
  return h === 'localhost' || h === '127.0.0.1'
}

async function _get<T>(path: string, params = {}): Promise<T> {
  if (isLocalhost()) return getRequest<T>(path, params)
  const res = await axios.get(path, { params })
  return res.data as T
}

async function _post<T>(path: string, payload = {}): Promise<T> {
  if (isLocalhost()) return postRequest<T>(path, {}, payload)
  const res = await axios.post(path, payload)
  return res.data as T
}

async function _delete<T>(path: string): Promise<T> {
  if (isLocalhost()) return deleteRequest<T>(path)
  const res = await axios.delete(path)
  return res.data as T
}

export interface ClipboardItem {
  id: number
  content: string
  source: string
  timestamp: string
  length: number
}

export interface LanServerStatus {
  running: boolean
  port: number | null
  ip: string
  url: string | null
}

export const addClipboardContent = (content: string, source = 'web') =>
  _post<ClipboardItem>(`${CLIPBOARD}/add`, { content, source })

export const getLatestClipboard = () =>
  _get<ClipboardItem>(`${CLIPBOARD}/latest`)

export const getClipboardHistory = (limit = 20) =>
  _get<ClipboardItem[]>(`${CLIPBOARD}/history`, { limit })

export const clearClipboardHistory = () =>
  _delete<{ message: string; count: number }>(`${CLIPBOARD}/clear`)

export const getLanServerStatus = () =>
  _get<LanServerStatus>(`${SERVER}/status`)

export const startLanServer = (port?: number) =>
  _post<LanServerStatus & { message: string }>(`${SERVER}/start`, port !== undefined ? { port } : {})

export const stopLanServer = () =>
  _post<LanServerStatus & { message: string }>(`${SERVER}/stop`)
