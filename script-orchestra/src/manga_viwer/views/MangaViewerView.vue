<template>

  <div class="viewer-root">

    <div class="header-bar">
      <div class="search-area">
        <div class="nav-buttons">
          <el-button type="primary" size="small" @click="goToRandom">🎲 Random</el-button>
          <el-button type="success" size="small" @click="goToBatch">🛠️ Batch</el-button>
          <el-button type="info" size="small" @click="goToImport">📥 Import</el-button>
          <el-button type="default" size="small" @click="goToSettings">⚙️ Settings</el-button>
          <el-button type="warning" size="small" @click="handleRefreshIndex" :loading="refreshLoading">🔄 Refresh</el-button>
        </div>
        <div class="search-tags">
          <el-tag v-for="(t, i) in searchTokens" :key="t + i" closable @close="removeSearchToken(i)">{{ t }}</el-tag>
          <el-input v-model="searchInput" class="search-tag-input" @keyup.enter="addSearchToken" />
          <span class="hot-label">热门:</span>
          <el-tag v-for="ht in hotTags" :key="ht" class="hot-tag" @click="addHotTag(ht)">{{ ht }}</el-tag>
        </div>
      </div>
      <div class="header-right">
        <el-switch v-model="sizeSortEnabled" inactive-text="size" active-text="" />
        <el-switch v-model="showUninitializedOnly" inactive-text="all" active-text="" />
        <el-switch v-model="nameSortEnabled" inactive-text="name" active-text="" />
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
            <div v-else class="name-cell" :title="f.name" @click="startEdit(f)">{{ f.name }}</div>

            <!-- Delete Icon - Right of Name -->
            <div class="delete-icon-wrapper">
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
            <!-- path /size / number -->
            <div class="tags-group"><span class="label">Path:</span> <span class="label">{{ f.path }}</span></div>
            <div class="tags-group"><span class="label">Size:</span> <span class="label">{{ Math.round(f.size / 1024/ 1024) }} MB</span></div>
            <div class="tags-group"><span class="label">Number:</span> <span class="label">{{ f.number }}</span></div>

            <!-- mosaic -->
            <div class="tags-group">
              <span class="label">Mosaic:</span>
              <el-radio-group v-model="f.tags.mosaic" @change="commitEdit('mosaic', f)">
                <el-radio size="small" label="true">true</el-radio>
                <el-radio size="small" label="false">false</el-radio>
              </el-radio-group>
            </div>

            <!-- category_main -->
            <div class="tags-group">
              <span class="label">Category Main:</span>
              <el-radio-group v-model="f.tags.category_main" @change="commitEdit('category_main', f)">
                <el-radio size="small" label="bou">bou</el-radio>
                <el-radio size="small" label="arch">arch</el-radio>
              </el-radio-group>
            </div>

            <!-- category_sub -->
            <div class="tags-group">
              <span class="label">Category Sub:</span>
              <el-radio-group v-model="f.tags.category_sub" @change="commitEdit('category_sub', f)">
                <el-radio size="small" label="hf">hf</el-radio>
                <el-radio size="small" label="ntr">ntr</el-radio>
                <el-radio size="small" label="3d">3d</el-radio>
                <el-radio size="small" label="hm">hm</el-radio>
                <el-radio size="small" label="q">q</el-radio>
                <el-radio size="small" label="m">m</el-radio>
                <el-radio size="small" label="ll">ll</el-radio>
                <el-radio size="small" label="lo">lo</el-radio>
                <el-radio size="small" label="xz">xz</el-radio>
                <el-radio size="small" label="zr">zr</el-radio>
                <el-radio size="small" label="sp">sp</el-radio>
                <el-radio size="small" label="tr">tr</el-radio>
              </el-radio-group>
            </div>

            <!-- 动态标签组: auth / name(tags.name) / custom / others -->
            <div class="tags-group">
              <span class="label">Auth:</span>
              <el-tag type="primary" v-for="(t, i) in f.tags.auth" :key="f.id + 'auth' + i" closable
                @close="removeTag(f, 'auth', i)">{{ t
                }}</el-tag>

              <el-input v-if="isTagInputVisible(f, 'auth')" :ref="setTagInputRef(f.id, 'auth')"
                v-model="tagInputValues[f.id].auth" size="small" class="tag-input"
                @keyup.enter="handleTagInputConfirm(f, 'auth')" @blur="handleTagInputConfirm(f, 'auth')" />
              <span v-else class="tag placeholder" @click="showTagInput(f, 'auth')">+</span>
            </div>

            <!-- Name -->
            <div class="tags-group">
              <span class="label">Name:</span>
              <el-tag type="success" v-for="(t, i) in f.tags.name" :key="f.id + 'nt' + i" closable
                @close="removeTag(f, 'name', i)">{{
                  t
                }}</el-tag>
              <el-input v-if="isTagInputVisible(f, 'name')" :ref="setTagInputRef(f.id, 'name')"
                v-model="tagInputValues[f.id].name" size="small" class="tag-input"
                @keyup.enter="handleTagInputConfirm(f, 'name')" @blur="handleTagInputConfirm(f, 'name')" />
              <span v-else class="tag placeholder" @click="showTagInput(f, 'name')">+</span>
            </div>

            <!-- Custom -->
            <div class="tags-group">
              <span class="label">Custom:</span>
              <el-tag type="warning" v-for="(t, i) in f.tags.custom" :key="f.id + 'custom' + i" closable
                @close="removeTag(f, 'custom', i)">{{ t }}</el-tag>
              <el-input v-if="isTagInputVisible(f, 'custom')" :ref="setTagInputRef(f.id, 'custom')"
                v-model="tagInputValues[f.id].custom" size="small" class="tag-input"
                @keyup.enter="handleTagInputConfirm(f, 'custom')" @blur="handleTagInputConfirm(f, 'custom')" />
              <span v-else class="tag placeholder" @click="showTagInput(f, 'custom')">+</span>
            </div>

            <!-- Others -->
            <div class="tags-group">
              <span class="label">Others:</span>
              <el-tag v-for="(t, i) in f.tags.others" :key="f.id + 'others' + i" type="danger" closable
                @close="removeTag(f, 'others', i)">{{ t }}</el-tag>
              <el-input v-if="isTagInputVisible(f, 'others')" :ref="setTagInputRef(f.id, 'others')"
                v-model="tagInputValues[f.id].others" size="small" class="tag-input"
                @keyup.enter="handleTagInputConfirm(f, 'others')" @blur="handleTagInputConfirm(f, 'others')" />
              <span v-else class="tag placeholder" @click="showTagInput(f, 'others')">+</span>
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
</style>
