
export enum FileType {
  Image = "image",
  Video = "video"
}

export enum FileStatus {
  Pending = "pending",
  IN_GROUP = "in_group",
  Done = "done",
}

export enum FileCategory {
  BEST = "best",
  BETTER = "better",
  NORMAL = "normal",
  DEL = "del",
}

export interface FileModel {
    filePath: string
    fileStatus: FileStatus
    fileUrl: string
    categoryTag: FileCategory
    groupId: number
    fileType: FileType
}

export enum GroupStatus {
  IN_PROGRESS = "in_progress",
  APPLIED = "applied"
}

export interface Group {
  files: FileModel[]
  // groupAvatar: FileModel
  groupStatus: GroupStatus
  groupId: number
}

export interface GroupList {
  groupList: Group[]
}


export interface DefaultGroup {
    files: FileModel[]
}
