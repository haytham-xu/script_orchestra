export interface DuplicateImage {
  file_path: string
  phash: string
  resolution: string
  filesize: number
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
}
