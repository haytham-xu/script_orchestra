import { defineComponent, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getRequest, postRequest, putRequest } from '@/basic/RequestService'
import { MANGA_SERIES_GROUPER_ENDPOINT } from '@/basic/Constants'

interface SeriesGroup {
  key: string
  display_name: string
  folders: string[]
  target_name: string   // editable — defaults to display_name
  selected: boolean
}

interface Settings {
  scan_paths: string[]
  output_path: string
}

const DEFAULT_SETTINGS: Settings = {
  scan_paths: [],
  output_path: '',
}

export default defineComponent({
  name: 'SeriesGrouperView',
  setup() {
    const settings = ref<Settings>({ ...DEFAULT_SETTINGS })
    const groups = ref<SeriesGroup[]>([])
    const scanning = ref(false)
    const executing = ref(false)
    const settingsDirty = ref(false)
    const savingSettings = ref(false)

    // ---- settings ----
    async function loadSettings() {
      try {
        const s = await getRequest<Settings>(`${MANGA_SERIES_GROUPER_ENDPOINT}/settings`)
        settings.value = {
          scan_paths: s.scan_paths || [],
          output_path: s.output_path || '',
        }
      } catch {
        settings.value = { ...DEFAULT_SETTINGS }
      }
    }

    async function saveSettings() {
      savingSettings.value = true
      try {
        const s = await putRequest<Settings>(`${MANGA_SERIES_GROUPER_ENDPOINT}/settings`, {}, settings.value)
        settings.value = { scan_paths: s.scan_paths || [], output_path: s.output_path || '' }
        settingsDirty.value = false
        ElMessage.success('Settings saved')
      } catch (e: any) {
        ElMessage.error(e.message || 'Failed to save settings')
      } finally {
        savingSettings.value = false
      }
    }

    function addScanPath() {
      settings.value.scan_paths.push('')
      settingsDirty.value = true
    }

    function removeScanPath(i: number) {
      settings.value.scan_paths.splice(i, 1)
      settingsDirty.value = true
    }

    // ---- scan ----
    async function scan() {
      const validPaths = settings.value.scan_paths.filter((p) => p.trim())
      if (!validPaths.length) {
        ElMessage.warning('Add at least one scan path')
        return
      }
      scanning.value = true
      groups.value = []
      try {
        const r = await postRequest<{ groups: Array<{ key: string; display_name: string; folders: string[] }> }>(
          `${MANGA_SERIES_GROUPER_ENDPOINT}/scan`,
          {},
          { scan_paths: validPaths },
        )
        groups.value = (r.groups || []).map((g) => ({
          ...g,
          target_name: g.display_name,
          selected: true,
        }))
        if (!groups.value.length) {
          ElMessage.info('No series groups found — all folders appear to be unique')
        }
      } catch (e: any) {
        ElMessage.error(e.message || 'Scan failed')
      } finally {
        scanning.value = false
      }
    }

    // ---- execute ----
    async function execute() {
      const selected = groups.value.filter((g) => g.selected)
      if (!selected.length) {
        ElMessage.warning('No groups selected')
        return
      }
      if (!settings.value.output_path.trim()) {
        ElMessage.warning('Output path is required')
        return
      }
      try {
        await ElMessageBox.confirm(
          `Move folders from ${selected.length} group(s) into "${settings.value.output_path}"?  This cannot be undone.`,
          'Confirm',
          { type: 'warning' },
        )
      } catch {
        return
      }
      executing.value = true
      try {
        const payload = {
          output_path: settings.value.output_path,
          groups: selected.map((g) => ({
            key: g.key,
            target_name: g.target_name || g.display_name,
            folders: g.folders,
          })),
        }
        const r = await postRequest<{ moved: number; errors: string[] }>(
          `${MANGA_SERIES_GROUPER_ENDPOINT}/execute`,
          {},
          payload,
        )
        if (r.errors?.length) {
          ElMessage.warning(`Moved ${r.moved}, but ${r.errors.length} error(s): ${r.errors[0]}`)
        } else {
          ElMessage.success(`Moved ${r.moved} folder(s) successfully`)
        }
        // Clear executed groups from the list
        const movedKeys = new Set(selected.map((g) => g.key))
        groups.value = groups.value.filter((g) => !movedKeys.has(g.key))
      } catch (e: any) {
        ElMessage.error(e.message || 'Execute failed')
      } finally {
        executing.value = false
      }
    }

    function toggleAll(val: boolean) {
      groups.value.forEach((g) => (g.selected = val))
    }

    const allSelected = () => groups.value.length > 0 && groups.value.every((g) => g.selected)

    onMounted(loadSettings)

    return {
      settings,
      groups,
      scanning,
      executing,
      settingsDirty,
      savingSettings,
      loadSettings,
      saveSettings,
      addScanPath,
      removeScanPath,
      scan,
      execute,
      toggleAll,
      allSelected,
    }
  },
})
