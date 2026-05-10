import { defineComponent, ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { useMangaIndexStore } from '@/manga_viwer/service/Store'
import { useRouter } from 'vue-router'
import type { FolderModel } from '../service/Model'
import { ElMessage, ElLoading } from 'element-plus'

export default defineComponent({
  name: 'RandomView',
  setup() {
    const store = useMangaIndexStore()
    const router = useRouter()

    // State
    const orSearchInput = ref('')
    const pageSize = 10
    const currentPage = ref(1)
    const loadingToken = ref(0)

    // Dialog
    const dialogVisible = ref(false)
    const dialogFolder = ref<FolderModel | null>(null)
    const dialogFiles = computed(() => dialogFolder.value?.files || [])

    // Computed
    const isRandomMode = computed(() => store.isRandomMode)
    const orSearchKeywords = computed(() => store.orSearchKeywords)
    const baseFolderCount = computed(() => store.baseFolderIds.length)
    const folders = computed(() => Object.values(store.mangaIndex.folders))
    const totalFolderCount = computed(() => folders.value.length)

    const pagedFolders = computed(() =>
      folders.value.slice(0, currentPage.value * pageSize)
    )

    const canLoadMore = computed(() =>
      pagedFolders.value.length < folders.value.length
    )

    // Functions
    function goBack() {
      router.push('/manga-viewer')
    }

    async function loadRandomFolders() {
      const loading = ElLoading.service({ lock: true, text: 'Loading random...', background: 'rgba(0,0,0,0.4)' })
      try {
        await store.loadRandomIndex()
        currentPage.value = 1
        fetchFilesForCurrentPage()
        ElMessage.success(`Random loaded ${totalFolderCount.value} folders`)
      } catch (e) {
        console.error('loadRandomFolders failed:', e)
        ElMessage.error('Failed to load random folders')
      } finally {
        loading.close()
      }
    }

    async function addOrSearchKeyword() {
      if (!orSearchInput.value.trim()) {
        ElMessage.warning('Please enter a keyword')
        return
      }

      if (!isRandomMode.value) {
        ElMessage.warning('Please use Random button first')
        return
      }

      const keyword = orSearchInput.value.trim()

      try {
        await store.addOrSearchKeyword(keyword)
        orSearchInput.value = ''
        currentPage.value = 1
        fetchFilesForCurrentPage()

        const addedCount = totalFolderCount.value - baseFolderCount.value
        ElMessage.success(`Total: ${baseFolderCount.value} + ${addedCount} = ${totalFolderCount.value}`)
      } catch (e) {
        console.error('addOrSearchKeyword failed:', e)
        ElMessage.error('Failed to search')
      }
    }

    function clearOrSearch() {
      store.clearOrSearchKeywords()
      currentPage.value = 1
      fetchFilesForCurrentPage()
      ElMessage.info('Cleared all search keywords')
    }

    async function fetchFilesForCurrentPage() {
      const token = ++loadingToken.value
      for (const f of pagedFolders.value) {
        if (loadingToken.value !== token) return
        if (!f.files || f.files.length === 0) {
          await store.fetchFolderFiles(f)
        }
      }
    }

    function previewImages(f: FolderModel): string[] {
      const exts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']
      const list: string[] = (f.files || []).filter((p: string) => {
        const e = p.split('.').pop()?.toLowerCase() || ''
        return exts.includes(e)
      })
      return list.slice(0, 3)
    }

    function openModal(f: FolderModel) {
      dialogFolder.value = f
      dialogVisible.value = true
      if (!f.files || f.files.length === 0) {
        store.fetchFolderFiles(f)
      }
    }

    function isImage(p: string) { return /\.(jpe?g|png|gif|webp|bmp|tiff)$/i.test(p) }
    function isVideo(p: string) { return /\.(mp4|webm|mov|mkv|avi|flv)$/i.test(p) }
    function isPdf(p: string) { return /\.pdf$/i.test(p) }

    function onScroll() {
      const nearBottom = window.innerHeight + window.scrollY >= document.body.offsetHeight - 300
      if (nearBottom && canLoadMore.value) {
        currentPage.value++
        fetchFilesForCurrentPage()
      }
    }

    onMounted(() => {
      window.addEventListener('scroll', onScroll)
      // Auto load random if not in random mode
      if (!isRandomMode.value) {
        loadRandomFolders()
      } else {
        fetchFilesForCurrentPage()
      }
    })

    onBeforeUnmount(() => {
      window.removeEventListener('scroll', onScroll)
    })

    return {
      goBack,
      loadRandomFolders,
      addOrSearchKeyword,
      clearOrSearch,
      orSearchInput,
      isRandomMode,
      orSearchKeywords,
      baseFolderCount,
      totalFolderCount,
      pagedFolders,
      previewImages,
      openModal,
      dialogVisible,
      dialogFolder,
      dialogFiles,
      isImage,
      isVideo,
      isPdf,
    }
  }
})
