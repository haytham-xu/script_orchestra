import { defineStore } from 'pinia'
import type { MangaIndex, FolderModel, TagData } from '../service/Model'
import { fetchIndex, fetchFileList } from '@/manga_viwer/service/Service'

interface State {
  mangaIndex: MangaIndex
  selectedFolderId: string | null
  filterTags: Partial<Record<keyof TagData, string[]>>
  keyword: string
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
    selectedFolderId: null,
    filterTags: {},
    keyword: ''
  }),

  getters: {
    // foldersArray: (s): FolderModel[] => Object.values(s.mang a mangaIndex.folders),
    // selectedFolder: (s): FolderModel | null =>
    //   s.selectedFolderId ? s.mangaIndex.folders[s.selectedFolderId] || null : null,
    // filteredFolders(): FolderModel[] {
    //   let list = this.foldersArray
    //   // 关键词（匹配 name 或 path）
    //   if (this.keyword.trim()) {
    //     const kw = this.keyword.trim().toLowerCase()
    //     list = list.filter(f => f.name.toLowerCase().includes(kw) || f.path.toLowerCase().includes(kw))
    //   }
    //   // 标签筛选（全部条件命中）
    //   for (const key of Object.keys(this.filterTags) as (keyof TagData)[]) {
    //     const values = this.filterTags[key]
    //     if (!values || values.length === 0) continue
    //     list = list.filter(f => {
    //       const t = f.tags[key]
    //       if (Array.isArray(t)) {
    //         return values.some(v => t.includes(v))
    //       } else if (typeof t === 'string') {
    //         return values.includes(t)
    //       } else if (typeof t === 'boolean' || t === null) {
    //         return values.includes(String(t))
    //       }
    //       return false
    //     })
    //   }
    //   return list
    // }
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
        console.log('fetch success:', folder.path)
      } catch {
        folder.files = []
      }
    }
  }
})
