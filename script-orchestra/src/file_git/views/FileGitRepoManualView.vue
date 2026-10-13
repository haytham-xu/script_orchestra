<template>
  <div class="fg-detail" v-loading="isLoading">
    <header class="fg-topbar">
      <div class="fg-topbar-left">
        <el-button link @click="goToDetail">
          <el-icon><ArrowLeft /></el-icon>
          <span>{{ repo?.name ?? 'Repository' }}</span>
        </el-button>
        <h1>Manual Transfer</h1>
      </div>
      <div class="fg-topbar-right">
        <el-button :icon="Refresh" size="small" @click="loadAll">Refresh</el-button>
      </div>
    </header>

    <main class="fg-content">

      <section class="fg-card fg-card-info">
        <p class="fg-info-text">
          Use when automated push/pull is too slow or you want to move individual files.
          You drag files yourself via the cloud app; this tool handles encryption, index tracking, and lock management.
          See <strong>Doc</strong> in the repo header for full details.
        </p>
      </section>

      <section class="fg-card">
        <h2>Manual Upload</h2>
        <el-form label-position="top" style="margin-bottom: 8px;">
          <el-form-item label="Subpath (relative, empty = whole repo)">
            <el-input
              v-model="manualSubpath"
              placeholder="e.g. photos/2024"
              :disabled="isLocked" />
            <div v-if="manualUploadLocalPath || manualUploadCloudPath" class="fg-path-preview">
              <div v-if="manualUploadLocalPath">
                Local path: <code>{{ manualUploadLocalPath }}</code>
              </div>
              <div v-if="manualUploadCloudPath">
                Cloud path: <code>{{ manualUploadCloudPath }}</code>
              </div>
            </div>
          </el-form-item>
        </el-form>

        <!-- Inline prepare progress -->
        <div v-if="prepareProgress" class="fg-prepare-progress">
          <div class="fg-prepare-bar-row">
            <el-progress
              :percentage="prepareProgress.pct"
              :stroke-width="6"
              :show-text="false"
              style="flex: 1;" />
            <span class="fg-prepare-pct">{{ prepareProgress.pct }}%</span>
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

        <!-- Confirm result -->
        <div v-if="confirmResult" class="fg-confirm-result" :class="confirmResult.missing.length > 0 ? 'fg-confirm-warn' : 'fg-confirm-ok'">
          <div class="fg-confirm-summary">
            <el-icon style="vertical-align: middle; margin-right: 4px;">
              <CircleCheck v-if="confirmResult.missing.length === 0" />
              <Warning v-else />
            </el-icon>
            {{ confirmResult.confirmed.toLocaleString() }} files confirmed on cloud
            <span v-if="confirmResult.missing.length > 0"> &nbsp;·&nbsp; {{ confirmResult.missing.length }} missing</span>
          </div>
          <div v-if="confirmResult.missing.length > 0" class="fg-confirm-missing">
            Missing: {{ confirmResult.missing.slice(0, 3).join(', ') }}{{ confirmResult.missing.length > 3 ? ` +${confirmResult.missing.length - 3} more` : '' }}
          </div>
        </div>

        <div class="fg-action-row">
          <el-button :icon="Upload" :disabled="!canManualUploadPrepare" :loading="isBusy && !isLocked" @click="manualUpload">Prepare</el-button>
          <el-button :icon="Check" :disabled="!canPostManualUpload" :loading="isBusy && isLocked" @click="postManualUpload">Confirm</el-button>
          <span v-if="postManualUploadHint" class="fg-action-hint">{{ postManualUploadHint }}</span>
        </div>
      </section>

      <section class="fg-card">
        <h2>Manual Download</h2>
        <div class="fg-action-row">
          <el-button :icon="Download" :disabled="!canPreManualDownload" @click="preManualDownload">Acquire Lock</el-button>
          <el-button :icon="Check" :disabled="!canPostManualDownload" @click="postManualDownload">Decrypt &amp; Reconcile</el-button>
        </div>
      </section>

    </main>
  </div>
</template>

<script lang="ts" setup>
import { useRouter, useRoute } from 'vue-router'
import { useFileGitRepoDetail } from './FileGitRepoDetailView'
import { ArrowLeft, Refresh, Upload, Download, Check, CircleCheck, Warning } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

const view = useFileGitRepoDetail()
const {
  repo, isLoading, isBusy,
  isLocked,
  canManualUploadPrepare, canPostManualUpload, postManualUploadHint,
  canPreManualDownload, canPostManualDownload,
  manualSubpath, manualUploadLocalPath, manualUploadCloudPath,
  prepareProgress, confirmResult,
  loadAll,
  manualUpload, postManualUpload,
  preManualDownload, postManualDownload,
} = view

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
.fg-card-info {
  background: #f0f7ff;
  border: 1px solid #c8e0ff;
}
.fg-info-text {
  font-size: 13px;
  color: #2c5282;
  margin: 0;
  line-height: 1.6;
}
.fg-card h2 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 12px;
}
.fg-path-preview {
  font-size: 12px;
  color: #86868b;
  margin-top: 6px;
}
.fg-path-preview code {
  font-family: monospace;
  color: #1d1d1f;
}
.fg-action-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.fg-action-hint {
  font-size: 12px;
  color: #909399;
}

/* Inline progress bar */
.fg-prepare-progress {
  margin-bottom: 12px;
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
.fg-prepare-eta {
  color: #909399;
}
.fg-prepare-done {
  color: #67c23a;
  font-weight: 600;
}
.fg-prepare-file {
  margin-top: 4px;
  font-size: 11px;
  color: #909399;
  font-family: monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Confirm result */
.fg-confirm-result {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 13px;
}
.fg-confirm-ok {
  background: #f0f9eb;
  border: 1px solid #b3e19d;
  color: #2d6a1c;
}
.fg-confirm-warn {
  background: #fdf6ec;
  border: 1px solid #f5dab1;
  color: #7d5a00;
}
.fg-confirm-summary {
  display: flex;
  align-items: center;
  font-weight: 500;
}
.fg-confirm-missing {
  margin-top: 4px;
  font-size: 11px;
  font-family: monospace;
  opacity: 0.8;
}
</style>
