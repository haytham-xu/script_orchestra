import { defineComponent, ref, onMounted, onBeforeUnmount, computed, watch, reactive, nextTick, toRefs } from 'vue'
import { useMangaIndexStore } from '@/manga_viwer/service/Store'
import { useRouter } from 'vue-router'
import type { FolderModel } from '../service/Model'
import { ElInput, ElTag, ElSwitch, ElRadio, ElRadioGroup, ElLoading, ElMessage, ElMessageBox } from 'element-plus'
import { Delete, RefreshLeft, Folder } from '@element-plus/icons-vue'
import { openFolder, refreshIndex } from '@/manga_viwer/service/Service'
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
    const classifierModeEnabled = ref(true)

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

      // Validate that both category_main and category_sub are selected
      if (field === 'category_main' || field === 'category_sub') {
        if (!f.tags.category_main || !f.tags.category_sub) {
          ElMessage.error('Please select both Main Category and Sub Category')
          return
        }
      }

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
      const loading = ElLoading.service({ lock: true, text: 'Applying...', background: 'rgba(0,0,0,0.4)' })
      await store.applyChanges(classifierModeEnabled.value)

      // Apply deletions if any
      if (store.deleteIdSet.size > 0) {
        try {
          await ElMessageBox.confirm(
            `确定要删除 ${store.deleteIdSet.size} 个文件夹吗？此操作不可恢复！`,
            '确认删除',
            { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
          )
          await store.applyDeletion()
          ElMessage.success(`已删除 ${store.deleteIdSet.size} 个文件夹`)
        } catch {
          ElMessage.info('已取消删除操作')
        }
      }

      loading.close()
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

    // Life Cycle
    // -------------------------------------------------------------------------------------------------------
    onMounted(async () => {
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
      classifierModeEnabled,
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
