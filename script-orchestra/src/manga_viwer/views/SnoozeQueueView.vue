<template>
  <div class="sq-root">
    <div class="sq-header">
      <el-button size="small" @click="router.back()">← Back</el-button>
      <h2 class="sq-title">Snooze Queue</h2>
      <span class="sq-count">{{ entries.length }} item{{ entries.length !== 1 ? 's' : '' }}</span>
    </div>

    <div v-if="loading" class="sq-loading">Loading…</div>

    <div v-else-if="entries.length === 0" class="sq-empty">
      No snoozed folders. Use the snooze button on a folder to hide it from random picks for 1 week.
    </div>

    <div v-else class="sq-list">
      <div v-for="entry in entries" :key="entry.folder_id"
           class="sq-item" :class="{ 'sq-expired': isExpired(entry) }">
        <div class="sq-item-info">
          <div class="sq-item-name">{{ folderName(entry.folder_id) }}</div>
          <div class="sq-item-meta">
            <span v-if="isExpired(entry)" class="sq-tag-expired">Expired</span>
            <span v-else class="sq-tag-active">Active — expires {{ formatDate(entry.expires_at) }}</span>
            <span class="sq-added">· Snoozed {{ formatDate(entry.added_at) }}</span>
          </div>
        </div>
        <el-button size="small" type="danger" @click="remove(entry.folder_id)" :loading="removing.has(entry.folder_id)">
          Remove
        </el-button>
      </div>
    </div>

    <div v-if="!loading && entries.length > 0" class="sq-actions">
      <el-button size="small" @click="cleanup" :loading="cleaning">Clean Up Expired</el-button>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElButton, ElMessage } from 'element-plus'
import { fetchSnoozeQueue, removeFromSnoozeQueue, cleanupSnoozeQueue } from '@/manga_viwer/service/Service'
import type { SnoozeQueueEntry } from '@/manga_viwer/service/Service'

const router = useRouter()
const loading = ref(true)
const entries = ref<SnoozeQueueEntry[]>([])
const folderNames = ref<Record<string, string>>({})
const removing = ref<Set<string>>(new Set())
const cleaning = ref(false)

function folderName(id: string): string {
  return folderNames.value[id] || id
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString()
}

function isExpired(entry: SnoozeQueueEntry): boolean {
  return entry.expires_at * 1000 < Date.now()
}

async function load() {
  loading.value = true
  try {
    const res = await fetchSnoozeQueue()
    entries.value = res.entries
    for (const [id, f] of Object.entries(res.folders)) {
      folderNames.value[id] = (f as any).name || id
    }
  } catch {
    ElMessage.error('Failed to load snooze queue')
  } finally {
    loading.value = false
  }
}

async function remove(folderId: string) {
  removing.value = new Set([...removing.value, folderId])
  try {
    await removeFromSnoozeQueue(folderId)
    entries.value = entries.value.filter(e => e.folder_id !== folderId)
    ElMessage.success('Removed from snooze queue')
  } catch {
    ElMessage.error('Failed to remove')
  } finally {
    const s = new Set(removing.value)
    s.delete(folderId)
    removing.value = s
  }
}

async function cleanup() {
  cleaning.value = true
  try {
    const { deleted } = await cleanupSnoozeQueue()
    ElMessage.success(`Cleaned up ${deleted} expired entries`)
    await load()
  } catch {
    ElMessage.error('Cleanup failed')
  } finally {
    cleaning.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.sq-root { padding: 24px 32px; }
.sq-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.sq-title { margin: 0; font-size: 20px; font-weight: 700; }
.sq-count { font-size: 14px; color: #909399; }
.sq-loading, .sq-empty { color: #909399; padding: 40px 0; text-align: center; font-size: 15px; }
.sq-list { display: flex; flex-direction: column; gap: 12px; }
.sq-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px; border-radius: 12px;
  background: #fff; border: 1px solid #ebeef5;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.sq-item.sq-expired { opacity: 0.55; }
.sq-item-name { font-size: 15px; font-weight: 600; color: #303133; }
.sq-item-meta { font-size: 12px; color: #909399; margin-top: 3px; display: flex; gap: 6px; }
.sq-tag-active { color: #e6a23c; font-weight: 600; }
.sq-tag-expired { color: #f56c6c; font-weight: 600; }
.sq-added { color: #c0c4cc; }
.sq-actions { margin-top: 20px; display: flex; justify-content: flex-end; }
</style>
