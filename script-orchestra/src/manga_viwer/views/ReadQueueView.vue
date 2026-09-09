<template>
  <div class="rq-root">
    <div class="rq-header">
      <el-button size="small" @click="router.back()">← Back</el-button>
      <h2 class="rq-title">Read Queue</h2>
      <span class="rq-count">{{ entries.length }} item{{ entries.length !== 1 ? 's' : '' }}</span>
    </div>

    <div v-if="loading" class="rq-loading">Loading…</div>

    <div v-else-if="entries.length === 0" class="rq-empty">
      No folders saved for later. Use the bookmark button on a folder to add it here.
    </div>

    <div v-else class="rq-list">
      <div v-for="entry in entries" :key="entry.folder_id" class="rq-item">
        <div class="rq-item-info">
          <div class="rq-item-name">{{ folderName(entry.folder_id) }}</div>
          <div class="rq-item-meta">Added {{ formatDate(entry.added_at) }}</div>
        </div>
        <el-button size="small" type="danger" @click="remove(entry.folder_id)" :loading="removing.has(entry.folder_id)">
          Remove
        </el-button>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElButton, ElMessage } from 'element-plus'
import { fetchReadQueue, removeFromReadQueue } from '@/manga_viwer/service/Service'
import type { ReadQueueEntry } from '@/manga_viwer/service/Service'

const router = useRouter()
const loading = ref(true)
const entries = ref<ReadQueueEntry[]>([])
const folderNames = ref<Record<string, string>>({})
const removing = ref<Set<string>>(new Set())

function folderName(id: string): string {
  return folderNames.value[id] || id
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString()
}

async function load() {
  loading.value = true
  try {
    const res = await fetchReadQueue()
    entries.value = res.entries
    for (const [id, f] of Object.entries(res.folders)) {
      folderNames.value[id] = (f as any).name || id
    }
  } catch {
    ElMessage.error('Failed to load read queue')
  } finally {
    loading.value = false
  }
}

async function remove(folderId: string) {
  removing.value = new Set([...removing.value, folderId])
  try {
    await removeFromReadQueue(folderId)
    entries.value = entries.value.filter(e => e.folder_id !== folderId)
    ElMessage.success('Removed from read queue')
  } catch {
    ElMessage.error('Failed to remove')
  } finally {
    const s = new Set(removing.value)
    s.delete(folderId)
    removing.value = s
  }
}

onMounted(load)
</script>

<style scoped>
.rq-root { padding: 24px 32px; }
.rq-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.rq-title { margin: 0; font-size: 20px; font-weight: 700; }
.rq-count { font-size: 14px; color: #909399; }
.rq-loading, .rq-empty { color: #909399; padding: 40px 0; text-align: center; font-size: 15px; }
.rq-list { display: flex; flex-direction: column; gap: 12px; }
.rq-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px; border-radius: 12px;
  background: #fff; border: 1px solid #ebeef5;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.rq-item-name { font-size: 15px; font-weight: 600; color: #303133; }
.rq-item-meta { font-size: 12px; color: #909399; margin-top: 3px; }
</style>
