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
        <el-button size="small" @click="loadConfig">Discard</el-button>
        <el-button type="primary" size="small" @click="saveConfig" :loading="isBusy">Save</el-button>
      </div>
    </header>

    <main class="fg-content">

      <!-- Info -->
      <section class="fg-card" v-loading="statsLoading">
        <div class="fg-section-header">
          <h2>Info</h2>
          <el-button size="small" :icon="Refresh" @click="loadStats">Refresh</el-button>
        </div>
        <div v-if="statsLocal" class="fg-stats-grid">
          <div class="fg-stats-group">
            <div class="fg-stats-label">Local index</div>
            <div class="fg-stat-row">
              <span class="fg-stat-name">Files</span>
              <span class="fg-stat-val">{{ statsLocal.file_count.toLocaleString() }}</span>
            </div>
            <div class="fg-stat-row">
              <span class="fg-stat-name">Folders</span>
              <span class="fg-stat-val">{{ statsLocal.folder_count.toLocaleString() }}</span>
            </div>
            <div class="fg-stat-row">
              <span class="fg-stat-name">Total items</span>
              <span class="fg-stat-val">{{ statsLocal.total_count.toLocaleString() }}</span>
            </div>
            <div class="fg-stat-row">
              <span class="fg-stat-name">Total size</span>
              <span class="fg-stat-val">{{ formatSize(statsLocal.total_size) }}</span>
            </div>
          </div>
          <div class="fg-stats-group">
            <div class="fg-stats-label">Cloud index</div>
            <div class="fg-stat-row">
              <span class="fg-stat-name">Files</span>
              <span class="fg-stat-val">{{ statsCloud!.file_count.toLocaleString() }}</span>
            </div>
            <div class="fg-stat-row">
              <span class="fg-stat-name">Folders</span>
              <span class="fg-stat-val">{{ statsCloud!.folder_count.toLocaleString() }}</span>
            </div>
            <div class="fg-stat-row">
              <span class="fg-stat-name">Total items</span>
              <span class="fg-stat-val">{{ statsCloud!.total_count.toLocaleString() }}</span>
            </div>
            <div class="fg-stat-row">
              <span class="fg-stat-name">Total size</span>
              <span class="fg-stat-val">{{ formatSize(statsCloud!.total_size) }}</span>
            </div>
          </div>
        </div>
        <div v-else-if="!statsLoading" class="fg-hint" style="margin-top:8px;">
          No index data — run Rebuild Local Index first.
        </div>
      </section>

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
          <el-form-item label="Decrypt destination (manual download)">
            <el-input v-model="editDownloadDestRoot" placeholder="e.g. D:\recovered\boutique" spellcheck="false" />
            <p class="fg-hint">
              Absolute path. Used only when "Decrypt to custom destination" is checked on the
              Manual Transfer page — files are decrypted here (preserving their folder structure)
              instead of being reconciled into the repo. Leave empty to disable.
            </p>
          </el-form-item>
        </el-form>
      </section>

      <section class="fg-card">
        <h2>Index &amp; Cleanup</h2>
        <div class="fg-action-row">
          <el-button :icon="Refresh" :disabled="!canRebuildLocal" @click="rebuildLocalIndex">Rebuild Local Index</el-button>
          <el-button :icon="Refresh" :disabled="!canRebuildCloud" :loading="isBusy" @click="rebuildCloudIndex">Rebuild Cloud Index</el-button>
          <el-button :icon="Delete" :disabled="!canCleanup" @click="cleanup('expired')">Cleanup Expired</el-button>
          <el-button :icon="Delete" type="danger" plain :disabled="!canCleanup" @click="cleanup('all')">Cleanup All</el-button>
        </div>

        <!-- Operation progress panel -->
        <transition name="fg-op-expand">
          <div v-if="settingsProgress.active" class="fg-op-panel">
            <!-- Status line -->
            <div class="fg-op-status-line">
              <el-icon v-if="settingsProgress.status === 'running'" class="fg-op-icon-spin"><Loading /></el-icon>
              <el-icon v-else-if="settingsProgress.status === 'done'" class="fg-op-icon-done"><CircleCheck /></el-icon>
              <el-icon v-else class="fg-op-icon-error"><CircleClose /></el-icon>
              <span class="fg-op-label">{{ settingsProgress.label }}</span>
              <span v-if="settingsProgress.count > 0" class="fg-op-count">
                {{ settingsProgress.count.toLocaleString() }} files
              </span>
              <span class="fg-op-dot" :class="`fg-op-dot--${settingsProgress.status}`"></span>
            </div>
            <!-- Progress bar -->
            <div class="fg-op-bar-wrap">
              <div v-if="settingsProgress.status === 'running'" class="fg-op-bar-indeterminate">
                <div class="fg-op-bar-inner"></div>
              </div>
              <div v-else-if="settingsProgress.status === 'done'" class="fg-op-bar-done"></div>
              <div v-else class="fg-op-bar-error"></div>
            </div>
            <!-- Current file / result message -->
            <div class="fg-op-detail">
              <span v-if="settingsProgress.status === 'running' && settingsProgress.currentFile"
                class="fg-op-current-file" :title="settingsProgress.currentFile">
                {{ settingsProgress.currentFile }}
              </span>
              <span v-else-if="settingsProgress.message" class="fg-op-message"
                :class="settingsProgress.status === 'error' ? 'fg-op-message--error' : ''">
                {{ settingsProgress.message }}
              </span>
            </div>
          </div>
        </transition>
      </section>

      <!-- File Log -->
      <section class="fg-card" v-if="fileLogFolders.length > 0">
        <div class="fg-files-header">
          <h2>File Log</h2>
          <div style="display:flex;align-items:center;gap:8px;">
            <el-select
              :model-value="fileLogFolder"
              size="small"
              style="width:220px;"
              @change="(v: string) => loadFileLog(v)">
              <el-option v-for="f in fileLogFolders" :key="f" :label="f" :value="f" />
            </el-select>
            <el-button size="small" :icon="Refresh" @click="loadFileLogFolders">Refresh</el-button>
          </div>
        </div>
        <div v-loading="fileLogLoading">
          <div v-if="fileLogRecords.length === 0" class="fg-hint" style="margin-top:8px;">
            No records for this action folder.
          </div>
          <el-table
            v-else
            :data="fileLogRecords"
            size="small"
            style="width:100%;margin-top:8px;"
            :row-class-name="(row: any) => row.row.result === 'error' ? 'fg-log-error' : ''">
            <el-table-column prop="path" label="Path" min-width="200" show-overflow-tooltip />
            <el-table-column prop="action" label="Action" width="150" />
            <el-table-column prop="mode" label="Mode" width="110" />
            <el-table-column label="Local" width="65" align="center">
              <template #default="{ row }">
                <el-icon v-if="row.in_local" style="color:#34c759"><Check /></el-icon>
                <span v-else style="color:#86868b">—</span>
              </template>
            </el-table-column>
            <el-table-column label="Remote" width="70" align="center">
              <template #default="{ row }">
                <el-icon v-if="row.in_remote" style="color:#34c759"><Check /></el-icon>
                <span v-else style="color:#86868b">—</span>
              </template>
            </el-table-column>
            <el-table-column label="Result" width="80">
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="row.result === 'ok' ? 'success' : row.result === 'error' ? 'danger' : 'info'">
                  {{ row.result ?? 'pending' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="Detail" min-width="160" show-overflow-tooltip />
            <el-table-column prop="ts" label="Time" width="90" show-overflow-tooltip />
          </el-table>
        </div>
      </section>

    </main>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useFileGitRepoDetail } from './FileGitRepoDetailView'
import { FileGitService } from '../service/FileGitService'
import type { RepoIndexStats } from '../service/FileGitService'
import {
  ArrowLeft, Refresh, Check, Delete, Loading, CircleCheck, CircleClose,
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

const view = useFileGitRepoDetail()
const {
  repo, config, isLoading, isBusy,
  canRebuildLocal, canRebuildCloud, canCleanup,
  editPassword, editRemotePath, editHookDays, editDownloadDestRoot,
  finalRemotePath,
  settingsProgress,
  loadAll, loadConfig,
  saveConfig,
  rebuildLocalIndex, rebuildCloudIndex,
  cleanup,
  fileLogFolders, fileLogFolder, fileLogRecords, fileLogLoading,
  loadFileLogFolders, loadFileLog,
  repoId,
} = view

const statsLocal = ref<RepoIndexStats | null>(null)
const statsCloud = ref<RepoIndexStats | null>(null)
const statsLoading = ref(false)

async function loadStats() {
  statsLoading.value = true
  try {
    const res = await FileGitService.getStats(repoId.value)
    if (res.success) {
      statsLocal.value = res.local
      statsCloud.value = res.cloud
    }
  } catch {
    // non-fatal
  } finally {
    statsLoading.value = false
  }
}

function formatSize(n: number): string {
  if (!Number.isFinite(n) || n < 0) return '?'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(2)} GB`
}

onMounted(() => {
  loadStats()
})

function goToDetail() {
  router.push(`/file-git/${route.params.id}`)
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
  align-items: center;
  gap: 12px;
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
.fg-files-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.fg-files-header h2 { margin: 0; }
:deep(.fg-log-error td) {
  background: #fff5f5 !important;
}
.fg-action-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
}
.fg-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.fg-section-header h2 { margin: 0; }
.fg-stats-grid {
  display: flex;
  gap: 32px;
  flex-wrap: wrap;
}
.fg-stats-group { min-width: 180px; flex: 1; }
.fg-stats-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #86868b;
  margin-bottom: 8px;
}
.fg-stat-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 5px 0;
  border-bottom: 1px solid #f2f2f7;
}
.fg-stat-row:last-child { border-bottom: none; }
.fg-stat-name { font-size: 13px; color: #48484a; }
.fg-stat-val { font-size: 14px; font-weight: 600; color: #1d1d1f; font-variant-numeric: tabular-nums; }

/* Operation progress panel */
.fg-op-panel {
  margin-top: 12px;
  padding: 10px 14px 8px;
  background: #f8f9fa;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
}
.fg-op-status-line {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 8px;
}
.fg-op-icon-spin {
  color: #409eff;
  animation: fg-spin 1s linear infinite;
}
.fg-op-icon-done { color: #67c23a; }
.fg-op-icon-error { color: #f56c6c; }
@keyframes fg-spin { to { transform: rotate(360deg); } }
.fg-op-label {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  flex: 1;
  min-width: 0;
}
.fg-op-count {
  font-size: 12px;
  font-weight: 600;
  color: #409eff;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.fg-op-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.fg-op-dot--running  { background: #409eff; animation: fg-pulse 1.2s ease-in-out infinite; }
.fg-op-dot--done     { background: #67c23a; }
.fg-op-dot--error    { background: #f56c6c; }
.fg-op-dot--idle     { background: #c0c4cc; }
@keyframes fg-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* Progress bar */
.fg-op-bar-wrap { height: 4px; border-radius: 2px; overflow: hidden; margin-bottom: 8px; background: #e4e7ed; }
.fg-op-bar-indeterminate { height: 100%; width: 100%; position: relative; overflow: hidden; }
.fg-op-bar-inner {
  position: absolute;
  height: 100%;
  width: 35%;
  background: #409eff;
  border-radius: 2px;
  animation: fg-indeterminate 1.4s ease-in-out infinite;
}
@keyframes fg-indeterminate {
  0%   { left: -40%; }
  60%  { left: 100%; }
  100% { left: 100%; }
}
.fg-op-bar-done  { height: 100%; width: 100%; background: #67c23a; border-radius: 2px; }
.fg-op-bar-error { height: 100%; width: 100%; background: #f56c6c; border-radius: 2px; }

/* Current file / message */
.fg-op-detail { min-height: 16px; }
.fg-op-current-file {
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}
.fg-op-message {
  font-size: 12px;
  color: #606266;
}
.fg-op-message--error { color: #f56c6c; }

/* Expand/collapse transition */
.fg-op-expand-enter-active, .fg-op-expand-leave-active {
  transition: max-height 0.25s ease, opacity 0.25s ease;
  max-height: 120px;
}
.fg-op-expand-enter-from, .fg-op-expand-leave-to {
  max-height: 0;
  opacity: 0;
}
</style>
