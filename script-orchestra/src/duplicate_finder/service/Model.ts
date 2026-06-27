export interface DuplicateImage {
  file_path: string
  phash: string
  resolution: string
  filesize: number
  display_path?: string  // Directory path without root prefix
  filename?: string      // Just the filename
}

export interface DuplicateGroup {
  images: DuplicateImage[]
  selectedAction: 'keep' | 'delete'  // Default action for each image
}

export interface ScanRequest {
  paths: string[]
  threshold?: number
}

export interface ScanResponse {
  duplicate_groups: DuplicateImage[][]
  total_files: number
  duplicate_count: number
}

export interface DeleteRequest {
  files: string[]
}

export interface DeleteResponse {
  success: number
  failed: number
  errors: string[]
}

export interface Settings {
  delete_target_path: string
  similarity_threshold: number
  root_path?: string
  folder_paths?: string[]
  max_cpu_cores?: number
  system_cpu_count?: number
  folder_root_paths?: { [key: string]: string }
  exclude_folder_paths?: string[]
  auto_selection_rules?: any
  phase1?: Phase1Settings
  phase2?: Phase2Settings
  performance?: PerformanceSettings  // Keep for backward compatibility
  page_size?: number  // Pagination: groups per page (20-500, default 100)
}

export interface Phase1Settings {
  worker_handler_size: number
  db_commit_batch_size: number
  progress_update_interval: number
  ipc_chunk_size: number
  scan_delay: number
  compute_delay: number
}

export interface Phase2Settings {
  worker_handler_size: number
  db_commit_batch_size: number
  progress_update_interval: number
  ipc_chunk_size: number
  compare_delay: number
}

export interface PerformanceSettings {
  scan_delay: number      // Delay between file scans (seconds)
  compute_delay: number   // Delay between hash computations (seconds)
  compare_delay: number   // Delay between comparisons (seconds)
  chunk_size: number      // Number of files to process per batch
  progress_update_interval: number  // Send progress update every N files
}
