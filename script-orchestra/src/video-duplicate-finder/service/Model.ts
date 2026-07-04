/**
 * Video Duplicate Finder — TypeScript Model definitions.
 *
 * DECOUPLED: this file must not import anything from `@/duplicate_finder/*`.
 * Types are copied and adapted where they overlap with the image-side tool.
 *
 * Refer to backend documentation for canonical shapes:
 *   - buffer/02_api_reference.md  (image version, base contracts)
 *   - buffer/04_image_to_video_mapping.md  (video-specific fields)
 *
 * Naming: types are prefixed with `Video` when they meaningfully differ from
 * the image side (e.g. VideoInfo vs ImageInfo). Shared shapes keep neutral
 * names (Settings, PhaseProgress, etc.).
 */


// ============================================================================
// Core video record — everything the frontend needs about a single video
// ============================================================================

/**
 * One video's rendered representation on the Phase 3 list page.
 *
 * Backend fields come from `video_hashes` (S1.7) plus computed extras added
 * at read time in `phase3_get_duplicates` (S5.1):
 *   folder_dup, folder_total       — per-directory duplicate stats
 *   display_path                   — project-root-relative dir
 *   auto_delete_suggestion         — server-side auto-selection result (D-14)
 */
export interface VideoInfo {
  // Primary identity + storage
  id:             number
  filename:       string
  filesize:       number
  file_path:      string         // always abspath (D-19)
  video_hash:     string         // N-frame '|'-joined signature

  // Media metadata (cv2 probe result — see frame_extractor.probe_metadata)
  duration?:      number | null  // seconds
  width?:         number | null
  height?:        number | null
  fps?:           number | null
  bitrate?:       number | null  // may be null; cv2 doesn't expose (Q-06 pending)
  vcodec?:        string | null  // e.g. 'h264', 'hevc'
  acodec?:        string | null  // may be null; cv2 doesn't expose
  container?:     string | null  // e.g. 'mp4', 'mkv' (guessed from extension)

  // Cache pointers
  thumbnail_path?: string | null
  mtime?:         number | null

  // Phase-3-computed fields (present only in Phase 3 responses)
  folder_dup?:              number  // # of duplicate files under this member's folder
  folder_total?:            number  // # of total files under this member's folder
  display_path?:            string  // '/' or 'sub/dir' — never a full abs path
  auto_delete_suggestion?:  boolean // server-side auto-select verdict
}

/**
 * A single materialized duplicate group.
 * Members within a group are pre-sorted by the backend:
 *   folder_dup DESC, folder_total ASC, filename ASC.
 * So `images[0]` is always the group's "anchor" — the file that shows first.
 */
export type VideoGroup = VideoInfo[]


// ============================================================================
// Request / Response shapes for each endpoint
// ============================================================================

// ---- /phase1/refresh ----

export interface Phase1RefreshRequest {
  paths:    string[]
  scan_id?: string
}

export interface Phase1RefreshResponse {
  added:    number
  removed:  number
  skipped:  number
  errors:   Phase1WorkerError[]
  elapsed:  number
  stopped:  boolean
  scan_id:  string
}

export interface Phase1WorkerError {
  file_path:  string
  error_type: string    // one of FRAME_EXTRACT_ERROR_TYPES
  error_msg:  string
}

// ---- /phase2/build ----

export interface Phase2BuildRequest {
  threshold_distance?: number  // 0..VIDEO_HASH_BITS (512); default 102
  threshold_percent?:  number  // alternative: server converts to distance
  scan_id?:            string
}

export interface Phase2BuildResponse {
  processed:            number
  similarities_found:   number
  elapsed:              number
  stopped:              boolean
  scan_id:              string
  threshold_distance:   number
}

// ---- /phase2.5/materialize ----

export interface Phase25MaterializeRequest {
  threshold_percent?:   number   // 80 | 90 | 95 | 100
  same_folder_filter?:  boolean  // default true
  scan_id?:             string
}

export interface Phase25MaterializeResponse {
  groups_count:         number
  members_count:        number
  whitelisted_dropped:  number
  threshold_percent:    number
  same_folder_filter:   boolean
  elapsed:              number
  stopped:              boolean
  scan_id:              string
}

/** Result of GET /phase2.5/meta — key/value strings from video_duplicate_finder_meta. */
export interface Phase25MetaResponse {
  meta: Record<string, string>
  // Common keys (all values are strings on the wire):
  //   materialized_threshold, materialized_at,
  //   materialized_same_folder_filter, materialized_group_count,
  //   last_incremental_update
}

// ---- /phase3/get-duplicates ----

export type Phase3SortBy =
  | 'folder_dup_count'
  | 'representative_file_path'
  | 'member_count'
  | 'max_filesize' | 'min_filesize'
  | 'max_duration' | 'min_duration'   // video-specific
  | 'max_bitrate'  | 'min_bitrate'    // video-specific
  | 'max_mtime'    | 'min_mtime'

export interface Phase3GetDuplicatesRequest {
  threshold_percent?: number
  page?:              number   // 1-indexed; 0 = return all
  page_size?:         number
  sort_by?:           Phase3SortBy
  sort_order?:        'asc' | 'desc'
  scan_id?:           string
}

export interface Phase3GetDuplicatesResponse {
  groups:               VideoGroup[]
  total_groups:         number
  total_duplicates:     number
  total_files_in_db:    number
  current_page:         number
  page_size:            number
  total_pages:          number
  elapsed:              number
  stopped:              boolean
  materialization_meta: Record<string, string>
  sort_by:              string
  sort_order:           string
  scan_id?:             string

  // Only present on strict-mode errors (HTTP 409):
  error?:                 'no_materialization' | 'threshold_mismatch' | string
  message?:               string
  materialized_threshold?: number
  current_threshold?:      number
}

// ---- /delete ----

export interface DeleteRequest {
  files: string[]
}

export interface DeleteResponse {
  success:            number
  failed:             number
  errors:             string[]
  companions_moved:   number
  stats_repair:       StatsRepairSummary | null
}

// ---- /whitelist ----

export interface WhitelistMember {
  video_id:  number
  filename:  string
  filesize:  number
  file_path: string
  duration?: number | null
  width?:    number | null
  height?:   number | null
}

export interface WhitelistGroup {
  group_id:   number
  added_time: number
  members:    WhitelistMember[]
}

export interface WhitelistIndividual {
  video_id:   number
  added_time: number
  note?:      string | null
  filename:   string
  filesize:   number
  file_path:  string
  duration?:  number | null
  width?:     number | null
  height?:    number | null
}

export interface WhitelistResponse {
  whitelist_groups: WhitelistGroup[]
  whitelist:        WhitelistIndividual[]
}

export interface WhitelistAddRequest {
  video_ids: number[]   // must be length ≥ 2
}

export interface WhitelistAddResponse {
  message:      string
  stats_repair: StatsRepairSummary
}

export interface WhitelistCleanupResponse {
  removed_count: number
  message:       string
}

// ---- /verify ----

export interface VerifyRequest {
  duplicate_groups: VideoGroup[]
}

export interface AffectedGroupRecord {
  group_index:      number
  missing_files:    string[]
  remaining_files:  string[]
}

export interface VerifyResponse {
  missing_files:        string[]
  missing_count:        number
  affected_groups:      AffectedGroupRecord[]
  cleaned_groups:       VideoGroup[]
  removed_groups_count: number
}

// ---- /cleanup ----

export interface CleanupResponse {
  removed_hashes:    number
  removed_whitelist: number   // always 0 (CASCADE handles it)
  existing_files:    number
  message:           string
}

// ---- /metadata ----

export interface VideoMetadata {
  duration:    number
  width:       number
  height:      number
  fps:         number
  frame_count: number
  vcodec:      string
  container:   string
}

// ---- /settings ----

export interface AutoSelectionRules {
  auto_mark_lower_resolution?:  boolean
  auto_mark_lower_bitrate?:     boolean
  auto_mark_smaller_filesize?:  boolean
  auto_mark_older_codec?:       boolean
  auto_mark_numbered_copies?:   boolean
  prefer_folders?:              string[]
}

export interface Phase1Settings {
  worker_handler_size:      number
  db_commit_batch_size:     number
  progress_update_interval: number
  ipc_chunk_size:           number
  scan_delay:               number
  compute_delay:            number
}

export interface Phase2Settings {
  worker_handler_size:      number
  db_commit_batch_size:     number
  progress_update_interval: number
  ipc_chunk_size:           number
  compare_delay:            number
}

export interface Settings {
  delete_target_path:            string
  similarity_threshold:          number
  folder_paths:                  string[]
  folder_root_paths?:            { [key: string]: string }
  exclude_folder_paths?:         string[]

  auto_selection_rules?:         AutoSelectionRules
  companion_extensions?:         string[]

  video_db_path?:                string | null
  thumbnail_cache_dir?:          string | null
  ffmpeg_path?:                  string | null

  max_cpu_cores?:                number
  system_cpu_count?:             number   // injected by GET /settings; ignored on POST

  n_frames?:                     number
  frame_extract_timeout_seconds?: number
  thumbnail_position_percent?:   number

  page_size?:                    number

  phase1?: Phase1Settings
  phase2?: Phase2Settings
}


// ---- /compare-folders + /compare-folders-all ----

export interface CompareFoldersResponse {
  scan_id: string
  compare: {
    folders:                     string[]
    fs_files:                    number
    scope_total:                 number
    new_phashes_computed:        number
    errors:                      number
    pairs_found:                 number
    new_similarities_inserted:   number
    elapsed:                     number
  }
  phase25: Phase25MaterializeResponse
}

export interface CompareFoldersAllResponse {
  scan_id:                        string
  clusters_count:                 number
  clusters_skipped:                number
  folders_in_skipped_clusters:     number
  folders_count:                   number
  largest_cluster_sizes:           number[]
  compare?: {
    scope_total:                   number
    new_phashes_computed:          number
    errors:                        number
    pairs_found:                   number
    new_similarities_inserted:     number
    elapsed:                       number
  }
  phase25?: Phase25MaterializeResponse
  message?: string
}

// ---- /replace + /replace-batch ----

export interface ReplaceRequest {
  selected_file_path: string
  anchor_file_path:   string
  group_file_paths:   string[]   // must have length 2
}

export interface ReplaceResponse {
  deleted_count:      number
  renamed:            boolean
  new_selected_path:  string
  errors:             string[]
  stats_repair:       StatsRepairSummary | null
}

export interface ReplaceBatchRequest {
  operations: ReplaceRequest[]
}

export interface ReplaceBatchResponse {
  operations_count: number
  deleted_count:    number
  renamed_count:    number
  errors_per_op:    Array<{ op_index: number; errors: string[] }>
  stats_repair:     StatsRepairSummary | null
}

// ---- /batch-delete-by-path ----

export interface BatchDeleteByPathRequest {
  deep_path:     string
  preview_only?: boolean
}

export interface BatchDeleteByPathResponse {
  matched_files?:   number
  file_list?:       string[]
  preview:          boolean
  deleted?:         number
  failed?:          number
  companions_moved?: number
  pruned_dirs?:     number
  stats_repair?:    StatsRepairSummary | null
}

// ---- /whitelist/preview-by-path + /whitelist/bulk-add-groups ----

export interface WhitelistPreviewByPathResponse {
  deep_path:      string
  matched_groups: number
  matched_files:  number
  groups:         VideoGroup[]
}

export interface WhitelistBulkAddGroupsRequest {
  groups: number[][]
}

export interface WhitelistBulkAddGroupsResponse {
  added_groups:   number
  skipped_groups: number
  video_count:    number
  stats_repair:   StatsRepairSummary
}


// ============================================================================
// Stats repair summary — returned by mutation endpoints
// ============================================================================

export interface StatsRepairSummary {
  video_ids_processed:     number
  affected_groups:         number
  orphan_groups_deleted:   number
  survivor_groups_updated: number
  folders_refreshed:       number
  elapsed:                 number
}


// ============================================================================
// WebSocket event payloads (broadcast on `vscan:{scan_id}:*` rooms)
// ============================================================================

export interface WSProgressPayload {
  scan_id:      string
  current:      number
  total:        number
  percentage:   number
  message:      string
  // Optional extra data (Phase 2.5 / rescan may pack incremental groups)
  groups_batch?: VideoGroup[]
}

export interface WSCompletePayload {
  scan_id: string
  result:  {
    scan_id:              string
    // Phase 1
    added?:               number
    removed?:             number
    skipped?:             number
    // Phase 2
    processed?:           number
    similarities_found?:  number
    // Phase 2.5
    groups_count?:        number
    members_count?:       number
    whitelisted_dropped?: number
    // Common
    error_count?:         number
    elapsed?:             number
    stopped?:             boolean
  }
}

export interface WSErrorPayload {
  scan_id: string
  error:   string
}


// ============================================================================
// UI-local state shapes (not backend-derived)
// ============================================================================

/**
 * Per-phase progress state used by the composable to render the progress bar.
 * `phase = 0` means "idle" — nothing displayed.
 */
export interface PhaseProgress {
  phase:      0 | 1 | 2 | 25 | 3
  message:    string
  details:    string
  current:    number
  total:      number
  percentage: number
}

export interface Phase1Summary {
  added:    number
  removed:  number
  skipped:  number
  elapsed:  string   // '.toFixed(1)' formatted
}

export interface Phase2Summary {
  processed:          number
  similarities_found: number
  elapsed:            string
}

export interface Phase25Summary {
  groups_count:  number
  members_count: number
  elapsed:       string
}
