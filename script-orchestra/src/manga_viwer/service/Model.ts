export interface TagData {
  category_main: string
  category_sub: string
  mosaic: string
  auth: string[]
  name: string[]
  custom: string[]
  others: string[]
}

export interface FolderModel {
  id: string
  name: string
  path: string
  size: number
  number: number
  initialized: boolean
  files: string[]
  tags: TagData
  favorite?: boolean
  read_count?: number
}

export interface MetadataModel {
  auth: string[]
  category_main: string[]
  category_sub: string[]
  total_folders?: number
  total_files?: number
  total_size?: number
}

export interface MangaIndex {
  folders: Record<string, FolderModel>
  metadata: MetadataModel
}

export interface UpdateFolderPayload {
  name?: string
  tags?: Partial<TagData>
}

// Settings Models
export interface CategoryOption {
  key: string       // shown in UI + used as the category label
  name?: string     // currently unused, kept for future use
  path?: string     // on-disk folder name under root_path
}

export interface RandomSettings {
  count: number
  enabled: boolean
}

export interface CategoriesSettings {
  main: CategoryOption[]
  sub: CategoryOption[]
}

export interface DisplaySettings {
  page_size: number
  show_uninitialized_only: boolean
  default_sort: string
}

export interface PathsSettings {
  root_path: string
  delete_paths: string
  ignore_scan_folders: string[]
}

export interface MangaViewerSettings {
  random: RandomSettings
  categories: CategoriesSettings
  display: DisplaySettings
  paths: PathsSettings
}
