<template>
  <div class="rq-root">
    <div class="rq-header">
      <el-button size="small" @click="router.back()">← Back</el-button>
      <h2 class="rq-title">Read Queue</h2>
      <span class="rq-count">{{ folders.length }} item{{ folders.length !== 1 ? 's' : '' }}</span>
    </div>

    <div v-if="loading" class="rq-loading">Loading…</div>

    <div v-else-if="folders.length === 0" class="rq-empty">
      No folders saved for later. Use the 🔖 button on a folder to add it here.
    </div>

    <div v-else class="rq-list">
      <div v-for="f in folders" :key="f.id" class="rq-row">
        <FolderLine
          :folder="f"
          :mainCategories="mainCategories"
          :subCategories="subCategories"
          :isMarkedForDeletion="false"
          :isInReadQueue="true"
          :isInSnoozeQueue="false"
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
import { fetchReadQueue, removeFromReadQueue, fetchSettings, updateFolderModels } from '@/manga_viwer/service/Service'
import FolderLine from '@/manga_viwer/components/FolderLine.vue'
import type { FolderModel } from '@/manga_viwer/service/Model'

const router = useRouter()
const loading = ref(true)
const folders = ref<FolderModel[]>([])
const removing = ref<Set<string>>(new Set())
const mainCategories = ref<{ key: string }[]>([])
const subCategories = ref<{ key: string }[]>([])

async function load() {
  loading.value = true
  try {
    const [res, settings] = await Promise.all([fetchReadQueue(), fetchSettings().catch(() => null)])
    if (settings?.categories) {
      mainCategories.value = settings.categories.main || []
      subCategories.value = settings.categories.sub || []
    }
    folders.value = res.entries
      .map(e => res.folders[e.folder_id] as FolderModel | undefined)
      .filter((f): f is FolderModel => !!f)
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
    folders.value = folders.value.filter(f => f.id !== folderId)
    ElMessage.success('Removed from read queue')
  } catch {
    ElMessage.error('Failed to remove')
  } finally {
    const s = new Set(removing.value)
    s.delete(folderId)
    removing.value = s
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
.rq-root { padding: 24px 32px; }
.rq-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.rq-title { margin: 0; font-size: 20px; font-weight: 700; }
.rq-count { font-size: 14px; color: #909399; }
.rq-loading, .rq-empty { color: #909399; padding: 40px 0; text-align: center; font-size: 15px; }
.rq-list { display: flex; flex-direction: column; gap: 24px; }
.rq-row { }
</style>
