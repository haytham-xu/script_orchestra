/**
 * Duplicate Finder Service
 */
import { getRequest, postRequest } from '@/basic/RequestService'
import { BACKEND_BASE_URL } from '@/basic/Constants'

export interface ScanRequest {
  paths: string[]
  threshold?: number
  scan_id?: string
}

export interface ImageInfo {
  file_path: string
  phash: string
  resolution: string
  filesize: number
}

export interface ScanResult {
  scan_id: string
  duplicate_groups: ImageInfo[][]
  total_files: number
  duplicate_count: number
}

export interface Settings {
  similarity_threshold: number
  delete_target_path: string
}

export class DuplicateFinderService {
  private static BASE_URL = '/duplicate-finder'

  /**
   * Scan directories for duplicates
   */
  static async scan(request: ScanRequest): Promise<ScanResult> {
    const response = await postRequest(`${this.BASE_URL}/scan`, {}, request)
    return response
  }

  /**
   * Delete (move) files to delete target
   */
  static async deleteFiles(files: string[]): Promise<{ success: number; failed: number; errors: string[] }> {
    const response = await postRequest(`${this.BASE_URL}/delete`, {}, { files })
    return response
  }

  /**
   * Get settings
   */
  static async getSettings(): Promise<Settings> {
    const response = await getRequest<Settings>(`${this.BASE_URL}/settings`)
    return response
  }

  /**
   * Update settings
   */
  static async updateSettings(settings: Partial<Settings>): Promise<{ settings: Settings }> {
    const response = await postRequest(`${this.BASE_URL}/settings`, {}, settings)
    return response
  }

  /**
   * Get image URL for preview
   */
  static getImageUrl(filePath: string): string {
    return `${BACKEND_BASE_URL}${this.BASE_URL}/image?path=${encodeURIComponent(filePath)}`
  }

  /**
   * Open folder in system file manager
   */
  static async openFolder(folderPath: string): Promise<{ success: boolean; message?: string; error?: string }> {
    const response = await postRequest(`${this.BASE_URL}/open-folder`, {}, { folder_path: folderPath })
    return response
  }
}
