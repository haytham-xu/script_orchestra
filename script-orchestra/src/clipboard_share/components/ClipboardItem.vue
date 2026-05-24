<template>
  <div class="clipboard-item">
    <div class="item-header">
      <div class="item-info">
        <el-tag :type="sourceTagType" size="small">{{ item.source }}</el-tag>
        <span class="item-time">{{ formatTime(item.timestamp) }}</span>
        <span class="item-length">{{ item.length }} chars</span>
      </div>
      <div class="item-actions">
        <el-button type="primary" size="small" @click="copyToClipboard">
          <el-icon><DocumentCopy /></el-icon>
          Copy
        </el-button>
      </div>
    </div>
    <div class="item-content">
      <pre>{{ item.content }}</pre>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentCopy } from '@element-plus/icons-vue'
import type { ClipboardItem } from '../service/api'

interface Props {
  item: ClipboardItem
}

const props = defineProps<Props>()

const sourceTagType = computed(() => {
  switch (props.item.source) {
    case 'mac':
      return 'success'
    case 'windows':
      return 'warning'
    default:
      return 'info'
  }
})

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffSec < 60) return `${diffSec}s ago`
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffHour < 24) return `${diffHour}h ago`
  if (diffDay < 7) return `${diffDay}d ago`

  return date.toLocaleString()
}

async function copyToClipboard() {
  try {
    await navigator.clipboard.writeText(props.item.content)
    ElMessage.success('Copied to clipboard!')
  } catch (error) {
    console.error('Failed to copy:', error)
    ElMessage.error('Failed to copy to clipboard')
  }
}
</script>

<style scoped>
.clipboard-item {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  background: #fff;
  transition: all 0.2s;
}

.clipboard-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.item-info {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: #606266;
}

.item-time {
  color: #909399;
}

.item-length {
  color: #909399;
  font-size: 12px;
}

.item-content {
  background: #f5f7fa;
  border-radius: 4px;
  padding: 12px;
  max-height: 300px;
  overflow: auto;
}

.item-content pre {
  margin: 0;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
  color: #303133;
}
</style>
