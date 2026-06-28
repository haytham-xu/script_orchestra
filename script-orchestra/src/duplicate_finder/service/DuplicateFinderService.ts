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
   * Batch delete files by path (preview or execute)
   * This scans ALL duplicate groups for files under the specified path
   */
  static async batchDeleteByPath(
    deepPath: string,
    previewOnly: boolean = true
  ): Promise<{
    matched_files?: number
    file_list?: string[]
    deleted?: number
    failed?: number
    preview: boolean
  }> {
    const response = await postRequest(`${this.BASE_URL}/batch-delete-by-path`, {}, {
      deep_path: deepPath,
      preview_only: previewOnly
    })
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
   * Add duplicate group to whitelist
   */
  static async addGroupToWhitelist(image_ids: number[]): Promise<{ message: string }> {
    const response = await postRequest(`${this.BASE_URL}/whitelist`, {}, { image_ids })
    return response
  }

  /**
   * Bulk-add multiple groups to whitelist (e.g. entire Phase 3 page).
   * One stats repair at the end — scales with unique images, not group count.
   */
  static async bulkAddGroupsToWhitelist(groups: number[][]): Promise<{
    added_groups: number
    skipped_groups: number
    image_count: number
    stats_repair?: any
  }> {
    const response = await postRequest(`${this.BASE_URL}/whitelist/bulk-add-groups`, {}, { groups })
    return response
  }

  /**
   * Compare Folder — focused pairwise comparison within the given folders.
   * Reuses existing phash from the DB; only computes phash for files not yet
   * in the DB. Compares ALL images in scope (recursive over subdirs) and
   * INSERT OR IGNORE matching pairs into phash_similarities. Never deletes
   * anything; never touches data outside the scope. Triggers Phase 2.5 at
   * the end so Phase 3 immediately reflects new edges.
   */
  static async compareFolders(
    folders: string[],
    thresholdPercent: number = 80
  ): Promise<{
    scan_id: string
    compare: {
      folders: string[]
      fs_files: number
      scope_total: number
      new_phashes_computed: number
      errors: number
      pairs_found: number
      new_similarities_inserted: number
      elapsed: number
    }
    phase25: any
  }> {
    const response = await postRequest(`${this.BASE_URL}/compare-folders`, {}, {
      folders,
      threshold_percent: thresholdPercent
    })
    return response
  }

  /**
   * Get all whitelist groups
   */
  static async getWhitelistGroups(): Promise<{
    whitelist_groups: Array<{
      group_id: number
      added_time: number
      members: Array<{
        image_id: number
        filename: string
        filesize: number
        file_path: string
        phash: string
        resolution: string
      }>
    }>
  }> {
    const response = await getRequest(`${this.BASE_URL}/whitelist`)
    return response
  }

  /**
   * Remove whitelist group
   */
  static async removeWhitelistGroup(group_id: number): Promise<{ message: string }> {
    const response = await fetch(`${BACKEND_BASE_URL}${this.BASE_URL}/whitelist?group_id=${group_id}`, {
      method: 'DELETE'
    })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.error || 'Failed to remove from whitelist')
    }
    return response.json()
  }

  /**
   * Clean up invalid whitelist groups (with < 2 members)
   */
  static async cleanupWhitelistGroups(): Promise<{ removed_count: number; message: string }> {
    const response = await postRequest(`${this.BASE_URL}/whitelist/cleanup`, {}, {})
    return response
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
   * Phase 2.5: Materialize duplicate groups + per-group stats.
   * Manual trigger between Phase 2 and Phase 3.
   */
  static async phase25Materialize(
    thresholdPercent: number = 80,
    sameFolderFilter: boolean = true
  ): Promise<{
    groups_count: number
    members_count: number
    whitelisted_dropped: number
    threshold_percent: number
    same_folder_filter: boolean
    elapsed: number
    stopped: boolean
    scan_id?: string
  }> {
    const response = await postRequest(`${this.BASE_URL}/phase2.5/materialize`, {}, {
      threshold_percent: thresholdPercent,
      same_folder_filter: sameFolderFilter
    })
    return response
  }

  /**
   * Phase 2.5: Stop
   */
  static async phase25Stop(): Promise<{ message: string }> {
    const response = await postRequest(`${this.BASE_URL}/phase2.5/stop`, {}, {})
    return response
  }

  /**
   * Phase 2.5: Read materialization metadata (which threshold, when, etc.)
   */
  static async phase25Meta(): Promise<{ meta: Record<string, string> }> {
    const response = await getRequest<{ meta: Record<string, string> }>(`${this.BASE_URL}/phase2.5/meta`)
    return response
  }

  /**
   * Phase 3: Get duplicates from materialized tables.
   *
   * Returns 409 with `error: 'no_materialization' | 'threshold_mismatch'` if
   * Phase 2.5 hasn't been run (or was run at a different threshold).
   */
  static async phase3GetDuplicates(
    thresholdPercent: number = 80,
    page: number = 1,
    pageSize: number = 100,
    sortBy: string = 'folder_dup_count',
    sortOrder: 'asc' | 'desc' = 'desc'
  ): Promise<{
    groups: ImageInfo[][]
    total_groups: number
    total_duplicates: number
    current_page: number
    page_size: number
    total_pages: number
    elapsed: number
    scan_id?: string
    materialization_meta?: Record<string, string>
    sort_by?: string
    sort_order?: string
    error?: 'no_materialization' | 'threshold_mismatch' | string
    message?: string
    materialized_threshold?: number
    current_threshold?: number
  }> {
    try {
      const response = await postRequest(`${this.BASE_URL}/phase3/get-duplicates`, {}, {
        threshold_percent: thresholdPercent,
        page: page,
        page_size: pageSize,
        sort_by: sortBy,
        sort_order: sortOrder
      })
      return response
    } catch (err: any) {
      // Backend returns 409 with structured `error` field when materialization
      // is missing or its threshold is stale. Unwrap so callers see a normal
      // response and can branch on `result.error`.
      const data = err?.response?.data
      if (err?.response?.status === 409 && data?.error) {
        return data
      }
      throw err
    }
  }

  /**
   * Phase 3: Stop
   */
  static async phase3Stop(): Promise<{ message: string }> {
    const response = await postRequest(`${this.BASE_URL}/phase3/stop`, {}, {})
    return response
  }
}
