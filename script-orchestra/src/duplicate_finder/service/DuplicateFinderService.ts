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
  display_path?: string
  filename?: string
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
  phash_db_path?: string
  folder_paths?: string[]
  folder_root_paths?: { [key: string]: string }
  exclude_folder_paths?: string[]
  max_cpu_cores?: number
  system_cpu_count?: number
  auto_selection_rules?: {
    auto_mark_numbered_copies?: boolean
    auto_mark_copy_suffix?: boolean
    prefer_folders?: string[]
  }
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
  static async deleteFiles(files: string[], deepPathDelete?: string): Promise<{ success: number; failed: number; errors: string[] }> {
    const requestBody: any = { files }
    if (deepPathDelete) {
      requestBody.deep_path_delete = deepPathDelete
    }
    const response = await postRequest(`${this.BASE_URL}/delete`, {}, requestBody)
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

  /**
   * Add to whitelist
   */
  static async addToWhitelist(filename: string, filesize: number, note?: string, preview_path?: string): Promise<{ message: string }> {
    const response = await postRequest(`${this.BASE_URL}/whitelist`, {}, { filename, filesize, note, preview_path })
    return response
  }

  /**
   * Get whitelist
   */
  static async getWhitelist(): Promise<{ whitelist: Array<{ filename: string; filesize: number; added_time: number; note: string; preview_path?: string }> }> {
    const response = await getRequest(`${this.BASE_URL}/whitelist`)
    return response
  }

  /**
   * Remove from whitelist
   */
  static async removeFromWhitelist(filename: string, filesize: number): Promise<{ message: string }> {
    const response = await fetch(`${BACKEND_BASE_URL}${this.BASE_URL}/whitelist?filename=${encodeURIComponent(filename)}&filesize=${filesize}`, {
      method: 'DELETE'
    })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.error || 'Failed to remove from whitelist')
    }
    return response.json()
  }

  /**
   * Clean up database by removing entries for files that no longer exist
   */
  static async cleanupDatabase(): Promise<{ removed_hashes: number; removed_whitelist: number; message: string }> {
    const response = await postRequest(`${this.BASE_URL}/cleanup`, {}, {})
    return response
  }

  /**
   * Verify which files from duplicate groups still exist on filesystem.
   * Returns detailed information about missing files and cleaned groups.
   */
  static async verifyFiles(duplicateGroups: ImageInfo[][]): Promise<{
    missing_files: string[]
    missing_count: number
    affected_groups: Array<{
      group_index: number
      missing_files: string[]
      remaining_files: string[]
    }>
    cleaned_groups: ImageInfo[][]
    removed_groups_count: number
  }> {
    const response = await postRequest(`${this.BASE_URL}/verify`, {}, { duplicate_groups: duplicateGroups })
    return response
  }

  /**
   * Stop an active scan
   */
  static async stopScan(scanId: string): Promise<{ message: string; scan_id: string }> {
    const response = await postRequest(`${this.BASE_URL}/stop`, {}, { scan_id: scanId })
    return response
  }

  /**
   * Get active scans
   */
  static async getActiveScans(): Promise<{ active_scans: string[]; count: number }> {
    const response = await getRequest(`${this.BASE_URL}/active-scans`)
    return response
  }

  /**
   * Rescan for duplicates using only cached phash data from database
   */
  static async rescanFromCache(threshold: number, verifyFiles: boolean = true): Promise<ScanResult> {
    const response = await postRequest(`${this.BASE_URL}/rescan-from-cache`, {}, { threshold, verify_files: verifyFiles })
    return response
  }

  /**
   * Phase 1: Refresh images - scan filesystem, sync DB, compute phash
   */
  static async phase1Refresh(paths: string[], scanId?: string): Promise<{ added: number; removed: number; skipped: number; errors: any[]; elapsed: number; scan_id: string }> {
    const response = await postRequest(`${this.BASE_URL}/phase1/refresh`, {}, { paths, scan_id: scanId })
    return response
  }

  /**
   * Phase 1: Stop
   */
  static async phase1Stop(): Promise<{ message: string }> {
    const response = await postRequest(`${this.BASE_URL}/phase1/stop`, {}, {})
    return response
  }

  /**
   * Phase 2: Build similarities table
   */
  static async phase2Build(thresholdDistance: number = 12, scanId?: string): Promise<{ processed: number; similarities_found: number; elapsed: number }> {
    const response = await postRequest(`${this.BASE_URL}/phase2/build`, {}, {
      threshold_distance: thresholdDistance,
      scan_id: scanId
    })
    return response
  }

  /**
   * Phase 2: Stop
   */
  static async phase2Stop(): Promise<{ message: string }> {
    const response = await postRequest(`${this.BASE_URL}/phase2/stop`, {}, {})
    return response
  }

  /**
   * Phase 3: Get duplicates from similarities
   */
  static async phase3GetDuplicates(thresholdPercent: number = 90): Promise<{ groups: ImageInfo[][]; total_groups: number; total_duplicates: number; elapsed: number }> {
    const response = await postRequest(`${this.BASE_URL}/phase3/get-duplicates`, {}, { threshold_percent: thresholdPercent })
    return response
  }

  /**
   * Phase 3: Stop
   */
  static async phase3Stop(): Promise<{ message: string }> {
    const response = await postRequest(`${this.BASE_URL}/phase3/stop`, {}, {})
    return response
  }
}
