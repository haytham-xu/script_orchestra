import { defineComponent, ref, onMounted, onBeforeUnmount, computed, watch, reactive, nextTick, toRefs } from 'vue'
import { useMangaIndexStore } from '@/manga_viwer/service/Store'
import { useRouter } from 'vue-router'
import type { FolderModel } from '../service/Model'
import { ElInput, ElTag, ElSwitch, ElRadio, ElRadioGroup, ElLoading, ElMessage, ElMessageBox } from 'element-plus'
import { Delete, RefreshLeft, Folder } from '@element-plus/icons-vue'
import { openFolder, refreshIndex, fetchSettings } from '@/manga_viwer/service/Service'
import * as pdfjsLib from 'pdfjs-dist'
// Import worker as URL
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

// Configure PDF.js worker - use local worker file
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker

export default defineComponent({
  name: 'MangaViewerView',
  components: { ElInput, ElTag, ElSwitch, ElRadio, ElRadioGroup },
  setup() {
    console.log('[MangaViewer] Component setup started')

    //  Basic
    // -------------------------------------------------------------------------------------------------------
    const store = useMangaIndexStore()
    const router = useRouter()
    const { hotTags, isRandomMode, orSearchKeywords } = toRefs(store)

    // Navigation
    // -------------------------------------------------------------------------------------------------------
    function goToRandom() {
      router.push('/manga-viewer/random')
    }

    function goToSettings() {
      router.push('/manga-viewer/settings')
    }

    function goToBatch() {
      router.push('/manga-viewer/batch')
    }

    function goToImport() {
      router.push('/manga-viewer/import')
    }

    // Random功能 (removed, now in separate view)
    // -------------------------------------------------------------------------------------------------------

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
    const showUninitializedOnly = ref(false)
    const sizeSortEnabled = ref(false)
    const nameSortEnabled = ref(true)

    function addSearchToken() {
      const v = searchInput.value.trim()
      if (!v) return
      if (!searchTokens.value.includes(v)) searchTokens.value.push(v)
      store.recordHotTag(v)
      searchInput.value = ''
    }
    function removeSearchToken(idx: number) {
      searchTokens.value.splice(idx, 1)
    }
    function addHotTag(tag: string) {
      store.recordHotTag(tag)
      if (!searchTokens.value.includes(tag)) searchTokens.value.push(tag)
    }
    function addSearchTokenFromImport(token: string) {
      if (!searchTokens.value.includes(token)) {
        searchTokens.value.push(token)
        store.recordHotTag(token)
      }
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
      if (nameSortEnabled.value) {
        base = [...base].sort((a, b) => a.name.localeCompare(b.name))
      } else if (sizeSortEnabled.value) {
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
    watch(nameSortEnabled, () => {
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
      for (const f of pagedFolders.value) {
        if (loadingToken.value !== token) return
        if (!f.files || f.files.length === 0) {
          await store.fetchFolderFiles(f)
        }
        // Pre-render PDF first pages for preview
        const pdfs = (f.files || []).filter(isPdf)
        for (const pdf of pdfs) {
          if (loadingToken.value !== token) return
          await renderPdfFirstPage(pdf)
        }
      }
    }

    watch(filteredFolders, () => {
      currentPage.value = 1
      fetchFilesForCurrentPage()
    })

    // Preivew Imag/Video
    // -------------------------------------------------------------------------------------------------------
    function previewImages(f: FolderModel): string[] {
      const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']
      const list: string[] = (f.files || []).filter((p: string) => {
        const e = p.split('.').pop()?.toLowerCase() || ''
        return imageExts.includes(e) || e === 'pdf'
      })
      return list.slice(0, 3)
    }

    function getPreviewSrc(url: string): string {
      if (isPdf(url)) {
        return pdfFirstPages.value[url] || ''
      }
      return url
    }

    const dialogVisible = ref(false)
    const dialogFolder = ref<FolderModel | null>(null)
    const dialogFiles = computed(() => dialogFolder.value?.files || [])
    const pdfPages = ref<Record<string, string[]>>({})
    const pdfFirstPages = ref<Record<string, string>>({})

    async function renderPdfFirstPage(pdfUrl: string) {
      if (pdfFirstPages.value[pdfUrl]) {
        return pdfFirstPages.value[pdfUrl]
      }

      try {
        const loadingTask = pdfjsLib.getDocument(pdfUrl)
        const pdf = await loadingTask.promise
        const page = await pdf.getPage(1)
        const viewport = page.getViewport({ scale: 1.5 })

        const canvas = document.createElement('canvas')
        const context = canvas.getContext('2d')
        if (!context) return ''

        canvas.height = viewport.height
        canvas.width = viewport.width

        await page.render({
          canvasContext: context,
          viewport: viewport
        }).promise

        const dataUrl = canvas.toDataURL()
        pdfFirstPages.value[pdfUrl] = dataUrl
        return dataUrl
      } catch (e) {
        console.error('Failed to render PDF first page:', pdfUrl, e)
        return ''
      }
    }

    async function renderPdfPages(pdfUrl: string) {
      if (pdfPages.value[pdfUrl]) {
        console.log(`PDF already rendered: ${pdfUrl}, pages: ${pdfPages.value[pdfUrl].length}`)
        return pdfPages.value[pdfUrl]
      }

      try {
        console.log(`Starting to render PDF: ${pdfUrl}`)
        const loadingTask = pdfjsLib.getDocument(pdfUrl)
        const pdf = await loadingTask.promise
        console.log(`PDF loaded, total pages: ${pdf.numPages}`)

        const pages: string[] = []

        for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
          console.log(`Rendering page ${pageNum}/${pdf.numPages}`)
          const page = await pdf.getPage(pageNum)
          const viewport = page.getViewport({ scale: 1.5 })

          const canvas = document.createElement('canvas')
          const context = canvas.getContext('2d')
          if (!context) {
            console.error(`Failed to get canvas context for page ${pageNum}`)
            continue
          }

          canvas.height = viewport.height
          canvas.width = viewport.width

          await page.render({
            canvasContext: context,
            viewport: viewport
          }).promise

          const dataUrl = canvas.toDataURL()
          pages.push(dataUrl)
          console.log(`Page ${pageNum} rendered, data URL length: ${dataUrl.length}`)
        }

        console.log(`All ${pages.length} pages rendered for ${pdfUrl}`)
        pdfPages.value[pdfUrl] = pages
        return pages
      } catch (e) {
        console.error('Failed to render PDF:', pdfUrl, e)
        return []
      }
    }

    function openModal(f: FolderModel) {
      dialogFolder.value = f
      dialogVisible.value = true
      if (!f.files || f.files.length === 0) {
        store.fetchFolderFiles(f)
      }
      // Pre-render PDFs
      nextTick(async () => {
        const pdfs = (f.files || []).filter(isPdf)
        for (const pdf of pdfs) {
          await renderPdfPages(pdf)
        }
      })
    }
    function closeModal() {
      dialogVisible.value = false
      dialogFolder.value = null
    }

    function isImage(p: string) { return /\.(jpe?g|png|gif|webp|bmp|tiff)$/i.test(p) }
    function isVideo(p: string) { return /\.(mp4|webm|mov|mkv|avi|flv)$/i.test(p) }
    function isPdf(p: string) { return /\.pdf$/i.test(p) }

    // Code for Update
    // -------------------------------------------------------------------------------------------------------

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

    const editingNameFlag = ref<string | null>(null)
    const editValue = reactive({name: ''})
    function startNameEdit(f: FolderModel) {
      editingNameFlag.value = f.id
      editValue.name = f.name
    }

    async function commitNameAndRadioEdit(field: 'name' | 'category_main' | 'category_sub' | 'mosaic', f: FolderModel) {
      if (field === 'name') {
        editingNameFlag.value = null
        if (f.name !== editValue.name) {
          f.name = editValue.name.trim()
          f.initialized = true
          store.addChangeId(f.id)
        }
        return
      }

      // Don't validate here - just mark as changed
      // Validation will happen when Apply is clicked
      f.initialized = true
      store.addChangeId(f.id)
      if (field === 'category_main' || field === 'category_sub') {
        store.addMoveId(f.id)
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

    function parseAuthName(raw: string): { auth: string; name: string } {
      const s = (raw || '').trim()
      const m = s.match(/^(\[(?<b>[^\]]+)\]|\((?<p>[^)]+)\))(?<rest>.*)$/)
      if (!m) {
        const nm = s.match(/^([^[(]+)/)
        return { auth: '', name: (nm ? nm[1] : s).trim() }
      }
      const auth = (m.groups?.b || m.groups?.p || '').trim()
      const rest = (m.groups?.rest || '')
      const nm = rest.match(/^([^[(]+)/)
      const name = (nm ? nm[1] : '').trim()
      return { auth, name }
    }

    function showTagInput(f: FolderModel, group: 'auth' | 'name' | 'custom' | 'others') {
      ensureTagState(f.id, group)
      tagInputVisible[f.id][group] = true
      const { auth, name } = parseAuthName(f.name)
      if (group === 'auth') {
        tagInputValues[f.id].auth = auth
      }
      if (group === 'name') {
        tagInputValues[f.id].name = name
      }
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
        store.addChangeId(f.id)
      }
      tagInputValues[f.id][group] = ''
    }

    async function removeTag(f: FolderModel, group: 'auth' | 'name' | 'custom' | 'others', index: number) {
      f.tags[group].splice(index, 1)
      store.addChangeId(f.id)
    }


    // Appying
    // -------------------------------------------------------------------------------------------------------
    async function applyChanges() {
      // Validate all changed folders before applying
      for (const folderId of store.changeIdList) {
        const folder = store.mangaIndex.folders[folderId]
        if (folder) {
          // If category_main or category_sub is set, both must be set
          const hasMainCat = folder.tags.category_main && folder.tags.category_main.trim()
          const hasSubCat = folder.tags.category_sub && folder.tags.category_sub.trim()
          if ((hasMainCat || hasSubCat) && !(hasMainCat && hasSubCat)) {
            ElMessage.error(`Folder "${folder.name}": Both Main Category and Sub Category must be selected together`)
            return
          }
        }
      }

      const loading = ElLoading.service({ lock: true, text: 'Applying...', background: 'rgba(0,0,0,0.4)' })

      // Apply deletions first if any (no confirmation dialog - marking for deletion is already a confirmation)
      if (store.deleteIdSet.size > 0) {
        await store.applyDeletion()
        ElMessage.success(`已删除 ${store.deleteIdSet.size} 个文件夹`)
      }

      // Apply other changes (classifier_mode is now always false)
      await store.applyChanges(false)

      // Reload index to get updated file paths and folders
      await store.loadIndex()
      currentPage.value = 1
      fetchFilesForCurrentPage()

      loading.close()
      ElMessage.success('Changes applied successfully')
    }

    // Deletion
    // -------------------------------------------------------------------------------------------------------
    function markForDeletion(folderId: string) {
      store.markForDeletion(folderId)
    }

    function unmarkForDeletion(folderId: string) {
      store.unmarkForDeletion(folderId)
    }

    // Open Folder
    // -------------------------------------------------------------------------------------------------------
    async function handleOpenFolder(folderId: string) {
      try {
        await openFolder(folderId)
        // Silently succeed - folder is opened in background
      } catch (e) {
        // Silently ignore errors - the folder is likely already opened
        // The backend subprocess opens the folder but may return before completion
        console.debug('Open folder request sent:', folderId)
      }
    }

    // Refresh Index
    // -------------------------------------------------------------------------------------------------------
    const refreshLoading = ref(false)
    async function handleRefreshIndex() {
      refreshLoading.value = true
      try {
        await refreshIndex()
        ElMessage.success('索引刷新成功')
        // Reload the index after refresh
        await store.loadIndex()
        currentPage.value = 1
        fetchFilesForCurrentPage()
      } catch (e) {
        ElMessage.error('索引刷新失败')
        console.error('Failed to refresh index:', e)
      } finally {
        refreshLoading.value = false
      }
    }

    // Import Sidebar
    // -------------------------------------------------------------------------------------------------------
    // Removed - now a separate page at /manga-viewer/import

    // Life Cycle
    // -------------------------------------------------------------------------------------------------------
    onMounted(async () => {
      // Load settings to get default values
      try {
        const settingsData = await fetchSettings()
        if (settingsData && settingsData.display) {
          showUninitializedOnly.value = settingsData.display.show_uninitialized_only ?? false
          sizeSortEnabled.value = settingsData.display.size_sort_enabled ?? false
          nameSortEnabled.value = settingsData.display.name_sort_enabled ?? true
        }
      } catch (e) {
        console.warn('Failed to load settings, using default values:', e)
      }

      await store.loadIndex()
      fetchFilesForCurrentPage()
      window.addEventListener('scroll', onScroll)
    })
    onBeforeUnmount(() => {
      window.removeEventListener('scroll', onScroll)
    })

    return {
      // Navigation
      goToRandom,
      goToSettings,
      goToBatch,
      goToImport,
      // Search with Hot Tags
      searchTokens,
      searchInput,
      hotTags,
      addSearchToken,
      removeSearchToken,
      addHotTag,
      // Update - Basic
      startEdit: startNameEdit,
      commitEdit: commitNameAndRadioEdit,
      editingNameFlag,
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
      getPreviewSrc,
      openModal,
      closeModal,
      dialogVisible,
      dialogFolder,
      dialogFiles,
      isImage,
      isVideo,
      isPdf,
      pdfPages,
      pdfFirstPages,
      // Switch Initialized
      showUninitializedOnly,
      sizeSortEnabled,
      nameSortEnabled,
      // Applying
      applyChanges,
      // Deletion
      markForDeletion,
      unmarkForDeletion,
      // Open Folder
      handleOpenFolder,
      // Refresh Index
      handleRefreshIndex,
      refreshLoading,
      // Icons
      Delete,
      RefreshLeft,
      Folder,
      // Store (for checking deleteIdSet)
      store,
    }
  }
})
