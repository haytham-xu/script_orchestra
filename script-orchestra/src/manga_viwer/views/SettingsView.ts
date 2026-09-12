import { defineComponent, ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRouter } from 'vue-router'
import { fetchSettings, updateSettings, refreshIndex, fetchRefreshStatus, fetchStats, cleanEmptyFolders } from '@/manga_viwer/service/Service'
import type { MangaViewerSettings, CategoryOption } from '../service/Model'
import { ElMessage, ElMessageBox, ElLoading } from 'element-plus'
import { postRequest } from '@/basic/RequestService'
import { MANGA_SERIES_GROUPER_ENDPOINT } from '@/basic/Constants'

export default defineComponent({
  name: 'SettingsView',
  setup() {
    const router = useRouter()
    const settings = ref<MangaViewerSettings | null>(null)
    const stats = ref<{ total_folders: number; total_files: number; total_size: number } | null>(null)
    const refreshLoading = ref(false)
    const refreshProgress = ref('')
    let pollTimer: number | null = null
    const subBulkImportPath = ref('')
    const subBulkImporting = ref(false)

    const totalSizeHuman = computed(() => {
      if (!stats.value) return '-'
      const bytes = stats.value.total_size
      const units = ['B', 'KB', 'MB', 'GB', 'TB']
      let v = bytes, i = 0
      while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
      return `${v.toFixed(2)} ${units[i]}`
    })

    function goBack() {
      router.push('/manga-viewer')
    }

    async function loadSettings() {
      const loading = ElLoading.service({ lock: true, text: 'Loading settings...', background: 'rgba(0,0,0,0.4)' })
      try {
        settings.value = await fetchSettings()
      } catch (e) {
        console.error('Failed to load settings:', e)
        ElMessage.error('Failed to load settings')
      } finally {
        loading.close()
      }
    }

    async function loadStats() {
      try {
        stats.value = await fetchStats()
      } catch (e) {
        console.error('Failed to load stats:', e)
      }
    }

    async function handleSave() {
      if (!settings.value) return

      const loading = ElLoading.service({ lock: true, text: 'Saving...', background: 'rgba(0,0,0,0.4)' })
      try {
        await updateSettings(settings.value)
        ElMessage.success('Settings saved successfully')
      } catch (e) {
        console.error('Failed to save settings:', e)
        ElMessage.error('Failed to save settings')
      } finally {
        loading.close()
      }
    }

    async function handleRefreshIndex() {
      await runIndexTask('refresh', async () => { await refreshIndex() }, 'build index successfully', 'failed to refresh index')
    }

    async function handleCleanEmpty() {
      try {
        await ElMessageBox.confirm(
          'This will scan all indexed folders and move folders without manga files to delete_paths. Continue?',
          'Confirm Cleanup',
          { confirmButtonText: 'Continue', cancelButtonText: 'Cancel', type: 'warning' }
        )
      } catch {
        return
      }
      await runIndexTask('clean', async () => { await cleanEmptyFolders() }, 'cleanup completed', 'cleanup failed')
    }

    async function runIndexTask(
      _tag: 'refresh' | 'clean',
      kickoff: () => Promise<void>,
      successMsg: string,
      failMsg: string,
    ) {
      if (refreshLoading.value) return
      refreshLoading.value = true
      refreshProgress.value = 'Starting...'
      try {
        await kickoff()
        await new Promise<void>((resolve) => {
          pollTimer = window.setInterval(async () => {
            try {
              const s = await fetchRefreshStatus()
              refreshProgress.value = s.total > 0
                ? `${s.phase} (${s.done}/${s.total})`
                : s.phase
              if (!s.running) {
                if (pollTimer !== null) { clearInterval(pollTimer); pollTimer = null }
                resolve()
              }
            } catch {
              // transient error — keep polling
            }
          }, 1000)
        })
        ElMessage.success(successMsg)
        await loadStats()
      } catch (e) {
        console.error(`${failMsg}:`, e)
        ElMessage.error(failMsg)
      } finally {
        if (pollTimer !== null) { clearInterval(pollTimer); pollTimer = null }
        refreshLoading.value = false
        refreshProgress.value = ''
      }
    }

    function addMainCategory() {
      if (!settings.value) return
      settings.value.categories.main.push({
        key: '',
        name: '',
        path: ''
      })
    }

    function removeMainCategory(index: number) {
      if (!settings.value) return
      settings.value.categories.main.splice(index, 1)
    }

    function addSubCategory() {
      if (!settings.value) return
      settings.value.categories.sub.push({
        key: '',
        name: '',
        path: ''
      })
    }

    function removeSubCategory(index: number) {
      if (!settings.value) return
      settings.value.categories.sub.splice(index, 1)
    }

    async function bulkImportSubCategories() {
      const root = subBulkImportPath.value.trim()
      if (!root || !settings.value) return
      subBulkImporting.value = true
      try {
        const r = await postRequest<{ subdirs: string[] }>(
          `${MANGA_SERIES_GROUPER_ENDPOINT}/list-subdirs`, {}, { path: root },
        )
        const existing = new Set(settings.value.categories.sub.map((c) => c.path.trim()).filter(Boolean))
        const added: CategoryOption[] = (r.subdirs || [])
          .map((d) => d.replace(/\\/g, '/').split('/').pop() || '')
          .filter((name) => name && !existing.has(name))
          .map((name) => ({ key: name, name: '', path: name }))
        if (!added.length) {
          ElMessage.info('No new subfolders found (all already in list)')
          return
        }
        settings.value.categories.sub.push(...added)
        subBulkImportPath.value = ''
        ElMessage.success(`Added ${added.length} sub category entry(ies)`)
      } catch (e: any) {
        ElMessage.error(e.message || 'Failed to list subdirectories')
      } finally {
        subBulkImporting.value = false
      }
    }

    function addIgnoreScanFolder() {
      if (!settings.value) return
      settings.value.paths.ignore_scan_folders.push('')
    }

    function removeIgnoreScanFolder(index: number) {
      if (!settings.value) return
      settings.value.paths.ignore_scan_folders.splice(index, 1)
    }

    onMounted(() => {
      loadSettings()
      loadStats()
    })

    onBeforeUnmount(() => {
      if (pollTimer !== null) { clearInterval(pollTimer); pollTimer = null }
    })

    return {
      settings,
      stats,
      totalSizeHuman,
      refreshLoading,
      refreshProgress,
      subBulkImportPath,
      subBulkImporting,
      goBack,
      handleSave,
      handleRefreshIndex,
      handleCleanEmpty,
      addMainCategory,
      removeMainCategory,
      addSubCategory,
      removeSubCategory,
      bulkImportSubCategories,
      addIgnoreScanFolder,
      removeIgnoreScanFolder,
    }
  }
})
