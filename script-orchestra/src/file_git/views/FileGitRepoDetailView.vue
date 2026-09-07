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
        <span v-if="cloudIndexSyncedAt" class="fg-synced-at" :title="'cloud_index last synced: ' + cloudIndexSyncedAt">
          synced {{ formatBeijingTime(cloudIndexSyncedAt) }}
        </span>
        <span v-else class="fg-synced-at fg-synced-never">never synced</span>
        <el-button :icon="FolderOpened" size="small" @click="openFolder">Open Folder</el-button>
        <el-button :icon="Tools" size="small" @click="goToManual">Manual</el-button>
        <el-button :icon="Filter" size="small" @click="goToSyncFilter">Sync Filter</el-button>
        <el-button :icon="Setting" size="small" @click="goToSettings">Settings</el-button>
        <el-button :icon="QuestionFilled" size="small" @click="docDrawerVisible = true">Doc</el-button>
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
        <div class="fg-action-row">
          <el-button type="primary" :icon="Upload" :disabled="!canPushPull" @click="push" :loading="isBusy">Push</el-button>
          <el-button type="primary" plain :icon="Download" :disabled="!canPushPull" @click="pull" :loading="isBusy">Pull</el-button>
          <ProgressPopover v-model:visible="progressVisible" :items="progressItems" :count="progressActiveCount" />
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

    <!-- Doc drawer -->
    <el-drawer v-model="docDrawerVisible" title="How it works" size="600px" direction="rtl">
      <div class="fg-doc">
        <section>
          <h3>Push <span class="fg-doc-sub">local → cloud</span></h3>
          <ul>
            <li>Downloads latest <code>cloud_index</code> from remote first</li>
            <li>Rebuilds <code>local_index</code> by scanning local files</li>
            <li>Diffs local vs cloud; uploads new/modified files</li>
            <li>Moves cloud copies of locally-deleted files to remote trash</li>
            <li>Skips <em>local-only</em> and <em>remote-only</em> paths entirely</li>
            <li>Rewrites and uploads <code>cloud_index</code></li>
            <li>Runs hook cleanup at the end</li>
          </ul>
        </section>
        <section>
          <h3>Pull <span class="fg-doc-sub">cloud → local</span></h3>
          <ul>
            <li>Downloads latest <code>cloud_index</code> from remote first</li>
            <li>Downloads new/modified files from cloud</li>
            <li>Moves local copies of cloud-deleted files to local trash</li>
            <li>Moves local copies of <em>remote-only</em> paths to local trash</li>
            <li>Skips <em>local-only</em> paths entirely</li>
            <li>Rebuilds <code>local_index</code> after applying changes</li>
            <li>Runs hook cleanup at the end</li>
          </ul>
        </section>
        <section>
          <h3>Manual</h3>
          <p class="fg-doc-p">Use when automated push/pull is too slow or you want to move individual files. You drag files yourself via the cloud app; this tool handles encryption, index tracking, and lock management.</p>
          <p class="fg-doc-p"><strong>Upload:</strong></p>
          <ul>
            <li><em>Prepare</em> — scans the subpath, encrypts files to <code>.fgit/buffer/</code> (encrypted mode) or records them as-is, acquires the lock. Then drag the files into the cloud app by hand.</li>
            <li><em>Confirm</em> — verifies what actually landed in cloud, updates and uploads <code>cloud_index</code>, releases lock</li>
          </ul>
          <p class="fg-doc-p"><strong>Download:</strong></p>
          <ul>
            <li><em>Acquire Lock</em> — locks the repo and opens <code>.fgit/buffer/</code> as drop target. Then download files from the cloud app into that folder.</li>
            <li><em>Decrypt &amp; Reconcile</em> — decrypts buffer files to their correct paths (encrypted mode), rebuilds <code>local_index</code>, updates and uploads <code>cloud_index</code>, releases lock</li>
          </ul>
        </section>
        <section>
          <h3>Sync Filter</h3>
          <p class="fg-doc-p"><strong>Modes:</strong></p>
          <ul>
            <li><em>synced</em> — included in push &amp; pull (default)</li>
            <li><em>local-only</em> — never uploaded; push/pull skip it completely</li>
            <li><em>remote-only</em> — never downloaded; pull skips it; push trashes any local copy</li>
          </ul>
          <p class="fg-doc-p"><strong>Status tags (what each mode + file state means):</strong></p>
          <ul>
            <li><em>synced</em> + exists in both → <code>synced</code></li>
            <li><em>synced</em> + local only → <code>pending push</code></li>
            <li><em>synced</em> + cloud only → <code>pending pull</code></li>
            <li><em>synced</em> + both but different size → <code>changed</code></li>
            <li><em>local-only</em> + local only → <code>local-only · not pushed</code></li>
            <li><em>remote-only</em> + cloud only → <code>remote-only · not pulled</code></li>
            <li><em>remote-only</em> + local copy exists → <code>conflict — local copy should not exist</code></li>
          </ul>
          <p class="fg-doc-p"><strong>Apply:</strong> full idempotent scan — uploads missing synced files, downloads missing synced files, soft-deletes files that are in the wrong place per the current mode</p>
          <p class="fg-doc-p">Child paths inherit parent mode. Override per folder by selecting a mode in the dropdown (only valid transitions are shown).</p>
        </section>
        <section>
          <h3>Local Index <span class="fg-doc-sub">(Settings)</span></h3>
          <ul>
            <li><em>Rebuild Local Index</em> — rescans the local file tree, overwrites <code>.fgit/local_index.json</code>. Push and Pull both do this automatically; only run manually if the index looks stale.</li>
            <li><em>Rebuild Cloud Index</em> — traverses the entire cloud folder via storage API (slow/expensive for large repos), overwrites the local mirror and uploads the new version. Use when cloud was changed outside this tool.</li>
            <li><em>Cleanup Expired</em> — removes <code>.fgit/action/</code> and <code>.fgit/trash/</code> folders older than the retention days set in Config</li>
            <li><em>Cleanup All</em> — removes all action/trash folders regardless of age</li>
          </ul>
        </section>
        <section>
          <h3>Hook</h3>
          <ul>
            <li>Runs automatically at the <strong>end</strong> of every operation (Push, Pull, Apply)</li>
            <li>Deletes <code>.fgit/action/</code> and <code>.fgit/trash/</code> subfolders older than the retention period</li>
            <li>Retention days configured in Settings → Config → <em>Auto-cleanup retention</em></li>
            <li>Set to 0 to clean up everything after each operation; set higher to keep history</li>
            <li>Hook runs synchronously before the operation returns — no background process</li>
          </ul>
        </section>
      </div>
    </el-drawer>
  </div>
</template>

<script lang="ts" setup>
import { computed, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useFileGitRepoDetail } from './FileGitRepoDetailView'
import {
  ArrowLeft, FolderOpened, Refresh, Upload, Download, Lock, Setting, Tools, Filter, QuestionFilled,
} from '@element-plus/icons-vue'
import ProgressPopover from '../components/ProgressPopover.vue'

const router = useRouter()
const route = useRoute()

const docDrawerVisible = ref(false)

const view = useFileGitRepoDetail()
const {
  repo, queue, isLoading, isBusy,
  isLocked, lockActionType, pendingUploadCount, pendingQueueCount,
  canPushPull, canResume,
  repoId,
  cloudIndexSyncedAt,
  loadAll,
  push, pull, resume,
  openFolder, goBack,
  fileTreeKey, filesLoading, loadFileTreeChildren, refreshFileTree,
  queueItems, queueStats, loadQueue,
  progressItems, progressVisible, progressActiveCount,
} = view

function goToSettings() {
  router.push(`/file-git/${route.params.id}/settings`)
}

function goToManual() {
  router.push(`/file-git/${route.params.id}/manual`)
}

function goToSyncFilter() {
  router.push(`/file-git/${route.params.id}/sync-filter`)
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

function formatBeijingTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  })
}

function formatRelTime(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
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
  margin: 12px 24px 0;
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
.fg-action-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
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
:deep(.fg-log-error td) {
  background: #fff5f5 !important;
}
.fg-step-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 4px;
}
.fg-step {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 12px 14px;
  background: #f5f5f7;
  border-radius: 8px;
}
.fg-step-btn {
  flex-shrink: 0;
  width: 110px;
  padding-top: 2px;
}
.fg-step-btn .el-button { width: 100%; }
.fg-step-desc { flex: 1; }
.fg-step-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 4px;
}
.fg-step-body {
  font-size: 12px;
  color: #48484a;
  line-height: 1.5;
}
.fg-step-body code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: #e5e5ea;
  border-radius: 3px;
  padding: 0 3px;
  font-size: 11px;
}
.fg-synced-at {
  font-size: 11px;
  color: #86868b;
  white-space: nowrap;
}
.fg-synced-never {
  color: #ff9500;
}
.fg-doc {
  display: flex;
  flex-direction: column;
  gap: 20px;
  font-size: 13px;
  line-height: 1.6;
  color: #1d1d1f;
  padding: 4px 0;
}
.fg-doc section h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 8px;
  color: #1d1d1f;
}
.fg-doc-sub {
  font-size: 12px;
  font-weight: 400;
  color: #86868b;
  margin-left: 4px;
}
.fg-doc ul {
  margin: 0 0 6px;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.fg-doc-p {
  font-size: 13px;
  color: #3a3a3c;
  margin: 6px 0 4px;
}
.fg-doc li {
  color: #3a3a3c;
}
.fg-doc code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: #e5e5ea;
  border-radius: 3px;
  padding: 0 3px;
  font-size: 11px;
}
</style>
