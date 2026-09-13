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
            <div v-for="f in grouped.danger" :key="f.id" class="ft-file-row ft-row-danger">
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
                  <el-button size="small" circle plain @click="revealFile(f)" title="Open folder">📂</el-button>
                  <el-button size="small" circle plain @click="setStatus(f, 'ignored')" title="Ignore">🚫</el-button>
                  <el-button size="small" circle plain @click="setStatus(f, 'archived')" title="Archive">📦</el-button>
                  <el-button size="small" circle plain type="danger" @click="deleteFile(f)" title="Delete">🗑️</el-button>
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
            <div v-for="f in grouped.warn" :key="f.id" class="ft-file-row ft-row-warn">
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
                  <el-button size="small" circle plain @click="revealFile(f)" title="Open folder">📂</el-button>
                  <el-button size="small" circle plain @click="setStatus(f, 'ignored')" title="Ignore">🚫</el-button>
                  <el-button size="small" circle plain @click="setStatus(f, 'archived')" title="Archive">📦</el-button>
                  <el-button size="small" circle plain type="danger" @click="deleteFile(f)" title="Delete">🗑️</el-button>
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
            <div v-for="f in grouped.archive" :key="f.id" class="ft-file-row ft-row-archive">
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
                  <el-button size="small" circle plain @click="revealFile(f)" title="Open folder">📂</el-button>
                  <el-button size="small" circle plain @click="setStatus(f, 'ignored')" title="Ignore">🚫</el-button>
                  <el-button size="small" circle plain @click="setStatus(f, 'archived')" title="Archive">📦</el-button>
                  <el-button size="small" circle plain type="danger" @click="deleteFile(f)" title="Delete">🗑️</el-button>
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
            <div v-for="f in grouped.recent" :key="f.id" class="ft-file-row">
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
                  <el-button size="small" circle plain @click="revealFile(f)" title="Open folder">📂</el-button>
                  <el-button size="small" circle plain @click="setStatus(f, 'ignored')" title="Ignore">🚫</el-button>
                  <el-button size="small" circle plain @click="setStatus(f, 'archived')" title="Archive">📦</el-button>
                  <el-button size="small" circle plain type="danger" @click="deleteFile(f)" title="Delete">🗑️</el-button>
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
          <el-button size="small" circle plain @click="revealFile(row)" title="Open folder">📂</el-button>
          <el-button size="small" circle plain @click="setStatus(row, 'ignored')" title="Ignore">🚫</el-button>
          <el-button size="small" circle plain @click="setStatus(row, 'archived')" title="Archive">📦</el-button>
          <el-button size="small" circle plain type="danger" @click="deleteFile(row)" title="Delete">🗑️</el-button>
        </template>
      </el-table-column>
    </el-table>
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
.ft-root { width: 100%; min-height: 100vh; padding: 24px 28px; box-sizing: border-box; }
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

.ft-group-title { display: flex; align-items: center; gap: 10px; font-weight: 600; font-size: 14px; }
.ft-group-meta { font-size: 12px; color: #909399; font-weight: 400; }
.ft-age-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.ft-age-dot-danger { background: #f5222d; }
.ft-age-dot-warn { background: #faad14; }
.ft-age-dot-archive { background: #fa8c16; }
.ft-age-dot-recent { background: #52c41a; }

.ft-file-list { display: flex; flex-direction: column; gap: 2px; }
.ft-file-row { border-radius: 4px; padding: 2px 0; }
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
