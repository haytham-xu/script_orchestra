<template>
  <div class="duplicate-finder-container">
    <el-card class="main-card">
      <template #header>
        <div class="card-header">
          <h2>Duplicate Image Finder</h2>
          <span class="subtitle">Find and remove duplicate images using perceptual hashing</span>
        </div>
      </template>

      <!-- Input Section -->
      <div class="input-section">
        <el-input
          v-model="scanPaths"
          type="textarea"
          :rows="3"
          placeholder="/path/to/folder1&#10;/path/to/folder2"
          :disabled="isScanning"
        >
          <template #prepend>Paths</template>
        </el-input>
        <p class="hint">Enter folder paths (one per line or comma-separated). Get path: Right-click folder in Finder → Hold Option → Copy Pathname</p>

        <div class="threshold-section">
          <span class="threshold-label">Similarity Threshold: {{ threshold }}%</span>
          <el-slider
            v-model="threshold"
            :min="80"
            :max="100"
            :disabled="isScanning"
            show-stops
          />
          <p class="hint">Higher = more strict (only very similar images)</p>
        </div>

        <el-button
          type="primary"
          :loading="isScanning"
          :disabled="!scanPaths.trim()"
          @click="startScan"
          class="scan-button"
        >
          {{ isScanning ? 'Scanning...' : 'Start Scan' }}
        </el-button>
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
              <el-button
                size="small"
                type="danger"
                :disabled="!hasSelectedInGroup(group)"
                @click="deleteSelectedInGroup(group, groupIndex)"
              >
                🗑️ Delete Selected ({{ getSelectedCountInGroup(group) }})
              </el-button>
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
                <p class="image-filename" :title="image.file_path">{{ image.file_path.split('/').pop() }}</p>
                <p class="image-path" :title="image.file_path">{{ getRelativePath(image.file_path) }}</p>
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
  </div>
</template>

<script setup lang="ts">
import { CircleCheck } from '@element-plus/icons-vue'
import { useDuplicateFinderView } from './DuplicateFinderView'

const {
  scanPaths,
  threshold,
  isScanning,
  scanProgress,
  scanResult,
  selectedForDelete,
  hasResults,
  startScan,
  toggleFileSelection,
  hasSelectedInGroup,
  getSelectedCountInGroup,
  deleteSelectedInGroup,
  openFolder,
  getImageUrl,
  getRelativePath,
  formatFileSize
} = useDuplicateFinderView()
</script>

<style scoped>
.duplicate-finder-container {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.main-card {
  margin-bottom: 20px;
}

.card-header {
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
  gap: 16px;
}

.hint {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.threshold-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.threshold-label {
  font-weight: 500;
  font-size: 14px;
}

.scan-button {
  align-self: flex-start;
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
}

.group-title {
  font-weight: 600;
  font-size: 16px;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.image-item {
  cursor: pointer;
  border: 2px solid transparent;
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.2s;
  background: #fff;
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
  width: 100%;
  height: 200px;
  overflow: hidden;
  background: #f5f7fa;
}

.image-wrapper img {
  width: 100%;
  height: 100%;
  object-fit: cover;
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
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: monospace;
}

.image-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #909399;
}
</style>
