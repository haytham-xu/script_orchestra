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
}

export interface MetadataModel {
  auth: string[]
  category_main: string[]
  category_sub: string[]
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
  id: string
  label: string
  target_folder?: string
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
  index_path: string
  scan_folders: string[]
  ignore_scan_folders: string[]
  category_paths: string
  delete_paths: string
}

export interface MangaViewerSettings {
  random: RandomSettings
  categories: CategoriesSettings
  display: DisplaySettings
  paths: PathsSettings
}
