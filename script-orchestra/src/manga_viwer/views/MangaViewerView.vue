<template>

  <div class="viewer-root">

    <div class="header-bar">
      <div class="search-area">
        <div class="nav-buttons">
          <!-- DEPRECATED: standalone Random page hidden for now (kept, not removed).
          <el-button type="primary" size="small" @click="goToRandom">🎲 Random</el-button>
          -->
          <el-button size="small" @click="goBack">← Home</el-button>
          <el-button type="success" size="small" @click="goToBatch">🛠️ Batch</el-button>
          <!-- DEPRECATED: Import page hidden for now (kept, not removed).
          <el-button type="info" size="small" @click="goToImport">📥 Import</el-button>
          -->
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
      <div v-for="f in pagedFolders" :key="f.id" class="folder-line" :class="{ 'marked-for-deletion': store.deleteIdSet.has(f.id) }">
        <!-- Folder Line - Left -->
        <div class="line-left">

          <!-- FolderName with Delete Icon -->
          <div class="name-row">
            <div v-if="editingNameFlag === f.id" class="edit-inline">
              <el-input :ref="setActiveInput" v-model="editValue.name" size="small" @keyup.enter="commitEdit('name', f)"
                @blur="commitEdit('name', f)" />
            </div>
            <div v-else class="name-cell" :title="f.name">{{ f.name }}</div>

            <!-- Action icons - Right of Name -->
            <div class="delete-icon-wrapper">
              <el-button
                :icon="EditPen"
                circle
                size="small"
                type="default"
                @click.stop="startEdit(f)"
                title="Edit name"
              />
              <el-button
                :icon="f.favorite ? StarFilled : Star"
                circle
                size="small"
                :type="f.favorite ? 'warning' : 'default'"
                @click.stop="toggleFavorite(f)"
                :title="f.favorite ? 'Unfavorite' : 'Favorite'"
              />
              <el-button
                :icon="Folder"
                circle
                size="small"
                type="default"
                @click.stop="handleOpenFolder(f.id)"
                title="Open Folder"
              />
              <el-button
                v-if="!store.deleteIdSet.has(f.id)"
                :icon="Delete"
                circle
                size="small"
                type="danger"
                @click.stop="markForDeletion(f.id)"
                title="标记删除"
              />
              <el-button
                v-else
                :icon="RefreshLeft"
                circle
                size="small"
                type="info"
                @click.stop="unmarkForDeletion(f.id)"
                title="取消删除"
              />
            </div>
          </div>

          <div class="tags-row">
            <!-- size / number -->
            <div class="tags-group"><span class="label">Size:</span> <span class="label">{{ Math.round(f.size / 1024/ 1024) }} MB</span></div>
            <div class="tags-group"><span class="label">Number:</span> <span class="label">{{ f.number }}</span></div>
            <div class="tags-group">
              <span class="label">Read:</span>
              <span class="label read-count" :class="{ zero: !(f.read_count) }">{{ f.read_count ?? 0 }}</span>
              <el-button
                v-if="(f.read_count ?? 0) > 0"
                size="small"
                text
                class="reset-read-btn"
                title="Reset read count to 0"
                @click.stop="handleResetReadCount(f)"
              >↺</el-button>
            </div>

            <!-- mosaic -->
            <div class="tags-group">
              <span class="label">Mosaic:</span>
              <el-radio-group v-model="f.tags.mosaic" @change="commitEdit('mosaic', f)">
                <el-radio size="small" label="None">None</el-radio>
                <el-radio size="small" label="Light">Light</el-radio>
                <el-radio size="small" label="Heavy">Heavy</el-radio>
              </el-radio-group>
            </div>

            <!-- category_main (options from settings.categories.main) -->
            <div class="tags-group">
              <span class="label">Category Main:</span>
              <el-radio-group v-model="f.tags.category_main" @change="commitEdit('category_main', f)">
                <el-radio v-for="c in mainCategories" :key="c.key" size="small" :label="c.key">{{ c.key }}</el-radio>
              </el-radio-group>
            </div>

            <!-- category_sub (options from settings.categories.sub) -->
            <div class="tags-group">
              <span class="label">Category Sub:</span>
              <el-radio-group v-model="f.tags.category_sub" @change="commitEdit('category_sub', f)">
                <el-radio v-for="c in subCategories" :key="c.key" size="small" :label="c.key">{{ c.key }}</el-radio>
              </el-radio-group>
            </div>

            <!-- Custom (auth / name / others tag groups removed — unused) -->
            <div class="tags-group">
              <span class="label">Custom:</span>
              <el-tag type="warning" v-for="(t, i) in f.tags.custom" :key="f.id + 'custom' + i" closable
                @close="removeTag(f, 'custom', i)">{{ t }}</el-tag>
              <el-input v-if="isTagInputVisible(f, 'custom')" :ref="setTagInputRef(f.id, 'custom')"
                v-model="tagInputValues[f.id].custom" size="small" class="tag-input"
                @keyup.enter="handleTagInputConfirm(f, 'custom')" @blur="handleTagInputConfirm(f, 'custom')" />
              <span v-else class="tag placeholder" @click="showTagInput(f, 'custom')">+</span>
            </div>
          </div>
        </div>

        <!-- Preview -->
        <div class="line-right" @click="openModal(f)">
          <div v-if="previewImages(f).length" class="thumbs">
            <div v-for="(img, i) in previewImages(f)" :key="img + i" class="thumb" :title="img">
              <img :src="getPreviewSrc(img)" v-if="getPreviewSrc(img)" />
            </div>
          </div>
          <div v-else class="no-thumb">无图片预览</div>
        </div>
      </div>

    </div>

    <el-dialog v-model="dialogVisible" :show-close="false" :close-on-click-modal="true" :close-on-press-escape="false"
      width="800px" :title="dialogFolder?.name || ''" destroy-on-close class="manga-center-dialog" top="0vh">
      <div class="dialog-body">
        <template v-for="(p, i) in dialogFiles" :key="p + i">
          <div v-if="isImage(p)" class="media-item">
            <img :src="p" :alt="p" />
          </div>
          <div v-else-if="isPdf(p)" v-for="(pageUrl, pageIdx) in pdfPages[p]" :key="p + '-page-' + pageIdx" class="media-item">
            <img :src="pageUrl" :alt="`${p} - Page ${pageIdx + 1}`" />
          </div>
          <div v-else-if="isVideo(p)" class="media-item">
            <video :src="p" controls preload="metadata"></video>
          </div>
          <div v-else class="media-item">
            <div class="unknown">{{ p }}</div>
          </div>
        </template>
      </div>
    </el-dialog>
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
</style>
