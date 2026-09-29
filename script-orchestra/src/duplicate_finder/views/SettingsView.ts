import { defineComponent, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Refresh } from '@element-plus/icons-vue'
import { DuplicateFinderService, type Settings } from '../service/DuplicateFinderService'

interface WhitelistMember {
  image_id: number
  filename: string
  filesize: number
  file_path: string
  phash: string
  resolution: string
}

interface WhitelistGroup {
  group_id: number
  added_time: number
  members: WhitelistMember[]
}

const DEFAULT_SETTINGS: Settings = {
  delete_target_path: '',
  similarity_threshold: 80,
  folder_paths: [],
  exclude_folder_paths: [],
  max_cpu_cores: 1,
  page_size: 100,
  auto_selection_rules: {
    auto_mark_numbered_copies: true,
    auto_mark_copy_suffix: true,
    prefer_folders: [],
  },
  phase1: {
    worker_handler_size: 1,
    db_commit_batch_size: 100,
    progress_update_interval: 100,
    ipc_chunk_size: 10,
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
  name: 'DuplicateFinderSettingsView',
  components: { ArrowLeft, Refresh },
  setup() {
    const router = useRouter()
    const loading = ref(false)
    const saving = ref(false)
    const threshold = ref(80)
    const settings = ref<Settings>(JSON.parse(JSON.stringify(DEFAULT_SETTINGS)))

    const whitelistGroups = ref<WhitelistGroup[]>([])
    const isLoadingWhitelist = ref(false)

    function getCpuMarks() {
      const count = settings.value.system_cpu_count || 12
      const marks: Record<number, string> = { 1: '1' }
      if (count >= 4) marks[4] = '4'
      if (count >= 8) marks[8] = '8'
      if (count >= 12) marks[12] = '12'
      if (count > 12) marks[count] = String(count)
      return marks
    }

    async function load() {
      loading.value = true
      try {
        const s = await DuplicateFinderService.getSettings()
        settings.value = s
        threshold.value = s.similarity_threshold || 80
        if (!settings.value.folder_paths) settings.value.folder_paths = []
        if (!settings.value.exclude_folder_paths) settings.value.exclude_folder_paths = []
        if (!settings.value.auto_selection_rules) {
          settings.value.auto_selection_rules = { auto_mark_numbered_copies: true, auto_mark_copy_suffix: true, prefer_folders: [] }
        }
        if (!settings.value.auto_selection_rules.prefer_folders) settings.value.auto_selection_rules.prefer_folders = []
        if (!settings.value.phase1) settings.value.phase1 = { ...DEFAULT_SETTINGS.phase1 }
        if (!settings.value.phase2) settings.value.phase2 = { ...DEFAULT_SETTINGS.phase2 }
      } catch (e: any) {
        ElMessage.error(e?.message || 'Failed to load settings')
      } finally {
        loading.value = false
      }
    }

    async function save() {
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
        await DuplicateFinderService.updateSettings({ ...settings.value, similarity_threshold: threshold.value })
        settings.value.similarity_threshold = threshold.value
        ElMessage.success('Settings saved')
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.error || e?.message || 'Failed to save settings')
      } finally {
        saving.value = false
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

    async function loadWhitelistGroups() {
      isLoadingWhitelist.value = true
      try {
        const result = await DuplicateFinderService.getWhitelistGroups()
        whitelistGroups.value = result.whitelist_groups
      } catch (e: any) {
        ElMessage.error(e?.message || 'Failed to load whitelist')
      } finally {
        isLoadingWhitelist.value = false
      }
    }

    async function removeWhitelistGroup(group_id: number, index: number) {
      const group = whitelistGroups.value[index]
      const memberCount = group?.members?.length || 0
      try {
        await ElMessageBox.confirm(`Remove this whitelist group (${memberCount} images)?`, 'Confirm Remove', {
          confirmButtonText: 'Remove', cancelButtonText: 'Cancel', type: 'warning',
        })
        await DuplicateFinderService.removeWhitelistGroup(group_id)
        ElMessage.success('Removed from whitelist')
        whitelistGroups.value.splice(index, 1)
      } catch (e: any) {
        if (e !== 'cancel') ElMessage.error(e?.message || 'Failed to remove from whitelist')
      }
    }

    function getImageUrl(filePath: string): string {
      return DuplicateFinderService.getImageUrl(filePath)
    }

    function formatTimestamp(ts: number): string {
      return new Date(ts * 1000).toLocaleString()
    }

    function goBack() { router.push('/duplicate-finder') }

    onMounted(load)

    return {
      loading, saving, threshold, settings,
      whitelistGroups, isLoadingWhitelist,
      getCpuMarks, load, save,
      addFolderPath, removeFolderPath,
      addExcludePath, removeExcludePath,
      addPreferFolder, removePreferFolder,
      loadWhitelistGroups, removeWhitelistGroup,
      getImageUrl, formatTimestamp,
      goBack, Refresh, ArrowLeft,
    }
  },
})
