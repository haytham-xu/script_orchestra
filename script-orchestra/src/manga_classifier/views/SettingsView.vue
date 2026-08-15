<template>
  <div class="mc-settings">
    <header class="mc-topbar">
      <div class="mc-topbar-left">
        <el-button link @click="goBack" class="mc-back">
          <el-icon><ArrowLeft /></el-icon>
          <span>Manga Classifier</span>
        </el-button>
        <h1>Settings</h1>
      </div>
      <div class="mc-topbar-right">
        <el-button :icon="Refresh" @click="load" :loading="loading" text />
        <el-button
          type="primary"
          @click="save"
          :disabled="!isDirty || saving"
          :loading="saving">
          Save
        </el-button>
      </div>
    </header>

    <main class="mc-content">
      <!-- Paths -->
      <section class="mc-card">
        <div class="mc-card-header">
          <h2>Paths</h2>
          <p class="mc-hint">Root, target and delete directories used when classifying folders.</p>
        </div>
        <div class="mc-card-body">
          <div class="mc-row">
            <label class="mc-label">Root path</label>
            <el-input v-model="state.rootPath" placeholder="/absolute/path/to/mangas" spellcheck="false" />
          </div>
          <div class="mc-row">
            <label class="mc-label">Target path</label>
            <el-input v-model="state.targetPath" placeholder="/absolute/path/to/classified" spellcheck="false" />
          </div>
          <div class="mc-row">
            <label class="mc-label">Delete path</label>
            <el-input v-model="state.deletePath" placeholder="/absolute/path/to/deleted" spellcheck="false" />
          </div>
        </div>
      </section>

      <!-- Scan extensions -->
      <section class="mc-card">
        <div class="mc-card-header">
          <h2>Scan extensions</h2>
          <p class="mc-hint">File extensions detected inside each folder. Saved values are normalized (lowercase, leading dot).</p>
        </div>
        <div class="mc-card-body">
          <div class="mc-row">
            <label class="mc-label">Images</label>
            <div class="mc-tag-input">
              <el-tag
                v-for="ext in state.imageExts"
                :key="ext"
                closable
                round
                @close="removeExt('image', ext)">
                {{ ext }}
              </el-tag>
              <el-input
                v-model="newImageExt"
                placeholder=".jpg"
                size="small"
                class="mc-tag-add"
                @keydown.enter.prevent="addExt('image')" />
              <el-button :icon="Plus" size="small" @click="addExt('image')" circle />
            </div>
          </div>
          <div class="mc-row">
            <label class="mc-label">Videos</label>
            <div class="mc-tag-input">
              <el-tag
                v-for="ext in state.videoExts"
                :key="ext"
                closable
                round
                type="success"
                @close="removeExt('video', ext)">
                {{ ext }}
              </el-tag>
              <el-input
                v-model="newVideoExt"
                placeholder=".mp4"
                size="small"
                class="mc-tag-add"
                @keydown.enter.prevent="addExt('video')" />
              <el-button :icon="Plus" size="small" @click="addExt('video')" circle />
            </div>
          </div>
        </div>
      </section>

      <!-- Category buttons -->
      <section class="mc-card">
        <div class="mc-card-header">
          <h2>Category buttons</h2>
          <p class="mc-hint">Two side panels shown on the main view. Main buttons stay visible; sub-buttons collapse under an expander.</p>
        </div>
        <div class="mc-card-body mc-two-col">
          <!-- Left -->
          <div class="mc-side">
            <div class="mc-side-header">
              <el-input v-model="state.categoty.left.name" placeholder="Left panel name" size="small" />
            </div>

            <div class="mc-group">
              <div class="mc-group-header">
                <span>Main</span>
                <el-button :icon="Plus" size="small" @click="addButton('left', 'mainButtons')" text>Add</el-button>
              </div>
              <div v-if="leftMain.length === 0" class="mc-empty">No buttons yet</div>
              <div
                v-for="(btn, i) in state.categoty.left.mainButtons"
                :key="'lm' + i"
                class="mc-btn-item">
                <div class="mc-btn-row">
                  <el-input v-model="btn.label" placeholder="Label" size="small" />
                  <el-input v-model="btn.folderPath" placeholder="Folder path" size="small" />
                  <el-button :icon="Delete" size="small" @click="removeButton('left', 'mainButtons', i)" text />
                </div>
                <div class="mc-btn-preview">
                  <span v-if="resolveTargetPath(btn.folderPath)">→ {{ resolveTargetPath(btn.folderPath) }}</span>
                  <span v-else class="mc-btn-preview-empty">set a target path above</span>
                </div>
              </div>
            </div>

            <div class="mc-group">
              <div class="mc-group-header">
                <span>Sub</span>
                <el-button :icon="Plus" size="small" @click="addButton('left', 'subButtons')" text>Add</el-button>
              </div>
              <div v-if="leftSub.length === 0" class="mc-empty">No buttons yet</div>
              <div
                v-for="(btn, i) in state.categoty.left.subButtons"
                :key="'ls' + i"
                class="mc-btn-item">
                <div class="mc-btn-row">
                  <el-input v-model="btn.label" placeholder="Label" size="small" />
                  <el-input v-model="btn.folderPath" placeholder="Folder path" size="small" />
                  <el-button :icon="Delete" size="small" @click="removeButton('left', 'subButtons', i)" text />
                </div>
                <div class="mc-btn-preview">
                  <span v-if="resolveTargetPath(btn.folderPath)">→ {{ resolveTargetPath(btn.folderPath) }}</span>
                  <span v-else class="mc-btn-preview-empty">set a target path above</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Right -->
          <div class="mc-side">
            <div class="mc-side-header">
              <el-input v-model="state.categoty.right.name" placeholder="Right panel name" size="small" />
            </div>

            <div class="mc-group">
              <div class="mc-group-header">
                <span>Main</span>
                <el-button :icon="Plus" size="small" @click="addButton('right', 'mainButtons')" text>Add</el-button>
              </div>
              <div v-if="rightMain.length === 0" class="mc-empty">No buttons yet</div>
              <div
                v-for="(btn, i) in state.categoty.right.mainButtons"
                :key="'rm' + i"
                class="mc-btn-item">
                <div class="mc-btn-row">
                  <el-input v-model="btn.label" placeholder="Label" size="small" />
                  <el-input v-model="btn.folderPath" placeholder="Folder path" size="small" />
                  <el-button :icon="Delete" size="small" @click="removeButton('right', 'mainButtons', i)" text />
                </div>
                <div class="mc-btn-preview">
                  <span v-if="resolveTargetPath(btn.folderPath)">→ {{ resolveTargetPath(btn.folderPath) }}</span>
                  <span v-else class="mc-btn-preview-empty">set a target path above</span>
                </div>
              </div>
            </div>

            <div class="mc-group">
              <div class="mc-group-header">
                <span>Sub</span>
                <el-button :icon="Plus" size="small" @click="addButton('right', 'subButtons')" text>Add</el-button>
              </div>
              <div v-if="rightSub.length === 0" class="mc-empty">No buttons yet</div>
              <div
                v-for="(btn, i) in state.categoty.right.subButtons"
                :key="'rs' + i"
                class="mc-btn-item">
                <div class="mc-btn-row">
                  <el-input v-model="btn.label" placeholder="Label" size="small" />
                  <el-input v-model="btn.folderPath" placeholder="Folder path" size="small" />
                  <el-button :icon="Delete" size="small" @click="removeButton('right', 'subButtons', i)" text />
                </div>
                <div class="mc-btn-preview">
                  <span v-if="resolveTargetPath(btn.folderPath)">→ {{ resolveTargetPath(btn.folderPath) }}</span>
                  <span v-else class="mc-btn-preview-empty">set a target path above</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div class="mc-footer">
        <el-button link @click="resetToDefaults">Reset to defaults</el-button>
      </div>
    </main>
  </div>
</template>

<script lang="ts" src="@/manga_classifier/views/SettingsView.ts"></script>

<style scoped>
.mc-settings {
  min-height: 100vh;
  background: #f5f5f7;
  color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}

.mc-topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(245, 245, 247, 0.85);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  padding: 12px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.mc-topbar-left {
  display: flex;
  align-items: baseline;
  gap: 16px;
}

.mc-back {
  color: #0071e3;
}

.mc-topbar h1 {
  font-size: 17px;
  font-weight: 600;
  margin: 0;
}

.mc-topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mc-content {
  max-width: 820px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.mc-card {
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  overflow: hidden;
}

.mc-card-header {
  padding: 16px 20px 8px;
}

.mc-card-header h2 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 4px;
}

.mc-hint {
  font-size: 12px;
  color: #86868b;
  margin: 0;
}

.mc-card-body {
  padding: 8px 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mc-row {
  display: grid;
  grid-template-columns: 120px 1fr;
  align-items: center;
  gap: 12px;
}

.mc-label {
  font-size: 13px;
  color: #1d1d1f;
}

.mc-tag-input {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  background: #f5f5f7;
  border-radius: 8px;
  min-height: 36px;
}

.mc-tag-add {
  width: 90px;
}

.mc-two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  padding-top: 8px;
}

.mc-side {
  background: #fbfbfd;
  border-radius: 10px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mc-side-header {
  padding-bottom: 4px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.mc-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mc-group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  color: #86868b;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.mc-btn-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.mc-btn-row {
  display: grid;
  grid-template-columns: 1fr 1fr 32px;
  gap: 6px;
  align-items: center;
}

.mc-btn-preview {
  font-size: 10px;
  color: #86868b;
  padding-left: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  word-break: break-all;
  line-height: 1.4;
}

.mc-btn-preview-empty {
  font-style: italic;
  color: #b0b0b6;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}

.mc-empty {
  font-size: 12px;
  color: #b0b0b6;
  font-style: italic;
  padding: 4px 0;
}

.mc-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 4px;
}

@media (max-width: 720px) {
  .mc-two-col {
    grid-template-columns: 1fr;
  }
  .mc-row {
    grid-template-columns: 1fr;
    align-items: stretch;
  }
}
</style>
