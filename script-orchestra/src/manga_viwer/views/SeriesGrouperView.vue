<template>
  <div class="sg-root">
    <div class="sg-header">
      <el-button type="default" size="small" @click="$router.push('/manga-viewer/batch')">← Back</el-button>
      <h2 class="sg-title">Series Grouper</h2>
      <el-button type="default" size="small" @click="goSettings">⚙️ Settings</el-button>
    </div>

    <!-- Action bar -->
    <div class="sg-toolbar">
      <div class="sg-paths-empty" v-if="!settings.scan_paths.filter(p => p.trim()).length">
        No scan paths configured — <el-button type="primary" link @click="goSettings">open Settings</el-button>
      </div>
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
        <span>📦 Proposed Groups</span>
      </template>

      <div class="sg-group-list">
        <div
          v-for="g in groups"
          :key="g.key"
          class="sg-group"
        >
          <!-- Group header row -->
          <div class="sg-group-top">
            <div class="sg-group-meta">
              <div class="sg-group-name-row">
                <span class="sg-group-key">{{ g.key }}</span>
                <span class="sg-group-count">{{ g.folders.length }} folders</span>
              </div>
              <div class="sg-target-row">
                <span class="sg-target-label">Target folder name:</span>
                <el-input v-model="g.target_name" size="small" class="sg-target-input" />
              </div>
            </div>

            <!-- Per-group action buttons -->
            <div class="sg-group-actions">
              <el-button
                type="success"
                size="small"
                :loading="g.executing"
                @click="executeGroup(g)"
              >▶ Execute</el-button>
              <el-button
                size="small"
                plain
                @click="startMerge(g)"
                :type="g.mergeTarget !== null ? 'warning' : 'default'"
              >⛙ Merge</el-button>
              <el-button
                type="danger"
                size="small"
                plain
                @click="addToWhitelist(g)"
              >🚫 Whitelist</el-button>
            </div>
          </div>

          <!-- Merge selector (shown when merge mode active) -->
          <div v-if="g.mergeTarget !== null" class="sg-merge-bar">
            <span class="sg-merge-label">Merge with:</span>
            <el-select
              v-model="g.mergeTarget"
              placeholder="Select a group"
              size="small"
              style="width: 320px"
              filterable
            >
              <el-option
                v-for="other in otherGroups(g.key)"
                :key="other.key"
                :label="`${other.key} (${other.folders.length})`"
                :value="other.key"
              />
            </el-select>
            <el-button
              size="small"
              type="warning"
              :disabled="!g.mergeTarget"
              @click="confirmMerge(g)"
            >Confirm Merge</el-button>
            <el-button size="small" @click="g.mergeTarget = null">Cancel</el-button>
          </div>

          <!-- Folder list -->
          <div class="sg-folder-list">
            <div v-for="f in g.folders" :key="f" class="sg-folder-item">
              <span class="sg-folder-path">{{ f }}</span>
              <el-button size="small" plain @click="openFolder(f)" class="sg-open-btn">📂</el-button>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <div v-else-if="!scanning" class="sg-empty">
      Configure scan paths in <el-button type="primary" link @click="goSettings">Settings</el-button>, then press <strong>Scan</strong>.
    </div>
  </div>
</template>

<script lang="ts">
import SeriesGrouperLogic from './SeriesGrouperView.ts'
export default SeriesGrouperLogic
</script>

<style scoped>
.sg-root { min-height: 100vh; padding: 28px 32px; box-sizing: border-box; }
.sg-header { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
.sg-title { margin: 0; font-size: 22px; font-weight: 600; flex: 1; }

.sg-toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
.sg-paths-empty { font-size: 13px; color: #909399; flex: 1; }
.sg-summary { font-size: 14px; color: #606266; white-space: nowrap; }

.sg-card { margin-bottom: 20px; }

.sg-group-list { display: flex; flex-direction: column; gap: 12px; }
.sg-group {
  border: 1px solid #e4e7ed; border-radius: 8px;
  padding: 12px 16px; background: #fafafa;
}
.sg-group-top { display: flex; align-items: flex-start; gap: 12px; }
.sg-group-meta { flex: 1; min-width: 0; }
.sg-group-name-row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.sg-group-key { font-weight: 600; font-size: 14px; color: #303133; }
.sg-group-count { font-size: 12px; color: #909399; background: #f0f0f0; padding: 1px 7px; border-radius: 10px; }
.sg-target-row { display: flex; align-items: center; gap: 8px; }
.sg-target-label { font-size: 12px; color: #606266; white-space: nowrap; }
.sg-target-input { width: 360px; }

.sg-group-actions { display: flex; gap: 6px; align-items: flex-start; flex-shrink: 0; }

.sg-merge-bar {
  display: flex; align-items: center; gap: 8px;
  margin: 10px 0 6px; padding: 8px 12px;
  background: #fdf6ec; border: 1px solid #f5a623; border-radius: 6px;
}
.sg-merge-label { font-size: 13px; color: #606266; white-space: nowrap; }

.sg-folder-list { margin-top: 10px; padding-left: 4px; display: flex; flex-direction: column; gap: 4px; }
.sg-folder-item { display: flex; align-items: center; gap: 8px; }
.sg-folder-path { font-size: 12px; color: #606266; font-family: monospace; word-break: break-all; flex: 1; }
.sg-open-btn { flex-shrink: 0; padding: 2px 6px; }

.sg-empty { text-align: center; color: #909399; font-size: 14px; padding: 48px 0; }
</style>
