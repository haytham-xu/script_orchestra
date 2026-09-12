<template>
  <div class="sg-root">
    <div class="sg-header">
      <el-button type="default" size="small" @click="$router.push('/manga-viewer/hub')">← Back</el-button>
      <h2 class="sg-title">Series Grouper</h2>
    </div>

    <!-- Settings card -->
    <el-card class="sg-card">
      <template #header>
        <div class="sg-card-header">
          <span>⚙️ Settings</span>
          <el-button
            type="primary"
            size="small"
            :loading="savingSettings"
            @click="saveSettings"
          >Save</el-button>
        </div>
      </template>

      <el-form label-width="130px">
        <el-form-item label="Scan Paths">
          <div class="sg-path-list">
            <div
              v-for="(_, i) in settings.scan_paths"
              :key="'sp-' + i"
              class="sg-path-row"
            >
              <el-input
                v-model="settings.scan_paths[i]"
                placeholder="/path/to/scan"
                @input="settingsDirty = true"
              />
              <el-button
                type="danger"
                size="small"
                plain
                @click="removeScanPath(i)"
              >✕</el-button>
            </div>
            <el-button size="small" @click="addScanPath">+ Add Path</el-button>
          </div>
          <div class="sg-hint">Each path is scanned one level deep (immediate subdirectories only).</div>
        </el-form-item>

        <el-form-item label="Output Path">
          <el-input
            v-model="settings.output_path"
            placeholder="/path/to/output"
            @input="settingsDirty = true"
          />
          <div class="sg-hint">Series folders are created here. Each series gets its own subfolder.</div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Scan action -->
    <div class="sg-actions">
      <el-button
        type="primary"
        :loading="scanning"
        :disabled="!settings.scan_paths.some(p => p.trim())"
        @click="scan"
      >🔍 Scan</el-button>
      <span v-if="groups.length" class="sg-summary">
        {{ groups.length }} series found ({{ groups.reduce((n, g) => n + g.folders.length, 0) }} folders total)
      </span>
    </div>

    <!-- Results -->
    <el-card v-if="groups.length" class="sg-card">
      <template #header>
        <div class="sg-card-header">
          <span>📦 Proposed Groups</span>
          <div class="sg-header-right">
            <el-button size="small" @click="toggleAll(true)">Select All</el-button>
            <el-button size="small" @click="toggleAll(false)">Deselect All</el-button>
            <el-button
              type="success"
              size="small"
              :loading="executing"
              :disabled="!groups.some(g => g.selected)"
              @click="execute"
            >▶ Execute Move</el-button>
          </div>
        </div>
      </template>

      <div class="sg-group-list">
        <div
          v-for="g in groups"
          :key="g.key"
          class="sg-group"
          :class="{ 'sg-group--deselected': !g.selected }"
        >
          <div class="sg-group-top">
            <el-checkbox v-model="g.selected" class="sg-check" />
            <div class="sg-group-meta">
              <div class="sg-group-name-row">
                <span class="sg-group-key">{{ g.key }}</span>
                <span class="sg-group-count">{{ g.folders.length }} folders</span>
              </div>
              <div class="sg-target-row">
                <span class="sg-target-label">Target folder name:</span>
                <el-input
                  v-model="g.target_name"
                  size="small"
                  class="sg-target-input"
                />
              </div>
            </div>
          </div>
          <div class="sg-folder-list">
            <div
              v-for="f in g.folders"
              :key="f"
              class="sg-folder-item"
            >{{ f }}</div>
          </div>
        </div>
      </div>
    </el-card>

    <div v-else-if="!scanning" class="sg-empty">
      Configure scan paths above and press <strong>Scan</strong> to find series groups.
    </div>
  </div>
</template>

<script lang="ts">
import SeriesGrouperLogic from './SeriesGrouperView.ts'
export default SeriesGrouperLogic
</script>

<style scoped>
.sg-root { min-height: 100vh; padding: 28px 32px; box-sizing: border-box; }
.sg-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.sg-title { margin: 0; font-size: 22px; font-weight: 600; }

.sg-card { margin-bottom: 20px; }
.sg-card-header { display: flex; align-items: center; justify-content: space-between; }
.sg-header-right { display: flex; gap: 8px; align-items: center; }

.sg-hint { font-size: 12px; color: #909399; margin-top: 4px; }

.sg-path-list { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.sg-path-row { display: flex; gap: 8px; align-items: center; }
.sg-path-row .el-input { flex: 1; }

.sg-actions { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.sg-summary { font-size: 14px; color: #606266; }

.sg-group-list { display: flex; flex-direction: column; gap: 12px; }
.sg-group {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px 16px;
  background: #fafafa;
  transition: opacity 0.2s;
}
.sg-group--deselected { opacity: 0.45; }
.sg-group-top { display: flex; align-items: flex-start; gap: 12px; }
.sg-check { margin-top: 2px; flex-shrink: 0; }
.sg-group-meta { flex: 1; min-width: 0; }
.sg-group-name-row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.sg-group-key { font-weight: 600; font-size: 14px; color: #303133; }
.sg-group-count { font-size: 12px; color: #909399; background: #f0f0f0; padding: 1px 7px; border-radius: 10px; }
.sg-target-row { display: flex; align-items: center; gap: 8px; }
.sg-target-label { font-size: 12px; color: #606266; white-space: nowrap; }
.sg-target-input { width: 360px; }

.sg-folder-list { margin-top: 10px; padding-left: 36px; display: flex; flex-direction: column; gap: 2px; }
.sg-folder-item { font-size: 12px; color: #606266; font-family: monospace; word-break: break-all; }

.sg-empty { text-align: center; color: #909399; font-size: 14px; padding: 48px 0; }
</style>
