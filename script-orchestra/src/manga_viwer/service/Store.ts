import { defineStore } from 'pinia'
import type { MangaIndex, FolderModel } from '../service/Model'
import { fetchIndex, fetchFileList, updateFolderModels, fetchRandomIndex, deleteFolders } from '@/manga_viwer/service/Service'

interface State {
  mangaIndex: MangaIndex
  changeIdList: Set<string>,
  moveIdList: Set<string>,
  deleteIdSet: Set<string>,  // Folders marked for deletion
  hotTags: string[]
  // Random mode
  isRandomMode: boolean
  baseFolderIds: string[]  // 基础随机组的 ID 列表
  orSearchKeywords: string[]  // "或"搜索关键词列表
}

export const useMangaIndexStore = defineStore('mangaIndex', {
  state: (): State => ({
    mangaIndex: {
      folders: {},
      metadata: {
        auth: [],
        category_main: [],
        category_sub: []
      }
    },
    changeIdList: new Set<string>(),
    moveIdList: new Set<string>(),
    deleteIdSet: new Set<string>(),
    hotTags: [],
    isRandomMode: false,
    baseFolderIds: [],
    orSearchKeywords: [],
  }),

  getters: {
  },

  actions: {
    async loadIndex(): Promise<void> {
        this.mangaIndex = await fetchIndex()
        this.isRandomMode = false
        this.baseFolderIds = []
        this.orSearchKeywords = []
    },

    async loadRandomIndex(count?: number): Promise<void> {
      const randomIndex = await fetchRandomIndex(count)
      this.mangaIndex = randomIndex
      this.isRandomMode = true
      this.baseFolderIds = Object.keys(randomIndex.folders)
      this.orSearchKeywords = []
    },

    async addOrSearchKeyword(keyword: string): Promise<void> {
      const k = keyword.trim()
      if (!k || this.orSearchKeywords.includes(k)) return

      // Add keyword to list
      this.orSearchKeywords.push(k)

      // Search in all folders (not just current index)
      const fullIndex = await fetchIndex()
      const allFolders = Object.values(fullIndex.folders)

      // Filter folders that match the keyword
      const matchedFolders = allFolders.filter(f => {
        const searchString = `${f.name} ${f.path}`.toLowerCase()
        return searchString.includes(k.toLowerCase())
      })

      // Add matched folders to current index (avoid duplicates)
      for (const folder of matchedFolders) {
        if (!this.mangaIndex.folders[folder.id]) {
          this.mangaIndex.folders[folder.id] = folder
        }
      }
    },

    clearOrSearchKeywords() {
      this.orSearchKeywords = []
      // 恢复到基础随机组
      const newFolders: Record<string, FolderModel> = {}
      for (const id of this.baseFolderIds) {
        if (this.mangaIndex.folders[id]) {
          newFolders[id] = this.mangaIndex.folders[id]
        }
      }
      this.mangaIndex.folders = newFolders
    },

    async fetchFolderFiles(folder: FolderModel): Promise<void> {
      if (folder.files && folder.files.length > 0) return
      try {
        const list = await fetchFileList(folder.id)
        folder.files = list
      } catch {
        folder.files = []
      }
    },
    recordHotTag(tag: string) {
      const t = tag.trim()
      if (!t) return
      this.hotTags = [t, ...this.hotTags.filter(x => x !== t)].slice(0, 10)
    },
    addChangeId(id: string) {
      if (!id) return
      if (!this.changeIdList.has(id)) {
        const s = new Set(this.changeIdList)
        s.add(id)
        this.changeIdList = s
      }
    },
    addMoveId(id: string) {
      if (!id) return
      if (!this.moveIdList.has(id)) {
        const s = new Set(this.moveIdList)
        s.add(id)
        this.moveIdList = s
      }
    },

    markForDeletion(id: string) {
      if (!id) return
      if (!this.deleteIdSet.has(id)) {
        const s = new Set(this.deleteIdSet)
        s.add(id)
        this.deleteIdSet = s
      }
    },

    unmarkForDeletion(id: string) {
      if (!id) return
      if (this.deleteIdSet.has(id)) {
        const s = new Set(this.deleteIdSet)
        s.delete(id)
        this.deleteIdSet = s
      }
    },

    async applyChanges(classifierModeEnabled: boolean): Promise<void> {
      if (!this.changeIdList.size) return
      const changed: Record<string, FolderModel> = {}
      for (const id of this.changeIdList) {
        const fm = this.mangaIndex.folders[id]
        if (fm) changed[id] = fm
      }
      if (!Object.keys(changed).length) {
        this.changeIdList = new Set()
        return
      }
      try {
        await updateFolderModels(changed, classifierModeEnabled)
        this.changeIdList = new Set()
        if (classifierModeEnabled) {
          for (const id of this.moveIdList) {
            if (id in this.mangaIndex.folders) {
              delete this.mangaIndex.folders[id]
            }
          }
          this.moveIdList = new Set()
        }
      } catch (e) {
        console.error('applyChanges failed:', e)
      }
      await new Promise(resolve => setTimeout(resolve, 1000))
    },

    async applyDeletion(): Promise<void> {
      if (!this.deleteIdSet.size) return

      const deleteList = Array.from(this.deleteIdSet)

      try {
        // Call backend API to delete folders
        await deleteFolders(deleteList)

        // Remove from local index
        for (const id of deleteList) {
          delete this.mangaIndex.folders[id]
        }

        // Clear deletion set
        this.deleteIdSet = new Set()
      } catch (e) {
        console.error('applyDeletion failed:', e)
        throw e
      }
    },
  }
})
