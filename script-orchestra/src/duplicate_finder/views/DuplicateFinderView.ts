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
  const threshold = ref(90)
  const isScanning = ref(false)
  const isSaving = ref(false)
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
  const settings = ref<Settings>({
    delete_target_path: '',
    similarity_threshold: 90,
    folder_paths: [],
    folder_root_paths: {},
    max_cpu_cores: 1,
    auto_selection_rules: {
      auto_mark_numbered_copies: true,
      auto_mark_copy_suffix: true,
      prefer_folders: []
    }
  })
  const showWhitelistDrawer = ref(false)
  const whitelist = ref<Array<{ filename: string; filesize: number; added_time: number; note: string; preview_path?: string }>>([])
  const isLoadingWhitelist = ref(false)
  const isCleaning = ref(false)

  // 3-Phase workflow states
  const isPhase1Running = ref(false)
  const isPhase2Running = ref(false)
  const isPhase3Running = ref(false)
  const phaseProgress = ref({
    phase: 0,
    message: '',
    details: ''
  })

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
        const fileName = filePath.split('/').pop() || ''
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
    if (selectedFolders.value.length === 0) {
      ElMessage.warning('Please select at least one folder')
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

    // Start scan - HTTP API returns the full result
    try {
      const result = await DuplicateFinderService.scan({
        paths: selectedFolders.value,
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
    if (selectedFolders.value.length === 0) {
      ElMessage.warning('Please select at least one folder')
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

      // Now call API with the scan_id
      console.log('[Phase 1] Calling API with scan_id:', scanId)
      const result = await DuplicateFinderService.phase1Refresh(selectedFolders.value, scanId)

      // Update to 100% complete
      phaseProgress.value = {
        phase: 1,
        message: 'Phase 1: Complete',
        details: `Added: ${result.added}, Removed: ${result.removed}, Skipped: ${result.skipped}, Time: ${result.elapsed.toFixed(1)}s`,
        current: 100,
        total: 100,
        percentage: 100
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
      console.error('[Duplicate Finder] Phase 1 failed:', error)
      if (error.message && error.message.includes('stopped')) {
        ElMessage.warning('Phase 1 stopped by user')
      } else {
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
      await DuplicateFinderService.phase1Stop()
      ElMessage.info('Phase 1 stop signal sent')
    } catch (error: any) {
      console.error('[Duplicate Finder] Stop Phase 1 failed:', error)
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
      }

      // Convert threshold percentage to distance (80% = 12, 90% = 6)
      const thresholdDistance = Math.round(64 * (100 - threshold.value) / 100)

      const result = await DuplicateFinderService.phase2Build(thresholdDistance)

      // Listen for progress updates
      if (result.scan_id) {
        const startTime = Date.now()
        socket?.on(`scan:${result.scan_id}:progress`, (data: any) => {
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
      }

      // Update to 100% complete
      phaseProgress.value = {
        phase: 2,
        message: 'Phase 2: Complete',
        details: `Processed: ${result.processed}, Similarities: ${result.similarities_found}, Time: ${result.elapsed.toFixed(1)}s`,
        current: 100,
        total: 100,
        percentage: 100
      }

      ElMessage.success(`Phase 2 complete: Processed ${result.processed} images, found ${result.similarities_found} similarities (${result.elapsed.toFixed(1)}s)`)

      // Clean up listener
      if (result.scan_id) {
        socket?.off(`scan:${result.scan_id}:progress`)
      }

      // Clear progress after 2 seconds
      setTimeout(() => {
        if (phaseProgress.value.phase === 2) {
          phaseProgress.value = { phase: 0, message: '', details: '', current: 0, total: 0, percentage: 0 }
        }
      }, 2000)
    } catch (error: any) {
      console.error('[Duplicate Finder] Phase 2 failed:', error)
      if (error.message && error.message.includes('stopped')) {
        ElMessage.warning('Phase 2 stopped by user')
      } else {
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
      await DuplicateFinderService.phase2Stop()
      ElMessage.info('Phase 2 stop signal sent')
    } catch (error: any) {
      console.error('[Duplicate Finder] Stop Phase 2 failed:', error)
      ElMessage.error(error.message || 'Failed to stop Phase 2')
    }
  }

  /**
   * Phase 3: Get duplicates from similarities
   */
  async function runPhase3() {
    try {
      isPhase3Running.value = true
      phaseProgress.value = {
        phase: 3,
        message: 'Phase 3: Getting duplicates...',
        details: 'Starting...',
        current: 0,
        total: 0,
        percentage: 0
      }

      // Ensure WebSocket is connected
      if (!socket || !socket.connected) {
        connectWebSocket()
      }

      const result = await DuplicateFinderService.phase3GetDuplicates(threshold.value)

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

        scanResult.value = {
          scan_id: 'phase3-' + Date.now(),
          duplicate_groups: result.groups,
          total_files: result.total_duplicates,
          duplicate_count: result.total_duplicates
        }

        selectedForDelete.value.clear()

        // Apply auto-selection rules
        if (result.groups.length > 0) {
          applyAutoSelectionRules(result.groups)
        }
      }

      // Update to 100% complete
      phaseProgress.value = {
        phase: 3,
        message: 'Phase 3: Complete',
        details: `Groups: ${result.total_groups}, Duplicates: ${result.total_duplicates}, Time: ${result.elapsed.toFixed(3)}s`,
        current: 100,
        total: 100,
        percentage: 100
      }

      ElMessage.success(`Phase 3 complete: Found ${result.total_groups} duplicate groups with ${result.total_duplicates} images (${result.elapsed.toFixed(3)}s)`)

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
      console.error('[Duplicate Finder] Phase 3 failed:', error)
      if (error.message && error.message.includes('stopped')) {
        ElMessage.warning('Phase 3 stopped by user')
      } else {
        ElMessage.error(error.message || 'Phase 3 failed')
      }
    } finally {
      isPhase3Running.value = false
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
   * Open folder containing the image
   */
  async function openFolder(filePath: string) {
    const folderPath = filePath.substring(0, filePath.lastIndexOf('/'))
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
  function getRelativePath(filePath: string): string {
    const parts = filePath.split('/')
    if (parts.length >= 2) {
      // Show last 2-3 parts of the path
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
      threshold.value = result.similarity_threshold || 90

      // Initialize folder_root_paths if not present (backward compatibility)
      if (!settings.value.folder_root_paths) {
        settings.value.folder_root_paths = {}
      }

      // Initialize auto_selection_rules if not present (backward compatibility)
      if (!settings.value.auto_selection_rules) {
        settings.value.auto_selection_rules = {
          auto_mark_numbered_copies: true,
          auto_mark_copy_suffix: true,
          prefer_folders: []
        }
      }

      // Auto-select all folders on load
      if (result.folder_paths && result.folder_paths.length > 0) {
        selectedFolders.value = [...result.folder_paths]
      }
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
    if (!settings.value.folder_root_paths) {
      settings.value.folder_root_paths = {}
    }
    settings.value.folder_paths.push('')
  }

  /**
   * Remove folder path from settings
   */
  function removeFolderPath(index: number) {
    if (settings.value.folder_paths) {
      const pathToRemove = settings.value.folder_paths[index]
      settings.value.folder_paths.splice(index, 1)
      // Also remove from folder_root_paths
      if (settings.value.folder_root_paths && pathToRemove) {
        delete settings.value.folder_root_paths[pathToRemove]
      }
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
   * Add group to whitelist
   */
  async function addGroupToWhitelist(group: ImageInfo[], groupIndex: number) {
    if (group.length === 0) return

    const firstImage = group[0]
    const filename = firstImage.filename || firstImage.file_path.split('/').pop() || ''
    const filesize = firstImage.filesize

    try {
      await ElMessageBox.confirm(
        `Add "${filename}" (${formatFileSize(filesize)}) to whitelist? This group will not appear in future scans.`,
        'Add to Whitelist',
        {
          confirmButtonText: 'Add',
          cancelButtonText: 'Cancel',
          type: 'info'
        }
      )

      await DuplicateFinderService.addToWhitelist(filename, filesize, `Group ${groupIndex + 1}`, firstImage.file_path)
      ElMessage.success('Added to whitelist')

      // Auto-refresh whitelist
      await loadWhitelist()

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
   * Load whitelist
   */
  async function loadWhitelist() {
    isLoadingWhitelist.value = true
    try {
      const result = await DuplicateFinderService.getWhitelist()
      whitelist.value = result.whitelist
    } catch (error: any) {
      console.error('[Duplicate Finder] Failed to load whitelist:', error)
      ElMessage.error(error.message || 'Failed to load whitelist')
    } finally {
      isLoadingWhitelist.value = false
    }
  }

  /**
   * Remove from whitelist
   */
  async function removeFromWhitelist(filename: string, filesize: number, index: number) {
    try {
      await ElMessageBox.confirm(
        `Remove "${filename}" from whitelist?`,
        'Confirm Remove',
        {
          confirmButtonText: 'Remove',
          cancelButtonText: 'Cancel',
          type: 'warning'
        }
      )

      await DuplicateFinderService.removeFromWhitelist(filename, filesize)
      ElMessage.success('Removed from whitelist')

      // Remove from local list
      whitelist.value.splice(index, 1)
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
   * Clean up database by removing entries for files that no longer exist
   */
  async function cleanupDatabase() {
    try {
      await ElMessageBox.confirm(
        'This will scan your folder paths and remove database entries for files that no longer exist. Continue?',
        'Confirm Cleanup',
        {
          confirmButtonText: 'Clean',
          cancelButtonText: 'Cancel',
          type: 'warning'
        }
      )

      isCleaning.value = true
      const result = await DuplicateFinderService.cleanupDatabase()
      ElMessage.success(result.message || `Cleanup complete: removed ${result.removed_hashes} hash entries and ${result.removed_whitelist} whitelist entries`)
    } catch (error: any) {
      if (error !== 'cancel') {
        console.error('[Duplicate Finder] Cleanup failed:', error)
        ElMessage.error(error.message || 'Cleanup failed')
      }
    } finally {
      isCleaning.value = false
    }
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
    isCleaning,
    isVerifying,
    scanProgress,
    scanResult,
    selectedForDelete,
    hasResults,
    settings,
    showWhitelistDrawer,
    whitelist,
    isLoadingWhitelist,
    // 3-Phase workflow states
    isPhase1Running,
    isPhase2Running,
    isPhase3Running,
    phaseProgress,
    // Methods
    startScan,
    stopScan,
    rescanFromCache,
    // 3-Phase workflow methods
    runPhase1,
    stopPhase1,
    runPhase2,
    stopPhase2,
    runPhase3,
    stopPhase3,
    toggleFileSelection,
    hasSelectedInGroup,
    getSelectedCountInGroup,
    deleteSelectedInGroup,
    openFolder,
    getImageUrl,
    getRelativePath,
    formatFileSize,
    getCpuMarks,
    saveFolderSettings,
    saveAdvancedSettings,
    addFolderPath,
    removeFolderPath,
    addExcludeFolderPath,
    removeExcludeFolderPath,
    addGroupToWhitelist,
    loadWhitelist,
    removeFromWhitelist,
    formatTimestamp,
    cleanupDatabase,
    verifyAndCleanup,
    addPreferFolder,
    removePreferFolder
  }
}
