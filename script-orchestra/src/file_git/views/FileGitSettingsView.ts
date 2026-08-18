/**
 * File-Git global settings — currently a placeholder for future
 * Baidu Cloud credentials. Repo-level credentials (mode, password,
 * remote_path) live in the repo detail page instead.
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { FileGitService, type GlobalSettings } from '../service/FileGitService'

export function useFileGitSettingsView() {
  const router = useRouter()
  const settings = ref<GlobalSettings>({
    baidu_cloud: {
      app_id: '', secret_key: '', app_key: '',
      sign_code: '', expires_in: '',
      refresh_token: '', access_token: '',
    },
  })
  const isLoading = ref(false)
  const isSaving = ref(false)

  async function load() {
    isLoading.value = true
    try {
      const res = await FileGitService.getSettings()
      if (res.success && res.settings) {
        settings.value = {
          ...settings.value,
          ...res.settings,
          baidu_cloud: {
            ...(settings.value.baidu_cloud || {}),
            ...(res.settings.baidu_cloud || {}),
          },
        }
      } else if (res.error) {
        ElMessage.error(res.error)
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to load settings')
    } finally {
      isLoading.value = false
    }
  }

  async function save() {
    isSaving.value = true
    try {
      const res = await FileGitService.updateSettings({
        baidu_cloud: settings.value.baidu_cloud,
      })
      if (res.success) {
        ElMessage.success(res.message || 'Settings saved')
        await load()
      } else {
        ElMessage.error(res.error || 'Failed to save settings')
      }
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to save settings')
    } finally {
      isSaving.value = false
    }
  }

  function goBack() {
    router.push('/file-git')
  }

  onMounted(load)

  return { settings, isLoading, isSaving, load, save, goBack }
}
