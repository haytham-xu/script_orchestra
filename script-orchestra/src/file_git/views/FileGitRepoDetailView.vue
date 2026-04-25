<template>
  <div class="repo-detail-container">
    <!-- Left Sidebar -->
    <div class="sidebar">
      <!-- Repository Info Card -->
      <el-card class="sidebar-card info-card">
        <el-button :icon="ArrowLeft" @click="goBack" text class="back-button">Back</el-button>

        <div class="repo-title">
          <el-icon class="repo-icon"><FolderOpened /></el-icon>
          <h2>{{ repo?.name }}</h2>
        </div>

        <div class="meta-tags">
          <el-tag :type="repo?.mode === 'ENCRYPTED' ? 'success' : 'info'" size="small">
            {{ repo?.mode }}
          </el-tag>
          <el-tag
            :type="
              repo?.status === 'ready'
                ? 'success'
                : repo?.status === 'syncing'
                ? 'warning'
                : 'danger'
            "
            size="small"
          >
            {{ repo?.status === 'ready' ? 'Ready' : repo?.status === 'syncing' ? 'Syncing' : 'Error' }}
          </el-tag>
        </div>

        <div class="quick-actions">
          <el-button @click="refreshStatus" :loading="isLoadingStatus" class="quick-button">
            <el-icon><Refresh /></el-icon>
            <span>Refresh</span>
          </el-button>
          <el-button @click="openFolder" class="quick-button">
            <el-icon><FolderOpened /></el-icon>
            <span>Open Folder</span>
          </el-button>
        </div>
      </el-card>

      <!-- Statistics Card -->
      <el-card v-if="status" class="sidebar-card stats-card">
        <div class="stats-list">
          <div class="stat-row added">
            <span class="stat-label">Added</span>
            <span class="stat-value">{{ status.added.length }}</span>
          </div>
          <div class="stat-row modified">
            <span class="stat-label">Modified</span>
            <span class="stat-value">{{ status.modified.length }}</span>
          </div>
          <div class="stat-row deleted">
            <span class="stat-label">Deleted</span>
            <span class="stat-value">{{ status.deleted.length }}</span>
          </div>
          <div class="stat-row total">
            <span class="stat-label">Total</span>
            <span class="stat-value">{{ status.total_files }}</span>
          </div>
        </div>
      </el-card>

      <!-- Actions Card -->
      <el-card class="sidebar-card actions-card">
        <div class="actions-list">
          <el-button @click="pushChanges" :disabled="!hasChanges" :loading="isPushing" plain class="action-button">
            <el-icon><Upload /></el-icon>
            <span>Push</span>
          </el-button>
          <el-button @click="pullChanges" :loading="isPulling" plain class="action-button">
            <el-icon><Download /></el-icon>
            <span>Pull</span>
          </el-button>
          <el-button plain class="action-button">
            <el-icon><CircleCheck /></el-icon>
            <span>Verify</span>
          </el-button>
        </div>
      </el-card>
    </div>

    <!-- Main Content -->
    <el-card v-loading="isLoading" class="content-card">
      <el-tabs v-model="activeTab" class="content-tabs">
        <!-- Changes Tab -->
        <el-tab-pane label="Changes" name="changes">
          <div class="changes-content">
            <!-- Changes List -->
            <div v-if="hasChanges" class="changes-list">
              <!-- Added Files -->
              <div v-if="status.added.length > 0" class="change-group">
                <h3 class="group-title added-title">
                  <el-icon><Plus /></el-icon>
                  Added ({{ status.added.length }})
                </h3>
                <div class="file-list">
                  <div v-for="file in status.added" :key="file.middle_path"
                       :class="['file-item', 'added-item', getFileStatus(file.middle_path) ? `status-${getFileStatus(file.middle_path)}` : '']">
                    <el-icon class="file-icon">
                      <Upload v-if="getFileStatus(file.middle_path) === 'uploading'" class="rotating" />
                      <CircleCheck v-else-if="getFileStatus(file.middle_path) === 'success'" />
                      <Delete v-else-if="getFileStatus(file.middle_path) === 'error'" />
                      <Document v-else />
                    </el-icon>
                    <div class="file-info">
                      <span class="file-path">{{ file.middle_path }}</span>
                      <span v-if="getFileAction(file.middle_path)" class="file-action-badge" :class="`action-type-${getActionType(getFileAction(file.middle_path))}`">
                        {{ getFileAction(file.middle_path) }}
                      </span>
                    </div>
                    <span class="file-size">{{ formatFileSize(file.size) }}</span>
                  </div>
                </div>
              </div>

              <!-- Modified Files -->
              <div v-if="status.modified.length > 0" class="change-group">
                <h3 class="group-title modified-title">
                  <el-icon><Edit /></el-icon>
                  Modified ({{ status.modified.length }})
                </h3>
                <div class="file-list">
                  <div v-for="file in status.modified" :key="file.middle_path"
                       :class="['file-item', 'modified-item', getFileStatus(file.middle_path) ? `status-${getFileStatus(file.middle_path)}` : '']">
                    <el-icon class="file-icon">
                      <Upload v-if="getFileStatus(file.middle_path) === 'uploading'" class="rotating" />
                      <CircleCheck v-else-if="getFileStatus(file.middle_path) === 'success'" />
                      <Delete v-else-if="getFileStatus(file.middle_path) === 'error'" />
                      <Document v-else />
                    </el-icon>
                    <div class="file-info">
                      <span class="file-path">{{ file.middle_path }}</span>
                      <span v-if="getFileAction(file.middle_path)" class="file-action-badge" :class="`action-type-${getActionType(getFileAction(file.middle_path))}`">
                        {{ getFileAction(file.middle_path) }}
                      </span>
                    </div>
                    <span class="file-size">{{ formatFileSize(file.size) }}</span>
                  </div>
                </div>
              </div>

              <!-- Deleted Files -->
              <div v-if="status.deleted.length > 0" class="change-group">
                <h3 class="group-title deleted-title">
                  <el-icon><Delete /></el-icon>
                  Deleted ({{ status.deleted.length }})
                </h3>
                <div class="file-list">
                  <div v-for="file in status.deleted" :key="file.middle_path"
                       :class="['file-item', 'deleted-item', getFileStatus(file.middle_path) ? `status-${getFileStatus(file.middle_path)}` : '']">
                    <el-icon class="file-icon">
                      <Upload v-if="getFileStatus(file.middle_path) === 'uploading'" class="rotating" />
                      <CircleCheck v-else-if="getFileStatus(file.middle_path) === 'success'" />
                      <Delete v-else-if="getFileStatus(file.middle_path) === 'error'" />
                      <Document v-else />
                    </el-icon>
                    <div class="file-info">
                      <span class="file-path">{{ file.middle_path }}</span>
                      <span v-if="getFileAction(file.middle_path)" class="file-action-badge" :class="`action-type-${getActionType(getFileAction(file.middle_path))}`">
                        {{ getFileAction(file.middle_path) }}
                      </span>
                    </div>
                    <span class="file-size">{{ formatFileSize(file.size) }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- No Changes -->
            <div v-else class="no-changes">
              <el-empty description="No changes detected">
                <el-icon :size="64" color="#c0c4cc"><CircleCheck /></el-icon>
              </el-empty>
            </div>
          </div>
        </el-tab-pane>

        <!-- Logs Tab -->
        <el-tab-pane label="Logs" name="logs">
          <div class="logs-content">
            <el-empty description="Operation logs - Coming soon" />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ArrowLeft, FolderOpened, Refresh, Upload, Download, CircleCheck, Plus, Edit, Delete, Document } from '@element-plus/icons-vue'
import { useFileGitRepoDetail } from './FileGitRepoDetailView'

const {
  repo,
  status,
  activeTab,
  isLoading,
  isLoadingStatus,
  isPushing,
  isPulling,
  hasChanges,
  fileQueue,
  visibleFiles,
  isOperating,
  getFileStatus,
  getFileAction,
  getActionType,
  goBack,
  openFolder,
  refreshStatus,
  formatFileSize,
  pushChanges,
  pullChanges
} = useFileGitRepoDetail()
</script>

<style scoped>
.repo-detail-container {
  padding: 20px;
  max-width: 100vw;
  overflow-x: hidden;
  min-height: 100vh;
  height: 100vh;
  background: #f5f5f7;
  box-sizing: border-box;
  display: flex;
  flex-direction: row;
  gap: 16px;
}

.sidebar {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-self: flex-start;
}

.back-button {
  margin-bottom: 12px;
  padding-left: 0 !important;
}

.sidebar-card {
  border-radius: 12px;
  border: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.sidebar-card :deep(.el-card__body) {
  padding: 16px;
}

.card-header {
  font-size: 13px;
  font-weight: 600;
  color: #1d1d1f;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.sidebar-card :deep(.el-card__header) {
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
}

/* Info Card */
.info-card .repo-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.repo-icon {
  font-size: 24px;
  color: #007aff;
  flex-shrink: 0;
}

.repo-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1d1d1f;
  letter-spacing: -0.3px;
  word-break: break-word;
}

.meta-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.quick-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 16px;
}

.quick-button {
  width: 100%;
  height: 32px;
  justify-content: flex-start !important;
  padding: 0 12px !important;
  margin: 0 !important;
}

.quick-button :deep(.el-icon) {
  margin-right: 8px !important;
  margin-left: 0 !important;
  font-size: 14px;
}

.quick-button :deep(span) {
  font-size: 13px;
  margin-left: 0 !important;
}

/* Stats Card */
.stats-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  background: #f5f5f7;
  border-radius: 6px;
  transition: background 0.2s;
}

.stat-row:hover {
  background: #ebebed;
}

.stat-label {
  font-size: 13px;
  color: #1d1d1f;
  font-weight: 500;
}

.stat-value {
  font-size: 15px;
  font-weight: 600;
}

.stat-row.added .stat-value {
  color: #34c759;
}

.stat-row.modified .stat-value {
  color: #ff9500;
}

.stat-row.deleted .stat-value {
  color: #ff3b30;
}

.stat-row.total .stat-value {
  color: #1d1d1f;
}

/* Actions Card */
.actions-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.action-button {
  width: 100%;
  height: 36px;
  justify-content: flex-start !important;
  padding: 0 12px !important;
  margin: 0 !important;
}

.action-button :deep(.el-icon) {
  margin-right: 8px !important;
  margin-left: 0 !important;
  font-size: 16px;
}

.action-button :deep(span) {
  font-size: 14px;
  margin-left: 0 !important;
}

.content-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  border: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  overflow: hidden;
  min-width: 0;
}

.content-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
  min-height: 0;
}

.content-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.content-tabs :deep(.el-tabs__header) {
  margin: 0;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.content-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 24px;
  min-height: 0;
}

.changes-content {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.changes-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.change-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: #1d1d1f;
  letter-spacing: -0.2px;
}

.added-title {
  color: #34c759;
}

.modified-title {
  color: #ff9500;
}

.deleted-title {
  color: #ff3b30;
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e5e5e7;
  transition: all 0.2s;
}

.file-item:hover {
  border-color: #d2d2d7;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

/* Status-based styling */
.file-item.status-uploading {
  background: #f0f9ff;
  border-left-width: 3px;
}

.file-item.status-success {
  background: #f0fff4;
  border-left-width: 3px;
}

.file-item.status-error {
  background: #fff0f0;
  border-left-width: 3px;
}

.file-icon {
  font-size: 20px;
  color: #86868b;
  flex-shrink: 0;
}

.file-item.status-uploading .file-icon {
  color: #007aff;
}

.file-item.status-success .file-icon {
  color: #34c759;
}

.file-item.status-error .file-icon {
  color: #ff3b30;
}

.file-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-path {
  font-size: 14px;
  color: #1d1d1f;
  font-family: 'SF Mono', Monaco, 'Courier New', monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-action-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  width: fit-content;
}

/* Action type colors */
.file-action-badge.action-type-uploading {
  background: #f0f9ff;
  color: #007aff;
}

.file-action-badge.action-type-downloading {
  background: #f0f4ff;
  color: #5856d6;
}

.file-action-badge.action-type-remote-deleting {
  background: #fff0f0;
  color: #ff3b30;
}

.file-action-badge.action-type-local-deleting {
  background: #fff5e5;
  color: #ff9500;
}

.file-size {
  font-size: 13px;
  color: #86868b;
  flex-shrink: 0;
}

.added-item {
  border-left: 3px solid #34c759;
}

.modified-item {
  border-left: 3px solid #ff9500;
}

.deleted-item {
  border-left: 3px solid #ff3b30;
  opacity: 0.7;
}

.no-changes {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
}

/* Rotating animation */
@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.rotating {
  animation: rotate 2s linear infinite;
}
</style>


