import { defineStore } from 'pinia'
import type { GroupList, DefaultGroup, FileModel, Group } from '@/photo_classifier/model/Model.ts'
import { FileCategory, FileStatus, FileType, GroupStatus } from '@/photo_classifier/model/Model.ts'
import {postMoveFolder} from '@/photo_classifier/service/PhotoClassifierService.ts'

interface PhotoClassifierStoreState {
  groupList: GroupList
  defaultGroup: DefaultGroup
  initialized: boolean,
}

export const usePhotoClassifierStore = defineStore('photoClassifierStore', {
  state: (): PhotoClassifierStoreState => ({
    groupList: { groupList: [] },
    defaultGroup: { files: [] },
    initialized: false ,
  }),

  getters: {

    defaultGroupAvatar: (state): string => {
      const firstImage = state.defaultGroup.files.find(
        (file: FileModel) => file.fileType === FileType.Image
      )
      return firstImage?.fileUrl ?? ''
    },

    groupAvatar: (state) => {
      return (groupId: number): string => {
        const firstImage = state.groupList.groupList[groupId].files.find(
          (file: FileModel) => file.fileType === FileType.Image
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
      if(file.fileStatus == FileStatus.IN_GROUP) {
        console.log("FIle already in group, skip: ", file.groupId)
        return file.groupId;
      }

      const newGroupId = this.groupList.groupList.length
      file.fileStatus = FileStatus.IN_GROUP
      file.groupId = newGroupId

      const newGroup: Group = {
        files: [file],
        groupStatus: GroupStatus.IN_PROGRESS,
        groupId: newGroupId
      }

      this.groupList.groupList.push(newGroup)
      return file.groupId
    },

    addFileToGroup(file: FileModel, groupIndex: number) {
      if(file.fileStatus == FileStatus.IN_GROUP) {
        console.log("FIle already in group, skip: ", file.groupId)
        return;
      }

      const targetGroup = this.groupList.groupList[groupIndex]
      if (!targetGroup) {
        console.warn(`[PhotoClassifierStore] Group ${groupIndex} not found`)
        return
      }

      file.fileStatus = FileStatus.IN_GROUP
      file.groupId = groupIndex
      targetGroup.files.push(file)
    },

    async applyFiles(files: FileModel[]) {
      for(const a_file of files) {
        await this.applyFile(a_file)
      }
    },

    async applyFile(a_file: FileModel) {
        if(a_file.fileStatus == FileStatus.Done) return
        if(!a_file.categoryTag) return
        await postMoveFolder(a_file.filePath,a_file.categoryTag)
        a_file.fileStatus = FileStatus.Done
    },
  }
})
