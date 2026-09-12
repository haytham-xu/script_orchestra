import { defineComponent, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { getRequest, postRequest, deleteRequest } from '@/basic/RequestService'
import { MANGA_SERIES_GROUPER_ENDPOINT } from '@/basic/Constants'

interface SeriesGroup {
  key: string
  display_name: string
  folders: string[]
  target_name: string
  executing: boolean
  // merge UI
  mergeTarget: string | null
}

interface Settings {
  scan_paths: string[]
  output_path: string
}

interface WhitelistEntry {
  key: string
  folders: string[]
}

export default defineComponent({
  name: 'SeriesGrouperView',
  setup() {
    const router = useRouter()
    const settings = ref<Settings>({ scan_paths: [], output_path: '' })
    const groups = ref<SeriesGroup[]>([])
    const scanning = ref(false)

    async function loadSettings() {
      try {
        const s = await getRequest<Settings>(`${MANGA_SERIES_GROUPER_ENDPOINT}/settings`)
        settings.value = { scan_paths: s.scan_paths || [], output_path: s.output_path || '' }
      } catch {
        settings.value = { scan_paths: [], output_path: '' }
      }
    }

    async function scan() {
      const validPaths = settings.value.scan_paths.filter((p) => p.trim())
      if (!validPaths.length) {
        ElMessage.warning('No scan paths configured — go to Settings first')
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
          executing: false,
          mergeTarget: null,
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

    async function executeGroup(g: SeriesGroup) {
      if (!settings.value.output_path.trim()) {
        ElMessage.warning('Output path not configured — go to Settings')
        return
      }
      try {
        await ElMessageBox.confirm(
          `Move ${g.folders.length} folder(s) from "${g.target_name || g.key}" into "${settings.value.output_path}"? This cannot be undone.`,
          'Confirm', { type: 'warning' },
        )
      } catch { return }
      g.executing = true
      try {
        const r = await postRequest<{ moved: number; errors: string[] }>(
          `${MANGA_SERIES_GROUPER_ENDPOINT}/execute`,
          {},
          {
            output_path: settings.value.output_path,
            groups: [{ key: g.key, target_name: g.target_name || g.display_name, folders: g.folders }],
          },
        )
        if (r.errors?.length) {
          ElMessage.warning(`Moved ${r.moved}, but ${r.errors.length} error(s): ${r.errors[0]}`)
        } else {
          ElMessage.success(`Moved ${r.moved} folder(s)`)
        }
        groups.value = groups.value.filter((x) => x.key !== g.key)
      } catch (e: any) {
        ElMessage.error(e.message || 'Execute failed')
      } finally {
        g.executing = false
      }
    }

    async function addToWhitelist(g: SeriesGroup) {
      try {
        await postRequest(`${MANGA_SERIES_GROUPER_ENDPOINT}/whitelist`, {}, { key: g.key, folders: g.folders })
        ElMessage.success(`"${g.key}" added to whitelist`)
        groups.value = groups.value.filter((x) => x.key !== g.key)
      } catch (e: any) {
        ElMessage.error(e.message || 'Failed to add to whitelist')
      }
    }

    function startMerge(g: SeriesGroup) {
      g.mergeTarget = g.mergeTarget ? null : ''
    }

    function confirmMerge(g: SeriesGroup) {
      const targetKey = g.mergeTarget
      if (!targetKey) return
      const other = groups.value.find((x) => x.key === targetKey)
      if (!other) return
      // Merge other into g
      g.folders = [...g.folders, ...other.folders]
        .filter((v, i, a) => a.indexOf(v) === i)
        .sort()
      g.mergeTarget = null
      groups.value = groups.value.filter((x) => x.key !== targetKey)
      ElMessage.success(`Merged "${targetKey}" into "${g.key}"`)
    }

    async function openFolder(path: string) {
      try {
        await postRequest('/manga-viewer/open-folder', {}, { folderPath: path })
      } catch (e: any) {
        ElMessage.error(e.message || 'Failed to open folder')
      }
    }

    onMounted(loadSettings)

    return {
      settings, groups, scanning,
      scan, executeGroup, addToWhitelist, openFolder,
      startMerge, confirmMerge,
      goSettings: () => router.push('/manga-viewer/series-grouper/settings'),
      otherGroups: (key: string) => groups.value.filter((g) => g.key !== key),
    }
  },
})
