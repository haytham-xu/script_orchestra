import { defineComponent, ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { io } from 'socket.io-client'
import { BACKEND_BASE_URL } from '@/basic/Constants'
import { FileDuplicateService } from '../service/FileDuplicateService'
import type {
  Settings, DuplicateGroup, FileMember, Stats, PhaseProgress, ScanRoot
} from '../service/Model'

export default defineComponent({
  name: 'FileDuplicateView',
  setup() {
    // ── State ──────────────────────────────────────────────────────────────
    const settings = ref<Settings>({
      scan_roots: [],
      exclude_patterns: ['.git', '__pycache__', 'node_modules'],
      include_extensions: [],
      trash_path: '',
      hash_batch_size: 200,
      max_workers: 4,
      page_size: 20,
    })
    const showSettings = ref(false)

    // Phase running
    const isPhase1Running = ref(false)
    const isPhase2Running = ref(false)
    const isPhase3Running = ref(false)
    const isFullPipelineRunning = ref(false)
    const phaseProgress = ref<PhaseProgress | null>(null)

    // Results
    const groups = ref<DuplicateGroup[]>([])
    const totalGroups = ref(0)
    const totalPages = ref(1)
    const currentPage = ref(1)
    const pageSize = ref(20)
    const sortBy = ref<'filesize' | 'member_count'>('filesize')
    const sortOrder = ref<'desc' | 'asc'>('desc')
    const rootFilter = ref<number | null>(null)
    const hasResults = computed(() => groups.value.length > 0)

    // Stats
    const stats = ref<Stats | null>(null)

    // Selection: map group_hash → Set<file_id>
    const selectedMap = ref<Record<string, Set<number>>>({})

    // Resolve dialog
    const showResolveDialog = ref(false)
    const resolveGroup = ref<DuplicateGroup | null>(null)

    // Settings editing
    const newRootName = ref('')
    const newRootPath = ref('')
    const newRootPriority = ref(10)
    const newExcludePattern = ref('')
    const newExtension = ref('')

    // Socket.IO
    let socket: ReturnType<typeof io> | null = null

    // ── Helpers ────────────────────────────────────────────────────────────

    function formatBytes(bytes: number): string {
      if (bytes === 0) return '0 B'
      const units = ['B', 'KB', 'MB', 'GB', 'TB']
      const i = Math.floor(Math.log(bytes) / Math.log(1024))
      return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
    }

    function formatDate(ts: number): string {
      return new Date(ts * 1000).toLocaleDateString()
    }

    function rootNameOf(rootId: number): string {
      const r = settings.value.scan_roots.find(r => r.id === rootId)
      return r ? r.name : `Root ${rootId}`
    }

    function rootColorOf(rootId: number): string {
      const colors = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399',
                      '#6366f1', '#10b981', '#f59e0b']
      return colors[rootId % colors.length]
    }

    // ── Settings ───────────────────────────────────────────────────────────

    async function loadSettings() {
      try {
        settings.value = await FileDuplicateService.getSettings()
        pageSize.value = settings.value.page_size
      } catch {
        // first run — defaults already set
      }
    }

    async function saveSettings() {
      await FileDuplicateService.saveSettings(settings.value)
      ElMessage.success('Settings saved')
    }

    function addRoot() {
      if (!newRootPath.value.trim()) return
      const roots = settings.value.scan_roots
      const id = roots.length > 0 ? Math.max(...roots.map(r => r.id)) + 1 : 1
      roots.push({
        id,
        name: newRootName.value.trim() || `Root ${id}`,
        path: newRootPath.value.trim(),
        priority: newRootPriority.value,
      })
      newRootName.value = ''
      newRootPath.value = ''
      newRootPriority.value = 10
    }

    function removeRoot(id: number) {
      settings.value.scan_roots = settings.value.scan_roots.filter(r => r.id !== id)
    }

    function addExcludePattern() {
      const p = newExcludePattern.value.trim()
      if (!p) return
      if (!settings.value.exclude_patterns.includes(p)) {
        settings.value.exclude_patterns.push(p)
      }
      newExcludePattern.value = ''
    }

    function removeExcludePattern(p: string) {
      settings.value.exclude_patterns = settings.value.exclude_patterns.filter(x => x !== p)
    }

    function addExtension() {
      const e = newExtension.value.trim().toLowerCase().replace(/^\./, '')
      if (!e) return
      if (!settings.value.include_extensions.includes(e)) {
        settings.value.include_extensions.push(e)
      }
      newExtension.value = ''
    }

    function removeExtension(e: string) {
      settings.value.include_extensions = settings.value.include_extensions.filter(x => x !== e)
    }

    // ── Phases ─────────────────────────────────────────────────────────────

    async function runPhase1() {
      isPhase1Running.value = true
      phaseProgress.value = { op_id: '', current: 0, total: 0, percentage: 0, message: 'Indexing files...' }
      try {
        await FileDuplicateService.startPhase1()
      } catch {
        isPhase1Running.value = false
      }
    }

    async function runPhase2() {
      isPhase2Running.value = true
      phaseProgress.value = { op_id: '', current: 0, total: 0, percentage: 0, message: 'Computing hashes...' }
      try {
        await FileDuplicateService.startPhase2()
      } catch {
        isPhase2Running.value = false
      }
    }

    async function runPhase3() {
      isPhase3Running.value = true
      phaseProgress.value = { op_id: '', current: 0, total: 0, percentage: 0, message: 'Building groups...' }
      try {
        await FileDuplicateService.startPhase3()
      } catch {
        isPhase3Running.value = false
      }
    }

    async function runFullPipeline() {
      try {
        await ElMessageBox.confirm(
          'This will index all files, compute hashes, and find duplicates. Continue?',
          'Run Full Pipeline',
          { confirmButtonText: 'Run', cancelButtonText: 'Cancel', type: 'info' }
        )
      } catch {
        return
      }
      isFullPipelineRunning.value = true
      try {
        await runPhase1()
        await waitForPhase('phase1')
        await runPhase2()
        await waitForPhase('phase2')
        await runPhase3()
        await waitForPhase('phase3')
        await loadGroupsPage(1)
        await loadStats()
      } finally {
        isFullPipelineRunning.value = false
      }
    }

    function waitForPhase(phase: string): Promise<void> {
      return new Promise(resolve => {
        const check = () => {
          const running = phase === 'phase1' ? isPhase1Running.value
                        : phase === 'phase2' ? isPhase2Running.value
                        : isPhase3Running.value
          if (!running) resolve()
          else setTimeout(check, 500)
        }
        check()
      })
    }

    async function stopAll() {
      if (isPhase1Running.value) await FileDuplicateService.stopPhase1()
      if (isPhase2Running.value) await FileDuplicateService.stopPhase2()
    }

    // ── Results ────────────────────────────────────────────────────────────

    async function loadGroupsPage(page: number) {
      currentPage.value = page
      try {
        const res = await FileDuplicateService.getGroups({
          page,
          page_size: pageSize.value,
          sort_by: sortBy.value,
          sort_order: sortOrder.value,
          root_id: rootFilter.value,
        })
        groups.value = res.groups
        totalGroups.value = res.total_groups
        totalPages.value = res.total_pages
        // init selection map for new groups
        for (const g of res.groups) {
          if (!selectedMap.value[g.group_hash]) {
            selectedMap.value[g.group_hash] = new Set()
          }
        }
      } catch (e: any) {
        ElMessage.error('Failed to load groups')
      }
    }

    async function loadStats() {
      try {
        stats.value = await FileDuplicateService.getStats()
      } catch {}
    }

    function onSortChange() {
      loadGroupsPage(1)
    }

    // ── Selection ──────────────────────────────────────────────────────────

    function isSelected(groupHash: string, fileId: number): boolean {
      return selectedMap.value[groupHash]?.has(fileId) ?? false
    }

    function toggleSelect(groupHash: string, fileId: number) {
      if (!selectedMap.value[groupHash]) {
        selectedMap.value[groupHash] = new Set()
      }
      const s = selectedMap.value[groupHash]
      if (s.has(fileId)) s.delete(fileId)
      else s.add(fileId)
    }

    function selectAllExceptFirst(group: DuplicateGroup) {
      if (!selectedMap.value[group.group_hash]) {
        selectedMap.value[group.group_hash] = new Set()
      }
      const s = selectedMap.value[group.group_hash]
      s.clear()
      // Keep first member (usually highest-priority root), select the rest
      group.members.slice(1).forEach(m => s.add(m.id))
    }

    function selectByRoot(group: DuplicateGroup, rootId: number) {
      if (!selectedMap.value[group.group_hash]) {
        selectedMap.value[group.group_hash] = new Set()
      }
      const s = selectedMap.value[group.group_hash]
      group.members.filter(m => m.root_id === rootId).forEach(m => s.add(m.id))
    }

    function deselectAll(groupHash: string) {
      if (selectedMap.value[groupHash]) {
        selectedMap.value[groupHash].clear()
      }
    }

    function selectedCount(groupHash: string): number {
      return selectedMap.value[groupHash]?.size ?? 0
    }

    // ── Actions ────────────────────────────────────────────────────────────

    async function trashSelected(group: DuplicateGroup) {
      const ids = [...(selectedMap.value[group.group_hash] ?? [])]
      if (ids.length === 0) {
        ElMessage.warning('No files selected')
        return
      }
      const keepCount = group.member_count - ids.length
      if (keepCount === 0) {
        try {
          await ElMessageBox.confirm(
            'You are about to trash ALL files in this group. Continue?',
            'Warning',
            { type: 'warning', confirmButtonText: 'Trash All', cancelButtonText: 'Cancel' }
          )
        } catch { return }
      }
      try {
        const res = await FileDuplicateService.moveToTrash(ids)
        ElMessage.success(`Moved ${res.moved.length} file(s) to trash`)
        if (res.errors.length) ElMessage.error(`${res.errors.length} error(s)`)
        await loadGroupsPage(currentPage.value)
        await loadStats()
      } catch {
        ElMessage.error('Failed to move files')
      }
    }

    function openResolveDialog(group: DuplicateGroup) {
      resolveGroup.value = group
      // Auto-select all except first
      selectAllExceptFirst(group)
      showResolveDialog.value = true
    }

    async function confirmResolve() {
      if (!resolveGroup.value) return
      const group = resolveGroup.value
      const trashIds = [...(selectedMap.value[group.group_hash] ?? [])]
      const keepIds = group.members.filter(m => !trashIds.includes(m.id)).map(m => m.id)
      try {
        const res = await FileDuplicateService.resolveGroup(keepIds, trashIds)
        ElMessage.success(`Moved ${res.moved.length} file(s) to trash`)
        showResolveDialog.value = false
        await loadGroupsPage(currentPage.value)
        await loadStats()
      } catch {
        ElMessage.error('Failed to resolve group')
      }
    }

    // ── WebSocket ──────────────────────────────────────────────────────────

    function connectSocket() {
      socket = io(BACKEND_BASE_URL)
      socket.on('file-duplicate:progress', (data: PhaseProgress) => {
        phaseProgress.value = data
      })
      socket.on('file-duplicate:complete', (data: any) => {
        phaseProgress.value = null
        isPhase1Running.value = false
        isPhase2Running.value = false
        isPhase3Running.value = false
        ElMessage.success(`Phase complete: ${data.result?.message || 'done'}`)
        loadStats()
      })
      socket.on('file-duplicate:error', (data: any) => {
        phaseProgress.value = null
        isPhase1Running.value = false
        isPhase2Running.value = false
        isPhase3Running.value = false
        ElMessage.error(`Error: ${data.error}`)
      })
    }

    // ── Lifecycle ──────────────────────────────────────────────────────────

    onMounted(async () => {
      await loadSettings()
      await loadStats()
      connectSocket()
      // If groups exist from a previous session, load them
      if (stats.value && stats.value.group_stats.total_groups > 0) {
        await loadGroupsPage(1)
      }
    })

    onUnmounted(() => {
      socket?.disconnect()
    })

    return {
      settings, showSettings,
      isPhase1Running, isPhase2Running, isPhase3Running, isFullPipelineRunning,
      phaseProgress,
      groups, totalGroups, totalPages, currentPage, pageSize,
      sortBy, sortOrder, rootFilter, hasResults,
      stats,
      selectedMap,
      showResolveDialog, resolveGroup,
      newRootName, newRootPath, newRootPriority,
      newExcludePattern, newExtension,
      // methods
      formatBytes, formatDate, rootNameOf, rootColorOf,
      loadSettings, saveSettings,
      addRoot, removeRoot, addExcludePattern, removeExcludePattern,
      addExtension, removeExtension,
      runPhase1, runPhase2, runPhase3, runFullPipeline, stopAll,
      loadGroupsPage, loadStats, onSortChange,
      isSelected, toggleSelect, selectAllExceptFirst, selectByRoot,
      deselectAll, selectedCount,
      trashSelected, openResolveDialog, confirmResolve,
    }
  }
})
