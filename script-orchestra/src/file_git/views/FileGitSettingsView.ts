/**
 * File-Git global settings — Baidu Cloud credentials + OAuth connect flow.
 * Repo-level credentials (mode, password, remote_path) live in the repo
 * detail page instead.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { FileGitService, type GlobalSettings } from '../service/FileGitService'

export function useFileGitSettingsView() {
  const router = useRouter()
  const settings = ref<GlobalSettings>({
    baidu_cloud: {
      app_id: '', secret_key: '', app_key: '',
      sign_code: '', expires_in: '',
      refresh_token: '', access_token: '', root_prefix: '',
    },
    use_mock_baidu: true,
  })
  const isLoading = ref(false)
  const isSaving = ref(false)

  // Baidu connection status.
  const baiduConnected = ref(false)
  const baiduName = ref('')
  const baiduExpiresAt = ref(0)

  // Token expiry rendered as Beijing time (UTC+8), e.g. "2026-09-23 14:18:50 (北京时间)".
  const baiduExpiresBeijing = computed(() => {
    if (!baiduExpiresAt.value) return ''
    const d = new Date(baiduExpiresAt.value * 1000)
    const bj = new Date(d.getTime() + 8 * 3600 * 1000)
    const p = (n: number) => String(n).padStart(2, '0')
    return `${bj.getUTCFullYear()}-${p(bj.getUTCMonth() + 1)}-${p(bj.getUTCDate())} `
      + `${p(bj.getUTCHours())}:${p(bj.getUTCMinutes())}:${p(bj.getUTCSeconds())} (北京时间)`
  })

  // In-page OAuth dialog: the Baidu authorize page loads in an iframe; the
  // callback page posts a message back so we can close + refresh automatically.
  const authDialogVisible = ref(false)
  const authUrl = ref('')

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
      await refreshBaiduStatus()
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to load settings')
    } finally {
      isLoading.value = false
    }
  }

  async function refreshBaiduStatus() {
    try {
      const s = await FileGitService.getBaiduStatus()
      baiduConnected.value = !!s.connected
      baiduName.value = s.baidu_name || ''
      baiduExpiresAt.value = s.expires_at || 0
    } catch {
      baiduConnected.value = false
    }
  }

  async function save() {
    isSaving.value = true
    try {
      const res = await FileGitService.updateSettings({
        baidu_cloud: settings.value.baidu_cloud,
        use_mock_baidu: settings.value.use_mock_baidu,
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

  async function connectBaidu() {
    try {
      // Save first so app_key/secret_key are persisted before the OAuth call.
      await FileGitService.updateSettings({
        baidu_cloud: settings.value.baidu_cloud,
        use_mock_baidu: settings.value.use_mock_baidu,
      })
      const res = await FileGitService.getBaiduAuthUrl()
      if (!res.success || !res.url) {
        ElMessage.error(res.error || 'Failed to build auth URL')
        return
      }
      // Open the authorize page inside an in-page dialog (iframe). The
      // callback page posts a message back (handleAuthMessage) to close it.
      authUrl.value = res.url
      authDialogVisible.value = true
    } catch (e: any) {
      ElMessage.error(e.response?.data?.error || e.message || 'Failed to start OAuth')
    }
  }

  async function handleAuthMessage(ev: MessageEvent) {
    const data = ev.data
    if (!data || data.type !== 'baidu-oauth') return
    authDialogVisible.value = false
    authUrl.value = ''
    if (data.status === 'ok') {
      ElMessage.success('Baidu connected')
      await load()
    } else {
      ElMessage.error('Baidu connection failed')
    }
  }

  function closeAuthDialog() {
    authDialogVisible.value = false
    authUrl.value = ''
    // The user may have finished authorizing without us catching the message
    // (cross-origin quirks) — refresh status to be safe.
    refreshBaiduStatus()
  }

  function goBack() {
    router.push('/file-git')
  }

  onMounted(() => {
    window.addEventListener('message', handleAuthMessage)
    load()
  })
  onUnmounted(() => window.removeEventListener('message', handleAuthMessage))

  return {
    settings, isLoading, isSaving,
    baiduConnected, baiduName, baiduExpiresAt, baiduExpiresBeijing,
    authDialogVisible, authUrl,
    load, save, connectBaidu, refreshBaiduStatus, closeAuthDialog, goBack,
  }
}
