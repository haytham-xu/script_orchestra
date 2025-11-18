
import { defineComponent, ref, onMounted, onBeforeUnmount, computed, watch, reactive, nextTick } from 'vue'
import { useMangaIndexStore } from '@/manga_viwer/service/Store'
import type { FolderModel } from '../service/Model'
import { ElInput, ElTag, ElSwitch } from 'element-plus'
import { Delete, Star } from '@element-plus/icons-vue'
import { updateFolderModel, fetchHotTags, deleteFolderModel, starFolderModel } from '@/manga_viwer/service/Service'

export default defineComponent({
  name: 'MangaViewerView',
  components: { ElInput, ElTag, ElSwitch },
  setup() {
    //  Basic
    // -------------------------------------------------------------------------------------------------------
    const store = useMangaIndexStore()


    // Lazy load on scroll
    // -------------------------------------------------------------------------------------------------------
    const pageSize = 10
    const currentPage = ref(1)
    const loadingToken = ref(0)
    function onScroll() {
      const nearBottom = window.innerHeight + window.scrollY >= document.body.offsetHeight - 300
      if (nearBottom && canLoadMore.value) {
        currentPage.value++
        fetchFilesForCurrentPage()
      }
    }

    // Search with Hot Tags
    // -------------------------------------------------------------------------------------------------------
    const searchTokens = ref<string[]>([])
    const searchInput = ref('')
    const hotTags = ref<string[]>([])
    const showUninitializedOnly = ref(false)
    const sizeSortEnabled = ref(false)

    function addSearchToken() {
      const v = searchInput.value.trim()
      if (!v) return
      if (!searchTokens.value.includes(v)) searchTokens.value.push(v)
      searchInput.value = ''
    }
    function removeSearchToken(idx: number) {
      searchTokens.value.splice(idx, 1)
    }
    function addHotTag(tag: string) {
      if (!searchTokens.value.includes(tag)) searchTokens.value.push(tag)
    }

    const folders = computed(() => Object.values(store.mangaIndex.folders))

    const filteredFolders = computed(() => {
      const tokens = searchTokens.value.map(t => t.trim().toLowerCase()).filter(Boolean)
      let base = folders.value
      if (tokens.length) {
        base = base.filter(f => {
          const pool: string[] = [
            f.name,
            f.tags.category_main,
            f.tags.category_sub,
            String(f.tags.mosaic ?? '')
          ].concat(f.tags.auth, f.tags.name, f.tags.custom, f.tags.others).map(s => s?.toLowerCase())
          return tokens.every(tok => pool.some(p => p && p.includes(tok)))
        })
      }
      if (showUninitializedOnly.value) {
        base = base.filter(f => !f.initialized)
      }
      if (sizeSortEnabled.value) {
        base = [...base].sort((a, b) => b.size - a.size)
      }
      return base
    })

    watch(searchTokens, () => {
      currentPage.value = 1
      fetchFilesForCurrentPage()
    })

    watch(sizeSortEnabled, () => {
      currentPage.value = 1
      fetchFilesForCurrentPage()
    })

    // Lazy Load Files
    // -------------------------------------------------------------------------------------------------------
    const pagedFolders = computed(() =>
      filteredFolders.value.slice(0, currentPage.value * pageSize)
    )

    const canLoadMore = computed(() =>
      pagedFolders.value.length < filteredFolders.value.length
    )

    async function fetchFilesForCurrentPage() {
      const token = ++loadingToken.value
      // 顺序加载当前页中尚未加载的文件夹
      for (const f of pagedFolders.value) {
        if (loadingToken.value !== token) return // 被重置，中止
        if (!f.files || f.files.length === 0) {
          await store.fetchFolderFiles(f)
        }
      }
    }

    watch(filteredFolders, () => {
      // 搜索或过滤变化：重置页数并重新加载第一页需要的文件
      currentPage.value = 1
      fetchFilesForCurrentPage()
    })

    function previewImages(f: FolderModel): string[] {
      const exts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']
      const list: string[] = (f.files || []).filter((p: string) => {
        const e = p.split('.').pop()?.toLowerCase() || ''
        return exts.includes(e)
      })
      return list.slice(0, 3)
    }

    const dialogVisible = ref(false)
    const dialogFolder = ref<FolderModel | null>(null)
    const dialogFiles = computed(() => dialogFolder.value?.files || [])

    function openModal(f: FolderModel) {
      dialogFolder.value = f
      dialogVisible.value = true
      // 若尚未加载此文件夹的文件，加载
      if (!f.files || f.files.length === 0) {
        store.fetchFolderFiles(f)
      }
    }
    function closeModal() {
      dialogVisible.value = false
      dialogFolder.value = null
    }

    function isImage(p: string) {
      return /\.(jpe?g|png|gif|webp|bmp|tiff)$/i.test(p)
    }
    function isVideo(p: string) {
      return /\.(mp4|webm|mov|mkv|avi|flv)$/i.test(p)
    }

    // Code for Update
    // -------------------------------------------------------------------------------------------------------
    const editingNameFlag = ref<string | null>(null)
    const activeInput = ref<InstanceType<typeof ElInput> | null>(null)

    function setActiveInput(el: InstanceType<typeof ElInput> | null) {
      activeInput.value = el
      if (!el) return
      nextTick(() => {
        if (typeof el.focus === 'function') {
          el.focus()
          return
        }
        const root: HTMLElement | null = (el as unknown as { $el?: HTMLElement }).$el || null
        const raw: HTMLInputElement | null = root?.querySelector('input') || null
        raw?.focus()
      })
    }

    const editingCategoryMainFlag = ref<string | null>(null)
    const editingCategorySubFlag = ref<string | null>(null)
    const editingMosaicFlag = ref<string | null>(null)

    const editValue = reactive({
      name: '',
      category_main: '',
      category_sub: '',
      mosaic: ''
    })

    function startEdit(field: 'name' | 'category_main' | 'category_sub' | 'mosaic', f: FolderModel) {
      if (field === 'name') {
        editingNameFlag.value = f.id
        editValue.name = f.name
      }
      if (field === 'category_main') {
        editingCategoryMainFlag.value = f.id
        editValue.category_main = f.tags.category_main
        return
      }
      if (field === 'category_sub') {
        editingCategorySubFlag.value = f.id
        editValue.category_sub = f.tags.category_sub
        return
      }
      if (field === 'mosaic') {
        editingMosaicFlag.value = f.id
        editValue.mosaic = String(f.tags.mosaic ?? '')
      }
    }

    async function commitEdit(field: 'name' | 'category_main' | 'category_sub' | 'mosaic', f: FolderModel) {
      let changed = false
      if (field === 'name') {
        editingNameFlag.value = null
        if (f.name !== editValue.name) {
          f.name = editValue.name.trim()
          changed = true
        }
      } else if (field === 'category_main') {
        editingCategoryMainFlag.value = null
        if (f.tags.category_main !== editValue.category_main) {
          f.tags.category_main = editValue.category_main.trim()
          changed = true
        }
      } else if (field === 'category_sub') {
        editingCategorySubFlag.value = null
        if (f.tags.category_sub !== editValue.category_sub) {
          f.tags.category_sub = editValue.category_sub.trim()
          changed = true
        }
      } else if (field === 'mosaic') {
        const v = editValue.mosaic.trim()
        if (String(f.tags.mosaic ?? '') !== v) {
          f.tags.mosaic = v as any
          changed = true
        }
        editingMosaicFlag.value = null
      }
      if (changed) {
        f.initialized = true
        await updateFolderModel(f)
      }
    }


    // Update -Tags
    // -------------------------------------------------------------------------------------------------------
    const tagInputVisible = reactive<Record<string, Record<string, boolean>>>({})
    const tagInputValues = reactive<Record<string, Record<string, string>>>({})
    const tagInputRefs = reactive<Record<string, Record<string, InstanceType<typeof ElInput> | null>>>({})

    function ensureTagState(folderId: string, group: string) {
      if (!tagInputVisible[folderId]) tagInputVisible[folderId] = {}
      if (!tagInputValues[folderId]) tagInputValues[folderId] = {}
      if (!tagInputRefs[folderId]) tagInputRefs[folderId] = {}
      if (tagInputValues[folderId][group] === undefined) tagInputValues[folderId][group] = ''
    }

    function isTagInputVisible(f: FolderModel, group: 'auth' | 'name' | 'custom' | 'others'): boolean {
      return !!tagInputVisible[f.id]?.[group]
    }

    function setTagInputRef(folderId: string, group: string) {
      return (el: InstanceType<typeof ElInput> | null) => {
        ensureTagState(folderId, group)
        tagInputRefs[folderId][group] = el
        if (el) {
          nextTick(() => {
            if (typeof el.focus === 'function') el.focus()
            else {
              const raw: HTMLInputElement | null = (el as any).$el?.querySelector('input') || null
              raw?.focus()
            }
          })
        }
      }
    }

    function showTagInput(f: FolderModel, group: 'auth' | 'name' | 'custom' | 'others') {
      ensureTagState(f.id, group)
      tagInputVisible[f.id][group] = true
    }

    async function handleTagInputConfirm(f: FolderModel, group: 'auth' | 'name' | 'custom' | 'others') {
      ensureTagState(f.id, group)
      const v = tagInputValues[f.id][group].trim()
      tagInputVisible[f.id][group] = false
      if (!v) {
        tagInputValues[f.id][group] = ''
        return
      }
      if (!f.tags[group].includes(v)) {
        f.tags[group].push(v)
        f.initialized = true
        await updateFolderModel(f)
      }
      tagInputValues[f.id][group] = ''
    }

    async function removeTag(f: FolderModel, group: 'auth' | 'name' | 'custom' | 'others', index: number) {
      f.tags[group].splice(index, 1)
      await updateFolderModel(f)
    }

    // Folder Delete
    // -------------------------------------------------------------------------------------------------------
    async function deleteFolder(f: FolderModel) {
      try {
        await deleteFolderModel(f)
        delete store.mangaIndex.folders[f.id]
      } catch (e) {
        console.error('Delete failed', e)
      }
    }
    // Folder Star
    // -------------------------------------------------------------------------------------------------------
    async function starFolder(f: FolderModel) {
      try {
        await starFolderModel(f)
        delete store.mangaIndex.folders[f.id]
      } catch (e) {
        console.error('Star failed', e)
      }
    }
    // Life Cycle
    // -------------------------------------------------------------------------------------------------------
    onMounted(async () => {
      await store.loadIndex()
      hotTags.value = await fetchHotTags().catch(() => [])
      fetchFilesForCurrentPage()
      window.addEventListener('scroll', onScroll)
    })
    onBeforeUnmount(() => {
      window.removeEventListener('scroll', onScroll)
    })

    return {
      // Search with Hot Tags
      searchTokens,
      searchInput,
      hotTags,
      addSearchToken,
      removeSearchToken,
      addHotTag,
      // Update - Basic
      startEdit,
      commitEdit,
      editingNameFlag,
      editingCategoryMainFlag,
      editingCategorySubFlag,
      editingMosaicFlag,
      editValue,
      setActiveInput,
      // Update — Tag
      isTagInputVisible,
      showTagInput,
      handleTagInputConfirm,
      setTagInputRef,
      removeTag,
      tagInputValues,
      // unknown
      pagedFolders,
      canLoadMore,
      previewImages,
      openModal,
      closeModal,
      dialogVisible,
      dialogFolder,
      dialogFiles,
      isImage,
      isVideo,
      // Switch Initialized
      showUninitializedOnly,
      sizeSortEnabled,
      // Folder Delete
      deleteFolder,
      Delete,
      // Star Folder
      starFolder,
      Star,
    }
  }
})
