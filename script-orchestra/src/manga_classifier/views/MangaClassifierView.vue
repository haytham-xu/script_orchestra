<template>
  <div>
    <el-container>
      <el-header>
        <span class="mc-title">{{ currentFolderName }}</span>
        <div v-if="!isEmpty" class="mc-progress">
          <input
            v-if="editingIndex"
            ref="indexInputRef"
            v-model="indexInputValue"
            type="number"
            :min="1"
            :max="totalCount"
            class="mc-progress-input"
            @keydown.enter="commitIndexEdit"
            @keydown.esc="cancelIndexEdit"
            @blur="commitIndexEdit"
          />
          <span
            v-else
            class="mc-progress-index"
            title="Click to jump to a folder"
            @click="startIndexEdit">
            {{ currentDisplayIndex }}
          </span>
          <span class="mc-progress-sep">/</span>
          <span class="mc-progress-total">{{ totalCount }}</span>
        </div>
        <el-button
          class="mc-settings-btn"
          circle
          text
          @click="goToSettings">
          <el-icon><Setting /></el-icon>
        </el-button>
      </el-header>
      <el-main>
        <div v-if="isEmpty" class="mc-empty-state">
          <el-empty description="No folders found">
            <template #image>
              <div class="mc-empty-icon">📂</div>
            </template>
            <div class="mc-empty-hint">
              The root path is empty or not configured yet.
              <br />
              Open Settings to set the <b>Root path</b>.
            </div>
            <el-button type="primary" @click="goToSettings">Open Settings</el-button>
          </el-empty>
        </div>
        <div v-else-if="canRestoreCurrent" class="mc-processed-state">
          <div class="mc-processed-icon">✓</div>
          <div class="mc-processed-title">{{ currentFolderName }} was moved</div>
          <div class="mc-processed-hint">Use ← / → to navigate, or restore this folder below.</div>
          <el-button
            type="primary"
            size="large"
            @click="handleUndoCurrent">
            <el-icon><RefreshLeft /></el-icon>
            <span style="margin-left: 6px;">Undo</span>
          </el-button>
        </div>
        <div v-else-if="isProcessedNoUndo" class="mc-processed-state">
          <div class="mc-processed-icon mc-processed-icon-muted">✓</div>
          <div class="mc-processed-title">{{ currentFolderName }} was moved</div>
          <div class="mc-processed-hint">Undo is no longer available for this folder.</div>
        </div>
        <div v-else-if="isLoadingFiles && !currentFileList" class="mc-loading-state">
          <div class="mc-loading-spinner"></div>
          <div class="mc-loading-hint">Loading files…</div>
        </div>
        <div v-else v-for="(file, index) in currentFileList?.files" :key="index" class="media-item">
          <img
            v-if="file.fileType === 'image'"
            :src="file.fileUrl"
            alt="image"
            loading="lazy"
          />
          <video
            v-else-if="file.fileType === 'video'"
            :src="file.fileUrl"
            controls
            autoplay
            preload="none">
            <!-- muted> -->
          </video>
        </div>
      </el-main>
    </el-container>
    <template v-if="!isEmpty">
      <CategoryButtonCardComponment
        v-if="categoryButtonCardJSON && categoryButtonCardJSON.left"
        :currentFolderPath="currentFolderName"
        side="left"
        :buttonCard="categoryButtonCardJSON.left"
        @folderChange="moveFolder"
      />
      <CategoryButtonCardComponment
        v-if="categoryButtonCardJSON && categoryButtonCardJSON.right"
        :currentFolderPath="currentFolderName"
        side="right"
        :buttonCard="categoryButtonCardJSON.right"
        @folderChange="moveFolder"
      />
    </template>
  </div>
</template>

<style scoped>

.el-header {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 40px;
  font-size: 20px;
  font-weight: bold;
  /* background-color: aqua; */
  border: 1px solid #eee;
  position: relative;
}
.mc-title {
  flex: 1;
  text-align: center;
}
.mc-settings-btn {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
}
.mc-progress {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: normal;
  font-size: 13px;
  color: #86868b;
  font-variant-numeric: tabular-nums;
}
.mc-progress-index {
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  color: #1d1d1f;
  min-width: 24px;
  text-align: right;
  transition: background 0.15s;
}
.mc-progress-index:hover {
  background: #f0f0f5;
}
.mc-progress-sep,
.mc-progress-total {
  color: #86868b;
}
.mc-progress-input {
  width: 60px;
  padding: 2px 6px;
  border: 1px solid #0071e3;
  border-radius: 4px;
  font-size: 13px;
  font-family: inherit;
  color: #1d1d1f;
  outline: none;
  font-variant-numeric: tabular-nums;
  text-align: right;
  /* Suppress spinner arrows to keep it clean. */
  -moz-appearance: textfield;
}
.mc-progress-input::-webkit-outer-spin-button,
.mc-progress-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.mc-empty-state {
  padding: 80px 20px;
  display: flex;
  justify-content: center;
}
.mc-empty-icon {
  font-size: 64px;
  line-height: 1;
  opacity: 0.6;
  margin-bottom: 8px;
}
.mc-empty-hint {
  font-size: 13px;
  color: #86868b;
  line-height: 1.6;
  margin-bottom: 16px;
  text-align: center;
}
.mc-processed-state {
  padding: 100px 20px 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
}
.mc-processed-icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: #0071e3;
  color: white;
  font-size: 36px;
  line-height: 64px;
  text-align: center;
  margin-bottom: 6px;
}
.mc-processed-icon-muted {
  background: #d0d0d5;
}
.mc-processed-title {
  font-size: 18px;
  font-weight: 600;
  color: #1d1d1f;
}
.mc-processed-hint {
  font-size: 13px;
  color: #86868b;
  margin-bottom: 12px;
}
.mc-loading-state {
  padding: 120px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.mc-loading-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid #e5e5ea;
  border-top-color: #0071e3;
  border-radius: 50%;
  animation: mc-spin 0.8s linear infinite;
}
.mc-loading-hint {
  font-size: 12px;
  color: #86868b;
}
@keyframes mc-spin {
  to { transform: rotate(360deg); }
}
.el-main{
  margin: 0px;
  padding: 0px;
}
img {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
  width: auto;
}
video {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
  width: auto;
}
</style>

<script lang="ts" src="@/manga_classifier/views/MangaClassifierView.ts"></script>
