/**
 * File-Git Repository Detail View Logic
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { FileGitService, type Repository, type RepoStatus } from '../service/FileGitService'
import io from 'socket.io-client'

export function useFileGitRepoDetail() {
  const route = useRoute()
  const router = useRouter()
  const repoId = ref<string>(route.params.id as string)

  const repo = ref<Repository | null>(null)
  const status = ref<RepoStatus | null>(null)
  const activeTab = ref('changes')
  const isLoading = ref(false)
  const isLoadingStatus = ref(false)
  const isPushing = ref(false)
  const isPulling = ref(false)

  // File queue for progress tracking
  interface QueueFile {
    path: string
    name: string
    action: string // 'Uploading (new)', 'Uploading (modified)', 'Deleting'
    status: 'pending' | 'uploading' | 'success' | 'error'
    error?: string
  }

  const fileQueue = ref<QueueFile[]>([])
  const isOperating = computed(() => isPushing.value || isPulling.value)

  // Show all files including completed ones (they fade out after delay)
  const visibleFiles = computed(() => {
    return fileQueue.value
  })

  // WebSocket connection
  let socket: any = null

  const hasChanges = computed(() => {
    if (!status.value) return false
    return (
      status.value.added.length > 0 ||
      status.value.modified.length > 0 ||
      status.value.deleted.length > 0
    )
  })

  /**
   * Load repository details
   */
  async function loadRepo() {
    console.log('[FileGit] Loading repo:', repoId.value)
    isLoading.value = true
    try {
      const response = await FileGitService.getRepo(repoId.value)
      console.log('[FileGit] Repo loaded:', response)
      if (response.success && response.repo) {
        repo.value = response.repo
      } else {
        ElMessage.error(response.error || 'Failed to load repository')
      }
    } catch (error: any) {
      console.error('[FileGit] Load repo failed:', error)
      ElMessage.error(error.response?.data?.error || 'Failed to load repository')
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Load repository file status
   */
  async function loadStatus() {
    console.log('[FileGit] Loading repo status:', repoId.value)
    isLoadingStatus.value = true
    try {
      const response = await FileGitService.getRepoStatus(repoId.value)
      console.log('[FileGit] Status loaded:', response)
      if (response.success && response.status) {
        status.value = response.status
        ElMessage.success('Status loaded successfully')
      } else {
        ElMessage.error(response.error || 'Failed to load status')
      }
    } catch (error: any) {
      console.error('[FileGit] Load status failed:', error)
      ElMessage.error(error.response?.data?.error || 'Failed to load status')
    } finally {
      isLoadingStatus.value = false
    }
  }

  /**
   * Refresh status manually
   */
  async function refreshStatus() {
    await loadStatus()
  }

  /**
   * Go back to repositories list
   */
  function goBack() {
    router.push('/file-git')
  }

  /**
   * Open repository folder in system file manager
   */
  async function openFolder() {
    console.log('[FileGit] Opening folder for repo:', repoId.value)
    try {
      const response = await FileGitService.openFolder(repoId.value)
      if (response.success) {
        ElMessage.success('Folder opened successfully')
      } else {
        ElMessage.error(response.error || 'Failed to open folder')
      }
    } catch (error: any) {
      console.error('[FileGit] Open folder failed:', error)
      ElMessage.error(error.response?.data?.error || 'Failed to open folder')
    }
  }

  /**
   * Initialize WebSocket connection
   */
  function initWebSocket() {
    try {
      // Connect to backend WebSocket
      socket = io('http://localhost:5001', {
        transports: ['websocket', 'polling']
      })

      socket.on('connect', () => {
        console.log('[FileGit] WebSocket connected')
      })

      socket.on('disconnect', () => {
        console.log('[FileGit] WebSocket disconnected')
      })

      // Listen to progress updates for this repo
      socket.on(`repo:${repoId.value}:progress`, (data: any) => {
        console.log('[FileGit] Progress update:', data)

        // Use phase to determine what's happening
        if (data.phase === 'uploading' || data.phase === 'deleting' || data.phase === 'downloading') {
          // Extract filename and action from message
          // Push: "Uploading (new): path" or "Uploading (modified): path" or "Deleting: path"
          // Pull: "Downloading (new): path" or "Downloading (modified): path" or "Local deleting: path"
          let filePath = null
          let action = null

          const uploadMatch = data.message.match(/Uploading \((.+?)\): (.+)$/)
          const downloadMatch = data.message.match(/Downloading \((.+?)\): (.+)$/)
          const remoteDeleteMatch = data.message.match(/Deleting: (.+)$/)
          const localDeleteMatch = data.message.match(/Local deleting: (.+)$/)

          if (uploadMatch) {
            action = `Uploading (${uploadMatch[1]})`
            filePath = uploadMatch[2]
          } else if (downloadMatch) {
            action = `Downloading (${downloadMatch[1]})`
            filePath = downloadMatch[2]
          } else if (remoteDeleteMatch) {
            action = 'Remote deleting'
            filePath = remoteDeleteMatch[1]
          } else if (localDeleteMatch) {
            action = 'Local deleting'
            filePath = localDeleteMatch[1]
          }

          if (filePath) {
            // For pull operations, dynamically add files to queue
            let file = fileQueue.value.find(f => f.path === filePath)
            if (!file) {
              file = {
                path: filePath,
                name: filePath.split('/').pop() || filePath,
                action: action || 'Processing',
                status: 'pending'
              }
              fileQueue.value.push(file)
            }

            // Update status to uploading
            if (file.status === 'pending') {
              file.status = 'uploading'
            }
          }
        }
      })

      // Listen to log messages
      socket.on(`repo:${repoId.value}:log`, (data: any) => {
        console.log('[FileGit] Log:', data)

        // Parse log message to update file status
        const message = data.message

        // Success: "✓ Uploaded: path" or "✓ Deleted: path"
        if (message.startsWith('✓')) {
          const match = message.match(/: (.+)$/)
          if (match) {
            const filePath = match[1]
            const file = fileQueue.value.find(f => f.path === filePath)
            if (file) {
              file.status = 'success'

              // Immediately remove from status lists
              if (status.value) {
                // Remove from added
                const addedIndex = status.value.added.findIndex(f => f.middle_path === filePath)
                if (addedIndex !== -1) {
                  status.value.added.splice(addedIndex, 1)
                }

                // Remove from modified
                const modifiedIndex = status.value.modified.findIndex(f => f.middle_path === filePath)
                if (modifiedIndex !== -1) {
                  status.value.modified.splice(modifiedIndex, 1)
                }

                // Remove from deleted
                const deletedIndex = status.value.deleted.findIndex(f => f.middle_path === filePath)
                if (deletedIndex !== -1) {
                  status.value.deleted.splice(deletedIndex, 1)
                }

                // Update total count
                status.value.total_files = status.value.added.length + status.value.modified.length + status.value.deleted.length
              }

              // Remove from fileQueue after a short delay for visual feedback
              setTimeout(() => {
                const index = fileQueue.value.findIndex(f => f.path === filePath)
                if (index !== -1 && fileQueue.value[index].status === 'success') {
                  fileQueue.value.splice(index, 1)
                }
              }, 1000)
            }
          }
        }
        // Error: "✗ Failed: path - error"
        else if (message.startsWith('✗')) {
          const match = message.match(/: (.+?) - (.+)$/)
          if (match) {
            const filePath = match[1]
            const errorMsg = match[2]
            const file = fileQueue.value.find(f => f.path === filePath)
            if (file) {
              file.status = 'error'
              file.error = errorMsg
            }
          }
        }
        // No need for Starting upload/delete parsing - handled by progress event
      })

      // Listen to status updates
      socket.on(`repo:${repoId.value}:status`, (data: any) => {
        console.log('[FileGit] Status update:', data)
        if (repo.value) {
          repo.value.status = data.status
        }
      })
    } catch (error) {
      console.error('[FileGit] WebSocket init failed:', error)
    }
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
   * Initialize file queue from changes
   */
  function initFileQueue(changes: RepoStatus) {
    fileQueue.value = []

    // Add files to upload
    for (const file of changes.added) {
      fileQueue.value.push({
        path: file.middle_path,
        name: file.middle_path.split('/').pop() || file.middle_path,
        action: 'Uploading (new)',
        status: 'pending'
      })
    }

    for (const file of changes.modified) {
      fileQueue.value.push({
        path: file.middle_path,
        name: file.middle_path.split('/').pop() || file.middle_path,
        action: 'Uploading (modified)',
        status: 'pending'
      })
    }

    // Add files to delete
    for (const file of changes.deleted) {
      fileQueue.value.push({
        path: file.middle_path,
        name: file.middle_path.split('/').pop() || file.middle_path,
        action: 'Remote deleting',
        status: 'pending'
      })
    }
  }
  /**
   * Get file sync status from queue by path
   */
  function getFileStatus(middlePath: string) {
    const file = fileQueue.value.find(f => f.path === middlePath)
    return file ? file.status : null
  }

  /**
   * Get file action from queue by path
   */
  function getFileAction(middlePath: string) {
    const file = fileQueue.value.find(f => f.path === middlePath)
    return file ? file.action : null
  }

  /**
   * Extract operation type from action string
   * Returns: 'uploading', 'downloading', 'local-deleting', 'remote-deleting', or 'unknown'
   */
  function getActionType(action: string): string {
    if (!action) return 'unknown'
    if (action.startsWith('Uploading')) return 'uploading'
    if (action.startsWith('Downloading')) return 'downloading'
    if (action.startsWith('Local deleting')) return 'local-deleting'
    if (action.startsWith('Remote deleting')) return 'remote-deleting'
    return 'unknown'
  }

  function formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  /**
   * Push changes to cloud
   */
  async function pushChanges() {
    console.log('[FileGit] Pushing changes for repo:', repoId.value)

    if (!status.value) return

    // Initialize file queue from current changes
    initFileQueue(status.value)

    isPushing.value = true
    try {
      const response = await FileGitService.pushRepo(repoId.value)
      console.log('[FileGit] Push response:', response)

      if (response.success) {
        ElMessage.success(response.message || 'Changes pushed successfully')
        // Clear queue after success
        fileQueue.value = []
        // Reload status and repo after push
        await loadStatus()
        await loadRepo()
      } else {
        ElMessage.error(response.error || 'Failed to push changes')
      }
    } catch (error: any) {
      console.error('[FileGit] Push failed:', error)
      ElMessage.error(error.response?.data?.error || 'Failed to push changes')
    } finally {
      isPushing.value = false
    }
  }

  /**
   * Pull changes from cloud
   */
  async function pullChanges() {
    console.log('[FileGit] Pulling changes for repo:', repoId.value)

    // Clear file queue - files will be added dynamically via WebSocket
    fileQueue.value = []

    isPulling.value = true
    try {
      const response = await FileGitService.pullRepo(repoId.value)
      console.log('[FileGit] Pull response:', response)

      if (response.success) {
        ElMessage.success(response.message || 'Changes pulled successfully')
        // Clear queue after success
        fileQueue.value = []
        // Reload status and repo after pull
        await loadStatus()
        await loadRepo()
      } else {
        ElMessage.error(response.error || 'Failed to pull changes')
      }
    } catch (error: any) {
      console.error('[FileGit] Pull failed:', error)
      ElMessage.error(error.response?.data?.error || 'Failed to pull changes')
    } finally {
      isPulling.value = false
    }
  }

  onMounted(async () => {
    await loadRepo()
    // Automatically load status when page opens
    await loadStatus()
    // Initialize WebSocket for real-time updates
    initWebSocket()
  })

  onBeforeUnmount(() => {
    disconnectWebSocket()
  })

  return {
    repo,
    status,
    activeTab,
    isLoading,
    isLoadingStatus,
    isPushing,
    isPulling,
    hasChanges,
    fileQueue,
    visibleFiles,
    isOperating,
    getFileStatus,
    getFileAction,
    getActionType,
    goBack,
    openFolder,
    refreshStatus,
    formatFileSize,
    pushChanges,
    pullChanges
  }
}
