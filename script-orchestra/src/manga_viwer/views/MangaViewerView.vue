<template>

  <div class="viewer-root">

    <div class="header-bar">
      <div class="search-area">
        <div class="nav-buttons">
          <!-- DEPRECATED: standalone Random page hidden for now (kept, not removed).
          <el-button type="primary" size="small" @click="goToRandom">🎲 Random</el-button>
          -->
          <el-button size="small" @click="goBack">← Home</el-button>
          <el-button type="success" size="small" @click="goToBatch">🛠️ Tools</el-button>
          <el-button type="default" size="small" @click="goToSettings">⚙️ Settings</el-button>
        </div>
        <div class="search-tags">
          <el-tag v-for="(t, i) in searchTokens" :key="t + i" closable @close="removeSearchToken(i)">{{ t }}</el-tag>
          <el-input v-model="searchInput" class="search-tag-input" @keyup.enter="addSearchToken" />
          <span class="hot-label">热门:</span>
          <el-tag v-for="ht in hotTags" :key="ht" class="hot-tag" @click="addHotTag(ht)">{{ ht }}</el-tag>
        </div>
      </div>
      <div class="header-right">
        <el-switch v-model="showFavoritesOnly" inactive-text="★ fav" active-text="" />
        <el-switch v-model="unreadOnlyMode" inactive-text="👁 unread" active-text="" />
        <el-button size="small" title="Reshuffle random order" @click="reshuffle">🎲 Random</el-button>
        <el-button size="small" :type="unreadOnlyMode ? 'success' : 'default'" title="Random over unread manga only" @click="reshuffleUnread">🎲 Random Unread</el-button>
        <el-button class="apply-button" type="primary" @click="applyChanges">
          Apply
          <span v-if="store.deleteIdSet.size > 0" style="margin-left: 5px;">
            & 删除({{ store.deleteIdSet.size }})
          </span>
        </el-button>
      </div>
    </div>

    <div class="folder-list">
      <FolderLine
        v-for="f in pagedFolders"
        :key="f.id"
        :folder="f"
        :editingNameId="editingNameFlag"
        :editValue="editValue"
        :mainCategories="mainCategories"
        :subCategories="subCategories"
        :isMarkedForDeletion="store.deleteIdSet.has(f.id)"
        :isInReadQueue="readQueueIds.has(f.id)"
        :isInSnoozeQueue="snoozeQueueIds.has(f.id)"
        @start-edit="startEdit"
        @commit-edit="commitEdit"
        @toggle-favorite="toggleFavorite"
        @open-folder="handleOpenFolder"
        @mark-delete="markForDeletion"
        @unmark-delete="unmarkForDeletion"
        @reset-read-count="handleResetReadCount"
        @confirm-tag="handleTagInputConfirm"
        @remove-tag="removeTag"
        @save-for-later="handleSaveForLater"
        @snooze="handleSnooze"
      />
    </div>
  </div>
</template>

<script lang="ts" src="@/manga_viwer/views/MangaViewerView.ts"></script>

<style scoped>
.viewer-root {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
}

/* ===== Search - with Hot Tags ===== */

/* .search-input {
  width: 300px;
  padding: 6px 10px;
  border: 1px solid #cfd5dc;
  border-radius: 6px;
  font-size: 14px;
}

.search-input:focus {
  outline: none;
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, .25);
} */

.search-area {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 12px;
}

.nav-buttons {
  display: flex;
  gap: 8px;
  flex: 0 0 auto;
}

.search-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.search-tag-input {
  width: 240px;
  flex: 0 0 auto;
}

.hot-label {
  font-size: 11px;
  font-weight: 600;
  color: #506070;
  margin-left: 4px;
}

.hot-tag {
  cursor: pointer;
  user-select: none;
}

.hot-tag:hover {
  filter: brightness(0.92);
}

/* ===== Search - with Hot Tags ===== */

.folder-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.folder-line {
  display: flex;
  flex-direction: row;
  gap: 18px;
  /* min-height: 120px; */
  /* height: 300px; */
  border: 1px solid #e3e7ec;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 2px 6px -2px rgba(40, 48, 63, .12);
}

.folder-line.marked-for-deletion {
  border: 2px solid #f56c6c;
  background: #fef0f0;
  opacity: 0.8;
}

.folder-line:hover {
  box-shadow: 0 4px 14px -4px rgba(40, 48, 63, .22);
}

.name-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.name-cell {
  flex: 1;
  min-width: 0;
}

.edit-inline {
  flex: 1;
  min-width: 0;
}
.edit-inline :deep(.el-input) {
  width: 100%;
}

.delete-icon-wrapper {
  flex-shrink: 0;
}

.line-left {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 15px 15px 15px;
  margin: 0;
}

.line-right {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  /* padding: 24px 16px 28px 0; */
  min-width: 0;
  margin-right: 15px;
}

/* .line-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
} */

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

.tag {
  font-size: 11px;
  padding: 3px 8px 4px;
  background: #f0f4f8;
  border: 1px solid #d9e1e8;
  border-radius: 16px;
  color: #3f4c5a;
  line-height: 1.3;
}

.thumbs {
  display: flex;
  flex-direction: row;
  gap: 12px;
  align-items: center;
  height: 250px;
  max-width: 520px;
}

.thumb {
  height: 250px;
  width: auto;
  max-width: 160px;
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
  max-height: 250px;
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

/* .empty { padding:28px 0; text-align:center; color:#7d8792; font-size:13px; border:1px dashed #d9e1e8; border-radius:10px; background:#fff; } */

.manga-center-dialog {
  padding: 0;
}

/* .dialog-header {
  padding: 10px 16px 6px;
  font-weight: 600;
  font-size: 14px;
  border-bottom: 1px solid #e3e7ec;
}
.dialog-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
} */

.dialog-body {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  scrollbar-width: thin;
}

.dialog-body::-webkit-scrollbar {
  width: 8px;
}

.dialog-body::-webkit-scrollbar-track {
  background: #f1f3f5;
  border-radius: 4px;
}

.dialog-body::-webkit-scrollbar-thumb {
  background: #bfc6cc;
  border-radius: 4px;
}

.dialog-body::-webkit-scrollbar-thumb:hover {
  background: #a5adb4;
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

/* ------------- */
.tag.placeholder {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px 3px;
  line-height: 1;
  min-width: 22px;
  text-align: center;
  cursor: pointer;
  background: #f7f9fb;
  border: 1px dashed #cfd6dd;
  color: #54606c;
}

.tag.placeholder:hover {
  background: #eef3f6;
  border-color: #b6c1c9;
}

/* -------------- */

/* ---- switch for initialized  ---- */

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
  align-items: flex-start;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 4px;
  flex: 0 0 auto;
  white-space: nowrap;
  font-size: 11px;
  color: #5a636d;
}

/* ---- folder delete button  ---- */
.delete-btn {
  position: absolute;
  bottom: 25px;
  right: 8px;
  box-shadow: 0 2px 6px -2px rgba(40, 48, 63, .25);
}

.delete-btn:hover {
  box-shadow: 0 4px 12px -4px rgba(40, 48, 63, .3);
}

/* ---- folder star button  ---- */
.star-btn {
  position: absolute;
  bottom: 245px;
  right: 8px;
  box-shadow: 0 2px 6px -2px rgba(40, 48, 63, .25);
}

.star-btn:hover {
  box-shadow: 0 4px 12px -4px rgba(40, 48, 63, .3);
}

/* ---- apply button  ---- */
.apply-button {
  margin-left: 20px;
  width: 120px;
}

.read-count {
  font-weight: 600;
  color: #67C23A;
}
.read-count.zero {
  color: #909399;
  font-weight: 400;
}
.reset-read-btn {
  margin-left: 4px;
  padding: 0 4px;
  min-height: unset;
  height: 20px;
  font-size: 14px;
  color: #909399;
}
.reset-read-btn:hover {
  color: #F56C6C;
}

/* Queue floating action buttons */
.line-left-actions {
  display: none;
  position: absolute;
  bottom: 10px;
  right: 10px;
  flex-direction: row;
  gap: 6px;
  z-index: 10;
}
.folder-line:hover .line-left-actions {
  display: flex;
}
.ql-btn {
  border: none;
  border-radius: 8px;
  padding: 5px 10px;
  font-size: 15px;
  cursor: pointer;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.14);
  transition: background 0.15s, transform 0.1s, opacity 0.15s;
  opacity: 0.75;
  line-height: 1;
}
.ql-btn:hover {
  opacity: 1;
  transform: translateY(-1px);
  background: #fff;
}
.ql-btn.active {
  opacity: 1;
  background: #ecf5ff;
  box-shadow: 0 1px 6px rgba(64, 158, 255, 0.25);
}
</style>
