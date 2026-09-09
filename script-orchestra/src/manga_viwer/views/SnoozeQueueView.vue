<template>
  <div class="sq-root">
    <div class="sq-header">
      <el-button size="small" @click="router.back()">← Back</el-button>
      <h2 class="sq-title">Snooze Queue</h2>
      <span class="sq-count">{{ folders.length }} item{{ folders.length !== 1 ? 's' : '' }}</span>
      <el-button v-if="folders.length > 0" size="small" @click="cleanup" :loading="cleaning">
        Clean Up Expired
      </el-button>
    </div>

    <div v-if="loading" class="sq-loading">Loading…</div>

    <div v-else-if="folders.length === 0" class="sq-empty">
      No snoozed folders. Use the 💤 button on a folder to hide it from random picks for 1 week.
    </div>

    <div v-else class="sq-list">
      <div v-for="f in folders" :key="f.id" class="sq-row">
        <div class="sq-status-bar">
          <span v-if="isExpired(f.id)" class="sq-tag-expired">Expired</span>
          <span v-else class="sq-tag-active">Active — expires {{ formatExpiry(f.id) }}</span>
        </div>
        <FolderLine
          :folder="f"
          :mainCategories="mainCategories"
          :subCategories="subCategories"
          :isMarkedForDeletion="false"
          :isInReadQueue="false"
          :isInSnoozeQueue="true"
          removeLabel="Remove from snooze"
          @toggle-favorite="toggleFavorite"
          @confirm-tag="handleConfirmTag"
          @remove-tag="handleRemoveTag"
          @remove-from-queue="remove"
          @save-for-later="() => {}"
          @snooze="() => {}"
          @start-edit="() => {}"
          @commit-edit="() => {}"
          @open-folder="() => {}"
          @mark-delete="() => {}"
          @unmark-delete="() => {}"
          @reset-read-count="() => {}"
        />
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElButton, ElMessage } from 'element-plus'
import { fetchSnoozeQueue, removeFromSnoozeQueue, cleanupSnoozeQueue, fetchSettings, updateFolderModels } from '@/manga_viwer/service/Service'
import FolderLine from '@/manga_viwer/components/FolderLine.vue'
import type { FolderModel } from '@/manga_viwer/service/Model'

const router = useRouter()
const loading = ref(true)
const folders = ref<FolderModel[]>([])
const expiries = ref<Record<string, number>>({})
const mainCategories = ref<{ key: string }[]>([])
const subCategories = ref<{ key: string }[]>([])
const cleaning = ref(false)

function isExpired(folderId: string): boolean {
  const exp = expiries.value[folderId]
  return exp != null && exp * 1000 < Date.now()
}

function formatExpiry(folderId: string): string {
  const exp = expiries.value[folderId]
  return exp ? new Date(exp * 1000).toLocaleString() : ''
}

async function load() {
  loading.value = true
  try {
    const [res, settings] = await Promise.all([fetchSnoozeQueue(), fetchSettings().catch(() => null)])
    if (settings?.categories) {
      mainCategories.value = settings.categories.main || []
      subCategories.value = settings.categories.sub || []
    }
    expiries.value = {}
    for (const entry of res.entries) {
      expiries.value[entry.folder_id] = entry.expires_at
    }
    folders.value = res.entries
      .map(e => res.folders[e.folder_id] as FolderModel | undefined)
      .filter((f): f is FolderModel => !!f)
  } catch {
    ElMessage.error('Failed to load snooze queue')
  } finally {
    loading.value = false
  }
}

async function remove(folderId: string) {
  try {
    await removeFromSnoozeQueue(folderId)
    folders.value = folders.value.filter(f => f.id !== folderId)
    ElMessage.success('Removed from snooze queue')
  } catch {
    ElMessage.error('Failed to remove')
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

async function toggleFavorite(f: FolderModel) {
  const next = !f.favorite
  f.favorite = next
  try {
    await updateFolderModels({ [f.id]: { ...f, favorite: next } }, false)
  } catch {
    f.favorite = !next
    ElMessage.error('Failed to update favorite')
  }
}

function handleConfirmTag(f: FolderModel, _group: string) {
  updateFolderModels({ [f.id]: f }, false).catch(() => {})
}

function handleRemoveTag(f: FolderModel, group: string, index: number) {
  ;(f.tags as any)[group].splice(index, 1)
  updateFolderModels({ [f.id]: f }, false).catch(() => {})
}

onMounted(load)
</script>

<style scoped>
.sq-root { padding: 24px 32px; }
.sq-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.sq-title { margin: 0; font-size: 20px; font-weight: 700; }
.sq-count { font-size: 14px; color: #909399; }
.sq-loading, .sq-empty { color: #909399; padding: 40px 0; text-align: center; font-size: 15px; }
.sq-list { display: flex; flex-direction: column; gap: 24px; }
.sq-row { display: flex; flex-direction: column; gap: 4px; }
.sq-status-bar { display: flex; align-items: center; gap: 8px; padding: 0 4px; }
.sq-tag-active { font-size: 12px; font-weight: 600; color: #e6a23c; }
.sq-tag-expired { font-size: 12px; font-weight: 600; color: #f56c6c; }
</style>
