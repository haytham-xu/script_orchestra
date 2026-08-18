/**
 * File-Git Repos List — UI logic.
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FileGitService, type RepoMode, type Repository } from '../service/FileGitService'

export function useFileGitReposView() {
  const router = useRouter()

  const repos = ref<Repository[]>([])
  const isLoading = ref(false)

  const showAddDialog = ref(false)
  const newRepoPath = ref('')
  const newRepoMode = ref<RepoMode>('ENCRYPTED')

  const showImportDialog = ref(false)
  const importRepoPath = ref('')

  const showDeleteDialog = ref(false)
  const deleteRepoId = ref('')
  const deleteRepoName = ref('')
  const deleteConfirmInput = ref('')

  const hasRepos = computed(() => repos.value.length > 0)

  // -------------------------------------------------------------------

  async function loadRepos() {
    isLoading.value = true
    try {
      const res = await FileGitService.listRepos()
      if (res.success) {
        repos.value = res.repos
      } else {
        ElMessage.error(res.error || 'Failed to load repositories')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to load repositories')
    } finally {
      isLoading.value = false
    }
  }

  function openAddDialog() {
    newRepoPath.value = ''
    newRepoMode.value = 'ENCRYPTED'
    showAddDialog.value = true
  }

  async function addRepo() {
    const path = newRepoPath.value.trim()
    if (!path) return ElMessage.warning('Please enter a folder path')
    try {
      const res = await FileGitService.addRepo(path, newRepoMode.value, false)
      if (res.success) {
        ElMessage.success(res.message || 'Repository added')
        showAddDialog.value = false
        await loadRepos()
      } else {
        ElMessage.error(res.error || 'Failed to add repository')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to add repository')
    }
  }

  function openImportDialog() {
    importRepoPath.value = ''
    showImportDialog.value = true
  }

  async function importRepo() {
    const path = importRepoPath.value.trim()
    if (!path) return ElMessage.warning('Please enter a folder path')
    try {
      // Import: skip_init=true, mode is read back from the existing .fgit/config.json
      const res = await FileGitService.addRepo(path, 'ENCRYPTED', true)
      if (res.success) {
        ElMessage.success(res.message || 'Repository imported')
        showImportDialog.value = false
        await loadRepos()
      } else {
        ElMessage.error(res.error || 'Failed to import repository')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to import repository')
    }
  }

  function openDeleteDialog(repo: Repository) {
    deleteRepoId.value = repo.id
    deleteRepoName.value = repo.name
    deleteConfirmInput.value = ''
    showDeleteDialog.value = true
  }

  async function confirmDelete() {
    if (deleteConfirmInput.value !== deleteRepoName.value) {
      ElMessage.warning('Repository name does not match')
      return
    }
    try {
      const res = await FileGitService.deleteRepo(deleteRepoId.value)
      if (res.success) {
        ElMessage.success(res.message || 'Repository deleted')
        showDeleteDialog.value = false
        await loadRepos()
      } else {
        ElMessage.error(res.error || 'Failed to delete repository')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to delete repository')
    }
  }

  async function openFolder(repoId: string) {
    try {
      const res = await FileGitService.openFolder(repoId)
      if (!res.success) ElMessage.error(res.error || 'Failed to open folder')
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to open folder')
    }
  }

  function goToRepo(repoId: string) {
    router.push(`/file-git/${repoId}`)
  }

  function goToSettings() {
    router.push('/file-git/settings')
  }

  onMounted(loadRepos)

  return {
    repos,
    hasRepos,
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
    addRepo,
    openImportDialog,
    importRepo,
    openDeleteDialog,
    confirmDelete,
    openFolder,
    goToRepo,
    goToSettings,
  }
}
