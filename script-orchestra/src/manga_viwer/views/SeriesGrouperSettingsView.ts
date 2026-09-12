import { defineComponent, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { getRequest, putRequest, postRequest, deleteRequest } from '@/basic/RequestService'
import { MANGA_SERIES_GROUPER_ENDPOINT } from '@/basic/Constants'

interface Settings {
  scan_paths: string[]
  output_path: string
}

interface WhitelistEntry {
  key: string
  folders: string[]
}

export default defineComponent({
  name: 'SeriesGrouperSettingsView',
  setup() {
    const router = useRouter()
    const settings = ref<Settings>({ scan_paths: [], output_path: '' })
    const whitelist = ref<WhitelistEntry[]>([])
    const saving = ref(false)
    const scanning = ref(false)

    async function load() {
      try {
        const s = await getRequest<Settings>(`${MANGA_SERIES_GROUPER_ENDPOINT}/settings`)
        settings.value = { scan_paths: s.scan_paths || [], output_path: s.output_path || '' }
      } catch {
        settings.value = { scan_paths: [], output_path: '' }
      }
      await loadWhitelist()
    }

    async function loadWhitelist() {
      try {
        const r = await getRequest<{ whitelist: Record<string, string[]> }>(`${MANGA_SERIES_GROUPER_ENDPOINT}/whitelist`)
        whitelist.value = Object.entries(r.whitelist || {}).map(([key, folders]) => ({ key, folders }))
      } catch {
        whitelist.value = []
      }
    }

    async function save() {
      saving.value = true
      try {
        const s = await putRequest<Settings>(`${MANGA_SERIES_GROUPER_ENDPOINT}/settings`, {}, settings.value)
        settings.value = { scan_paths: s.scan_paths || [], output_path: s.output_path || '' }
        ElMessage.success('Settings saved')
      } catch (e: any) {
        ElMessage.error(e.message || 'Failed to save')
      } finally {
        saving.value = false
      }
    }

    async function removeWhitelistEntry(key: string) {
      try {
        await deleteRequest(`${MANGA_SERIES_GROUPER_ENDPOINT}/whitelist/${encodeURIComponent(key)}`, {})
        whitelist.value = whitelist.value.filter((e) => e.key !== key)
        ElMessage.success(`"${key}" removed from whitelist`)
      } catch (e: any) {
        ElMessage.error(e.message || 'Failed to remove')
      }
    }

    async function scanWhitelist() {
      scanning.value = true
      try {
        const r = await postRequest<{ whitelist: Record<string, string[]>; removed: string[] }>(
          `${MANGA_SERIES_GROUPER_ENDPOINT}/whitelist/scan`, {}, {},
        )
        whitelist.value = Object.entries(r.whitelist || {}).map(([key, folders]) => ({ key, folders }))
        if (r.removed?.length) {
          ElMessage.success(`Pruned ${r.removed.length} stale entry(ies): ${r.removed.join(', ')}`)
        } else {
          ElMessage.info('All whitelist entries are still valid')
        }
      } catch (e: any) {
        ElMessage.error(e.message || 'Scan failed')
      } finally {
        scanning.value = false
      }
    }

    function addPath() { settings.value.scan_paths.push('') }
    function removePath(i: number) { settings.value.scan_paths.splice(i, 1) }

    onMounted(load)

    return {
      settings, whitelist, saving, scanning,
      save, addPath, removePath,
      removeWhitelistEntry, scanWhitelist,
      goBack: () => router.push('/manga-viewer/series-grouper'),
    }
  },
})
