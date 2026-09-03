import { defineComponent, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Setting, Refresh, RefreshLeft, Delete } from '@element-plus/icons-vue'
import { getTasks, retryTask, deleteTask, listTabs, sendTabsToDownloadQueue } from '../service/BrowserAgentService'
import { getWebSocketService } from '../service/websocket'
import { BrowserTaskStatus, type BrowserTask, type ProgressEvent } from '../service/Model'

export default defineComponent({
  name: 'BrowserAgentView',
  components: { Setting, Refresh, RefreshLeft, Delete },
  setup() {
    const router = useRouter()
    const tasks = ref<BrowserTask[]>([])
    const loading = ref(false)
    const sending = ref(false)
    // Live progress per task id, overlaid on the table.
    const liveProgress = ref<Record<number, number>>({})
    const ws = getWebSocketService()

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
      goToSettings: () => router.push('/browser-agent/settings'),
      Setting,
      Refresh,
      RefreshLeft,
      Delete,
      BrowserTaskStatus,
    }
  },
})
