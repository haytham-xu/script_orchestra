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

        <!-- Inline progress bar for Rebuild Cloud Index -->
        <div v-if="prepareProgress" class="fg-prepare-progress" style="margin-top:12px;">
          <div class="fg-prepare-bar-row">
            <el-progress
              :percentage="Math.min(prepareProgress.pct, 100)"
              :stroke-width="6"
              :show-text="false"
              style="flex: 1;" />
            <span class="fg-prepare-pct">{{ Math.min(prepareProgress.pct, 100) }}%</span>
          </div>
          <div class="fg-prepare-meta">
            <span>{{ prepareProgress.current.toLocaleString() }} / {{ prepareProgress.total.toLocaleString() }} files</span>
            <span v-if="prepareProgress.eta" class="fg-prepare-eta">ETA {{ prepareProgress.eta }}</span>
            <span v-else-if="prepareProgress.pct >= 100" class="fg-prepare-done">Done</span>
          </div>
          <div v-if="prepareProgress.pct < 100 && prepareProgress.currentFile" class="fg-prepare-file" :title="prepareProgress.currentFile">
            {{ prepareProgress.currentFile }}
          </div>
        </div>
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
  ArrowLeft, Refresh, Check, Delete,
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

const view = useFileGitRepoDetail()
const {
  repo, config, isLoading, isBusy,
  canRebuildLocal, canRebuildCloud, canCleanup,
  editPassword, editRemotePath, editHookDays,
  finalRemotePath,
  prepareProgress,
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
.fg-stats-group {
  min-width: 180px;
  flex: 1;
}
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
.fg-stat-name {
  font-size: 13px;
  color: #48484a;
}
.fg-stat-val {
  font-size: 14px;
  font-weight: 600;
  color: #1d1d1f;
  font-variant-numeric: tabular-nums;
}
.fg-prepare-progress {
  padding: 10px 12px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}
.fg-prepare-bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.fg-prepare-pct {
  font-size: 12px;
  font-weight: 600;
  color: #409eff;
  min-width: 36px;
  text-align: right;
}
.fg-prepare-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #606266;
}
.fg-prepare-eta { color: #909399; }
.fg-prepare-done { color: #67c23a; font-weight: 600; }
.fg-prepare-file {
  margin-top: 4px;
  font-size: 11px;
  color: #909399;
  font-family: monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
