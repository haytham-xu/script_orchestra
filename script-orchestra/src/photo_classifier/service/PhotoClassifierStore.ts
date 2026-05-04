import { defineStore } from 'pinia'
import type { GroupList, DefaultGroup, FileModel, Group } from '@/photo_classifier/service/Model.ts'
import { FileStatus, FileType, GroupStatus } from '@/photo_classifier/service/Model.ts'
import { postMoveFolder } from '@/photo_classifier/service/PhotoClassifierService.ts'
import { ElMessage } from 'element-plus'

interface PhotoClassifierStoreState {
  groupList: GroupList
  defaultGroup: DefaultGroup
  initialized: boolean
  groupActionLock: boolean
  currentGroupIndex: number  // Track current active group index
}

export const usePhotoClassifierStore = defineStore('photoClassifierStore', {
  state: (): PhotoClassifierStoreState => ({
    groupList: { groupList: [] },
    defaultGroup: { files: [] },
    initialized: false,
    groupActionLock: false,
    currentGroupIndex: -1,  // -1 means no group selected
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
      if (this.groupActionLock) {
        ElMessage.warning('Operation in progress, please wait')
        return file.groupId ?? -1
      }
      this.groupActionLock = true

      try {
        // If file is already in a group, remove it from that group first
        if (file.fileStatus == FileStatus.IN_GROUP && file.groupId !== null) {
          const oldGroup = this.groupList.groupList[file.groupId]
          if (oldGroup) {
            oldGroup.files = oldGroup.files.filter(f => f.filePath !== file.filePath)
            ElMessage.info(`Moved file from Group ${file.groupId} to new group`)
          }
        }

        const newGroupId = this.groupList.groupList.length
        file.fileStatus = FileStatus.IN_GROUP
        file.groupId = newGroupId

        const newGroup: Group = {
          files: [file],
          groupStatus: GroupStatus.IN_PROGRESS,
          groupId: newGroupId,
        }

        this.groupList.groupList.push(newGroup)

        // Update currentGroupIndex to the newly created group
        this.currentGroupIndex = newGroupId

        ElMessage.success('Added file to new Group: ' + newGroupId)
        return newGroupId
      } finally {
        this.groupActionLock = false
      }
    },

    addFileToGroup(file: FileModel, groupIndex: number) {
      if (this.groupActionLock) {
        ElMessage.warning('Operation in progress, please wait')
        return
      }
      this.groupActionLock = true

      try {
        const targetGroup = this.groupList.groupList[groupIndex]
        if (!targetGroup) {
          ElMessage.warning(`Group ${groupIndex} not found`)
          return
        }

        // If file is already in the same group, do nothing
        if (file.fileStatus == FileStatus.IN_GROUP && file.groupId === groupIndex) {
          ElMessage.warning('File already in this group')
          return
        }

        // If file is in a different group, remove it from that group first
        if (file.fileStatus == FileStatus.IN_GROUP && file.groupId !== null && file.groupId !== groupIndex) {
          const oldGroup = this.groupList.groupList[file.groupId]
          if (oldGroup) {
            oldGroup.files = oldGroup.files.filter(f => f.filePath !== file.filePath)
            ElMessage.info(`Moved file from Group ${file.groupId} to Group ${groupIndex}`)
          }
        }

        // Add file to target group
        file.fileStatus = FileStatus.IN_GROUP
        file.groupId = groupIndex
        targetGroup.files.push(file)

        // Update currentGroupIndex to the group we just added to
        this.currentGroupIndex = groupIndex

        ElMessage.success('Added file to Group: ' + groupIndex)
      } finally {
        this.groupActionLock = false
      }
    },

    async applyFiles(files: FileModel[]) {
      let successCount = 0
      let skipCount = 0
      let errorCount = 0

      for (const a_file of files) {
        const result = await this.applyFile(a_file)
        if (result === 'success') successCount++
        else if (result === 'skip') skipCount++
        else if (result === 'error') errorCount++
      }

      // 从 defaultGroup 中移除已处理的文件
      this.defaultGroup.files = this.defaultGroup.files.filter(
        (file) => file.fileStatus !== FileStatus.Done
      )

      // 显示结果统计
      if (successCount > 0) {
        ElMessage.success(`成功处理 ${successCount} 个文件`)
      }
      if (skipCount > 0) {
        ElMessage.info(`跳过 ${skipCount} 个文件（未标记或已处理）`)
      }
      if (errorCount > 0) {
        ElMessage.error(`处理失败 ${errorCount} 个文件`)
      }
      if (successCount === 0 && skipCount === 0 && errorCount === 0) {
        ElMessage.warning('没有需要处理的文件')
      }
    },

    async applyFile(a_file: FileModel): Promise<'success' | 'skip' | 'error'> {
      if (a_file.fileStatus == FileStatus.Done) return 'skip'
      if (!a_file.categoryTag) return 'skip'

      try {
        await postMoveFolder(a_file.filePath, a_file.categoryTag)
        a_file.fileStatus = FileStatus.Done
        return 'success'
      } catch (error) {
        console.error(`Failed to move file ${a_file.filePath}:`, error)
        return 'error'
      }
    },
  },
})
