import { defineStore } from 'pinia'
import type { MangaIndex, FolderModel } from '../service/Model'
import { fetchIndex, fetchFileList, updateFolderModels } from '@/manga_viwer/service/Service'

interface State {
  mangaIndex: MangaIndex
  changeIdList: Set<string>,
  moveIdList: Set<string>,
  hotTags: string[]
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
    hotTags: [],
  }),

  getters: {
  },

  actions: {
    async loadIndex(): Promise<void> {
        this.mangaIndex = await fetchIndex()
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
        for (const id of Object.keys(changed)) {
          if (this.mangaIndex.folders[id].tags.category_main === 'del') {
            delete this.mangaIndex.folders[id]
          }
        }
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
  }
})
