import { defineComponent, ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting, Refresh, RefreshLeft, Delete, Plus } from '@element-plus/icons-vue'
import { getTasks, retryTask, deleteTask, listTabs, sendTabsToDownloadQueue, getSettings, updateSettings } from '../service/BrowserAgentService'
import { getWebSocketService } from '../service/websocket'
import { BrowserTaskStatus, type BrowserTask, type ProgressEvent, type SiteRule } from '../service/Model'

export default defineComponent({
  name: 'BrowserAgentView',
  components: { Setting, Refresh, RefreshLeft, Delete, Plus },
  setup() {
    const tasks = ref<BrowserTask[]>([])
    const loading = ref(false)
    const sending = ref(false)
    const liveProgress = ref<Record<number, number>>({})
    const ws = getWebSocketService()

    // Global settings drawer (downloadDir, maxRetries, pollIntervalSec, siteRules)
    const settingsOpen = ref(false)
    const settingsCfg = reactive({
      downloadDir: '',
      maxRetries: 3,
      pollIntervalSec: 60,
      siteRules: [] as SiteRule[],
    })
    const settingsSaving = ref(false)

    function domainsText(rule: SiteRule): string { return rule.coverDomains.join(', ') }
    function setDomainsText(rule: SiteRule, text: string) {
      rule.coverDomains = text.split(',').map(s => s.trim()).filter(Boolean)
    }
    function addRule() {
      settingsCfg.siteRules.push({ coverDomains: [], overviewUriFormat: '', downloadUriFormat: '', downloadLinkRegex: '' } as SiteRule)
    }
    function removeRule(i: number) { settingsCfg.siteRules.splice(i, 1) }

    async function openSettings() {
      const s = await getSettings()
      settingsCfg.downloadDir = s.downloadDir || ''
      settingsCfg.maxRetries = s.maxRetries ?? 3
      settingsCfg.pollIntervalSec = s.pollIntervalSec ?? 60
      settingsCfg.siteRules = JSON.parse(JSON.stringify(s.siteRules || []))
      settingsOpen.value = true
    }
    async function saveSettings() {
      settingsSaving.value = true
      try {
        await updateSettings({
          downloadDir: settingsCfg.downloadDir,
          maxRetries: settingsCfg.maxRetries,
          pollIntervalSec: settingsCfg.pollIntervalSec,
          siteRules: JSON.parse(JSON.stringify(settingsCfg.siteRules)),
        })
        settingsOpen.value = false
        ElMessage.success('Settings saved')
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.error || e?.message || 'Failed to save')
      } finally {
        settingsSaving.value = false
      }
    }

    async function load() {
      loading.value = true
      try {
        tasks.value = await getTasks()
      } catch (e: any) {
        ElMessage.error(e.message || 'Failed to load tasks')
      } finally {
        loading.value = false
      }
    }

    async function onSendCurrentTabs() {
      if (sending.value) return
      sending.value = true
      try {
        const tabs = await listTabs()
        const urls = tabs
          .map(t => t.url)
          .filter(u => u && /^https?:/.test(u))
        if (urls.length === 0) {
          ElMessage.info('No http(s) tabs to send')
          return
        }
        const res = await sendTabsToDownloadQueue(urls)
        ElMessage.success(
          `Sent ${urls.length} tab(s): ${res.added} added, ${res.skipped} skipped, ${res.unmatched} unmatched`)
        await load()
      } catch (e: any) {
        const msg = e?.response?.data?.error || e.message || 'Failed to send tabs'
        ElMessage.error(msg)
      } finally {
        sending.value = false
      }
    }

    function handleProgress(e: ProgressEvent) {
      liveProgress.value = { ...liveProgress.value, [e.taskId]: e.progress }
      const t = tasks.value.find(x => x.id === e.taskId)
      if (t) {
        t.status = e.status
        if (typeof e.retryTimes === 'number') t.retry_times = e.retryTimes
      } else {
        // A brand-new task started downloading — refresh the list.
        load()
      }
    }

    async function onRetry(task: BrowserTask) {
      try {
        await retryTask(task.id)
        ElMessage.success(`Retrying: ${task.file_name}`)
        await load()
      } catch (e: any) {
        ElMessage.error(e.message || 'Retry failed')
      }
    }

    async function onDelete(task: BrowserTask) {
      try {
        await deleteTask(task.id)
        ElMessage.success('Task removed')
        await load()
      } catch (e: any) {
        ElMessage.error(e.message || 'Delete failed')
      }
    }

    function statusTag(status: string) {
      if (status === BrowserTaskStatus.Completed) return 'success'
      if (status === BrowserTaskStatus.InProgress) return 'warning'
      if (status === BrowserTaskStatus.Failed) return 'danger'
      return 'info'
    }

    onMounted(() => {
      load()
      ws.connect()
      ws.onProgress(handleProgress)
    })
    onUnmounted(() => ws.disconnect())

    return {
      tasks, loading, sending, liveProgress,
      load, onRetry, onDelete, statusTag,
      onSendCurrentTabs,
      settingsOpen, settingsCfg, settingsSaving,
      openSettings, saveSettings,
      domainsText, setDomainsText, addRule, removeRule,
      Setting,
      Refresh,
      RefreshLeft,
      Delete,
      Plus,
      BrowserTaskStatus,
    }
  },
})
