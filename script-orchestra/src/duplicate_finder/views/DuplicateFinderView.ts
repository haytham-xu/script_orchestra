/**
 * Duplicate Finder View Logic
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { DuplicateFinderService, type ImageInfo, type ScanResult } from '../service/DuplicateFinderService'
import io, { Socket } from 'socket.io-client'
import { v4 as uuidv4 } from 'uuid'
import { BACKEND_BASE_URL } from '@/basic/Constants'

export function useDuplicateFinderView() {
  const scanPaths = ref<string>('')
  const threshold = ref(90)
  const isScanning = ref(false)
  const scanProgress = ref({
    current: 0,
    total: 0,
    percentage: 0,
    message: ''
  })
  const scanResult = ref<ScanResult | null>(null)
  const selectedForDelete = ref<Set<string>>(new Set())

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
   * Start scan
   */
  async function startScan() {
    if (!scanPaths.value.trim()) {
      ElMessage.warning('Please enter at least one path')
      return
    }

    // Parse paths (comma or newline separated)
    const paths = scanPaths.value
      .split(/[,\n]/)
      .map(p => p.trim())
      .filter(p => p.length > 0)

    if (paths.length === 0) {
      ElMessage.warning('Please enter valid paths')
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
        paths,
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
  })

  onBeforeUnmount(() => {
    disconnectWebSocket()
  })

  return {
    scanPaths,
    threshold,
    isScanning,
    scanProgress,
    scanResult,
    selectedForDelete,
    hasResults,
    startScan,
    toggleFileSelection,
    hasSelectedInGroup,
    getSelectedCountInGroup,
    deleteSelectedInGroup,
    openFolder,
    getImageUrl,
    getRelativePath,
    formatFileSize
  }
}
