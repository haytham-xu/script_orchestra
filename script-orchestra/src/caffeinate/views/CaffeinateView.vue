<template>
  <div class="caffeinate-view">
    <div class="header">
      <div class="header-left">
        <el-button @click="goBack" circle>
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1>Caffeinate</h1>
        <el-tag v-if="isConnected" type="success" size="small">
          <el-icon><Connection /></el-icon>
          Live
        </el-tag>
        <el-tag v-else type="danger" size="small">
          <el-icon><CircleClose /></el-icon>
          Offline
        </el-tag>
      </div>
      <div class="header-right">
        <el-button @click="refreshAll" :loading="isLoading">
          <el-icon><Refresh /></el-icon>
          Refresh
        </el-button>
      </div>
    </div>

    <el-card class="control-section">
      <template #header>
        <div class="card-header">
          <span>Control</span>
          <el-tag
            :type="status.running ? 'success' : 'info'"
            size="default"
          >
            {{ status.running ? 'Running' : 'Stopped' }}
          </el-tag>
        </div>
      </template>

      <div class="control-grid">
        <div class="control-item">
          <label>Heartbeat interval (seconds)</label>
          <el-input-number
            v-model="intervalSeconds"
            :min="5"
            :max="3600"
            :step="30"
            :disabled="status.running"
          />
        </div>
        <div class="control-item">
          <label>Started at</label>
          <span class="value">{{ status.started_at || '-' }}</span>
        </div>
        <div class="control-item">
          <label>Process pid</label>
          <span class="value">{{ status.pid ?? '-' }}</span>
        </div>
        <div class="control-item">
          <label>Current interval</label>
          <span class="value">{{ status.interval_seconds }}s</span>
        </div>
      </div>

      <div class="control-actions">
        <el-button
          v-if="!status.running"
          type="primary"
          size="large"
          @click="handleStart"
          :loading="isStarting"
        >
          <el-icon><VideoPlay /></el-icon>
          Start
        </el-button>
        <el-button
          v-else
          type="danger"
          size="large"
          @click="handleStop"
          :loading="isStopping"
        >
          <el-icon><VideoPause /></el-icon>
          Stop
        </el-button>
      </div>
    </el-card>

    <el-card class="logs-section">
      <template #header>
        <div class="card-header">
          <span>Logs ({{ logs.length }})</span>
          <el-button size="small" @click="handleClearLogs" plain>
            <el-icon><Delete /></el-icon>
            Clear
          </el-button>
        </div>
      </template>

      <div v-if="logs.length === 0" class="empty-logs">
        <el-empty description="No logs yet — start caffeinate to see heartbeat lines" />
      </div>

      <div v-else class="log-list" ref="logListRef">
        <div v-for="entry in logs" :key="entry.id" class="log-line">
          <span class="log-timestamp">{{ formatTimestamp(entry.timestamp) }}</span>
          <span class="log-message">{{ entry.message }}</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  Refresh,
  Delete,
  VideoPlay,
  VideoPause,
  Connection,
  CircleClose,
} from '@element-plus/icons-vue'
import {
  getStatus,
  startCaffeinate,
  stopCaffeinate,
  getLogs,
  clearLogs,
  type CaffeinateStatus,
  type CaffeinateLogEntry,
} from '../service/api'
import { getWebSocketService } from '../service/websocket'

const router = useRouter()
const wsService = getWebSocketService()

const intervalSeconds = ref(300)
const status = ref<CaffeinateStatus>({
  running: false,
  interval_seconds: 300,
  started_at: null,
  pid: null,
  log_count: 0,
})
const logs = ref<CaffeinateLogEntry[]>([])
const isLoading = ref(false)
const isStarting = ref(false)
const isStopping = ref(false)
const isConnected = ref(false)
const logListRef = ref<HTMLElement | null>(null)

function goBack() {
  router.push('/')
}

function formatTimestamp(ts: string) {
  try {
    return new Date(ts).toLocaleTimeString()
  } catch {
    return ts
  }
}

async function scrollLogsToBottom() {
  await nextTick()
  if (logListRef.value) {
    logListRef.value.scrollTop = logListRef.value.scrollHeight
  }
}

async function refreshStatus() {
  try {
    status.value = await getStatus()
    if (!status.value.running) {
      intervalSeconds.value = status.value.interval_seconds || intervalSeconds.value
    } else {
      intervalSeconds.value = status.value.interval_seconds
    }
  } catch (error: any) {
    console.error('Failed to fetch status:', error)
    ElMessage.error(error.message || 'Failed to fetch status')
  }
}

async function refreshLogs() {
  try {
    logs.value = await getLogs(500)
    scrollLogsToBottom()
  } catch (error: any) {
    console.error('Failed to fetch logs:', error)
    ElMessage.error(error.message || 'Failed to fetch logs')
  }
}

async function refreshAll() {
  isLoading.value = true
  try {
    await Promise.all([refreshStatus(), refreshLogs()])
  } finally {
    isLoading.value = false
  }
}

async function handleStart() {
  isStarting.value = true
  try {
    status.value = await startCaffeinate(intervalSeconds.value)
    ElMessage.success('Caffeinate started')
  } catch (error: any) {
    ElMessage.error(error.message || 'Failed to start caffeinate')
  } finally {
    isStarting.value = false
  }
}

async function handleStop() {
  isStopping.value = true
  try {
    status.value = await stopCaffeinate()
    ElMessage.success('Caffeinate stopped')
  } catch (error: any) {
    ElMessage.error(error.message || 'Failed to stop caffeinate')
  } finally {
    isStopping.value = false
  }
}

async function handleClearLogs() {
  try {
    await clearLogs()
    logs.value = []
    ElMessage.success('Logs cleared')
  } catch (error: any) {
    ElMessage.error(error.message || 'Failed to clear logs')
  }
}

function handleWsLog(entry: CaffeinateLogEntry) {
  const exists = logs.value.some((e) => e.id === entry.id)
  if (!exists) {
    logs.value.push(entry)
    scrollLogsToBottom()
  }
}

let connectionInterval: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  wsService.connect()
  wsService.onLog(handleWsLog)

  connectionInterval = setInterval(() => {
    isConnected.value = wsService.isConnected()
  }, 3000)

  await refreshAll()

  setTimeout(() => {
    isConnected.value = wsService.isConnected()
  }, 1000)
})

onUnmounted(() => {
  wsService.offLog()
  wsService.disconnect()
  if (connectionInterval) {
    clearInterval(connectionInterval)
  }
})
</script>

<style scoped>
.caffeinate-view {
  padding: 20px;
  max-width: 1000px;
  margin: 0 auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-left h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.header-right {
  display: flex;
  gap: 12px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.control-section {
  margin-bottom: 20px;
}

.control-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.control-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.control-item label {
  font-size: 12px;
  color: #909399;
}

.control-item .value {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  color: #303133;
}

.control-actions {
  display: flex;
  justify-content: flex-end;
}

.logs-section {
  margin-bottom: 20px;
}

.empty-logs {
  padding: 20px 0;
}

.log-list {
  max-height: 480px;
  overflow-y: auto;
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  line-height: 1.6;
}

.log-line {
  display: flex;
  gap: 12px;
  padding: 2px 0;
}

.log-timestamp {
  color: #6a9955;
  flex-shrink: 0;
}

.log-message {
  color: #d4d4d4;
  word-break: break-all;
}
</style>
