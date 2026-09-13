<template>
  <div class="fts-root">
    <div class="fts-header">
      <el-button type="default" size="small" @click="goBack">← Back</el-button>
      <h2 class="fts-title">File Tracker — Settings</h2>
    </div>

    <!-- Scan Paths -->
    <el-card class="fts-card">
      <template #header><span class="fts-card-title">📁 Scan Paths</span></template>
      <div class="fts-paths">
        <div v-for="p in settings.scan_paths" :key="p" class="fts-path-row">
          <span class="fts-path-text">{{ p }}</span>
          <el-button size="small" type="danger" plain circle @click="removePath(p)" title="Remove">✕</el-button>
        </div>
        <div v-if="!settings.scan_paths.length" class="fts-empty-hint">No paths configured.</div>
      </div>
      <div class="fts-add-row">
        <el-input
          v-model="newPath"
          placeholder="/absolute/path/to/scan"
          size="small"
          style="flex:1"
          @keyup.enter="addPath"
        />
        <el-button size="small" type="primary" @click="addPath">Add</el-button>
      </div>
    </el-card>

    <!-- Ignore Patterns -->
    <el-card class="fts-card">
      <template #header><span class="fts-card-title">🚫 Ignore Patterns</span></template>
      <div class="fts-tags">
        <el-tag
          v-for="p in settings.ignore_patterns"
          :key="p"
          closable
          @close="removePattern(p)"
          class="fts-tag"
          size="small"
        >{{ p }}</el-tag>
      </div>
      <div class="fts-add-row" style="margin-top:10px">
        <el-input
          v-model="newPattern"
          placeholder="e.g. node_modules or *.log"
          size="small"
          style="flex:1"
          @keyup.enter="addPattern"
        />
        <el-button size="small" type="primary" @click="addPattern">Add</el-button>
      </div>
    </el-card>

    <!-- Stale Thresholds -->
    <el-card class="fts-card">
      <template #header><span class="fts-card-title">⏱ Stale Thresholds (days)</span></template>
      <el-form label-width="160px" size="small">
        <el-form-item label="Archive threshold">
          <el-input-number
            v-model="settings.stale_thresholds_days.archive"
            :min="1" :max="3650"
            style="width:160px"
          />
          <span class="fts-hint">Files older than this shown as 🟠</span>
        </el-form-item>
        <el-form-item label="Warn threshold">
          <el-input-number
            v-model="settings.stale_thresholds_days.warn"
            :min="1" :max="3650"
            style="width:160px"
          />
          <span class="fts-hint">Files older than this shown as 🟡</span>
        </el-form-item>
        <el-form-item label="Danger threshold">
          <el-input-number
            v-model="settings.stale_thresholds_days.danger"
            :min="1" :max="3650"
            style="width:160px"
          />
          <span class="fts-hint">Files older than this shown as 🔴</span>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Maintenance -->
    <el-card class="fts-card">
      <template #header><span class="fts-card-title">🧹 Maintenance</span></template>
      <p class="fts-desc">Remove DB entries for files that no longer exist on disk (e.g. after manual deletion).</p>
      <el-button type="warning" size="small" :loading="pruneLoading" @click="pruneDeleted">
        Prune deleted files from DB
      </el-button>
    </el-card>

    <!-- Save -->
    <div class="fts-footer">
      <el-button type="primary" :loading="saving" @click="save">Save Settings</el-button>
    </div>
  </div>
</template>

<script lang="ts">
import FileTrackerSettingsLogic from './FileTrackerSettingsView.ts'
export default FileTrackerSettingsLogic
</script>

<style scoped>
.fts-root { min-height: 100vh; padding: 24px 28px; box-sizing: border-box; max-width: 760px; }
.fts-header { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; }
.fts-title { margin: 0; font-size: 20px; font-weight: 700; }
.fts-card { margin-bottom: 16px; }
.fts-card-title { font-size: 14px; font-weight: 600; }

.fts-paths { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.fts-path-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.fts-path-text { flex: 1; font-family: monospace; font-size: 13px; color: #303133; word-break: break-all; }
.fts-empty-hint { font-size: 13px; color: #909399; padding: 4px 0; }

.fts-add-row { display: flex; gap: 8px; align-items: center; }

.fts-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.fts-tag { font-family: monospace; }

.fts-hint { font-size: 12px; color: #909399; margin-left: 8px; }
.fts-desc { font-size: 13px; color: #606266; margin-bottom: 10px; }

.fts-footer { padding: 8px 0 24px; }
</style>
