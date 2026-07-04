/**
 * Video Duplicate Finder — View composable.
 *
 * DECOUPLED: no imports from `@/duplicate_finder/*`.
 *
 * Structural parallel to image-version `useDuplicateFinderView`, but with
 * video-specific adaptations:
 *
 *   - Auto-selection rules are computed server-side (D-14). Client just
 *     reads `auto_delete_suggestion` on each VideoInfo — no client-side
 *     regex / codec ranking.
 *   - Media preview via <video> element sourcing /preview; thumbnail via
 *     /thumbnail. See VideoDuplicateFinderService.getThumbnailUrl /
 *     getPreviewUrl.
 *   - No Replace / Deep Replace (S7.2 pending)
 *   - No Compare / Compare-All (S6 pending)
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElLoading, ElMessage, ElMessageBox } from 'element-plus'
import io, { Socket } from 'socket.io-client'
import { v4 as uuidv4 } from 'uuid'

import { BACKEND_BASE_URL } from '@/basic/Constants'
import { VideoDuplicateFinderService } from '../service/VideoDuplicateFinderService'
import type {
  Phase1Summary,
  Phase2Summary,
  Phase25Summary,
  Phase3SortBy,
  PhaseProgress,
  Settings,
  VideoGroup,
  VideoInfo,
  WhitelistGroup,
} from '../service/Model'


// -----------------------------------------------------------------------------
// Small helpers (pure functions, kept outside the composable to be reusable
// and easy to unit-test if we ever wire up Vitest).
// -----------------------------------------------------------------------------

function getFilenameFromPath(filePath: string): string {
  const lastSep = Math.max(filePath.lastIndexOf('/'), filePath.lastIndexOf('\\'))
  return lastSep >= 0 ? filePath.substring(lastSep + 1) : filePath
}

function splitPath(filePath: string): string[] {
  return filePath.replace(/\\/g, '/').split('/')
}

function formatFileSize(bytes: number | null | undefined): string {
  if (!bytes && bytes !== 0) return '?'
  if (bytes === 0) return '0 B'
  const k = 1024
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(k)))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${units[i]}`
}

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds && seconds !== 0) return '?'
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const totalSec = Math.floor(seconds)
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

/**
 * Format an average-bitrate estimate (bits per second) into a display string.
 * Uses SI-style k/M/G suffixes (1000-based) since bitrates are traditionally
 * quoted that way (a "10 Mbps" video means 10,000,000 bits/sec, not 2^20).
 *
 * The value comes from the server-side `filesize * 8 / duration` estimate
 * (D-23 / Q-06 resolution) — accurate for ranking, approximate as an
 * absolute number.
 */
function formatBitrate(bitrate: number | null | undefined): string {
  if (bitrate === null || bitrate === undefined) return '?'
  if (bitrate <= 0) return '0 bps'
  if (bitrate < 1_000) return `${bitrate} bps`
  if (bitrate < 1_000_000) return `${(bitrate / 1_000).toFixed(0)} kbps`
  if (bitrate < 1_000_000_000) return `${(bitrate / 1_000_000).toFixed(1)} Mbps`
  return `${(bitrate / 1_000_000_000).toFixed(2)} Gbps`
}

function formatTimestamp(unixSec: number): string {
  return new Date(unixSec * 1000).toLocaleString()
}

/** Extract "1080p" style label from height. */
function formatResolutionLabel(width: number | null | undefined, height: number | null | undefined): string {
  if (!width || !height) return '?'
  return `${width}x${height}`
}

/** Cross-platform: parent directory of a file path. */
function dirnameOf(filePath: string): string {
  const lastSep = Math.max(filePath.lastIndexOf('/'), filePath.lastIndexOf('\\'))
  return lastSep >= 0 ? filePath.substring(0, lastSep) : ''
}


// -----------------------------------------------------------------------------
// Composable: useVideoDuplicateFinderView()
//
// Returns an object with all reactive state + method references. The `.vue`
// template destructures what it needs.
// -----------------------------------------------------------------------------

export function useVideoDuplicateFinderView() {

  // ========================================================================
  // Core state
  // ========================================================================

  const threshold = ref<number>(80)

  // Long-running task guards (one boolean per phase)
  const isPhase1Running = ref(false)
  const isPhase2Running = ref(false)
  const isPhase25Running = ref(false)
  const isPhase3Running = ref(false)
  const isFullPipelineRunning = ref(false)
  const isDeleting = ref(false)
  const isVerifying = ref(false)
  const isSaving = ref(false)
  const isBulkWhitelisting = ref(false)
  const isLoadingWhitelist = ref(false)
  const isCleaningDb = ref(false)
  // Tracks whether the initial GET /settings succeeded. saveAllSettings
  // refuses to run before this flips true (Tier-2 review).
  const settingsLoaded = ref<boolean>(false)

  // Phase 1 progress uses `scanProgress` (image-version parity); Phase 2/2.5/3
  // use `phaseProgress` (single struct describing which phase is running).
  const phaseProgress = ref<PhaseProgress>({
    phase: 0, message: '', details: '',
    current: 0, total: 0, percentage: 0,
  })

  const phase1Summary = ref<Phase1Summary | null>(null)
  const phase2Summary = ref<Phase2Summary | null>(null)
  const phase25Summary = ref<Phase25Summary | null>(null)
  const phase25Meta = ref<Record<string, string>>({})

  // Phase 3 result state — one page of groups, plus paging metadata
  const scanResult = ref<{
    scan_id:            string
    duplicate_groups:   VideoGroup[]
    total_duplicates:   number
    duplicate_count:    number
    total_files:        number
  } | null>(null)

  const currentPage = ref<number>(1)
  const pageSize = ref<number>(100)
  const totalPages = ref<number>(1)
  const totalGroupsAll = ref<number>(0)
  const totalFilesInDb = ref<number>(0)
  const isLoadingPage = ref(false)
  // Request-generation counter — stale Phase 3 responses (from earlier clicks
  // that lost the race) are ignored if a newer load has started.
  const phase3LoadGen = ref<number>(0)

  const sortBy = ref<Phase3SortBy>('folder_dup_count')
  const sortOrder = ref<'asc' | 'desc'>('desc')

  const SORT_OPTIONS: { value: Phase3SortBy; label: string }[] = [
    { value: 'folder_dup_count',         label: 'Hot folder (most duplicates first)' },
    { value: 'representative_file_path', label: 'Folder + filename' },
    { value: 'member_count',             label: 'Group size (member count)' },
    { value: 'max_filesize',             label: 'Max file size' },
    { value: 'min_filesize',             label: 'Min file size' },
    { value: 'max_duration',             label: 'Longest video' },
    { value: 'min_duration',             label: 'Shortest video' },
    { value: 'max_bitrate',              label: 'Highest bitrate' },
    { value: 'min_bitrate',              label: 'Lowest bitrate' },
    { value: 'max_mtime',                label: 'Newest modified' },
    { value: 'min_mtime',                label: 'Oldest modified' },
  ]

  // Selection state: paths marked for deletion (persists across pages)
  const selectedForDelete = ref<Set<string>>(new Set())

  // Settings — hydrated from GET /settings on mount
  const settings = ref<Settings>({
    delete_target_path:    '',
    similarity_threshold:  80,
    folder_paths:          [],
    exclude_folder_paths:  [],
    max_cpu_cores:         2,
    n_frames:              8,
    page_size:             100,
    companion_extensions:  ['.srt', '.ass', '.vtt', '.sub', '.idx',
                            '.nfo', '.jpg', '.png', '.chapters'],
    auto_selection_rules: {
      auto_mark_lower_resolution: true,
      auto_mark_lower_bitrate:    true,
      auto_mark_smaller_filesize: false,
      auto_mark_older_codec:      true,
      auto_mark_numbered_copies:  true,
      prefer_folders:             [],
    },
    phase1: {
      worker_handler_size:      1,
      db_commit_batch_size:     50,
      progress_update_interval: 10,
      ipc_chunk_size:           1,
      scan_delay:               0,
      compute_delay:            0,
    },
    phase2: {
      worker_handler_size:      1,
      db_commit_batch_size:     100,
      progress_update_interval: 100,
      ipc_chunk_size:           10,
      compare_delay:            0,
    },
  })

  // Video preview dialog — shows <video> for a clicked file
  const showVideoPreviewDialog = ref(false)
  const previewVideo = ref<VideoInfo | null>(null)
  const previewVideoUrl = ref<string>('')

  // Whitelist drawer
  const showWhitelistDrawer = ref(false)
  const whitelistGroups = ref<WhitelistGroup[]>([])

  // Bulk-whitelist preview dialog (used by "whitelist all on this page" +
  // "deep whitelist under this folder")
  const showBulkWhitelistDialog = ref(false)
  const bulkWhitelistPreview = ref<{
    groups:      VideoGroup[]
    payload:     number[][]
    groupCount:  number
    videoCount:  number
    contextLabel: string   // "current page" or `folder: <path>`
  }>({ groups: [], payload: [], groupCount: 0, videoCount: 0, contextLabel: '' })


  // ========================================================================
  // WebSocket
  // ========================================================================

  let socket: Socket | null = null

  function connectWebSocket() {
    if (socket && socket.connected) {
      console.log('[FE DEBUG] WebSocket already connected — skip re-connect')
      return
    }
    console.log('[FE DEBUG] Connecting WebSocket to', BACKEND_BASE_URL)
    socket = io(BACKEND_BASE_URL)
    socket.on('connect',    () => console.log('[FE DEBUG] WS connect fired (socket id=' + socket?.id + ')'))
    socket.on('disconnect', () => console.log('[FE DEBUG] WS disconnect fired'))
    socket.on('connect_error', (err: any) => console.error('[FE DEBUG] WS connect_error:', err?.message))
  }

  function disconnectWebSocket() {
    if (socket) {
      console.log('[FE DEBUG] Disconnecting WebSocket')
      socket.disconnect()
      socket = null
    }
  }

  /**
   * Subscribe to a scan's progress events for the duration of a promise.
   * Auto-unsubscribes on resolve/reject.
   *
   * Awaits the 'connect' event before attaching the room handler — otherwise
   * a fresh mount could subscribe on a still-connecting socket, and any
   * server-side progress events emitted before the client actually joined
   * the room would be silently lost. Round-1 review fix.
   */
  async function withProgressListener<T>(
    scanId: string,
    phase: PhaseProgress['phase'],
    baseMessage: string,
    work: () => Promise<T>,
  ): Promise<T> {
    if (!socket || !socket.connected) connectWebSocket()

    // Await the 'connect' event with a 3s timeout — if the WS server isn't
    // reachable, fall through to HTTP and log the connectivity problem;
    // the HTTP call will still work, just without live progress.
    if (socket && !socket.connected) {
      console.log('[FE DEBUG] withProgressListener: awaiting WS connect...')
      await new Promise<void>((resolve) => {
        let done = false
        const timer = setTimeout(() => {
          if (done) return
          done = true
          console.warn('[FE DEBUG] WS connect timeout after 3s — proceeding without live progress')
          resolve()
        }, 3000)
        const onConnect = () => {
          if (done) return
          done = true
          clearTimeout(timer)
          console.log('[FE DEBUG] WS connect fired — subscribing to room now')
          resolve()
        }
        socket?.once('connect', onConnect)
        // If it connected between the check above and here, resolve immediately
        if (socket && socket.connected) {
          if (!done) {
            done = true
            clearTimeout(timer)
            socket.off('connect', onConnect)
            resolve()
          }
        }
      })
    }

    const room = `vscan:${scanId}:progress`
    const startTs = Date.now()
    let progressCount = 0
    console.log('[FE DEBUG] withProgressListener: subscribing to room=' + room + ', phase=' + phase)

    const handler = (data: {
      current: number
      total:   number
      percentage: number
      message:  string
    }) => {
      progressCount += 1
      // Log every 10th event to reduce noise, but always log the first + last-ish
      if (progressCount <= 3 || progressCount % 10 === 0) {
        console.log('[FE DEBUG] WS progress[' + progressCount + '] '
          + room + ' → ' + data.current + '/' + data.total + ' (' + data.percentage + '%) — ' + data.message)
      }
      const elapsedSec = (Date.now() - startTs) / 1000
      const rate = data.current > 0 && elapsedSec > 0 ? data.current / elapsedSec : 0
      const remaining = rate > 0 ? Math.ceil((data.total - data.current) / rate) : 0
      phaseProgress.value = {
        phase,
        message: data.message || baseMessage,
        details: `${data.current}/${data.total}${remaining > 0 ? ` — ETA ${remaining}s` : ''}`,
        current: data.current,
        total:   data.total,
        percentage: data.percentage,
      }
    }
    socket?.on(room, handler)

    return work().finally(() => {
      console.log('[FE DEBUG] withProgressListener: unsubscribing from ' + room
        + ' (received ' + progressCount + ' events)')
      socket?.off(room, handler)
    })
  }

  function clearProgressAfter(phase: PhaseProgress['phase'], delayMs = 2000) {
    setTimeout(() => {
      if (phaseProgress.value.phase === phase) {
        phaseProgress.value = { phase: 0, message: '', details: '', current: 0, total: 0, percentage: 0 }
      }
    }, delayMs)
  }

  /** Recognise HTTP 499 stop signal. Narrow (Tier-2 review):
   *  the previous version also treated any ERR_BAD_REQUEST (i.e. any 4xx)
   *  as a stop, which silently reclassified genuine 400/401/403/404
   *  responses as "stopped by user". */
  function isStopError(error: any): boolean {
    return (
      error?.status === 499
      || error?.response?.status === 499
      || String(error?.message || '').includes('stopped')
    )
  }

  /**
   * Reset the phase progress panel to idle. Used on failure paths so a
   * stalled bar at N% doesn't persist visually after an error.
   */
  function resetPhaseProgress() {
    phaseProgress.value = { phase: 0, message: '', details: '', current: 0, total: 0, percentage: 0 }
  }

  /**
   * Show a full-page loading lock during long-running destructive file
   * operations (move to trash, copy + backup for replace, etc). Videos can
   * be gigabytes each and a Windows shutil.move across drives blocks for
   * seconds per file — the user should not be able to click other buttons
   * during that window. Returns a handle with `.close()` — caller must
   * call it in a finally block.
   *
   * `lock: true` also freezes body scroll, so the fullscreen overlay stays
   * anchored while the operation runs.
   */
  function openFileOpLock(text: string) {
    return ElLoading.service({
      lock: true,
      text,
      background: 'rgba(0, 0, 0, 0.6)',
    })
  }


  // ========================================================================
  // Phase methods (each phase follows the same 5-step pattern:
  //   1. guard + generate scan_id
  //   2. init progress
  //   3. ensure WS connected + listener bound
  //   4. call HTTP
  //   5. finalize progress + summary + cleanup
  // )
  // ========================================================================

  async function runPhase1() {
    const validPaths = (settings.value.folder_paths || []).filter(p => p && p.trim() !== '')
    console.log('[FE DEBUG] runPhase1() called')
    console.log('[FE DEBUG]   folder_paths from settings:', settings.value.folder_paths)
    console.log('[FE DEBUG]   filtered validPaths:', validPaths)
    if (validPaths.length === 0) {
      ElMessage.warning('Please add at least one valid folder in Settings')
      console.warn('[FE DEBUG] runPhase1 aborted: no folder paths configured')
      return false
    }

    const scanId = `vphase1-${uuidv4()}`
    console.log('[FE DEBUG] runPhase1 scan_id=' + scanId)
    isPhase1Running.value = true
    phase1Summary.value = null
    phaseProgress.value = {
      phase: 1, message: 'Phase 1: Refreshing videos...',
      details: 'Starting...', current: 0, total: 0, percentage: 0,
    }

    try {
      console.log('[FE DEBUG] Phase 1 HTTP POST /phase1/refresh — paths.count=' + validPaths.length)
      const result = await withProgressListener(
        scanId, 1, 'Phase 1: Refreshing videos...',
        () => VideoDuplicateFinderService.phase1Refresh(validPaths, scanId),
      )
      console.log('[FE DEBUG] Phase 1 HTTP response:', result)

      phase1Summary.value = {
        added:    result.added,
        removed:  result.removed,
        skipped:  result.skipped,
        elapsed:  result.elapsed.toFixed(1),
      }
      phaseProgress.value = {
        phase: 1, message: 'Phase 1 complete',
        details: `+${result.added}, -${result.removed}, skipped ${result.skipped}, ${result.elapsed.toFixed(1)}s`,
        current: 100, total: 100, percentage: 100,
      }
      ElMessage.success(
        `Phase 1 complete: +${result.added}, -${result.removed}, ` +
        `skipped ${result.skipped} (${result.elapsed.toFixed(1)}s)`,
      )
      clearProgressAfter(1)
      const success = result.stopped !== true
      console.log('[FE DEBUG] runPhase1 returning success=' + success + ' (stopped=' + result.stopped + ')')
      return success
    } catch (error: any) {
      console.error('[FE DEBUG] runPhase1 caught error:', error)
      resetPhaseProgress()
      if (isStopError(error)) {
        ElMessage.warning('Phase 1 stopped by user')
      } else {
        console.error('[Phase 1] failed:', error)
        ElMessage.error(error?.message || 'Phase 1 failed')
      }
      return false
    } finally {
      isPhase1Running.value = false
      console.log('[FE DEBUG] runPhase1 finally — isPhase1Running=false')
    }
  }

  async function stopPhase1() {
    try {
      await VideoDuplicateFinderService.phase1Stop()
      ElMessage.info('Phase 1 stop signal sent')
    } catch (error: any) {
      console.error('[Phase 1 stop] failed:', error)
      ElMessage.error(error?.message || 'Failed to stop Phase 1')
    }
  }

  async function runPhase2() {
    const scanId = `vphase2-${uuidv4()}`
    console.log('[FE DEBUG] runPhase2() called, scan_id=' + scanId + ', threshold=' + threshold.value + '%')
    isPhase2Running.value = true
    phase2Summary.value = null
    phaseProgress.value = {
      phase: 2, message: 'Phase 2: Building similarities...',
      details: 'Starting...', current: 0, total: 0, percentage: 0,
    }

    try {
      console.log('[FE DEBUG] Phase 2 HTTP POST /phase2/build — threshold_percent=' + threshold.value)
      const result = await withProgressListener(
        scanId, 2, 'Phase 2: Building similarities...',
        () => VideoDuplicateFinderService.phase2Build(undefined, threshold.value, scanId),
      )
      console.log('[FE DEBUG] Phase 2 HTTP response:', result)

      phase2Summary.value = {
        processed:          result.processed,
        similarities_found: result.similarities_found,
        elapsed:            result.elapsed.toFixed(1),
      }
      phaseProgress.value = {
        phase: 2, message: 'Phase 2 complete',
        details: `Processed ${result.processed}, ${result.similarities_found} edges, ${result.elapsed.toFixed(1)}s`,
        current: 100, total: 100, percentage: 100,
      }
      ElMessage.success(
        `Phase 2 complete: processed ${result.processed}, ` +
        `${result.similarities_found} edges (${result.elapsed.toFixed(1)}s)`,
      )
      clearProgressAfter(2)
      const success = result.stopped !== true
      console.log('[FE DEBUG] runPhase2 returning success=' + success)
      return success
    } catch (error: any) {
      console.error('[FE DEBUG] runPhase2 caught error:', error)
      resetPhaseProgress()
      if (isStopError(error)) {
        ElMessage.warning('Phase 2 stopped by user')
      } else {
        console.error('[Phase 2] failed:', error)
        ElMessage.error(error?.message || 'Phase 2 failed')
      }
      return false
    } finally {
      isPhase2Running.value = false
      console.log('[FE DEBUG] runPhase2 finally — isPhase2Running=false')
    }
  }

  async function stopPhase2() {
    try {
      await VideoDuplicateFinderService.phase2Stop()
      ElMessage.info('Phase 2 stop signal sent')
    } catch (error: any) {
      console.error('[Phase 2 stop] failed:', error)
      ElMessage.error(error?.message || 'Failed to stop Phase 2')
    }
  }

  async function runPhase25(sameFolderFilter: boolean = true) {
    const scanId = `vphase25-${uuidv4()}`
    console.log('[FE DEBUG] runPhase25() called, scan_id=' + scanId
      + ', threshold=' + threshold.value + '%, same_folder_filter=' + sameFolderFilter)
    isPhase25Running.value = true
    phase25Summary.value = null
    phaseProgress.value = {
      phase: 25, message: 'Phase 2.5: Materializing groups...',
      details: 'Starting...', current: 0, total: 0, percentage: 0,
    }

    try {
      console.log('[FE DEBUG] Phase 2.5 HTTP POST /phase2.5/materialize')
      const result = await withProgressListener(
        scanId, 25, 'Phase 2.5: Materializing groups...',
        () => VideoDuplicateFinderService.phase25Materialize(threshold.value, sameFolderFilter, scanId),
      )
      console.log('[FE DEBUG] Phase 2.5 HTTP response:', result)

      phase25Summary.value = {
        groups_count:  result.groups_count,
        members_count: result.members_count,
        elapsed:       result.elapsed.toFixed(2),
      }
      phaseProgress.value = {
        phase: 25, message: 'Phase 2.5 complete',
        details: `${result.groups_count} groups, ${result.members_count} members, ${result.elapsed.toFixed(2)}s`,
        current: 100, total: 100, percentage: 100,
      }
      ElMessage.success(
        `Phase 2.5 complete: ${result.groups_count} groups at ${result.threshold_percent}% ` +
        `(${result.elapsed.toFixed(2)}s)`,
      )
      console.log('[FE DEBUG] Phase 2.5 → refreshing meta')
      await loadPhase25Meta()
      clearProgressAfter(25)
      const success = result.stopped !== true
      console.log('[FE DEBUG] runPhase25 returning success=' + success)
      return success
    } catch (error: any) {
      console.error('[FE DEBUG] runPhase25 caught error:', error)
      resetPhaseProgress()
      if (isStopError(error)) {
        ElMessage.warning('Phase 2.5 stopped by user')
      } else {
        console.error('[Phase 2.5] failed:', error)
        ElMessage.error(error?.message || 'Phase 2.5 failed')
      }
      return false
    } finally {
      isPhase25Running.value = false
      console.log('[FE DEBUG] runPhase25 finally — isPhase25Running=false')
    }
  }

  async function stopPhase25() {
    try {
      await VideoDuplicateFinderService.phase25Stop()
      ElMessage.info('Phase 2.5 stop signal sent')
    } catch (error: any) {
      console.error('[Phase 2.5 stop] failed:', error)
      ElMessage.error(error?.message || 'Failed to stop Phase 2.5')
    }
  }

  async function loadPhase25Meta() {
    try {
      const { meta } = await VideoDuplicateFinderService.phase25Meta()
      phase25Meta.value = meta || {}
    } catch (error: any) {
      console.warn('[Phase 2.5 meta] failed:', error)
      phase25Meta.value = {}
    }
  }

  /**
   * True if Phase 2.5 needs (re-)running: never materialized, or materialized
   * at a threshold that doesn't match the current UI threshold.
   */
  const phase25NeedsAttention = computed(() => {
    const m = phase25Meta.value
    if (!m || !m.materialized_threshold) return true
    return parseInt(m.materialized_threshold, 10) !== threshold.value
  })

  const phase25TooltipContent = computed(() => {
    const m = phase25Meta.value
    if (!m || !m.materialized_threshold) {
      return 'No materialization yet. Click to materialize duplicate groups for Phase 3.'
    }
    const matT = parseInt(m.materialized_threshold, 10)
    if (matT !== threshold.value) {
      return `Materialized at ${matT}%, current UI threshold is ${threshold.value}%. Click to re-materialize.`
    }
    const groupCount = m.materialized_group_count || '?'
    const ts = m.materialized_at ? formatTimestamp(parseFloat(m.materialized_at)) : '?'
    return `Materialized at ${matT}% with ${groupCount} groups (${ts}).`
  })

  async function runPhase3() {
    await loadDuplicatesPage(1)
  }

  async function stopPhase3() {
    try {
      await VideoDuplicateFinderService.phase3Stop()
      ElMessage.info('Phase 3 stop signal sent')
    } catch (error: any) {
      console.error('[Phase 3 stop] failed:', error)
      ElMessage.error(error?.message || 'Failed to stop Phase 3')
    }
  }


  // ========================================================================
  // Phase 3 pagination + sort
  // ========================================================================

  async function loadDuplicatesPage(page: number) {
    console.log('[FE DEBUG] loadDuplicatesPage(' + page + ') invoked')
    console.log('[FE DEBUG]   threshold=' + threshold.value + '%, pageSize=' + pageSize.value
      + ', sortBy=' + sortBy.value + ', sortOrder=' + sortOrder.value)

    // Guard against overlapping loads (Tier-2 review): the top pagination /
    // sort controls used to fire concurrent requests, causing whichever
    // response arrived last to win — potentially showing page-3 results
    // labelled page-1.
    if (isLoadingPage.value) {
      console.log('[FE DEBUG] loadDuplicatesPage skipped — another load in flight')
      return
    }
    isPhase3Running.value = true
    isLoadingPage.value = true

    // Bump a request-generation counter so a late-arriving stale response
    // can be dropped even if the guard above is bypassed by fast clicks.
    const genId = ++phase3LoadGen.value
    console.log('[FE DEBUG] loadDuplicatesPage genId=' + genId)

    try {
      console.log('[FE DEBUG] Phase 3 HTTP POST /phase3/get-duplicates')
      const result = await VideoDuplicateFinderService.phase3GetDuplicates(
        threshold.value,
        page,
        pageSize.value,
        sortBy.value,
        sortOrder.value,
      )
      console.log('[FE DEBUG] Phase 3 HTTP response: error=' + result.error
        + ', total_groups=' + result.total_groups + ', groups_on_page=' + (result.groups?.length ?? 0)
        + ', total_files_in_db=' + result.total_files_in_db)

      // Drop stale responses (a newer load has already started)
      if (genId !== phase3LoadGen.value) {
        console.log('[FE DEBUG] loadDuplicatesPage: dropping stale response (gen=' + genId
          + ', current=' + phase3LoadGen.value + ')')
        return
      }

      // Strict-mode error markers (HTTP 409) — un-thrown by service layer
      if (result.error === 'no_materialization') {
        console.warn('[FE DEBUG] Phase 3 returned no_materialization → prompting user')
        ElMessage.warning('No materialized groups. Please run Phase 2.5 first.')
        scanResult.value = null
        currentPage.value = 1
        totalPages.value = 0
        totalGroupsAll.value = 0
        await loadPhase25Meta()
        return
      }
      if (result.error === 'threshold_mismatch') {
        console.warn('[FE DEBUG] Phase 3 returned threshold_mismatch → prompting user')
        ElMessage.warning(
          result.message
            || `Materialized at ${result.materialized_threshold}% but UI wants ${result.current_threshold}%. Re-run Phase 2.5.`,
        )
        scanResult.value = null
        currentPage.value = 1
        totalPages.value = 0
        totalGroupsAll.value = 0
        await loadPhase25Meta()
        return
      }

      // Success — populate
      scanResult.value = {
        scan_id:          result.scan_id || `vphase3-${Date.now()}`,
        duplicate_groups: result.groups,
        total_duplicates: result.total_duplicates,
        duplicate_count:  result.total_duplicates,
        total_files:      result.total_duplicates,
      }
      currentPage.value    = result.current_page
      totalPages.value     = result.total_pages
      totalGroupsAll.value = result.total_groups
      totalFilesInDb.value = result.total_files_in_db

      // Server-side auto_delete_suggestion → prefill selectedForDelete (D-14)
      selectedForDelete.value.clear()
      let autoMarkCount = 0
      for (const grp of result.groups) {
        for (const m of grp) {
          if (m.auto_delete_suggestion) {
            selectedForDelete.value.add(m.file_path)
            autoMarkCount += 1
          }
        }
      }
      console.log('[FE DEBUG] Phase 3 populated: ' + result.groups.length + ' groups on page, '
        + autoMarkCount + ' auto-marked members')
      // Force reactivity for Set
      selectedForDelete.value = new Set(selectedForDelete.value)

      if (page === 1) {
        ElMessage.success(
          `Phase 3: ${result.total_groups} groups / ${result.total_duplicates} videos ` +
          `(${(result.elapsed * 1000).toFixed(0)}ms)`,
        )
      }
    } catch (error: any) {
      console.error('[FE DEBUG] loadDuplicatesPage caught error:', error)
      if (isStopError(error)) {
        ElMessage.warning('Phase 3 stopped by user')
      } else {
        console.error('[Phase 3] failed:', error)
        ElMessage.error(error?.message || 'Phase 3 failed')
      }
    } finally {
      isPhase3Running.value = false
      isLoadingPage.value = false
      console.log('[FE DEBUG] loadDuplicatesPage finally — done')
    }
  }

  async function handlePageChange(newPage: number) {
    await loadDuplicatesPage(newPage)
  }

  async function handlePageSizeChange(newSize: number) {
    pageSize.value = newSize
    currentPage.value = 1
    await loadDuplicatesPage(1)
  }

  async function handleSortChange() {
    currentPage.value = 1
    await loadDuplicatesPage(1)
  }

  async function toggleSortOrder() {
    sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
    await handleSortChange()
  }


  // ========================================================================
  // Full pipeline: Phase 1 → 2 → 2.5 → 3
  // ========================================================================

  async function runFullPipeline() {
    console.log('[FE DEBUG] ============================================================')
    console.log('[FE DEBUG] runFullPipeline() invoked')
    console.log('[FE DEBUG] threshold =', threshold.value + '%')
    console.log('[FE DEBUG] folder_paths =', settings.value.folder_paths)
    console.log('[FE DEBUG] ============================================================')
    try {
      await ElMessageBox.confirm(
        'Run the full pipeline?\n\n' +
        '  1. Phase 1  — scan + compute hashes\n' +
        '  2. Phase 2  — pairwise distance\n' +
        '  3. Phase 2.5 — materialize groups\n' +
        '  4. Phase 3  — load results',
        'Full Pipeline',
        { type: 'info', confirmButtonText: 'Run All', cancelButtonText: 'Cancel' },
      )
    } catch {
      console.log('[FE DEBUG] runFullPipeline cancelled by user')
      return
    }

    isFullPipelineRunning.value = true
    try {
      console.log('[FE DEBUG] Pipeline → Phase 1 starting')
      const ok1 = await runPhase1()
      console.log('[FE DEBUG] Pipeline → Phase 1 done, ok=' + ok1)
      if (!ok1) { ElMessage.info('Full pipeline: Phase 1 stopped or failed — aborting'); return }

      console.log('[FE DEBUG] Pipeline → Phase 2 starting')
      const ok2 = await runPhase2()
      console.log('[FE DEBUG] Pipeline → Phase 2 done, ok=' + ok2)
      if (!ok2) { ElMessage.info('Full pipeline: Phase 2 stopped or failed — aborting'); return }

      console.log('[FE DEBUG] Pipeline → Phase 2.5 starting')
      const ok25 = await runPhase25(true)
      console.log('[FE DEBUG] Pipeline → Phase 2.5 done, ok=' + ok25)
      if (!ok25) { ElMessage.info('Full pipeline: Phase 2.5 stopped or failed — aborting'); return }

      console.log('[FE DEBUG] Pipeline → Phase 3 starting (loadDuplicatesPage(1))')
      await loadDuplicatesPage(1)
      console.log('[FE DEBUG] Pipeline → Phase 3 done')
      ElMessage.success('Full pipeline complete')
    } catch (error: any) {
      console.error('[FE DEBUG] Pipeline caught error:', error)
      ElMessage.error(error?.message || 'Pipeline failed')
    } finally {
      isFullPipelineRunning.value = false
      console.log('[FE DEBUG] runFullPipeline finally — done')
    }
  }


  // ========================================================================
  // Selection helpers (per-group)
  // ========================================================================

  function toggleFileSelection(filePath: string) {
    const set = new Set(selectedForDelete.value)
    if (set.has(filePath)) set.delete(filePath); else set.add(filePath)
    selectedForDelete.value = set
  }

  function hasSelectedInGroup(group: VideoGroup): boolean {
    return group.some(v => selectedForDelete.value.has(v.file_path))
  }

  function hasAllSelectedInGroup(group: VideoGroup): boolean {
    return group.length > 0 && group.every(v => selectedForDelete.value.has(v.file_path))
  }

  function getSelectedCountInGroup(group: VideoGroup): number {
    return group.filter(v => selectedForDelete.value.has(v.file_path)).length
  }

  function selectAllInGroup(group: VideoGroup) {
    const set = new Set(selectedForDelete.value)
    if (hasAllSelectedInGroup(group)) {
      for (const v of group) set.delete(v.file_path)
    } else {
      for (const v of group) set.add(v.file_path)
    }
    selectedForDelete.value = set
  }

  const selectedCount = computed(() => selectedForDelete.value.size)


  // ========================================================================
  // Delete
  // ========================================================================

  async function deleteSelectedInGroup(group: VideoGroup, groupIndex: number) {
    const paths = group
      .filter(v => selectedForDelete.value.has(v.file_path))
      .map(v => v.file_path)

    if (paths.length === 0) {
      ElMessage.warning('No files selected in this group')
      return
    }
    if (paths.length === group.length) {
      ElMessage.warning('Cannot delete every member of a group — keep at least one')
      return
    }

    // Pre-flight: delete_target_path must be set (Tier-3 review).
    const target = (settings.value.delete_target_path || '').trim()
    if (!target) {
      ElMessage.error('Set a delete target path in Settings first')
      return
    }

    try {
      await ElMessageBox.confirm(
        `Move ${paths.length} file(s) to:\n  ${target}\n` +
        `Companion sidecars (.srt / .nfo / covers) will move too.`,
        'Confirm Delete',
        { type: 'warning', confirmButtonText: 'Delete', cancelButtonText: 'Cancel' },
      )
    } catch { return }

    try {
      isDeleting.value = true
      const loadingHandle = openFileOpLock(
        `Moving ${paths.length} video(s) + companions to trash…\n` +
        `Large files may take a while — please wait.`,
      )
      try {
        const result = await VideoDuplicateFinderService.deleteFiles(paths)
        if (result.success > 0) {
          ElMessage.success(
            `Deleted ${result.success} file(s) + ${result.companions_moved} companion(s)`,
          )
        }
        if (result.failed > 0) {
          ElMessage.error(`Failed on ${result.failed} file(s) — see console`)
          console.error('[Delete] errors:', result.errors)
        }
        // Reload from server so counters/pagination stay consistent.
        await loadDuplicatesPage(currentPage.value)
        // Drop selections
        const set = new Set(selectedForDelete.value)
        for (const p of paths) set.delete(p)
        selectedForDelete.value = set
        void groupIndex
      } finally {
        loadingHandle.close()
      }
    } catch (error: any) {
      console.error('[Delete] failed:', error)
      ElMessage.error(error?.message || 'Delete failed')
    } finally {
      isDeleting.value = false
    }
  }

  /** Delete every selection across all pages currently loaded — bulk action. */
  async function deleteAllSelected() {
    const paths = Array.from(selectedForDelete.value)
    if (paths.length === 0) {
      ElMessage.warning('Nothing selected')
      return
    }

    const target = (settings.value.delete_target_path || '').trim()
    if (!target) {
      ElMessage.error('Set a delete target path in Settings first')
      return
    }

    try {
      await ElMessageBox.confirm(
        `Move ${paths.length} selected file(s) to:\n  ${target}\n\n` +
        `This may span multiple groups. Groups falling below 2 remaining members will be removed.`,
        'Confirm Delete All Selected',
        { type: 'warning', confirmButtonText: 'Delete', cancelButtonText: 'Cancel' },
      )
    } catch { return }

    try {
      isDeleting.value = true
      const loadingHandle = openFileOpLock(
        `Moving ${paths.length} selected video(s) + companions to trash…\n` +
        `This may span multiple groups. Large files can take a while.`,
      )
      try {
        const result = await VideoDuplicateFinderService.deleteFiles(paths)
        ElMessage.success(
          `Deleted ${result.success} file(s) + ${result.companions_moved} companion(s)`,
        )
        if (result.failed > 0) {
          ElMessage.error(`Failed on ${result.failed} file(s) — see console`)
          console.error('[Delete all] errors:', result.errors)
        }
        selectedForDelete.value = new Set()
        // Reload page — DB state changed, groups may have shifted
        await loadDuplicatesPage(currentPage.value)
      } finally {
        loadingHandle.close()
      }
    } catch (error: any) {
      console.error('[Delete all] failed:', error)
      ElMessage.error(error?.message || 'Delete failed')
    } finally {
      isDeleting.value = false
    }
  }


  // ========================================================================
  // Whitelist
  // ========================================================================

  async function addGroupToWhitelist(group: VideoGroup, groupIndex: number) {
    if (group.length < 2) return
    const videoIds = group.map(v => v.id).filter(id => typeof id === 'number')
    if (videoIds.length < 2) {
      ElMessage.error('Group must have ≥ 2 videos with ids')
      return
    }

    try {
      await ElMessageBox.confirm(
        `Add this group (${videoIds.length} videos) to whitelist? ` +
        `It will not appear in future materializations.`,
        'Whitelist Group',
        { type: 'info', confirmButtonText: 'Whitelist', cancelButtonText: 'Cancel' },
      )
    } catch { return }

    try {
      await VideoDuplicateFinderService.addGroupToWhitelist(videoIds)
      ElMessage.success('Group added to whitelist')
      // Reload from server so counters stay consistent (Tier-2 review).
      await loadDuplicatesPage(currentPage.value)
      await loadWhitelistGroups()
      void groupIndex
    } catch (error: any) {
      console.error('[Whitelist add] failed:', error)
      ElMessage.error(error?.message || 'Failed to add to whitelist')
    }
  }

  function whitelistCurrentPage() {
    const groups = scanResult.value?.duplicate_groups || []
    if (groups.length === 0) { ElMessage.info('No groups to whitelist'); return }

    const payload = groups
      .map(g => g.map(v => v.id).filter((x): x is number => typeof x === 'number'))
      .filter(ids => ids.length >= 2)
    if (payload.length === 0) {
      ElMessage.warning('No valid groups (need ≥ 2 videos with ids each)')
      return
    }

    const videoCount = payload.reduce((s, ids) => s + ids.length, 0)
    bulkWhitelistPreview.value = {
      groups,
      payload,
      groupCount: payload.length,
      videoCount,
      contextLabel: `current page (${groups.length} groups)`,
    }
    showBulkWhitelistDialog.value = true
  }

  /**
   * Deep whitelist by folder — uses server-side /whitelist/preview-by-path
   * to enumerate ALL materialized groups (not just current page) that have
   * a member under the clicked file's folder. Opens the same bulk-whitelist
   * dialog as `whitelistCurrentPage`.
   */
  async function deepWhitelistPath(filePath: string) {
    if (isBulkWhitelisting.value) {
      console.log('[FE DEBUG] deepWhitelistPath skipped — bulk WL in flight')
      return
    }
    if (!filePath) { ElMessage.warning('Empty file path'); return }
    const dirPath = dirnameOf(filePath)
    if (!dirPath) { ElMessage.warning('Cannot extract folder'); return }
    try {
      console.log('[FE DEBUG] deepWhitelistPath POST /whitelist/preview-by-path')
      console.log('[FE DEBUG]   deep_path=' + dirPath)
      const preview = await VideoDuplicateFinderService.previewWhitelistByPath(dirPath)
      console.log('[FE DEBUG] preview response: matched_groups=' + preview.matched_groups
        + ', matched_files=' + preview.matched_files)
      if (!preview.groups || preview.groups.length === 0) {
        ElMessage.info(`No materialized groups have files under ${dirPath}`)
        return
      }
      const payload = preview.groups
        .map(g => g.map(v => v.id).filter((x): x is number => typeof x === 'number'))
        .filter(ids => ids.length >= 2)
      const videoCount = payload.reduce((s, ids) => s + ids.length, 0)
      bulkWhitelistPreview.value = {
        groups: preview.groups,
        payload,
        groupCount: payload.length,
        videoCount,
        contextLabel: `folder (server-side): ${dirPath} — ${preview.matched_files} files`,
      }
      showBulkWhitelistDialog.value = true
    } catch (error: any) {
      console.error('[FE DEBUG] deepWhitelistPath failed:', error)
      ElMessage.error(error?.message || 'Preview by path failed')
    }
  }

  async function confirmBulkWhitelist() {
    if (isBulkWhitelisting.value) {
      console.log('[FE DEBUG] confirmBulkWhitelist skipped — already in flight')
      return
    }
    const { payload, groupCount, videoCount } = bulkWhitelistPreview.value
    if (payload.length === 0) { showBulkWhitelistDialog.value = false; return }

    isBulkWhitelisting.value = true
    try {
      // Use the server-side bulk endpoint — single stats repair, scales with
      // unique videos not group count. Falls back to per-group POST in the
      // rare case bulk fails.
      console.log('[FE DEBUG] confirmBulkWhitelist POST /whitelist/bulk-add-groups, groups =', payload.length)
      const result = await VideoDuplicateFinderService.bulkAddGroupsToWhitelist(payload)
      console.log('[FE DEBUG] bulk-add response:', result)
      ElMessage.success(
        `Whitelisted ${result.added_groups} of ${groupCount} groups ` +
        `(${result.video_count} videos)` +
        (result.skipped_groups ? `, ${result.skipped_groups} skipped` : ''),
      )
      showBulkWhitelistDialog.value = false
      // Reload from page 1 (may have gone past last page after bulk mutation).
      await loadDuplicatesPage(1)
      await loadWhitelistGroups()
      void videoCount
    } catch (error: any) {
      console.error('[FE DEBUG] confirmBulkWhitelist failed:', error)
      ElMessage.error(error?.message || 'Bulk whitelist failed')
    } finally {
      isBulkWhitelisting.value = false
    }
  }

  function cancelBulkWhitelist() {
    showBulkWhitelistDialog.value = false
  }

  async function loadWhitelistGroups() {
    try {
      isLoadingWhitelist.value = true
      const r = await VideoDuplicateFinderService.getWhitelist()
      whitelistGroups.value = r.whitelist_groups
    } catch (error: any) {
      console.error('[Whitelist load] failed:', error)
      ElMessage.error(error?.message || 'Failed to load whitelist')
    } finally {
      isLoadingWhitelist.value = false
    }
  }

  async function removeWhitelistGroup(groupId: number, index: number) {
    try {
      await ElMessageBox.confirm('Remove this whitelist group?', 'Confirm', {
        type: 'warning', confirmButtonText: 'Remove', cancelButtonText: 'Cancel',
      })
    } catch { return }
    try {
      await VideoDuplicateFinderService.removeWhitelistGroup(groupId)
      whitelistGroups.value.splice(index, 1)
      ElMessage.success('Removed from whitelist')
    } catch (error: any) {
      console.error('[Whitelist remove] failed:', error)
      ElMessage.error(error?.message || 'Failed')
    }
  }


  // ========================================================================
  // Verify / Cleanup
  // ========================================================================

  async function verifyAndCleanup() {
    if (!scanResult.value?.duplicate_groups?.length) {
      ElMessage.warning('No results to verify')
      return
    }
    try {
      isVerifying.value = true
      const r = await VideoDuplicateFinderService.verifyFiles(scanResult.value.duplicate_groups)
      if (r.missing_count === 0) {
        ElMessage.success('All files still exist')
        return
      }
      const sample = r.missing_files.slice(0, 5).join('\n')
      const more = r.missing_files.length > 5 ? `\n... and ${r.missing_files.length - 5} more` : ''
      await ElMessageBox.confirm(
        `Found ${r.missing_count} missing files affecting ${r.affected_groups.length} groups. ` +
        `${r.removed_groups_count} groups will be removed (< 2 remaining members).\n\n` +
        `Sample missing:\n${sample}${more}\n\nReload the page from the server (recommended)?`,
        'Missing Files',
        { type: 'warning', confirmButtonText: 'Reload', cancelButtonText: 'Cancel' },
      )
      // Reload the current page from the server so totalGroupsAll / totalPages
      // are consistent with the local view (Tier-2 review — stale counter fix).
      await loadDuplicatesPage(currentPage.value)
      ElMessage.success('Reloaded from server')
    } catch (error: any) {
      if (error !== 'cancel') {
        console.error('[Verify] failed:', error)
        ElMessage.error(error?.message || 'Verify failed')
      }
    } finally {
      isVerifying.value = false
    }
  }

  async function cleanupDatabase() {
    try {
      await ElMessageBox.confirm(
        'Scan `folder_paths` and remove DB rows for files that no longer exist on disk?',
        'Cleanup Database',
        { type: 'warning', confirmButtonText: 'Cleanup', cancelButtonText: 'Cancel' },
      )
    } catch { return }
    try {
      isCleaningDb.value = true
      const r = await VideoDuplicateFinderService.cleanupDatabase()
      ElMessage.success(`Cleanup: removed ${r.removed_hashes} rows (${r.existing_files} files remain)`)
    } catch (error: any) {
      console.error('[Cleanup] failed:', error)
      ElMessage.error(error?.message || 'Cleanup failed')
    } finally {
      isCleaningDb.value = false
    }
  }


  // ========================================================================
  // S6: Compare folders (focused + cluster-based all)
  // ========================================================================

  const isComparingFolder = ref(false)
  const isCompareAllRunning = ref(false)

  /**
   * Re-run compare + Phase 2.5 focused on the folders containing a group's
   * members. Use case: a group is missing partners the user can see on disk
   * — force a scoped re-comparison. Never deletes anything on disk.
   */
  async function compareFolderForGroup(group: VideoGroup) {
    if (!Array.isArray(group) || group.length === 0) {
      ElMessage.info('Empty group')
      return
    }
    const folderSet = new Set<string>()
    for (const v of group) {
      const fp = v?.file_path
      if (typeof fp === 'string' && fp) {
        const d = dirnameOf(fp)
        if (d) folderSet.add(d)
      }
    }
    const folders = Array.from(folderSet)
    if (folders.length === 0) {
      ElMessage.warning('No folders extracted from this group')
      return
    }

    try {
      await ElMessageBox.confirm(
        `Pairwise-compare ALL videos under ${folders.length} folder(s) (recursive):\n\n` +
        folders.slice(0, 5).join('\n') +
        (folders.length > 5 ? `\n… and ${folders.length - 5} more` : '') +
        '\n\nOnly inserts new similarity edges within this scope — nothing is deleted, ' +
        'nothing outside these folders is touched. Phase 2.5 rematerializes at the end.',
        'Compare Folder',
        { type: 'warning', confirmButtonText: 'Run', cancelButtonText: 'Cancel' },
      )
    } catch { return }

    try {
      isComparingFolder.value = true
      phaseProgress.value = {
        phase: 1, message: 'Compare Folder: starting…',
        details: `${folders.length} folder(s)`,
        current: 0, total: 100, percentage: 0,
      }
      console.log('[FE DEBUG] compareFolderForGroup POST /compare-folders')
      console.log('[FE DEBUG]   folders =', folders)
      const result = await VideoDuplicateFinderService.compareFolders(folders, threshold.value)
      console.log('[FE DEBUG] compareFolderForGroup response:', result)
      const cmp = result?.compare ?? ({} as any)
      const groups25 = result?.phase25?.groups_count ?? '?'
      ElMessage.success(
        `Compare folder complete: scope=${cmp.scope_total ?? '?'}, ` +
        `new_phashes=${cmp.new_phashes_computed ?? 0}, ` +
        `pairs_found=${cmp.pairs_found ?? 0}, ` +
        `new_edges=${cmp.new_similarities_inserted ?? 0}, ` +
        `phase2.5 groups=${groups25}`,
      )
      phaseProgress.value = {
        phase: 25, message: 'Compare Folder: complete',
        details: `Materialized ${groups25} groups`,
        current: 100, total: 100, percentage: 100,
      }
      await loadPhase25Meta()
      await loadDuplicatesPage(1)
      clearProgressAfter(25)
    } catch (error: any) {
      console.error('[FE DEBUG] compareFolderForGroup failed:', error)
      resetPhaseProgress()
      ElMessage.error(error?.message || 'Compare folder failed')
    } finally {
      isComparingFolder.value = false
    }
  }

  /**
   * Global Compare All — server clusters folders that share a duplicate
   * group and runs Compare Folder once per cluster. Skips clusters ≥ 4
   * folders (noise heuristic).
   */
  async function runCompareAllFolders(skipConfirm: boolean = false) {
    if (!skipConfirm) {
      try {
        await ElMessageBox.confirm(
          'Run Compare Folder for EVERY folder that has files in any duplicate group.\n\n' +
          'Folders are grouped into connected clusters (share ≥ 1 group). Each cluster is compared ' +
          'independently. Clusters with ≥ 4 folders are skipped as noise.\n\n' +
          'No files on disk are modified. Only new similarity edges may be added.',
          'Compare All Folders',
          { type: 'warning', confirmButtonText: 'Run', cancelButtonText: 'Cancel' },
        )
      } catch { return }
    }
    try {
      isCompareAllRunning.value = true
      phaseProgress.value = {
        phase: 1, message: 'Compare All Folders: starting…',
        details: 'Building folder clusters',
        current: 0, total: 100, percentage: 0,
      }
      console.log('[FE DEBUG] runCompareAllFolders POST /compare-folders-all')
      const result = await VideoDuplicateFinderService.compareAllFolders(threshold.value)
      console.log('[FE DEBUG] runCompareAllFolders response:', result)
      const cmp = result?.compare ?? ({} as any)
      const groups25 = result?.phase25?.groups_count ?? '?'
      if (result.folders_count === 0) {
        ElMessage.info(result.message || 'No folders to compare')
      } else {
        const skipMsg = result.clusters_skipped
          ? `, skipped ${result.clusters_skipped} large cluster(s) covering ${result.folders_in_skipped_clusters ?? 0} folder(s)`
          : ''
        ElMessage.success(
          `Compare All complete: ${result.clusters_count ?? '?'} cluster(s) over ` +
          `${result.folders_count} folder(s)${skipMsg}, ` +
          `new_phashes=${cmp.new_phashes_computed ?? 0}, ` +
          `pairs_found=${cmp.pairs_found ?? 0}, ` +
          `new_edges=${cmp.new_similarities_inserted ?? 0}, ` +
          `phase2.5 groups=${groups25}`,
        )
      }
      phaseProgress.value = {
        phase: 25, message: 'Compare All Folders: complete',
        details: `Materialized ${groups25} groups`,
        current: 100, total: 100, percentage: 100,
      }
      await loadPhase25Meta()
      await loadDuplicatesPage(1)
      clearProgressAfter(25)
    } catch (error: any) {
      console.error('[FE DEBUG] runCompareAllFolders failed:', error)
      resetPhaseProgress()
      ElMessage.error(error?.message || 'Compare All Folders failed')
    } finally {
      isCompareAllRunning.value = false
    }
  }


  // ========================================================================
  // S7.2: Replace (single, size=2) + Deep Replace (batch on current page)
  // ========================================================================

  const isReplacing = ref(false)
  const isDeepReplacing = ref(false)

  const showDeepReplaceDialog = ref(false)
  const deepReplacePreview = ref<{
    folderPath: string
    operations: Array<{ selected: VideoInfo; anchor: VideoInfo; group: VideoGroup }>
    badGroups: VideoGroup[]
  }>({ folderPath: '', operations: [], badGroups: [] })

  /** Replace op on a size-2 group. Requires exactly 1 selection. */
  async function replaceInGroup(group: VideoGroup, groupIndex: number) {
    if (isReplacing.value) {
      console.log('[FE DEBUG] replaceInGroup skipped — already in flight')
      return
    }
    if (!Array.isArray(group) || group.length === 0) {
      ElMessage.warning('Empty group')
      return
    }
    if (group.length !== 2) {
      ElMessage.warning('Replace only works on groups with exactly 2 videos')
      return
    }
    const selected = group.filter(v => selectedForDelete.value.has(v.file_path))
    if (selected.length !== 1) {
      ElMessage.warning('Replace requires exactly 1 selected video in this group')
      return
    }
    const selectedVid = selected[0]
    const anchorVid = group[0]  // group is pre-sorted; [0] is anchor
    const isAnchorSelected = selectedVid.file_path === anchorVid.file_path

    const target = (settings.value.delete_target_path || '').trim()
    if (!target) {
      ElMessage.error('Set a delete target path in Settings first')
      return
    }

    // Preview the eventual target path for the confirm dialog
    const winSep = anchorVid.file_path.includes('\\')
    const sep = winSep ? '\\' : '/'
    const anchorLast = Math.max(anchorVid.file_path.lastIndexOf('/'), anchorVid.file_path.lastIndexOf('\\'))
    const anchorDir = anchorLast > 0 ? anchorVid.file_path.substring(0, anchorLast) : ''
    const anchorBase = anchorLast > 0 ? anchorVid.file_path.substring(anchorLast + 1) : anchorVid.file_path
    const anchorBaseNoExt = anchorBase.includes('.') ? anchorBase.substring(0, anchorBase.lastIndexOf('.')) : anchorBase
    const selBase = (() => {
      const last = Math.max(selectedVid.file_path.lastIndexOf('/'), selectedVid.file_path.lastIndexOf('\\'))
      return last > 0 ? selectedVid.file_path.substring(last + 1) : selectedVid.file_path
    })()
    const selExt = selBase.includes('.') ? selBase.substring(selBase.lastIndexOf('.')) : ''
    const previewDest = `${anchorDir}${sep}${anchorBaseNoExt}${selExt}`

    try {
      await ElMessageBox.confirm(
        `This will:\n` +
        `  • Move the non-selected video + its companions to:\n      ${target}\n` +
        (isAnchorSelected
          ? `  • (Selected is already the anchor — no rename)\n`
          : `  • COPY selected to:\n      ${previewDest}\n` +
            `  • Back up the ORIGINAL selected to the delete target (safety copy)\n`),
        'Replace',
        { type: 'warning', confirmButtonText: 'Replace', cancelButtonText: 'Cancel' },
      )
    } catch { return }

    try {
      isReplacing.value = true
      const loadingHandle = openFileOpLock(
        `Replace: copying selected video to anchor slot, then moving originals to trash…\n` +
        `Large files may take a while — do not close this page.`,
      )
      const groupPaths = group.map(v => v.file_path)
      try {
        console.log('[FE DEBUG] replaceInGroup POST /replace')
        console.log('[FE DEBUG]   selected=' + selectedVid.file_path)
        console.log('[FE DEBUG]   anchor  =' + anchorVid.file_path)
        const result = await VideoDuplicateFinderService.replaceInGroup(
          selectedVid.file_path, anchorVid.file_path, groupPaths,
        )
        console.log('[FE DEBUG] replaceInGroup response:', result)
        const errs = (result.errors || []).filter(Boolean)
        if (errs.length) {
          console.warn('[Replace] errors:', errs)
          ElMessage.warning(`Completed with ${errs.length} error(s) — see console`)
        } else {
          ElMessage.success(
            `Replace complete: deleted ${result.deleted_count} file(s)` +
            (result.renamed ? `, kept selected as ${result.new_selected_path}` : ''),
          )
        }
        // Drop selections for files that no longer exist + reload the page.
        const set = new Set(selectedForDelete.value)
        for (const p of groupPaths) set.delete(p)
        selectedForDelete.value = set
        await loadDuplicatesPage(currentPage.value)
        void groupIndex
      } finally {
        loadingHandle.close()
      }
    } catch (error: any) {
      console.error('[FE DEBUG] replaceInGroup failed:', error)
      ElMessage.error(error?.message || 'Replace failed')
    } finally {
      isReplacing.value = false
    }
  }

  /** Deep Replace — batch replace across the current page for a folder. */
  function deepReplacePath(filePath: string) {
    if (isDeepReplacing.value) {
      console.log('[FE DEBUG] deepReplacePath skipped — already in flight')
      return
    }
    if (!filePath) { ElMessage.warning('Empty file path'); return }
    const dirPath = dirnameOf(filePath)
    if (!dirPath) { ElMessage.warning('Cannot extract folder'); return }

    // Normalize both dirPath and every candidate file_path to forward-slashes
    // so a mixed-separator DB (e.g., paths inserted from a networked drive
    // or WSL) doesn't silently exclude siblings using the opposite separator.
    // Round-2 review D-fe.2.
    const toFwd = (s: string) => s.replace(/\\/g, '/')
    const dirPathN = toFwd(dirPath).replace(/\/+$/, '')
    const dirPrefixN = dirPathN + '/'

    const groups = (scanResult.value?.duplicate_groups ?? []) as VideoGroup[]
    const matched = groups.filter(g =>
      Array.isArray(g) && g.some(v => {
        const fp = v?.file_path
        if (typeof fp !== 'string') return false
        const fpN = toFwd(fp)
        return fpN === dirPathN || fpN.startsWith(dirPrefixN)
      })
    )
    if (matched.length === 0) {
      ElMessage.info('No groups on this page have files under that folder')
      return
    }

    const operations: Array<{ selected: VideoInfo; anchor: VideoInfo; group: VideoGroup }> = []
    const badGroups: VideoGroup[] = []
    for (const g of matched) {
      if (g.length === 2) {
        const selected = g.find(v => {
          const fp = v?.file_path
          if (typeof fp !== 'string') return false
          const fpN = toFwd(fp)
          return fpN === dirPathN || fpN.startsWith(dirPrefixN)
        })
        const anchor = g.find(v => v !== selected)
        if (selected && anchor) operations.push({ selected, anchor, group: g })
        else badGroups.push(g)
      } else {
        badGroups.push(g)
      }
    }

    deepReplacePreview.value = { folderPath: dirPath, operations, badGroups }
    showDeepReplaceDialog.value = true
  }

  function cancelDeepReplace() { showDeepReplaceDialog.value = false }

  async function confirmDeepReplace() {
    if (isDeepReplacing.value) {
      console.log('[FE DEBUG] confirmDeepReplace skipped — already in flight')
      return
    }
    if (deepReplacePreview.value.badGroups.length > 0) {
      ElMessage.error(
        `Replace is blocked: ${deepReplacePreview.value.badGroups.length} group(s) have a size other than 2`,
      )
      return
    }
    const ops = deepReplacePreview.value.operations
    if (!ops.length) { showDeepReplaceDialog.value = false; return }
    const target = (settings.value.delete_target_path || '').trim()
    if (!target) {
      ElMessage.error('Set a delete target path in Settings first')
      return
    }
    const payload = ops.map(o => ({
      selected_file_path: o.selected.file_path,
      anchor_file_path:   o.anchor.file_path,
      group_file_paths:   o.group.map(v => v.file_path),
    }))
    // Set the in-flight flag BEFORE closing the dialog, so a rapid double-click
    // on the primary button (Element Plus doesn't debounce it) can't enqueue a
    // second call while `showDeepReplaceDialog` is still true. Round-2 review.
    isDeepReplacing.value = true
    const loadingHandle = openFileOpLock(
      `Deep Replace: performing ${payload.length} copy-and-move op(s)…\n` +
      `Large files may take a while — please wait.`,
    )
    try {
      console.log('[FE DEBUG] confirmDeepReplace POST /replace-batch, ops =', payload.length)
      const result = await VideoDuplicateFinderService.replaceBatch(payload)
      console.log('[FE DEBUG] replaceBatch response:', result)
      const errCount = (result.errors_per_op ?? []).length
      if (errCount) {
        console.warn('[Deep Replace] error_ops:', result.errors_per_op)
        ElMessage.warning(
          `Completed with ${errCount} error op(s). deleted=${result.deleted_count}, renamed=${result.renamed_count}`,
        )
      } else {
        ElMessage.success(
          `Deep Replace complete: ${result.operations_count} ops, ` +
          `deleted=${result.deleted_count}, renamed=${result.renamed_count}`,
        )
      }
      showDeepReplaceDialog.value = false
      selectedForDelete.value = new Set()
      await loadDuplicatesPage(currentPage.value)
    } catch (error: any) {
      console.error('[FE DEBUG] confirmDeepReplace failed:', error)
      ElMessage.error(error?.message || 'Deep Replace failed')
    } finally {
      loadingHandle.close()
      isDeepReplacing.value = false
    }
  }


  // ========================================================================
  // S7.3: Deep delete by path
  // ========================================================================

  const deepPathDelete = ref<string>('')
  const showDeepDeleteDialog = ref(false)
  const deepDeletePreview = ref<{
    deepPath:     string
    matchedCount: number
    fileList:     string[]
  }>({ deepPath: '', matchedCount: 0, fileList: [] })

  /** Set deepPathDelete from a clicked video, then immediately preview. */
  async function setDeepDeletePath(filePath: string) {
    if (isDeleting.value) {
      console.log('[FE DEBUG] setDeepDeletePath skipped — a delete is in flight')
      return
    }
    if (!filePath) { ElMessage.warning('Empty file path'); return }
    const d = dirnameOf(filePath)
    if (!d) { ElMessage.warning('Cannot extract folder'); return }
    deepPathDelete.value = d
    await executeDeepPathDelete()
  }

  /** Preview which duplicate files live under deepPathDelete (no side-effects). */
  async function executeDeepPathDelete() {
    if (isDeleting.value) {
      console.log('[FE DEBUG] executeDeepPathDelete skipped — already in flight')
      return
    }
    if (!deepPathDelete.value || !deepPathDelete.value.trim()) {
      ElMessage.warning('Please enter a deep path to delete')
      return
    }
    const target = (settings.value.delete_target_path || '').trim()
    if (!target) {
      ElMessage.error('Set a delete target path in Settings first')
      return
    }
    isDeleting.value = true
    try {
      console.log('[FE DEBUG] executeDeepPathDelete POST /batch-delete-by-path preview_only=true')
      console.log('[FE DEBUG]   deep_path=' + deepPathDelete.value)
      const preview = await VideoDuplicateFinderService.batchDeleteByPath(
        deepPathDelete.value, /* previewOnly */ true,
      )
      console.log('[FE DEBUG] preview response:', preview)
      if (!preview.matched_files || preview.matched_files === 0) {
        ElMessage.warning(`No duplicate files under: ${deepPathDelete.value}`)
        return
      }
      deepDeletePreview.value = {
        deepPath:     deepPathDelete.value,
        matchedCount: preview.matched_files,
        fileList:     preview.file_list ?? [],
      }
      showDeepDeleteDialog.value = true
    } catch (error: any) {
      console.error('[FE DEBUG] executeDeepPathDelete failed:', error)
      ElMessage.error(error?.message || 'Preview failed')
    } finally {
      isDeleting.value = false
    }
  }

  async function confirmDeepDelete() {
    if (isDeleting.value) {
      console.log('[FE DEBUG] confirmDeepDelete skipped — already in flight')
      return
    }
    // Set the in-flight flag BEFORE closing the dialog so a rapid double-click
    // on the Element Plus primary button can't fire a second delete call.
    isDeleting.value = true
    showDeepDeleteDialog.value = false
    const loadingHandle = openFileOpLock(
      `Deep Delete: moving ${deepDeletePreview.value.matchedCount} video(s) + companions to trash,\n` +
      `then pruning empty directories. Large files may take a while.`,
    )
    try {
      console.log('[FE DEBUG] confirmDeepDelete POST /batch-delete-by-path preview_only=false')
      const result = await VideoDuplicateFinderService.batchDeleteByPath(
        deepDeletePreview.value.deepPath, /* previewOnly */ false,
      )
      console.log('[FE DEBUG] delete response:', result)
      if (result.deleted) {
        // Defensive: prune the just-deleted paths from selectedForDelete
        // BEFORE reloading. If the reload fails, we still avoid the stale-
        // selection footgun on the next deleteAllSelected. Round-2 review.
        const set = new Set(selectedForDelete.value)
        for (const fp of (deepDeletePreview.value.fileList || [])) set.delete(fp)
        selectedForDelete.value = set

        ElMessage.success(
          `Deleted ${result.deleted} file(s) (+${result.companions_moved ?? 0} companions, ` +
          `pruned ${result.pruned_dirs ?? 0} empty dirs)` +
          (result.failed ? `, ${result.failed} failed` : ''),
        )
        deepPathDelete.value = ''
        // Reload page 1 if we may have gone past the last page after mutation
        // (Round-2 review — clamp currentPage after bulk mutation).
        await loadDuplicatesPage(1)
      } else {
        ElMessage.error('No files were deleted')
      }
    } catch (error: any) {
      console.error('[FE DEBUG] confirmDeepDelete failed:', error)
      ElMessage.error(error?.message || 'Delete failed')
    } finally {
      loadingHandle.close()
      isDeleting.value = false
    }
  }

  function cancelDeepDelete() { showDeepDeleteDialog.value = false }

  /** File list relative to deep_path (for pretty display in the preview dialog). */
  const deepDeleteFileListRelative = computed(() => {
    const basePath = deepDeletePreview.value.deepPath
    if (!basePath) return []
    return deepDeletePreview.value.fileList.map(fp => {
      if (fp.startsWith(basePath)) {
        let rel = fp.substring(basePath.length)
        if (rel.startsWith('/') || rel.startsWith('\\')) rel = rel.substring(1)
        return rel || fp
      }
      return fp
    })
  })


  // ========================================================================
  // Video preview dialog
  // ========================================================================

  function openVideoPreview(video: VideoInfo) {
    previewVideo.value = video
    previewVideoUrl.value = VideoDuplicateFinderService.getPreviewUrl(video.file_path)
    showVideoPreviewDialog.value = true
  }

  function closeVideoPreview() {
    showVideoPreviewDialog.value = false
    previewVideo.value = null
    previewVideoUrl.value = ''
  }


  // ========================================================================
  // Media helpers
  // ========================================================================

  function getThumbnailUrl(filePath: string, tSeconds?: number): string {
    return VideoDuplicateFinderService.getThumbnailUrl(filePath, tSeconds)
  }

  function getPreviewUrl(filePath: string): string {
    return VideoDuplicateFinderService.getPreviewUrl(filePath)
  }

  async function openFolder(filePath: string) {
    const folder = dirnameOf(filePath)
    if (!folder) { ElMessage.error('Invalid file path'); return }
    try {
      const r = await VideoDuplicateFinderService.openFolder(folder)
      if (r.success) ElMessage.success(r.message || 'Folder opened')
      else ElMessage.error(r.error || 'Failed to open folder')
    } catch (error: any) {
      console.error('[Open folder] failed:', error)
      ElMessage.error(error?.message || 'Failed to open folder')
    }
  }


  // ========================================================================
  // Settings
  // ========================================================================

  async function loadSettings() {
    try {
      const s = await VideoDuplicateFinderService.getSettings()
      // Deep-merge for nested objects (phase1/phase2/auto_selection_rules)
      // — Tier-2 review: previously the shallow spread replaced whole
      // nested objects wholesale, losing defaults for keys the server
      // hadn't seeded yet.
      settings.value = {
        ...settings.value,
        ...s,
        phase1: { ...(settings.value.phase1 || {}), ...(s.phase1 || {}) } as any,
        phase2: { ...(settings.value.phase2 || {}), ...(s.phase2 || {}) } as any,
        auto_selection_rules: {
          ...(settings.value.auto_selection_rules || {}),
          ...(s.auto_selection_rules || {}),
        } as any,
      }
      // Nullish coalescing preserves an explicit 0 rather than falling
      // back to the default (Tier-3 review).
      threshold.value = s.similarity_threshold ?? 80
      pageSize.value  = s.page_size ?? 100
      settingsLoaded.value = true
    } catch (error: any) {
      console.error('[Settings load] failed:', error)
      ElMessage.error(error?.message || 'Failed to load settings')
      settingsLoaded.value = false
    }
  }

  async function saveAllSettings() {
    // Refuse to save if the initial GET failed — otherwise we'd overwrite
    // real server state with local defaults (Tier-2 review).
    if (!settingsLoaded.value) {
      ElMessage.error(
        'Cannot save: initial settings load failed. Reload the page and check the backend.'
      )
      return
    }

    // Basic input validation
    if (settings.value.folder_paths) {
      const empty = settings.value.folder_paths.filter(p => !p || p.trim() === '')
      if (empty.length > 0) {
        ElMessage.error('Folder path cannot be empty. Remove empty entries first.')
        return
      }
    }
    if (settings.value.page_size !== undefined) {
      if (settings.value.page_size < 20 || settings.value.page_size > 500) {
        ElMessage.error('Page size must be between 20 and 500')
        return
      }
    }

    try {
      isSaving.value = true
      settings.value.similarity_threshold = threshold.value
      await VideoDuplicateFinderService.updateSettings(settings.value)
      ElMessage.success('Settings saved')
    } catch (error: any) {
      console.error('[Settings save] failed:', error)
      ElMessage.error(error?.message || 'Save failed')
    } finally {
      isSaving.value = false
    }
  }

  // Settings list editors (folder_paths / exclude_folder_paths / prefer_folders / companion_extensions)

  function addFolderPath() {
    if (!settings.value.folder_paths) settings.value.folder_paths = []
    settings.value.folder_paths.push('')
  }
  function removeFolderPath(index: number) {
    settings.value.folder_paths?.splice(index, 1)
  }

  function addExcludeFolderPath() {
    if (!settings.value.exclude_folder_paths) settings.value.exclude_folder_paths = []
    settings.value.exclude_folder_paths.push('')
  }
  function removeExcludeFolderPath(index: number) {
    settings.value.exclude_folder_paths?.splice(index, 1)
  }

  function addPreferFolder() {
    if (!settings.value.auto_selection_rules) {
      settings.value.auto_selection_rules = { prefer_folders: [] }
    }
    if (!settings.value.auto_selection_rules.prefer_folders) {
      settings.value.auto_selection_rules.prefer_folders = []
    }
    settings.value.auto_selection_rules.prefer_folders.push('')
  }
  function removePreferFolder(index: number) {
    settings.value.auto_selection_rules?.prefer_folders?.splice(index, 1)
  }

  function addCompanionExtension() {
    if (!settings.value.companion_extensions) settings.value.companion_extensions = []
    settings.value.companion_extensions.push('')
  }
  function removeCompanionExtension(index: number) {
    settings.value.companion_extensions?.splice(index, 1)
  }


  // ========================================================================
  // Computed helpers
  // ========================================================================

  const hasResults = computed(() =>
    !!(scanResult.value?.duplicate_groups?.length),
  )

  const paginatedGroups = computed(() =>
    scanResult.value?.duplicate_groups || [],
  )

  function getActualGroupIndex(localIndex: number): number {
    return (currentPage.value - 1) * pageSize.value + localIndex
  }


  // ========================================================================
  // Lifecycle
  // ========================================================================

  onMounted(() => {
    connectWebSocket()
    loadSettings()
    loadPhase25Meta()
  })

  onBeforeUnmount(() => {
    disconnectWebSocket()
  })


  // ========================================================================
  // Public API
  // ========================================================================

  return {
    // -- state --
    threshold,
    scanResult,
    hasResults,
    paginatedGroups,

    // phase running states
    isPhase1Running, isPhase2Running, isPhase25Running, isPhase3Running,
    isFullPipelineRunning, isDeleting, isVerifying, isSaving,
    isBulkWhitelisting, isLoadingWhitelist, isLoadingPage,

    // phase progress + summaries
    phaseProgress,
    phase1Summary, phase2Summary, phase25Summary,
    phase25Meta, phase25NeedsAttention, phase25TooltipContent,

    // paging + sort
    currentPage, pageSize, totalPages, totalGroupsAll, totalFilesInDb,
    sortBy, sortOrder, SORT_OPTIONS,

    // selection
    selectedForDelete, selectedCount,

    // settings
    settings,

    // preview dialog
    showVideoPreviewDialog, previewVideo, previewVideoUrl,

    // whitelist drawer
    showWhitelistDrawer, whitelistGroups,

    // bulk-whitelist dialog
    showBulkWhitelistDialog, bulkWhitelistPreview,

    // additional loading flags
    isCleaningDb,
    settingsLoaded,

    // -- helpers --
    getFilenameFromPath, splitPath,
    formatFileSize, formatDuration, formatBitrate,
    formatTimestamp, formatResolutionLabel,

    // -- phase methods --
    runPhase1, stopPhase1,
    runPhase2, stopPhase2,
    runPhase25, stopPhase25, loadPhase25Meta,
    runPhase3, stopPhase3,
    runFullPipeline,

    // -- Phase 3 paging/sort --
    loadDuplicatesPage,
    handlePageChange, handlePageSizeChange, handleSortChange, toggleSortOrder,
    getActualGroupIndex,

    // -- selection --
    toggleFileSelection,
    hasSelectedInGroup, hasAllSelectedInGroup, getSelectedCountInGroup,
    selectAllInGroup,

    // -- delete / whitelist / verify --
    deleteSelectedInGroup, deleteAllSelected,
    addGroupToWhitelist,
    whitelistCurrentPage, deepWhitelistPath,
    confirmBulkWhitelist, cancelBulkWhitelist,
    loadWhitelistGroups, removeWhitelistGroup,
    verifyAndCleanup, cleanupDatabase,

    // -- S6 compare --
    isComparingFolder, isCompareAllRunning,
    compareFolderForGroup, runCompareAllFolders,

    // -- S7.2 replace --
    isReplacing, isDeepReplacing,
    replaceInGroup,
    deepReplacePath, cancelDeepReplace, confirmDeepReplace,
    showDeepReplaceDialog, deepReplacePreview,

    // -- S7.3 deep delete by path --
    deepPathDelete,
    showDeepDeleteDialog, deepDeletePreview, deepDeleteFileListRelative,
    setDeepDeletePath, executeDeepPathDelete, confirmDeepDelete, cancelDeepDelete,

    // -- preview --
    openVideoPreview, closeVideoPreview,

    // -- media / folder --
    getThumbnailUrl, getPreviewUrl, openFolder,

    // -- settings --
    loadSettings, saveAllSettings,
    addFolderPath, removeFolderPath,
    addExcludeFolderPath, removeExcludeFolderPath,
    addPreferFolder, removePreferFolder,
    addCompanionExtension, removeCompanionExtension,
  }
}
