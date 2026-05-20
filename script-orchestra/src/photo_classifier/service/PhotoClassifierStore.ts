import { defineStore } from 'pinia'
import type { GroupList, DefaultGroup, FileModel, Group } from '@/photo_classifier/service/Model.ts'
import { FileStatus, FileType, GroupStatus } from '@/photo_classifier/service/Model.ts'
import { postMoveFolder, saveWorkingState, loadWorkingState, clearWorkingState } from '@/photo_classifier/service/PhotoClassifierService.ts'
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
      // First try to find an image
      const firstImage = state.defaultGroup.files.find(
        (file: FileModel) => file.fileType === FileType.Image,
      )
      if (firstImage) return firstImage.fileUrl

      // If no image, use first video
      const firstVideo = state.defaultGroup.files.find(
        (file: FileModel) => file.fileType === FileType.Video,
      )
      return firstVideo?.fileUrl ?? ''
    },

    groupAvatar: (state) => {
      return (groupId: number): string => {
        const group = state.groupList.groupList[groupId]
        if (!group) return ''

        // First try to find an image
        const firstImage = group.files.find(
          (file: FileModel) => file.fileType === FileType.Image,
        )
        if (firstImage) return firstImage.fileUrl

        // If no image, use first video
        const firstVideo = group.files.find(
          (file: FileModel) => file.fileType === FileType.Video,
        )
        return firstVideo?.fileUrl ?? ''
      }
    },
  },

  actions: {
    // Auto-save working state to backend
    async autoSaveWorkingState() {
      try {
        await saveWorkingState({
          defaultGroup: this.defaultGroup,
          groupList: this.groupList,
        })
      } catch (error) {
        console.error('Failed to auto-save working state:', error)
        // Don't show error message to avoid annoying the user
      }
    },

    // Load working state from backend
    async loadWorkingStateFromBackend(): Promise<boolean> {
      try {
        const state = await loadWorkingState()
        if (state) {
          this.defaultGroup = state.defaultGroup
          this.groupList = state.groupList
          this.initialized = true
          return true
        }
        return false
      } catch (error) {
        console.error('Failed to load working state:', error)
        return false
      }
    },

    // Clear working state (called after Apply or path change)
    async clearWorkingStateFromBackend(targetRootPath?: string) {
      try {
        await clearWorkingState(targetRootPath)
      } catch (error) {
        console.error('Failed to clear working state:', error)
      }
    },

    // Reset all state (clear all groups and marks)
    async resetAllState() {
      // Clear all groups
      this.groupList = { groupList: [] }

      // Reset all files to pending state and clear categoryTag
      for (const file of this.defaultGroup.files) {
        file.fileStatus = FileStatus.Pending
        file.categoryTag = null
        file.groupId = null
      }

      // Reset current group index
      this.currentGroupIndex = -1

      ElMessage.success({
        message: '已重置所有分组和标记',
        offset: 20,
        duration: 1500,
        customClass: 'message-bottom'
      })
    },

    initDefaultGroup(defaultGroup: DefaultGroup, force = false) {
      // Allow force re-initialization for test isolation
      if (this.initialized && !force) return

      // Clear existing state when re-initializing
      if (force) {
        this.groupList = { groupList: [] }
        this.currentGroupIndex = -1
      }

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
            ElMessage.info({
              message: `Moved file from Group ${file.groupId} to new group`,
              offset: 20,
              duration: 1500,
              customClass: 'message-bottom'
            })
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

        ElMessage.success({
          message: 'Added file to new Group: ' + newGroupId,
          offset: 20,
          duration: 1500,
          customClass: 'message-bottom'
        })

        // Auto-save after creating new group
        this.autoSaveWorkingState()

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
            ElMessage.info({
              message: `Moved file from Group ${file.groupId} to Group ${groupIndex}`,
              offset: 20,
              duration: 1500,
              customClass: 'message-bottom'
            })
          }
        }

        // Add file to target group
        file.fileStatus = FileStatus.IN_GROUP
        file.groupId = groupIndex
        targetGroup.files.push(file)

        // Update currentGroupIndex to the group we just added to
        this.currentGroupIndex = groupIndex

        ElMessage.success({
          message: 'Added file to Group: ' + groupIndex,
          offset: 20,
          duration: 1500,
          customClass: 'message-bottom'
        })

        // Auto-save after adding file to group
        this.autoSaveWorkingState()
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
      const messageConfig = { offset: 20, duration: 1500, customClass: 'message-bottom' }
      if (successCount > 0) {
        ElMessage.success({ message: `成功处理 ${successCount} 个文件`, ...messageConfig })
      }
      if (skipCount > 0) {
        ElMessage.info({ message: `跳过 ${skipCount} 个文件（未标记或已处理）`, ...messageConfig })
      }
      if (errorCount > 0) {
        ElMessage.error({ message: `处理失败 ${errorCount} 个文件`, ...messageConfig })
      }
      if (successCount === 0 && skipCount === 0 && errorCount === 0) {
        ElMessage.warning({ message: '没有需要处理的文件', ...messageConfig })
      }

      // Auto-save after applying files
      await this.autoSaveWorkingState()
    },

    async applyFile(a_file: FileModel): Promise<'success' | 'skip' | 'error'> {
      console.log('[Store] applyFile:', a_file.filePath, '- Status:', a_file.fileStatus, '- CategoryTag:', a_file.categoryTag)

      if (a_file.fileStatus == FileStatus.Done) return 'skip'
      if (!a_file.categoryTag) return 'skip'

      try {
        console.log('[Store] applyFile - Calling postMoveFolder:', a_file.filePath, '->', a_file.categoryTag)
        await postMoveFolder(a_file.filePath, a_file.categoryTag)
        a_file.fileStatus = FileStatus.Done
        console.log('[Store] applyFile - Success:', a_file.filePath)
        return 'success'
      } catch (error) {
        console.error(`Failed to move file ${a_file.filePath}:`, error)
        return 'error'
      }
    },

    // Batch operations for multi-select
    batchCreateNewGroup(files: FileModel[]): number {
      if (this.groupActionLock) {
        ElMessage.warning('Operation in progress, please wait')
        return -1
      }
      this.groupActionLock = true

      try {
        const newGroupId = this.groupList.groupList.length
        const filesToAdd: FileModel[] = []

        // Remove files from their old groups if needed
        for (const file of files) {
          if (file.fileStatus === FileStatus.IN_GROUP && file.groupId !== null) {
            const oldGroup = this.groupList.groupList[file.groupId]
            if (oldGroup) {
              oldGroup.files = oldGroup.files.filter(f => f.filePath !== file.filePath)
            }
          }

          file.fileStatus = FileStatus.IN_GROUP
          file.groupId = newGroupId
          filesToAdd.push(file)
        }

        const newGroup: Group = {
          files: filesToAdd,
          groupStatus: GroupStatus.IN_PROGRESS,
          groupId: newGroupId,
        }

        this.groupList.groupList.push(newGroup)
        this.currentGroupIndex = newGroupId

        // Auto-save after batch creating new group
        this.autoSaveWorkingState()

        return newGroupId
      } finally {
        this.groupActionLock = false
      }
    },

    batchAddFilesToGroup(files: FileModel[], groupIndex: number) {
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

        let addedCount = 0
        let movedCount = 0

        for (const file of files) {
          // Skip if already in target group
          if (file.fileStatus === FileStatus.IN_GROUP && file.groupId === groupIndex) {
            continue
          }

          // Remove from old group if needed
          if (file.fileStatus === FileStatus.IN_GROUP && file.groupId !== null) {
            const oldGroup = this.groupList.groupList[file.groupId]
            if (oldGroup) {
              oldGroup.files = oldGroup.files.filter(f => f.filePath !== file.filePath)
              movedCount++
            }
          } else {
            addedCount++
          }

          file.fileStatus = FileStatus.IN_GROUP
          file.groupId = groupIndex
          targetGroup.files.push(file)
        }

        this.currentGroupIndex = groupIndex

        const messageConfig = { offset: 20, duration: 1500, customClass: 'message-bottom' }
        if (movedCount > 0 && addedCount > 0) {
          ElMessage.success({ message: `移动了 ${movedCount} 张，新增了 ${addedCount} 张到分组 ${groupIndex}`, ...messageConfig })
        } else if (movedCount > 0) {
          ElMessage.success({ message: `移动了 ${movedCount} 张到分组 ${groupIndex}`, ...messageConfig })
        } else if (addedCount > 0) {
          ElMessage.success({ message: `添加了 ${addedCount} 张到分组 ${groupIndex}`, ...messageConfig })
        }

        // Auto-save after batch adding files to group
        this.autoSaveWorkingState()
      } finally {
        this.groupActionLock = false
      }
    },

    removeFilesFromGroup(files: FileModel[], groupIndex: number) {
      if (this.groupActionLock) {
        ElMessage.warning('Operation in progress, please wait')
        return
      }
      this.groupActionLock = true

      try {
        const group = this.groupList.groupList[groupIndex]
        if (!group) {
          ElMessage.warning(`Group ${groupIndex} not found`)
          return
        }

        const filePathsToRemove = files.map(f => f.filePath)
        group.files = group.files.filter(f => !filePathsToRemove.includes(f.filePath))

        // Update file status
        for (const file of files) {
          file.fileStatus = FileStatus.Pending
          file.groupId = null
        }

        ElMessage.success({
          message: `已从分组 ${groupIndex} 移除 ${files.length} 张图片`,
          offset: 20,
          duration: 1500,
          customClass: 'message-bottom'
        })

        // Auto-save after removing files from group
        this.autoSaveWorkingState()
      } finally {
        this.groupActionLock = false
      }
    },
  },
})
