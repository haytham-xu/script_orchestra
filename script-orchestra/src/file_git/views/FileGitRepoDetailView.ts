/**
 * File-Git Repository Detail — UI logic.
 *
 * Buttons (REQUIREMENTS §3.13):
 *   Push, Pull, Manual Upload, Post Manual Upload,
 *   Pre Manual Download, Post Manual Download,
 *   Diff, Rebuild Local Index, Rebuild Cloud Index,
 *   Cleanup, Resume (visible only when lock=true)
 */
import { computed, onMounted, onUnmounted, ref, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  FileGitService,
  type CleanupMode,
  type DiffEntry,
  type FileTreeEntry,
  type FileLogRecord,
  type QueueItem,
  type QueueStatus,
  type RepoConfig,
  type Repository,
  type SyncFilterChild,
  type SyncMode,
} from '../service/FileGitService'
import { fileGitWS } from '../service/FileGitWebSocket'

export interface ProgressItem {
  path: string
  action: string
  status: 'pending' | 'active' | 'done' | 'error'
  detail: string
}

export function useFileGitRepoDetail() {
  const route = useRoute()
  const router = useRouter()
  const repoId = ref<string>(route.params.id as string)

  const repo = ref<Repository | null>(null)
  const queue = ref<QueueStatus | null>(null)
  const config = ref<RepoConfig | null>(null)
  const cloudIndexSyncedAt = ref<string | null>(null)

  const isLoading = ref(false)
  const isBusy = ref(false)              // any single action in flight

  // Progress tracking (WebSocket-driven per-file progress)
  const progressItems = ref<ProgressItem[]>([])
  const progressVisible = ref(false)
  const progressHasError = computed(() => progressItems.value.some(i => i.status === 'error'))
  const progressActiveCount = computed(() => progressItems.value.filter(i => i.status === 'active').length)

  // Diff panel state
  const diffAdded = ref<DiffEntry[]>([])
  const diffModified = ref<DiffEntry[]>([])
  const diffDeleted = ref<DiffEntry[]>([])
  const diffTotalLocal = ref(0)
  const diffTotalCloud = ref(0)
  const diffMessage = ref('')

  // Config edit state (buffered so the user can edit before saving)
  const editPassword = ref('')
  const editRemotePath = ref('')
  const editHookDays = ref<number | null>(null)

  // Manual upload state
  const manualSubpath = ref('')

  // File tree (lazy, one level at a time)
  const fileTreeKey = ref(0)   // bump to force el-tree remount on refresh
  const filesLoading = ref(false)

  async function loadFileTreeChildren(node: any, resolve: (data: any[]) => void) {
    const relPath = node.level === 0 ? '' : node.data.path
    try {
      const res = await FileGitService.getFilesTree(repoId.value, relPath)
      if (res.success) {
        resolve(res.entries.map((e: FileTreeEntry) => ({
          label: e.name,
          path: e.path,
          is_dir: e.is_dir,
          size: e.size,
          isLeaf: !e.is_dir,
        })))
      } else {
        resolve([])
      }
    } catch {
      resolve([])
    }
  }

  function refreshFileTree() {
    fileTreeKey.value += 1
  }

  // Queue panel
  const queueItems = ref<QueueItem[]>([])
  const queueStats = ref({ total: 0, done: 0, in_progress: 0, error: 0, todo: 0 })
  let queuePollTimer: ReturnType<typeof setTimeout> | null = null

  // Baidu root prefix (from global settings) — used to preview the final
  // remote path the repo maps to on the cloud.
  const rootPrefix = ref('')

  // The absolute cloud path this repo's files land under, combining the
  // global root_prefix with the repo's remote_path. Normalizes slashes.
  const finalRemotePath = computed(() => {
    const root = (rootPrefix.value || '').replace(/\/+$/, '')
    const rp = (editRemotePath.value || '').trim().replace(/^\/+/, '').replace(/\/+$/, '')
    if (!rp) return ''
    return root ? `${root}/${rp}` : `/${rp}`
  })

  // ------------------------------------------------------------------
  // Sync filter — 3-mode system (immediate PUT per change)
  // ------------------------------------------------------------------

  const syncTreeRef = ref<any>(null)
  const syncChildren = ref<SyncFilterChild[]>([])

  async function loadSyncChildren(node: any, resolve: (data: any[]) => void) {
    const parentPath = node.level === 0 ? '' : node.data.path
    try {
      let children: SyncFilterChild[]
      if (node.level === 0) {
        const res = await FileGitService.getSyncFilter(repoId.value)
        children = res.children || []
        syncChildren.value = children
      } else {
        const res = await FileGitService.getSyncFilterChildren(repoId.value, parentPath)
        children = res.children || []
      }
      const nodes = children.map((c) => ({
        label: c.name,
        path: c.path,
        is_dir: c.is_dir,
        in_local: c.in_local,
        in_remote: c.in_remote,
        mode: c.mode,
        status: c.status,
        can_set: c.can_set,
        isLeaf: !c.is_dir,
      }))
      resolve(nodes)
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to load sync tree')
      resolve([])
    }
  }

  async function setSyncNodeMode(path: string, mode: SyncMode) {
    try {
      const res = await FileGitService.setSyncMode(repoId.value, path, mode)
      if (!res.success) {
        ElMessage.error(res.error || 'Failed to set mode')
        return
      }
      ElMessage.success(`Set ${path || '(root)'} → ${mode}`)
      // Reload tree from root (mode changes cascade, so a full refresh is simplest)
      syncTreeKey.value += 1
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to set mode')
    }
  }

  const syncTreeKey = ref(0)

  // ------------------------------------------------------------------
  // File Log — per-action structured log viewer
  // ------------------------------------------------------------------

  const fileLogFolders = ref<string[]>([])
  const fileLogFolder = ref<string>('')
  const fileLogRecords = ref<FileLogRecord[]>([])
  const fileLogLoading = ref(false)

  async function loadFileLogFolders() {
    try {
      const res = await FileGitService.listActionFolders(repoId.value)
      if (res.success) {
        fileLogFolders.value = res.folders
        if (res.folders.length > 0 && !fileLogFolder.value) {
          fileLogFolder.value = res.folders[0]
          await loadFileLog(res.folders[0])
        }
      }
    } catch {
      // non-fatal
    }
  }

  async function loadFileLog(folder: string) {
    if (!folder) return
    fileLogLoading.value = true
    try {
      const res = await FileGitService.getFileLog(repoId.value, folder)
      if (res.success) {
        fileLogRecords.value = res.records
        fileLogFolder.value = folder
      } else {
        ElMessage.error(res.error || 'Failed to load file log')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to load file log')
    } finally {
      fileLogLoading.value = false
    }
  }

  // ------------------------------------------------------------------
  // Derived
  // ------------------------------------------------------------------

  const isLocked = computed(() => queue.value?.lock === true)
  const lockActionType = computed(() => queue.value?.action_type ?? null)
  const pendingUploadCount = computed(() => queue.value?.pending_upload_count ?? 0)
  const pendingQueueCount = computed(() => queue.value?.pending_count ?? 0)
  const isEncrypted = computed(() => repo.value?.mode === 'ENCRYPTED')

  // Which buttons are enabled given the current lock state?
  // (REQUIREMENTS §3.8 lock semantics)
  const canPushPull = computed(() => !isBusy.value && !isLocked.value)
  const canResume = computed(() =>
    !isBusy.value && isLocked.value &&
    (lockActionType.value === 'push' || lockActionType.value === 'pull')
  )
  const canManualUploadPrepare = computed(() =>
    !isBusy.value && !isLocked.value
  )
  const canPostManualUpload = computed(() =>
    !isBusy.value && isLocked.value && lockActionType.value === 'manual_upload'
  )
  const canPreManualDownload = computed(() =>
    !isBusy.value && !isLocked.value
  )
  const canPostManualDownload = computed(() =>
    !isBusy.value && isLocked.value && lockActionType.value === 'manual_download'
  )
  // Read-only actions can run in most states
  const canDiff = computed(() => !isBusy.value)
  const canRebuildLocal = computed(() => !isBusy.value)
  const canRebuildCloud = computed(() => !isBusy.value && !isLocked.value)
  const canCleanup = computed(() => !isBusy.value)

  // ------------------------------------------------------------------
  // Loaders
  // ------------------------------------------------------------------

  async function loadAll() {
    isLoading.value = true
    try {
      await Promise.all([loadStatus(), loadConfig(), loadRootPrefix()])
    } finally {
      isLoading.value = false
    }
  }

  async function loadStatus() {
    try {
      const res = await FileGitService.getStatus(repoId.value)
      if (res.success) {
        repo.value = res.repo
        queue.value = res.queue
        cloudIndexSyncedAt.value = res.cloud_index_synced_at ?? null
      } else if (res.error) {
        ElMessage.error(res.error)
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to load status')
    }
  }

  async function loadConfig() {
    try {
      const res = await FileGitService.getConfig(repoId.value)
      if (res.success && res.config) {
        config.value = res.config
        editPassword.value = ''
        editRemotePath.value = res.config.remote_path
        editHookDays.value = res.config.hook_retention_days ?? 7
      } else if (res.error) {
        ElMessage.error(res.error)
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to load config')
    }
  }

  async function loadRootPrefix() {
    try {
      const res = await FileGitService.getSettings()
      if (res.success && res.settings) {
        rootPrefix.value = res.settings.baidu_cloud?.root_prefix || ''
      }
    } catch {
      // Non-fatal: the preview just omits the root prefix.
    }
  }

  // ------------------------------------------------------------------
  // Config save
  // ------------------------------------------------------------------

  async function saveConfig() {
    isBusy.value = true
    try {
      const patch: any = {
        remote_path: editRemotePath.value.trim(),
        hook_retention_days: editHookDays.value ?? 7,
      }
      // Only send password when the user typed a new one
      if (editPassword.value) patch.password = editPassword.value
      const res = await FileGitService.updateConfig(repoId.value, patch)
      if (res.success) {
        ElMessage.success('Config saved')
        editPassword.value = ''
        await loadConfig()
      } else {
        ElMessage.error(res.error || 'Failed to save config')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to save config')
    } finally {
      isBusy.value = false
    }
  }

  // ------------------------------------------------------------------
  // Commands
  // ------------------------------------------------------------------

  async function runAction<T>(
    label: string,
    fn: () => Promise<T & { success: boolean; message?: string; error?: string }>,
    onSuccess?: (data: T) => void,
  ): Promise<void> {
    isBusy.value = true
    try {
      const res: any = await fn()
      if (res.success) {
        ElMessage.success(res.message || `${label} done`)
        onSuccess?.(res)
      } else {
        ElMessage.error(res.error || res.message || `${label} failed`)
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || `${label} failed`)
    } finally {
      isBusy.value = false
      await loadStatus()
      await loadFileLogFolders()
    }
  }

  const push = () => _pushWithDryRun()
  const pull = () => _pullWithDryRun()

  function startProgressTracking(operation: string) {
    progressItems.value = []
    fileGitWS.connect()
    fileGitWS.onProgress(repoId.value, (evt) => {
      progressVisible.value = true
      if (evt.phase === 'queue') {
        // message format: "ACTION path/to/file"
        const spaceIdx = evt.message.indexOf(' ')
        const action = spaceIdx > -1 ? evt.message.slice(0, spaceIdx) : evt.message
        const path = spaceIdx > -1 ? evt.message.slice(spaceIdx + 1) : ''
        const existing = progressItems.value.find(i => i.path === path)
        if (existing) {
          existing.status = 'active'
          existing.detail = action
        } else {
          progressItems.value.push({ path, action, status: 'active', detail: '' })
        }
      } else {
        // phase-level event (lock, scan, cloud_index, hook)
        const label = `(${evt.phase})`
        const existing = progressItems.value.find(i => i.path === label)
        if (existing) {
          existing.status = 'active'
          existing.detail = evt.message
        } else {
          progressItems.value.push({ path: label, action: operation, status: 'active', detail: evt.message })
        }
      }
    })
    fileGitWS.onStatus(repoId.value, (evt) => {
      // Only update visual state — runAction's finally handles isBusy and data reload
      progressItems.value.forEach(i => {
        if (i.status === 'active') i.status = evt.status === 'error' ? 'error' : 'done'
      })
    })
  }

  function _finishProgressTracking() {
    fileGitWS.off(repoId.value)
    progressItems.value.forEach(i => { if (i.status === 'active') i.status = 'done' })
  }

  async function _pushWithDryRun() {
    if (isBusy.value) return
    isBusy.value = true
    try {
      const dr = await FileGitService.pushDryRun(repoId.value)
      if (dr.success && dr.conflicts.length > 0) {
        const lines = dr.conflicts.map((c) => `• ${c.path}  [${c.issue}] → ${c.action}`).join('\n')
        try {
          await ElMessageBox.confirm(
            `Push has ${dr.conflicts.length} issue(s):\n\n${lines}\n\nContinue?`,
            'Push Dry-Run',
            { confirmButtonText: 'Push anyway', cancelButtonText: 'Cancel', type: 'warning' },
          )
        } catch {
          isBusy.value = false
          return
        }
      }
    } catch {
      // dry-run failure is non-fatal — proceed with push
    } finally {
      isBusy.value = false
    }
    startProgressTracking('push')
    return runAction('Push', () => FileGitService.push(repoId.value), _finishProgressTracking)
  }

  async function _pullWithDryRun() {
    if (isBusy.value) return
    isBusy.value = true
    try {
      const dr = await FileGitService.pullDryRun(repoId.value)
      if (dr.success && dr.conflicts.length > 0) {
        const lines = dr.conflicts.map((c) => `• ${c.path}  [${c.issue}] → ${c.action}`).join('\n')
        try {
          await ElMessageBox.confirm(
            `Pull has ${dr.conflicts.length} issue(s):\n\n${lines}\n\nContinue?`,
            'Pull Dry-Run',
            { confirmButtonText: 'Pull anyway', cancelButtonText: 'Cancel', type: 'warning' },
          )
        } catch {
          isBusy.value = false
          return
        }
      }
    } catch {
      // dry-run failure is non-fatal — proceed with pull
    } finally {
      isBusy.value = false
    }
    startProgressTracking('pull')
    return runAction('Pull', () => FileGitService.pull(repoId.value), _finishProgressTracking)
  }

  const resume = () => runAction('Resume', () => FileGitService.resume(repoId.value))

  const manualUpload = () => runAction(
    'Manual Upload',
    () => FileGitService.manualUpload(repoId.value, manualSubpath.value.trim()),
  )
  const postManualUpload = () => runAction(
    'Post Manual Upload',
    () => FileGitService.postManualUpload(repoId.value),
  )
  const preManualDownload = () => runAction(
    'Pre Manual Download',
    () => FileGitService.preManualDownload(repoId.value),
  )
  const postManualDownload = () => runAction(
    'Post Manual Download',
    () => FileGitService.postManualDownload(repoId.value),
  )

  async function runDiff() {
    isBusy.value = true
    try {
      const res = await FileGitService.diff(repoId.value)
      if (res.success) {
        diffAdded.value = res.added
        diffModified.value = res.modified
        diffDeleted.value = res.deleted
        diffTotalLocal.value = res.total_local
        diffTotalCloud.value = res.total_cloud
        diffMessage.value = res.message || ''
      } else {
        ElMessage.error('Diff failed')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Diff failed')
    } finally {
      isBusy.value = false
    }
  }

  const rebuildLocalIndex = () => runAction(
    'Rebuild Local Index',
    () => FileGitService.rebuildLocalIndex(repoId.value),
  )

  const applyFilter = () => {
    startProgressTracking('apply_filter')
    return runAction('Apply Filter', () => FileGitService.applyFilter(repoId.value), _finishProgressTracking)
  }

  async function rebuildCloudIndex() {
    if (isBusy.value) return
    // Estimate first
    isBusy.value = true
    try {
      const est = await FileGitService.estimateRebuildCloudIndex(repoId.value)
      if (!est.success) {
        ElMessage.error(est.error || 'Failed to estimate')
        return
      }
      const count = est.approximate_file_count ?? 0
      const remoteRoot = est.remote_root ?? '?'
      await ElMessageBox.confirm(
        `This will list all files under "${remoteRoot}" (~${count} entries) and rebuild cloud_index.json. It hits the cloud API ${count} times. Continue?`,
        'Rebuild Cloud Index',
        { confirmButtonText: 'Rebuild', cancelButtonText: 'Cancel', type: 'warning' },
      )
    } catch {
      isBusy.value = false
      return // user cancelled
    }

    // Confirmed — run
    try {
      const res = await FileGitService.rebuildCloudIndex(repoId.value)
      if (res.success) {
        ElMessage.success(res.message || 'Cloud index rebuilt')
      } else {
        ElMessage.error(res.error || 'Rebuild failed')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Rebuild failed')
    } finally {
      isBusy.value = false
      await loadStatus()
    }
  }

  async function cleanup(mode: CleanupMode) {
    if (isBusy.value) return
    isBusy.value = true
    try {
      const dry = await FileGitService.cleanupDryRun(repoId.value, mode)
      if (!dry.success) {
        ElMessage.error(dry.error || 'Cleanup dry-run failed')
        return
      }
      const trashN = dry.trash_candidates?.length ?? 0
      const actionN = dry.action_candidates?.length ?? 0
      await ElMessageBox.confirm(
        `Cleanup (${mode}) will remove ${trashN} trash folder(s) and ${actionN} action folder(s). Continue?`,
        'Cleanup',
        { confirmButtonText: 'Delete', cancelButtonText: 'Cancel', type: 'warning' },
      )
    } catch {
      isBusy.value = false
      return
    }
    try {
      const res = await FileGitService.cleanup(repoId.value, mode)
      if (res.success) {
        ElMessage.success(res.message || 'Cleanup complete')
      } else {
        ElMessage.error(res.error || 'Cleanup failed')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Cleanup failed')
    } finally {
      isBusy.value = false
      await loadStatus()
    }
  }

  const openFolder = () => runAction(
    'Open folder',
    () => FileGitService.openFolder(repoId.value),
  )

  async function loadQueue() {
    try {
      const res = await FileGitService.getQueue(repoId.value)
      if (res.success) {
        queueItems.value = res.items
        queueStats.value = {
          total: res.total,
          done: res.done,
          in_progress: res.in_progress,
          error: res.error,
          todo: res.todo,
        }
        // Auto-poll while items are active
        if (res.lock && (res.in_progress > 0 || res.todo > 0)) {
          queuePollTimer = setTimeout(loadQueue, 2000)
        } else {
          queuePollTimer = null
        }
      }
    } catch {
      // Non-fatal
    }
  }

  function stopQueuePoll() {
    if (queuePollTimer !== null) {
      clearTimeout(queuePollTimer)
      queuePollTimer = null
    }
  }

  function goBack() {
    router.push('/file-git')
  }

  // ------------------------------------------------------------------

  onMounted(() => { loadAll(); loadQueue(); loadFileLogFolders() })
  onUnmounted(() => { stopQueuePoll(); fileGitWS.off(repoId.value) })

  return {
    repoId,
    repo,
    queue,
    config,
    rootPrefix,
    finalRemotePath,
    cloudIndexSyncedAt,
    syncTreeRef,
    syncTreeKey,
    syncChildren,
    loadSyncChildren,
    setSyncNodeMode,
    isLoading,
    isBusy,
    isLocked,
    lockActionType,
    pendingUploadCount,
    pendingQueueCount,
    isEncrypted,
    progressItems,
    progressVisible,
    progressHasError,
    progressActiveCount,
    canPushPull,
    canResume,
    canManualUploadPrepare,
    canPostManualUpload,
    canPreManualDownload,
    canPostManualDownload,
    canDiff,
    canRebuildLocal,
    canRebuildCloud,
    canCleanup,
    diffAdded,
    diffModified,
    diffDeleted,
    diffTotalLocal,
    diffTotalCloud,
    diffMessage,
    editPassword,
    editRemotePath,
    editHookDays,
    manualSubpath,
    loadAll,
    loadStatus,
    loadConfig,
    saveConfig,
    push,
    pull,
    resume,
    manualUpload,
    postManualUpload,
    preManualDownload,
    postManualDownload,
    runDiff,
    rebuildLocalIndex,
    rebuildCloudIndex,
    applyFilter,
    cleanup,
    openFolder,
    goBack,
    fileTreeKey,
    filesLoading,
    loadFileTreeChildren,
    refreshFileTree,
    queueItems,
    queueStats,
    loadQueue,
    fileLogFolders,
    fileLogFolder,
    fileLogRecords,
    fileLogLoading,
    loadFileLogFolders,
    loadFileLog,
  }
}
