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
