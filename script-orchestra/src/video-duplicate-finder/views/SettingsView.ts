import { defineComponent, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Refresh } from '@element-plus/icons-vue'
import { VideoDuplicateFinderService } from '../service/VideoDuplicateFinderService'
import type { Settings } from '../service/Model'

const DEFAULT_SETTINGS: Settings = {
  delete_target_path: '',
  similarity_threshold: 80,
  folder_paths: [],
  exclude_folder_paths: [],
  auto_selection_rules: {
    auto_mark_lower_resolution: true,
    auto_mark_lower_bitrate: false,
    auto_mark_smaller_filesize: false,
    auto_mark_older_codec: false,
    auto_mark_numbered_copies: true,
    prefer_folders: [],
  },
  companion_extensions: ['.srt', '.ass', '.vtt', '.sub', '.idx', '.nfo', '.jpg', '.png'],
  max_cpu_cores: 2,
  n_frames: 8,
  frame_extract_timeout_seconds: 30,
  thumbnail_position_percent: 30,
  page_size: 100,
  phase1: {
    worker_handler_size: 1,
    db_commit_batch_size: 50,
    progress_update_interval: 10,
    ipc_chunk_size: 1,
    scan_delay: 0.0,
    compute_delay: 0.0,
  },
  phase2: {
    worker_handler_size: 1,
    db_commit_batch_size: 100,
    progress_update_interval: 100,
    ipc_chunk_size: 10,
    compare_delay: 0.0,
  },
}

export default defineComponent({
  name: 'VideoDuplicateFinderSettingsView',
  components: { ArrowLeft, Refresh },
  setup() {
    const router = useRouter()
    const loading = ref(false)
    const saving = ref(false)
    const isCleaningDb = ref(false)
    const settingsLoaded = ref(false)
    const threshold = ref(80)
    const settings = ref<Settings>(JSON.parse(JSON.stringify(DEFAULT_SETTINGS)))

    async function load() {
      loading.value = true
      try {
        const s = await VideoDuplicateFinderService.getSettings()
        settings.value = {
          ...settings.value,
          ...s,
          phase1: { ...(settings.value.phase1 || {}), ...(s.phase1 || {}) } as any,
          phase2: { ...(settings.value.phase2 || {}), ...(s.phase2 || {}) } as any,
          auto_selection_rules: {
            ...(settings.value.auto_selection_rules || {}),
            ...(s.auto_selection_rules || {}),
          } as any,
        }
        if (!settings.value.folder_paths) settings.value.folder_paths = []
        if (!settings.value.exclude_folder_paths) settings.value.exclude_folder_paths = []
        if (!settings.value.companion_extensions) settings.value.companion_extensions = []
        if (!settings.value.auto_selection_rules) settings.value.auto_selection_rules = { prefer_folders: [] }
        if (!settings.value.auto_selection_rules.prefer_folders) settings.value.auto_selection_rules.prefer_folders = []
        threshold.value = s.similarity_threshold || 80
        settingsLoaded.value = true
      } catch (e: any) {
        ElMessage.error(e?.message || 'Failed to load settings')
        settingsLoaded.value = false
      } finally {
        loading.value = false
      }
    }

    async function save() {
      if (!settingsLoaded.value) {
        ElMessage.error('Cannot save: initial settings load failed. Reload the page.')
        return
      }
      if (settings.value.folder_paths) {
        const empty = settings.value.folder_paths.filter(p => !p || !p.trim())
        if (empty.length > 0) { ElMessage.error('Folder paths cannot be empty'); return }
      }
      if (settings.value.page_size !== undefined && (settings.value.page_size < 20 || settings.value.page_size > 500)) {
        ElMessage.error('Page size must be between 20 and 500')
        return
      }
      saving.value = true
      try {
        settings.value.similarity_threshold = threshold.value
        await VideoDuplicateFinderService.updateSettings(settings.value)
        ElMessage.success('Settings saved')
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.error || e?.message || 'Failed to save settings')
      } finally {
        saving.value = false
      }
    }

    async function cleanupDatabase() {
      isCleaningDb.value = true
      try {
        const r = await VideoDuplicateFinderService.cleanupDatabase()
        ElMessage.success(`Cleanup done: removed ${r.removed_count ?? 0} stale entries`)
      } catch (e: any) {
        ElMessage.error(e?.message || 'Cleanup failed')
      } finally {
        isCleaningDb.value = false
      }
    }

    function addFolderPath() {
      if (!settings.value.folder_paths) settings.value.folder_paths = []
      settings.value.folder_paths.push('')
    }
    function removeFolderPath(i: number) { settings.value.folder_paths?.splice(i, 1) }
    function addExcludePath() {
      if (!settings.value.exclude_folder_paths) settings.value.exclude_folder_paths = []
      settings.value.exclude_folder_paths.push('')
    }
    function removeExcludePath(i: number) { settings.value.exclude_folder_paths?.splice(i, 1) }
    function addPreferFolder() {
      if (!settings.value.auto_selection_rules) settings.value.auto_selection_rules = { prefer_folders: [] }
      if (!settings.value.auto_selection_rules.prefer_folders) settings.value.auto_selection_rules.prefer_folders = []
      settings.value.auto_selection_rules.prefer_folders.push('')
    }
    function removePreferFolder(i: number) { settings.value.auto_selection_rules?.prefer_folders?.splice(i, 1) }
    function addCompanionExt() {
      if (!settings.value.companion_extensions) settings.value.companion_extensions = []
      settings.value.companion_extensions.push('')
    }
    function removeCompanionExt(i: number) { settings.value.companion_extensions?.splice(i, 1) }

    function goBack() { router.push('/video-duplicate-finder') }

    onMounted(load)

    return {
      loading, saving, isCleaningDb, threshold, settings,
      Refresh, ArrowLeft,
      load, save, cleanupDatabase,
      addFolderPath, removeFolderPath,
      addExcludePath, removeExcludePath,
      addPreferFolder, removePreferFolder,
      addCompanionExt, removeCompanionExt,
      goBack,
    }
  },
})
