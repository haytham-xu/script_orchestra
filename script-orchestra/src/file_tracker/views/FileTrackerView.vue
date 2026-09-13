<template>
  <div class="ft-root">
    <!-- Header -->
    <div class="ft-header">
      <el-button type="default" size="small" @click="$router.push('/')">← Back</el-button>
      <h2 class="ft-title">File Tracker</h2>
      <el-button type="default" size="small" @click="goSettings">Settings</el-button>
      <el-button
        type="primary"
        size="small"
        :loading="scanStatus.running"
        @click="triggerScan"
      >{{ scanStatus.running ? 'Scanning...' : 'Scan' }}</el-button>
    </div>

    <!-- Scan progress -->
    <div v-if="scanStatus.running" class="ft-progress-bar">
      <el-progress
        :percentage="scanPercent"
        :format="() => `${scanStatus.progress.scanned.toLocaleString()} / ${scanStatus.progress.total.toLocaleString()} files`"
        striped
        striped-flow
        :duration="10"
      />
      <div class="ft-progress-path">{{ scanStatus.progress.path }}</div>
    </div>

    <!-- Stats chips -->
    <div class="ft-stats" v-if="stats">
      <el-tag class="ft-stat-chip">{{ stats.total.toLocaleString() }} files</el-tag>
      <el-tag class="ft-stat-chip" type="info">{{ totalSizeDisplay }} total</el-tag>
      <el-tag class="ft-stat-chip" type="success" v-if="stats.by_status['normal']">
        {{ stats.by_status['normal'].count }} normal
      </el-tag>
      <el-tag class="ft-stat-chip" type="info" v-if="stats.by_status['ignored']">
        {{ stats.by_status['ignored'].count }} ignored
      </el-tag>
      <el-tag class="ft-stat-chip" type="warning" v-if="stats.by_status['archived']">
        {{ stats.by_status['archived'].count }} archived
      </el-tag>
      <span v-if="scanStatus.last_scan_time" class="ft-last-scan">
        Last scan: {{ fmtDate(scanStatus.last_scan_time) }}
      </span>
    </div>

    <!-- Status filter tabs + toolbar -->
    <div class="ft-toolbar">
      <el-tabs v-model="activeStatusFilter" @tab-change="loadFiles" class="ft-tabs">
        <el-tab-pane label="All" name="all" />
        <el-tab-pane label="Normal" name="normal" />
        <el-tab-pane label="Ignored" name="ignored" />
        <el-tab-pane label="Archived" name="archived" />
      </el-tabs>
      <div class="ft-toolbar-right">
        <el-input
          v-model="searchText"
          placeholder="Filter by path..."
          clearable
          size="small"
          style="width: 260px"
        />
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="grouped">Grouped</el-radio-button>
          <el-radio-button value="table">Table</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- Bulk action bar -->
    <div class="ft-bulk-bar" v-if="selectedIds.length">
      <span class="ft-bulk-label">{{ selectedIds.length }} selected</span>
      <el-button size="small" @click="bulkAction('ignored')">Ignore all</el-button>
      <el-button size="small" type="warning" @click="bulkAction('archived')">Archive all</el-button>
      <el-button size="small" type="danger" @click="bulkAction('delete')">Delete all</el-button>
    </div>

    <!-- Empty state -->
    <div v-if="!loading && !filteredFiles.length" class="ft-empty">
      <template v-if="!stats || !stats.total">
        Configure scan paths in
        <el-button type="primary" link @click="goSettings">Settings</el-button>,
        then press <strong>Scan</strong> to start tracking files.
      </template>
      <template v-else>No files match current filter.</template>
    </div>

    <!-- Main content area — split when file selected -->
    <div class="ft-content-area" :class="{ 'ft-split': !!selectedFile }">

      <!-- File list (left pane) -->
      <div class="ft-list-pane">

        <!-- ===================== GROUPED VIEW ===================== -->
        <template v-if="viewMode === 'grouped' && filteredFiles.length">
          <el-collapse :model-value="['danger','warn','archive','recent']">

            <el-collapse-item v-if="grouped.danger.length" name="danger">
              <template #title>
                <span class="ft-group-title">
                  <span class="ft-age-dot ft-age-dot-danger"></span>
                  &gt; {{ thresholds.danger }} days old
                  <span class="ft-group-meta">{{ grouped.danger.length }} files · {{ groupSize(grouped.danger) }}</span>
                </span>
              </template>
              <div class="ft-file-list">
                <div
                  v-for="f in grouped.danger" :key="f.id"
                  class="ft-file-row ft-row-danger"
                  :class="{ 'ft-row-selected': selectedFile && selectedFile.id === f.id }"
                  @click="selectFile(f)"
                >
                  <div class="ft-row-inner">
                    <div class="ft-cell-file">
                      <span class="ft-basename">{{ f.path.split('/').pop() }}</span>
                      <span class="ft-dirname">{{ f.path.split('/').slice(0, -1).join('/') }}</span>
                    </div>
                    <div class="ft-row-meta">
                      <span class="ft-size">{{ fmtSize(f.size_bytes) }}</span>
                      <span class="ft-age ft-age-danger">{{ ageDays(f.last_active) }}d ago</span>
                      <el-tag size="small" :type="statusTagType(f.status)">{{ f.status }}</el-tag>
                    </div>
                    <div class="ft-row-actions">
                      <el-button size="small" circle plain @click.stop="revealFile(f)" title="Open folder">📂</el-button>
                      <el-button size="small" circle plain @click.stop="setStatus(f, 'ignored')" title="Ignore">🚫</el-button>
                      <el-button size="small" circle plain @click.stop="setStatus(f, 'archived')" title="Archive">📦</el-button>
                      <el-button size="small" circle plain type="danger" @click.stop="deleteFile(f)" title="Delete">🗑️</el-button>
                    </div>
                  </div>
                </div>
              </div>
            </el-collapse-item>

            <el-collapse-item v-if="grouped.warn.length" name="warn">
              <template #title>
                <span class="ft-group-title">
                  <span class="ft-age-dot ft-age-dot-warn"></span>
                  {{ thresholds.warn }}–{{ thresholds.danger }} days old
                  <span class="ft-group-meta">{{ grouped.warn.length }} files · {{ groupSize(grouped.warn) }}</span>
                </span>
              </template>
              <div class="ft-file-list">
                <div
                  v-for="f in grouped.warn" :key="f.id"
                  class="ft-file-row ft-row-warn"
                  :class="{ 'ft-row-selected': selectedFile && selectedFile.id === f.id }"
                  @click="selectFile(f)"
                >
                  <div class="ft-row-inner">
                    <div class="ft-cell-file">
                      <span class="ft-basename">{{ f.path.split('/').pop() }}</span>
                      <span class="ft-dirname">{{ f.path.split('/').slice(0, -1).join('/') }}</span>
                    </div>
                    <div class="ft-row-meta">
                      <span class="ft-size">{{ fmtSize(f.size_bytes) }}</span>
                      <span class="ft-age ft-age-warn">{{ ageDays(f.last_active) }}d ago</span>
                      <el-tag size="small" :type="statusTagType(f.status)">{{ f.status }}</el-tag>
                    </div>
                    <div class="ft-row-actions">
                      <el-button size="small" circle plain @click.stop="revealFile(f)" title="Open folder">📂</el-button>
                      <el-button size="small" circle plain @click.stop="setStatus(f, 'ignored')" title="Ignore">🚫</el-button>
                      <el-button size="small" circle plain @click.stop="setStatus(f, 'archived')" title="Archive">📦</el-button>
                      <el-button size="small" circle plain type="danger" @click.stop="deleteFile(f)" title="Delete">🗑️</el-button>
                    </div>
                  </div>
                </div>
              </div>
            </el-collapse-item>

            <el-collapse-item v-if="grouped.archive.length" name="archive">
              <template #title>
                <span class="ft-group-title">
                  <span class="ft-age-dot ft-age-dot-archive"></span>
                  {{ thresholds.archive }}–{{ thresholds.warn }} days old
                  <span class="ft-group-meta">{{ grouped.archive.length }} files · {{ groupSize(grouped.archive) }}</span>
                </span>
              </template>
              <div class="ft-file-list">
                <div
                  v-for="f in grouped.archive" :key="f.id"
                  class="ft-file-row ft-row-archive"
                  :class="{ 'ft-row-selected': selectedFile && selectedFile.id === f.id }"
                  @click="selectFile(f)"
                >
                  <div class="ft-row-inner">
                    <div class="ft-cell-file">
                      <span class="ft-basename">{{ f.path.split('/').pop() }}</span>
                      <span class="ft-dirname">{{ f.path.split('/').slice(0, -1).join('/') }}</span>
                    </div>
                    <div class="ft-row-meta">
                      <span class="ft-size">{{ fmtSize(f.size_bytes) }}</span>
                      <span class="ft-age ft-age-archive">{{ ageDays(f.last_active) }}d ago</span>
                      <el-tag size="small" :type="statusTagType(f.status)">{{ f.status }}</el-tag>
                    </div>
                    <div class="ft-row-actions">
                      <el-button size="small" circle plain @click.stop="revealFile(f)" title="Open folder">📂</el-button>
                      <el-button size="small" circle plain @click.stop="setStatus(f, 'ignored')" title="Ignore">🚫</el-button>
                      <el-button size="small" circle plain @click.stop="setStatus(f, 'archived')" title="Archive">📦</el-button>
                      <el-button size="small" circle plain type="danger" @click.stop="deleteFile(f)" title="Delete">🗑️</el-button>
                    </div>
                  </div>
                </div>
              </div>
            </el-collapse-item>

            <el-collapse-item v-if="grouped.recent.length" name="recent">
              <template #title>
                <span class="ft-group-title">
                  <span class="ft-age-dot ft-age-dot-recent"></span>
                  &lt; {{ thresholds.archive }} days old
                  <span class="ft-group-meta">{{ grouped.recent.length }} files · {{ groupSize(grouped.recent) }}</span>
                </span>
              </template>
              <div class="ft-file-list">
                <div
                  v-for="f in grouped.recent" :key="f.id"
                  class="ft-file-row"
                  :class="{ 'ft-row-selected': selectedFile && selectedFile.id === f.id }"
                  @click="selectFile(f)"
                >
                  <div class="ft-row-inner">
                    <div class="ft-cell-file">
                      <span class="ft-basename">{{ f.path.split('/').pop() }}</span>
                      <span class="ft-dirname">{{ f.path.split('/').slice(0, -1).join('/') }}</span>
                    </div>
                    <div class="ft-row-meta">
                      <span class="ft-size">{{ fmtSize(f.size_bytes) }}</span>
                      <span class="ft-age ft-age-recent">{{ ageDays(f.last_active) }}d ago</span>
                      <el-tag size="small" :type="statusTagType(f.status)">{{ f.status }}</el-tag>
                    </div>
                    <div class="ft-row-actions">
                      <el-button size="small" circle plain @click.stop="revealFile(f)" title="Open folder">📂</el-button>
                      <el-button size="small" circle plain @click.stop="setStatus(f, 'ignored')" title="Ignore">🚫</el-button>
                      <el-button size="small" circle plain @click.stop="setStatus(f, 'archived')" title="Archive">📦</el-button>
                      <el-button size="small" circle plain type="danger" @click.stop="deleteFile(f)" title="Delete">🗑️</el-button>
                    </div>
                  </div>
                </div>
              </div>
            </el-collapse-item>

          </el-collapse>
        </template>

        <!-- ===================== TABLE VIEW ===================== -->
        <el-table
          v-if="viewMode === 'table' && filteredFiles.length"
          :data="filteredFiles"
          v-loading="loading"
          @selection-change="onTableSelectionChange"
          @row-click="(row: any) => selectFile(row)"
          :row-class-name="(scope: any) => selectedFile && selectedFile.id === scope.row.id ? 'ft-table-row-selected' : ''"
          style="width: 100%"
          size="small"
        >
          <el-table-column type="selection" width="40" />
          <el-table-column label="File" min-width="320">
            <template #default="{ row }">
              <div class="ft-cell-file">
                <span class="ft-basename">{{ row.path.split('/').pop() }}</span>
                <span class="ft-dirname">{{ row.path.split('/').slice(0, -1).join('/') }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="Size" width="90" sortable prop="size_bytes">
            <template #default="{ row }">{{ fmtSize(row.size_bytes) }}</template>
          </el-table-column>
          <el-table-column label="Last Active" width="130" sortable prop="last_active">
            <template #default="{ row }">
              <span :class="'ft-age-' + ageGroup(ageDays(row.last_active), thresholds)">
                {{ ageDays(row.last_active) }}d ago
              </span>
            </template>
          </el-table-column>
          <el-table-column label="Status" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="statusTagType(row.status)">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Actions" width="160">
            <template #default="{ row }">
              <el-button size="small" circle plain @click.stop="revealFile(row)" title="Open folder">📂</el-button>
              <el-button size="small" circle plain @click.stop="setStatus(row, 'ignored')" title="Ignore">🚫</el-button>
              <el-button size="small" circle plain @click.stop="setStatus(row, 'archived')" title="Archive">📦</el-button>
              <el-button size="small" circle plain type="danger" @click.stop="deleteFile(row)" title="Delete">🗑️</el-button>
            </template>
          </el-table-column>
        </el-table>

      </div><!-- /ft-list-pane -->

      <!-- ===================== PREVIEW PANEL ===================== -->
      <div v-if="selectedFile" class="ft-preview-pane">
        <div class="ft-preview-header">
          <span class="ft-preview-name">{{ selectedFile.path.split('/').pop() }}</span>
          <el-button size="small" circle @click="clearSelection" title="Close">✕</el-button>
        </div>

        <div class="ft-preview-body" v-loading="previewLoading">
          <!-- Image -->
          <template v-if="preview && preview.type === 'image'">
            <img :src="rawUrl(selectedFile)" class="ft-preview-img" :alt="preview.name" />
          </template>

          <!-- Video -->
          <template v-else-if="preview && preview.type === 'video'">
            <video :src="rawUrl(selectedFile)" controls class="ft-preview-video" />
          </template>

          <!-- Text -->
          <template v-else-if="preview && preview.type === 'text'">
            <div class="ft-preview-text-meta">
              <span>{{ fmtSize(preview.size || 0) }}</span>
              <span v-if="preview.truncated" class="ft-preview-truncated">— truncated at 100 KB</span>
            </div>
            <pre class="ft-preview-text">{{ preview.content }}</pre>
          </template>

          <!-- Unsupported -->
          <template v-else-if="preview && preview.type === 'unsupported'">
            <div class="ft-preview-unsupported">
              <div class="ft-preview-icon">📄</div>
              <div class="ft-preview-unsupported-name">{{ preview.name || selectedFile.path.split('/').pop() }}</div>
              <div v-if="preview.size" class="ft-preview-unsupported-size">{{ fmtSize(preview.size) }}</div>
              <div v-if="preview.ext" class="ft-preview-unsupported-ext">{{ preview.ext }} — no preview available</div>
            </div>
          </template>

          <!-- Loading placeholder -->
          <template v-else-if="!previewLoading">
            <div class="ft-preview-unsupported">
              <div class="ft-preview-icon">📄</div>
            </div>
          </template>
        </div>

        <div class="ft-preview-footer">
          <span class="ft-preview-hint">↑ ↓ keys to navigate</span>
          <span class="ft-preview-path">{{ selectedFile.path }}</span>
        </div>
      </div><!-- /ft-preview-pane -->

    </div><!-- /ft-content-area -->
  </div>
</template>

<script lang="ts">
import FileTrackerLogic from './FileTrackerView.ts'
export default {
  ...FileTrackerLogic,
  methods: {
    statusTagType(status: string) {
      if (status === 'normal') return 'success'
      if (status === 'ignored') return 'info'
      return 'warning'
    },
  },
}
</script>

<style scoped>
.ft-root { min-height: 100vh; padding: 24px 28px; box-sizing: border-box; }
.ft-header { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.ft-title { margin: 0; font-size: 20px; font-weight: 700; flex: 1; }

.ft-progress-bar { margin-bottom: 12px; }
.ft-progress-path { font-size: 11px; color: #909399; font-family: monospace; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.ft-stats { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.ft-stat-chip { font-size: 12px; }
.ft-last-scan { font-size: 12px; color: #909399; margin-left: 4px; }

.ft-toolbar { display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; }
.ft-tabs { flex: 1; min-width: 0; }
.ft-toolbar-right { display: flex; align-items: center; gap: 8px; padding-top: 4px; }

.ft-bulk-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; margin-bottom: 12px;
  background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 6px;
}
.ft-bulk-label { font-size: 13px; color: #0369a1; flex: 1; }

.ft-empty { text-align: center; color: #909399; font-size: 14px; padding: 48px 0; }

/* Content split layout */
.ft-content-area { display: flex; gap: 0; }
.ft-list-pane { flex: 1; min-width: 0; }
.ft-split .ft-list-pane { flex: 0 0 55%; min-width: 0; }

/* Preview pane */
.ft-preview-pane {
  flex: 0 0 44%;
  min-width: 0;
  margin-left: 16px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  background: #fff;
  max-height: calc(100vh - 220px);
  position: sticky;
  top: 16px;
  overflow: hidden;
}
.ft-preview-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
}
.ft-preview-name {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ft-preview-body {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: 12px;
  min-height: 0;
}
.ft-preview-img {
  max-width: 100%;
  max-height: 60vh;
  object-fit: contain;
  border-radius: 4px;
}
.ft-preview-video {
  max-width: 100%;
  max-height: 60vh;
  border-radius: 4px;
}
.ft-preview-text-meta {
  width: 100%;
  font-size: 11px;
  color: #909399;
  margin-bottom: 6px;
  display: flex;
  gap: 8px;
}
.ft-preview-truncated { color: #faad14; }
.ft-preview-text {
  width: 100%;
  margin: 0;
  font-size: 11px;
  font-family: 'SF Mono', 'Menlo', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  color: #303133;
  line-height: 1.5;
}
.ft-preview-unsupported {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 140px;
  gap: 8px;
  color: #909399;
}
.ft-preview-icon { font-size: 48px; }
.ft-preview-unsupported-name { font-size: 13px; font-weight: 600; color: #606266; text-align: center; word-break: break-all; }
.ft-preview-unsupported-size { font-size: 12px; }
.ft-preview-unsupported-ext { font-size: 12px; }
.ft-preview-footer {
  padding: 6px 14px;
  border-top: 1px solid #f0f0f0;
  background: #fafafa;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.ft-preview-hint { font-size: 11px; color: #c0c4cc; white-space: nowrap; }
.ft-preview-path { font-size: 10px; color: #c0c4cc; font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.ft-group-title { display: flex; align-items: center; gap: 10px; font-weight: 600; font-size: 14px; }
.ft-group-meta { font-size: 12px; color: #909399; font-weight: 400; }
.ft-age-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.ft-age-dot-danger { background: #f5222d; }
.ft-age-dot-warn { background: #faad14; }
.ft-age-dot-archive { background: #fa8c16; }
.ft-age-dot-recent { background: #52c41a; }

.ft-file-list { display: flex; flex-direction: column; gap: 2px; }
.ft-file-row { border-radius: 4px; padding: 2px 0; cursor: pointer; }
.ft-file-row:hover .ft-row-inner { background: rgba(0,0,0,0.02); border-radius: 4px; }
.ft-row-selected .ft-row-inner { background: #ecf5ff !important; border-radius: 4px; outline: 1px solid #409eff; }
.ft-row-danger { background: #fff1f0; }
.ft-row-warn { background: #fffbe6; }
.ft-row-archive { background: #fff7e6; }

.ft-row-inner { display: flex; align-items: center; gap: 8px; padding: 5px 8px; }
.ft-cell-file { flex: 1; min-width: 0; }
.ft-basename { font-size: 13px; font-weight: 600; color: #303133; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ft-dirname { font-size: 11px; color: #909399; font-family: monospace; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ft-row-meta { display: flex; align-items: center; gap: 8px; white-space: nowrap; }
.ft-size { font-size: 12px; color: #606266; min-width: 60px; text-align: right; }
.ft-age { font-size: 12px; min-width: 60px; text-align: right; }
.ft-row-actions { display: flex; gap: 2px; }

/* Age colors */
.ft-age-danger { color: #f5222d; font-weight: 600; }
.ft-age-warn { color: #faad14; font-weight: 600; }
.ft-age-archive { color: #fa8c16; }
.ft-age-recent { color: #52c41a; }
</style>

<style>
/* Table row selected — not scoped because el-table row class is injected outside shadow DOM */
.ft-table-row-selected td { background-color: #ecf5ff !important; }
</style>
