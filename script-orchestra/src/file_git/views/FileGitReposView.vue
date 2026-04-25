<template>
  <div class="file-git-repos-container">
    <!-- Header -->
    <el-card class="header-card">
      <div class="header-content">
        <div class="title-section">
          <h2>File-Git Repositories</h2>
          <p class="subtitle">Encrypted cloud backup with git-style operations</p>
        </div>
        <div class="header-actions">
          <el-button :icon="Setting" @click="goToSettings">
            Settings
          </el-button>
          <el-button @click="openImportDialog" :icon="FolderOpened">
            Import Existing
          </el-button>
          <el-button type="primary" @click="openAddDialog" :icon="Plus">
            Add Repository
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- Repository List -->
    <el-card v-loading="isLoading" class="repos-list-card">
      <div v-if="repos.length === 0" class="empty-state">
        <el-empty description="No repositories yet">
          <el-button type="primary" @click="openAddDialog">Add Your First Repository</el-button>
        </el-empty>
      </div>

      <div v-else class="repos-grid">
        <el-card
          v-for="repo in repos"
          :key="repo.id"
          class="repo-card"
          shadow="hover"
          @click="goToRepo(repo.id)"
        >
          <div class="repo-header">
            <div class="repo-title">
              <el-icon class="repo-icon"><FolderOpened /></el-icon>
              <span class="repo-name">{{ repo.name }}</span>
            </div>
            <div class="repo-actions" @click.stop>
              <el-button
                type="primary"
                size="small"
                :icon="FolderOpened"
                @click="openFolder(repo.id)"
                circle
                title="Open Folder"
              />
              <el-button
                type="danger"
                size="small"
                :icon="Delete"
                @click="openDeleteDialog(repo)"
                circle
                title="Delete Repository"
              />
            </div>
          </div>

          <div class="repo-info">
            <div class="info-row">
              <span class="info-label">Path:</span>
              <span class="info-value">{{ repo.local_path }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Mode:</span>
              <el-tag :type="repo.mode === 'ENCRYPTED' ? 'success' : 'info'" size="small">
                {{ repo.mode }}
              </el-tag>
            </div>
            <div class="info-row">
              <span class="info-label">Status:</span>
              <el-tag
                :type="
                  repo.status === 'ready'
                    ? 'success'
                    : repo.status === 'syncing'
                    ? 'warning'
                    : 'danger'
                "
                size="small"
              >
                {{
                  repo.status === 'ready'
                    ? 'Ready'
                    : repo.status === 'syncing'
                    ? 'Syncing'
                    : 'Error'
                }}
              </el-tag>
            </div>
            <div class="info-row">
              <span class="info-label">Updated:</span>
              <span class="info-value">{{ new Date(repo.last_updated).toLocaleString() }}</span>
            </div>
          </div>
        </el-card>
      </div>
    </el-card>

    <!-- Add Repository Dialog -->
    <el-dialog
      v-model="showAddDialog"
      title="Add New Repository"
      width="520px"
      :close-on-click-modal="false"
      class="apple-dialog"
    >
      <div class="dialog-content">
        <div class="form-group">
          <label class="form-label">Folder Path</label>
          <el-input
            v-model="newRepoPath"
            placeholder="/absolute/path/to/folder"
            size="large"
            clearable
          />
          <p class="form-description">Enter the absolute path to the folder you want to backup</p>
        </div>

        <div class="form-group">
          <label class="form-label">Mode</label>
          <el-radio-group v-model="newRepoMode" size="large" class="mode-radio-group">
            <el-radio-button value="ENCRYPTED">Encrypted (Recommended)</el-radio-button>
            <el-radio-button value="ORIGINAL">Original</el-radio-button>
          </el-radio-group>
          <p class="form-description warning">
            ⚠️ Mode cannot be changed after creation
          </p>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button size="large" @click="showAddDialog = false">Cancel</el-button>
          <el-button size="large" type="primary" @click="addRepo">Add Repository</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Import Existing Repository Dialog -->
    <el-dialog
      v-model="showImportDialog"
      title="Import Existing Repository"
      width="520px"
      :close-on-click-modal="false"
      class="apple-dialog"
    >
      <div class="dialog-content">
        <div class="info-box">
          <div class="info-icon">ℹ️</div>
          <div class="info-text">
            <h4>Import existing File-Git repository</h4>
            <p>
              This will import a folder that already has a <code>.fgit</code> directory.
              The mode (ENCRYPTED/ORIGINAL) will be automatically detected from the existing configuration.
            </p>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Folder Path</label>
          <el-input
            v-model="importRepoPath"
            placeholder="/path/to/existing/repo"
            size="large"
            clearable
          />
          <p class="form-description">Path to a folder that already contains a .fgit directory</p>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button size="large" @click="showImportDialog = false">Cancel</el-button>
          <el-button size="large" type="primary" @click="importRepo">Import Repository</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Delete Confirmation Dialog -->
    <el-dialog
      v-model="showDeleteDialog"
      title="Delete Repository"
      width="520px"
      :close-on-click-modal="false"
      class="apple-dialog"
    >
      <div class="dialog-content">
        <div class="warning-box">
          <div class="warning-icon">⚠️</div>
          <div class="warning-text">
            <h4>This action cannot be undone</h4>
            <p>
              Deleting this repository will remove it from the registry, but the
              <code>.fgit</code> folder and your files will NOT be deleted.
            </p>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Repository Name</label>
          <el-input :value="deleteRepoName" size="large" disabled />
        </div>

        <div class="form-group">
          <label class="form-label">Confirm Deletion</label>
          <el-input
            v-model="deleteConfirmInput"
            :placeholder="`Type '${deleteRepoName}' to confirm`"
            size="large"
            clearable
          />
          <p class="form-description">Type the repository name exactly to confirm deletion</p>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button size="large" @click="showDeleteDialog = false">Cancel</el-button>
          <el-button
            size="large"
            type="danger"
            @click="deleteRepo"
            :disabled="deleteConfirmInput !== deleteRepoName"
          >
            Delete Repository
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { Plus, Delete, FolderOpened, Setting } from '@element-plus/icons-vue'
import { useFileGitReposView } from './FileGitReposView'

const {
  repos,
  isLoading,
  showAddDialog,
  showImportDialog,
  showDeleteDialog,
  newRepoPath,
  newRepoMode,
  importRepoPath,
  deleteRepoName,
  deleteConfirmInput,
  openAddDialog,
  openImportDialog,
  addRepo,
  importRepo,
  openDeleteDialog,
  deleteRepo,
  goToRepo,
  openFolder,
  goToSettings
} = useFileGitReposView()
</script>

<style scoped>
.file-git-repos-container {
  padding: 20px;
  max-width: 100vw;
  overflow-x: hidden;
  min-height: 100vh;
  height: 100vh;
  background: #f5f5f7;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}

.header-card {
  margin-bottom: 16px;
  border-radius: 12px;
  border: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  flex-shrink: 0;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title-section h2 {
  margin: 0;
  font-size: 28px;
  font-weight: 600;
  color: #1d1d1f;
  letter-spacing: -0.5px;
}

.subtitle {
  margin: 8px 0 0 0;
  color: #86868b;
  font-size: 15px;
  font-weight: 400;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.repos-list-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  border: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}

.repos-list-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
}

.repos-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 20px;
  width: 100%;
}

.repo-card {
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  border-radius: 12px;
  border: 1px solid #e5e5e7;
  background: #ffffff;
}

.repo-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  border-color: #d2d2d7;
}

.repo-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f5f5f7;
}

.repo-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.repo-icon {
  font-size: 26px;
  color: #007aff;
}

.repo-name {
  font-size: 19px;
  font-weight: 600;
  color: #1d1d1f;
  letter-spacing: -0.3px;
}

.repo-actions {
  display: flex;
  gap: 8px;
}

.repo-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.info-label {
  font-weight: 500;
  color: #86868b;
  min-width: 70px;
  font-size: 14px;
}

.info-value {
  color: #1d1d1f;
  font-size: 14px;
  word-break: break-all;
}

/* Apple-style Dialog */
.apple-dialog :deep(.el-dialog) {
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.apple-dialog :deep(.el-dialog__header) {
  padding: 24px 24px 16px;
  border-bottom: 1px solid #f5f5f7;
}

.apple-dialog :deep(.el-dialog__title) {
  font-size: 20px;
  font-weight: 600;
  color: #1d1d1f;
  letter-spacing: -0.3px;
}

.apple-dialog :deep(.el-dialog__body) {
  padding: 24px;
}

.apple-dialog :deep(.el-dialog__footer) {
  padding: 16px 24px 24px;
  border-top: 1px solid #f5f5f7;
}

.dialog-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 14px;
  font-weight: 600;
  color: #1d1d1f;
  letter-spacing: -0.1px;
}

.form-description {
  font-size: 13px;
  color: #86868b;
  margin: 4px 0 0 0;
  line-height: 1.4;
}

.form-description.warning {
  color: #ff9500;
  font-weight: 500;
}

.mode-radio-group {
  width: 100%;
}

.mode-radio-group :deep(.el-radio-button) {
  flex: 1;
}

.mode-radio-group :deep(.el-radio-button__inner) {
  width: 100%;
  border-radius: 8px;
  padding: 12px 20px;
  font-size: 15px;
  font-weight: 500;
}

.info-box {
  display: flex;
  gap: 12px;
  padding: 12px 14px;
  background: #f0f9ff;
  border-radius: 8px;
  border: 1px solid #cce5ff;
}

.info-icon {
  font-size: 20px;
  flex-shrink: 0;
  line-height: 1.2;
}

.info-text h4 {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
  color: #1d1d1f;
  line-height: 1.3;
}

.info-text p {
  margin: 0;
  font-size: 13px;
  color: #86868b;
  line-height: 1.4;
}

.info-text code {
  background-color: #f5f5f7;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'SF Mono', Monaco, 'Courier New', monospace;
  font-size: 13px;
  color: #1d1d1f;
}

.warning-box {
  display: flex;
  gap: 12px;
  padding: 12px 14px;
  background: #fff9f0;
  border-radius: 8px;
  border: 1px solid #ffe5cc;
}

.warning-icon {
  font-size: 20px;
  flex-shrink: 0;
  line-height: 1.2;
}

.warning-text h4 {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
  color: #1d1d1f;
  line-height: 1.3;
}

.warning-text p {
  margin: 0;
  font-size: 13px;
  color: #86868b;
  line-height: 1.4;
}

.warning-text code {
  background-color: #f5f5f7;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'SF Mono', Monaco, 'Courier New', monospace;
  font-size: 13px;
  color: #1d1d1f;
}

.dialog-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.dialog-footer .el-button {
  min-width: 120px;
  border-radius: 8px;
  font-weight: 500;
}
</style>
