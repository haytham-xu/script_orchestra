<template>
  <div class="duplicate-finder-container">
    <el-card class="main-card">
      <template #header>
        <div class="card-header">
          <div>
            <h2>Duplicate Image Finder</h2>
            <span class="subtitle">Find and remove duplicate images using perceptual hashing</span>
          </div>
          <el-button @click="showWhitelistDrawer = true">⚙️ Settings</el-button>
        </div>
      </template>

      <!-- Input Section -->
      <div class="input-section">
        <!-- Folder Paths Section -->
        <div class="folder-section">
          <div class="folder-header">
            <h3>Scan Folders</h3>
            <el-button size="small" @click="addFolderPath">+ Add Folder</el-button>
          </div>

          <div v-if="settings.folder_paths && settings.folder_paths.length > 0" class="folder-list-edit">
            <div v-for="(path, index) in settings.folder_paths" :key="index" class="folder-item-with-root">
              <el-checkbox
                v-model="selectedFolders"
                :value="path"
                size="large"
                class="folder-checkbox"
              />
              <div class="folder-input-group">
                <el-input
                  v-model="settings.folder_paths[index]"
                  placeholder="Folder Path: /path/to/folder"
                  class="folder-path-input"
                />
                <el-input
                  v-model="settings.folder_root_paths[path]"
                  placeholder="Root Path: /path/to/root"
                  class="root-path-input"
                />
              </div>
              <el-button
                @click="removeFolderPath(index)"
                type="danger"
                size="small"
                :icon="'Delete'"
              >
                Remove
              </el-button>
            </div>
          </div>
          <div v-else class="no-folders">
            <p>No folder paths configured. Click "Add Folder" to add paths.</p>
          </div>
      </div>

      <!-- Exclude Folder Paths Section -->
      <div class="folder-section">
        <div class="folder-header">
          <h3>Exclude Folders</h3>
          <el-button size="small" @click="addExcludeFolderPath">+ Add Exclude Folder</el-button>
        </div>

        <div v-if="settings.exclude_folder_paths && settings.exclude_folder_paths.length > 0" class="folder-list-edit">
          <div v-for="(path, index) in settings.exclude_folder_paths" :key="index" class="folder-item">
            <el-input
              v-model="settings.exclude_folder_paths[index]"
              placeholder="/path/to/exclude/folder"
              style="flex: 1"
            />
            <el-button
              @click="removeExcludeFolderPath(index)"
              type="danger"
              size="small"
              :icon="'Delete'"
            >
              Remove
            </el-button>
          </div>
        </div>
        <div v-else class="no-folders">
          <p>No exclude folders configured.</p>
        </div>
      </div>

      <!-- Scan Button -->
      <div class="action-buttons">
        <el-button
          type="primary"
          size="large"
          :loading="isScanning"
          :disabled="selectedFolders.length === 0"
          @click="startScan"
          class="scan-button"
        >
          {{ isScanning ? 'Scanning...' : `🔍 Scan ${selectedFolders.length} Folder${selectedFolders.length > 1 ? 's' : ''}` }}
        </el-button>

        <el-button
          type="info"
          size="large"
          :loading="isVerifying"
          :disabled="!hasResults || !scanResult"
          @click="verifyAndCleanup"
        >
          {{ isVerifying ? 'Verifying...' : '🔍 Verify & Cleanup' }}
        </el-button>
      </div>
      </div>

      <!-- Progress Section -->
      <div v-if="isScanning" class="progress-section">
        <el-progress
          :percentage="scanProgress.percentage"
          :status="scanProgress.percentage === 100 ? 'success' : undefined"
        />
        <p class="progress-message">{{ scanProgress.message }}</p>
        <p class="progress-count">{{ scanProgress.current }} / {{ scanProgress.total }}</p>
      </div>
    </el-card>

    <!-- Results Section -->
    <div v-if="hasResults && scanResult" class="results-section">
      <!-- Summary Card -->
      <el-card class="summary-card">
        <div class="summary-content">
          <div class="summary-item">
            <span class="summary-label">Total Files Scanned:</span>
            <span class="summary-value">{{ scanResult.total_files }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Duplicate Groups:</span>
            <span class="summary-value highlight">{{ scanResult.duplicate_groups.length }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Total Duplicates:</span>
            <span class="summary-value highlight">{{ scanResult.duplicate_count }}</span>
          </div>
        </div>
      </el-card>

      <!-- Duplicate Groups -->
      <div v-for="(group, groupIndex) in scanResult.duplicate_groups" :key="groupIndex" class="duplicate-group">
        <el-card>
          <template #header>
            <div class="group-header">
              <span class="group-title">Group {{ groupIndex + 1 }} ({{ group.length }} similar images)</span>
              <div class="group-actions">
                <el-button
                  size="small"
                  @click="addGroupToWhitelist(group, groupIndex)"
                >
                  ✅ Add to Whitelist
                </el-button>
                <el-button
                  size="small"
                  type="danger"
                  :disabled="!hasSelectedInGroup(group)"
                  @click="deleteSelectedInGroup(group, groupIndex)"
                >
                  🗑️ Delete Selected ({{ getSelectedCountInGroup(group) }})
                </el-button>
              </div>
            </div>
          </template>

          <div class="image-grid">
            <div
              v-for="(image, imageIndex) in group"
              :key="image.file_path"
              :class="['image-item', { selected: selectedForDelete.has(image.file_path) }]"
              @click="toggleFileSelection(image.file_path)"
            >
              <div class="image-wrapper">
                <img :src="getImageUrl(image.file_path)" :alt="image.file_path" />
                <div v-if="selectedForDelete.has(image.file_path)" class="selected-overlay">
                  <el-icon :size="32"><CircleCheck /></el-icon>
                  <p class="selected-text">DELETE</p>
                </div>
                <div v-if="imageIndex === 0" class="highest-badge">🏆 HIGHEST RESOLUTION</div>
              </div>
              <div class="image-info">
                <p class="image-filename" :title="image.filename || image.file_path.split('/').pop()">
                  {{ image.filename || image.file_path.split('/').pop() }}
                </p>
                <p class="image-path" :title="image.display_path || image.file_path">
                  {{ image.display_path || getRelativePath(image.file_path) }}
                </p>
                <div class="image-meta">
                  <span>{{ image.resolution }}</span>
                  <span>{{ formatFileSize(image.filesize) }}</span>
                </div>
                <el-button
                  size="small"
                  @click.stop="openFolder(image.file_path)"
                  class="open-folder-button"
                >
                  📁 Open Folder
                </el-button>
              </div>
            </div>
          </div>
        </el-card>
      </div>
    </div>

    <!-- No Results -->
    <el-card v-else-if="scanResult && scanResult.duplicate_groups.length === 0" class="no-results-card">
      <el-empty description="No duplicates found">
        <template #image>
          <el-icon :size="64" color="#67c23a"><CircleCheck /></el-icon>
        </template>
      </el-empty>
    </el-card>

    <!-- Settings Drawer -->
    <el-drawer
      v-model="showWhitelistDrawer"
      title="Settings"
      :size="600"
    >
      <div class="whitelist-content">
        <!-- Advanced Settings -->
        <div class="settings-section-drawer">
          <h3>Advanced Settings</h3>

          <div class="setting-item">
            <label>Similarity Threshold: {{ threshold }}%</label>
            <el-slider
              v-model="threshold"
              :min="60"
              :max="100"
              show-stops
            />
            <p class="settings-hint">Higher = more strict (only very similar images). Range: 60%-100%</p>
          </div>

          <div class="setting-item">
            <label>Delete Target Path</label>
            <el-input v-model="settings.delete_target_path" placeholder="/path/to/delete/folder" />
            <p class="settings-hint">Where deleted files will be moved to</p>
          </div>

          <div class="setting-item">
            <label>PHash Database Path</label>
            <el-input v-model="settings.phash_db_path" placeholder="/path/to/phash_cache.db" />
            <p class="settings-hint">Path to the perceptual hash cache database</p>
          </div>

          <div class="setting-item">
            <label>Max CPU Usage: {{ settings.max_cpu_usage_percent || 50 }}%</label>
            <el-slider
              v-model="settings.max_cpu_usage_percent"
              :min="10"
              :max="100"
              :step="10"
              :marks="{ 25: '25%', 50: '50%', 75: '75%', 100: '100%' }"
              show-stops
            />
            <p class="settings-hint">
              Percentage of CPU cores to use for hash computation. Lower values reduce system load.
              Default: 50%
            </p>
          </div>

          <el-button
            type="primary"
            @click="saveAdvancedSettings"
            :loading="isSaving"
            style="margin-top: 12px"
          >
            💾 Save Advanced Settings
          </el-button>
        </div>

        <el-divider />

        <!-- Auto-Selection Rules -->
        <div class="settings-section-drawer">
          <h3>Auto-Selection Rules</h3>
          <p class="settings-hint-text">
            Automatically mark files for deletion based on common patterns
          </p>

          <div class="rule-item">
            <el-checkbox v-model="settings.auto_selection_rules.auto_mark_numbered_copies">
              Auto-mark numbered copies
            </el-checkbox>
            <p class="rule-description">
              Automatically select files like <code>photo(1).jpg</code>, <code>photo(2).jpg</code> for deletion, keeping only <code>photo.jpg</code>
            </p>
          </div>

          <div class="rule-item">
            <el-checkbox v-model="settings.auto_selection_rules.auto_mark_copy_suffix">
              Auto-mark "copy" suffix
            </el-checkbox>
            <p class="rule-description">
              Automatically select files like <code>photo_copy.jpg</code>, <code>photo-copy.jpg</code>, <code>photo copy.jpg</code> for deletion
            </p>
          </div>

          <div class="rule-item">
            <label>Prefer specific folders</label>
            <p class="rule-description">
              Files in these folders will be kept, others marked for deletion
            </p>
            <div v-if="settings.auto_selection_rules.prefer_folders && settings.auto_selection_rules.prefer_folders.length > 0" class="prefer-folders-list">
              <div v-for="(folder, index) in settings.auto_selection_rules.prefer_folders" :key="index" class="prefer-folder-item">
                <el-input
                  v-model="settings.auto_selection_rules.prefer_folders[index]"
                  placeholder="/path/to/preferred/folder"
                />
                <el-button
                  @click="removePreferFolder(index)"
                  type="danger"
                  size="small"
                >
                  Remove
                </el-button>
              </div>
            </div>
            <el-button size="small" @click="addPreferFolder" style="margin-top: 8px">
              + Add Preferred Folder
            </el-button>
          </div>

          <el-button
            type="primary"
            @click="saveAdvancedSettings"
            :loading="isSaving"
            style="margin-top: 12px"
          >
            💾 Save Advanced Settings
          </el-button>
        </div>

        <el-divider />

        <!-- Whitelist Management -->
        <div class="settings-section-drawer">
          <h3>Whitelist Management</h3>
          <p class="whitelist-hint">
            Whitelisted items will be excluded from future duplicate scans.
          </p>

          <el-button
            type="primary"
            @click="loadWhitelist"
            :loading="isLoadingWhitelist"
            style="margin-bottom: 16px"
          >
            🔄 Refresh List
          </el-button>

          <div v-if="whitelist.length > 0" class="whitelist-list">
            <div v-for="(item, index) in whitelist" :key="`${item.filename}-${item.filesize}`" class="whitelist-item">
              <img v-if="item.preview_path" :src="getImageUrl(item.preview_path)" class="whitelist-thumbnail" :alt="item.filename" />
              <div class="whitelist-info">
                <p class="whitelist-filename">{{ item.filename }}</p>
                <p class="whitelist-meta">
                  <span>Size: {{ formatFileSize(item.filesize) }}</span>
                  <span>Added: {{ formatTimestamp(item.added_time) }}</span>
                </p>
                <p v-if="item.note" class="whitelist-note">{{ item.note }}</p>
              </div>
              <el-button
                type="danger"
                size="small"
                @click="removeFromWhitelist(item.filename, item.filesize, index)"
              >
                Remove
              </el-button>
            </div>
          </div>
          <el-empty v-else description="No whitelisted items" />
        </div>

        <el-divider />

        <!-- Database Maintenance -->
        <div class="settings-section-drawer">
          <h3>Database Maintenance</h3>
          <p class="settings-hint-text">
            Clean up database by removing entries for files that no longer exist on disk.
          </p>

          <el-button
            type="warning"
            @click="cleanupDatabase"
            :loading="isCleaning"
            :disabled="!settings.folder_paths || settings.folder_paths.length === 0"
          >
            {{ isCleaning ? 'Cleaning...' : '🧹 Clean Database' }}
          </el-button>

          <p class="settings-hint" style="margin-top: 12px;">
            This will scan all configured folder paths and remove stale database entries. Use this periodically to keep database healthy.
          </p>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { CircleCheck } from '@element-plus/icons-vue'
import { useDuplicateFinderView } from './DuplicateFinderView'

const {
  selectedFolders,
  threshold,
  isScanning,
  isSaving,
  isCleaning,
  scanProgress,
  scanResult,
  selectedForDelete,
  hasResults,
  settings,
  showWhitelistDrawer,
  whitelist,
  isLoadingWhitelist,
  startScan,
  toggleFileSelection,
  hasSelectedInGroup,
  getSelectedCountInGroup,
  deleteSelectedInGroup,
  openFolder,
  getImageUrl,
  getRelativePath,
  formatFileSize,
  saveFolderSettings,
  saveAdvancedSettings,
  addFolderPath,
  removeFolderPath,
  addExcludeFolderPath,
  removeExcludeFolderPath,
  addGroupToWhitelist,
  loadWhitelist,
  removeFromWhitelist,
  formatTimestamp,
  cleanupDatabase,
  addPreferFolder,
  removePreferFolder
} = useDuplicateFinderView()
</script>

<style scoped>
.duplicate-finder-container {
  padding: 20px;
  max-width: 1800px;
  margin: 0 auto;
}

.main-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header > div {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.card-header h2 {
  margin: 0;
  font-size: 24px;
}

.subtitle {
  color: #909399;
  font-size: 14px;
}

/* Input Section */
.input-section {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Settings Section */
.settings-section h3,
.folder-section h3 {
  margin: 0 0 16px 0;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.settings-section {
  padding: 20px;
  background: #f5f7fa;
  border-radius: 8px;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
}

.setting-item label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  font-size: 14px;
  color: #606266;
}

.settings-hint {
  margin: 4px 0 0 0;
  font-size: 12px;
  color: #909399;
}

/* Folder Section */
.folder-section {
  padding: 20px;
  background: #f5f7fa;
  border-radius: 8px;
}

.folder-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.folder-list-edit {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.folder-item-with-root {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px;
  background: white;
  border-radius: 6px;
  border: 1px solid #dcdfe6;
}

.folder-checkbox {
  flex: 0 0 auto;
  margin: 0;
}

.folder-input-group {
  flex: 1;
  display: flex;
  gap: 12px;
}

.folder-path-input {
  flex: 1;
  min-width: 0;
}

.root-path-input {
  flex: 1;
  min-width: 0;
}

/* Remove old styles that are no longer used */
.folder-row {
  display: none;
}

.folder-label {
  display: none;
}

.root-path-row {
  display: none;
}

.root-path-label {
  display: none;
}

.folder-item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px;
  background: white;
  border-radius: 6px;
  border: 1px solid #dcdfe6;
}

.folder-item .el-checkbox {
  flex: 1;
  margin: 0;
}

.folder-item .el-checkbox :deep(.el-checkbox__label) {
  width: 100%;
  overflow: visible;
}

.folder-item .el-input {
  margin-left: 8px;
  flex: 1;
}

.no-folders {
  padding: 16px;
  text-align: center;
  background: white;
  border-radius: 6px;
  color: #909399;
  margin-bottom: 0;
}

.no-folders p {
  margin: 0;
  font-size: 13px;
}

.hint {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.action-buttons {
  display: flex;
  gap: 12px;
  align-items: center;
}

.scan-button {
  flex: 0 0 auto;
}

/* Progress Section */
.progress-section {
  margin-top: 20px;
  padding: 20px;
  background: #f5f7fa;
  border-radius: 8px;
}

.progress-message {
  margin-top: 12px;
  margin-bottom: 4px;
  font-size: 14px;
  color: #606266;
}

.progress-count {
  margin: 0;
  font-size: 13px;
  color: #909399;
}

/* Results Section */
.results-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tips-card {
  background: #f0f9ff;
  border: 1px solid #409eff;
}

.tips-card h3 {
  margin: 0;
  font-size: 16px;
  color: #409eff;
}

.tips-list {
  margin: 8px 0 0 0;
  padding-left: 20px;
  list-style: disc;
}

.tips-list li {
  margin: 8px 0;
  font-size: 14px;
  line-height: 1.6;
}

.summary-card {
  position: sticky;
  top: 0;
  z-index: 10;
}

.summary-content {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-label {
  font-size: 13px;
  color: #909399;
}

.summary-value {
  font-size: 24px;
  font-weight: 600;
}

.summary-value.highlight {
  color: #409eff;
}

.summary-value.warning {
  color: #f56c6c;
}

.delete-button {
  width: 100%;
}

.no-results-card {
  margin-top: 20px;
}

/* Duplicate Groups */
.duplicate-group {
  margin-bottom: 16px;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.group-actions {
  display: flex;
  gap: 8px;
}

.group-title {
  font-weight: 600;
  font-size: 16px;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 16px;
}

.image-item {
  cursor: pointer;
  border: 2px solid transparent;
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.2s;
  background: #fff;
  width: 400px;
}

.image-item:hover {
  border-color: #409eff;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.image-item.selected {
  border-color: #f56c6c;
  background: #fef0f0;
}

.image-item.first {
  border-color: #67c23a;
}

.image-wrapper {
  position: relative;
  width: 400px;
  height: 300px;
  overflow: hidden;
  background: #f5f7fa;
}

.image-wrapper img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.selected-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(245, 108, 108, 0.7);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: white;
}

.selected-text {
  margin: 8px 0 0 0;
  font-size: 16px;
  font-weight: 700;
}

.highest-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: #67c23a;
  color: white;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.first-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: #67c23a;
  color: white;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.image-info {
  padding: 12px;
}

.image-filename {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.image-path {
  margin: 0 0 8px 0;
  font-size: 11px;
  color: #909399;
  word-break: break-all;
  line-height: 1.4;
  max-height: 2.8em;
  overflow: hidden;
  font-family: monospace;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.image-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #909399;
}

/* Settings Drawer */
.whitelist-content {
  padding: 0 20px;
}

.settings-section-drawer {
  margin-bottom: 24px;
}

.settings-section-drawer h3 {
  margin: 0 0 16px 0;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.settings-section-drawer .setting-item {
  margin-bottom: 20px;
}

.settings-section-drawer .setting-item label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  font-size: 14px;
  color: #606266;
}

.settings-hint-text {
  margin: 0 0 16px 0;
  padding: 12px;
  background: #f0f9ff;
  border-radius: 6px;
  color: #606266;
  font-size: 14px;
}

.rule-item {
  margin-bottom: 20px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}

.rule-item label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  font-size: 14px;
  color: #606266;
}

.rule-description {
  margin: 8px 0 0 24px;
  font-size: 13px;
  color: #909399;
  line-height: 1.5;
}

.rule-description code {
  padding: 2px 6px;
  background: #e4e7ed;
  border-radius: 3px;
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 12px;
  color: #303133;
}

.prefer-folders-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.prefer-folder-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

.prefer-folder-item .el-input {
  flex: 1;
}

.whitelist-hint {
  margin: 0 0 16px 0;
  padding: 12px;
  background: #f0f9ff;
  border-radius: 6px;
  color: #606266;
  font-size: 14px;
}

.whitelist-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.whitelist-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  border: 1px solid #dcdfe6;
}

.whitelist-thumbnail {
  width: 80px;
  height: 60px;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
}

.whitelist-info {
  flex: 1;
  margin-right: 16px;
}

.whitelist-filename {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.whitelist-meta {
  margin: 0 0 4px 0;
  font-size: 12px;
  color: #909399;
  display: flex;
  gap: 16px;
}

.whitelist-note {
  margin: 0;
  font-size: 13px;
  color: #606266;
  font-style: italic;
}
</style>
