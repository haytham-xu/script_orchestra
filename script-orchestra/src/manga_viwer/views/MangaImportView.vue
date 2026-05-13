<template>
  <div class="import-root">
    <!-- Left Panel: Current folder to import (1/3) -->
    <div class="left-panel">
      <div v-if="!currentFolder" class="scan-prompt">
        <h2>Import New Manga</h2>
        <p class="scan-info">Scanning from: <strong>{{ scanPath || 'Loading...' }}</strong></p>
        <div class="scan-actions">
          <el-button type="primary" size="large" @click="handleScan" :loading="scanning">
            🔍 Scan Now
          </el-button>
          <el-button size="large" @click="goBack">
            ← Back
          </el-button>
        </div>
        <div v-if="folders.length > 0" class="scan-result">
          Found {{ folders.length }} folders ready to import
        </div>
      </div>

      <div v-else class="folder-display">
        <!-- Full images display (scrollable) - Pure preview -->
        <div class="images-container">
          <template v-for="(item, i) in currentFolderImagesWithPdf" :key="item.url">
            <!-- Regular Image -->
            <img
              v-if="item.type === 'image'"
              :src="item.url"
              class="full-image"
            />
            <!-- PDF Pages -->
            <template v-else-if="item.type === 'pdf'">
              <!-- Show rendered pages if available -->
              <template v-if="item.pdfPages && item.pdfPages.length > 0">
                <img
                  v-for="(page, pageIdx) in item.pdfPages"
                  :key="`${item.url}-page-${pageIdx}`"
                  :src="page"
                  class="full-image"
                />
              </template>
              <!-- Show placeholder while loading or if not rendered yet -->
              <div v-else class="pdf-placeholder">
                <div class="pdf-icon">📄</div>
                <div class="pdf-text">PDF - Rendering...</div>
              </div>
            </template>
            <!-- Video -->
            <video
              v-else-if="item.type === 'video'"
              :src="item.url"
              class="full-video"
              controls
              preload="metadata"
            ></video>
          </template>
        </div>
      </div>
    </div>

    <!-- Middle Panel: Current folder info + comparison (1/3) -->
    <div class="middle-panel">
      <!-- Fixed Header Section -->
      <div v-if="currentFolder" class="middle-panel-header">
        <!-- Current folder header (moved from left panel) -->
        <div class="current-folder-header">
          <div class="classify-row top-info">
            <div class="classify-section compact" style="flex: 1;">
              <div class="classify-label">Folder Name</div>
              <el-input v-model="formData.name" size="small" />
            </div>
            <div class="classify-section compact" style="width: 70px;">
              <div class="classify-label">Files</div>
              <div class="info-value">{{ currentFolder.number }}</div>
            </div>
            <div class="classify-section compact" style="width: 70px;">
              <div class="classify-label">Size</div>
              <div class="info-value">{{ currentFolder.size ? Math.round(currentFolder.size / 1024 / 1024) : 0 }}MB</div>
            </div>
            <div class="classify-section compact" style="width: 60px;">
              <div class="classify-label">Progress</div>
              <div class="info-value">{{ currentIndex + 1 }}/{{ folders.length }}</div>
            </div>
          </div>
        </div>

        <!-- Classify Panel (moved from left panel) -->
        <div class="classify-panel">
        <!-- Category Main & Mosaic (one row) -->
        <div class="classify-row">
          <div class="classify-section-inline" style="flex: 1;">
            <span class="classify-label">Category Main:</span>
            <el-radio-group v-model="formData.category_main" size="small">
              <el-radio v-for="cat in categoryMainOptions" :key="cat.id" :label="cat.id">{{ cat.label || cat.id }}</el-radio>
            </el-radio-group>
          </div>
          <div class="classify-section-inline" style="width: 150px;">
            <span class="classify-label">Mosaic:</span>
            <el-radio-group v-model="formData.mosaic" size="small">
              <el-radio label="true">✓</el-radio>
              <el-radio label="false">✗</el-radio>
            </el-radio-group>
          </div>
        </div>

        <!-- Category Sub -->
        <div class="classify-section-inline">
          <span class="classify-label">Category Sub:</span>
          <el-radio-group v-model="formData.category_sub" size="small" class="category-sub-radio-group">
            <el-radio v-for="cat in categorySubOptions" :key="cat.id" :label="cat.id">{{ cat.label || cat.id }}</el-radio>
          </el-radio-group>
        </div>

        <!-- Tags: inline layout (label + tags in same row) -->
        <div class="tags-section">
          <div class="classify-section-inline">
            <span class="classify-label">Auth:</span>
            <div class="tags-list-mini">
              <el-tag
                v-for="(t, i) in formData.auth"
                :key="i"
                closable
                @close="formData.auth.splice(i, 1)"
                size="small"
                type="primary"
              >
                {{ t }}
              </el-tag>
              <el-input
                v-if="showAuthInput"
                v-model="authInput"
                size="small"
                @keyup.enter="addAuth"
                @blur="addAuth"
                style="width: 60px;"
              />
              <el-button v-else size="small" @click="showAuthInput = true">+</el-button>
            </div>
          </div>

          <div class="classify-section-inline">
            <span class="classify-label">Name:</span>
            <div class="tags-list-mini">
              <el-tag
                v-for="(t, i) in formData.name_tags"
                :key="i"
                closable
                @close="formData.name_tags.splice(i, 1)"
                size="small"
                type="success"
              >
                {{ t }}
              </el-tag>
              <el-input
                v-if="showNameInput"
                v-model="nameInput"
                size="small"
                @keyup.enter="addName"
                @blur="addName"
                style="width: 60px;"
              />
              <el-button v-else size="small" @click="showNameInput = true">+</el-button>
            </div>
          </div>

          <div class="classify-section-inline">
            <span class="classify-label">Custom:</span>
            <div class="tags-list-mini">
              <el-tag
                v-for="(t, i) in formData.custom"
                :key="i"
                closable
                @close="formData.custom.splice(i, 1)"
                size="small"
                type="warning"
              >
                {{ t }}
              </el-tag>
              <el-input
                v-if="showCustomInput"
                v-model="customInput"
                size="small"
                @keyup.enter="addCustom"
                @blur="addCustom"
                style="width: 60px;"
              />
              <el-button v-else size="small" @click="showCustomInput = true">+</el-button>
            </div>
          </div>

          <div class="classify-section-inline">
            <span class="classify-label">Others:</span>
            <div class="tags-list-mini">
              <el-tag
                v-for="(t, i) in formData.others"
                :key="i"
                closable
                @close="formData.others.splice(i, 1)"
                size="small"
                type="danger"
              >
                {{ t }}
              </el-tag>
              <el-input
                v-if="showOthersInput"
                v-model="othersInput"
                size="small"
                @keyup.enter="addOthers"
                @blur="addOthers"
                style="width: 60px;"
              />
              <el-button v-else size="small" @click="showOthersInput = true">+</el-button>
            </div>
          </div>
        </div>

        <!-- Action Buttons at bottom -->
        <div class="action-buttons-row">
          <el-button
            @click="prevFolder"
            :disabled="currentIndex === 0"
            size="small"
            style="flex: 1;"
          >
            ← Prev
          </el-button>
          <el-button
            @click="nextFolder"
            :disabled="currentIndex === folders.length - 1"
            size="small"
            style="flex: 1;"
          >
            Next →
          </el-button>
          <el-button
            type="danger"
            @click="handleDelete"
            :loading="deleting"
            size="small"
            style="flex: 1.5;"
          >
            Delete
          </el-button>
          <el-button
            type="primary"
            @click="handleImport"
            :loading="importing"
            :disabled="!formData.category_main || !formData.category_sub"
            size="small"
            style="flex: 2;"
          >
            Import
          </el-button>
        </div>
      </div>
      </div>

      <!-- Scrollable Content Section -->
      <div class="middle-panel-content">
        <!-- Comparison folder section -->
        <div v-if="!middleFolder" class="empty-state">
        <p>👈 Click a folder from the right panel to compare</p>
      </div>

      <div v-else class="folder-display">
        <!-- Full images display (scrollable) -->
        <div class="images-container">
          <template v-for="(item, i) in middleFilesWithPdf" :key="item.url">
            <!-- Regular Image -->
            <img
              v-if="item.type === 'image'"
              :src="item.url"
              class="full-image"
            />
            <!-- PDF Pages -->
            <template v-else-if="item.type === 'pdf'">
              <!-- Show rendered pages if available -->
              <template v-if="item.pdfPages && item.pdfPages.length > 0">
                <img
                  v-for="(page, pageIdx) in item.pdfPages"
                  :key="`${item.url}-page-${pageIdx}`"
                  :src="page"
                  class="full-image"
                />
              </template>
              <!-- Show placeholder while loading or if not rendered yet -->
              <div v-else class="pdf-placeholder">
                <div class="pdf-icon">📄</div>
                <div class="pdf-text">PDF - Rendering...</div>
              </div>
            </template>
            <!-- Video -->
            <video
              v-else-if="item.type === 'video'"
              :src="item.url"
              class="full-video"
              controls
              preload="metadata"
            ></video>
          </template>
        </div>
      </div>
      </div>
    </div>

    <!-- Right Panel: Manga Viewer (browsable) (1/3) -->
    <div class="right-panel">
      <!-- Fixed Header Section -->
      <div class="right-panel-header">
        <div class="viewer-header">
          <div class="header-left">
            <el-button type="default" size="small" @click="goBack">← Back</el-button>
            <!-- Name Parts (clickable) -->
            <div class="name-parts-inline" v-if="currentFolder && nameParts.length > 0">
              <el-tag
                v-for="(part, i) in nameParts"
                :key="i"
                @click="addToRightSearch(part)"
                size="small"
                style="cursor: pointer;"
              >
                {{ part }}
              </el-tag>
            </div>
          </div>
          <el-button size="small" @click="refreshRightPanel">🔄</el-button>
        </div>

        <!-- Search Input & Tokens -->
        <div class="search-section">
          <el-input
            v-model="rightSearchInput"
            placeholder="Search..."
            size="small"
            @keyup.enter="addRightSearchToken"
            style="flex: 1; max-width: 300px;"
          >
            <template #append>
              <el-button @click="addRightSearchToken">Search</el-button>
            </template>
          </el-input>
        </div>

        <div class="search-tokens" v-if="rightSearchTokens.length > 0">
          <el-tag
            v-for="(token, i) in rightSearchTokens"
            :key="i"
            closable
            @close="removeRightSearchToken(i)"
            size="small"
          >
            {{ token }}
          </el-tag>
          <el-button
            size="small"
            @click="clearRightSearch"
          >
            Clear All
          </el-button>
        </div>
      </div>

      <!-- Scrollable Content Section -->
      <div class="right-panel-content" @scroll="onRightScroll">
        <!-- Folder cards (manga viewer style) -->
        <div class="folder-list" v-loading="loadingRight">
        <div
          v-for="f in rightDisplayedFolders"
          :key="f.id"
          class="folder-line"
        >
          <!-- Left: Info -->
          <div class="line-left">
            <div class="name-row">
              <div class="name-cell" :title="f.name">{{ f.name }}</div>
              <div class="action-buttons">
                <el-button size="small" type="primary" @click="copyCardToForm(f)" title="Copy tags to left form">
                  📋 Copy
                </el-button>
              </div>
            </div>

            <div class="tags-row">
              <div class="tags-group">
                <span class="label">Size:</span>
                <span class="value">{{ Math.round(f.size / 1024 / 1024) }} MB</span>
              </div>
              <div class="tags-group">
                <span class="label">Number:</span>
                <span class="value">{{ f.number }}</span>
              </div>
              <div class="tags-group">
                <span class="label">Mosaic:</span>
                <span class="value">{{ f.tags.mosaic }}</span>
              </div>
              <div class="tags-group">
                <span class="label">Category:</span>
                <el-tag size="small">{{ f.tags.category_main }}</el-tag>
                <el-tag size="small" type="success">{{ f.tags.category_sub }}</el-tag>
              </div>

              <div class="tags-group" v-if="f.tags.auth && f.tags.auth.length > 0">
                <span class="label">Auth:</span>
                <el-tag type="primary" v-for="(t, i) in f.tags.auth" :key="'auth-' + i" size="small">{{ t }}</el-tag>
              </div>

              <div class="tags-group" v-if="f.tags.name && f.tags.name.length > 0">
                <span class="label">Name:</span>
                <el-tag type="success" v-for="(t, i) in f.tags.name" :key="'name-' + i" size="small">{{ t }}</el-tag>
              </div>

              <div class="tags-group" v-if="f.tags.custom && f.tags.custom.length > 0">
                <span class="label">Custom:</span>
                <el-tag type="warning" v-for="(t, i) in f.tags.custom" :key="'custom-' + i" size="small">{{ t }}</el-tag>
              </div>

              <div class="tags-group" v-if="f.tags.others && f.tags.others.length > 0">
                <span class="label">Others:</span>
                <el-tag type="danger" v-for="(t, i) in f.tags.others" :key="'others-' + i" size="small">{{ t }}</el-tag>
              </div>
            </div>
          </div>

          <!-- Right: Preview -->
          <div class="line-right" @click="selectMiddleFolder(f)">
            <div v-if="rightPreviewImages(f).length > 0" class="thumbs">
              <div v-for="(item, i) in rightPreviewImages(f)" :key="i" class="thumb">
                <img v-if="item.type === 'image'" :src="item.url" />
                <img v-else-if="item.type === 'pdf' && rightPdfPreviews[item.url]" :src="rightPdfPreviews[item.url]" />
                <div v-else-if="item.type === 'pdf'" class="pdf-loading">PDF</div>
              </div>
            </div>
            <div v-else class="no-thumb">无图片预览</div>
          </div>
        </div>
        </div>

        <!-- Loading indicator for infinite scroll -->
        <div v-if="loadingRight" class="loading-more">
          Loading...
        </div>
        <div v-else-if="!rightCanLoadMore && rightDisplayedFolders.length > 0" class="no-more">
          No more results
        </div>
        <div v-else-if="rightDisplayedFolders.length === 0 && !loadingRight" class="no-more">
          No results found
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" src="@/manga_viwer/views/MangaImportView.ts"></script>

<style scoped>
.import-root {
  display: flex;
  height: 100vh;
  overflow: hidden;
  position: relative;
}

/* Left Panel (1/3) */
.left-panel {
  width: 33.33%;
  flex-shrink: 0;
  overflow-y: auto;
  background: #fafbfc;
  display: flex;
  flex-direction: column;
  border-right: 2px solid #e3e7ec;
}

.scan-prompt {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 20px;
  padding: 40px;
}

.scan-prompt h2 {
  margin: 0;
  color: #313c4c;
}

.scan-info {
  font-size: 14px;
  color: #606266;
  margin: 0;
}

.scan-info strong {
  color: #409eff;
  word-break: break-all;
}

.scan-actions {
  display: flex;
  gap: 12px;
}

.scan-result {
  margin-top: 20px;
  padding: 12px 24px;
  background: #e7f5ff;
  border: 1px solid #409eff;
  border-radius: 8px;
  color: #409eff;
  font-weight: 600;
}

.folder-display {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.folder-header {
  position: sticky;
  top: 0;
  background: #fff;
  border-bottom: 2px solid #e3e7ec;
  padding: 15px 20px;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.folder-title h2 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: #313c4c;
}

.folder-meta {
  display: flex;
  gap: 15px;
  font-size: 13px;
  color: #606266;
}

.folder-progress {
  font-weight: 600;
  color: #409eff;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.images-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
}

.full-image {
  max-width: 100%;
  width: auto;
  height: auto;
  display: block;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.pdf-placeholder {
  width: 100%;
  min-height: 300px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  border: 2px dashed #dcdfe6;
  border-radius: 8px;
  margin: 10px 0;
}

.pdf-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.pdf-text {
  color: #909399;
  font-size: 14px;
}

.full-video {
  max-width: 100%;
  width: auto;
  height: auto;
  display: block;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* Classify Panel (in left panel) */
.classify-panel {
  padding: 12px 15px;
  background: #fff;
  border-bottom: 2px solid #e3e7ec;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 35vh;
  overflow-y: auto;
}

.classify-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.classify-section.compact {
  gap: 2px;
}

.classify-section-inline {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.classify-label {
  font-size: 10px;
  font-weight: 600;
  color: #606266;
  flex-shrink: 0;
}

.classify-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.classify-row.top-info {
  align-items: flex-end;
}

.info-value {
  font-size: 12px;
  font-weight: 500;
  color: #313c4c;
  padding: 4px 8px;
  background: #f0f4f8;
  border-radius: 4px;
  text-align: center;
}

.action-buttons-row {
  display: flex;
  gap: 8px;
  margin-top: auto;
  padding-top: 8px;
}

.tags-section {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.tags-section .classify-section-inline {
  flex: 1 1 auto;
  min-width: 0;
}

.tags-list-mini {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  align-items: center;
  flex: 1;
  min-width: 0;
}

.category-sub-radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  flex: 1;
}

.category-sub-radio-group :deep(.el-radio) {
  margin-right: 0;
}

.category-sub-radio-group :deep(.el-radio__label) {
  font-size: 11px;
  padding-left: 4px;
}

/* Middle Panel (1/3) */
.middle-panel {
  width: 33.33%;
  flex-shrink: 0;
  background: #f5f7fa;
  display: flex;
  flex-direction: column;
  border-right: 2px solid #e3e7ec;
  overflow: hidden;
}

.middle-panel-header {
  flex-shrink: 0;
  background: #fff;
  border-bottom: 2px solid #e3e7ec;
  z-index: 10;
}

.middle-panel-content {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.current-folder-header {
  background: #fff;
  padding: 12px 15px;
}

.comparison-header {
  border-top: 2px solid #409eff;
}

.comparison-header h3 {
  font-size: 16px;
  color: #409eff;
  margin: 0;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 40px;
  text-align: center;
}

.empty-state p {
  font-size: 16px;
  color: #909399;
  margin: 0;
}

/* Right Panel (1/3) */
.right-panel {
  width: 33.33%;
  flex-shrink: 0;
  background: #fff;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.right-panel-header {
  flex-shrink: 0;
  padding: 15px;
  background: #fff;
  border-bottom: 2px solid #e3e7ec;
  display: flex;
  flex-direction: column;
  gap: 12px;
  z-index: 10;
}

.right-panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 15px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.viewer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 10px;
  border-bottom: 1px solid #e3e7ec;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.name-parts-inline {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.search-section {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.search-tokens {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.folder-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 200px;
}

.loading-more,
.no-more {
  padding: 20px;
  text-align: center;
  color: #909399;
  font-size: 14px;
}

.folder-line {
  display: flex;
  flex-direction: row;
  gap: 18px;
  border: 1px solid #e3e7ec;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 2px 6px -2px rgba(40, 48, 63, .12);
  transition: all 0.2s;
}

.folder-line:hover {
  box-shadow: 0 4px 14px -4px rgba(40, 48, 63, .22);
}

.line-left {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 15px;
  margin: 0;
}

.line-right {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  min-width: 0;
  margin-right: 15px;
  cursor: pointer;
}

.name-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.name-cell {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
  color: #313c4c;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.action-buttons {
  flex-shrink: 0;
}

.tags-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tags-group {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.label {
  font-size: 11px;
  font-weight: 600;
  color: #66717d;
  flex-shrink: 0;
}

.value {
  font-size: 11px;
  color: #3f4c5a;
}

.thumbs {
  display: flex;
  flex-direction: row;
  gap: 8px;
  align-items: center;
  height: 180px;
  max-width: 360px;
}

.thumb {
  height: 180px;
  width: auto;
  max-width: 120px;
  flex: 0 0 auto;
  border: 1px solid #d9e1e8;
  border-radius: 10px;
  overflow: hidden;
  background: #fafbfc;
  display: flex;
  align-items: center;
  justify-content: center;
}

.thumb img {
  max-height: 180px;
  max-width: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
  display: block;
}

.no-thumb {
  font-size: 11px;
  color: #7d8590;
  padding: 6px 10px;
  background: #f5f7fa;
  border: 1px dashed #d3d9df;
  border-radius: 8px;
}

.pdf-loading {
  font-size: 11px;
  color: #909399;
  font-weight: 600;
  padding: 4px 8px;
  background: #f0f4f8;
  border-radius: 4px;
}

</style>

