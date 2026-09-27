// File Duplicate — TypeScript models

export interface ScanRoot {
  id: number
  name: string
  path: string
  priority: number
}

export interface RootStats {
  root_id: number
  root_path: string
  total: number
  indexed: number
  total_size: number
}

export interface RootDupStats {
  root_id: number
  root_path: string
  dup_file_count: number
  dup_total_size: number
}

export interface GroupStats {
  total_groups: number
  total_duplicate_files: number
  wasted_bytes: number
}

export interface FileMember {
  id: number
  root_id: number
  root_path: string
  file_path: string
  relative_path: string
  filename: string
  filesize: number
  mtime: number
  full_hash: string | null
  hash_status: string
}

export interface DuplicateGroup {
  group_hash: string
  filesize: number
  member_count: number
  members: FileMember[]
  root_ids: number[]
}

export interface GroupsResponse {
  groups: DuplicateGroup[]
  total_groups: number
  page: number
  page_size: number
  total_pages: number
  wasted_bytes: number
}

export interface Stats {
  group_stats: GroupStats
  root_stats: RootStats[]
  root_dup_stats: RootDupStats[]
  counts: Record<string, number>
  total_files: number
}

export interface Settings {
  scan_roots: ScanRoot[]
  exclude_patterns: string[]
  include_extensions: string[]
  trash_path: string
  hash_batch_size: number
  max_workers: number
  page_size: number
}

export interface PhaseProgress {
  op_id: string
  current: number
  total: number
  percentage: number
  message: string
}
