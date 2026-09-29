<template>
  <div class="df-settings">
    <header class="df-topbar">
      <div class="df-topbar-left">
        <el-button link @click="goBack" class="df-back">
          <el-icon><ArrowLeft /></el-icon>
          <span>Duplicate Finder</span>
        </el-button>
        <h1>Settings</h1>
      </div>
      <div class="df-topbar-right">
        <el-button :icon="Refresh" @click="load" :loading="loading" text />
        <el-button type="primary" @click="save" :loading="saving">Save</el-button>
      </div>
    </header>

    <main class="df-content">

      <!-- Scan Folders -->
      <section class="df-card">
        <div class="df-card-header">
          <h2>Scan Folders</h2>
          <p class="df-hint">Directories to scan for duplicate images.</p>
        </div>
        <div class="df-card-body">
          <div v-if="settings.folder_paths && settings.folder_paths.length" class="path-list">
            <div v-for="(_, i) in settings.folder_paths" :key="`fp-${i}`" class="path-row">
              <el-input :model-value="settings.folder_paths?.[i]" @update:model-value="val => { if (settings.folder_paths) settings.folder_paths[i] = val }" placeholder="/absolute/path/to/folder" spellcheck="false" />
              <el-button type="danger" plain size="default" @click="removeFolderPath(i)">Remove</el-button>
            </div>
          </div>
          <p v-else class="df-empty">No folders configured.</p>
          <el-button size="small" @click="addFolderPath">+ Add Folder</el-button>
        </div>
      </section>

      <!-- Exclude Folders -->
      <section class="df-card">
        <div class="df-card-header">
          <h2>Exclude Folders</h2>
          <p class="df-hint">Subdirectories to skip during scanning.</p>
        </div>
        <div class="df-card-body">
          <div v-if="settings.exclude_folder_paths && settings.exclude_folder_paths.length" class="path-list">
            <div v-for="(_, i) in settings.exclude_folder_paths" :key="`ex-${i}`" class="path-row">
              <el-input :model-value="settings.exclude_folder_paths?.[i]" @update:model-value="val => { if (settings.exclude_folder_paths) settings.exclude_folder_paths[i] = val }" placeholder="/path/to/exclude" spellcheck="false" />
              <el-button type="danger" plain size="default" @click="removeExcludePath(i)">Remove</el-button>
            </div>
          </div>
          <p v-else class="df-empty">No exclude folders configured.</p>
          <el-button size="small" @click="addExcludePath">+ Add Exclude Folder</el-button>
        </div>
      </section>

      <!-- Core Settings -->
      <section class="df-card">
        <div class="df-card-header">
          <h2>Core Settings</h2>
        </div>
        <div class="df-card-body">
          <div class="df-row">
            <label class="df-label">Delete target path</label>
            <el-input v-model="settings.delete_target_path" placeholder="/path/to/trash" spellcheck="false" />
          </div>
          <div class="df-row">
            <label class="df-label">PHash DB path</label>
            <el-input v-model="settings.phash_db_path" placeholder="/path/to/phash_cache.db (blank = default)" spellcheck="false" />
          </div>
          <div class="df-row">
            <label class="df-label">Similarity threshold: {{ threshold }}%</label>
            <el-slider v-model="threshold" :min="60" :max="100" show-stops />
          </div>
          <div class="df-row">
            <label class="df-label">Max CPU cores: {{ settings.max_cpu_cores || 1 }} / {{ settings.system_cpu_count || '?' }}</label>
            <el-slider
              v-model="settings.max_cpu_cores"
              :min="1"
              :max="settings.system_cpu_count || 12"
              :step="1"
              :marks="getCpuMarks()"
              show-stops
            />
          </div>
          <div class="df-row">
            <label class="df-label">Page size (groups/page)</label>
            <el-input-number
              v-model="settings.page_size"
              :min="20"
              :max="500"
              :step="10"
              controls-position="right"
            />
          </div>
        </div>
      </section>

      <!-- Performance — Phase 1 -->
      <section class="df-card">
        <div class="df-card-header">
          <h2>Performance — Phase 1 (Scan &amp; Hash)</h2>
          <p class="df-hint">Tune batch sizes and optional delays to control CPU/disk load.</p>
        </div>
        <div class="df-card-body df-perf-grid">
          <div class="df-perf-item">
            <label>Worker Handler Size</label>
            <el-input-number v-model="settings.phase1.worker_handler_size" :min="1" :max="100" controls-position="right" />
            <p class="df-sub-hint">Recommended: 1</p>
          </div>
          <div class="df-perf-item">
            <label>DB Commit Batch</label>
            <el-input-number v-model="settings.phase1.db_commit_batch_size" :min="1" :max="10000" :step="10" controls-position="right" />
            <p class="df-sub-hint">Recommended: 100</p>
          </div>
          <div class="df-perf-item">
            <label>Progress Update Interval</label>
            <el-input-number v-model="settings.phase1.progress_update_interval" :min="1" :max="10000" :step="10" controls-position="right" />
            <p class="df-sub-hint">Recommended: 100</p>
          </div>
          <div class="df-perf-item">
            <label>IPC Chunk Size</label>
            <el-input-number v-model="settings.phase1.ipc_chunk_size" :min="1" :max="1000" controls-position="right" />
            <p class="df-sub-hint">Recommended: 10</p>
          </div>
          <div class="df-perf-item">
            <label>Scan Delay (s)</label>
            <el-input-number v-model="settings.phase1.scan_delay" :min="0" :max="5" :step="0.1" :precision="1" controls-position="right" />
            <p class="df-sub-hint">0 = no delay</p>
          </div>
          <div class="df-perf-item">
            <label>Compute Delay (s)</label>
            <el-input-number v-model="settings.phase1.compute_delay" :min="0" :max="5" :step="0.1" :precision="1" controls-position="right" />
            <p class="df-sub-hint">0 = no delay</p>
          </div>
        </div>
      </section>

      <!-- Performance — Phase 2 -->
      <section class="df-card">
        <div class="df-card-header">
          <h2>Performance — Phase 2 (Compare)</h2>
        </div>
        <div class="df-card-body df-perf-grid">
          <div class="df-perf-item">
            <label>Worker Handler Size</label>
            <el-input-number v-model="settings.phase2.worker_handler_size" :min="1" :max="100" controls-position="right" />
            <p class="df-sub-hint">Recommended: 1</p>
          </div>
          <div class="df-perf-item">
            <label>DB Commit Batch</label>
            <el-input-number v-model="settings.phase2.db_commit_batch_size" :min="1" :max="10000" :step="10" controls-position="right" />
            <p class="df-sub-hint">Recommended: 100</p>
          </div>
          <div class="df-perf-item">
            <label>Progress Update Interval</label>
            <el-input-number v-model="settings.phase2.progress_update_interval" :min="1" :max="10000" :step="10" controls-position="right" />
            <p class="df-sub-hint">Recommended: 100</p>
          </div>
          <div class="df-perf-item">
            <label>IPC Chunk Size</label>
            <el-input-number v-model="settings.phase2.ipc_chunk_size" :min="1" :max="1000" controls-position="right" />
            <p class="df-sub-hint">Recommended: 10</p>
          </div>
          <div class="df-perf-item">
            <label>Compare Delay (s)</label>
            <el-input-number v-model="settings.phase2.compare_delay" :min="0" :max="5" :step="0.1" :precision="1" controls-position="right" />
            <p class="df-sub-hint">0 = no delay</p>
          </div>
        </div>
      </section>

      <!-- Auto-Selection Rules -->
      <section class="df-card">
        <div class="df-card-header">
          <h2>Auto-Selection Rules</h2>
          <p class="df-hint">Automatically mark files for deletion based on naming patterns.</p>
        </div>
        <div class="df-card-body">
          <div class="df-row-check">
            <el-checkbox v-model="settings.auto_selection_rules.auto_mark_numbered_copies">
              Auto-mark numbered copies
            </el-checkbox>
            <p class="df-sub-hint">Selects <code>photo(1).jpg</code>, <code>photo(2).jpg</code> — keeps <code>photo.jpg</code></p>
          </div>
          <div class="df-row-check">
            <el-checkbox v-model="settings.auto_selection_rules.auto_mark_copy_suffix">
              Auto-mark "copy" suffix
            </el-checkbox>
            <p class="df-sub-hint">Selects <code>photo_copy.jpg</code>, <code>photo-copy.jpg</code>, etc.</p>
          </div>
          <div class="df-group">
            <div class="df-group-header">
              <span>Prefer folders</span>
              <el-button size="small" text @click="addPreferFolder">+ Add</el-button>
            </div>
            <p class="df-hint" style="margin-bottom: 8px;">Files in these folders are kept; others are marked for deletion.</p>
            <div v-if="settings.auto_selection_rules.prefer_folders && settings.auto_selection_rules.prefer_folders.length" class="path-list">
              <div v-for="(_, i) in settings.auto_selection_rules.prefer_folders" :key="`pf-${i}`" class="path-row">
                <el-input :model-value="settings.auto_selection_rules.prefer_folders?.[i]" @update:model-value="val => { if (settings.auto_selection_rules.prefer_folders) settings.auto_selection_rules.prefer_folders[i] = val }" placeholder="/path/to/preferred" spellcheck="false" />
                <el-button type="danger" plain size="default" @click="removePreferFolder(i)">Remove</el-button>
              </div>
            </div>
            <p v-else class="df-empty">No preferred folders.</p>
          </div>
        </div>
      </section>

      <!-- Gap Analysis -->
      <section class="df-card">
        <div class="df-card-header">
          <h2>Gap Analysis</h2>
          <p class="df-hint">Settings for detecting missed duplicate pairs.</p>
        </div>
        <div class="df-card-body">
          <div class="df-row">
            <label class="df-label">Auto-trigger threshold (%)</label>
            <el-input-number
              v-model="settings.gap_analysis_selection_threshold"
              :min="50"
              :max="100"
              :step="5"
              controls-position="right"
            />
            <p class="df-sub-hint">When this % of a folder's images are already detected as duplicates during deep delete preview, gap analysis triggers automatically. Default: 80</p>
          </div>
          <div class="df-row">
            <label class="df-label">Lower similarity bound (%)</label>
            <el-input-number
              v-model="settings.gap_analysis_lower_similarity"
              :min="30"
              :max="100"
              :step="5"
              controls-position="right"
            />
            <p class="df-sub-hint">Minimum similarity % for a pair to appear as a gap candidate. Lower = more results but more false positives. Default: 60</p>
          </div>
        </div>
      </section>

      <!-- Whitelist -->
      <section class="df-card">
        <div class="df-card-header">
          <h2>Whitelist</h2>
          <p class="df-hint">Whitelisted groups are excluded from future scans. Changes take effect immediately (no Save needed).</p>
        </div>
        <div class="df-card-body">
          <el-button @click="loadWhitelistGroups" :loading="isLoadingWhitelist">Refresh Whitelist</el-button>
          <div v-if="whitelistGroups.length" class="wl-list">
            <div v-for="(group, i) in whitelistGroups" :key="group.group_id" class="wl-group">
              <div class="wl-group-header">
                <span class="wl-group-title">Group {{ group.group_id }} ({{ group.members.length }} images)</span>
                <span class="wl-group-time">{{ formatTimestamp(group.added_time) }}</span>
                <el-button type="danger" size="small" @click="removeWhitelistGroup(group.group_id, i)">Remove</el-button>
              </div>
              <div class="wl-thumbs">
                <div v-for="m in group.members" :key="m.image_id" class="wl-thumb">
                  <img :src="getImageUrl(m.file_path)" :alt="m.filename" class="wl-thumb-img" />
                  <p class="wl-thumb-name">{{ m.filename }}</p>
                </div>
              </div>
            </div>
          </div>
          <el-empty v-else-if="!isLoadingWhitelist" description="No whitelisted groups" />
        </div>
      </section>

    </main>
  </div>
</template>

<script lang="ts" src="@/duplicate_finder/views/SettingsView.ts"></script>

<style scoped>
.df-settings {
  min-height: 100vh;
  background: #f5f5f7;
  color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}
.df-topbar {
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
.df-topbar-left { display: flex; align-items: baseline; gap: 16px; }
.df-back { color: #0071e3; }
.df-topbar h1 { font-size: 17px; font-weight: 600; margin: 0; }
.df-topbar-right { display: flex; align-items: center; gap: 8px; }
.df-content {
  max-width: 820px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.df-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
  overflow: hidden;
}
.df-card-header { padding: 16px 20px 8px; }
.df-card-header h2 { font-size: 15px; font-weight: 600; margin: 0 0 4px; }
.df-hint { font-size: 12px; color: #86868b; margin: 0; }
.df-card-body {
  padding: 8px 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.df-row {
  display: grid;
  grid-template-columns: 220px 1fr;
  align-items: center;
  gap: 12px;
}
.df-label { font-size: 13px; color: #1d1d1f; }
.df-row-check { display: flex; flex-direction: column; gap: 4px; }
.df-sub-hint { font-size: 11px; color: #86868b; margin: 0; padding-left: 2px; }
.df-empty { font-size: 12px; color: #b0b0b6; font-style: italic; margin: 0; }
.df-group { display: flex; flex-direction: column; gap: 6px; }
.df-group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  color: #1d1d1f;
}
.path-list { display: flex; flex-direction: column; gap: 8px; }
.path-row { display: flex; gap: 8px; align-items: center; }
.path-row .el-input { flex: 1; }
.df-perf-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.df-perf-item { display: flex; flex-direction: column; gap: 4px; }
.df-perf-item label { font-size: 12px; color: #606266; font-weight: 500; }
/* Whitelist */
.wl-list { display: flex; flex-direction: column; gap: 12px; margin-top: 12px; }
.wl-group {
  background: #f9f9fb;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
}
.wl-group-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.wl-group-title { font-size: 13px; font-weight: 600; flex: 1; }
.wl-group-time { font-size: 11px; color: #86868b; }
.wl-thumbs { display: flex; flex-wrap: wrap; gap: 8px; }
.wl-thumb { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.wl-thumb-img { width: 60px; height: 60px; object-fit: cover; border-radius: 4px; border: 1px solid #ebeef5; }
.wl-thumb-name { font-size: 10px; color: #86868b; max-width: 60px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 600px) {
  .df-row { grid-template-columns: 1fr; }
  .df-perf-grid { grid-template-columns: 1fr 1fr; }
}
</style>
