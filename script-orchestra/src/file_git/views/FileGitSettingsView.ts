/**
 * File-Git Settings View Logic
 */
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { FileGitService, type Settings } from '../service/FileGitService'

export function useFileGitSettings() {
  const isLoading = ref(false)
  const isSaving = ref(false)

  const settingsForm = reactive<Settings>({
    baidu_cloud: {
      app_id: '',
      secret_key: '',
      app_key: '',
      sign_code: '',
      expires_in: '',
      refresh_token: '',
      access_token: ''
    },
    use_mock_baidu: true,
    default_password: ''
  })

  /**
   * Load settings from backend
   */
  async function loadSettings() {
    console.log('[FileGit] Loading settings...')
    isLoading.value = true
    try {
      const response = await FileGitService.getSettings()
      console.log('[FileGit] Settings loaded:', response)

      if (response.success && response.settings) {
        // Update form with loaded settings
        Object.assign(settingsForm, response.settings)
        ElMessage.success('Settings loaded successfully')
      } else {
        ElMessage.error(response.error || 'Failed to load settings')
      }
    } catch (error: any) {
      console.error('[FileGit] Load settings failed:', error)
      ElMessage.error(error.response?.data?.error || 'Failed to load settings')
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Save settings to backend
   */
  async function saveSettings() {
    console.log('[FileGit] Saving settings...', settingsForm)
    isSaving.value = true
    try {
      const response = await FileGitService.updateSettings(settingsForm)
      console.log('[FileGit] Settings saved:', response)

      if (response.success) {
        ElMessage.success(response.message || 'Settings saved successfully')
        // Reload to get updated settings
        await loadSettings()
      } else {
        ElMessage.error(response.error || 'Failed to save settings')
      }
    } catch (error: any) {
      console.error('[FileGit] Save settings failed:', error)
      ElMessage.error(error.response?.data?.error || 'Failed to save settings')
    } finally {
      isSaving.value = false
    }
  }

  onMounted(() => {
    loadSettings()
  })

  return {
    settingsForm,
    isLoading,
    isSaving,
    loadSettings,
    saveSettings
  }
}
