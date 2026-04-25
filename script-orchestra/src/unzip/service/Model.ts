/**
 * Unzip API Response Models
 */

export interface UnzipResult {
  archivePath: string
  status: 'success' | 'failed'
  outputFolder: string | null
  fileCount: number
  passwordUsed: string | null
  passwordsTried: number
  error?: string
}

export interface UnzipResponse {
  results: UnzipResult[]
  summary: {
    total: number
    success: number
    failed: number
  }
}

export interface UnzipRequest {
  files: string[]
}
