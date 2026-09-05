export enum BrowserTaskStatus {
  Todo = 'TODO',
  InProgress = 'IN_PROGRESS',
  Failed = 'FAILED',
  Completed = 'COMPLETED',
}

export interface BrowserTask {
  id: number
  code: string
  created_at: string
  updated_at: string
  status: BrowserTaskStatus
  retry_times: number
  file_name: string
  size: number
  download_link: string
}

export interface SiteRule {
  coverDomains: string[]
  overviewUriFormat: string
  downloadUriFormat: string
  downloadLinkRegex: string
}

export interface DownloadSSMHConfig {
  sourceDomains: string[]
  downloadDomains: string[]
  downloadPath: string
  linkLabel: string
}

export interface DownloadJMConfig {
  sourceDomain: string
  downloadPath: string
}

export interface TabArchiveSettings {
  safeExcludeDomains: string[]
  safeExcludeKeywords: string[]
  embedModel: string
  semanticTopK: number
  heatThresholds: {
    high: number
    medium: number
    low: number
  }
  healthCheckTimeoutSec: number
}

export interface BrowserAgentSettings {
  downloadDir: string
  maxRetries: number
  pollIntervalSec: number
  siteRules: SiteRule[]
  downloadSSMH: DownloadSSMHConfig
  downloadJM: DownloadJMConfig
  tabArchive: TabArchiveSettings
}

// Live progress event pushed over WebSocket.
export interface ProgressEvent {
  taskId: number
  status: BrowserTaskStatus
  progress: number
  retryTimes?: number
}

export type HeatLevel = 'high' | 'medium' | 'low' | 'cold'

export interface TabArchiveLiveCard {
  tab_id: number
  title: string
  favicon_url: string
  pinned: boolean
  active: boolean
  window_id: number
  url: string
  domain: string
  normalized_url: string | null
  record_id: number | null
  comment: string
  labels: string[]
  eternal: boolean
  heat_score: number
  heat_level: HeatLevel
}

export interface TabArchiveRecord {
  id: number
  normalized_url: string
  url: string
  title: string
  domain: string
  favicon_url: string
  comment: string
  eternal: boolean
  created_at: string
  first_archived_at: string | null
  last_archived_at: string | null
  last_opened_at: string | null
  last_seen_at: string | null
  open_count: number
  archive_count: number
  health_status: string
  last_checked_at: string | null
  last_http_status: number | null
  final_url: string
  labels: string[]
  is_live: boolean
  heat_score: number
  heat_level: HeatLevel
}

export interface TabArchiveSnapshot {
  extension_available: boolean
  live_error: string | null
  live: TabArchiveLiveCard[]
  archive: TabArchiveRecord[]
  counts: {
    live: number
    archive: number
    total_archived: number
  }
  search: {
    semantic_requested: boolean
    semantic_available: boolean
    semantic_error: string
    semantic_model: string
    semantic_top_k: number
  }
}

export type TabArchiveSortBy = 'relevance' | 'heat' | 'last_opened' | 'last_archived' | 'open_count' | 'title'
export type TabArchiveSortOrder = 'asc' | 'desc'

export interface TabArchiveSafePreviewRow {
  tab_id: number
  title: string
  favicon_url: string
  pinned: boolean
  domain: string
  url: string
  reason: string | null
}

export interface TabArchiveSafePreview {
  include_pinned: boolean
  requested: number
  candidates: TabArchiveSafePreviewRow[]
  excluded: TabArchiveSafePreviewRow[]
  candidate_count: number
  excluded_count: number
}

export interface TabArchiveArchiveResult {
  mode: string
  batch_id: number | null
  requested: number
  persisted_count: number
  closed_count: number
  failed_count: number
  close_error: string
  closed_record_ids: number[]
  failures: Array<{ tab_id: number; title: string; ok: boolean; reason: string }>
  excluded?: Array<{ tab_id: number; title: string; reason: string }>
  excluded_count?: number
}

export interface TabArchiveRestoreResultRow {
  record_id: number
  ok: boolean
  status: 'opened' | 'already_live' | 'failed'
  tab_id: number | null
  error: string
  title?: string
  url?: string
}

export interface TabArchiveRestoreResult {
  requested: number
  destination: 'new_window' | 'current_window'
  opened_count: number
  already_live_count: number
  failed_count: number
  results: TabArchiveRestoreResultRow[]
}

export interface TabArchiveLabel {
  id: number
  name: string
  created_at: string
}

export interface TabArchiveHealthCheckResult {
  checked: number
  healthy: number
  unavailable: number
  unknown: number
  timeout_sec: number
  records: Array<TabArchiveRecord & { health_error?: string }>
}

export type TabArchiveHealthJobStatus =
  | 'queued'
  | 'running'
  | 'cancelling'
  | 'completed'
  | 'cancelled'
  | 'failed'
  | 'unknown'

export interface TabArchiveHealthCheckJob {
  job_id: string
  status: TabArchiveHealthJobStatus
  created_at: string
  started_at: string | null
  finished_at: string | null
  updated_at: string
  total: number
  processed: number
  healthy: number
  unavailable: number
  unknown: number
  batch_size: number
  cancel_requested: boolean
  last_error: string
  progress_percent: number
}

export interface TabArchiveReplaceUrlPreviewRow {
  id: number
  title: string
  old_url: string
  new_url: string
}

export interface TabArchiveReplaceUrlResult {
  preview?: TabArchiveReplaceUrlPreviewRow[]
  count?: number
  updated?: number
  error?: string
}
