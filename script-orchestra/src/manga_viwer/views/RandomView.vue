<template>
  <div class="viewer-root">
    <div class="header-bar">
      <div class="header-left">
        <el-button type="default" size="small" @click="goBack">← Back</el-button>
        <el-button type="primary" size="small" @click="loadRandomFolders" style="margin-left: 12px;">
          🎲 Random
        </el-button>
        <span v-if="isRandomMode" style="margin-left: 12px; color: #606266;">
          Base: {{ baseFolderCount }} | Total: {{ totalFolderCount }}
        </span>
      </div>

      <div class="header-right">
        <el-input
          v-model="orSearchInput"
          placeholder="OR keyword"
          size="small"
          @keyup.enter="addOrSearchKeyword"
          style="width: 200px; margin-right: 8px;"
        >
          <template #append>
            <el-button @click="addOrSearchKeyword">Add</el-button>
          </template>
        </el-input>
        <el-button
          v-if="orSearchKeywords.length > 0"
          size="small"
          @click="clearOrSearch"
        >
          Clear ({{ orSearchKeywords.length }})
        </el-button>
      </div>
    </div>

    <div class="folder-list">
      <div v-for="f in pagedFolders" :key="f.id" class="folder-line">
        <div class="line-left">
          <div class="name-cell" :title="f.name">{{ f.name }}</div>
          <div class="tags-row">
            <div class="tags-group"><span class="label">Path:</span> <span class="label">{{ f.path }}</span></div>
            <div class="tags-group"><span class="label">Size:</span> <span class="label">{{ Math.round(f.size / 1024/ 1024) }} MB</span></div>
            <div class="tags-group"><span class="label">Number:</span> <span class="label">{{ f.number }}</span></div>
          </div>
        </div>

        <div class="line-right" @click="openModal(f)">
          <div v-if="previewImages(f).length" class="thumbs">
            <div v-for="(img, i) in previewImages(f)" :key="img + i" class="thumb" :title="img">
              <img :src="img" />
            </div>
          </div>
          <div v-else class="no-thumb">无图片预览</div>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" :show-close="false" :close-on-click-modal="true" width="800px" :title="dialogFolder?.name || ''" destroy-on-close class="manga-center-dialog" top="0vh">
      <div class="dialog-body">
        <div v-for="(p, i) in dialogFiles" :key="p + i" class="media-item">
          <img v-if="isImage(p)" :src="p" :alt="p" />
          <video v-else-if="isVideo(p)" :src="p" controls preload="metadata"></video>
          <embed v-else-if="isPdf(p)" :src="p" type="application/pdf" class="pdf-embed" />
          <div v-else class="unknown">{{ p }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts" src="@/manga_viwer/views/RandomView.ts"></script>

<style scoped>
.viewer-root {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
}

.header-bar {
  position: sticky;
  top: 0;
  background: #fff;
  padding: 10px 12px;
  border: 1px solid #e2e6eb;
  border-radius: 8px;
  z-index: 5;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}

.folder-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.folder-line {
  display: flex;
  flex-direction: row;
  gap: 18px;
  border: 1px solid #e3e7ec;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 2px 6px -2px rgba(40, 48, 63, .12);
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

.name-cell {
  font-size: 15px;
  font-weight: 600;
  color: #313c4c;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: 12px;
}

.tags-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tags-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.label {
  font-size: 11px;
  font-weight: 600;
  color: #66717d;
}

.thumbs {
  display: flex;
  flex-direction: row;
  gap: 12px;
  align-items: center;
  height: 180px;
  max-width: 520px;
}

.thumb {
  height: 180px;
  width: auto;
  max-width: 140px;
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

.dialog-body {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  scrollbar-width: thin;
}

.media-item {
  width: 100%;
  max-width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  overflow: visible;
  position: relative;
  min-height: 120px;
}

.media-item img,
.media-item video {
  width: 100%;
  height: auto;
  object-fit: contain;
  display: block;
}

.media-item img {
  height: auto !important;
}

.media-item .unknown {
  font-size: 11px;
  color: #666;
  text-align: center;
  padding: 4px;
  word-break: break-all;
}

.pdf-embed {
  width: 100%;
  height: 800px;
  border: none;
}
</style>
