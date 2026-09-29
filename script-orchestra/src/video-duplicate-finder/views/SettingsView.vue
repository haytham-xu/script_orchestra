<template>
  <div class="vdf-settings">
    <header class="vdf-topbar">
      <div class="vdf-topbar-left">
        <el-button link @click="goBack" class="vdf-back">
          <el-icon><ArrowLeft /></el-icon>
          <span>Video Duplicate Finder</span>
        </el-button>
        <h1>Settings</h1>
      </div>
      <div class="vdf-topbar-right">
        <el-button :icon="Refresh" @click="load" :loading="loading" text />
        <el-button plain :loading="isCleaningDb" @click="cleanupDatabase">Cleanup DB</el-button>
        <el-button type="primary" @click="save" :loading="saving">Save</el-button>
      </div>
    </header>

    <main class="vdf-content">

      <!-- Folders -->
      <section class="vdf-card">
        <div class="vdf-card-header">
          <h2>Folders</h2>
        </div>
        <div class="vdf-card-body">
          <div class="vdf-row">
            <label class="vdf-label">Delete target path</label>
            <el-input v-model="settings.delete_target_path" placeholder="/path/to/trash" spellcheck="false" />
          </div>
          <div class="vdf-group">
            <div class="vdf-group-header">
              <span>Scan folders</span>
              <el-button size="small" text @click="addFolderPath">+ Add</el-button>
            </div>
            <div v-if="settings.folder_paths && settings.folder_paths.length" class="path-list">
              <div v-for="(_, i) in settings.folder_paths" :key="`fp-${i}`" class="path-row">
                <el-input :model-value="settings.folder_paths?.[i]" @update:model-value="val => { if (settings.folder_paths) settings.folder_paths[i] = val }" placeholder="/path/to/videos" spellcheck="false" />
                <el-button type="danger" plain @click="removeFolderPath(i)">Remove</el-button>
              </div>
            </div>
            <p v-else class="vdf-empty">No scan folders configured.</p>
          </div>
          <div class="vdf-group">
            <div class="vdf-group-header">
              <span>Exclude folders</span>
              <el-button size="small" text @click="addExcludePath">+ Add</el-button>
            </div>
            <div v-if="settings.exclude_folder_paths && settings.exclude_folder_paths.length" class="path-list">
              <div v-for="(_, i) in settings.exclude_folder_paths" :key="`ex-${i}`" class="path-row">
                <el-input :model-value="settings.exclude_folder_paths?.[i]" @update:model-value="val => { if (settings.exclude_folder_paths) settings.exclude_folder_paths[i] = val }" placeholder="/path/to/exclude" spellcheck="false" />
                <el-button type="danger" plain @click="removeExcludePath(i)">Remove</el-button>
              </div>
            </div>
            <p v-else class="vdf-empty">No exclude folders.</p>
          </div>
        </div>
      </section>

      <!-- Core Settings -->
      <section class="vdf-card">
        <div class="vdf-card-header">
          <h2>Core Settings</h2>
        </div>
        <div class="vdf-card-body">
          <div class="vdf-row">
            <label class="vdf-label">Similarity threshold: {{ threshold }}%</label>
            <el-slider v-model="threshold" :min="60" :max="100" show-stops />
          </div>
          <div class="vdf-row">
            <label class="vdf-label">Max CPU cores: {{ settings.max_cpu_cores || 2 }} / {{ settings.system_cpu_count || '?' }}</label>
            <el-input-number v-model="settings.max_cpu_cores" :min="1" :max="settings.system_cpu_count || 16" controls-position="right" />
          </div>
          <div class="vdf-row">
            <label class="vdf-label">Frames per video</label>
            <el-input-number v-model="settings.n_frames" :min="1" :max="32" controls-position="right" />
          </div>
          <div class="vdf-row">
            <label class="vdf-label">Thumbnail position (%)</label>
            <el-input-number v-model="settings.thumbnail_position_percent" :min="0" :max="100" :step="5" controls-position="right" />
          </div>
          <div class="vdf-row">
            <label class="vdf-label">Page size (groups/page)</label>
            <el-input-number v-model="settings.page_size" :min="20" :max="500" :step="10" controls-position="right" />
          </div>
        </div>
      </section>

      <!-- Auto-Selection Rules -->
      <section class="vdf-card">
        <div class="vdf-card-header">
          <h2>Auto-Selection Rules</h2>
          <p class="vdf-hint">Automatically mark one video from each duplicate pair for deletion.</p>
        </div>
        <div class="vdf-card-body">
          <div class="vdf-row-switch">
            <el-switch v-model="settings.auto_selection_rules.auto_mark_lower_resolution" />
            <label>Mark lower resolution</label>
          </div>
          <div class="vdf-row-switch">
            <el-switch v-model="settings.auto_selection_rules.auto_mark_lower_bitrate" />
            <label>Mark lower bitrate</label>
          </div>
          <div class="vdf-row-switch">
            <el-switch v-model="settings.auto_selection_rules.auto_mark_smaller_filesize" />
            <label>Mark smaller filesize</label>
          </div>
          <div class="vdf-row-switch">
            <el-switch v-model="settings.auto_selection_rules.auto_mark_older_codec" />
            <label>Mark older codec</label>
          </div>
          <div class="vdf-row-switch">
            <el-switch v-model="settings.auto_selection_rules.auto_mark_numbered_copies" />
            <label>Mark numbered copies</label>
          </div>
          <div class="vdf-group">
            <div class="vdf-group-header">
              <span>Prefer folders</span>
              <el-button size="small" text @click="addPreferFolder">+ Add</el-button>
            </div>
            <p class="vdf-hint">Files in these folders are kept; others marked for deletion.</p>
            <div v-if="settings.auto_selection_rules && settings.auto_selection_rules.prefer_folders && settings.auto_selection_rules.prefer_folders.length" class="path-list">
              <div v-for="(_, i) in settings.auto_selection_rules.prefer_folders" :key="`pf-${i}`" class="path-row">
                <el-input :model-value="settings.auto_selection_rules.prefer_folders?.[i]" @update:model-value="val => { if (settings.auto_selection_rules.prefer_folders) settings.auto_selection_rules.prefer_folders[i] = val }" placeholder="/path/to/prefer" spellcheck="false" />
                <el-button type="danger" plain @click="removePreferFolder(i)">Remove</el-button>
              </div>
            </div>
            <p v-else class="vdf-empty">No preferred folders.</p>
          </div>
        </div>
      </section>

      <!-- Companion Extensions -->
      <section class="vdf-card">
        <div class="vdf-card-header">
          <h2>Companion Extensions</h2>
          <p class="vdf-hint">Sidecar files deleted alongside the video (subtitles, metadata, etc.).</p>
        </div>
        <div class="vdf-card-body">
          <div v-if="settings.companion_extensions && settings.companion_extensions.length" class="path-list">
            <div v-for="(_, i) in settings.companion_extensions" :key="`ce-${i}`" class="path-row">
              <el-input :model-value="settings.companion_extensions?.[i]" @update:model-value="val => { if (settings.companion_extensions) settings.companion_extensions[i] = val }" placeholder=".srt" spellcheck="false" style="max-width: 200px" />
              <el-button type="danger" plain @click="removeCompanionExt(i)">Remove</el-button>
            </div>
          </div>
          <p v-else class="vdf-empty">No extensions configured.</p>
          <el-button size="small" @click="addCompanionExt">+ Add Extension</el-button>
        </div>
      </section>

      <!-- Performance — Phase 1 -->
      <section class="vdf-card">
        <div class="vdf-card-header">
          <h2>Performance — Phase 1 (Scan &amp; Hash)</h2>
        </div>
        <div class="vdf-card-body vdf-perf-grid" v-if="settings.phase1">
          <div class="vdf-perf-item">
            <label>Worker Handler Size</label>
            <el-input-number v-model="settings.phase1.worker_handler_size" :min="1" :max="100" controls-position="right" />
            <p class="vdf-sub-hint">Recommended: 1</p>
          </div>
          <div class="vdf-perf-item">
            <label>DB Commit Batch</label>
            <el-input-number v-model="settings.phase1.db_commit_batch_size" :min="1" :max="10000" :step="10" controls-position="right" />
            <p class="vdf-sub-hint">Recommended: 50</p>
          </div>
          <div class="vdf-perf-item">
            <label>Progress Update Interval</label>
            <el-input-number v-model="settings.phase1.progress_update_interval" :min="1" :max="10000" :step="10" controls-position="right" />
            <p class="vdf-sub-hint">Recommended: 10</p>
          </div>
          <div class="vdf-perf-item">
            <label>IPC Chunk Size</label>
            <el-input-number v-model="settings.phase1.ipc_chunk_size" :min="1" :max="1000" controls-position="right" />
            <p class="vdf-sub-hint">Recommended: 1</p>
          </div>
          <div class="vdf-perf-item">
            <label>Scan Delay (s)</label>
            <el-input-number v-model="settings.phase1.scan_delay" :min="0" :max="5" :step="0.1" :precision="1" controls-position="right" />
            <p class="vdf-sub-hint">0 = no delay</p>
          </div>
          <div class="vdf-perf-item">
            <label>Compute Delay (s)</label>
            <el-input-number v-model="settings.phase1.compute_delay" :min="0" :max="5" :step="0.1" :precision="1" controls-position="right" />
            <p class="vdf-sub-hint">0 = no delay</p>
          </div>
        </div>
      </section>

      <!-- Performance — Phase 2 -->
      <section class="vdf-card">
        <div class="vdf-card-header">
          <h2>Performance — Phase 2 (Compare)</h2>
        </div>
        <div class="vdf-card-body vdf-perf-grid" v-if="settings.phase2">
          <div class="vdf-perf-item">
            <label>Worker Handler Size</label>
            <el-input-number v-model="settings.phase2.worker_handler_size" :min="1" :max="100" controls-position="right" />
            <p class="vdf-sub-hint">Recommended: 1</p>
          </div>
          <div class="vdf-perf-item">
            <label>DB Commit Batch</label>
            <el-input-number v-model="settings.phase2.db_commit_batch_size" :min="1" :max="10000" :step="10" controls-position="right" />
            <p class="vdf-sub-hint">Recommended: 100</p>
          </div>
          <div class="vdf-perf-item">
            <label>Progress Update Interval</label>
            <el-input-number v-model="settings.phase2.progress_update_interval" :min="1" :max="10000" :step="10" controls-position="right" />
            <p class="vdf-sub-hint">Recommended: 100</p>
          </div>
          <div class="vdf-perf-item">
            <label>IPC Chunk Size</label>
            <el-input-number v-model="settings.phase2.ipc_chunk_size" :min="1" :max="1000" controls-position="right" />
            <p class="vdf-sub-hint">Recommended: 10</p>
          </div>
          <div class="vdf-perf-item">
            <label>Compare Delay (s)</label>
            <el-input-number v-model="settings.phase2.compare_delay" :min="0" :max="5" :step="0.1" :precision="1" controls-position="right" />
            <p class="vdf-sub-hint">0 = no delay</p>
          </div>
        </div>
      </section>

      <!-- Advanced Paths -->
      <section class="vdf-card">
        <div class="vdf-card-header">
          <h2>Advanced Paths</h2>
          <p class="vdf-hint">Leave blank to use default locations. ffmpeg is read-only (edit settings.json directly).</p>
        </div>
        <div class="vdf-card-body">
          <div class="vdf-row">
            <label class="vdf-label">Video DB path</label>
            <el-input v-model="settings.video_db_path" placeholder="video_hash_cache.db (blank = default)" spellcheck="false" />
          </div>
          <div class="vdf-row">
            <label class="vdf-label">Thumbnail cache dir</label>
            <el-input v-model="settings.thumbnail_cache_dir" placeholder="Thumbnails dir (blank = default)" spellcheck="false" />
          </div>
          <div class="vdf-row">
            <label class="vdf-label">ffmpeg path (read-only)</label>
            <el-input :model-value="settings.ffmpeg_path || ''" placeholder="imageio_ffmpeg bundled" disabled />
          </div>
        </div>
      </section>

    </main>
  </div>
</template>

<script lang="ts" src="@/video-duplicate-finder/views/SettingsView.ts"></script>

<style scoped>
.vdf-settings {
  min-height: 100vh;
  background: #f5f5f7;
  color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}
.vdf-topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(245,245,247,0.85);
  backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid rgba(0,0,0,0.06);
  padding: 12px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.vdf-topbar-left { display: flex; align-items: baseline; gap: 16px; }
.vdf-back { color: #0071e3; }
.vdf-topbar h1 { font-size: 17px; font-weight: 600; margin: 0; }
.vdf-topbar-right { display: flex; align-items: center; gap: 8px; }
.vdf-content {
  max-width: 820px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.vdf-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
  overflow: hidden;
}
.vdf-card-header { padding: 16px 20px 8px; }
.vdf-card-header h2 { font-size: 15px; font-weight: 600; margin: 0 0 4px; }
.vdf-hint { font-size: 12px; color: #86868b; margin: 0; }
.vdf-card-body {
  padding: 8px 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.vdf-row {
  display: grid;
  grid-template-columns: 200px 1fr;
  align-items: center;
  gap: 12px;
}
.vdf-label { font-size: 13px; color: #1d1d1f; }
.vdf-row-switch { display: flex; align-items: center; gap: 10px; }
.vdf-row-switch label { font-size: 13px; color: #1d1d1f; }
.vdf-group { display: flex; flex-direction: column; gap: 6px; }
.vdf-group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  color: #1d1d1f;
}
.vdf-empty { font-size: 12px; color: #b0b0b6; font-style: italic; margin: 0; }
.vdf-sub-hint { font-size: 11px; color: #86868b; margin: 0; }
.path-list { display: flex; flex-direction: column; gap: 8px; }
.path-row { display: flex; gap: 8px; align-items: center; }
.path-row .el-input { flex: 1; }
.vdf-perf-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.vdf-perf-item { display: flex; flex-direction: column; gap: 4px; }
.vdf-perf-item label { font-size: 12px; color: #606266; font-weight: 500; }
@media (max-width: 600px) {
  .vdf-row { grid-template-columns: 1fr; }
  .vdf-perf-grid { grid-template-columns: 1fr 1fr; }
}
</style>
