/**
 * Duplicate Finder View Logic
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DuplicateFinderService, type ImageInfo, type ScanResult, type Settings } from '../service/DuplicateFinderService'
import io, { Socket } from 'socket.io-client'
import { v4 as uuidv4 } from 'uuid'
import { BACKEND_BASE_URL } from '@/basic/Constants'
import { RecycleScroller } from 'vue-virtual-scroller'

export function useDuplicateFinderView() {
  const selectedFolders = ref<string[]>([])
  const threshold = ref(80)
  const isScanning = ref(false)
  const isSaving = ref(false)
  const isDeleting = ref(false)
  const deepPathDelete = ref<string>('')
  const currentScanId = ref<string | null>(null)
  const scanProgress = ref({
    current: 0,
    total: 0,
    percentage: 0,
    message: ''
  })
  const scanResult = ref<ScanResult | null>(null)
  const selectedForDelete = ref<Set<string>>(new Set())

  // Deep path delete confirmation dialog
  const showDeepDeleteDialog = ref(false)
  const deepDeletePreview = ref<{
    deepPath: string
    matchedCount: number
    fileList: string[]
  }>({
    deepPath: '',
    matchedCount: 0,
    fileList: []
  })

  const settings = ref<Settings>({
    delete_target_path: '',
    similarity_threshold: 80,
    folder_paths: [],
    max_cpu_cores: 1,
    page_size: 100,  // Default page size
    auto_selection_rules: {
      auto_mark_numbered_copies: true,
      auto_mark_copy_suffix: true,
      prefer_folders: []
    },
    phase1: {
      worker_handler_size: 1,
      db_commit_batch_size: 100,
      progress_update_interval: 100,
      ipc_chunk_size: 10,
      scan_delay: 0.0,
      compute_delay: 0.0
    },
    phase2: {
      worker_handler_size: 1,
      db_commit_batch_size: 100,
      progress_update_interval: 100,
      ipc_chunk_size: 10,
      compare_delay: 0.0
    },
    // Keep old performance for backward compatibility
    performance: {
      scan_delay: 0.0,
      compute_delay: 0.0,
      compare_delay: 0.0,
      chunk_size: 100,
      progress_update_interval: 100
    }
  })
  const showWhitelistDrawer = ref(false)
  const whitelistGroups = ref<Array<{
    group_id: number
    added_time: number
    members: Array<{
      image_id: number
      filename: string
      filesize: number
      file_path: string
      phash: string
      resolution: string
    }>
  }>>([])
  const isLoadingWhitelist = ref(false)

  /**
   * Helper: Get filename from path (cross-platform)
   */
  function getFilenameFromPath(filePath: string): string {
    const lastSlash = Math.max(filePath.lastIndexOf('/'), filePath.lastIndexOf('\\'))
    return lastSlash >= 0 ? filePath.substring(lastSlash + 1) : filePath
  }

  /**
   * Helper: Split path into parts (cross-platform)
   */
  function splitPath(filePath: string): string[] {
    // Normalize path separators to forward slash, then split
    return filePath.replace(/\\/g, '/').split('/')
  }

  // Pagination for duplicate groups
  const currentPage = ref(1)
  const pageSize = ref(100)
  const totalPages = ref(1)
  const totalGroupsAll = ref(0)  // Total groups across all pages
  const totalFilesInDb = ref(0)  // Total rows in image_hashes (all known files)
  const isLoadingPage = ref(false)  // Loading indicator for page changes

  // Phase 3 sort controls (UI-exposed; backend whitelist of columns enforced server-side)
  type SortBy =
    | 'folder_dup_count'
    | 'representative_file_path'
    | 'max_filesize'
    | 'min_filesize'
    | 'max_mtime'
    | 'min_mtime'
    | 'member_count'
  const sortBy = ref<SortBy>('folder_dup_count')
  const sortOrder = ref<'asc' | 'desc'>('desc')
  // Tiebreakers (representative_file_path ASC, then group_id ASC) are applied
  // server-side regardless of the user's primary sort, so within-tier groups
  // always appear in folder + filename order.
  const SORT_OPTIONS: { value: SortBy; label: string }[] = [
    { value: 'folder_dup_count',         label: 'Hot folder (most duplicates first)' },
    { value: 'representative_file_path', label: 'Folder + filename' },
    { value: 'member_count',             label: 'Group size (member count)' },
    { value: 'max_filesize',             label: 'Max file size' },
    { value: 'min_filesize',             label: 'Min file size' },
    { value: 'max_mtime',                label: 'Newest modified' },
    { value: 'min_mtime',                label: 'Oldest modified' },
  ]

  // 3-Phase workflow states
  const isPhase1Running = ref(false)
  const isPhase2Running = ref(false)
  const isPhase25Running = ref(false)
  const isPhase3Running = ref(false)
  const isBulkWhitelisting = ref(false)
  const isComparingFolder = ref(false)
  const isCompareAllRunning = ref(false)
  const isFullPipelineRunning = ref(false)

  // Group preview dialog (large side-by-side image view).
  // Only available for groups with ≤3 members.
  const showGroupPreviewDialog = ref(false)
  const groupPreviewData = ref<{ group: any[]; groupIndex: number; actualIndex: number }>({
    group: [],
    groupIndex: 0,
    actualIndex: 0,
  })

  function openGroupPreview(group: any[], groupIndex: number) {
    if (!Array.isArray(group) || group.length === 0) {
      ElMessage.info('Empty group')
      return
    }
    if (group.length > 3) {
      ElMessage.warning('Preview is only available for groups with ≤3 images')
      return
    }
    groupPreviewData.value = {
      group,
      groupIndex,
      actualIndex: getActualGroupIndex(groupIndex),
    }
    showGroupPreviewDialog.value = true
  }

  function closeGroupPreview() {
    showGroupPreviewDialog.value = false
  }
  // Latest Phase 2.5 materialization metadata (loaded on mount + after each run)
  const phase25Meta = ref<Record<string, string>>({})
  const phaseProgress = ref({
    phase: 0,
    message: '',
    details: '',
    current: 0,
    total: 0,
    percentage: 0
  })

  const phase1Summary = ref<{
    added: number
    removed: number
    skipped: number
    elapsed: string
  } | null>(null)

  const phase2Summary = ref<{
    processed: number
    similarities_found: number
    elapsed: string
  } | null>(null)

  let socket: Socket | null = null

  /**
   * Connect WebSocket
   */
  function connectWebSocket() {
    socket = io(BACKEND_BASE_URL)

    socket.on('connect', () => {
      console.log('[Duplicate Finder] WebSocket connected')
    })

    socket.on('disconnect', () => {
      console.log('[Duplicate Finder] WebSocket disconnected')
    })
  }

  /**
   * Disconnect WebSocket
   */
  function disconnectWebSocket() {
    if (socket) {
      socket.disconnect()
      socket = null
    }
  }

  /**
   * Apply auto-selection rules to duplicate groups
   */
  function applyAutoSelectionRules(groups: ImageInfo[][]) {
    if (!settings.value.auto_selection_rules) return

    const rules = settings.value.auto_selection_rules

    groups.forEach(group => {
      if (group.length < 2) return

      // Extract filenames without extensions for comparison
      const getBaseName = (filePath: string) => {
        const fileName = getFilenameFromPath(filePath)
        return fileName.replace(/\.[^/.]+$/, '') // Remove extension
      }

      // Rule 1: Auto-mark numbered copies like X(1).jpg, X(2).jpg
      if (rules.auto_mark_numbered_copies) {
        // Find the base file (without numbered suffix)
        const baseFile = group.find(img => {
          const baseName = getBaseName(img.file_path)
          return !/\(\d+\)$/.test(baseName) && !/\s+\(\d+\)$/.test(baseName)
        })

        if (baseFile) {
          // Mark all numbered copies for deletion
          group.forEach(img => {
            if (img.file_path !== baseFile.file_path) {
              const baseName = getBaseName(img.file_path)
              // Match patterns like "filename(1)", "filename (2)"
              if (/\(\d+\)$/.test(baseName) || /\s+\(\d+\)$/.test(baseName)) {
                selectedForDelete.value.add(img.file_path)
              }
            }
          })
        }
      }

      // Rule 2: Auto-mark "copy" suffix like X_copy.jpg, X-copy.jpg, X copy.jpg
      if (rules.auto_mark_copy_suffix) {
        // Find the original file (without copy suffix)
        const originalFile = group.find(img => {
          const baseName = getBaseName(img.file_path)
          return !/_copy$/i.test(baseName) &&
                 !/-copy$/i.test(baseName) &&
                 !/\s+copy$/i.test(baseName) &&
                 !/\scopy$/i.test(baseName)
        })

        if (originalFile) {
          // Mark all copy files for deletion
          group.forEach(img => {
            if (img.file_path !== originalFile.file_path) {
              const baseName = getBaseName(img.file_path)
              if (/_copy$/i.test(baseName) ||
                  /-copy$/i.test(baseName) ||
                  /\s+copy$/i.test(baseName) ||
                  /\scopy$/i.test(baseName)) {
                selectedForDelete.value.add(img.file_path)
              }
            }
          })
        }
      }

      // Rule 3: Prefer files in specific folders
      if (rules.prefer_folders && rules.prefer_folders.length > 0) {
        const preferredFiles = group.filter(img =>
          rules.prefer_folders!.some(folder => img.file_path.startsWith(folder))
        )

        if (preferredFiles.length > 0) {
          // Mark all non-preferred files for deletion
          group.forEach(img => {
            if (!preferredFiles.includes(img)) {
              selectedForDelete.value.add(img.file_path)
            }
          })
        }
      }
    })
  }

  /**
   * Start scan
   */
  async function startScan() {
    if (!settings.value.folder_paths || settings.value.folder_paths.length === 0) {
      ElMessage.warning('Please add at least one folder in Settings')
      return
    }

    // Filter out empty paths before sending to API
    const validPaths = settings.value.folder_paths.filter(path => path && path.trim() !== '')
    if (validPaths.length === 0) {
      ElMessage.warning('Please add at least one valid folder path in Settings')
      return
    }

    // Save settings before scanning
    try {
      settings.value.similarity_threshold = threshold.value
      await DuplicateFinderService.updateSettings(settings.value)
    } catch (error: any) {
      console.error('[Duplicate Finder] Failed to save settings:', error)
      ElMessage.error(error.message || 'Failed to save settings')
      return
    }

    // Generate scan ID
    const scanId = uuidv4()
    currentScanId.value = scanId
    isScanning.value = true
    scanProgress.value = {
      current: 0,
      total: 0,
      percentage: 0,
      message: 'Starting scan...'
    }
    // Initialize with empty result for streaming
    scanResult.value = {
      scan_id: scanId,
      duplicate_groups: [],
      total_files: 0,
      duplicate_count: 0
    }
    selectedForDelete.value.clear()

    // Connect WebSocket if not connected
    if (!socket || !socket.connected) {
      connectWebSocket()
    }

    // Listen for progress updates (with streaming groups)
    socket?.on(`scan:${scanId}:progress`, (data: any) => {
      console.log('[Duplicate Finder] Progress:', data)
      scanProgress.value = {
        current: data.current,
        total: data.total,
        percentage: data.percentage,
        message: data.message
      }

      // If progress contains groups_batch, add them to the result in real-time
      if (data.groups_batch && Array.isArray(data.groups_batch)) {
        if (scanResult.value && scanResult.value.duplicate_groups) {
          // Add group_id to each new group
          const newGroups = data.groups_batch.map((group: any, index: number) => {
            const groupId = `group-${scanResult.value!.duplicate_groups.length + index}`
            return Object.assign(group, { group_id: groupId })
          })

          // Append new groups
          scanResult.value.duplicate_groups.push(...newGroups)

          console.log(`[Duplicate Finder] Received ${newGroups.length} groups, total: ${scanResult.value.duplicate_groups.length}`)
        }
      }
    })

    // Listen for completion (WebSocket now only sends summary, not full result)
    socket?.on(`scan:${scanId}:complete`, (data: any) => {
      console.log('[Duplicate Finder] Complete (summary):', data)
      // Note: data.result is now just a summary, not the full scan result
      // The full result will come from the HTTP response below
      isScanning.value = false
      ElMessage.success(`Scan complete: Found ${data.result.groups_count || 0} duplicate groups`)
    })

    // Listen for errors
    socket?.on(`scan:${scanId}:error`, (data: any) => {
      console.error('[Duplicate Finder] Error:', data)
      ElMessage.error(`Scan failed: ${data.error}`)
      isScanning.value = false
    })

    // Start scan - HTTP API returns the full result - use filtered valid paths
    try {
      const result = await DuplicateFinderService.scan({
        paths: validPaths,
        threshold: threshold.value,
        scan_id: currentScanId.value
      })

      // Merge HTTP result with WebSocket streaming result
      // HTTP result is the authoritative final result
      if (result.duplicate_groups) {
        result.duplicate_groups = result.duplicate_groups.map((group, index) => {
          // Add a unique ID for each group for virtual scroller
          return Object.assign(group, { group_id: `group-${index}` })
        })
      }

      // Update with final result (may include groups missed by WebSocket)
      scanResult.value = result

      // Apply auto-selection rules
      if (result.duplicate_groups && result.duplicate_groups.length > 0) {
        applyAutoSelectionRules(result.duplicate_groups)
      }
    } catch (error: any) {
      console.error('[Duplicate Finder] Scan failed:', error)
      ElMessage.error(error.message || 'Scan failed')
      isScanning.value = false
    }
  }

  /**
   * Stop current scan
   */
  async function stopScan() {
    if (!currentScanId.value) {
      ElMessage.warning('No active scan to stop')
      return
    }

    try {
      await ElMessageBox.confirm(
        'Are you sure you want to stop the current scan? Already found groups will be kept.',
        'Stop Scan',
        {
          confirmButtonText: 'Stop',
          cancelButtonText: 'Continue Scanning',
          type: 'warning'
        }
      )

      const result = await DuplicateFinderService.stopScan(currentScanId.value)
      ElMessage.success(result.message || 'Scan stopped')
      isScanning.value = false
      currentScanId.value = null
    } catch (error: any) {
      if (error !== 'cancel') {
        console.error('[Duplicate Finder] Stop scan failed:', error)
        ElMessage.error(error.message || 'Failed to stop scan')
      }
    }
  }

  /**
   * Rescan from cache (using existing phash data)
   */
  async function rescanFromCache() {
    try {
      isScanning.value = true
      scanProgress.value = {
        current: 0,
        total: 0,
        percentage: 0,
        message: 'Loading cached data...'
      }

      const result = await DuplicateFinderService.rescanFromCache(threshold.value, true)

      // Add group IDs for virtual scroller
      if (result.duplicate_groups) {
        result.duplicate_groups = result.duplicate_groups.map((group, index) => {
          return Object.assign(group, { group_id: `group-${index}` })
        })
      }

      scanResult.value = result
      selectedForDelete.value.clear()

      // Apply auto-selection rules
      if (result.duplicate_groups && result.duplicate_groups.length > 0) {
        applyAutoSelectionRules(result.duplicate_groups)
      }

      ElMessage.success(`Quick rescan complete: Found ${result.duplicate_groups.length} duplicate groups using cached data`)
    } catch (error: any) {
      console.error('[Duplicate Finder] Rescan from cache failed:', error)
      ElMessage.error(error.message || 'Rescan failed')
    } finally {
      isScanning.value = false
    }
  }

  /**
   * Phase 1: Refresh images - scan filesystem, sync DB, compute phash
   */
  async function runPhase1() {
    if (!settings.value.folder_paths || settings.value.folder_paths.length === 0) {
      ElMessage.warning('Please add at least one folder in Settings')
      return
    }

    // Filter out empty paths before sending to API
    const validPaths = settings.value.folder_paths.filter(path => path && path.trim() !== '')
    if (validPaths.length === 0) {
      ElMessage.warning('Please add at least one valid folder path in Settings')
      return
    }

    // Generate scan_id FIRST
    const scanId = `phase1-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`

    try {
      isPhase1Running.value = true
      phaseProgress.value = {
        phase: 1,
        message: 'Phase 1: Refreshing images...',
        details: 'Starting...',
        current: 0,
        total: 0,
        percentage: 0
      }

      // Ensure WebSocket is connected
      if (!socket || !socket.connected) {
        connectWebSocket()
        // Wait a bit for connection
        await new Promise(resolve => setTimeout(resolve, 200))
      }

      // Register listener BEFORE calling API
      const startTime = Date.now()

      console.log('[Phase 1] Registering WebSocket listener for:', `scan:${scanId}:progress`)

      socket?.on(`scan:${scanId}:progress`, (data: any) => {
        console.log('[Phase 1] Progress update:', data)
        const elapsed = (Date.now() - startTime) / 1000
        const rate = data.current > 0 ? data.current / elapsed : 0
        const remaining = rate > 0 ? (data.total - data.current) / rate : 0

        phaseProgress.value = {
          phase: 1,
          message: data.message || 'Phase 1: Refreshing images...',
          details: `${data.current}/${data.total} - ETA: ${remaining > 0 ? Math.ceil(remaining) + 's' : 'N/A'}`,
          current: data.current,
          total: data.total,
          percentage: data.percentage
        }
      })

      // Now call API with the scan_id - use filtered valid paths
      console.log('[Phase 1] Calling API with scan_id:', scanId)
      const result = await DuplicateFinderService.phase1Refresh(validPaths, scanId)

      // Update to 100% complete
      phaseProgress.value = {
        phase: 1,
        message: 'Phase 1: Complete',
        details: `Added: ${result.added}, Removed: ${result.removed}, Skipped: ${result.skipped}, Time: ${result.elapsed.toFixed(1)}s`,
        current: 100,
        total: 100,
        percentage: 100
      }

      // Set Phase 1 Summary
      phase1Summary.value = {
        added: result.added,
        removed: result.removed,
        skipped: result.skipped,
        elapsed: result.elapsed.toFixed(1)
      }

      ElMessage.success(`Phase 1 complete: +${result.added}, -${result.removed}, skipped ${result.skipped} (${result.elapsed.toFixed(1)}s)`)

      // Clean up listener
      socket?.off(`scan:${scanId}:progress`)

      // Clear progress after 2 seconds
      setTimeout(() => {
        if (phaseProgress.value.phase === 1) {
          phaseProgress.value = { phase: 0, message: '', details: '', current: 0, total: 0, percentage: 0 }
        }
      }, 2000)
    } catch (error: any) {
      // Check if error is due to stop (499 = Client Closed Request, or ERR_BAD_REQUEST, or contains 'stopped')
      const isStopped = error.status === 499 ||
                        error.code === 'ERR_BAD_REQUEST' ||
                        (error.message && error.message.includes('stopped'))

      if (isStopped) {
        console.log('[Duplicate Finder] Phase 1 stopped by user')
        ElMessage.warning('Phase 1 stopped by user')
      } else {
        console.error('[Duplicate Finder] Phase 1 failed:', error)
        ElMessage.error(error.message || 'Phase 1 failed')
      }
    } finally {
      isPhase1Running.value = false
    }
  }

  /**
   * Phase 1: Stop
   */
  async function stopPhase1() {
    try {
      console.log('[Frontend] 🛑 User clicked STOP for Phase 1')
      console.log('[Frontend] Calling API: /duplicate-finder/phase1/stop')
      const response = await DuplicateFinderService.phase1Stop()
      console.log('[Frontend] ✅ Phase 1 stop API response:', response)
      ElMessage.info('Phase 1 stop signal sent')
    } catch (error: any) {
      console.error('[Frontend] ❌ Stop Phase 1 failed:', error)
      ElMessage.error(error.message || 'Failed to stop Phase 1')
    }
  }

  /**
   * Phase 2: Build similarities table
   */
  async function runPhase2() {
    try {
      isPhase2Running.value = true
      phaseProgress.value = {
        phase: 2,
        message: 'Phase 2: Building similarities...',
        details: 'Starting...',
        current: 0,
        total: 0,
        percentage: 0
      }

      // Ensure WebSocket is connected
      if (!socket || !socket.connected) {
        connectWebSocket()
        // Wait a bit for connection
        await new Promise(resolve => setTimeout(resolve, 200))
      }

      // Generate scan_id and register listener BEFORE calling API
      const scanId = `phase2-${Date.now()}-${Math.random().toString(36).substring(7)}`
      const startTime = Date.now()

      console.log('[Phase 2] Registering WebSocket listener for:', `scan:${scanId}:progress`)

      socket?.on(`scan:${scanId}:progress`, (data: any) => {
        console.log('[Phase 2] Progress update:', data)
        const elapsed = (Date.now() - startTime) / 1000
        const rate = data.current > 0 ? data.current / elapsed : 0
        const remaining = rate > 0 ? (data.total - data.current) / rate : 0

        phaseProgress.value = {
          phase: 2,
          message: data.message || 'Phase 2: Building similarities...',
          details: `${data.current}/${data.total} - ETA: ${remaining > 0 ? Math.ceil(remaining) + 's' : 'N/A'}`,
          current: data.current,
          total: data.total,
          percentage: data.percentage
        }
      })

      // Convert threshold percentage to distance (80% = 12, 90% = 6)
      const thresholdDistance = Math.round(64 * (100 - threshold.value) / 100)

      // Now call API with the scan_id
      console.log('[Phase 2] Calling API with scan_id:', scanId)
      const result = await DuplicateFinderService.phase2Build(thresholdDistance, scanId)

      // Update to 100% complete
      phaseProgress.value = {
        phase: 2,
        message: 'Phase 2: Complete',
        details: `Processed: ${result.processed}, Similarities: ${result.similarities_found}, Time: ${result.elapsed.toFixed(1)}s`,
        current: 100,
        total: 100,
        percentage: 100
      }

      // Set Phase 2 Summary
      phase2Summary.value = {
        processed: result.processed,
        similarities_found: result.similarities_found,
        elapsed: result.elapsed.toFixed(1)
      }

      ElMessage.success(`Phase 2 complete: Processed ${result.processed} images, found ${result.similarities_found} similarities (${result.elapsed.toFixed(1)}s)`)

      // Clean up listener
      socket?.off(`scan:${scanId}:progress`)

      // Clear progress after 2 seconds
      setTimeout(() => {
        if (phaseProgress.value.phase === 2) {
          phaseProgress.value = { phase: 0, message: '', details: '', current: 0, total: 0, percentage: 0 }
        }
      }, 2000)
    } catch (error: any) {
      // Check if error is due to stop (499 = Client Closed Request, or ERR_BAD_REQUEST, or contains 'stopped')
      const isStopped = error.status === 499 ||
                        error.code === 'ERR_BAD_REQUEST' ||
                        (error.message && error.message.includes('stopped'))

      if (isStopped) {
        console.log('[Duplicate Finder] Phase 2 stopped by user')
        ElMessage.warning('Phase 2 stopped by user')
      } else {
        console.error('[Duplicate Finder] Phase 2 failed:', error)
        ElMessage.error(error.message || 'Phase 2 failed')
      }
    } finally {
      isPhase2Running.value = false
    }
  }

  /**
   * Phase 2: Stop
   */
  async function stopPhase2() {
    try {
      console.log('[Frontend] 🛑 User clicked STOP for Phase 2')
      console.log('[Frontend] Calling API: /duplicate-finder/phase2/stop')
      const response = await DuplicateFinderService.phase2Stop()
      console.log('[Frontend] ✅ Phase 2 stop API response:', response)
      ElMessage.info('Phase 2 stop signal sent')
    } catch (error: any) {
      console.error('[Frontend] ❌ Stop Phase 2 failed:', error)
      ElMessage.error(error.message || 'Failed to stop Phase 2')
    }
  }

  // ========== Phase 2.5: Materialize Groups ==========

  /**
   * True if Phase 2.5 needs (re-)running: never materialized, or threshold
   * doesn't match the current UI threshold.
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
    const ts = m.materialized_at ? new Date(parseFloat(m.materialized_at) * 1000).toLocaleString() : '?'
    return `Materialized at ${matT}% with ${groupCount} groups (${ts}).`
  })

  async function loadPhase25Meta() {
    try {
      const { meta } = await DuplicateFinderService.phase25Meta()
      phase25Meta.value = meta || {}
    } catch (error: any) {
      console.warn('[Frontend] Failed to load Phase 2.5 meta:', error)
      phase25Meta.value = {}
    }
  }

  async function runPhase25() {
    try {
      isPhase25Running.value = true
      phaseProgress.value = {
        phase: 25,
        message: 'Phase 2.5: Materializing groups...',
        details: 'Starting...',
        current: 0,
        total: 100,
        percentage: 0,
      }

      if (!socket || !socket.connected) {
        connectWebSocket()
      }

      // Pre-subscribe is not possible (we get scan_id only after the call returns)
      // Use a temporary listener pattern after the call kicks off — but the call
      // is synchronous from the FE perspective. Instead, just rely on initial /
      // final progress: WebSocket events fire during the call.
      // Workaround: bind listener to a generic channel pattern after we know scan_id.

      const result = await DuplicateFinderService.phase25Materialize(threshold.value, true)

      // Late-bind WS listener won't catch much (call already finished), so
      // synthesize final progress here.
      phaseProgress.value = {
        phase: 25,
        message: 'Phase 2.5: Complete',
        details: `Groups: ${result.groups_count}, Members: ${result.members_count}, Time: ${result.elapsed.toFixed(2)}s`,
        current: 100,
        total: 100,
        percentage: 100,
      }

      ElMessage.success(
        `Phase 2.5 complete: ${result.groups_count} groups materialized at ${result.threshold_percent}% (${result.elapsed.toFixed(2)}s)`
      )

      await loadPhase25Meta()

      setTimeout(() => {
        if (phaseProgress.value.phase === 25) {
          phaseProgress.value = { phase: 0, message: '', details: '', current: 0, total: 0, percentage: 0 }
        }
      }, 2000)
    } catch (error: any) {
      console.error('[Frontend] Phase 2.5 failed:', error)
      ElMessage.error(error.message || 'Phase 2.5 failed')
    } finally {
      isPhase25Running.value = false
    }
  }

  async function stopPhase25() {
    try {
      await DuplicateFinderService.phase25Stop()
      ElMessage.info('Phase 2.5 stop signal sent')
    } catch (error: any) {
      console.error('[Frontend] Stop Phase 2.5 failed:', error)
      ElMessage.error(error.message || 'Failed to stop Phase 2.5')
    }
  }

  /**
   * Bulk-whitelist all groups on the current Phase 3 page. After confirmation,
   * sends one batch request to the backend; group_stats repair runs once on
   * the unique image set, then the current page is reloaded.
   */
  // Dialog state for bulk-whitelist preview (shown before sending the request)
  const showBulkWhitelistDialog = ref(false)
  const bulkWhitelistPreview = ref<{
    groups: any[][]              // raw groups (each group is an array of image objects)
    payload: number[][]          // sanitized image_ids per group
    groupCount: number
    imageCount: number
  }>({ groups: [], payload: [], groupCount: 0, imageCount: 0 })

  function whitelistCurrentPage() {
    const groups = (scanResult.value?.duplicate_groups || []) as any[][]
    if (groups.length === 0) {
      ElMessage.info('No groups to whitelist')
      return
    }

    const payload = groups
      .map((g) => Array.isArray(g) ? g.map((img: any) => img.id).filter((x: any) => typeof x === 'number') : [])
      .filter((ids: number[]) => ids.length >= 2)

    if (payload.length === 0) {
      ElMessage.warning('No valid groups (need ≥ 2 images with ids)')
      return
    }

    const imageCount = payload.reduce((s, ids) => s + ids.length, 0)
    bulkWhitelistPreview.value = {
      groups,
      payload,
      groupCount: payload.length,
      imageCount,
    }
    showBulkWhitelistDialog.value = true
  }

  function cancelBulkWhitelist() {
    showBulkWhitelistDialog.value = false
  }

  /**
   * Deep Whitelist (current-page scoped) — given a file under some folder,
   * find every duplicate group ON THE CURRENT PHASE-3 PAGE that has at least
   * one member under that folder (recursive), and show them in the bulk-
   * whitelist confirmation dialog. Confirming reuses the existing bulk-
   * whitelist confirm flow.
   *
   * Constraint: scope is the currently-visible page, not the whole DB.
   * Use the "Whitelist all on this page" button for everything visible
   * without the folder filter.
   */
  async function deepWhitelistPath(filePath: string) {
    if (!filePath) {
      ElMessage.warning('Empty file path')
      return
    }
    // Extract the directory path (works for both / and \)
    const lastSep = Math.max(filePath.lastIndexOf('/'), filePath.lastIndexOf('\\'))
    if (lastSep < 0) {
      ElMessage.warning('Cannot extract folder from path')
      return
    }
    const dirPath = filePath.substring(0, lastSep)
    const sep     = filePath.includes('\\') ? '\\' : '/'
    const dirPrefix = dirPath + sep

    // Filter the CURRENT page's groups — recursive match on member.file_path
    const currentPageGroups = (scanResult.value?.duplicate_groups || []) as any[]
    const matchedGroups = currentPageGroups.filter((g: any) =>
      Array.isArray(g) && g.some((img: any) => {
        const fp = img?.file_path
        if (typeof fp !== 'string') return false
        return fp === dirPath || fp.startsWith(dirPrefix)
      })
    )

    if (matchedGroups.length === 0) {
      ElMessage.info('No groups on this page have files under that folder.')
      return
    }

    const payload = matchedGroups
      .map((g: any) => Array.isArray(g) ? g.map((img: any) => img.id).filter((x: any) => typeof x === 'number') : [])
      .filter((ids: number[]) => ids.length >= 2)
    const imageCount = payload.reduce((s: number, ids: number[]) => s + ids.length, 0)

    bulkWhitelistPreview.value = {
      groups: matchedGroups,
      payload,
      groupCount: payload.length,
      imageCount,
    }
    showBulkWhitelistDialog.value = true
  }

  async function confirmBulkWhitelist() {
    const { payload, groupCount, imageCount } = bulkWhitelistPreview.value
    if (!payload.length) {
      showBulkWhitelistDialog.value = false
      return
    }
    try {
      isBulkWhitelisting.value = true
      const result = await DuplicateFinderService.bulkAddGroupsToWhitelist(payload)
      ElMessage.success(
        `Whitelisted ${result.added_groups} groups (${result.image_count} images)` +
        (result.skipped_groups ? `, skipped ${result.skipped_groups}` : '')
      )
      showBulkWhitelistDialog.value = false
      // Reload current page so the whitelisted groups disappear
      await loadDuplicatesPage(currentPage.value)
    } catch (error: any) {
      console.error('[Frontend] Bulk whitelist failed:', error)
      ElMessage.error(error.message || 'Bulk whitelist failed')
    } finally {
      isBulkWhitelisting.value = false
      // (Keep the preview values intact in case user wants to inspect afterward)
      void groupCount
      void imageCount
    }
  }

  /**
   * Re-run Phase 1 + 2 + 2.5 against the folders containing a specific group's
   * members. Use case: a group looks like it's missing duplicate partners that
   * the user can see on disk — force a focused re-comparison.
   */
  async function compareFolderForGroup(group: any[]) {
    if (!Array.isArray(group) || group.length === 0) {
      ElMessage.info('Empty group')
      return
    }
    // Collect unique dir_paths (parent folders of every member)
    const folderSet = new Set<string>()
    for (const img of group) {
      const fp = img?.file_path
      if (typeof fp === 'string' && fp) {
        const sep = fp.includes('\\') ? '\\' : '/'
        const lastSep = fp.lastIndexOf(sep)
        const dir = lastSep > 0 ? fp.substring(0, lastSep) : fp
        folderSet.add(dir)
      }
    }
    const folders = Array.from(folderSet)
    if (folders.length === 0) {
      ElMessage.warning('No folders extracted from this group')
      return
    }

    try {
      await ElMessageBox.confirm(
        `This will pairwise-compare ALL images under ${folders.length} folder(s) (recursive):\n\n` +
        folders.slice(0, 5).join('\n') +
        (folders.length > 5 ? `\n… and ${folders.length - 5} more` : '') +
        '\n\nIt only inserts new similarity edges within this scope — nothing is deleted, ' +
        'nothing outside these folders is touched. Then Phase 2.5 rematerializes. Continue?',
        'Compare Folder',
        { type: 'warning', confirmButtonText: 'Run', cancelButtonText: 'Cancel' }
      )
    } catch {
      return
    }

    try {
      isComparingFolder.value = true
      phaseProgress.value = {
        phase: 1,
        message: 'Compare Folder: starting…',
        details: `${folders.length} folder(s)`,
        current: 0,
        total: 100,
        percentage: 0,
      }
      const result = await DuplicateFinderService.compareFolders(folders, threshold.value)
      const cmp = result?.compare || {}
      const groups25 = result?.phase25?.groups_count ?? '?'
      ElMessage.success(
        `Compare folder complete: scope=${cmp.scope_total ?? '?'}, ` +
        `new phashes=${cmp.new_phashes_computed ?? 0}, ` +
        `pairs found=${cmp.pairs_found ?? 0}, ` +
        `new edges=${cmp.new_similarities_inserted ?? 0}, ` +
        `phase2.5 groups=${groups25}`
      )
      phaseProgress.value = {
        phase: 25,
        message: 'Compare Folder: complete',
        details: `Materialized ${groups25} groups`,
        current: 100,
        total: 100,
        percentage: 100,
      }
      // Refresh meta and reload current Phase 3 page (groups may have shifted)
      await loadPhase25Meta()
      await loadDuplicatesPage(1)
      setTimeout(() => {
        if (phaseProgress.value.phase === 25) {
          phaseProgress.value = { phase: 0, message: '', details: '', current: 0, total: 0, percentage: 0 }
        }
      }, 2000)
    } catch (error: any) {
      console.error('[Frontend] Compare folder failed:', error)
      ElMessage.error(error.message || 'Compare folder failed')
    } finally {
      isComparingFolder.value = false
    }
  }

  /**
   * Compare All Folders — server-side collects every folder touching any
   * materialized duplicate group, then runs Compare Folder over the union.
   * Used to backfill missed similarities globally in one shot.
   */
  async function runCompareAllFolders(skipConfirm: boolean = false) {
    if (!skipConfirm) {
      try {
        await ElMessageBox.confirm(
          'This will run Compare Folder for every folder that has files in any duplicate group.\n\n' +
          'Folders are first grouped into connected clusters (folders that share at least one group). ' +
          'Each cluster is then compared independently — total work scales with the sum of cluster sizes, ' +
          'not the grand total.\n\n' +
          'No files on disk are modified. Only new similarity edges may be added; nothing is deleted.\n\n' +
          'Continue?',
          'Compare All Folders',
          { type: 'warning', confirmButtonText: 'Run', cancelButtonText: 'Cancel' },
        )
      } catch {
        return
      }
    }

    try {
      isCompareAllRunning.value = true
      phaseProgress.value = {
        phase: 1,
        message: 'Compare All Folders: starting…',
        details: 'Building folder clusters',
        current: 0,
        total: 100,
        percentage: 0,
      }
      const result = await DuplicateFinderService.compareAllFolders(threshold.value)
      const cmp = result?.compare || {}
      const groups25 = result?.phase25?.groups_count ?? '?'
      if (result.folders_count === 0) {
        ElMessage.info(result.message || 'No folders to compare')
      } else {
        const skipMsg = (result as any).clusters_skipped
          ? `, skipped ${(result as any).clusters_skipped} large cluster(s) covering ${(result as any).folders_in_skipped_clusters} folder(s)`
          : ''
        ElMessage.success(
          `Compare All complete: ${result.clusters_count ?? '?'} cluster(s) over ${result.folders_count} folder(s)${skipMsg}, ` +
          `scope=${cmp.scope_total ?? '?'}, ` +
          `new phashes=${cmp.new_phashes_computed ?? 0}, ` +
          `pairs found=${cmp.pairs_found ?? 0}, ` +
          `new edges=${cmp.new_similarities_inserted ?? 0}, ` +
          `phase2.5 groups=${groups25}`,
        )
      }
      phaseProgress.value = {
        phase: 25,
        message: 'Compare All Folders: complete',
        details: `Materialized ${groups25} groups`,
        current: 100,
        total: 100,
        percentage: 100,
      }
      await loadPhase25Meta()
      await loadDuplicatesPage(1)
      setTimeout(() => {
        if (phaseProgress.value.phase === 25) {
          phaseProgress.value = { phase: 0, message: '', details: '', current: 0, total: 0, percentage: 0 }
        }
      }, 2000)
    } catch (error: any) {
      console.error('[Frontend] Compare All Folders failed:', error)
      ElMessage.error(error.message || 'Compare All Folders failed')
    } finally {
      isCompareAllRunning.value = false
    }
  }

  /**
   * Full pipeline: Phase 1 → Phase 2 → Phase 2.5 → Compare All Folders.
   * Sequential, single confirmation. Each underlying phase still manages its
   * own progress UI and toasts; this wrapper just orchestrates.
   */
  async function runFullPipeline() {
    try {
      await ElMessageBox.confirm(
        'This runs the full pipeline in sequence:\n\n' +
        '  1. Phase 1  — scan filesystem, compute phash for new files\n' +
        '  2. Phase 2  — build similarity edges\n' +
        '  3. Phase 2.5 — materialize duplicate groups\n' +
        '  4. Compare All Folders — backfill missed similarities (clustered, ≥4-folder clusters skipped)\n\n' +
        'Each phase logs its own progress. Total time depends on file count.\n\nContinue?',
        'Run Full Pipeline',
        { type: 'warning', confirmButtonText: 'Run All', cancelButtonText: 'Cancel' },
      )
    } catch {
      return
    }

    isFullPipelineRunning.value = true
    try {
      console.log('[Pipeline] ▶ Phase 1 starting')
      await runPhase1()
      console.log('[Pipeline] ✓ Phase 1 done')

      console.log('[Pipeline] ▶ Phase 2 starting')
      await runPhase2()
      console.log('[Pipeline] ✓ Phase 2 done')

      console.log('[Pipeline] ▶ Phase 2.5 starting')
      await runPhase25()
      console.log('[Pipeline] ✓ Phase 2.5 done')

      console.log('[Pipeline] ▶ Compare All Folders starting')
      await runCompareAllFolders(true)  // skip its own confirm
      console.log('[Pipeline] ✓ Compare All Folders done')

      ElMessage.success('Full pipeline complete')
    } catch (error: any) {
      console.error('[Pipeline] failed:', error)
      ElMessage.error('Pipeline failed: ' + (error?.message || String(error)))
    } finally {
      isFullPipelineRunning.value = false
    }
  }

  /**
   * Phase 3: Get duplicates from similarities
   */
  /**
   * Phase 3: Get duplicates (initial load or page change)
   */
  async function runPhase3() {
    await loadDuplicatesPage(1)  // Start from page 1
  }

  /**
   * Load duplicates for a specific page
   */
  async function loadDuplicatesPage(page: number) {
    try {
      console.log(`[Phase 3 Frontend] 📥 Requesting page ${page} (page_size: ${pageSize.value})`)

      isPhase3Running.value = true
      isLoadingPage.value = true
      phaseProgress.value = {
        phase: 3,
        message: `Phase 3: Loading page ${page}...`,
        details: 'Starting...',
        current: 0,
        total: 0,
        percentage: 0
      }

      // Ensure WebSocket is connected
      if (!socket || !socket.connected) {
        connectWebSocket()
      }

      const result = await DuplicateFinderService.phase3GetDuplicates(
        threshold.value,
        page,
        pageSize.value,
        sortBy.value,
        sortOrder.value
      )

      // Handle 409-style materialization errors (unwrapped by service layer)
      if (result.error === 'no_materialization') {
        ElMessage.warning('No materialized groups. Please run Phase 2.5 first.')
        scanResult.value = null
        currentPage.value = 1
        totalPages.value = 0
        totalGroupsAll.value = 0
        await loadPhase25Meta()
        phaseProgress.value = { phase: 0, message: '', details: '', current: 0, total: 0, percentage: 0 }
        return
      }
      if (result.error === 'threshold_mismatch') {
        ElMessage.warning(
          result.message || `Materialized at ${result.materialized_threshold}%, but UI requests ${result.current_threshold}%. Please re-run Phase 2.5.`
        )
        scanResult.value = null
        currentPage.value = 1
        totalPages.value = 0
        totalGroupsAll.value = 0
        await loadPhase25Meta()
        phaseProgress.value = { phase: 0, message: '', details: '', current: 0, total: 0, percentage: 0 }
        return
      }

      console.log(`[Phase 3 Frontend] ✅ Response received:`)
      console.log(`[Phase 3 Frontend]   - Groups received: ${result.groups?.length || 0}`)
      console.log(`[Phase 3 Frontend]   - Total groups (all pages): ${result.total_groups}`)
      console.log(`[Phase 3 Frontend]   - Current page: ${result.current_page}`)
      console.log(`[Phase 3 Frontend]   - Total pages: ${result.total_pages}`)
      console.log(`[Phase 3 Frontend]   - Total duplicates (all pages): ${result.total_duplicates}`)

      // Listen for progress updates
      if (result.scan_id) {
        const startTime = Date.now()
        socket?.on(`scan:${result.scan_id}:progress`, (data: any) => {
          const elapsed = (Date.now() - startTime) / 1000
          const rate = data.current > 0 ? data.current / elapsed : 0
          const remaining = rate > 0 ? (data.total - data.current) / rate : 0

          phaseProgress.value = {
            phase: 3,
            message: data.message || 'Phase 3: Getting duplicates...',
            details: `${data.current}/${data.total} - ETA: ${remaining > 0 ? Math.ceil(remaining) + 's' : 'N/A'}`,
            current: data.current,
            total: data.total,
            percentage: data.percentage
          }
        })
      }

      // Convert to ScanResult format
      if (result.groups) {
        result.groups = result.groups.map((group, index) => {
          return Object.assign(group, { group_id: `group-${index}` })
        })

        // Count total files in current page groups
        const filesInCurrentPage = result.groups.reduce((sum, group) => sum + group.length, 0)

        console.log(`[Phase 3 Frontend] 📊 Storing in scanResult:`)
        console.log(`[Phase 3 Frontend]   - Groups in memory: ${result.groups.length}`)
        console.log(`[Phase 3 Frontend]   - Files in memory: ${filesInCurrentPage}`)

        scanResult.value = {
          scan_id: result.scan_id || 'phase3-' + Date.now(),
          duplicate_groups: result.groups,  // Only current page groups
          total_files: result.total_duplicates,
          duplicate_count: result.total_duplicates
        }

        // Update pagination info
        currentPage.value = result.current_page
        totalPages.value = result.total_pages
        totalGroupsAll.value = result.total_groups
        totalFilesInDb.value = result.total_files_in_db ?? 0

        console.log(`[Phase 3 Frontend] 🖼️  Images that will be loaded:`)
        result.groups.forEach((group, groupIdx) => {
          console.log(`[Phase 3 Frontend]   - Group ${groupIdx + 1}: ${group.length} images`)
        })

        selectedForDelete.value.clear()

        // Apply auto-selection rules to current page
        if (result.groups.length > 0) {
          applyAutoSelectionRules(result.groups)
        }
      }

      // Update to 100% complete
      phaseProgress.value = {
        phase: 3,
        message: page === 1 ? 'Phase 3: Complete' : `Page ${page} loaded`,
        details: `Groups: ${result.total_groups}, Duplicates: ${result.total_duplicates}, Time: ${result.elapsed.toFixed(3)}s`,
        current: 100,
        total: 100,
        percentage: 100
      }

      if (page === 1) {
        ElMessage.success(`Phase 3 complete: Found ${result.total_groups} duplicate groups with ${result.total_duplicates} images (${result.elapsed.toFixed(3)}s)`)
      } else {
        ElMessage.success(`Loaded page ${page} (${result.groups.length} groups)`)
      }

      // Clean up listener
      if (result.scan_id) {
        socket?.off(`scan:${result.scan_id}:progress`)
      }

      // Clear progress after 2 seconds
      setTimeout(() => {
        if (phaseProgress.value.phase === 3) {
          phaseProgress.value = { phase: 0, message: '', details: '', current: 0, total: 0, percentage: 0 }
        }
      }, 2000)
    } catch (error: any) {
      // Check if error is due to stop (499 = Client Closed Request, or ERR_BAD_REQUEST, or contains 'stopped')
      const isStopped = error.status === 499 ||
                        error.code === 'ERR_BAD_REQUEST' ||
                        (error.message && error.message.includes('stopped'))

      if (isStopped) {
        console.log('[Duplicate Finder] Phase 3 stopped by user')
        ElMessage.warning('Phase 3 stopped by user')
      } else {
        console.error('[Duplicate Finder] Phase 3 failed:', error)
        ElMessage.error(error.message || 'Phase 3 failed')
      }
    } finally {
      isPhase3Running.value = false
      isLoadingPage.value = false
    }
  }

  /**
   * Phase 3: Stop
   */
  async function stopPhase3() {
    try {
      await DuplicateFinderService.phase3Stop()
      ElMessage.info('Phase 3 stop signal sent')
    } catch (error: any) {
      console.error('[Duplicate Finder] Stop Phase 3 failed:', error)
      ElMessage.error(error.message || 'Failed to stop Phase 3')
    }
  }

  /**
   * Computed: Get paginated groups (now just returns current page data directly)
   */
  const paginatedGroups = computed(() => {
    if (!scanResult.value || !scanResult.value.duplicate_groups) {
      return []
    }
    // Backend already returned only current page data, no need to slice
    return scanResult.value.duplicate_groups
  })

  /**
   * Get actual group index (accounting for pagination)
   */
  function getActualGroupIndex(localIndex: number): number {
    return (currentPage.value - 1) * pageSize.value + localIndex
  }

  /**
   * Handle page change
   */
  async function handlePageChange(newPage: number) {
    console.log(`[Pagination] 📄 Page changed from ${currentPage.value} to ${newPage}`)
    await loadDuplicatesPage(newPage)
  }

  /**
   * Handle page size change
   */
  async function handlePageSizeChange(newSize: number) {
    console.log(`[Pagination] 📏 Page size changed from ${pageSize.value} to ${newSize}`)
    pageSize.value = newSize
    currentPage.value = 1  // Reset to first page
    await loadDuplicatesPage(1)
  }

  /**
   * Handle sort change — reset to page 1 and reload.
   */
  async function handleSortChange() {
    console.log(`[Sort] 🔀 sort changed to ${sortBy.value} ${sortOrder.value}; reloading page 1`)
    currentPage.value = 1
    await loadDuplicatesPage(1)
  }

  function toggleSortOrder() {
    sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
    handleSortChange()
  }

  /**
   * Toggle file selection for deletion
   */
  function toggleFileSelection(filePath: string) {
    if (selectedForDelete.value.has(filePath)) {
      selectedForDelete.value.delete(filePath)
    } else {
      selectedForDelete.value.add(filePath)
    }
  }

  /**
   * Check if group has selected files
   */
  function hasSelectedInGroup(group: ImageInfo[]): boolean {
    return group.some(img => selectedForDelete.value.has(img.file_path))
  }

  /**
   * Get count of selected files in group
   */
  function getSelectedCountInGroup(group: ImageInfo[]): number {
    return group.filter(img => selectedForDelete.value.has(img.file_path)).length
  }

  /**
   * Check if all files in group are selected
   */
  function hasAllSelectedInGroup(group: ImageInfo[]): boolean {
    return group.length > 0 && group.every(img => selectedForDelete.value.has(img.file_path))
  }

  /**
   * Select all files in a group (or deselect if all are already selected)
   */
  function selectAllInGroup(group: ImageInfo[]) {
    const allSelected = hasAllSelectedInGroup(group)

    if (allSelected) {
      // Deselect all
      group.forEach(img => {
        selectedForDelete.value.delete(img.file_path)
      })
    } else {
      // Select all
      group.forEach(img => {
        selectedForDelete.value.add(img.file_path)
      })
    }
  }

  /**
   * Delete selected files in a specific group
   */
  async function deleteSelectedInGroup(group: ImageInfo[], groupIndex: number) {
    const filesToDelete = group
      .filter(img => selectedForDelete.value.has(img.file_path))
      .map(img => img.file_path)

    if (filesToDelete.length === 0) {
      ElMessage.warning('No files selected in this group')
      return
    }

    try {
      // Pass deepPathDelete if it's set
      const result = await DuplicateFinderService.deleteFiles(
        filesToDelete,
        deepPathDelete.value || undefined
      )

      if (result.success > 0) {
        ElMessage.success(`Moved ${result.success} files to delete target`)

        // When using deep path delete, files are moved with folder structure preserved
        // We need to verify which files still exist and clean up the groups
        if (deepPathDelete.value) {
          await verifyAndCleanup()
        } else {
          // Remove deleted files from result (original behavior)
          if (scanResult.value) {
            // Remove deleted files from the group
            scanResult.value.duplicate_groups[groupIndex] = group.filter(
              img => !selectedForDelete.value.has(img.file_path)
            )

            // If group has less than 2 images, remove the entire group
            if (scanResult.value.duplicate_groups[groupIndex].length < 2) {
              scanResult.value.duplicate_groups.splice(groupIndex, 1)
            }
          }

          // Clear selections for deleted files
          filesToDelete.forEach(path => selectedForDelete.value.delete(path))
        }
      }

      if (result.failed > 0) {
        ElMessage.error(`Failed to move ${result.failed} files`)
        console.error('Delete errors:', result.errors)
      }
    } catch (error: any) {
      console.error('[Duplicate Finder] Delete failed:', error)
      ElMessage.error(error.message || 'Delete failed')
    }
  }

  /**
   * Replace operation: keep the single selected image in the group, delete
   * all others (move to delete target), and move the selected one into the
   * anchor (img1) position — anchor's directory + anchor's basename +
   * selected's own extension.
   *
   * Requires exactly one image selected in the group.
   */
  async function replaceInGroup(group: ImageInfo[], groupIndex: number) {
    if (!Array.isArray(group) || group.length === 0) {
      ElMessage.warning('Empty group')
      return
    }
    if (group.length !== 2) {
      ElMessage.warning('Replace only works on groups with exactly 2 images')
      return
    }
    const selectedImgs = group.filter(img => selectedForDelete.value.has(img.file_path))
    if (selectedImgs.length !== 1) {
      ElMessage.warning('Replace requires exactly 1 selected image in this group')
      return
    }
    const selectedImg = selectedImgs[0]
    const anchorImg = group[0]
    const isAnchorSelected = selectedImg.file_path === anchorImg.file_path

    const groupPaths = group.map(img => img.file_path)
    const othersCount = groupPaths.length - 1

    // Compute target path preview for the confirmation message (mirrors backend
    // logic: anchor's dir + anchor's basename (no ext) + selected's ext).
    const winSep = anchorImg.file_path.includes('\\')
    const sep = winSep ? '\\' : '/'
    const anchorLast = Math.max(anchorImg.file_path.lastIndexOf('/'), anchorImg.file_path.lastIndexOf('\\'))
    const anchorDir = anchorLast > 0 ? anchorImg.file_path.substring(0, anchorLast) : ''
    const anchorBase = anchorLast > 0
      ? anchorImg.file_path.substring(anchorLast + 1)
      : anchorImg.file_path
    const anchorBaseNoExt = anchorBase.includes('.')
      ? anchorBase.substring(0, anchorBase.lastIndexOf('.'))
      : anchorBase
    const selBase = (() => {
      const last = Math.max(selectedImg.file_path.lastIndexOf('/'), selectedImg.file_path.lastIndexOf('\\'))
      return last > 0 ? selectedImg.file_path.substring(last + 1) : selectedImg.file_path
    })()
    const selExt = selBase.includes('.') ? selBase.substring(selBase.lastIndexOf('.')) : ''
    const previewDest = `${anchorDir}${sep}${anchorBaseNoExt}${selExt}`

    try {
      await ElMessageBox.confirm(
        `This will:\n` +
        `  • Move ${othersCount} non-selected image(s) to the delete target\n` +
        (isAnchorSelected
          ? `  • (Selected is already the anchor — no rename)\n`
          : `  • COPY selected to:\n      ${previewDest}\n` +
            `  • Then back up the ORIGINAL selected file to the delete target (safety copy)\n`) +
        `\nContinue?`,
        'Replace',
        { type: 'warning', confirmButtonText: 'Replace', cancelButtonText: 'Cancel' },
      )
    } catch {
      return
    }

    try {
      const result = await DuplicateFinderService.replaceInGroup(
        selectedImg.file_path,
        anchorImg.file_path,
        groupPaths,
      )
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
      // Drop selections for files that no longer exist
      groupPaths.forEach(p => selectedForDelete.value.delete(p))
      // Reload current page so groups are fresh
      await loadDuplicatesPage(currentPage.value)
    } catch (error: any) {
      console.error('[Frontend] Replace failed:', error)
      ElMessage.error(error.message || 'Replace failed')
    }
  }

  // ---- Deep Replace ----
  const showDeepReplaceDialog = ref(false)
  const isDeepReplacing = ref(false)
  const deepReplacePreview = ref<{
    folderPath: string
    operations: Array<{ selected: any; anchor: any; group: any[] }>
    badGroups: any[][]    // matched groups whose size is NOT 2 — block the batch
  }>({ folderPath: '', operations: [], badGroups: [] })

  /**
   * Deep Replace — batch replace for all groups on the current page that
   * have a file under the clicked image's folder.
   *
   * Strict guard: ALL matched groups must have exactly 2 images, otherwise
   * the WHOLE batch is blocked. We still show the dialog (with bad groups
   * highlighted) so the user can SEE which groups are blocking and resolve
   * them manually before retrying.
   */
  async function deepReplacePath(filePath: string) {
    if (!filePath) {
      ElMessage.warning('Empty file path')
      return
    }
    const lastSep = Math.max(filePath.lastIndexOf('/'), filePath.lastIndexOf('\\'))
    if (lastSep < 0) {
      ElMessage.warning('Cannot extract folder from this path')
      return
    }
    const dirPath = filePath.substring(0, lastSep)
    const sep     = filePath.includes('\\') ? '\\' : '/'
    const dirPrefix = dirPath + sep

    const currentPageGroups = (scanResult.value?.duplicate_groups || []) as any[][]
    const matched = currentPageGroups.filter((g: any) =>
      Array.isArray(g) && g.some((img: any) => {
        const fp = img?.file_path
        if (typeof fp !== 'string') return false
        return fp === dirPath || fp.startsWith(dirPrefix)
      })
    )

    if (matched.length === 0) {
      ElMessage.info('No groups on this page have files under that folder')
      return
    }

    // Partition into operations (size=2) and badGroups (size!=2). Show both.
    const operations: Array<{ selected: any; anchor: any; group: any[] }> = []
    const badGroups: any[][] = []
    for (const g of matched) {
      if (g.length === 2) {
        const selected = g.find((img: any) => {
          const fp = img?.file_path
          return typeof fp === 'string' && (fp === dirPath || fp.startsWith(dirPrefix))
        })
        const anchor = g.find((img: any) => img !== selected)
        if (selected && anchor) {
          operations.push({ selected, anchor, group: g })
        } else {
          badGroups.push(g)
        }
      } else {
        badGroups.push(g)
      }
    }

    deepReplacePreview.value = {
      folderPath: dirPath,
      operations,
      badGroups,
    }
    showDeepReplaceDialog.value = true
  }

  function cancelDeepReplace() {
    showDeepReplaceDialog.value = false
  }

  async function confirmDeepReplace() {
    if (deepReplacePreview.value.badGroups.length > 0) {
      ElMessage.error(
        `Replace is blocked: ${deepReplacePreview.value.badGroups.length} group(s) have a size other than 2.`
      )
      return
    }
    const ops = deepReplacePreview.value.operations
    if (!ops.length) {
      showDeepReplaceDialog.value = false
      return
    }
    const payload = ops.map(o => ({
      selected_file_path: o.selected.file_path,
      anchor_file_path:   o.anchor.file_path,
      group_file_paths:   o.group.map((m: any) => m.file_path),
    }))
    try {
      isDeepReplacing.value = true
      const result = await DuplicateFinderService.replaceBatch(payload)
      const errCount = (result.errors_per_op || []).length
      if (errCount) {
        console.warn('[Deep Replace] error_ops:', result.errors_per_op)
        ElMessage.warning(
          `Completed with ${errCount} error op(s). deleted=${result.deleted_count}, renamed=${result.renamed_count}. See console.`
        )
      } else {
        ElMessage.success(
          `Deep Replace complete: ${result.operations_count} ops, deleted=${result.deleted_count}, renamed=${result.renamed_count}`
        )
      }
      showDeepReplaceDialog.value = false
      selectedForDelete.value.clear()
      await loadDuplicatesPage(currentPage.value)
    } catch (error: any) {
      console.error('[Deep Replace] failed:', error)
      ElMessage.error(error.message || 'Deep Replace failed')
    } finally {
      isDeepReplacing.value = false
    }
  }

  /**
   * Open folder containing the image
   */
  async function openFolder(filePath: string) {
    // Handle both Unix (/) and Windows (\) path separators
    const lastSlash = Math.max(filePath.lastIndexOf('/'), filePath.lastIndexOf('\\'))

    if (lastSlash === -1) {
      ElMessage.error('Invalid file path')
      return
    }

    const folderPath = filePath.substring(0, lastSlash)

    try {
      const result = await DuplicateFinderService.openFolder(folderPath)
      if (result.success) {
        ElMessage.success(result.message || 'Folder opened successfully')
      } else {
        ElMessage.error(result.error || 'Failed to open folder')
      }
    } catch (error: any) {
      console.error('[Duplicate Finder] Open folder failed:', error)
      ElMessage.error(error.message || 'Failed to open folder')
    }
  }

  /**
   * Get image URL for display
   */
  function getImageUrl(filePath: string): string {
    return DuplicateFinderService.getImageUrl(filePath)
  }

  /**
   * Get relative path for display (show parent folder/filename)
   */
  /**
   * Get relative path for display (based on folder_paths as root)
   * This is a fallback when display_path is not provided by backend
   */
  function getRelativePath(filePath: string): string {
    if (!settings.value || !settings.value.folder_paths) {
      // Fallback: show last 2-3 parts of the path
      const parts = splitPath(filePath)
      if (parts.length >= 2) {
        return '.../' + parts.slice(-3).join('/')
      }
      return filePath
    }

    // Find the scan folder that contains this file (use it as root)
    let scanFolder: string | null = null
    const folderPaths = settings.value.folder_paths

    for (const folder of folderPaths) {
      // Handle both / and \ for matching
      const normalizedPath = filePath.replace(/\\/g, '/')
      const normalizedFolder = folder.replace(/\\/g, '/')
      if (normalizedPath.startsWith(normalizedFolder + '/') || normalizedPath === normalizedFolder) {
        scanFolder = folder
        break
      }
    }

    if (scanFolder) {
      // Calculate relative path from scan folder
      const normalizedPath = filePath.replace(/\\/g, '/')
      const normalizedFolder = scanFolder.replace(/\\/g, '/')
      if (normalizedPath.startsWith(normalizedFolder + '/')) {
        const relativePath = normalizedPath.substring(normalizedFolder.length + 1)
        // Remove filename, keep only directory path
        const lastSlash = relativePath.lastIndexOf('/')
        if (lastSlash > 0) {
          return relativePath.substring(0, lastSlash)
        }
        return '/'
      }
    }

    // Fallback: show last 2-3 parts of the path
    const parts = splitPath(filePath)
    if (parts.length >= 2) {
      return '.../' + parts.slice(-3).join('/')
    }
    return filePath
  }

  /**
   * Format file size
   */
  function formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  /**
   * Get CPU marks for slider based on system CPU count
   */
  function getCpuMarks() {
    const cpuCount = settings.value.system_cpu_count || 12
    const marks: Record<number, string> = { 1: '1' }

    if (cpuCount >= 4) marks[4] = '4'
    if (cpuCount >= 8) marks[8] = '8'
    if (cpuCount >= 12) marks[12] = '12'
    if (cpuCount > 12) marks[cpuCount] = String(cpuCount)

    return marks
  }

  /**
   * Load settings
   */
  async function loadSettings() {
    try {
      const result = await DuplicateFinderService.getSettings()
      settings.value = result
      threshold.value = result.similarity_threshold || 80

      // Initialize page_size if not present (backward compatibility)
      if (!settings.value.page_size) {
        settings.value.page_size = 100
      }
      // Sync pageSize ref with settings
      pageSize.value = settings.value.page_size

      // Initialize auto_selection_rules if not present (backward compatibility)
      if (!settings.value.auto_selection_rules) {
        settings.value.auto_selection_rules = {
          auto_mark_numbered_copies: true,
          auto_mark_copy_suffix: true,
          prefer_folders: []
        }
      }

      // Initialize performance settings if not present (backward compatibility)
      if (!settings.value.performance) {
        settings.value.performance = {
          scan_delay: 0.0,
          compute_delay: 0.0,
          compare_delay: 0.0,
          chunk_size: 100,
          progress_update_interval: 100
        }
      } else {
        // Ensure all performance settings exist
        if (!settings.value.performance.compute_delay) {
          settings.value.performance.compute_delay = 0.0
        }
        if (!settings.value.performance.progress_update_interval) {
          settings.value.performance.progress_update_interval = 100
        }
      }

      // Initialize phase1/phase2 settings from old performance if needed (backward compatibility)
      if (!settings.value.phase1 && settings.value.performance) {
        settings.value.phase1 = {
          worker_handler_size: 1,
          db_commit_batch_size: settings.value.performance.chunk_size || 100,
          progress_update_interval: settings.value.performance.progress_update_interval || 100,
          ipc_chunk_size: 10,
          scan_delay: settings.value.performance.scan_delay || 0.0,
          compute_delay: settings.value.performance.compute_delay || 0.0
        }
      }

      if (!settings.value.phase2 && settings.value.performance) {
        settings.value.phase2 = {
          worker_handler_size: 1,
          db_commit_batch_size: settings.value.performance.chunk_size || 100,
          progress_update_interval: settings.value.performance.progress_update_interval || 100,
          ipc_chunk_size: 10,
          compare_delay: settings.value.performance.compare_delay || 0.0
        }
      }

      // Auto-select all folders on load - no longer needed, all folders are scanned automatically
      // if (result.folder_paths && result.folder_paths.length > 0) {
      //   selectedFolders.value = [...result.folder_paths]
      // }
    } catch (error: any) {
      console.error('[Duplicate Finder] Failed to load settings:', error)
    }
  }

  /**
   * Save folder settings
   */
  async function saveFolderSettings() {
    isSaving.value = true
    try {
      // Update threshold in settings
      settings.value.similarity_threshold = threshold.value

      await DuplicateFinderService.updateSettings(settings.value)
      ElMessage.success('Settings saved successfully')

      // Reload settings to update UI
      await loadSettings()

      // Auto-close drawer after successful save
      showWhitelistDrawer.value = false
    } catch (error: any) {
      console.error('[Duplicate Finder] Failed to save settings:', error)
      ElMessage.error(error.message || 'Failed to save settings')
    } finally {
      isSaving.value = false
    }
  }

  /**
   * Save all settings (unified save function for drawer)
   */
  async function saveAllSettings() {
    isSaving.value = true
    try {
      // Validate folder paths - must not be empty
      if (settings.value.folder_paths && settings.value.folder_paths.length > 0) {
        const emptyPaths = settings.value.folder_paths.filter(path => !path || path.trim() === '')
        if (emptyPaths.length > 0) {
          ElMessage.error('Folder Path cannot be empty. Please fill in all folder paths or remove empty ones.')
          isSaving.value = false
          return
        }
      }

      // Validate page_size
      if (settings.value.page_size) {
        if (settings.value.page_size < 20 || settings.value.page_size > 500) {
          ElMessage.error('Page Size must be between 20 and 500')
          isSaving.value = false
          return
        }
      }

      // Save all settings including folders, advanced settings, and auto-selection rules
      await DuplicateFinderService.updateSettings({
        ...settings.value,
        similarity_threshold: threshold.value
      })

      // Update local threshold and pageSize
      settings.value.similarity_threshold = threshold.value
      if (settings.value.page_size) {
        pageSize.value = settings.value.page_size
      }

      ElMessage.success('All settings saved successfully')

      // Auto-close drawer after successful save
      showWhitelistDrawer.value = false
    } catch (error: any) {
      console.error('[Duplicate Finder] Failed to save settings:', error)
      ElMessage.error(error.message || 'Failed to save settings')
    } finally {
      isSaving.value = false
    }
  }

  /**
   * Save advanced settings (delete_target_path, phash_db_path, similarity_threshold)
   */
  async function saveAdvancedSettings() {
    isSaving.value = true
    try {
      await DuplicateFinderService.updateSettings({
        similarity_threshold: threshold.value,
        delete_target_path: settings.value.delete_target_path,
        phash_db_path: settings.value.phash_db_path,
        max_cpu_cores: settings.value.max_cpu_cores
      })
      // Update local settings
      settings.value.similarity_threshold = threshold.value
      ElMessage.success('Advanced settings saved successfully')
    } catch (error: any) {
      console.error('[Duplicate Finder] Failed to save advanced settings:', error)
      ElMessage.error(error.message || 'Failed to save advanced settings')
    } finally {
      isSaving.value = false
    }
  }

  /**
   * Add folder path to settings
   */
  function addFolderPath() {
    if (!settings.value.folder_paths) {
      settings.value.folder_paths = []
    }
    settings.value.folder_paths.push('')
  }

  /**
   * Remove folder path from settings
   */
  function removeFolderPath(index: number) {
    if (settings.value.folder_paths) {
      settings.value.folder_paths.splice(index, 1)
    }
  }

  /**
   * Add exclude folder path to settings
   */
  function addExcludeFolderPath() {
    if (!settings.value.exclude_folder_paths) {
      settings.value.exclude_folder_paths = []
    }
    settings.value.exclude_folder_paths.push('')
  }

  /**
   * Remove exclude folder path from settings
   */
  function removeExcludeFolderPath(index: number) {
    if (settings.value.exclude_folder_paths) {
      settings.value.exclude_folder_paths.splice(index, 1)
    }
  }

  /**
   * Add preferred folder to auto-selection rules
   */
  function addPreferFolder() {
    if (!settings.value.auto_selection_rules) {
      settings.value.auto_selection_rules = {
        auto_mark_numbered_copies: true,
        auto_mark_copy_suffix: true,
        prefer_folders: []
      }
    }
    if (!settings.value.auto_selection_rules.prefer_folders) {
      settings.value.auto_selection_rules.prefer_folders = []
    }
    settings.value.auto_selection_rules.prefer_folders.push('')
  }

  /**
   * Remove preferred folder from auto-selection rules
   */
  function removePreferFolder(index: number) {
    if (settings.value.auto_selection_rules?.prefer_folders) {
      settings.value.auto_selection_rules.prefer_folders.splice(index, 1)
    }
  }

  /**
   * Execute deep path delete (全局批量删除指定路径下的所有duplicate文件)
   */
  async function executeDeepPathDelete() {
    console.log('[DEBUG] executeDeepPathDelete called, deepPathDelete.value:', deepPathDelete.value)

    if (!deepPathDelete.value || deepPathDelete.value.trim() === '') {
      console.warn('[DEBUG] deepPathDelete is empty, showing warning')
      ElMessage.warning('Please enter a deep path to delete')
      return
    }

    try {
      console.log('[DEBUG] Starting preview request...')
      // Step 1: Preview - get list of files that will be deleted
      isDeleting.value = true
      ElMessage.info('Scanning for files to delete...')

      console.log('[DEBUG] Calling DuplicateFinderService.batchDeleteByPath with:', deepPathDelete.value)
      const previewResult = await DuplicateFinderService.batchDeleteByPath(
        deepPathDelete.value,
        true  // preview only
      )
      console.log('[DEBUG] Preview result:', previewResult)

      if (!previewResult.matched_files || previewResult.matched_files === 0) {
        console.log('[DEBUG] No files matched, showing warning')
        ElMessage.warning(`No duplicate files found under path: ${deepPathDelete.value}`)
        isDeleting.value = false
        return
      }

      console.log('[DEBUG] Found', previewResult.matched_files, 'files, showing dialog')
      // Step 2: Show confirmation with preview
      deepDeletePreview.value = {
        deepPath: deepPathDelete.value,
        matchedCount: previewResult.matched_files,
        fileList: previewResult.file_list || []
      }
      showDeepDeleteDialog.value = true
      console.log('[DEBUG] Dialog should be visible now, showDeepDeleteDialog.value:', showDeepDeleteDialog.value)
      isDeleting.value = false  // Reset loading state

    } catch (error: any) {
      console.error('[DEBUG] executeDeepPathDelete error:', error)
      console.error('[DEBUG] Error details:', {
        message: error.message,
        status: error.status,
        response: error.response
      })
      console.error('[Duplicate Finder] Failed to preview deep path delete:', error)
      ElMessage.error(error.message || 'Failed to preview files')
      isDeleting.value = false
    }
  }

  // Confirm and execute deep delete
  async function confirmDeepDelete() {
    try {
      showDeepDeleteDialog.value = false
      isDeleting.value = true

      // Execute actual deletion
      ElMessage.info(`Deleting ${deepDeletePreview.value.matchedCount} files...`)

      const deleteResult = await DuplicateFinderService.batchDeleteByPath(
        deepDeletePreview.value.deepPath,
        false  // actual deletion
      )

      if (deleteResult.deleted) {
        ElMessage.success(
          `Successfully deleted ${deleteResult.deleted} files` +
          (deleteResult.failed ? ` (${deleteResult.failed} failed)` : '')
        )

        // Clear deep delete path after successful deletion
        deepPathDelete.value = ''

        // Reload current page to refresh the view
        if (currentPage.value > 0) {
          await loadDuplicatesPage(currentPage.value)
        } else {
          await runPhase3()
        }
      } else {
        ElMessage.error('No files were deleted')
      }
    } catch (error: any) {
      console.error('[Duplicate Finder] Failed to execute deep path delete:', error)
      ElMessage.error(error.message || 'Failed to execute deep path delete')
    } finally {
      isDeleting.value = false
    }
  }

  // Cancel deep delete
  function cancelDeepDelete() {
    showDeepDeleteDialog.value = false
    isDeleting.value = false
  }

  /**
   * Set deep delete path from an image file path and trigger preview
   * Extracts the directory path, sets it to deepPathDelete, and shows preview dialog
   * Always overwrites the existing value
   */
  async function setDeepDeletePath(filePath: string) {
    console.log('[DEBUG] setDeepDeletePath called with:', filePath)
    try {
      // Extract directory path from file path
      const lastSlash = Math.max(filePath.lastIndexOf('/'), filePath.lastIndexOf('\\'))
      console.log('[DEBUG] lastSlash index:', lastSlash)

      if (lastSlash >= 0) {
        const dirPath = filePath.substring(0, lastSlash)
        console.log('[DEBUG] Extracted dirPath:', dirPath)

        deepPathDelete.value = dirPath
        console.log('[DEBUG] Set deepPathDelete.value to:', deepPathDelete.value)

        // Auto-trigger deep delete preview
        console.log('[DEBUG] Calling executeDeepPathDelete()...')
        await executeDeepPathDelete()
        console.log('[DEBUG] executeDeepPathDelete() completed')
      } else {
        console.warn('[DEBUG] Could not extract directory - no slash found')
        ElMessage.warning('Could not extract directory path from file')
      }
    } catch (error: any) {
      console.error('[DEBUG] setDeepDeletePath error:', error)
      console.error('[DEBUG] Error stack:', error.stack)
      console.error('[Duplicate Finder] Failed to set deep delete path:', error)
      ElMessage.error('Failed to set deep delete path')
    }
  }

  // Compute relative path for display in deep delete dialog
  const deepDeleteFileListRelative = computed(() => {
    const basePath = deepDeletePreview.value.deepPath
    if (!basePath) return []

    return deepDeletePreview.value.fileList.map((filePath: string) => {
      // Remove base path prefix to get relative path
      if (filePath.startsWith(basePath)) {
        let relativePath = filePath.substring(basePath.length)
        // Remove leading slash if present
        if (relativePath.startsWith('/')) {
          relativePath = relativePath.substring(1)
        }
        return relativePath || filePath
      }
      return filePath
    })
  })

  /**
   * Add group to whitelist
   */
  async function addGroupToWhitelist(group: ImageInfo[], groupIndex: number) {
    if (group.length < 2) return

    // Collect all image_ids from the group
    const image_ids = group.map(img => img.id).filter(id => id) as number[]
    if (image_ids.length < 2) {
      ElMessage.error('Group must have at least 2 images with valid IDs')
      return
    }

    try {
      await ElMessageBox.confirm(
        `Add this group (${image_ids.length} images) to whitelist? This group will not appear in future scans.`,
        'Add to Whitelist',
        {
          confirmButtonText: 'Add',
          cancelButtonText: 'Cancel',
          type: 'info'
        }
      )

      await DuplicateFinderService.addGroupToWhitelist(image_ids)
      ElMessage.success('Added group to whitelist')

      // Auto-refresh whitelist
      await loadWhitelistGroups()

      // Remove this group from results
      if (scanResult.value) {
        scanResult.value.duplicate_groups.splice(groupIndex, 1)
      }
    } catch (error: any) {
      if (error !== 'cancel') {
        console.error('[Duplicate Finder] Failed to add to whitelist:', error)
        ElMessage.error(error.message || 'Failed to add to whitelist')
      }
    }
  }

  /**
   * Load whitelist groups
   */
  async function loadWhitelistGroups() {
    isLoadingWhitelist.value = true
    try {
      const result = await DuplicateFinderService.getWhitelistGroups()
      whitelistGroups.value = result.whitelist_groups
    } catch (error: any) {
      console.error('[Duplicate Finder] Failed to load whitelist:', error)
      ElMessage.error(error.message || 'Failed to load whitelist')
    } finally {
      isLoadingWhitelist.value = false
    }
  }

  /**
   * Remove whitelist group
   */
  async function removeWhitelistGroup(group_id: number, index: number) {
    try {
      const group = whitelistGroups.value[index]
      const memberCount = group?.members?.length || 0

      await ElMessageBox.confirm(
        `Remove this whitelist group (${memberCount} images)?`,
        'Confirm Remove',
        {
          confirmButtonText: 'Remove',
          cancelButtonText: 'Cancel',
          type: 'warning'
        }
      )

      await DuplicateFinderService.removeWhitelistGroup(group_id)
      ElMessage.success('Removed from whitelist')

      // Remove from local list
      whitelistGroups.value.splice(index, 1)

      // Auto-refresh Phase 3 results if they exist
      if (scanResult.value && scanResult.value.duplicate_groups) {
        ElMessage.info('Refreshing duplicate groups...')
        if (currentPage.value > 0) {
          await loadDuplicatesPage(currentPage.value)
        } else {
          await runPhase3()
        }
      }
    } catch (error: any) {
      if (error !== 'cancel') {
        console.error('[Duplicate Finder] Failed to remove from whitelist:', error)
        ElMessage.error(error.message || 'Failed to remove from whitelist')
      }
    }
  }

  /**
   * Format timestamp to readable string
   */
  function formatTimestamp(timestamp: number): string {
    const date = new Date(timestamp * 1000)
    return date.toLocaleString()
  }


  /**
   * Verify and cleanup current scan results by checking which files still exist
   */
  const isVerifying = ref(false)

  async function verifyAndCleanup() {
    if (!scanResult.value || !scanResult.value.duplicate_groups) {
      ElMessage.warning('No scan results to verify')
      return
    }

    try {
      isVerifying.value = true

      // Call verification API
      const result = await DuplicateFinderService.verifyFiles(scanResult.value.duplicate_groups)

      if (result.missing_count === 0) {
        ElMessage.success('All files still exist. No cleanup needed.')
        return
      }

      // Show confirmation dialog with details
      const affectedGroupsInfo = result.affected_groups.length > 0
        ? `\n\nAffected groups: ${result.affected_groups.length}\nSample missing files:\n${result.missing_files.slice(0, 5).join('\n')}${result.missing_files.length > 5 ? '\n...' : ''}`
        : ''

      const removedGroupsInfo = result.removed_groups_count > 0
        ? `\n${result.removed_groups_count} groups will be removed (less than 2 files remaining).`
        : ''

      await ElMessageBox.confirm(
        `Found ${result.missing_count} missing files that were externally deleted.${affectedGroupsInfo}${removedGroupsInfo}\n\nDo you want to clean up the display?`,
        'Missing Files Detected',
        {
          confirmButtonText: 'Clean Up',
          cancelButtonText: 'Cancel',
          type: 'warning'
        }
      )

      // Update scan result with cleaned groups
      scanResult.value.duplicate_groups = result.cleaned_groups
      scanResult.value.duplicate_count = result.cleaned_groups.reduce((sum, group) => sum + group.length, 0)

      // Remove deleted files from selection
      result.missing_files.forEach(filePath => {
        selectedForDelete.value.delete(filePath)
      })

      let successMessage = `Cleanup complete! Removed ${result.affected_groups.length} affected groups.`
      if (result.removed_groups_count > 0) {
        successMessage += ` (${result.removed_groups_count} groups had <2 files)`
      }
      ElMessage.success(successMessage)

    } catch (error: any) {
      if (error !== 'cancel') {
        console.error('[Duplicate Finder] Verify error:', error)
        ElMessage.error(error.message || 'Failed to verify files')
      }
    } finally {
      isVerifying.value = false
    }
  }

  /**
   * Computed: Total files selected
   */
  const selectedCount = computed(() => selectedForDelete.value.size)

  /**
   * Computed: Has any results
   */
  const hasResults = computed(() => {
    return scanResult.value && scanResult.value.duplicate_groups.length > 0
  })

  onMounted(() => {
    connectWebSocket()
    loadSettings()
    loadPhase25Meta()
  })

  onBeforeUnmount(() => {
    disconnectWebSocket()
  })

  return {
    // Data
    selectedFolders,
    threshold,
    deepPathDelete,
    currentScanId,
    isScanning,
    isSaving,
    isDeleting,
    isVerifying,
    scanProgress,
    scanResult,
    selectedForDelete,
    hasResults,
    settings,
    showWhitelistDrawer,
    whitelistGroups,
    isLoadingWhitelist,
    // Pagination
    currentPage,
    pageSize,
    totalPages,
    totalGroupsAll,
    totalFilesInDb,
    isLoadingPage,
    paginatedGroups,
    // 3-Phase workflow states
    isPhase1Running,
    isPhase2Running,
    isPhase25Running,
    isPhase3Running,
    isBulkWhitelisting,
    isComparingFolder,
    phase25Meta,
    phase25NeedsAttention,
    phase25TooltipContent,
    phaseProgress,
    phase1Summary,
    phase2Summary,
    // Deep delete dialog
    showDeepDeleteDialog,
    deepDeletePreview,
    deepDeleteFileListRelative,
    // Helper functions
    getFilenameFromPath,
    splitPath,
    // Methods
    startScan,
    stopScan,
    rescanFromCache,
    // 3-Phase workflow methods
    runPhase1,
    stopPhase1,
    runPhase2,
    stopPhase2,
    runPhase25,
    stopPhase25,
    whitelistCurrentPage,
    cancelBulkWhitelist,
    confirmBulkWhitelist,
    showBulkWhitelistDialog,
    bulkWhitelistPreview,
    deepWhitelistPath,
    compareFolderForGroup,
    runCompareAllFolders,
    isCompareAllRunning,
    runFullPipeline,
    isFullPipelineRunning,
    showGroupPreviewDialog,
    groupPreviewData,
    openGroupPreview,
    closeGroupPreview,
    replaceInGroup,
    deepReplacePath,
    showDeepReplaceDialog,
    deepReplacePreview,
    isDeepReplacing,
    cancelDeepReplace,
    confirmDeepReplace,
    runPhase3,
    stopPhase3,
    toggleFileSelection,
    hasSelectedInGroup,
    hasAllSelectedInGroup,
    selectAllInGroup,
    getSelectedCountInGroup,
    deleteSelectedInGroup,
    openFolder,
    getImageUrl,
    getRelativePath,
    formatFileSize,
    getCpuMarks,
    getActualGroupIndex,
    handlePageChange,
    handlePageSizeChange,
    sortBy,
    sortOrder,
    SORT_OPTIONS,
    handleSortChange,
    toggleSortOrder,
    saveFolderSettings,
    saveAdvancedSettings,
    saveAllSettings,
    addFolderPath,
    removeFolderPath,
    addExcludeFolderPath,
    removeExcludeFolderPath,
    executeDeepPathDelete,
    confirmDeepDelete,
    cancelDeepDelete,
    setDeepDeletePath,
    addGroupToWhitelist,
    loadWhitelistGroups,
    removeWhitelistGroup,
    formatTimestamp,
    verifyAndCleanup,
    addPreferFolder,
    removePreferFolder
  }
}
