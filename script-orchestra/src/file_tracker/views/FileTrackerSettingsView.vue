<template>
  <div class="fts-root">
    <div class="fts-header">
      <el-button type="default" size="small" @click="goBack">← Back</el-button>
      <h2 class="fts-title">File Tracker — Settings</h2>
    </div>

    <!-- Scan Paths -->
    <el-card class="fts-card">
      <template #header><span class="fts-card-title">Scan Paths</span></template>
      <div class="fts-paths">
        <div v-for="p in settings.scan_paths" :key="p" class="fts-path-row">
          <span class="fts-path-text">{{ p }}</span>
          <el-button size="small" type="danger" plain circle @click="removePath(p)">✕</el-button>
        </div>
        <div v-if="!settings.scan_paths.length" class="fts-empty-hint">No paths configured.</div>
      </div>
      <div class="fts-add-row">
        <el-input v-model="newPath" placeholder="/absolute/path/to/scan" size="small" style="flex:1" @keyup.enter="addPath" />
        <el-button size="small" type="primary" @click="addPath">Add</el-button>
      </div>
    </el-card>

    <!-- Ignore Patterns -->
    <el-card class="fts-card">
      <template #header><span class="fts-card-title">Ignore Patterns</span></template>
      <div class="fts-tags">
        <el-tag v-for="p in settings.ignore_patterns" :key="p" closable @close="removePattern(p)" class="fts-tag" size="small">{{ p }}</el-tag>
      </div>
      <div class="fts-add-row" style="margin-top:10px">
        <el-input v-model="newPattern" placeholder="e.g. node_modules or *.log" size="small" style="flex:1" @keyup.enter="addPattern" />
        <el-button size="small" type="primary" @click="addPattern">Add</el-button>
      </div>
    </el-card>

    <!-- Timestamp Rules -->
    <el-card class="fts-card">
      <template #header>
        <div class="fts-card-header-row">
          <span class="fts-card-title">Timestamp Rules</span>
          <el-button size="small" @click="addRule">+ Add Rule</el-button>
        </div>
      </template>
      <p class="fts-desc">
        Rules are evaluated top-to-bottom; first match wins.<br>
        <b>last_used</b> = macOS <code>kMDItemLastUsedDate</code> (when you last opened the file), fallback to mtime.<br>
        <b>mtime</b> = last modification time.
      </p>
      <div
        v-for="(rule, i) in settings.timestamp_rules"
        :key="i"
        class="fts-rule-row"
      >
        <div class="fts-rule-order">
          <el-button size="small" text @click="moveRule(i, -1)" :disabled="i === 0">↑</el-button>
          <el-button size="small" text @click="moveRule(i, 1)" :disabled="i === settings.timestamp_rules.length - 1">↓</el-button>
        </div>
        <div class="fts-rule-body">
          <div class="fts-rule-exts">
            <el-tag
              v-for="ext in rule.extensions"
              :key="ext"
              size="small"
              closable
              class="fts-tag"
              @close="removeExt(i, ext)"
            >{{ ext }}</el-tag>
            <div class="fts-rule-add-ext">
              <el-input
                v-model="newExt[i]"
                placeholder=".jpg or *"
                size="small"
                style="width: 100px"
                @keyup.enter="addExt(i)"
              />
              <el-button size="small" @click="addExt(i)">+</el-button>
            </div>
          </div>
          <el-select v-model="rule.source" size="small" style="width: 120px">
            <el-option value="last_used" label="last_used" />
            <el-option value="mtime" label="mtime" />
          </el-select>
        </div>
        <el-button size="small" type="danger" text @click="removeRule(i)">Remove</el-button>
      </div>
      <div v-if="!settings.timestamp_rules.length" class="fts-empty-hint">No rules configured. Add a rule or save to load defaults.</div>
    </el-card>

    <!-- Stale Thresholds -->
    <el-card class="fts-card">
      <template #header><span class="fts-card-title">Stale Thresholds (days)</span></template>
      <el-form label-width="160px" size="small">
        <el-form-item label="Archive threshold">
          <el-input-number v-model="settings.stale_thresholds_days.archive" :min="1" :max="3650" style="width:160px" />
          <span class="fts-hint">Shown as orange</span>
        </el-form-item>
        <el-form-item label="Warn threshold">
          <el-input-number v-model="settings.stale_thresholds_days.warn" :min="1" :max="3650" style="width:160px" />
          <span class="fts-hint">Shown as yellow</span>
        </el-form-item>
        <el-form-item label="Danger threshold">
          <el-input-number v-model="settings.stale_thresholds_days.danger" :min="1" :max="3650" style="width:160px" />
          <span class="fts-hint">Shown as red</span>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Maintenance -->
    <el-card class="fts-card">
      <template #header><span class="fts-card-title">Maintenance</span></template>
      <p class="fts-desc">Remove DB entries for files that no longer exist on disk.</p>
      <el-button type="warning" size="small" :loading="pruneLoading" @click="pruneDeleted">Prune deleted files from DB</el-button>
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
.fts-root { width: 100%; min-height: 100vh; padding: 24px 28px; box-sizing: border-box; max-width: 800px; }
.fts-header { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; }
.fts-title { margin: 0; font-size: 20px; font-weight: 700; }
.fts-card { margin-bottom: 16px; }
.fts-card-title { font-size: 14px; font-weight: 600; }
.fts-card-header-row { display: flex; align-items: center; justify-content: space-between; width: 100%; }

.fts-paths { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.fts-path-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.fts-path-text { flex: 1; font-family: monospace; font-size: 13px; color: #303133; word-break: break-all; }
.fts-empty-hint { font-size: 13px; color: #909399; padding: 4px 0; }

.fts-add-row { display: flex; gap: 8px; align-items: center; }
.fts-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.fts-tag { font-family: monospace; }

.fts-desc { font-size: 13px; color: #606266; margin-bottom: 12px; line-height: 1.6; }
.fts-hint { font-size: 12px; color: #909399; margin-left: 8px; }
.fts-footer { padding: 8px 0 24px; }

/* Timestamp rule rows */
.fts-rule-row {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 10px 0; border-bottom: 1px solid #f0f0f0;
}
.fts-rule-row:last-child { border-bottom: none; }
.fts-rule-order { display: flex; flex-direction: column; gap: 0; flex-shrink: 0; }
.fts-rule-body { flex: 1; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.fts-rule-exts { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; flex: 1; min-width: 200px; }
.fts-rule-add-ext { display: flex; gap: 4px; align-items: center; }
</style>
