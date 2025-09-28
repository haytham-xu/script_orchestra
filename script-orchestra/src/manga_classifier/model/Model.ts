
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
