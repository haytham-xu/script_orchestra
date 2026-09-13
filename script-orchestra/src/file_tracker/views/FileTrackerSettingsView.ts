import { defineComponent, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import * as api from '../service/FileTrackerService'
import type { FileTrackerSettings } from '../service/Model'

export default defineComponent({
  name: 'FileTrackerSettingsView',
  setup() {
    const router = useRouter()
    const settings = ref<FileTrackerSettings>({
      scan_paths: [],
      ignore_patterns: [],
      stale_thresholds_days: { archive: 90, warn: 180, danger: 365 },
    })
    const saving = ref(false)
    const pruneLoading = ref(false)
    const newPath = ref('')
    const newPattern = ref('')

    async function load() {
      try {
        settings.value = await api.getSettings()
      } catch { /* defaults already set */ }
    }

    async function save() {
      saving.value = true
      try {
        settings.value = await api.saveSettings(settings.value)
        ElMessage.success('Settings saved')
      } catch (e: any) {
        ElMessage.error(e.message || 'Failed to save')
      } finally {
        saving.value = false
      }
    }

    function addPath() {
      const p = newPath.value.trim()
      if (!p) return
      if (!settings.value.scan_paths.includes(p)) {
        settings.value.scan_paths.push(p)
      }
      newPath.value = ''
    }

    function removePath(p: string) {
      settings.value.scan_paths = settings.value.scan_paths.filter(x => x !== p)
    }

    function addPattern() {
      const p = newPattern.value.trim()
      if (!p) return
      if (!settings.value.ignore_patterns.includes(p)) {
        settings.value.ignore_patterns.push(p)
      }
      newPattern.value = ''
    }

    function removePattern(p: string) {
      settings.value.ignore_patterns = settings.value.ignore_patterns.filter(x => x !== p)
    }

    async function pruneDeleted() {
      try {
        await ElMessageBox.confirm(
          'Remove DB entries for files that no longer exist on disk?',
          'Confirm Prune',
          { type: 'warning' },
        )
      } catch { return }
      pruneLoading.value = true
      try {
        const n = await api.pruneDeleted()
        ElMessage.success(`Pruned ${n} stale DB entr${n === 1 ? 'y' : 'ies'}`)
      } catch (e: any) {
        ElMessage.error(e.message || 'Prune failed')
      } finally {
        pruneLoading.value = false
      }
    }

    onMounted(load)

    return {
      settings, saving, pruneLoading, newPath, newPattern,
      save, addPath, removePath, addPattern, removePattern, pruneDeleted,
      goBack: () => router.push('/file-tracker'),
    }
  },
})
