/**
 * Video Duplicate Finder — HTTP Client.
 *
 * DECOUPLED: no imports from `@/duplicate_finder/*`. All types come from
 * the local `Model.ts`; RequestService and Constants are shared project
 * infrastructure (not tool-specific).
 *
 * Endpoint contract source-of-truth:
 *   backend/video_duplicate_finder/video_duplicate_finder_controller.py
 *
 * URL scheme:
 *   All methods hit `/video-duplicate-finder/<endpoint>`.
 *   `getMediaUrl` returns a fully-qualified URL because <img src=...> and
 *   <video src=...> need absolute URLs (BACKEND_BASE_URL).
 */
import { BACKEND_BASE_URL } from '@/basic/Constants'
import { getRequest, postRequest } from '@/basic/RequestService'

import type {
  BatchDeleteByPathResponse,
  CleanupResponse,
  CompareFoldersAllResponse,
  CompareFoldersResponse,
  DeleteResponse,
  Phase1RefreshResponse,
  Phase25MaterializeResponse,
  Phase25MetaResponse,
  Phase2BuildResponse,
  Phase3GetDuplicatesResponse,
  Phase3SortBy,
  ReplaceBatchResponse,
  ReplaceRequest,
  ReplaceResponse,
  Settings,
  StatsRepairSummary,
  VerifyResponse,
  VideoGroup,
  VideoMetadata,
  WhitelistAddResponse,
  WhitelistBulkAddGroupsResponse,
  WhitelistCleanupResponse,
  WhitelistPreviewByPathResponse,
  WhitelistResponse,
} from './Model'


export class VideoDuplicateFinderService {
  private static BASE_URL = '/video-duplicate-finder'

  // =========================================================================
  // Health / diagnostics
  // =========================================================================

  static async health(): Promise<{ ok: boolean; tool: string; version: string }> {
    return await getRequest(`${this.BASE_URL}/health`)
  }


  // =========================================================================
  // Phase 1: refresh
  // =========================================================================

  static async phase1Refresh(paths: string[], scanId?: string): Promise<Phase1RefreshResponse> {
    return await postRequest(`${this.BASE_URL}/phase1/refresh`, {}, {
      paths,
      scan_id: scanId,
    })
  }

  static async phase1Stop(): Promise<{ message: string }> {
    return await postRequest(`${this.BASE_URL}/phase1/stop`, {}, {})
  }


  // =========================================================================
  // Phase 2: build similarities
  // =========================================================================

  /**
   * @param thresholdDistance  Explicit hamming distance ceiling (0..512).
   *                           Prefer this if you know exactly what edges you want.
   * @param thresholdPercent   UI-style percent (80/90/95/100). Server converts to
   *                           distance = VIDEO_HASH_BITS * (100 - percent) / 100
   *                           BUT clamps to at least 20% coverage so tighter
   *                           UI thresholds can still be filtered by Phase 2.5
   *                           without recomputing.
   *
   * At most ONE of the two should be provided. If both are, the server prefers
   * `threshold_distance`.
   */
  static async phase2Build(
    thresholdDistance?: number,
    thresholdPercent?: number,
    scanId?: string,
  ): Promise<Phase2BuildResponse> {
    const body: Record<string, unknown> = {}
    if (thresholdDistance !== undefined) body.threshold_distance = thresholdDistance
    if (thresholdPercent !== undefined)  body.threshold_percent  = thresholdPercent
    if (scanId !== undefined)             body.scan_id             = scanId
    return await postRequest(`${this.BASE_URL}/phase2/build`, {}, body)
  }

  static async phase2Stop(): Promise<{ message: string }> {
    return await postRequest(`${this.BASE_URL}/phase2/stop`, {}, {})
  }


  // =========================================================================
  // Phase 2.5: materialize groups
  // =========================================================================

  static async phase25Materialize(
    thresholdPercent: number = 80,
    sameFolderFilter: boolean = true,
    scanId?: string,
  ): Promise<Phase25MaterializeResponse> {
    return await postRequest(`${this.BASE_URL}/phase2.5/materialize`, {}, {
      threshold_percent:   thresholdPercent,
      same_folder_filter:  sameFolderFilter,
      scan_id:             scanId,
    })
  }

  static async phase25Stop(): Promise<{ message: string }> {
    return await postRequest(`${this.BASE_URL}/phase2.5/stop`, {}, {})
  }

  static async phase25Meta(): Promise<Phase25MetaResponse> {
    return await getRequest(`${this.BASE_URL}/phase2.5/meta`)
  }


  // =========================================================================
  // Phase 3: get duplicates (paged)
  // =========================================================================

  /**
   * Returns `{ error: 'no_materialization' | 'threshold_mismatch', ... }`
   * WITHOUT throwing when the backend responds with HTTP 409 — the caller
   * inspects `result.error` and prompts the user to re-materialize.
   *
   * Any other HTTP failure (500, network) still propagates as an exception.
   */
  static async phase3GetDuplicates(
    thresholdPercent: number = 80,
    page: number = 1,
    pageSize: number = 100,
    sortBy: Phase3SortBy = 'folder_dup_count',
    sortOrder: 'asc' | 'desc' = 'desc',
  ): Promise<Phase3GetDuplicatesResponse> {
    try {
      return await postRequest(`${this.BASE_URL}/phase3/get-duplicates`, {}, {
        threshold_percent: thresholdPercent,
        page,
        page_size:  pageSize,
        sort_by:    sortBy,
        sort_order: sortOrder,
      })
    } catch (err) {
      // Unwrap axios-style errors when the server returned an error marker
      const anyErr = err as { response?: { status?: number; data?: Phase3GetDuplicatesResponse } }
      const data = anyErr?.response?.data
      if (anyErr?.response?.status === 409 && data?.error) {
        return data
      }
      throw err
    }
  }

  static async phase3Stop(): Promise<{ message: string }> {
    return await postRequest(`${this.BASE_URL}/phase3/stop`, {}, {})
  }


  // =========================================================================
  // Delete
  // =========================================================================

  /**
   * Move the given video files (+ their companion sidecar files) to
   * `delete_target_path`. Server clears DB rows via CASCADE and repairs
   * `video_group_stats` incrementally.
   */
  static async deleteFiles(files: string[]): Promise<DeleteResponse> {
    return await postRequest(`${this.BASE_URL}/delete`, {}, { files })
  }


  // =========================================================================
  // Whitelist
  // =========================================================================

  static async getWhitelist(): Promise<WhitelistResponse> {
    return await getRequest(`${this.BASE_URL}/whitelist`)
  }

  /**
   * Add a duplicate group to the whitelist. The group must have ≥ 2 members.
   * Server does stats repair automatically.
   */
  static async addGroupToWhitelist(videoIds: number[]): Promise<WhitelistAddResponse> {
    return await postRequest(`${this.BASE_URL}/whitelist`, {}, { video_ids: videoIds })
  }

  /** Remove a whitelist group by its id. */
  static async removeWhitelistGroup(groupId: number): Promise<{ message: string }> {
    // Query-string DELETE isn't well-supported by RequestService's post helpers,
    // so we use fetch directly (same pattern as image version).
    const response = await fetch(
      `${BACKEND_BASE_URL}${this.BASE_URL}/whitelist?group_id=${groupId}`,
      { method: 'DELETE' },
    )
    if (!response.ok) {
      const err = await response.json().catch(() => ({ error: 'Unknown error' }))
      throw new Error(err.error || 'Failed to remove whitelist group')
    }
    return await response.json()
  }

  static async cleanupWhitelistGroups(): Promise<WhitelistCleanupResponse> {
    return await postRequest(`${this.BASE_URL}/whitelist/cleanup`, {}, {})
  }

  /** Preview which materialized duplicate groups live under a folder (recursive). */
  static async previewWhitelistByPath(deepPath: string): Promise<WhitelistPreviewByPathResponse> {
    return await postRequest(`${this.BASE_URL}/whitelist/preview-by-path`, {}, {
      deep_path: deepPath,
    })
  }

  /** Bulk-add multiple groups to whitelist in one call with a single stats repair. */
  static async bulkAddGroupsToWhitelist(groups: number[][]): Promise<WhitelistBulkAddGroupsResponse> {
    return await postRequest(`${this.BASE_URL}/whitelist/bulk-add-groups`, {}, { groups })
  }


  // =========================================================================
  // Compare folders (S6)
  // =========================================================================

  /**
   * Focused pairwise comparison of just the given folders.
   * Reuses DB hashes where available, computes only for new files.
   * Never deletes anything. Triggers Phase 2.5 at the end so Phase 3 reflects new edges.
   */
  static async compareFolders(
    folders: string[],
    thresholdPercent: number = 80,
  ): Promise<CompareFoldersResponse> {
    return await postRequest(`${this.BASE_URL}/compare-folders`, {}, {
      folders,
      threshold_percent: thresholdPercent,
    })
  }

  /**
   * Global cluster-based compare — folders are grouped into connected
   * components (edges = "share a duplicate group"), and Compare Folders
   * runs once per cluster. Clusters ≥ 4 folders are skipped (noise).
   */
  static async compareAllFolders(
    thresholdPercent: number = 80,
  ): Promise<CompareFoldersAllResponse> {
    return await postRequest(`${this.BASE_URL}/compare-folders-all`, {}, {
      threshold_percent: thresholdPercent,
    })
  }


  // =========================================================================
  // Replace (S7.2) — for size-2 groups only
  // =========================================================================

  /**
   * Replace op: keep the selected video, move the other to delete_target,
   * and move the selected video into the anchor's directory with the
   * anchor's basename + selected's own extension. Companions travel + rename.
   */
  static async replaceInGroup(
    selectedFilePath: string,
    anchorFilePath:   string,
    groupFilePaths:   string[],
  ): Promise<ReplaceResponse> {
    return await postRequest(`${this.BASE_URL}/replace`, {}, {
      selected_file_path: selectedFilePath,
      anchor_file_path:   anchorFilePath,
      group_file_paths:   groupFilePaths,
    })
  }

  /** Batch replace — many /replace operations, single stats repair. */
  static async replaceBatch(operations: ReplaceRequest[]): Promise<ReplaceBatchResponse> {
    return await postRequest(`${this.BASE_URL}/replace-batch`, {}, { operations })
  }


  // =========================================================================
  // Batch delete by path (S7.3)
  // =========================================================================

  /**
   * Move all duplicate files under `deepPath` to delete_target.
   *
   * preview_only=true (default): return matched_files count + file_list
   * preview_only=false:          actually delete + clean DB + repair stats
   */
  static async batchDeleteByPath(
    deepPath: string,
    previewOnly: boolean = true,
  ): Promise<BatchDeleteByPathResponse> {
    return await postRequest(`${this.BASE_URL}/batch-delete-by-path`, {}, {
      deep_path:     deepPath,
      preview_only:  previewOnly,
    })
  }


  // =========================================================================
  // Maintenance
  // =========================================================================

  /**
   * Remove video_hashes rows for files that no longer exist on disk. Scans
   * `folder_paths` from settings to enumerate current files.
   * CASCADE handles similarities + group memberships + whitelist entries.
   */
  static async cleanupDatabase(): Promise<CleanupResponse> {
    return await postRequest(`${this.BASE_URL}/cleanup`, {}, {})
  }

  /**
   * Given a snapshot of duplicate groups from a prior Phase 3 read, tell the
   * server to check which files are still on disk. Returns cleaned_groups
   * with missing entries removed (groups falling below 2 members are dropped).
   */
  static async verifyFiles(groups: VideoGroup[]): Promise<VerifyResponse> {
    return await postRequest(`${this.BASE_URL}/verify`, {}, { duplicate_groups: groups })
  }

  /** Open the given folder in the OS file manager. */
  static async openFolder(folderPath: string): Promise<{ success: boolean; message?: string; error?: string }> {
    return await postRequest(`${this.BASE_URL}/open-folder`, {}, { folder_path: folderPath })
  }


  // =========================================================================
  // Settings
  // =========================================================================

  static async getSettings(): Promise<Settings> {
    return await getRequest(`${this.BASE_URL}/settings`)
  }

  /**
   * Shallow-merge update.
   *
   * WARNING: Nested objects (e.g. `phase1`, `auto_selection_rules`) are
   * REPLACED WHOLESALE. To update one nested field, GET the current settings
   * first, mutate the nested object, and POST the whole thing back.
   */
  static async updateSettings(patch: Partial<Settings>): Promise<{ message: string; settings: Settings }> {
    return await postRequest(`${this.BASE_URL}/settings`, {}, patch)
  }


  // =========================================================================
  // Media URLs (return fully-qualified URLs for direct browser embedding)
  // =========================================================================

  /**
   * Thumbnail URL for the given video.
   *
   * @param filePath  absolute video path
   * @param tSeconds  optional timestamp — if provided, backend extracts a
   *                  fresh frame on-demand instead of returning the cached
   *                  thumbnail. Useful for scrubbing.
   */
  static getThumbnailUrl(filePath: string, tSeconds?: number): string {
    const encoded = encodeURIComponent(filePath)
    const t = tSeconds !== undefined ? `&t=${encodeURIComponent(String(tSeconds))}` : ''
    return `${BACKEND_BASE_URL}${this.BASE_URL}/thumbnail?path=${encoded}${t}`
  }

  /**
   * Preview URL — served with Range-request support so `<video src=...>` can
   * seek without downloading the full file.
   */
  static getPreviewUrl(filePath: string): string {
    return `${BACKEND_BASE_URL}${this.BASE_URL}/preview?path=${encodeURIComponent(filePath)}`
  }

  /** Fetch cv2-probed metadata (duration, resolution, fps, codec, container). */
  static async getMetadata(filePath: string): Promise<VideoMetadata> {
    return await getRequest(
      `${this.BASE_URL}/metadata?path=${encodeURIComponent(filePath)}`,
    )
  }
}


// Re-export the singleton-like class so callers can do:
//   import { VideoDuplicateFinderService } from '.../VideoDuplicateFinderService'
export default VideoDuplicateFinderService
export type { StatsRepairSummary }   // convenience re-export for consumers
