import { defineComponent, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import * as api from '../service/FileTrackerService'
import type { FileTrackerSettings, TimestampRule } from '../service/Model'

export default defineComponent({
  name: 'FileTrackerSettingsView',
  setup() {
    const router = useRouter()
    const settings = ref<FileTrackerSettings>({
      scan_paths: [],
      ignore_patterns: [],
      stale_thresholds_days: { archive: 90, warn: 180, danger: 365 },
      timestamp_rules: [],
    })
    const saving = ref(false)
    const pruneLoading = ref(false)
    const newPath = ref('')
    const newPattern = ref('')

    // Per-rule new-extension input state (keyed by rule index)
    const newExt = ref<Record<number, string>>({})

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

    // ---- scan paths ----
    function addPath() {
      const p = newPath.value.trim()
      if (!p) return
      if (!settings.value.scan_paths.includes(p))
        settings.value.scan_paths.push(p)
      newPath.value = ''
    }
    function removePath(p: string) {
      settings.value.scan_paths = settings.value.scan_paths.filter(x => x !== p)
    }

    // ---- ignore patterns ----
    function addPattern() {
      const p = newPattern.value.trim()
      if (!p) return
      if (!settings.value.ignore_patterns.includes(p))
        settings.value.ignore_patterns.push(p)
      newPattern.value = ''
    }
    function removePattern(p: string) {
      settings.value.ignore_patterns = settings.value.ignore_patterns.filter(x => x !== p)
    }

    // ---- timestamp rules ----
    function addRule() {
      settings.value.timestamp_rules.push({ extensions: ['*'], source: 'mtime' })
    }

    function removeRule(i: number) {
      settings.value.timestamp_rules.splice(i, 1)
    }

    function moveRule(i: number, dir: -1 | 1) {
      const rules = settings.value.timestamp_rules
      const j = i + dir
      if (j < 0 || j >= rules.length) return
      ;[rules[i], rules[j]] = [rules[j], rules[i]]
    }

    function addExt(i: number) {
      const raw = (newExt.value[i] || '').trim().toLowerCase()
      if (!raw) return
      // Normalise: ensure leading dot unless '*'
      const ext = raw === '*' ? '*' : raw.startsWith('.') ? raw : '.' + raw
      const rule = settings.value.timestamp_rules[i]
      if (!rule.extensions.includes(ext))
        rule.extensions.push(ext)
      newExt.value[i] = ''
    }

    function removeExt(i: number, ext: string) {
      settings.value.timestamp_rules[i].extensions =
        settings.value.timestamp_rules[i].extensions.filter(e => e !== ext)
    }

    // ---- maintenance ----
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
      settings, saving, pruneLoading, newPath, newPattern, newExt,
      save, addPath, removePath, addPattern, removePattern,
      addRule, removeRule, moveRule, addExt, removeExt, pruneDeleted,
      goBack: () => router.push('/file-tracker'),
    }
  },
})
