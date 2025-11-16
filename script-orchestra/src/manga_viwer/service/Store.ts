import { defineStore } from 'pinia'
import type { MangaIndex, FolderModel, TagData } from '../service/Model'
import { fetchIndex, fetchFileList } from '@/manga_viwer/service/Service'

interface State {
  mangaIndex: MangaIndex
  selectedFolderId: string | null
  filterTags: Partial<Record<keyof TagData, string[]>>  // 用于简单筛选
  keyword: string
}

// const emptyTag: TagData = {
//   auth: [],
//   name: [],
//   category_main: '',
//   category_sub: '',
//   custom: [],
//   mosaic: null,
//   others: []
// }

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
        // console.log('1: ', this.mangaIndex)
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
    // async fetchAllFolderFilesSequential(delayMs = 1000) {
    //   const folders = Object.values(this.mangaIndex.folders)
    //   for (const f of folders) {
    //     try {
    //         const list = await fetchFileList(f.path)
    //         f.files = list
    //         console.log('fetch success:', f.path)
    //     } catch {
    //         f.files = []
    //         console.log('fetch failed:', f.path)
    //     }
    //     await new Promise(r => setTimeout(r, delayMs))
    //   }
    // }


    // setKeyword(v: string) {
    //   this.keyword = v
    // },

    // setFilterTags(partial: Partial<Record<keyof TagData, string[]>>) {
    //   this.filterTags = { ...this.filterTags, ...partial }
    // },

    // clearFilters() {
    //   this.filterTags = {}
    //   this.keyword = ''
    // },

    // selectFolder(id: string | null) {
    //   this.selectedFolderId = id
    // }

    // ,
    // updateFolderLocally(id: string, payload: UpdateFolderPayload) {
    //   const f = this.mangaIndex.folders[id]
    //   if (!f) return
    //   if (payload.name !== undefined) {
    //     f.name = payload.name
    //   }
    //   if (payload.tags) {
    //     f.tags = { ...f.tags, ...payload.tags }
    //   }
    // },

    // async renameFolder(id: string, newName: string, url = '/api/manga/rename'): Promise<boolean> {
    //   const f = this.mangaIndex.folders[id]
    //   if (!f) return false
    //   const res = await fetch(url, {
    //     method: 'POST',
    //     headers: { 'Content-Type': 'application/json' },
    //     body: JSON.stringify({ id, name: newName })
    //   })
    //   if (!res.ok) return false
    //   f.name = newName
    //   return true
    // },

    // async updateTags(id: string, tagsPatch: Partial<TagData>, url = '/api/manga/update-tags'): Promise<boolean> {
    //   const f = this.mangaIndex.folders[id]
    //   if (!f) return false
    //   const res = await fetch(url, {
    //     method: 'POST',
    //     headers: { 'Content-Type': 'application/json' },
    //     body: JSON.stringify({ id, tags: tagsPatch })
    //   })
    //   if (!res.ok) return false
    //   f.tags = { ...f.tags, ...tagsPatch }
    //   return true
    // },

    // async refreshIndex(url = '/api/manga/refresh'): Promise<void> {
    //   // 后端刷新索引，然后重新拉
    //   const res = await fetch(url, { method: 'POST' })
    //   if (res.ok) {
    //     await this.loadIndex()
    //   }
    // },

    // getFolderByName(name: string): FolderModel | undefined {
    //   return this.foldersArray.find(f => f.name === name)
    // }
  }
})
