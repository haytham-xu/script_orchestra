<template>
  <div class="fg-detail" v-loading="isLoading">
    <header class="fg-topbar">
      <div class="fg-topbar-left">
        <el-button link @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          <span>Repositories</span>
        </el-button>
        <h1 v-if="repo">{{ repo.name }}</h1>
      </div>
      <div class="fg-topbar-right">
        <el-tag v-if="repo" :type="repo.mode === 'ENCRYPTED' ? 'success' : 'info'" size="small">
          {{ repo.mode }}
        </el-tag>
        <el-tag :type="statusColor(repo?.status)" size="small">
          {{ repo?.status ?? 'unknown' }}
        </el-tag>
        <el-button :icon="FolderOpened" size="small" @click="openFolder">Open Folder</el-button>
        <el-button :icon="Setting" size="small" @click="goToSettings">Settings</el-button>
        <el-button :icon="Refresh" size="small" @click="loadAll">Refresh</el-button>
      </div>
    </header>

    <!-- Lock banner -->
    <section v-if="isLocked" class="fg-banner">
      <el-icon><Lock /></el-icon>
      <div class="fg-banner-body">
        <div class="fg-banner-title">
          {{ lockLabel }} in progress
          <template v-if="lockActionType === 'manual_upload' && pendingUploadCount > 0">
            — {{ pendingUploadCount }} file(s) waiting to be uploaded manually
          </template>
        </div>
        <div class="fg-banner-sub">
          Action folder: <code>{{ queue?.action_folder }}</code>
          <template v-if="pendingQueueCount > 0">
            &nbsp;·&nbsp; {{ pendingQueueCount }} queued item(s)
          </template>
        </div>
      </div>
      <el-button
        v-if="canResume"
        size="small"
        type="primary"
        @click="resume"
        :loading="isBusy">
        Resume
      </el-button>
    </section>

    <main class="fg-content">

      <section class="fg-card">
        <h2>Sync</h2>
        <p class="fg-hint">Fully automated via API. Fast for small changes.</p>
        <div class="fg-actions">
          <el-button
            type="primary"
            :icon="Upload"
            :disabled="!canPushPull"
            @click="push"
            :loading="isBusy">
            Push
          </el-button>
          <el-button
            type="primary"
            plain
            :icon="Download"
            :disabled="!canPushPull"
            @click="pull"
            :loading="isBusy">
            Pull
          </el-button>
        </div>
      </section>

      <section class="fg-card" v-if="queueStats.total > 0 || queue?.lock">
        <div class="fg-files-header">
          <h2>
            Queue
            <span class="fg-files-count">({{ queueStats.total }})</span>
          </h2>
          <div class="fg-files-toolbar">
            <el-tag v-if="queueStats.in_progress > 0" type="warning" size="small">{{ queueStats.in_progress }} active</el-tag>
            <el-tag v-if="queueStats.error > 0" type="danger" size="small">{{ queueStats.error }} errors</el-tag>
            <el-tag v-if="queueStats.done > 0" type="success" size="small">{{ queueStats.done }} done</el-tag>
            <el-button size="small" :icon="Refresh" @click="loadQueue">Refresh</el-button>
          </div>
        </div>
        <el-progress
          v-if="queueStats.total > 0"
          :percentage="Math.round((queueStats.done / queueStats.total) * 100)"
          :status="queueStats.error > 0 ? 'exception' : queueStats.done === queueStats.total ? 'success' : undefined"
          style="margin-bottom:10px" />
        <div class="fg-files-list" style="max-height:300px">
          <div
            v-for="item in queueItems"
            :key="item.key"
            class="fg-file-row">
            <span class="fg-queue-status" :class="`fg-q-${item.status.toLowerCase()}`">
              {{ item.status === 'IN_PROGRESS' ? '⟳' : item.status === 'DONE' ? '✓' : item.status === 'ERROR' ? '✗' : '·' }}
            </span>
            <span class="fg-file-path mono">{{ item.path }}</span>
            <span class="fg-queue-action">{{ item.action }}</span>
            <span class="fg-size">{{ formatSize(item.size) }}</span>
          </div>
          <div v-if="queueItems.length === 0" class="fg-files-empty">No queued items.</div>
        </div>
        <div v-if="queueItems.some(i => i.last_error)" style="margin-top:8px">
          <div v-for="item in queueItems.filter(i => i.last_error)" :key="'e_'+item.key" class="fg-queue-error">
            <span class="mono">{{ item.path }}</span>: {{ item.last_error }}
          </div>
        </div>
      </section>

      <section class="fg-card">
        <div class="fg-files-header">
          <h2>Files</h2>
          <el-button size="small" :icon="Refresh" :loading="filesLoading" @click="refreshFileTree">Refresh</el-button>
        </div>
        <el-tree
          :key="fileTreeKey"
          lazy
          :load="loadFileTreeChildren"
          :props="{ label: 'label', isLeaf: 'isLeaf' }"
          node-key="path">
          <template #default="{ data }">
            <span class="fg-tree-node">
              <span>{{ data.label }}</span>
              <span v-if="!data.is_dir" class="fg-size">{{ formatSize(data.size) }}</span>
            </span>
          </template>
        </el-tree>
      </section>

    </main>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useFileGitRepoDetail } from './FileGitRepoDetailView'
import {
  ArrowLeft, FolderOpened, Refresh, Upload, Download, Lock, Setting,
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

const view = useFileGitRepoDetail()
const {
  repo, queue, isLoading, isBusy,
  isLocked, lockActionType, pendingUploadCount, pendingQueueCount,
  canPushPull, canResume,
  repoId,
  loadAll,
  push, pull, resume,
  openFolder, goBack,
  fileTreeKey, filesLoading, loadFileTreeChildren, refreshFileTree,
  queueItems, queueStats, loadQueue,
} = view

function goToSettings() {
  router.push(`/file-git/${route.params.id}/settings`)
}

const lockLabel = computed(() => {
  switch (lockActionType.value) {
    case 'push': return 'Push'
    case 'pull': return 'Pull'
    case 'manual_upload': return 'Manual upload'
    case 'manual_download': return 'Manual download'
    default: return 'Operation'
  }
})

function statusColor(status?: string) {
  if (status === 'ready') return 'success'
  if (status === 'syncing') return 'warning'
  if (status === 'locked') return 'warning'
  return 'danger'
}

function formatSize(n: number) {
  if (!Number.isFinite(n) || n < 0) return '?'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(2)} GB`
}
</script>

<style scoped>
.fg-detail {
  min-height: 100vh;
  background: #f5f5f7;
  color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}
.fg-topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(245, 245, 247, 0.85);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  padding: 12px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.fg-topbar-left {
  display: flex;
  align-items: baseline;
  gap: 16px;
}
.fg-topbar-left h1 {
  font-size: 17px;
  margin: 0;
  font-weight: 600;
}
.fg-topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.fg-banner {
  max-width: 900px;
  margin: 12px auto 0;
  padding: 12px 16px;
  background: #fff8e6;
  border: 1px solid #f5d97e;
  border-radius: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.fg-banner-body { flex: 1; }
.fg-banner-title {
  font-weight: 600;
  color: #7a5a00;
}
.fg-banner-sub {
  font-size: 12px;
  color: #7a5a00;
  margin-top: 2px;
}
.fg-content {
  max-width: 900px;
  margin: 0 auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.fg-card {
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  padding: 16px 20px;
}
.fg-card h2 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 4px;
}
.fg-hint {
  font-size: 12px;
  color: #86868b;
  margin: 0 0 12px;
}
.fg-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.fg-files-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.fg-files-header h2 { margin: 0; }
.fg-tree-node {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.fg-queue-status {
  width: 16px;
  flex-shrink: 0;
  font-size: 13px;
  text-align: center;
}
.fg-q-done { color: #34c759; }
.fg-q-in_progress { color: #ff9500; }
.fg-q-error { color: #ff3b30; }
.fg-q-todo { color: #86868b; }
.fg-queue-action {
  font-size: 11px;
  color: #86868b;
  flex-shrink: 0;
  margin-right: 8px;
}
.fg-queue-error {
  font-size: 11px;
  color: #ff3b30;
  padding: 2px 0;
}
</style>
