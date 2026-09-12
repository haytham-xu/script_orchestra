import { defineComponent, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { getRequest, postRequest } from '@/basic/RequestService'
import { MANGA_SERIES_GROUPER_ENDPOINT } from '@/basic/Constants'

interface SeriesGroup {
  key: string
  display_name: string
  folders: string[]
  target_name: string
  selected: boolean
}

interface Settings {
  scan_paths: string[]
  output_path: string
}

export default defineComponent({
  name: 'SeriesGrouperView',
  setup() {
    const router = useRouter()
    const settings = ref<Settings>({ scan_paths: [], output_path: '' })
    const groups = ref<SeriesGroup[]>([])
    const scanning = ref(false)
    const executing = ref(false)

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

    async function execute() {
      const selected = groups.value.filter((g) => g.selected)
      if (!selected.length) { ElMessage.warning('No groups selected'); return }
      if (!settings.value.output_path.trim()) { ElMessage.warning('Output path not configured — go to Settings'); return }
      try {
        await ElMessageBox.confirm(
          `Move folders from ${selected.length} group(s) into "${settings.value.output_path}"? This cannot be undone.`,
          'Confirm', { type: 'warning' },
        )
      } catch { return }
      executing.value = true
      try {
        const r = await postRequest<{ moved: number; errors: string[] }>(
          `${MANGA_SERIES_GROUPER_ENDPOINT}/execute`,
          {},
          {
            output_path: settings.value.output_path,
            groups: selected.map((g) => ({
              key: g.key,
              target_name: g.target_name || g.display_name,
              folders: g.folders,
            })),
          },
        )
        if (r.errors?.length) {
          ElMessage.warning(`Moved ${r.moved}, but ${r.errors.length} error(s): ${r.errors[0]}`)
        } else {
          ElMessage.success(`Moved ${r.moved} folder(s) successfully`)
        }
        const movedKeys = new Set(selected.map((g) => g.key))
        groups.value = groups.value.filter((g) => !movedKeys.has(g.key))
      } catch (e: any) {
        ElMessage.error(e.message || 'Execute failed')
      } finally {
        executing.value = false }
    }

    function toggleAll(val: boolean) { groups.value.forEach((g) => (g.selected = val)) }

    onMounted(loadSettings)

    return {
      settings, groups, scanning, executing,
      scan, execute, toggleAll,
      goSettings: () => router.push('/manga-viewer/series-grouper/settings'),
    }
  },
})

