/**
 * Duplicate Finder View Logic
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DuplicateFinderService, type ImageInfo, type ScanResult, type Settings } from '../service/DuplicateFinderService'
import io, { Socket } from 'socket.io-client'
import { v4 as uuidv4 } from 'uuid'
import { BACKEND_BASE_URL } from '@/basic/Constants'

export function useDuplicateFinderView() {
  const selectedFolders = ref<string[]>([])
  const threshold = ref(90)
  const isScanning = ref(false)
  const isSaving = ref(false)
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

  let socket: Socket | null = null
  let currentScanId: string | null = null

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
    currentScanId = uuidv4()
    isScanning.value = true
    scanProgress.value = {
      current: 0,
      total: 0,
      percentage: 0,
      message: 'Starting scan...'
    }
    scanResult.value = null
    selectedForDelete.value.clear()

    // Connect WebSocket if not connected
    if (!socket || !socket.connected) {
      connectWebSocket()
    }

    // Listen for progress updates
    socket?.on(`scan:${currentScanId}:progress`, (data: any) => {
      console.log('[Duplicate Finder] Progress:', data)
      scanProgress.value = {
        current: data.current,
        total: data.total,
        percentage: data.percentage,
        message: data.message
      }
    })

    // Listen for completion
    socket?.on(`scan:${currentScanId}:complete`, (data: any) => {
      console.log('[Duplicate Finder] Complete:', data)
      scanResult.value = data.result
      isScanning.value = false

      // Apply auto-selection rules
      if (data.result.duplicate_groups && data.result.duplicate_groups.length > 0) {
        applyAutoSelectionRules(data.result.duplicate_groups)
      }

      ElMessage.success(`Scan complete: Found ${data.result.duplicate_groups.length} duplicate groups`)
    })

    // Listen for errors
    socket?.on(`scan:${currentScanId}:error`, (data: any) => {
      console.error('[Duplicate Finder] Error:', data)
      ElMessage.error(`Scan failed: ${data.error}`)
      isScanning.value = false
    })

    // Start scan
    try {
      await DuplicateFinderService.scan({
        paths: selectedFolders.value,
        threshold: threshold.value,
        scan_id: currentScanId
      })
    } catch (error: any) {
      console.error('[Duplicate Finder] Scan failed:', error)
      ElMessage.error(error.message || 'Scan failed')
      isScanning.value = false
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
      const result = await DuplicateFinderService.deleteFiles(filesToDelete)

      if (result.success > 0) {
        ElMessage.success(`Moved ${result.success} files to delete target`)

        // Remove deleted files from result
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
        phash_db_path: settings.value.phash_db_path
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
    selectedFolders,
    threshold,
    isScanning,
    isSaving,
    isCleaning,
    scanProgress,
    scanResult,
    selectedForDelete,
    hasResults,
    settings,
    showWhitelistDrawer,
    whitelist,
    isLoadingWhitelist,
    startScan,
    toggleFileSelection,
    hasSelectedInGroup,
    getSelectedCountInGroup,
    deleteSelectedInGroup,
    openFolder,
    getImageUrl,
    getRelativePath,
    formatFileSize,
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
    addPreferFolder,
    removePreferFolder
  }
}
