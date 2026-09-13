export interface TrackedFile {
  id: number
  path: string
  size_bytes: number
  mtime: number
  atime: number
  last_active: number
  status: 'normal' | 'ignored' | 'archived'
  scan_time: number | null
  note: string
}

export interface ScanStatus {
  running: boolean
  progress: { scanned: number; total: number; path: string }
  last_scan_time: number | null
}

export interface TimestampRule {
  extensions: string[]   // e.g. ['.jpg', '.png'] or ['*']
  source: 'last_used' | 'mtime'
}

export interface FileTrackerSettings {
  scan_paths: string[]
  ignore_patterns: string[]
  stale_thresholds_days: { archive: number; warn: number; danger: number }
  timestamp_rules: TimestampRule[]
}

export interface FilesPage {
  files: TrackedFile[]
  total: number
}

export interface FileStats {
  total: number
  total_size: number
  by_status: Record<string, { count: number; size: number }>
}
