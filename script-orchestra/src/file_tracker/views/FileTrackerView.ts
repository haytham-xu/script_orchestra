import { defineComponent, ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '../service/FileTrackerService'
import type { TrackedFile, ScanStatus, FileStats } from '../service/Model'

type AgeGroup = 'danger' | 'warn' | 'archive' | 'recent'

export function fmtSize(bytes: number): string {
  if (!bytes) return '0 B'
  if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + ' GB'
  if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + ' MB'
  if (bytes >= 1e3) return (bytes / 1e3).toFixed(1) + ' KB'
  return bytes + ' B'
}

export function ageDays(lastActive: number): number {
  return Math.floor((Date.now() / 1000 - lastActive) / 86400)
}

export function ageGroup(days: number, thresholds = { archive: 90, warn: 180, danger: 365 }): AgeGroup {
  if (days >= thresholds.danger) return 'danger'
  if (days >= thresholds.warn) return 'warn'
  if (days >= thresholds.archive) return 'archive'
  return 'recent'
}

export function fmtDate(unix: number): string {
  if (!unix) return '—'
  return new Date(unix * 1000).toLocaleDateString()
}

export default defineComponent({
  name: 'FileTrackerView',
  setup() {
    const router = useRouter()
    const files = ref<TrackedFile[]>([])
    const total = ref(0)
    const stats = ref<FileStats | null>(null)
    const scanStatus = ref<ScanStatus>({
      running: false,
      progress: { scanned: 0, total: 0, path: '' },
      last_scan_time: null,
    })
    const viewMode = ref<'grouped' | 'table'>('grouped')
    const activeStatusFilter = ref('all')
    const searchText = ref('')
    const selectedIds = ref<number[]>([])
    const loading = ref(false)
    const thresholds = ref({ archive: 90, warn: 180, danger: 365 })

    let pollTimer: ReturnType<typeof setInterval> | null = null

    // ---- scan polling ----
    async function pollScan() {
      try {
        scanStatus.value = await api.getScanStatus()
      } catch { /* non-fatal */ }
    }

    function startPoll() {
      if (pollTimer) return
      pollTimer = setInterval(async () => {
        await pollScan()
        if (!scanStatus.value.running) {
          stopPoll()
          await loadAll()
        }
      }, 2000)
    }

    function stopPoll() {
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
    }

    async function triggerScan() {
      try {
        await api.startScan()
        await pollScan()
        startPoll()
      } catch (e: any) {
        if (e?.response?.status === 409) {
          ElMessage.info('Scan already running')
          startPoll()
        } else {
          ElMessage.error(e.message || 'Failed to start scan')
        }
      }
    }

    // ---- data loading ----
    async function loadFiles() {
      loading.value = true
      try {
        const r = await api.getFiles({
          status: activeStatusFilter.value,
          per_page: 500,
          sort: 'last_active',
          order: 'asc',
        })
        files.value = r.files
        total.value = r.total
      } finally {
        loading.value = false
      }
    }

    async function loadStats() {
      try { stats.value = await api.getStats() } catch { /* non-fatal */ }
    }

    async function loadAll() {
      await Promise.all([loadFiles(), loadStats()])
    }

    // ---- load settings thresholds ----
    async function loadThresholds() {
      try {
        const s = await api.getSettings()
        thresholds.value = s.stale_thresholds_days
      } catch { /* use defaults */ }
    }

    // ---- computed ----
    const filteredFiles = computed(() => {
      const q = searchText.value.toLowerCase()
      if (!q) return files.value
      return files.value.filter(f => f.path.toLowerCase().includes(q))
    })

    const grouped = computed(() => {
      const g: Record<AgeGroup, TrackedFile[]> = { danger: [], warn: [], archive: [], recent: [] }
      for (const f of filteredFiles.value) {
        g[ageGroup(ageDays(f.last_active), thresholds.value)].push(f)
      }
      return g
    })

    const totalSizeDisplay = computed(() => {
      if (!stats.value) return ''
      return fmtSize(stats.value.total_size)
    })

    const scanPercent = computed(() => {
      const { scanned, total: tot } = scanStatus.value.progress
      if (!tot) return 0
      return Math.min(100, Math.round((scanned / tot) * 100))
    })

    // ---- per-file actions ----
    async function setStatus(f: TrackedFile, status: string) {
      await api.patchFile(f.id, { status })
      f.status = status as any
      await loadStats()
    }

    async function deleteFile(f: TrackedFile) {
      const name = f.path.split('/').pop() || f.path
      try {
        await ElMessageBox.confirm(
          `Move "${name}" to Trash? This cannot be undone from here.`,
          'Confirm Delete',
          { type: 'warning', confirmButtonText: 'Move to Trash', cancelButtonText: 'Cancel' },
        )
      } catch { return }
      try {
        await api.trashFile(f.id)
        files.value = files.value.filter(x => x.id !== f.id)
        await loadStats()
        ElMessage.success(`"${name}" moved to Trash`)
      } catch (e: any) {
        ElMessage.error(e.message || 'Delete failed')
      }
    }

    async function revealFile(f: TrackedFile) {
      try { await api.revealFile(f.id) } catch (e: any) { ElMessage.error(e.message || 'Reveal failed') }
    }

    // ---- bulk ----
    async function bulkAction(action: 'ignored' | 'archived' | 'delete') {
      if (!selectedIds.value.length) return
      if (action === 'delete') {
        try {
          await ElMessageBox.confirm(
            `Move ${selectedIds.value.length} file(s) to Trash?`, 'Confirm',
            { type: 'warning' },
          )
        } catch { return }
        const r = await api.bulkDelete(selectedIds.value)
        if (r.errors?.length) {
          ElMessage.warning(`Moved ${r.deleted}, ${r.errors.length} error(s)`)
        } else {
          ElMessage.success(`Moved ${r.deleted} file(s) to Trash`)
        }
      } else {
        await api.bulkStatus(selectedIds.value, action)
        ElMessage.success(`${selectedIds.value.length} file(s) marked as ${action}`)
      }
      selectedIds.value = []
      await loadAll()
    }

    function onTableSelectionChange(rows: TrackedFile[]) {
      selectedIds.value = rows.map(r => r.id)
    }

    function groupSize(grp: TrackedFile[]): string {
      const sz = grp.reduce((s, f) => s + (f.size_bytes || 0), 0)
      return fmtSize(sz)
    }

    onMounted(async () => {
      await loadThresholds()
      await pollScan()
      if (scanStatus.value.running) startPoll()
      await loadAll()
    })
    onUnmounted(() => stopPoll())

    return {
      files, total, stats, scanStatus, viewMode, activeStatusFilter, searchText,
      selectedIds, loading, filteredFiles, grouped, totalSizeDisplay, scanPercent, thresholds,
      triggerScan, loadFiles, loadAll,
      setStatus, deleteFile, revealFile, bulkAction, onTableSelectionChange,
      fmtSize, ageDays, ageGroup, fmtDate, groupSize,
      goSettings: () => router.push('/file-tracker/settings'),
    }
  },
})
