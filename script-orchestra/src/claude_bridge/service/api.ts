/**
 * Claude Bridge — REST client (session lifecycle).
 *
 * Backend origin is resolved by backendOrigin() so it works on LAN dev (separate
 * :50001 process) and same-origin behind a tunnel. See origin.ts.
 */
import { backendOrigin } from './origin'

const BASE_URL = `${backendOrigin()}/claude-bridge`

export interface ModelAlias {
  label: string
  id: string
}

export interface BridgeConfig {
  models: ModelAlias[]
  default_model: string
  cwd_roots: string[]
  default_cwd: string
}

export interface SessionInfo {
  session_id: string
  cwd: string
  model: string
  ready: boolean
}

function authHeaders(token?: string): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function checkAuth(): Promise<{ auth_required: boolean }> {
  const res = await fetch(`${BASE_URL}/auth/check`)
  if (!res.ok) throw new Error('Failed to reach backend')
  return res.json()
}

export async function getConfig(token?: string): Promise<BridgeConfig> {
  const res = await fetch(`${BASE_URL}/config`, { headers: authHeaders(token) })
  if (!res.ok) throw new Error('Failed to fetch config')
  return res.json()
}

export async function createSession(
  cwd: string,
  model: string,
  token?: string,
): Promise<SessionInfo> {
  const res = await fetch(`${BASE_URL}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify({ cwd, model }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error || 'Failed to create session')
  }
  return res.json()
}

export async function closeSession(sessionId: string, token?: string): Promise<void> {
  await fetch(`${BASE_URL}/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  })
}

export interface PtyInfo {
  pty_id: string
  cwd: string
}

export async function createPty(cwd: string, token?: string): Promise<PtyInfo> {
  const res = await fetch(`${BASE_URL}/pty/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify({ cwd }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error || 'Failed to create pty session')
  }
  return res.json()
}

export async function closePty(ptyId: string, token?: string): Promise<void> {
  await fetch(`${BASE_URL}/pty/sessions/${ptyId}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  })
}
