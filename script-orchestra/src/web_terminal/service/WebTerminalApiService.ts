import { BACKEND_BASE_URL } from '../../basic/Constants'
import type { TerminalWindow } from './Model'

const BASE = `${BACKEND_BASE_URL}/web-terminal`

export async function listWindows(): Promise<TerminalWindow[]> {
  const res = await fetch(`${BASE}/windows`)
  if (!res.ok) throw new Error('Failed to fetch windows')
  const data = await res.json()
  return data.windows ?? []
}

export async function createWindow(title: string, cwd: string): Promise<TerminalWindow> {
  const res = await fetch(`${BASE}/windows`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, cwd }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error || 'Failed to create window')
  }
  return res.json()
}

export async function deleteWindow(windowId: string): Promise<void> {
  await fetch(`${BASE}/windows/${windowId}`, { method: 'DELETE' })
}

export async function getScrollback(windowId: string): Promise<string> {
  const res = await fetch(`${BASE}/windows/${windowId}/scrollback`)
  if (!res.ok) return ''
  const data = await res.json()
  return data.data ?? ''
}

export async function attachPty(windowId: string): Promise<{ already_running: boolean }> {
  const res = await fetch(`${BASE}/windows/${windowId}/pty`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to attach PTY')
  return res.json()
}

export async function detachPty(windowId: string): Promise<void> {
  await fetch(`${BASE}/windows/${windowId}/pty`, { method: 'DELETE' })
}
