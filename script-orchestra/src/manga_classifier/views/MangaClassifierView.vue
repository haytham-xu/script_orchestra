<template>
  <div>
    <el-container>
      <el-header>
        <span class="mc-title">{{ currentFolderName }}</span>
        <div v-if="!isEmpty" class="mc-progress">
          <div class="mc-progress-label">{{ currentDisplayIndex }} / {{ totalCount }}</div>
          <div class="mc-progress-bar">
            <div class="mc-progress-fill" :style="{ width: progressPercent + '%' }"></div>
          </div>
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
        <div v-else v-for="(file, index) in currentFileList?.files" :key="index" class="media-item">
          <img
            v-if="file.fileType === 'image'"
            :src="file.fileUrl"
            alt="image"
          />
          <video
            v-else-if="file.fileType === 'video'"
            :src="file.fileUrl"
            controls
            autoplay>
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
  gap: 8px;
  font-weight: normal;
  font-size: 12px;
  color: #86868b;
}
.mc-progress-label {
  font-variant-numeric: tabular-nums;
  min-width: 60px;
}
.mc-progress-bar {
  width: 140px;
  height: 4px;
  background: #e5e5ea;
  border-radius: 2px;
  overflow: hidden;
}
.mc-progress-fill {
  height: 100%;
  background: #0071e3;
  border-radius: 2px;
  transition: width 0.2s ease;
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
