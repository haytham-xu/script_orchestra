/**
 * File-Git Repository Detail — UI logic.
 *
 * Buttons (REQUIREMENTS §3.13):
 *   Push, Pull, Manual Upload, Post Manual Upload,
 *   Pre Manual Download, Post Manual Download,
 *   Diff, Rebuild Local Index, Rebuild Cloud Index,
 *   Cleanup, Resume (visible only when lock=true)
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  FileGitService,
  type CleanupMode,
  type DiffEntry,
  type QueueStatus,
  type RepoConfig,
  type Repository,
} from '../service/FileGitService'

export function useFileGitRepoDetail() {
  const route = useRoute()
  const router = useRouter()
  const repoId = ref<string>(route.params.id as string)

  const repo = ref<Repository | null>(null)
  const queue = ref<QueueStatus | null>(null)
  const config = ref<RepoConfig | null>(null)

  const isLoading = ref(false)
  const isBusy = ref(false)              // any single action in flight

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
  // Sync filter (selective sync) tree
  // ------------------------------------------------------------------

  // The sync decision, edited locally and PUT on save. The backend resolves
  // each path by longest-prefix match (parent→child cascade, override wins).
  const syncDecision = ref<{ checked_prefixes: string[]; unchecked_overrides: string[] }>({
    checked_prefixes: [],
    unchecked_overrides: [],
  })
  const syncDirty = ref(false)

  // el-tree lazy loader: fetch a node's children from the backend.
  async function loadSyncChildren(node: any, resolve: (data: any[]) => void) {
    const parentPath = node.level === 0 ? '' : node.data.path
    try {
      const res = node.level === 0
        ? await FileGitService.getSyncFilter(repoId.value)
        : await FileGitService.getSyncFilterChildren(repoId.value, parentPath)
      if (node.level === 0 && res.success && (res as any).filter) {
        syncDecision.value = (res as any).filter
        syncDirty.value = false
      }
      const children = (res as any).children || []
      resolve(children.map((c: any) => ({
        label: c.name,
        path: c.path,
        isLeaf: !c.is_dir,
        kind: c.kind,
        synced: c.synced,
        checked: c.checked,
      })))
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to load sync tree')
      resolve([])
    }
  }

  // Toggle a node's sync decision. Setting checked → add to checked_prefixes
  // and drop any override; unchecking → add an unchecked_override.
  function toggleSyncNode(path: string, checked: boolean) {
    const dec = syncDecision.value
    const strip = (arr: string[]) => arr.filter((p) => p !== path)
    if (checked) {
      dec.checked_prefixes = [...new Set([...strip(dec.checked_prefixes), path])]
      dec.unchecked_overrides = strip(dec.unchecked_overrides)
    } else {
      dec.unchecked_overrides = [...new Set([...strip(dec.unchecked_overrides), path])]
      dec.checked_prefixes = strip(dec.checked_prefixes)
    }
    syncDirty.value = true
  }

  async function saveSyncFilter() {
    try {
      const res = await FileGitService.updateSyncFilter(repoId.value, syncDecision.value)
      if (res.success) {
        syncDirty.value = false
        ElMessage.success(res.message || 'Sync filter saved (applies on next push/pull)')
      } else {
        ElMessage.error(res.error || 'Failed to save sync filter')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to save sync filter')
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
    }
  }

  const push = () => runAction('Push', () => FileGitService.push(repoId.value))
  const pull = () => runAction('Pull', () => FileGitService.pull(repoId.value))
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

  function goBack() {
    router.push('/file-git')
  }

  // ------------------------------------------------------------------

  onMounted(loadAll)

  return {
    repoId,
    repo,
    queue,
    config,
    rootPrefix,
    finalRemotePath,
    syncDecision,
    syncDirty,
    loadSyncChildren,
    toggleSyncNode,
    saveSyncFilter,
    isLoading,
    isBusy,
    isLocked,
    lockActionType,
    pendingUploadCount,
    pendingQueueCount,
    isEncrypted,
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
    cleanup,
    openFolder,
    goBack,
  }
}
