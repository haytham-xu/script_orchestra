<template>
  <div class="fg-detail" v-loading="isLoading">
    <header class="fg-topbar">
      <div class="fg-topbar-left">
        <el-button link @click="goToDetail">
          <el-icon><ArrowLeft /></el-icon>
          <span>{{ repo?.name ?? 'Repository' }}</span>
        </el-button>
        <h1>Settings</h1>
      </div>
      <div class="fg-topbar-right">
        <el-button :icon="Refresh" size="small" @click="loadAll">Refresh</el-button>
      </div>
    </header>

    <main class="fg-content">

      <section class="fg-card">
        <h2>Config</h2>
        <el-form v-if="config" label-position="top">
          <el-form-item label="Local path">
            <el-input :model-value="config.local_path" disabled />
          </el-form-item>
          <el-form-item label="Mode (immutable)">
            <el-input :model-value="config.mode" disabled />
          </el-form-item>
          <el-form-item label="Remote path (cloud folder)">
            <el-input v-model="editRemotePath" placeholder="/backup/photos" spellcheck="false" />
            <p class="fg-hint" v-if="finalRemotePath">
              Final cloud path: <code>{{ finalRemotePath }}</code>
            </p>
          </el-form-item>
          <el-form-item v-if="config.mode === 'ENCRYPTED'" label="Password">
            <el-input
              v-model="editPassword"
              type="password"
              show-password
              :placeholder="config.password_set ? 'set already — enter new to change' : 'set a password'"
              spellcheck="false" />
            <p class="fg-hint">
              Stored in <code>.fgit/config.json</code> (that folder is gitignored).
              AES-256-GCM keyed by scrypt(password, remote_path).
            </p>
          </el-form-item>
          <el-form-item label="Auto-cleanup retention (days)">
            <el-input-number v-model="editHookDays" :min="0" :max="365" />
          </el-form-item>
        </el-form>
        <div class="fg-actions">
          <el-button type="primary" @click="saveConfig" :loading="isBusy">Save Config</el-button>
          <el-button @click="loadConfig">Discard</el-button>
        </div>
      </section>

      <section class="fg-card">
        <h2>Sync Filter</h2>
        <p class="fg-hint">
          Choose which folders participate in push/pull. Changes apply on the
          next push/pull, not immediately. Unchecking a folder moves its local
          files to the buffer (remote copy is kept). Refresh the remote view
          with <b>Rebuild Cloud Index</b> below.
        </p>
        <el-tree
          ref="syncTreeRef"
          :key="repoId"
          lazy
          :load="loadSyncChildren"
          :props="{ label: 'label', isLeaf: 'isLeaf' }"
          node-key="path"
          show-checkbox
          :check-strictly="true"
          @check-change="(data: any, checked: boolean) => toggleSyncNode(data.path, checked)">
          <template #default="{ data }">
            <span class="fg-sync-node" :class="{ 'fg-sync-danger': !data.checked && data.kind === 'local-only' }">
              <span>{{ data.label }}</span>
              <el-tag
                size="small"
                :type="data.kind === 'both' ? 'success' : data.kind === 'local-only' ? 'info' : 'warning'">
                {{ data.kind === 'both' ? 'backed up' : data.kind === 'local-only' ? 'local only' : 'remote only' }}
              </el-tag>
              <span v-if="!data.checked && data.kind === 'local-only'" class="fg-sync-warn">
                not backed up — sync will refuse
              </span>
            </span>
          </template>
        </el-tree>
        <div class="fg-actions">
          <el-button type="primary" :disabled="!syncDirty" @click="saveSyncFilter">
            Save Sync Filter
          </el-button>
        </div>
      </section>

      <section class="fg-card">
        <h2>Manual Upload</h2>
        <p class="fg-hint">
          For large batches. {{ isEncrypted
            ? 'Files are encrypted into .fgit/buffer/; drag them into the cloud APP by hand.'
            : 'Drag source files into the cloud APP directly.' }}
        </p>
        <el-form label-position="top" style="margin-bottom: 12px;">
          <el-form-item label="Subpath (relative, empty = whole repo)">
            <el-input
              v-model="manualSubpath"
              placeholder="e.g. photos/2024"
              :disabled="isLocked" />
          </el-form-item>
        </el-form>
        <div class="fg-actions">
          <el-button
            :icon="Upload"
            :disabled="!canManualUploadPrepare"
            @click="manualUpload">
            Manual Upload — prepare
          </el-button>
          <el-button
            :icon="Check"
            :disabled="!canPostManualUpload"
            @click="postManualUpload">
            Post Manual Upload — confirm
          </el-button>
        </div>
      </section>

      <section class="fg-card">
        <h2>Manual Download</h2>
        <p class="fg-hint">
          {{ isEncrypted
            ? 'Download ciphertext from the cloud APP into .fgit/buffer/; the tool decrypts on Post.'
            : 'Download files from the cloud APP directly into the repo.' }}
        </p>
        <div class="fg-actions">
          <el-button
            :icon="Download"
            :disabled="!canPreManualDownload"
            @click="preManualDownload">
            Pre Manual Download — acquire lock
          </el-button>
          <el-button
            :icon="Check"
            :disabled="!canPostManualDownload"
            @click="postManualDownload">
            Post Manual Download — decrypt &amp; reconcile
          </el-button>
        </div>
      </section>

      <section class="fg-card">
        <h2>Diff</h2>
        <p class="fg-hint">Compare local files against cloud_index mirror. Read-only; safe while locked.</p>
        <div class="fg-actions">
          <el-button :icon="View" :disabled="!canDiff" @click="runDiff">Compute Diff</el-button>
        </div>
        <div v-if="diffMessage" class="fg-diff-summary">{{ diffMessage }}</div>
        <div v-if="diffAdded.length || diffModified.length || diffDeleted.length" class="fg-diff-lists">
          <div v-if="diffAdded.length" class="fg-diff-group">
            <h3><el-icon><Plus /></el-icon> Added ({{ diffAdded.length }})</h3>
            <ul>
              <li v-for="e in diffAdded" :key="'a_' + e.middle_path" class="mono">
                {{ e.middle_path }} <span class="fg-size">({{ formatSize(e.size) }})</span>
              </li>
            </ul>
          </div>
          <div v-if="diffModified.length" class="fg-diff-group">
            <h3><el-icon><Refresh /></el-icon> Modified ({{ diffModified.length }})</h3>
            <ul>
              <li v-for="e in diffModified" :key="'m_' + e.middle_path" class="mono">
                {{ e.middle_path }} <span class="fg-size">({{ formatSize(e.size) }})</span>
              </li>
            </ul>
          </div>
          <div v-if="diffDeleted.length" class="fg-diff-group">
            <h3><el-icon><Delete /></el-icon> Deleted ({{ diffDeleted.length }})</h3>
            <ul>
              <li v-for="e in diffDeleted" :key="'d_' + e.middle_path" class="mono">
                {{ e.middle_path }} <span class="fg-size">({{ formatSize(e.size) }})</span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section class="fg-card">
        <h2>Index &amp; Cleanup</h2>
        <div class="fg-actions">
          <el-button :icon="Refresh" :disabled="!canRebuildLocal" @click="rebuildLocalIndex">
            Rebuild Local Index
          </el-button>
          <el-button :icon="Refresh" :disabled="!canRebuildCloud" @click="rebuildCloudIndex">
            Rebuild Cloud Index…
          </el-button>
          <el-button :icon="Delete" :disabled="!canCleanup" @click="cleanup('expired')">
            Cleanup Expired
          </el-button>
          <el-button :icon="Delete" type="danger" plain :disabled="!canCleanup" @click="cleanup('all')">
            Cleanup All
          </el-button>
        </div>
      </section>

    </main>
  </div>
</template>

<script lang="ts" setup>
import { useRouter, useRoute } from 'vue-router'
import { useFileGitRepoDetail } from './FileGitRepoDetailView'
import {
  ArrowLeft, Refresh, Upload, Download, Check,
  View, Plus, Delete,
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

const view = useFileGitRepoDetail()
const {
  repo, config, isLoading, isBusy,
  isLocked, isEncrypted,
  canManualUploadPrepare, canPostManualUpload,
  canPreManualDownload, canPostManualDownload,
  canDiff, canRebuildLocal, canRebuildCloud, canCleanup,
  diffAdded, diffModified, diffDeleted, diffMessage,
  editPassword, editRemotePath, editHookDays, manualSubpath,
  finalRemotePath,
  repoId, syncDirty, syncTreeRef, loadSyncChildren, toggleSyncNode, saveSyncFilter,
  loadAll, loadConfig,
  saveConfig,
  manualUpload, postManualUpload,
  preManualDownload, postManualDownload,
  runDiff, rebuildLocalIndex, rebuildCloudIndex,
  cleanup,
} = view

function goToDetail() {
  router.push(`/file-git/${route.params.id}`)
}

function formatSize(n: number) {
  if (!Number.isFinite(n)) return '?'
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
.fg-sync-node {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.fg-sync-danger { color: #c0392b; }
.fg-sync-warn {
  font-size: 11px;
  color: #c0392b;
}
.fg-diff-summary {
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f5f7;
  border-radius: 8px;
  font-size: 12px;
}
.fg-diff-lists {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.fg-diff-group h3 {
  font-size: 13px;
  font-weight: 600;
  margin: 0 0 4px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.fg-diff-group ul {
  margin: 0;
  padding-left: 20px;
  max-height: 200px;
  overflow-y: auto;
  font-size: 12px;
}
.fg-diff-group li { padding: 2px 0; }
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  word-break: break-all;
}
.fg-size {
  color: #86868b;
  font-size: 11px;
}
</style>
