import { defineStore } from 'pinia'
import type { GroupList, DefaultGroup, FileModel, Group } from '@/photo_classifier/model/Model.ts'
import { FileStatus, FileType, GroupStatus } from '@/photo_classifier/model/Model.ts'
import { postMoveFolder } from '@/photo_classifier/service/PhotoClassifierService.ts'
import { ElMessage } from 'element-plus'
import { tr } from 'element-plus/es/locales.mjs'

interface PhotoClassifierStoreState {
  groupList: GroupList
  defaultGroup: DefaultGroup
  initialized: boolean
  groupActionLock: boolean
}

export const usePhotoClassifierStore = defineStore('photoClassifierStore', {
  state: (): PhotoClassifierStoreState => ({
    groupList: { groupList: [] },
    defaultGroup: { files: [] },
    initialized: false,
    groupActionLock: false,
  }),

  getters: {
    defaultGroupAvatar: (state): string => {
      const firstImage = state.defaultGroup.files.find(
        (file: FileModel) => file.fileType === FileType.Image,
      )
      return firstImage?.fileUrl ?? ''
    },

    groupAvatar: (state) => {
      return (groupId: number): string => {
        const firstImage = state.groupList.groupList[groupId].files.find(
          (file: FileModel) => file.fileType === FileType.Image,
        )
        return firstImage?.fileUrl ?? ''
      }
    },
  },

  actions: {
    initDefaultGroup(defaultGroup: DefaultGroup) {
      if (this.initialized) return
      this.defaultGroup = defaultGroup
      this.initialized = true
    },

    createNewGroupWithFile(file: FileModel): number {
      // ElMessage.info(file.filePath + ' -- ' + file.groupId + ' -- ' + this.groupActionLock)
      if (this.groupActionLock) {
        ElMessage.error(
          'Localed!! Failed: Add file ' + file.filePath + ' to new Group: ' + file.groupId,
        )
        return file.groupId
      }
      this.groupActionLock = true
      // if (file.fileStatus == FileStatus.IN_GROUP) {
      //   ElMessage.warning('FIle already in group, skip: ' + file.groupId)
      //   return file.groupId
      // }
      try {
        const newGroupId = this.groupList.groupList.length
        file.fileStatus = FileStatus.IN_GROUP
        file.groupId = newGroupId

        const newGroup: Group = {
          files: [file],
          groupStatus: GroupStatus.IN_PROGRESS,
          groupId: newGroupId,
        }

        this.groupList.groupList.push(newGroup)

        ElMessage.info('Add file ' + file.filePath + ' to new Group: ' + file.groupId)
        return file.groupId
      } finally {
        this.groupActionLock = false
      }
    },

    addFileToGroup(file: FileModel, groupIndex: number) {
      // ElMessage.info(
      //   file.filePath + ' -- ' + file.groupId + ' -- ' + groupIndex + ' -- ' + this.groupActionLock,
      // )
      if (this.groupActionLock) {
        ElMessage.error(
          'Localed!! Failed: Add file ' + file.filePath + ' to new Group: ' + file.groupId,
        )
        return file.groupId
      }
      this.groupActionLock = true
      // if (file.fileStatus == FileStatus.IN_GROUP) {
      //   ElMessage.warning('FIle already in group, skip: ' + file.groupId)
      //   return
      // }
      try {
        ElMessage.info('Add file ' + file.filePath + ' to new Group: ' + groupIndex)
        const targetGroup = this.groupList.groupList[groupIndex]
        if (!targetGroup) {
          ElMessage.warning(`[PhotoClassifierStore] Group ${groupIndex} not found`)
          return
        }

        file.fileStatus = FileStatus.IN_GROUP
        file.groupId = groupIndex
        targetGroup.files.push(file)
      } finally {
        this.groupActionLock = false
      }
    },

    async applyFiles(files: FileModel[]) {
      for (const a_file of files) {
        await this.applyFile(a_file)
      }
    },

    async applyFile(a_file: FileModel) {
      if (a_file.fileStatus == FileStatus.Done) return
      if (!a_file.categoryTag) return
      await postMoveFolder(a_file.filePath, a_file.categoryTag)
      a_file.fileStatus = FileStatus.Done
    },
  },
})
