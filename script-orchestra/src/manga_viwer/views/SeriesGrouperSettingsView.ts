import { defineComponent, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { getRequest, putRequest } from '@/basic/RequestService'
import { MANGA_SERIES_GROUPER_ENDPOINT } from '@/basic/Constants'

interface Settings {
  scan_paths: string[]
  output_path: string
}

export default defineComponent({
  name: 'SeriesGrouperSettingsView',
  setup() {
    const router = useRouter()
    const settings = ref<Settings>({ scan_paths: [], output_path: '' })
    const saving = ref(false)

    async function load() {
      try {
        const s = await getRequest<Settings>(`${MANGA_SERIES_GROUPER_ENDPOINT}/settings`)
        settings.value = { scan_paths: s.scan_paths || [], output_path: s.output_path || '' }
      } catch {
        settings.value = { scan_paths: [], output_path: '' }
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

    function addPath() { settings.value.scan_paths.push('') }
    function removePath(i: number) { settings.value.scan_paths.splice(i, 1) }

    onMounted(load)

    return { settings, saving, save, addPath, removePath, goBack: () => router.push('/manga-viewer/series-grouper') }
  },
})
