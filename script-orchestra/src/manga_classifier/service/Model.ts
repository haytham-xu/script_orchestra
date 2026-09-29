
export interface CategoryButton {
  label: string
  folderPath: string
}

export interface CategoryButtonCard {
  name: string
  mainButtons: CategoryButton[]
  subButtons: CategoryButton[]
}

export interface ButtonConfigJSON {
  left: CategoryButtonCard
  right: CategoryButtonCard
  epic?: CategoryButtonCard
}

// -----------

export enum FolderStatus {
  Pending = "pending",
  Done = "done"
}

export interface FolderObject {
  folderName: string
  status: FolderStatus
}

export interface FolderObjectList {
  folderList: FolderObject[]
}

// -----------

export enum FileType {
  Image = "image",
  Video = "video"
}

export interface FileModel {
    fileType: FileType
    fileUrl: string
}

export interface FileList {
  files: FileModel[]
}

// -----------

export interface ScanItem {
  name: string
  folderPath: string
  count: number
}

export interface ScanResult {
  items: ScanItem[]
}

// -----------

export interface MangaClassifierSettings {
  rootPath: string
  targetPath: string
  deletePath: string
  imageExts: string[]
  videoExts: string[]
  categoty: ButtonConfigJSON
  epicCategory: CategoryButtonCard
  imageWidthPx: number
  scrollPageRatio: number
  pinSidebars: boolean
  filePageSize: number
}
