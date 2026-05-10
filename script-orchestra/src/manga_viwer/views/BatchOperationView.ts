import { defineComponent, ref, computed, reactive } from 'vue'
import { useMangaIndexStore } from '@/manga_viwer/service/Store'
import { useRouter } from 'vue-router'
import type { FolderModel } from '../service/Model'
import { ElMessage, ElMessageBox, ElLoading } from 'element-plus'

export default defineComponent({
  name: 'BatchOperationView',
  setup() {
    const store = useMangaIndexStore()
    const router = useRouter()

    // Search
    const searchKeyword = ref('')
    const searchResults = ref<FolderModel[]>([])
    const selectedFolders = ref<Set<string>>(new Set())

    // Batch Operations
    const batchOperations = reactive({
      replaceFrom: '',
      replaceTo: '',
      prefix: '',
      suffix: '',
      customTag: ''
    })

    // Computed
    const allSelected = computed(() =>
      searchResults.value.length > 0 && selectedFolders.value.size === searchResults.value.length
    )

    const someSelected = computed(() =>
      selectedFolders.value.size > 0 && selectedFolders.value.size < searchResults.value.length
    )

    // Navigation
    function goBack() {
      router.push('/manga-viewer')
    }

    // Search
    function performSearch() {
      if (!searchKeyword.value.trim()) {
        ElMessage.warning('Please enter search keyword')
        return
      }

      const keyword = searchKeyword.value.trim().toLowerCase()
      const allFolders = Object.values(store.mangaIndex.folders)

      searchResults.value = allFolders.filter(f => {
        const searchPool = [
          f.name,
          f.path,
          ...f.tags.auth,
          ...f.tags.name,
          ...f.tags.custom,
          ...f.tags.others,
          f.tags.category_main,
          f.tags.category_sub
        ].map(s => (s || '').toLowerCase())

        return searchPool.some(s => s.includes(keyword))
      })

      selectedFolders.value.clear()
      ElMessage.success(`Found ${searchResults.value.length} folders`)
    }

    function clearSearch() {
      searchKeyword.value = ''
      searchResults.value = []
      selectedFolders.value.clear()
    }

    // Selection
    function toggleSelectAll() {
      if (allSelected.value) {
        selectedFolders.value.clear()
      } else {
        searchResults.value.forEach(f => selectedFolders.value.add(f.id))
      }
    }

    function toggleSelect(folderId: string) {
      if (selectedFolders.value.has(folderId)) {
        selectedFolders.value.delete(folderId)
      } else {
        selectedFolders.value.add(folderId)
      }
    }

    function isSelected(folderId: string): boolean {
      return selectedFolders.value.has(folderId)
    }

    // Batch Operations
    async function applyReplace() {
      if (!batchOperations.replaceFrom) {
        ElMessage.warning('Please enter text to replace')
        return
      }

      if (selectedFolders.value.size === 0) {
        ElMessage.warning('Please select folders')
        return
      }

      try {
        await ElMessageBox.confirm(
          `Replace "${batchOperations.replaceFrom}" with "${batchOperations.replaceTo}" in ${selectedFolders.value.size} folder(s)?`,
          'Confirm Replace',
          { type: 'warning' }
        )

        let count = 0
        for (const folderId of selectedFolders.value) {
          const folder = store.mangaIndex.folders[folderId]
          if (folder && folder.name.includes(batchOperations.replaceFrom)) {
            folder.name = folder.name.replaceAll(batchOperations.replaceFrom, batchOperations.replaceTo)
            folder.initialized = true
            store.addChangeId(folderId)
            store.addMoveId(folderId)
            count++
          }
        }

        ElMessage.success(`Replaced in ${count} folder(s)`)
        batchOperations.replaceFrom = ''
        batchOperations.replaceTo = ''
      } catch {
        // User cancelled
      }
    }

    async function applyPrefix() {
      if (!batchOperations.prefix.trim()) {
        ElMessage.warning('Please enter prefix')
        return
      }

      if (selectedFolders.value.size === 0) {
        ElMessage.warning('Please select folders')
        return
      }

      try {
        await ElMessageBox.confirm(
          `Add prefix "${batchOperations.prefix}" to ${selectedFolders.value.size} folder(s)?`,
          'Confirm Prefix',
          { type: 'warning' }
        )

        let count = 0
        for (const folderId of selectedFolders.value) {
          const folder = store.mangaIndex.folders[folderId]
          if (folder && !folder.name.startsWith(batchOperations.prefix)) {
            folder.name = batchOperations.prefix + folder.name
            folder.initialized = true
            store.addChangeId(folderId)
            store.addMoveId(folderId)
            count++
          }
        }

        ElMessage.success(`Added prefix to ${count} folder(s)`)
        batchOperations.prefix = ''
      } catch {
        // User cancelled
      }
    }

    async function applySuffix() {
      if (!batchOperations.suffix.trim()) {
        ElMessage.warning('Please enter suffix')
        return
      }

      if (selectedFolders.value.size === 0) {
        ElMessage.warning('Please select folders')
        return
      }

      try {
        await ElMessageBox.confirm(
          `Add suffix "${batchOperations.suffix}" to ${selectedFolders.value.size} folder(s)?`,
          'Confirm Suffix',
          { type: 'warning' }
        )

        let count = 0
        for (const folderId of selectedFolders.value) {
          const folder = store.mangaIndex.folders[folderId]
          if (folder && !folder.name.endsWith(batchOperations.suffix)) {
            folder.name = folder.name + batchOperations.suffix
            folder.initialized = true
            store.addChangeId(folderId)
            store.addMoveId(folderId)
            count++
          }
        }

        ElMessage.success(`Added suffix to ${count} folder(s)`)
        batchOperations.suffix = ''
      } catch {
        // User cancelled
      }
    }

    async function applyCustomTag() {
      if (!batchOperations.customTag.trim()) {
        ElMessage.warning('Please enter custom tag')
        return
      }

      if (selectedFolders.value.size === 0) {
        ElMessage.warning('Please select folders')
        return
      }

      try {
        await ElMessageBox.confirm(
          `Add custom tag "${batchOperations.customTag}" to ${selectedFolders.value.size} folder(s)?`,
          'Confirm Tag',
          { type: 'warning' }
        )

        for (const folderId of selectedFolders.value) {
          const folder = store.mangaIndex.folders[folderId]
          if (folder && !folder.tags.custom.includes(batchOperations.customTag)) {
            folder.tags.custom.push(batchOperations.customTag)
            folder.initialized = true
            store.addChangeId(folderId)
          }
        }

        ElMessage.success(`Added tag to ${selectedFolders.value.size} folder(s)`)
        batchOperations.customTag = ''
      } catch {
        // User cancelled
      }
    }

    // Apply Changes
    async function applyChanges() {
      if (store.changeIdList.size === 0) {
        ElMessage.info('No changes to apply')
        return
      }

      const loading = ElLoading.service({ lock: true, text: 'Applying changes...', background: 'rgba(0,0,0,0.4)' })
      try {
        await store.applyChanges(true)
        ElMessage.success('Changes applied successfully')

        // Refresh search results
        if (searchKeyword.value) {
          performSearch()
        }
      } catch (e) {
        console.error('Failed to apply changes:', e)
        ElMessage.error('Failed to apply changes')
      } finally {
        loading.close()
      }
    }

    return {
      // Navigation
      goBack,
      // Search
      searchKeyword,
      searchResults,
      performSearch,
      clearSearch,
      // Selection
      selectedFolders,
      allSelected,
      someSelected,
      toggleSelectAll,
      toggleSelect,
      isSelected,
      // Batch Operations
      batchOperations,
      applyReplace,
      applyPrefix,
      applySuffix,
      applyCustomTag,
      // Apply
      applyChanges,
      changeCount: computed(() => store.changeIdList.size)
    }
  }
})
