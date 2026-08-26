/**
 * Clipboard Share API Service
 *
 * Handles REST API calls for clipboard sharing
 */

// Dynamically determine the API base URL
// If accessing from Windows, use the Mac's IP (e.g., http://192.168.1.100:50001)
// If accessing from Mac, use localhost
const getBaseURL = () => {
  const protocol = window.location.protocol
  const hostname = window.location.hostname
  // If accessing via IP (like 192.168.1.100), use that IP for backend too
  // Otherwise, use localhost
  const backendHost = hostname === 'localhost' || hostname === '127.0.0.1'
    ? 'localhost'
    : hostname
  return `${protocol}//${backendHost}:50001/clipboard-share/clipboard`
}

const BASE_URL = getBaseURL()

export interface ClipboardItem {
  id: number
  content: string
  source: string
  timestamp: string
  length: number
}

export interface AddContentRequest {
  content: string
  source?: string
}

/**
 * Add new clipboard content
 */
export async function addClipboardContent(data: AddContentRequest): Promise<ClipboardItem> {
  const response = await fetch(`${BASE_URL}/add`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.message || 'Failed to add clipboard content')
  }

  return response.json()
}

/**
 * Get the latest clipboard content
 */
export async function getLatestClipboard(): Promise<ClipboardItem> {
  const response = await fetch(`${BASE_URL}/latest`)

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('No clipboard content available')
    }
    throw new Error('Failed to fetch latest clipboard')
  }

  return response.json()
}

/**
 * Get clipboard history
 */
export async function getClipboardHistory(limit: number = 20): Promise<ClipboardItem[]> {
  const response = await fetch(`${BASE_URL}/history?limit=${limit}`)

  if (!response.ok) {
    throw new Error('Failed to fetch clipboard history')
  }

  return response.json()
}

/**
 * Get specific clipboard item by ID
 */
export async function getClipboardById(id: number): Promise<ClipboardItem> {
  const response = await fetch(`${BASE_URL}/${id}`)

  if (!response.ok) {
    throw new Error(`Clipboard item ${id} not found`)
  }

  return response.json()
}

/**
 * Clear all clipboard history
 */
export async function clearClipboardHistory(): Promise<{ message: string; count: number }> {
  const response = await fetch(`${BASE_URL}/clear`, {
    method: 'DELETE'
  })

  if (!response.ok) {
    throw new Error('Failed to clear clipboard history')
  }

  return response.json()
}
