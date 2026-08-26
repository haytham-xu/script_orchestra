/**
 * @deprecated Manga Viewer Import page.
 *
 * Hidden from the UI (the entry button in MangaViewerView is commented out and
 * the route is marked deprecated). Kept intact for now — do not delete without
 * confirmation.
 */
import { defineComponent, ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useMangaIndexStore } from '@/manga_viwer/service/Store'
import { BACKEND_BASE_URL } from '@/basic/Constants'
import * as pdfjsLib from 'pdfjs-dist'
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

// Configure PDF.js worker
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker

const MANGA_VIEWER_BASE_URL = `${BACKEND_BASE_URL}/manga-viewer`

export default defineComponent({
  name: 'MangaImportView',
  setup() {
    const router = useRouter()
    const store = useMangaIndexStore()

    // ===== LEFT PANEL: Full-screen display =====

    // Scan state
    const scanPath = ref('')
    const scanning = ref(false)
    const folders = ref<any[]>([])
    const currentIndex = ref(0)
    const importing = ref(false)
    const deleting = ref(false)

    // Form data
    const formData = ref({
      name: '',
      auth: [] as string[],
      name_tags: [] as string[],
      custom: [] as string[],
      others: [] as string[],
      category_main: '',
      category_sub: '',
      mosaic: ''
    })

    // Categories from settings
    const categoryMainOptions = ref<Array<{id: string, label?: string, target_folder?: string}>>([])
    const categorySubOptions = ref<Array<{id: string, label?: string}>>([])

    // Root path from settings (for relative path calculation)
    const rootPath = ref('')

    // Tag input states
    const showAuthInput = ref(false)
    const showNameInput = ref(false)
    const showCustomInput = ref(false)
    const showOthersInput = ref(false)
    const authInput = ref('')
    const nameInput = ref('')
    const customInput = ref('')
    const othersInput = ref('')

    // Computed
    const currentFolder = computed(() => {
      if (folders.value.length === 0) return null
      return folders.value[currentIndex.value]
    })

    const nameParts = computed(() => {
      if (!currentFolder.value) return []
      const name = currentFolder.value.name
      const parts = name.split(/[\[\]【】()]+/).filter((p: string) => p.trim())
      return parts
    })

    const currentFolderImages = computed(() => {
      if (!currentFolder.value || !currentFolder.value.files) return []
      // Convert file paths to full URLs
      return currentFolder.value.files.map((file: string) =>
        `${MANGA_VIEWER_BASE_URL}/file/${encodeURIComponent(file)}`
      )
    })

    // PDF handling
    const pdfPages = ref<Record<string, string[]>>({})

    function isImage(path: string) { return /\.(jpe?g|png|gif|webp|bmp|tiff)$/i.test(path) }
    function isPdf(path: string) { return /\.pdf$/i.test(path) }
    function isVideo(path: string) { return /\.(mp4|webm|mov|mkv|avi|flv)$/i.test(path) }

    async function renderPdfPages(pdfUrl: string) {
      if (pdfPages.value[pdfUrl]) {
        return pdfPages.value[pdfUrl]
      }

      try {
        const pdf = await pdfjsLib.getDocument(pdfUrl).promise
        const pages: string[] = []

        for (let i = 1; i <= pdf.numPages; i++) {
          const page = await pdf.getPage(i)
          const viewport = page.getViewport({ scale: 1.5 })
          const canvas = document.createElement('canvas')
          const context = canvas.getContext('2d')!
          canvas.width = viewport.width
          canvas.height = viewport.height

          await page.render({
            canvasContext: context,
            viewport: viewport
          } as any).promise

          pages.push(canvas.toDataURL())
        }

        pdfPages.value[pdfUrl] = pages
        return pages
      } catch (e) {
        console.error('Failed to render PDF pages:', pdfUrl, e)
        return []
      }
    }

    const currentFolderImagesWithPdf = computed(() => {
      const files = currentFolder.value?.files || []
      const result: { url: string; type: 'image' | 'pdf' | 'video'; pdfPages?: string[] }[] = []

      for (const file of files) {
        const url = `${MANGA_VIEWER_BASE_URL}/file/${encodeURIComponent(file)}`

        if (isImage(file)) {
          result.push({ url, type: 'image' })
        } else if (isPdf(file)) {
          const pages = pdfPages.value[url] || []
          result.push({ url, type: 'pdf', pdfPages: pages })
        } else if (isVideo(file)) {
          result.push({ url, type: 'video' })
        }
      }

      return result
    })

    // Watch current folder change
    watch(currentFolder, (newFolder) => {
      if (newFolder) {
        formData.value.name = newFolder.name
        formData.value.auth = newFolder.auth || []
        formData.value.name_tags = newFolder.name_tags || []
        formData.value.custom = newFolder.custom || []
        formData.value.others = newFolder.others || []
        formData.value.category_main = newFolder.category_main || ''
        formData.value.category_sub = newFolder.category_sub || ''
        formData.value.mosaic = newFolder.mosaic || ''
        // Scroll to top
        window.scrollTo(0, 0)

        // Render PDFs in background (non-blocking)
        nextTick(async () => {
          const files = newFolder.files || []
          for (const file of files) {
            if (isPdf(file)) {
              const url = `${MANGA_VIEWER_BASE_URL}/file/${encodeURIComponent(file)}`
              // Render PDFs asynchronously without blocking
              renderPdfPages(url).catch(err => console.error('Failed to render PDF:', err))
            }
          }
        })
      }
    })

    // Methods - Left Panel
    async function handleScan() {
      if (!scanPath.value.trim()) {
        ElMessage.warning('Please enter a path to scan')
        return
      }

      scanning.value = true
      try {
        const res = await axios.post(`${MANGA_VIEWER_BASE_URL}/import/scan`, {
          path: scanPath.value
        })
        folders.value = res.data.folders
        currentIndex.value = 0
        ElMessage.success(`Found ${res.data.count} folders`)
      } catch (e: any) {
        ElMessage.error(e.response?.data?.error || 'Failed to scan path')
      } finally {
        scanning.value = false
      }
    }

    function prevFolder() {
      if (currentIndex.value > 0) {
        currentIndex.value--
        // Clear right search and middle preview
        clearRightSearch()
        middleFolder.value = null
        middleFiles.value = []
      } else {
        ElMessage.info('This is the first folder')
      }
    }

    function nextFolder() {
      if (currentIndex.value < folders.value.length - 1) {
        currentIndex.value++
        // Clear right search and middle preview
        clearRightSearch()
        middleFolder.value = null
        middleFiles.value = []
      } else {
        ElMessage.info('This is the last folder')
      }
    }

    function addToRightSearch(part: string) {
      const trimmed = part.trim()
      if (trimmed && !rightSearchTokens.value.includes(trimmed)) {
        rightSearchTokens.value.push(trimmed)
        store.recordHotTag(trimmed)
        ElMessage.success(`Added "${trimmed}" to search`)

        // Reset display count when search changes
        rightDisplayCount.value = rightPageSize

        // Load right panel data if not loaded yet
        if (rightAllFolders.value.length === 0) {
          loadRightPanel()
        }
      }
    }

    function addAuth() {
      if (authInput.value.trim() && !formData.value.auth.includes(authInput.value.trim())) {
        formData.value.auth.push(authInput.value.trim())
      }
      authInput.value = ''
      showAuthInput.value = false
    }

    function addName() {
      if (nameInput.value.trim() && !formData.value.name_tags.includes(nameInput.value.trim())) {
        formData.value.name_tags.push(nameInput.value.trim())
      }
      nameInput.value = ''
      showNameInput.value = false
    }

    function addCustom() {
      if (customInput.value.trim() && !formData.value.custom.includes(customInput.value.trim())) {
        formData.value.custom.push(customInput.value.trim())
      }
      customInput.value = ''
      showCustomInput.value = false
    }

    function addOthers() {
      if (othersInput.value.trim() && !formData.value.others.includes(othersInput.value.trim())) {
        formData.value.others.push(othersInput.value.trim())
      }
      othersInput.value = ''
      showOthersInput.value = false
    }

    async function handleImport() {
      if (!currentFolder.value) return

      if (!formData.value.category_main || !formData.value.category_sub) {
        ElMessage.error('Please select both category main and sub')
        return
      }

      importing.value = true
      try {
        const importData = {
          sourcePath: currentFolder.value.path,
          folderData: {
            name: formData.value.name,
            auth: formData.value.auth,
            name_tags: formData.value.name_tags,
            custom: formData.value.custom,
            others: formData.value.others,
            category_main: formData.value.category_main,
            category_sub: formData.value.category_sub,
            mosaic: formData.value.mosaic,
            size: currentFolder.value.size,
            number: currentFolder.value.number
          }
        }

        // Log import operation (frontend)
        console.log('📦 [Import] Starting import operation:', {
          folder: currentFolder.value.name,
          from: currentFolder.value.path,
          category: `${importData.folderData.category_main}_${importData.folderData.category_sub}`,
          size: `${Math.round(currentFolder.value.size / 1024 / 1024)} MB`,
          files: currentFolder.value.number,
          tags: {
            auth: importData.folderData.auth,
            name: importData.folderData.name_tags,
            custom: importData.folderData.custom,
            mosaic: importData.folderData.mosaic
          }
        })

        const response = await axios.post(`${MANGA_VIEWER_BASE_URL}/import/move`, importData)

        // Log success
        console.log('✅ [Import] Success:', {
          folder: currentFolder.value.name,
          to: response.data.targetPath,
          folderId: response.data.folderId
        })

        ElMessage.success('Folder imported successfully')

        // Remove current folder from list
        folders.value.splice(currentIndex.value, 1)

        // Clear right search and middle preview
        clearRightSearch()
        middleFolder.value = null
        middleFiles.value = []

        // Refresh right panel (only if user has searched)
        if (rightSearchTokens.value.length > 0) {
          await loadRightPanel()
        }

        // Auto move to next folder (which is now at the same index)
        if (folders.value.length > 0) {
          // If still at valid index, trigger reload
          if (currentIndex.value < folders.value.length) {
            // Force trigger watch by temporarily changing index
            const tempIndex = currentIndex.value
            currentIndex.value = -1
            await nextTick()
            currentIndex.value = tempIndex
          } else {
            // No more folders after this one
            currentIndex.value = folders.value.length - 1
          }
        } else {
          ElMessage.info('All folders processed!')
          currentIndex.value = -1
        }
      } catch (e: any) {
        console.error('❌ [Import] Failed:', {
          folder: currentFolder.value.name,
          error: e.response?.data?.error || e.message
        })
        ElMessage.error(e.response?.data?.error || 'Failed to import folder')
      } finally {
        importing.value = false
      }
    }

    async function handleDelete() {
      if (!currentFolder.value) return

      // Confirm deletion
      const confirmed = confirm(`Are you sure you want to move folder to delete_paths: ${currentFolder.value.name}?\n\n(This is a soft delete - folder will be moved to delete_paths, not permanently deleted)`)
      if (!confirmed) return

      deleting.value = true
      try {
        // Log delete operation (frontend)
        console.log('🗑️  [Delete] Starting soft delete operation:', {
          folder: currentFolder.value.name,
          from: currentFolder.value.path,
          size: `${Math.round(currentFolder.value.size / 1024 / 1024)} MB`,
          files: currentFolder.value.number
        })

        const response = await axios.post(`${MANGA_VIEWER_BASE_URL}/import/delete`, {
          sourcePath: currentFolder.value.path
        })

        // Log success
        console.log('✅ [Delete] Success:', {
          folder: currentFolder.value.name,
          movedTo: response.data.deletePath
        })

        ElMessage.success('Folder moved to delete_paths successfully')

        // Remove current folder from list
        folders.value.splice(currentIndex.value, 1)

        // Clear right search and middle preview
        clearRightSearch()
        middleFolder.value = null
        middleFiles.value = []

        // Auto move to next folder (same logic as import)
        if (folders.value.length > 0) {
          if (currentIndex.value < folders.value.length) {
            const tempIndex = currentIndex.value
            currentIndex.value = -1
            await nextTick()
            currentIndex.value = tempIndex
          } else {
            currentIndex.value = folders.value.length - 1
          }
        } else {
          ElMessage.info('All folders processed!')
          currentIndex.value = -1
        }
      } catch (e: any) {
        console.error('❌ [Delete] Failed:', {
          folder: currentFolder.value.name,
          error: e.response?.data?.error || e.message
        })
        ElMessage.error(e.response?.data?.error || 'Failed to delete folder')
      } finally {
        deleting.value = false
      }
    }

    function goBack() {
      router.push('/manga-viewer')
    }

    async function openCurrentFolder() {
      if (!currentFolder.value || !currentFolder.value.path) {
        ElMessage.warning('No folder selected')
        return
      }

      try {
        await axios.post(`${MANGA_VIEWER_BASE_URL}/open-folder`, {
          folderPath: currentFolder.value.path
        })
        ElMessage.success('Folder opened in file manager')
      } catch (e: any) {
        console.error('Failed to open folder:', e)
        ElMessage.error(e.response?.data?.error || 'Failed to open folder')
      }
    }

    // Keyboard shortcuts
    function handleKeyDown(event: KeyboardEvent) {
      if (!currentFolder.value) return

      // Don't handle keyboard shortcuts when user is typing in an input field
      const target = event.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
        return
      }

      switch (event.code) {
        case 'ArrowRight':
        case 'Space':
          event.preventDefault()
          nextFolder()
          break
        case 'Backspace':
          event.preventDefault()
          // Quick delete - set to delete category
          formData.value.category_main = 'del'
          handleImport()
          break
      }
    }

    // ===== RIGHT PANEL: Manga Viewer =====

    const rightSearchInput = ref('')
    const rightSearchTokens = ref<string[]>([])
    const loadingRight = ref(false)
    const rightAllFolders = ref<any[]>([])  // All folders from index
    const rightPdfPreviews = ref<Record<string, string>>({}) // Store first page of PDFs for preview

    // Display control (for infinite scroll)
    const rightDisplayCount = ref(20)
    const rightPageSize = 20

    async function renderPdfFirstPage(pdfUrl: string): Promise<string | null> {
      if (rightPdfPreviews.value[pdfUrl]) {
        return rightPdfPreviews.value[pdfUrl]
      }

      try {
        const pdf = await pdfjsLib.getDocument(pdfUrl).promise
        const page = await pdf.getPage(1)

        // Use smaller scale for thumbnail preview (0.5 instead of 1.5)
        const viewport = page.getViewport({ scale: 0.5 })
        const canvas = document.createElement('canvas')
        const context = canvas.getContext('2d')!
        canvas.width = viewport.width
        canvas.height = viewport.height

        await page.render({
          canvasContext: context,
          viewport: viewport
        }).promise

        const dataUrl = canvas.toDataURL()
        rightPdfPreviews.value[pdfUrl] = dataUrl
        return dataUrl
      } catch (e) {
        console.error('Failed to render PDF first page:', pdfUrl, e)
        return null
      }
    }

    // ===== MIDDLE PANEL: Selected folder for comparison =====
    const middleFolder = ref<any>(null)
    const middleFiles = ref<any[]>([])
    const middlePdfPages = ref<Record<string, string[]>>({})

    async function renderMiddlePdfPages(pdfUrl: string) {
      if (middlePdfPages.value[pdfUrl]) {
        return middlePdfPages.value[pdfUrl]
      }

      try {
        const pdf = await pdfjsLib.getDocument(pdfUrl).promise
        const pages: string[] = []

        for (let i = 1; i <= pdf.numPages; i++) {
          const page = await pdf.getPage(i)
          const viewport = page.getViewport({ scale: 1.5 })
          const canvas = document.createElement('canvas')
          const context = canvas.getContext('2d')!
          canvas.width = viewport.width
          canvas.height = viewport.height

          await page.render({
            canvasContext: context,
            viewport: viewport
          } as any).promise

          pages.push(canvas.toDataURL())
        }

        middlePdfPages.value[pdfUrl] = pages
        return pages
      } catch (e) {
        console.error('Failed to render PDF pages:', pdfUrl, e)
        return []
      }
    }

    const middleFilesWithPdf = computed(() => {
      const result: { url: string; type: 'image' | 'pdf' | 'video'; pdfPages?: string[] }[] = []

      for (const file of middleFiles.value) {
        if (isImage(file)) {
          result.push({ url: file, type: 'image' })
        } else if (isPdf(file)) {
          const pages = middlePdfPages.value[file] || []
          result.push({ url: file, type: 'pdf', pdfPages: pages })
        } else if (isVideo(file)) {
          result.push({ url: file, type: 'video' })
        }
      }

      return result
    })

    function addRightSearchToken() {
      const trimmed = rightSearchInput.value.trim()
      if (trimmed && !rightSearchTokens.value.includes(trimmed)) {
        rightSearchTokens.value.push(trimmed)
        store.recordHotTag(trimmed)
        rightSearchInput.value = ''

        // Reset display count when search changes
        rightDisplayCount.value = rightPageSize

        // Load right panel data if not loaded yet
        if (rightAllFolders.value.length === 0) {
          loadRightPanel()
        }
      }
    }

    // Filter folders based on search tokens (frontend filtering)
    const rightFilteredFolders = computed(() => {
      // Don't show anything by default - user must search first
      if (rightSearchTokens.value.length === 0) {
        return []
      }

      const tokens = rightSearchTokens.value.map(t => t.toLowerCase())
      return rightAllFolders.value.filter((folder) => {
        const searchableText = [
          folder.name,
          ...(folder.tags?.auth || []),
          ...(folder.tags?.name || []),
          ...(folder.tags?.custom || []),
          ...(folder.tags?.others || []),
          folder.tags?.category_main,
          folder.tags?.category_sub
        ].join(' ').toLowerCase()

        return tokens.every((token) => searchableText.includes(token))
      })
    })

    // Display folders with lazy loading (only show first N folders)
    const rightDisplayedFolders = computed(() =>
      rightFilteredFolders.value.slice(0, rightDisplayCount.value)
    )

    const rightCanLoadMore = computed(() =>
      rightDisplayedFolders.value.length < rightFilteredFolders.value.length
    )

    function rightPreviewImages(folder: any): Array<{url: string; type: 'image' | 'pdf' | 'video'}> {
      if (!folder.files || folder.files.length === 0) {
        return []
      }

      const imageExts = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
      const result: Array<{url: string; type: 'image' | 'pdf' | 'video'}> = []

      // First, collect images
      const images = folder.files.filter((file: string) => {
        const lower = file.toLowerCase()
        return imageExts.some(ext => lower.endsWith(ext))
      })

      for (const img of images) {
        result.push({ url: img, type: 'image' })
        if (result.length >= 3) break
      }

      // If less than 3 images, add PDFs
      if (result.length < 3) {
        const pdfs = folder.files.filter((file: string) => isPdf(file))
        for (const pdf of pdfs) {
          result.push({ url: pdf, type: 'pdf' })
          // Trigger PDF rendering in background (non-blocking)
          renderPdfFirstPage(pdf).catch(err => console.error('Failed to render PDF preview:', err))
          if (result.length >= 3) break
        }
      }

      // If still less than 3, add videos
      if (result.length < 3) {
        const videos = folder.files.filter((file: string) => isVideo(file))
        for (const video of videos) {
          result.push({ url: video, type: 'video' })
          if (result.length >= 3) break
        }
      }

      return result.slice(0, 3)
    }

    async function loadRightPanel() {
      if (loadingRight.value) return

      loadingRight.value = true
      try {
        // Load full index (like manga viewer)
        await store.loadIndex()
        rightAllFolders.value = Object.values(store.mangaIndex.folders)
      } catch (e) {
        ElMessage.error('Failed to load manga viewer data')
        rightAllFolders.value = []
      } finally {
        loadingRight.value = false
      }
    }

    function removeRightSearchToken(index: number) {
      rightSearchTokens.value.splice(index, 1)
      // Reset display count when search changes
      rightDisplayCount.value = rightPageSize
    }

    function clearRightSearch() {
      rightSearchTokens.value = []
      // Reset display count when search changes
      rightDisplayCount.value = rightPageSize
    }

    function loadMoreRight() {
      if (rightCanLoadMore.value) {
        rightDisplayCount.value += rightPageSize
      }
    }

    // Scroll handler for right panel
    function onRightScroll(event: Event) {
      const target = event.target as HTMLElement
      const nearBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 300
      if (nearBottom && rightCanLoadMore.value && !loadingRight.value) {
        loadMoreRight()
      }
    }

    async function selectMiddleFolder(folder: any) {
      middleFolder.value = folder

      try {
        const res = await axios.get(`${MANGA_VIEWER_BASE_URL}/files-url-list`, {
          params: { folderId: folder.id }
        })
        middleFiles.value = res.data

        // Pre-render PDFs
        await nextTick()
        for (const file of middleFiles.value) {
          if (isPdf(file)) {
            await renderMiddlePdfPages(file)
          }
        }
      } catch (e) {
        ElMessage.error('Failed to load folder files')
        middleFiles.value = []
      }
    }

    function refreshRightPanel() {
      loadRightPanel()
    }

    function getRelativePath(fullPath: string): string {
      // Get relative path from root_path to parent folder (exclude folder name)
      // Example: /root/manga/category_folder/main_sub/FolderName -> category_folder/main_sub
      if (!fullPath || !rootPath.value) return ''

      try {
        // Normalize paths for comparison
        const normalizedFull = fullPath.replace(/\\/g, '/').replace(/\/+$/, '')
        const normalizedRoot = rootPath.value.replace(/\\/g, '/').replace(/\/+$/, '')

        // Check if path starts with root_path
        if (normalizedFull.startsWith(normalizedRoot)) {
          // Get relative path from root
          let relativePath = normalizedFull.substring(normalizedRoot.length).replace(/^\//, '')

          // Remove last part (folder name)
          const parts = relativePath.split('/').filter(p => p)
          if (parts.length > 1) {
            // Return all parts except the last one (folder name)
            return parts.slice(0, -1).join('/')
          }
        }

        return ''
      } catch (e) {
        console.error('Failed to parse path:', e)
        return ''
      }
    }

    async function deleteRightFolder(folder: any) {
      if (!folder || !folder.id) return

      // Confirm deletion
      const confirmed = confirm(`Delete folder from index: ${folder.name}?\n\nPath: ${folder.path}\n\n(This will move the folder to delete_paths)`)
      if (!confirmed) return

      try {
        // Log delete operation (frontend)
        console.log('🗑️  [Delete Index] Starting delete operation:', {
          folder: folder.name,
          path: folder.path,
          folderId: folder.id,
          size: `${Math.round(folder.size / 1024 / 1024)} MB`
        })

        // Call backend delete API (same as main viewer delete)
        await axios.post(`${MANGA_VIEWER_BASE_URL}/delete`, {
          folderIds: [folder.id]
        })

        // Log success
        console.log('✅ [Delete Index] Success:', {
          folder: folder.name,
          folderId: folder.id
        })

        ElMessage.success('Folder deleted from index successfully')

        // Refresh right panel to remove deleted folder
        await loadRightPanel()

      } catch (e: any) {
        console.error('❌ [Delete Index] Failed:', {
          folder: folder.name,
          error: e.response?.data?.error || e.message
        })
        ElMessage.error(e.response?.data?.error || 'Failed to delete folder from index')
      }
    }

    async function openRightFolder(folder: any) {
      if (!folder || !folder.id) {
        ElMessage.warning('No folder selected')
        return
      }

      try {
        await axios.post(`${MANGA_VIEWER_BASE_URL}/open-folder`, {
          folderId: folder.id
        })
        ElMessage.success('Folder opened in file manager')
      } catch (e: any) {
        console.error('Failed to open folder:', e)
        ElMessage.error(e.response?.data?.error || 'Failed to open folder')
      }
    }

    // Init & Cleanup
    onMounted(async () => {
      // Don't auto-load right panel - wait for user to search
      // loadRightPanel()
      window.addEventListener('keydown', handleKeyDown)

      // Load settings (import path and categories)
      try {
        const res = await axios.get(`${MANGA_VIEWER_BASE_URL}/settings`)
        if (res.data) {
          // Load categories
          if (res.data.categories) {
            categoryMainOptions.value = res.data.categories.main || []
            categorySubOptions.value = res.data.categories.sub || []
          }

          // Load root path (for relative path calculation)
          if (res.data.paths && res.data.paths.root_path) {
            rootPath.value = res.data.paths.root_path
          }

          // Load import path and auto-scan
          if (res.data.paths && res.data.paths.import_path) {
            scanPath.value = res.data.paths.import_path

            // Auto-scan on load
            if (scanPath.value.trim()) {
              await handleScan()
            }
          } else {
            ElMessage.warning('Import path not configured in settings')
          }
        }
      } catch (e) {
        console.error('Failed to load settings:', e)
        ElMessage.error('Failed to load settings')
      }
    })

    onUnmounted(() => {
      window.removeEventListener('keydown', handleKeyDown)
    })

    return {
      // Left panel
      scanPath,
      scanning,
      folders,
      currentIndex,
      importing,
      deleting,
      formData,
      categoryMainOptions,
      categorySubOptions,
      showAuthInput,
      showNameInput,
      showCustomInput,
      showOthersInput,
      authInput,
      nameInput,
      customInput,
      othersInput,
      currentFolder,
      nameParts,
      currentFolderImages,
      currentFolderImagesWithPdf,
      isImage,
      isPdf,
      isVideo,
      handleScan,
      prevFolder,
      nextFolder,
      addToRightSearch,
      addAuth,
      addName,
      addCustom,
      addOthers,
      handleImport,
      handleDelete,
      goBack,
      openCurrentFolder,
      // Middle panel
      middleFolder,
      middleFilesWithPdf,
      // Right panel
      rightSearchInput,
      rightSearchTokens,
      loadingRight,
      rightDisplayedFolders,
      rightPreviewImages,
      rightPdfPreviews,
      rightCanLoadMore,
      loadRightPanel,
      addRightSearchToken,
      removeRightSearchToken,
      clearRightSearch,
      onRightScroll,
      selectMiddleFolder,
      refreshRightPanel,
      getRelativePath,
      deleteRightFolder,
      openRightFolder
    }
  }
})
