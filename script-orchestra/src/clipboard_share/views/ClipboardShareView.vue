<template>
  <div class="clipboard-share-view">
    <!-- Header -->
    <div class="header">
      <div class="header-left">
        <el-button @click="goBack" circle>
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1>Clipboard Share</h1>
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
        <el-button @click="refreshHistory" :loading="isLoading">
          <el-icon><Refresh /></el-icon>
          Refresh
        </el-button>
        <el-button @click="showClearConfirm" type="danger" plain>
          <el-icon><Delete /></el-icon>
          Clear All
        </el-button>
      </div>
    </div>

    <!-- Input Section -->
    <el-card class="input-section">
      <template #header>
        <div class="card-header">
          <span>Add New Content</span>
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
        :rows="6"
        placeholder="Paste or type your content here... (supports Ctrl+V / Cmd+V)"
        @keydown.ctrl.enter="submitContent"
        @keydown.meta.enter="submitContent"
      />
      <div class="input-actions">
        <span class="input-hint">Press Ctrl+Enter (Cmd+Enter) to submit</span>
        <el-button type="primary" @click="submitContent" :loading="isSubmitting">
          <el-icon><Upload /></el-icon>
          Submit
        </el-button>
      </div>
    </el-card>

    <!-- History Section -->
    <el-card class="history-section">
      <template #header>
        <div class="card-header">
          <span>History ({{ clipboardHistory.length }} items)</span>
          <el-input
            v-model="searchText"
            placeholder="Search..."
            size="small"
            style="width: 200px"
            clearable
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>
      </template>

      <div v-if="isLoading" class="loading-container">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>Loading history...</span>
      </div>

      <el-empty
        v-else-if="filteredHistory.length === 0 && clipboardHistory.length === 0"
        description="No clipboard content yet"
      >
        <el-button type="primary" @click="focusInput">Add Your First Item</el-button>
      </el-empty>

      <el-empty
        v-else-if="filteredHistory.length === 0"
        description="No matching results"
      />

      <div v-else class="history-list">
        <ClipboardItem
          v-for="item in filteredHistory"
          :key="item.id"
          :item="item"
        />
      </div>
    </el-card>

    <!-- Network Info -->
    <el-card class="info-section">
      <template #header>Connection Info</template>
      <div class="info-content">
        <p><strong>Current URL:</strong> {{ currentURL }}</p>
        <p><strong>Backend API:</strong> {{ backendURL }}</p>
        <p v-if="macIP !== 'YOUR_MAC_IP'">
          <strong>Access from other devices:</strong> http://{{ macIP }}:5001/clipboard-share
        </p>
        <p class="info-hint">
          💡 Tip: Make sure both devices are on the same network. The backend API URL is automatically detected based on your current access URL.
        </p>
      </div>
    </el-card>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft,
  Refresh,
  Delete,
  Upload,
  Search,
  Loading,
  Connection,
  CircleClose
} from '@element-plus/icons-vue'
import ClipboardItem from '../components/ClipboardItem.vue'
import {
  addClipboardContent,
  getClipboardHistory,
  clearClipboardHistory,
  type ClipboardItem as ClipboardItemType
} from '../service/api'
import { getWebSocketService } from '../service/websocket'

const router = useRouter()
const wsService = getWebSocketService()

// State
const newContent = ref('')
const selectedSource = ref('web')
const clipboardHistory = ref<ClipboardItemType[]>([])
const isLoading = ref(false)
const isSubmitting = ref(false)
const isConnected = ref(false)
const searchText = ref('')
const macIP = ref('YOUR_MAC_IP')
const currentURL = ref('')
const backendURL = ref('')

// Computed
const filteredHistory = computed(() => {
  if (!searchText.value) {
    return clipboardHistory.value
  }
  const search = searchText.value.toLowerCase()
  return clipboardHistory.value.filter((item) =>
    item.content.toLowerCase().includes(search)
  )
})

// Methods
function goBack() {
  router.push('/')
}

async function submitContent() {
  if (!newContent.value.trim()) {
    ElMessage.warning('Content cannot be empty')
    return
  }

  isSubmitting.value = true
  try {
    const item = await addClipboardContent({
      content: newContent.value,
      source: selectedSource.value
    })

    // Add to history (will also receive via WebSocket, but add immediately for better UX)
    clipboardHistory.value.unshift(item)

    newContent.value = ''
    ElMessage.success('Content added successfully!')
  } catch (error: any) {
    console.error('Failed to add content:', error)
    ElMessage.error(error.message || 'Failed to add content')
  } finally {
    isSubmitting.value = false
  }
}

async function refreshHistory() {
  isLoading.value = true
  try {
    clipboardHistory.value = await getClipboardHistory(50)
  } catch (error: any) {
    console.error('Failed to fetch history:', error)
    ElMessage.error(error.message || 'Failed to fetch history')
  } finally {
    isLoading.value = false
  }
}

async function showClearConfirm() {
  try {
    await ElMessageBox.confirm(
      'This will permanently delete all clipboard history. Continue?',
      'Warning',
      {
        confirmButtonText: 'Clear All',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )

    const result = await clearClipboardHistory()
    clipboardHistory.value = []
    ElMessage.success(result.message)
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('Failed to clear history:', error)
      ElMessage.error('Failed to clear history')
    }
  }
}

function focusInput() {
  document.querySelector('textarea')?.focus()
}

function handleWebSocketUpdate(item: ClipboardItemType) {
  // Check if item already exists (avoid duplicates)
  const exists = clipboardHistory.value.some((i) => i.id === item.id)
  if (!exists) {
    clipboardHistory.value.unshift(item)
    ElMessage({
      message: `New clipboard content from ${item.source}`,
      type: 'success',
      duration: 2000
    })
  }
}

async function detectMacIP() {
  // Detect current URL and backend URL
  try {
    currentURL.value = window.location.href
    const hostname = window.location.hostname
    const protocol = window.location.protocol

    if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
      macIP.value = hostname
    }

    // Show backend URL
    const backendHost = hostname === 'localhost' || hostname === '127.0.0.1'
      ? 'localhost'
      : hostname
    backendURL.value = `${protocol}//${backendHost}:50001`
  } catch (error) {
    console.error('Failed to detect IP:', error)
  }
}

// Lifecycle
onMounted(async () => {
  // Connect to WebSocket first (before any await)
  wsService.connect()
  wsService.onClipboardUpdate(handleWebSocketUpdate)

  // Monitor connection status
  const interval = setInterval(() => {
    isConnected.value = wsService.isConnected()
  }, 5000)

  // Register cleanup BEFORE any await
  onUnmounted(() => {
    wsService.offClipboardUpdate()
    wsService.disconnect()
    clearInterval(interval)
  })

  // Now do async operations
  await refreshHistory()

  // Check connection status
  setTimeout(() => {
    isConnected.value = wsService.isConnected()
  }, 1000)

  // Detect Mac IP
  detectMacIP()
})
</script>

<style scoped>
.clipboard-share-view {
  padding: 20px;
  max-width: 1200px;
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

.input-section {
  margin-bottom: 20px;
}

.input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}

.input-hint {
  font-size: 12px;
  color: #909399;
}

.history-section {
  margin-bottom: 20px;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: #909399;
  gap: 12px;
}

.loading-container .el-icon {
  font-size: 32px;
}

.history-list {
  max-height: 600px;
  overflow-y: auto;
}

.info-section {
  background: #f0f9ff;
  border-color: #91caff;
}

.info-content p {
  margin: 8px 0;
  font-size: 14px;
}

.info-hint {
  color: #1677ff;
  background: #e6f4ff;
  padding: 12px;
  border-radius: 4px;
  margin-top: 12px;
  border-left: 3px solid #1677ff;
}
</style>
