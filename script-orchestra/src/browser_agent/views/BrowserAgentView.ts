import { defineComponent, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Setting, Refresh, RefreshLeft, Delete } from '@element-plus/icons-vue'
import { getTasks, retryTask, deleteTask } from '../service/BrowserAgentService'
import { getWebSocketService } from '../service/websocket'
import { BrowserTaskStatus, type BrowserTask, type ProgressEvent } from '../service/Model'

export default defineComponent({
  name: 'BrowserAgentView',
  components: { Setting, Refresh, RefreshLeft, Delete },
  setup() {
    const router = useRouter()
    const tasks = ref<BrowserTask[]>([])
    const loading = ref(false)
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
      tasks, loading, liveProgress,
      load, onRetry, onDelete, statusTag,
      goToSettings: () => router.push('/browser-agent/settings'),
      BrowserTaskStatus,
    }
  },
})
