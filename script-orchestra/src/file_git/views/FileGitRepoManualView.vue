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

        <!-- Prepare progress panel -->
        <transition name="fg-manual-expand">
          <div v-if="manualPreparePanel.active" class="fg-mp-panel">
            <!-- Status line -->
            <div class="fg-mp-status-line">
              <el-icon v-if="manualPreparePanel.status === 'running'" class="fg-mp-icon-spin"><Loading /></el-icon>
              <el-icon v-else-if="manualPreparePanel.status === 'done'" class="fg-mp-icon-done"><CircleCheck /></el-icon>
              <el-icon v-else class="fg-mp-icon-error"><CircleClose /></el-icon>
              <span class="fg-mp-label">Preparing Upload</span>
              <span v-if="manualPreparePanel.total > 0" class="fg-mp-count">
                {{ manualPreparePanel.current.toLocaleString() }} / {{ manualPreparePanel.total.toLocaleString() }} files
                <span v-if="manualPreparePanel.eta" class="fg-mp-eta">· ETA {{ manualPreparePanel.eta }}</span>
              </span>
              <span class="fg-mp-dot" :class="`fg-mp-dot--${manualPreparePanel.status}`"></span>
            </div>
            <!-- Progress bar: indeterminate while scanning, determinate once total known -->
            <div class="fg-mp-bar-wrap">
              <div v-if="manualPreparePanel.status === 'running' && manualPreparePanel.total === 0" class="fg-mp-bar-indeterminate">
                <div class="fg-mp-bar-inner"></div>
              </div>
              <div v-else-if="manualPreparePanel.status === 'running'" class="fg-mp-bar-track">
                <div class="fg-mp-bar-fill" :style="{ width: `${manualPreparePanel.pct}%` }"></div>
              </div>
              <div v-else-if="manualPreparePanel.status === 'done'" class="fg-mp-bar-done"></div>
              <div v-else class="fg-mp-bar-error"></div>
            </div>
            <!-- Current file or final message -->
            <div class="fg-mp-detail">
              <span v-if="manualPreparePanel.status === 'running' && manualPreparePanel.currentFile"
                class="fg-mp-current-file" :title="manualPreparePanel.currentFile">
                {{ manualPreparePanel.currentFile }}
              </span>
              <span v-else-if="manualPreparePanel.message" class="fg-mp-message"
                :class="manualPreparePanel.status === 'error' ? 'fg-mp-message--error' : ''">
                {{ manualPreparePanel.message }}
              </span>
            </div>
          </div>
        </transition>

        <!-- Confirm progress panel -->
        <transition name="fg-manual-expand">
          <div v-if="confirmProgress.active" class="fg-confirm-progress">
            <div class="fg-cp-status-line">
              <el-icon v-if="confirmProgress.status === 'running'" class="fg-cp-icon-spin"><Loading /></el-icon>
              <el-icon v-else-if="confirmProgress.status === 'done'" class="fg-cp-icon-done"><CircleCheck /></el-icon>
              <el-icon v-else class="fg-cp-icon-error"><CircleClose /></el-icon>
              <span class="fg-cp-label">Confirming Upload</span>
              <span v-if="confirmProgress.step > 0 && confirmProgress.status === 'running'" class="fg-cp-steps">
                step {{ confirmProgress.step }} / {{ confirmProgress.totalSteps }}
              </span>
              <span class="fg-cp-dot" :class="`fg-cp-dot--${confirmProgress.status}`"></span>
            </div>
            <div class="fg-cp-bar-wrap">
              <div v-if="confirmProgress.status === 'running'" class="fg-cp-bar-track">
                <div
                  class="fg-cp-bar-fill"
                  :style="{ width: confirmProgress.totalSteps > 0 ? `${(confirmProgress.step / confirmProgress.totalSteps) * 100}%` : '0%' }"
                ></div>
              </div>
              <div v-else-if="confirmProgress.status === 'done'" class="fg-cp-bar-done"></div>
              <div v-else class="fg-cp-bar-error"></div>
            </div>
            <div v-if="confirmProgress.stepLabel" class="fg-cp-detail">
              <span class="fg-cp-message" :class="confirmProgress.status === 'error' ? 'fg-cp-message--error' : ''">
                {{ confirmProgress.stepLabel }}
              </span>
            </div>
          </div>
        </transition>

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
          <el-button :icon="Close" :disabled="!canAbandonManualUpload" type="danger" plain @click="abandonManualUpload">Cancel</el-button>
          <span v-if="postManualUploadHint" class="fg-action-hint">{{ postManualUploadHint }}</span>
        </div>
      </section>

      <section class="fg-card">
        <h2>Manual Download</h2>

        <!-- Stage 1: Scan differences -->
        <div class="fg-dl-stage">
          <div class="fg-dl-stage-head">
            <span class="fg-dl-stage-num">1</span>
            <span class="fg-dl-stage-title">Scan differences (remote exists, local missing)</span>
            <el-button size="small" :icon="Search" :loading="dlScanLoading" @click="runDownloadScan">Scan</el-button>
            <span v-if="dlScanSummary" class="fg-dl-summary">
              {{ dlScanSummary.count.toLocaleString() }} remote-only item(s) · {{ formatSize(dlScanSummary.total_size) }}
            </span>
          </div>
          <div v-if="dlScanDone" class="fg-dl-tree" v-loading="dlScanLoading">
            <el-tree
              ref="dlScanTreeRef"
              :key="dlScanTreeKey"
              lazy
              :load="loadDownloadScanChildren"
              :props="{ label: 'label', isLeaf: 'isLeaf' }"
              node-key="path"
              empty-text="Nothing remote-only — local is in sync with the cloud">
              <template #default="{ data }">
                <span class="fg-dl-node">
                  <el-icon class="fg-dl-node-icon">
                    <FolderOpened v-if="data.is_dir" />
                    <Document v-else />
                  </el-icon>
                  <span class="fg-dl-name">{{ data.label }}</span>
                  <span v-if="data.size != null" class="fg-dl-size">{{ formatSize(data.size) }}</span>
                  <el-tooltip v-if="isEncrypted" placement="top" :hide-after="0" effect="dark">
                    <template #content>
                      <div class="fg-enc-tooltip">
                        <div class="fg-enc-tooltip-label">Cloud path (encoded)</div>
                        <div class="fg-enc-tooltip-path">{{ data.encoded_path }}</div>
                      </div>
                    </template>
                    <el-icon class="fg-dl-enc-icon" @click.stop><InfoFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
            </el-tree>
          </div>
        </div>

        <!-- Stage 2: Acquire lock -->
        <div class="fg-dl-stage">
          <div class="fg-dl-stage-head">
            <span class="fg-dl-stage-num">2</span>
            <span class="fg-dl-stage-title">Acquire lock, then download the encrypted files into <code>.fgit/buffer/</code> by hand</span>
            <el-button size="small" :icon="Download" :disabled="!canPreManualDownload" @click="preManualDownload">Acquire Lock</el-button>
          </div>
        </div>

        <!-- Stage 3: Decrypt & reconcile -->
        <div class="fg-dl-stage">
          <div class="fg-dl-stage-head">
            <span class="fg-dl-stage-num">3</span>
            <span class="fg-dl-stage-title">Decrypt &amp; reconcile</span>
            <el-button :icon="Check" size="small" :disabled="!canPostManualDownload" @click="postManualDownload">Decrypt &amp; Reconcile</el-button>
          </div>
          <el-checkbox v-model="downloadUseCustomDest" class="fg-dl-custom-check">
            Decrypt to custom destination (set in repo Settings) — pure export, does not reconcile into the repo
          </el-checkbox>

          <!-- Decrypt progress panel (reuses the fg-mp-* panel styles) -->
          <transition name="fg-manual-expand">
            <div v-if="downloadPanel.active" class="fg-mp-panel">
              <div class="fg-mp-status-line">
                <el-icon v-if="downloadPanel.status === 'running'" class="fg-mp-icon-spin"><Loading /></el-icon>
                <el-icon v-else-if="downloadPanel.status === 'done'" class="fg-mp-icon-done"><CircleCheck /></el-icon>
                <el-icon v-else class="fg-mp-icon-error"><CircleClose /></el-icon>
                <span class="fg-mp-label">Decrypting Files</span>
                <span v-if="downloadPanel.total > 0" class="fg-mp-count">
                  {{ downloadPanel.current.toLocaleString() }} / {{ downloadPanel.total.toLocaleString() }} files
                  <span v-if="downloadPanel.eta" class="fg-mp-eta">· ETA {{ downloadPanel.eta }}</span>
                </span>
                <span class="fg-mp-dot" :class="`fg-mp-dot--${downloadPanel.status}`"></span>
              </div>
              <div class="fg-mp-bar-wrap">
                <div v-if="downloadPanel.status === 'running' && downloadPanel.total === 0" class="fg-mp-bar-indeterminate">
                  <div class="fg-mp-bar-inner"></div>
                </div>
                <div v-else-if="downloadPanel.status === 'running'" class="fg-mp-bar-track">
                  <div class="fg-mp-bar-fill" :style="{ width: `${downloadPanel.pct}%` }"></div>
                </div>
                <div v-else-if="downloadPanel.status === 'done'" class="fg-mp-bar-done"></div>
                <div v-else class="fg-mp-bar-error"></div>
              </div>
              <div class="fg-mp-detail">
                <span v-if="downloadPanel.status === 'running' && downloadPanel.currentFile"
                  class="fg-mp-current-file" :title="downloadPanel.currentFile">
                  {{ downloadPanel.currentFile }}
                </span>
                <span v-else-if="downloadPanel.message" class="fg-mp-message"
                  :class="downloadPanel.status === 'error' ? 'fg-mp-message--error' : ''">
                  {{ downloadPanel.message }}
                </span>
              </div>
            </div>
          </transition>

          <!-- Decrypt result -->
          <div v-if="downloadResult" class="fg-confirm-result fg-dl-result"
            :class="downloadResult.unmapped.length > 0 ? 'fg-confirm-warn' : 'fg-confirm-ok'">
            <div class="fg-confirm-summary">
              <el-icon style="vertical-align: middle; margin-right: 4px;">
                <CircleCheck v-if="downloadResult.unmapped.length === 0" />
                <Warning v-else />
              </el-icon>
              {{ downloadResult.decrypted.toLocaleString() }} files decrypted
              <span v-if="downloadResult.destination"> &nbsp;→&nbsp; <code>{{ downloadResult.destination }}</code></span>
              <span v-if="downloadResult.unmapped.length > 0"> &nbsp;·&nbsp; {{ downloadResult.unmapped.length }} unmapped</span>
            </div>
            <div v-if="downloadResult.unmapped.length > 0" class="fg-confirm-missing">
              Unmapped: {{ downloadResult.unmapped.slice(0, 3).join(', ') }}{{ downloadResult.unmapped.length > 3 ? ` +${downloadResult.unmapped.length - 3} more` : '' }}
            </div>
          </div>
        </div>
      </section>

    </main>
  </div>
</template>

<script lang="ts" setup>
import { useRouter, useRoute } from 'vue-router'
import { useFileGitRepoDetail } from './FileGitRepoDetailView'
import {
  ArrowLeft, Refresh, Upload, Download, Check, CircleCheck, CircleClose,
  Warning, Loading, Close, Search, FolderOpened, Document, InfoFilled,
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

const view = useFileGitRepoDetail()
const {
  repo, isLoading, isBusy,
  isLocked, isEncrypted,
  canManualUploadPrepare, canPostManualUpload, canAbandonManualUpload, postManualUploadHint,
  canPreManualDownload, canPostManualDownload,
  manualSubpath, manualUploadLocalPath, manualUploadCloudPath,
  manualPreparePanel, confirmResult, confirmProgress,
  downloadPanel, downloadResult, downloadUseCustomDest,
  dlScanTreeRef, dlScanTreeKey, dlScanLoading, dlScanSummary, dlScanDone,
  loadDownloadScanChildren, runDownloadScan,
  loadAll,
  manualUpload, postManualUpload, abandonManualUpload,
  preManualDownload, postManualDownload,
} = view

function goToDetail() {
  router.push(`/file-git/${route.params.id}`)
}

function formatSize(bytes: number | null): string {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
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

/* Prepare progress panel */
.fg-mp-panel {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  overflow: hidden;
}
.fg-mp-status-line {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.fg-mp-label {
  font-size: 13px;
  font-weight: 600;
  flex: 1;
}
.fg-mp-count {
  font-size: 12px;
  color: #409eff;
  font-weight: 600;
}
.fg-mp-eta {
  font-weight: 400;
  color: #909399;
}
.fg-mp-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.fg-mp-dot--running { background: #409eff; animation: fg-mp-pulse 1.2s ease-in-out infinite; }
.fg-mp-dot--done    { background: #67c23a; }
.fg-mp-dot--error   { background: #f56c6c; }
@keyframes fg-mp-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}
.fg-mp-icon-spin  { color: #409eff; animation: fg-mp-spin 0.9s linear infinite; }
.fg-mp-icon-done  { color: #67c23a; }
.fg-mp-icon-error { color: #f56c6c; }
@keyframes fg-mp-spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
.fg-mp-bar-wrap { margin-bottom: 5px; }
.fg-mp-bar-indeterminate {
  height: 5px;
  background: #e4e7ed;
  border-radius: 3px;
  overflow: hidden;
}
.fg-mp-bar-inner {
  height: 100%;
  width: 40%;
  background: #409eff;
  border-radius: 3px;
  animation: fg-mp-slide 1.4s ease-in-out infinite;
}
@keyframes fg-mp-slide {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(350%); }
}
.fg-mp-bar-track {
  height: 5px;
  background: #e4e7ed;
  border-radius: 3px;
  overflow: hidden;
}
.fg-mp-bar-fill {
  height: 100%;
  background: #409eff;
  border-radius: 3px;
  transition: width 0.3s ease;
}
.fg-mp-bar-done  { height: 5px; border-radius: 3px; background: #67c23a; }
.fg-mp-bar-error { height: 5px; border-radius: 3px; background: #f56c6c; }
.fg-mp-detail { min-height: 16px; }
.fg-mp-current-file {
  font-size: 11px;
  color: #909399;
  font-family: monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}
.fg-mp-message { font-size: 12px; color: #606266; }
.fg-mp-message--error { color: #f56c6c; }

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
/* Confirm progress panel */
.fg-confirm-progress {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  overflow: hidden;
}
.fg-cp-status-line {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.fg-cp-label {
  font-size: 13px;
  font-weight: 600;
  flex: 1;
}
.fg-cp-steps {
  font-size: 12px;
  color: #409eff;
  font-weight: 600;
}
.fg-cp-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.fg-cp-dot--running { background: #409eff; animation: fg-cp-pulse 1.2s ease-in-out infinite; }
.fg-cp-dot--done    { background: #67c23a; }
.fg-cp-dot--error   { background: #f56c6c; }
@keyframes fg-cp-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}
.fg-cp-icon-spin { color: #409eff; animation: fg-cp-spin 0.9s linear infinite; }
.fg-cp-icon-done { color: #67c23a; }
.fg-cp-icon-error { color: #f56c6c; }
@keyframes fg-cp-spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
.fg-cp-bar-wrap { margin-bottom: 5px; }
.fg-cp-bar-track {
  height: 5px;
  background: #e4e7ed;
  border-radius: 3px;
  overflow: hidden;
}
.fg-cp-bar-fill {
  height: 100%;
  background: #409eff;
  border-radius: 3px;
  transition: width 0.3s ease;
}
.fg-cp-bar-done  { height: 5px; border-radius: 3px; background: #67c23a; }
.fg-cp-bar-error { height: 5px; border-radius: 3px; background: #f56c6c; }
.fg-cp-detail { min-height: 16px; }
.fg-cp-message { font-size: 12px; color: #606266; }
.fg-cp-message--error { color: #f56c6c; }

/* Expand/collapse transition for confirm progress */
.fg-manual-expand-enter-active,
.fg-manual-expand-leave-active {
  transition: max-height 0.25s ease, opacity 0.2s ease;
  max-height: 120px;
  overflow: hidden;
}
.fg-manual-expand-enter-from,
.fg-manual-expand-leave-to {
  max-height: 0;
  opacity: 0;
}

/* Manual download — staged layout */
.fg-dl-stage {
  padding: 10px 0;
  border-top: 1px solid #f0f0f0;
}
.fg-dl-stage:first-of-type { border-top: none; }
.fg-dl-stage-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.fg-dl-stage-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}
.fg-dl-stage-title {
  font-size: 13px;
  color: #1d1d1f;
  flex: 1;
  min-width: 180px;
}
.fg-dl-stage-title code {
  font-family: monospace;
  background: #f0f0f0;
  padding: 0 4px;
  border-radius: 3px;
}
.fg-dl-summary {
  font-size: 12px;
  color: #409eff;
  font-weight: 600;
}
.fg-dl-tree {
  margin-top: 8px;
  max-height: 360px;
  overflow: auto;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 6px 10px;
}
.fg-dl-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.fg-dl-node-icon { font-size: 14px; color: #909399; flex-shrink: 0; }
.fg-dl-name { font-size: 13px; }
.fg-dl-size { font-size: 11px; color: #a8abb2; flex-shrink: 0; }
.fg-dl-enc-icon {
  font-size: 13px;
  color: #c0c4cc;
  cursor: default;
  flex-shrink: 0;
  vertical-align: middle;
}
.fg-dl-enc-icon:hover { color: #409eff; }
.fg-dl-custom-check { margin-top: 8px; display: block; }
.fg-dl-result { margin-top: 12px; margin-bottom: 0; }
.fg-dl-result code {
  font-family: monospace;
  font-size: 12px;
}
.fg-enc-tooltip { line-height: 1.5; }
.fg-enc-tooltip-label {
  font-size: 11px;
  opacity: 0.65;
  margin-bottom: 2px;
}
.fg-enc-tooltip-path {
  font-family: monospace;
  font-size: 12px;
  word-break: break-all;
  max-width: 480px;
}
</style>
