<template>
  <div class="clipboard-share-view">
    <div class="header">
      <div class="header-left">
        <el-button @click="goBack" circle>
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1>Clipboard Share</h1>
        <el-tag v-if="wsConnected" type="success" size="small">
          <el-icon><Connection /></el-icon> Live
        </el-tag>
        <el-tag v-else type="danger" size="small">
          <el-icon><CircleClose /></el-icon> Offline
        </el-tag>
      </div>
      <div class="header-right">
        <el-button @click="refreshHistory" :loading="isLoading">
          <el-icon><Refresh /></el-icon> Refresh
        </el-button>
        <el-button @click="showClearConfirm" type="danger" plain>
          <el-icon><Delete /></el-icon> Clear All
        </el-button>
      </div>
    </div>

    <!-- Input -->
    <el-card class="input-section">
      <template #header>
        <div class="card-header">
          <span>Add Content</span>
          <el-select v-model="selectedSource" size="small" style="width: 120px">
            <el-option label="Web" value="web" />
            <el-option label="Mac" value="mac" />
            <el-option label="Windows" value="windows" />
          </el-select>
        </div>
      </template>
      <el-input
        v-model="newContent"
        type="textarea"
        :rows="5"
        placeholder="Paste or type content here... (Ctrl+Enter to submit)"
        @keydown.ctrl.enter="submitContent"
        @keydown.meta.enter="submitContent"
      />
      <div class="input-actions">
        <span class="input-hint">Ctrl+Enter to submit</span>
        <el-button type="primary" @click="submitContent" :loading="isSubmitting">
          <el-icon><Upload /></el-icon> Submit
        </el-button>
      </div>
    </el-card>

    <!-- LAN Server -->
    <el-card class="lan-section">
      <template #header>
        <span>LAN Access</span>
      </template>
      <div class="lan-body">
        <div class="lan-ip-row">
          <span class="lan-label">Your IP</span>
          <span class="lan-ip">{{ lanStatus.ip || '—' }}</span>
        </div>
        <div class="lan-ip-row">
          <span class="lan-label">Share URL</span>
          <span class="lan-url">{{ viteUrl }}</span>
        </div>
        <div class="lan-hint">
          Open this URL on any device on the same network — uses the same Vue interface.
        </div>
        <div class="lan-actions">
          <el-button size="small" @click="copyUrl(viteUrl)">
            <el-icon><CopyDocument /></el-icon> Copy URL
          </el-button>
        </div>

        <el-divider content-position="left" style="margin: 12px 0 8px">
          <span style="font-size:12px;color:#aaa">Standalone (no Vite needed)</span>
        </el-divider>
        <div class="lan-actions" style="align-items:center">
          <template v-if="lanStatus.running">
            <span class="lan-url" style="font-size:13px">{{ lanStatus.url }}</span>
            <el-button size="small" @click="copyUrl(lanStatus.url!)">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
            <el-button type="danger" size="small" :loading="lanLoading" @click="stopLan">Stop</el-button>
          </template>
          <template v-else>
            <el-input-number v-model="lanPort" :min="1024" :max="65535" size="small"
              style="width:130px" controls-position="right" />
            <el-button type="primary" size="small" :loading="lanLoading" @click="startLan">
              Start (port {{ lanPort }})
            </el-button>
          </template>
        </div>
      </div>
    </el-card>

    <!-- History -->
    <el-card class="history-section">
      <template #header>
        <div class="card-header">
          <span>History ({{ clipboardHistory.length }})</span>
          <el-input
            v-model="searchText"
            placeholder="Search..."
            size="small"
            style="width: 200px"
            clearable
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
        </div>
      </template>

      <div v-if="isLoading" class="loading-container">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>Loading...</span>
      </div>
      <el-empty v-else-if="filteredHistory.length === 0 && clipboardHistory.length === 0" description="No clipboard content yet">
        <el-button type="primary" @click="focusInput">Add Your First Item</el-button>
      </el-empty>
      <el-empty v-else-if="filteredHistory.length === 0" description="No matching results" />
      <div v-else class="history-list">
        <ClipboardItem v-for="item in filteredHistory" :key="item.id" :item="item" />
      </div>
    </el-card>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, Refresh, Delete, Upload, Search,
  Loading, Connection, CircleClose, CopyDocument
} from '@element-plus/icons-vue'
import ClipboardItem from '../components/ClipboardItem.vue'
import {
  addClipboardContent,
  getClipboardHistory,
  clearClipboardHistory,
  getLanServerStatus,
  startLanServer,
  stopLanServer,
  type ClipboardItem as ClipboardItemType,
  type LanServerStatus
} from '../service/api'
import { getWebSocketService } from '../service/websocket'

const router = useRouter()
const wsService = getWebSocketService()

const newContent = ref('')
const selectedSource = ref('web')
const clipboardHistory = ref<ClipboardItemType[]>([])
const isLoading = ref(false)
const isSubmitting = ref(false)
const wsConnected = ref(false)
const searchText = ref('')

const lanStatus = ref<LanServerStatus>({ running: false, port: null, ip: '', url: null })
const lanPort = ref(50002)
const lanLoading = ref(false)

const viteUrl = computed(() =>
  lanStatus.value.ip ? `http://${lanStatus.value.ip}:5001/clipboard-share` : ''
)

const filteredHistory = computed(() => {
  if (!searchText.value) return clipboardHistory.value
  const q = searchText.value.toLowerCase()
  return clipboardHistory.value.filter(i => i.content.toLowerCase().includes(q))
})

function goBack() { router.push('/') }

async function submitContent() {
  if (!newContent.value.trim()) {
    ElMessage.warning('Content cannot be empty')
    return
  }
  isSubmitting.value = true
  try {
    const item = await addClipboardContent(newContent.value, selectedSource.value)
    clipboardHistory.value.unshift(item)
    newContent.value = ''
    ElMessage.success('Submitted!')
  } catch (e: any) {
    ElMessage.error(e.message || 'Failed to add content')
  } finally {
    isSubmitting.value = false
  }
}

async function refreshHistory() {
  isLoading.value = true
  try {
    clipboardHistory.value = await getClipboardHistory(50)
  } catch (e: any) {
    ElMessage.error(e.message || 'Failed to fetch history')
  } finally {
    isLoading.value = false
  }
}

async function showClearConfirm() {
  try {
    await ElMessageBox.confirm('Delete all clipboard history?', 'Warning', {
      confirmButtonText: 'Clear All',
      cancelButtonText: 'Cancel',
      type: 'warning'
    })
    const result = await clearClipboardHistory()
    clipboardHistory.value = []
    ElMessage.success(result.message)
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error('Failed to clear history')
  }
}

function focusInput() { document.querySelector('textarea')?.focus() }

function handleWebSocketUpdate(item: ClipboardItemType) {
  if (!clipboardHistory.value.some(i => i.id === item.id)) {
    clipboardHistory.value.unshift(item)
    ElMessage({ message: `New content from ${item.source}`, type: 'success', duration: 2000 })
  }
}

async function fetchLanStatus() {
  try {
    const status = await getLanServerStatus()
    lanStatus.value = status
    if (status.port) lanPort.value = status.port
  } catch (_) {}
}

async function startLan() {
  lanLoading.value = true
  try {
    const result = await startLanServer(lanPort.value)
    lanStatus.value = result
    ElMessage.success(`LAN server started: ${result.url}`)
  } catch (e: any) {
    ElMessage.error(e.message || 'Failed to start LAN server')
  } finally {
    lanLoading.value = false
  }
}

async function stopLan() {
  lanLoading.value = true
  try {
    const result = await stopLanServer()
    lanStatus.value = result
    ElMessage.success('LAN server stopped')
  } catch (e: any) {
    ElMessage.error(e.message || 'Failed to stop LAN server')
  } finally {
    lanLoading.value = false
  }
}

function copyUrl(url: string) {
  if (!url) return
  navigator.clipboard.writeText(url)
    .then(() => ElMessage.success('URL copied!'))
    .catch(() => ElMessage.error('Copy failed'))
}

onMounted(async () => {
  wsService.connect()
  wsService.onClipboardUpdate(handleWebSocketUpdate)

  const interval = setInterval(() => {
    wsConnected.value = wsService.isConnected()
  }, 5000)

  onUnmounted(() => {
    wsService.offClipboardUpdate()
    wsService.disconnect()
    clearInterval(interval)
  })

  await Promise.all([refreshHistory(), fetchLanStatus()])

  setTimeout(() => { wsConnected.value = wsService.isConnected() }, 1000)
})
</script>

<style scoped>
.clipboard-share-view {
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
.header-left { display: flex; align-items: center; gap: 12px; }
.header-left h1 { margin: 0; font-size: 24px; font-weight: 600; }
.header-right { display: flex; gap: 12px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.input-section { margin-bottom: 16px; }
.input-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; }
.input-hint { font-size: 12px; color: #909399; }
.lan-section { margin-bottom: 16px; }
.lan-body { display: flex; flex-direction: column; gap: 10px; }
.lan-ip-row { display: flex; align-items: center; gap: 12px; }
.lan-label { font-size: 13px; color: #909399; min-width: 72px; }
.lan-ip { font-size: 15px; font-weight: 600; font-family: monospace; color: #303133; }
.lan-url { font-size: 14px; font-family: monospace; color: #409eff; }
.lan-hint { font-size: 13px; color: #909399; }
.lan-actions { display: flex; gap: 8px; align-items: center; }
.history-section { margin-bottom: 20px; }
.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: #909399;
  gap: 12px;
}
.loading-container .el-icon { font-size: 32px; }
.history-list { max-height: 600px; overflow-y: auto; }
</style>
