<template>
  <div class="tabs-root" v-loading="busy" element-loading-text="Working">
    <div class="tabs-header">
      <el-button size="small" @click="goBack">Back to Browser Agent</el-button>
      <h2 class="tabs-title">Tabs Workspace</h2>
      <el-input
        v-model="search"
        class="tabs-search"
        clearable
        placeholder="Search title, URL, labels, and comment"
      />
      <el-button :loading="loading" @click="loadSnapshot">Refresh</el-button>
    </div>

    <div class="tabs-summary">
      <span>Live selected: {{ selectedLiveTabIds.size }}</span>
      <span>Archive basket: {{ selectedArchiveIds.size }}</span>
      <span>Archive rows: {{ archiveRows.length }}</span>
    </div>

    <el-alert
      v-if="semanticEnabled && !semanticAvailable"
      type="info"
      show-icon
      :closable="false"
      title="Semantic search unavailable, using keyword fallback"
      :description="semanticError || 'Configure tabArchive.embedModel in Settings to enable semantic ranking.'"
    />

    <el-alert
      v-else-if="semanticEnabled && semanticAvailable"
      type="success"
      show-icon
      :closable="false"
      title="Semantic search enabled"
      :description="`Model: ${semanticModel || '-'} · Top K: ${semanticTopK}`"
    />

    <el-alert
      v-if="!extensionAvailable"
      type="warning"
      show-icon
      :closable="false"
      title="Browser extension is unavailable"
      :description="liveError || 'Start the extension and keep the browser running.'"
    />

    <el-tabs v-model="activePane" class="tabs-pane-wrap">
      <el-tab-pane label="Live" name="live">
        <div class="live-toolbar">
          <el-button @click="mergeAll">Merge windows</el-button>
          <el-button @click="groupByDomain">Group by domain</el-button>
          <el-button type="primary" :disabled="selectedLiveTabIds.size === 0" @click="archiveSelectedLive">
            Archive selected ({{ selectedLiveTabIds.size }})
          </el-button>
          <el-button type="danger" :disabled="selectedLiveTabIds.size === 0" @click="closeSelectedLiveOnly">
            Close selected
          </el-button>
          <el-input
            v-model="liveKeywordSelect"
            clearable
            placeholder="Keyword to select"
            style="width: 200px"
            @keyup.enter="selectLiveByKeyword"
          />
          <el-button @click="selectLiveByKeyword">Select by keyword</el-button>
          <el-switch
            v-model="safeIncludePinned"
            class="with-label"
            inline-prompt
            active-text="Include pinned"
            inactive-text="Skip pinned"
          />
          <el-button type="warning" @click="previewSafeArchive">Safe archive preview</el-button>
        </div>

        <div class="table-wrap" v-if="liveRows.length > 0">
          <div class="table-row table-head">
            <el-checkbox
              :model-value="allVisibleLiveSelected"
              :indeterminate="someVisibleLiveSelected"
              @change="toggleVisibleLiveSelection"
            />
            <span class="col-fav"></span>
            <span class="col-title">Title</span>
            <span class="col-heat">Heat</span>
            <span class="col-eternal">Eternal</span>
            <span class="col-labels">Labels</span>
            <span class="col-actions">Actions</span>
          </div>

          <div
            v-for="row in liveRows"
            :key="row.tab_id"
            class="table-row"
            :class="{ selected: selectedLiveTabIds.has(row.tab_id) }"
          >
            <el-checkbox :model-value="selectedLiveTabIds.has(row.tab_id)" @change="toggleLiveSelection(row.tab_id)" />
            <span class="fav-slot">
              <img v-if="row.favicon_url" :src="row.favicon_url" class="fav" @error="hideFavicon" />
            </span>

            <div class="title-cell">
              <span class="title-line" :title="row.title">{{ row.title || '(no title)' }}</span>
              <span class="meta-line">{{ row.domain || '-' }}</span>
            </div>

            <span class="heat-cell">
              <el-tag :type="heatTagType(row.heat_level)" size="small">{{ row.heat_level }}</el-tag>
            </span>

            <span class="eternal-cell">
              <el-tag v-if="row.eternal" type="success" size="small">Eternal</el-tag>
              <span v-else class="muted">-</span>
            </span>

            <span class="labels-cell">
              <el-tag v-for="label in row.labels" :key="label" size="small" class="small-tag">{{ label }}</el-tag>
              <span v-if="row.labels.length === 0" class="muted">-</span>
            </span>

            <span class="actions-cell">
              <el-popover trigger="click" placement="left" width="460">
                <template #reference>
                  <el-button size="small" text>Details</el-button>
                </template>
                <div class="detail-grid">
                  <div><b>URL</b></div><div class="mono">{{ row.url || '-' }}</div>
                  <div><b>Comment</b></div><div>{{ row.comment || '-' }}</div>
                  <div><b>Window</b></div><div>{{ row.window_id }}</div>
                  <div><b>Pinned</b></div><div>{{ row.pinned ? 'yes' : 'no' }}</div>
                </div>
              </el-popover>
              <el-button size="small" type="danger" text @click="closeSingleLive(row.tab_id)">Close</el-button>
            </span>
          </div>
        </div>

        <el-empty v-else description="No live tabs match current search" />
      </el-tab-pane>

      <el-tab-pane label="Archive" name="archive">
        <div class="archive-toolbar">
          <el-switch
            v-model="semanticEnabled"
            active-text="Semantic"
            inactive-text="Keyword"
          />
          <el-select v-model="archiveSortBy" style="width: 180px">
            <el-option label="Sort: heat" value="heat" />
            <el-option label="Sort: relevance" value="relevance" />
            <el-option label="Sort: last opened" value="last_opened" />
            <el-option label="Sort: last archived" value="last_archived" />
            <el-option label="Sort: open count" value="open_count" />
            <el-option label="Sort: title" value="title" />
          </el-select>
          <el-select v-model="archiveSortOrder" style="width: 130px">
            <el-option label="Desc" value="desc" />
            <el-option label="Asc" value="asc" />
          </el-select>
          <el-select v-model="restoreDestination" style="width: 220px">
            <el-option label="Restore to one new window" value="new_window" />
            <el-option label="Restore to current window" value="current_window" />
          </el-select>
          <el-button :disabled="healthJobRunning" @click="checkArchiveHealthVisible">Health check visible</el-button>
          <el-button :disabled="selectedArchiveIds.size === 0 || healthJobRunning" @click="checkArchiveHealthSelected">
            Health check selected
          </el-button>
          <el-button
            v-if="healthJobRunning"
            type="warning"
            @click="cancelArchiveHealthCheck"
          >
            Cancel check
          </el-button>
          <el-button type="primary" :disabled="selectedArchiveIds.size === 0 || healthJobRunning" @click="restoreSelectedArchive">
            Restore selected ({{ selectedArchiveIds.size }})
          </el-button>
          <el-button :disabled="selectedArchiveIds.size === 0" @click="clearArchiveBasket">Clear basket</el-button>
          <el-button @click="openReplaceUrlDialog">Replace URL</el-button>
        </div>

        <div v-if="healthJob" class="health-job-box">
          <div class="health-job-head">
            <span>
              Health job {{ healthJob.job_id.slice(0, 8) }} ({{ healthScopeLabel || 'archive' }})
            </span>
            <el-tag size="small" :type="healthJobRunning ? 'warning' : (healthJob.status === 'completed' ? 'success' : (healthJob.status === 'failed' ? 'danger' : 'info'))">
              {{ healthJob.status }}
            </el-tag>
          </div>
          <el-progress :percentage="healthJob.progress_percent" :stroke-width="12" />
          <div class="health-job-meta">
            <span>{{ healthJob.processed }} / {{ healthJob.total }}</span>
            <span>healthy {{ healthJob.healthy }}</span>
            <span>unavailable {{ healthJob.unavailable }}</span>
            <span>unknown {{ healthJob.unknown }}</span>
          </div>
          <div v-if="healthJob.last_error" class="health-job-error">{{ healthJob.last_error }}</div>
        </div>

        <div class="archive-filters">
          <el-input v-model="archiveDomainFilter" clearable placeholder="Filter by domain" style="width: 220px" />
          <el-select v-model="archiveEternalFilter" style="width: 150px">
            <el-option label="All eternal" value="all" />
            <el-option label="Eternal only" value="eternal" />
            <el-option label="Not eternal" value="not_eternal" />
          </el-select>
          <el-select v-model="archiveHeatFilter" style="width: 140px">
            <el-option label="All heat" value="all" />
            <el-option label="High" value="high" />
            <el-option label="Medium" value="medium" />
            <el-option label="Low" value="low" />
            <el-option label="Cold" value="cold" />
          </el-select>
          <el-select v-model="archiveHealthFilter" style="width: 160px">
            <el-option label="All health" value="all" />
            <el-option label="Healthy" value="healthy" />
            <el-option label="Unknown" value="unknown" />
            <el-option label="Unavailable" value="unavailable" />
          </el-select>
          <el-select
            v-model="archiveLabelFilter"
            style="width: 240px"
            multiple
            collapse-tags
            collapse-tags-tooltip
            clearable
            placeholder="Filter by labels"
          >
            <el-option v-for="label in labels" :key="label.id" :label="label.name" :value="label.name" />
          </el-select>
        </div>

        <div class="table-wrap" v-if="visibleArchiveRows.length > 0">
          <div class="table-row table-head">
            <el-checkbox
              :model-value="allVisibleArchiveSelected"
              :indeterminate="someVisibleArchiveSelected"
              @change="toggleVisibleArchiveSelection"
            />
            <span class="col-fav"></span>
            <span class="col-title">Title</span>
            <span class="col-heat">Heat</span>
            <span class="col-eternal">Health</span>
            <span class="col-labels">Labels</span>
            <span class="col-actions">Actions</span>
          </div>

          <div
            v-for="row in visibleArchiveRows"
            :key="row.id"
            class="table-row"
            :class="{ selected: selectedArchiveIds.has(row.id) }"
          >
            <el-checkbox :model-value="selectedArchiveIds.has(row.id)" @change="toggleArchiveSelection(row.id)" />
            <span class="fav-slot">
              <img v-if="row.favicon_url" :src="row.favicon_url" class="fav" @error="hideFavicon" />
            </span>

            <div class="title-cell">
              <span class="title-line" :title="row.title">{{ row.title || '(no title)' }}</span>
              <span class="meta-line">{{ row.domain || '-' }}</span>
            </div>

            <span class="heat-cell">
              <el-tag :type="heatTagType(row.heat_level)" size="small">{{ row.heat_level }}</el-tag>
              <el-tag v-if="row.eternal" type="success" size="small" class="small-tag">Eternal</el-tag>
            </span>

            <span class="eternal-cell">
              <el-tag size="small" type="info">{{ row.health_status || 'unknown' }}</el-tag>
            </span>

            <span class="labels-cell">
              <el-tag v-for="label in row.labels" :key="label" size="small" class="small-tag">{{ label }}</el-tag>
              <span v-if="row.labels.length === 0" class="muted">-</span>
            </span>

            <span class="actions-cell">
              <el-popover trigger="click" placement="left" width="500">
                <template #reference>
                  <el-button size="small" text>Details</el-button>
                </template>
                <div class="detail-grid">
                  <div><b>URL</b></div><div class="mono">{{ row.url }}</div>
                  <div><b>Comment</b></div><div>{{ row.comment || '-' }}</div>
                  <div><b>Last opened</b></div><div>{{ formatTime(row.last_opened_at) }}</div>
                  <div><b>Last archived</b></div><div>{{ formatTime(row.last_archived_at) }}</div>
                  <div><b>Open count</b></div><div>{{ row.open_count }}</div>
                  <div><b>Archive count</b></div><div>{{ row.archive_count }}</div>
                </div>
              </el-popover>
              <el-button size="small" text @click="startEditRecord(row)">Edit</el-button>
              <el-button size="small" type="danger" text @click="deleteRecord(row)">Delete</el-button>
            </span>
          </div>
        </div>

        <el-empty v-else description="No archived rows match current filters" />

        <el-card class="basket-card">
          <template #header>
            <div class="basket-head">
              <span>Selection Basket ({{ selectedArchiveRecords.length }})</span>
              <el-button text @click="clearArchiveBasket" :disabled="selectedArchiveRecords.length === 0">Clear</el-button>
            </div>
          </template>

          <el-empty v-if="selectedArchiveRecords.length === 0" description="No selected archive records" />

          <div v-else class="basket-list">
            <div v-for="record in selectedArchiveRecords" :key="record.id" class="basket-row">
              <span class="basket-title" :title="record.title">{{ record.title || record.domain || record.url }}</span>
              <el-button text size="small" @click="removeFromArchiveBasket(record.id)">Remove</el-button>
            </div>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="safePreviewVisible" title="Safe Archive Preview" width="760px">
      <div v-if="safePreview" class="preview-wrap">
        <div class="preview-head">
          <el-tag type="success">Candidates: {{ safePreview.candidate_count }}</el-tag>
          <el-tag type="warning">Excluded: {{ safePreview.excluded_count }}</el-tag>
        </div>

        <h4>Excluded tabs</h4>
        <div class="preview-list" v-if="safePreview.excluded.length > 0">
          <div v-for="row in safePreview.excluded" :key="row.tab_id" class="preview-row">
            <span class="preview-title">{{ row.title || '(no title)' }}</span>
            <el-tag size="small" type="info">{{ row.reason || '-' }}</el-tag>
          </div>
        </div>
        <el-empty v-else description="No excluded tabs" />
      </div>
      <template #footer>
        <el-button @click="safePreviewVisible = false">Cancel</el-button>
        <el-button type="primary" @click="runSafeArchive">Run safe archive</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="replaceUrlVisible" title="Replace URL" width="760px">
      <el-form label-width="80px">
        <el-form-item label="Find">
          <el-input v-model="replaceUrlFind" placeholder="e.g. old.domain.com" />
        </el-form-item>
        <el-form-item label="Replace">
          <el-input v-model="replaceUrlReplace" placeholder="e.g. new.domain.com" />
        </el-form-item>
      </el-form>
      <el-alert
        v-if="selectedArchiveIds.size > 0"
        type="info"
        :closable="false"
        :title="`Scope: ${selectedArchiveIds.size} selected record(s). Clear basket to apply to all.`"
        style="margin-bottom: 10px"
      />
      <div v-if="replaceUrlPreviewed">
        <div style="margin-bottom: 6px; font-size: 13px; color: #475569">
          Preview: {{ replaceUrlPreviewRows.length }} record(s) will be updated
        </div>
        <div v-if="replaceUrlPreviewRows.length > 0" class="replace-preview-list">
          <div v-for="row in replaceUrlPreviewRows" :key="row.id" class="replace-preview-row">
            <span class="replace-preview-title">{{ row.title || row.old_url }}</span>
            <div class="replace-preview-urls">
              <span class="mono replace-old">{{ row.old_url }}</span>
              <span class="replace-arrow">→</span>
              <span class="mono replace-new">{{ row.new_url }}</span>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="replaceUrlVisible = false">Cancel</el-button>
        <el-button @click="previewReplaceUrl">Preview</el-button>
        <el-button
          type="primary"
          :disabled="!replaceUrlPreviewed || replaceUrlPreviewRows.length === 0"
          @click="applyReplaceUrl"
        >
          Apply ({{ replaceUrlPreviewRows.length }})
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="Edit archived record" width="680px">
      <el-form label-width="90px">
        <el-form-item label="Title">
          <el-input v-model="editTitle" />
        </el-form-item>
        <el-form-item label="Comment">
          <el-input v-model="editComment" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="Eternal">
          <el-switch v-model="editEternal" />
        </el-form-item>
        <el-form-item label="Labels">
          <div class="label-row">
            <el-select
              v-model="editLabelIds"
              multiple
              clearable
              collapse-tags
              collapse-tags-tooltip
              style="width: 100%"
              placeholder="Select labels"
            >
              <el-option
                v-for="label in labels"
                :key="label.id"
                :label="label.name"
                :value="label.id"
              />
            </el-select>
            <el-button @click="createLabelInEditor">New label</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">Cancel</el-button>
        <el-button type="primary" @click="saveRecordEdit">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts" src="@/browser_agent/views/TabsView.ts"></script>

<style scoped>
.tabs-root {
  padding: 20px 24px;
}
.tabs-header {
  display: grid;
  grid-template-columns: auto auto 1fr auto;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.tabs-title {
  margin: 0;
  font-size: 22px;
  font-weight: 650;
}
.tabs-search {
  max-width: 560px;
  justify-self: end;
}
.tabs-summary {
  display: flex;
  gap: 16px;
  color: #475569;
  font-size: 13px;
  margin-bottom: 12px;
}
.tabs-pane-wrap {
  margin-top: 10px;
}
.live-toolbar,
.archive-toolbar,
.archive-filters {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.health-job-box {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 12px;
  background: #f8fafc;
}
.health-job-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  margin-bottom: 8px;
}
.health-job-meta {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #475569;
  margin-top: 8px;
}
.health-job-error {
  margin-top: 6px;
  font-size: 12px;
  color: #b91c1c;
  word-break: break-all;
}
.with-label {
  margin-left: auto;
}
.table-wrap {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
}
.table-row {
  display: grid;
  grid-template-columns: 34px 24px minmax(220px, 1.2fr) 160px 130px minmax(120px, 1fr) 190px;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  border-top: 1px solid #f1f5f9;
}
.table-row:first-child {
  border-top: none;
}
.table-head {
  background: #f8fafc;
  font-weight: 700;
  color: #334155;
  font-size: 12px;
}
.selected {
  background: #f0f9ff;
}
.fav-slot {
  width: 16px;
  height: 16px;
  border-radius: 3px;
  background: #cbd5e1;
  overflow: hidden;
}
.fav {
  display: block;
  width: 16px;
  height: 16px;
  border-radius: 3px;
}
.title-cell {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.title-line {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #0f172a;
}
.meta-line {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #64748b;
  font-size: 12px;
}
.labels-cell {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.actions-cell {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}
.heat-cell,
.eternal-cell {
  display: flex;
  gap: 4px;
  align-items: center;
}
.small-tag {
  margin-left: 4px;
}
.muted {
  color: #94a3b8;
}
.detail-grid {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 6px 8px;
  font-size: 13px;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  word-break: break-all;
}
.basket-card {
  margin-top: 12px;
}
.basket-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.basket-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.basket-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.basket-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.preview-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.preview-head {
  display: flex;
  gap: 8px;
}
.preview-list {
  max-height: 260px;
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px;
}
.preview-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 0;
}
.preview-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.label-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.replace-preview-list {
  max-height: 320px;
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px;
}
.replace-preview-row {
  padding: 6px 0;
  border-top: 1px solid #f1f5f9;
}
.replace-preview-row:first-child {
  border-top: none;
}
.replace-preview-title {
  font-weight: 600;
  font-size: 13px;
  color: #0f172a;
  display: block;
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.replace-preview-urls {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
  flex-wrap: wrap;
}
.replace-old {
  color: #b91c1c;
  text-decoration: line-through;
  word-break: break-all;
}
.replace-new {
  color: #15803d;
  word-break: break-all;
}
.replace-arrow {
  color: #64748b;
  flex-shrink: 0;
}

@media (max-width: 1100px) {
  .tabs-header {
    grid-template-columns: auto 1fr auto;
  }
  .tabs-title {
    grid-column: 1 / 4;
  }
  .tabs-search {
    grid-column: 2 / 3;
    max-width: none;
    justify-self: stretch;
  }
  .table-row {
    grid-template-columns: 34px 24px minmax(180px, 1fr) 130px 120px minmax(100px, 1fr) 170px;
  }
}

@media (max-width: 760px) {
  .tabs-root {
    padding: 14px;
  }
  .table-row {
    grid-template-columns: 34px 24px minmax(140px, 1fr) 95px 95px 95px 130px;
    font-size: 12px;
  }
}
</style>
