/**
 * Roadmap Settings API Service
 */
import { getRequest, putRequest } from '@/basic/RequestService'

export interface Settings {
  inProgressTimeoutHours: number
  doneAutoRemoveDays: number | null
}

// Cache for settings (synchronously accessible)
let settingsCache: Settings | null = null

/**
 * Get roadmap settings
 */
export async function getSettings(): Promise<Settings> {
  const data = await getRequest<Settings>('/roadmap/settings')
  settingsCache = data
  return data
}

/**
 * Update roadmap settings
 */
export async function updateSettings(settings: Settings): Promise<Settings> {
  const data = await putRequest<Settings>('/roadmap/settings', {}, settings)
  settingsCache = data
  return data
}

/**
 * Get cached settings (synchronous)
 * Returns null if not loaded yet
 */
export function getCachedSettings(): Settings | null {
  return settingsCache
}

/**
 * Get In Progress timeout in milliseconds (synchronous)
 */
export function getInProgressTimeoutMs(): number {
  return (settingsCache?.inProgressTimeoutHours || 4) * 60 * 60 * 1000
}
