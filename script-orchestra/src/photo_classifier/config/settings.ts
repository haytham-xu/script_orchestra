/**
 * Settings management for Photo Classifier
 */

import { getSettings, updateSettings } from '../service/SettingsService'

const STORAGE_KEY = 'photo_classifier_root_path'

// Cache for root path
let cachedRootPath: string | null = null

export function getRootPath(): string {
  // Return cached value if available
  if (cachedRootPath !== null) {
    return cachedRootPath
  }

  // Fallback to localStorage (for backward compatibility)
  return localStorage.getItem(STORAGE_KEY) || ''
}

export async function loadRootPathFromBackend(): Promise<string> {
  try {
    const settings = await getSettings()
    cachedRootPath = settings.rootPath || ''

    // Also update localStorage for backward compatibility
    if (cachedRootPath) {
      localStorage.setItem(STORAGE_KEY, cachedRootPath)
    }

    return cachedRootPath
  } catch (error) {
    console.error('Failed to load settings from backend:', error)

    // Fallback to localStorage
    cachedRootPath = localStorage.getItem(STORAGE_KEY) || ''
    return cachedRootPath
  }
}

export async function setRootPath(path: string): Promise<void> {
  try {
    // Save to backend
    const settings = await updateSettings({ rootPath: path })
    cachedRootPath = settings.rootPath

    // Also save to localStorage for backward compatibility
    localStorage.setItem(STORAGE_KEY, path)
  } catch (error) {
    console.error('Failed to save settings to backend:', error)

    // Fallback to localStorage only
    localStorage.setItem(STORAGE_KEY, path)
    cachedRootPath = path

    throw error
  }
}

export function hasRootPath(): boolean {
  return !!getRootPath()
}
