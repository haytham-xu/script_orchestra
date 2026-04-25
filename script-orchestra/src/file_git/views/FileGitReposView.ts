/**
 * File-Git Repository List View Logic
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FileGitService, type Repository } from '../service/FileGitService'

export function useFileGitReposView() {
  const router = useRouter()
  const repos = ref<Repository[]>([])
  const isLoading = ref(false)
  const showAddDialog = ref(false)
  const showImportDialog = ref(false)
  const showDeleteDialog = ref(false)

  // Add dialog fields
  const newRepoPath = ref('')
  const newRepoMode = ref<'ORIGINAL' | 'ENCRYPTED'>('ENCRYPTED')

  // Import dialog fields
  const importRepoPath = ref('')

  // Delete dialog fields
  const deleteRepoId = ref('')
  const deleteRepoName = ref('')
  const deleteConfirmInput = ref('')

  /**
   * Load all repositories
   */
  async function loadRepos() {
    console.log('[FileGit] Loading repositories...')
    isLoading.value = true
    try {
      const response = await FileGitService.listRepos()
      console.log('[FileGit] Repos loaded:', response)
      if (response.success) {
        repos.value = response.repos
      } else {
        ElMessage.error(response.error || 'Failed to load repositories')
      }
    } catch (error: any) {
      console.error('[FileGit] Load repos failed:', error)
      ElMessage.error(error.response?.data?.error || 'Failed to load repositories')
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Open add repository dialog
   */
  function openAddDialog() {
    newRepoPath.value = ''
    newRepoMode.value = 'ENCRYPTED'
    showAddDialog.value = true
  }

  /**
   * Add new repository
   */
  async function addRepo() {
    const path = newRepoPath.value.trim()

    if (!path) {
      ElMessage.warning('Please enter a folder path')
      return
    }

    console.log('[FileGit] Adding repo:', path, newRepoMode.value)

    try {
      const response = await FileGitService.addRepo(path, newRepoMode.value, false)
      console.log('[FileGit] Add repo response:', response)

      if (response.success) {
        ElMessage.success(response.message || 'Repository added successfully')
        showAddDialog.value = false
        await loadRepos()
      } else {
        ElMessage.error(response.error || 'Failed to add repository')
      }
    } catch (error: any) {
      console.error('[FileGit] Add repo failed:', error)
      ElMessage.error(error.response?.data?.error || 'Failed to add repository')
    }
  }

  /**
   * Open import existing repository dialog
   */
  function openImportDialog() {
    importRepoPath.value = ''
    showImportDialog.value = true
  }

  /**
   * Import existing repository
   */
  async function importRepo() {
    const path = importRepoPath.value.trim()

    if (!path) {
      ElMessage.warning('Please enter a folder path')
      return
    }

    console.log('[FileGit] Importing existing repo:', path)

    try {
      const response = await FileGitService.addRepo(path, 'ENCRYPTED', true)
      console.log('[FileGit] Import repo response:', response)

      if (response.success) {
        ElMessage.success(response.message || 'Repository imported successfully')
        showImportDialog.value = false
        await loadRepos()
      } else {
        ElMessage.error(response.error || 'Failed to import repository')
      }
    } catch (error: any) {
      console.error('[FileGit] Import repo failed:', error)
      ElMessage.error(error.response?.data?.error || 'Failed to import repository')
    }
  }

  /**
   * Open delete confirmation dialog
   */
  function openDeleteDialog(repo: Repository) {
    deleteRepoId.value = repo.id
    deleteRepoName.value = repo.name
    deleteConfirmInput.value = ''
    showDeleteDialog.value = true
  }

  /**
   * Delete repository
   */
  async function deleteRepo() {
    if (deleteConfirmInput.value !== deleteRepoName.value) {
      ElMessage.warning('Repository name does not match')
      return
    }

    console.log('[FileGit] Deleting repo:', deleteRepoId.value)

    try {
      const response = await FileGitService.deleteRepo(deleteRepoId.value)
      console.log('[FileGit] Delete repo response:', response)

      if (response.success) {
        ElMessage.success(response.message || 'Repository deleted successfully')
        showDeleteDialog.value = false
        await loadRepos()
      } else {
        ElMessage.error(response.error || 'Failed to delete repository')
      }
    } catch (error: any) {
      console.error('[FileGit] Delete repo failed:', error)
      ElMessage.error(error.response?.data?.error || 'Failed to delete repository')
    }
  }

  /**
   * Navigate to repository detail page
   */
  function goToRepo(repoId: string) {
    console.log('[FileGit] Navigate to repo:', repoId)
    router.push(`/file-git/${repoId}`)
  }

  /**
   * Open repository folder in system file manager
   */
  async function openFolder(repoId: string) {
    console.log('[FileGit] Opening folder for repo:', repoId)
    try {
      const response = await FileGitService.openFolder(repoId)
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
   * Navigate to settings page
   */
  function goToSettings() {
    router.push('/file-git/settings')
  }

  onMounted(() => {
    loadRepos()
  })

  return {
    repos,
    isLoading,
    showAddDialog,
    showImportDialog,
    showDeleteDialog,
    newRepoPath,
    newRepoMode,
    importRepoPath,
    deleteRepoName,
    deleteConfirmInput,
    loadRepos,
    openAddDialog,
    openImportDialog,
    addRepo,
    importRepo,
    openDeleteDialog,
    deleteRepo,
    goToRepo,
    openFolder,
    goToSettings
  }
}
