<template>
  <div class="dt1-root">
    <div class="dt1-header">
      <el-button type="default" size="small" @click="goBack">← Browser Agent</el-button>
      <h2 class="dt1-title">Download SSMH</h2>
      <div class="dt1-header-actions">
        <el-button size="small" @click="$router.push('/browser-agent/settings')">Settings</el-button>
      </div>
    </div>

    <div v-if="!configReady" class="dt1-config-missing">
      <el-alert type="warning" show-icon :closable="false">
        <template #title>Download SSMH is not configured yet</template>
        Go to
        <el-button link @click="$router.push('/browser-agent/settings')">Settings</el-button>
        and fill in source domains, download domains, link label, and download path.
      </el-alert>
    </div>

    <el-card v-else class="dt1-card">
      <template #header>
        <div class="dt1-card-head">
          <span>Scan open tabs</span>
          <div class="dt1-card-head-actions">
            <el-button type="primary" :loading="scanning" @click="doScan">Scan now</el-button>
          </div>
        </div>
      </template>

      <div v-if="candidates.length === 0 && !scanning" class="dt1-hint">
        <template v-if="totalTabsScanned > 0">
          Scanned {{ totalTabsScanned }} tabs — none matched the source domain.
        </template>
        <template v-else>
          Click <em>Scan now</em> to filter open browser tabs whose host matches
          a configured source domain and whose path is
          <code>/photos-index-aid-&lt;id&gt;.html</code>.
        </template>
      </div>

      <div v-else class="dt1-cand-list">
        <div class="dt1-cand-head">
          <el-checkbox :model-value="allSelected" @change="toggleSelectAll" />
          <span>{{ selectedUrls.size }} / {{ candidates.length }} selected  (from {{ totalTabsScanned }} tabs)</span>
          <div class="dt1-cand-actions">
            <el-button type="danger" :disabled="selectedUrls.size === 0 || jobRunning"
                       @click="execute">Download selected</el-button>
          </div>
        </div>
        <label v-for="c in candidates" :key="c.url" class="dt1-cand-row"
               :class="{ 'dt1-selected': selectedUrls.has(c.url) }">
          <el-checkbox
            :model-value="selectedUrls.has(c.url)"
            @change="toggleSelected(c.url)" />
          <span class="dt1-cand-aid">aid {{ c.aid || '—' }}</span>
          <span class="dt1-cand-url" :title="c.url">{{ c.url }}</span>
        </label>
      </div>
    </el-card>

    <el-card v-if="jobItems.length > 0" class="dt1-card">
      <template #header>
        <div class="dt1-card-head">
          <span>Progress</span>
          <span class="dt1-progress-summary">
            {{ jobDone }} / {{ jobTotal }}
            <el-tag v-if="jobRunning" type="warning" size="small">running</el-tag>
            <el-tag v-else type="success" size="small">done</el-tag>
          </span>
        </div>
      </template>
      <div class="dt1-job-list">
        <div v-for="item in jobItems" :key="item.url" class="dt1-job-row">
          <div class="dt1-job-line1">
            <el-tag :type="statusTagType(item.status)" size="small" class="dt1-job-status">
              {{ item.status }}
            </el-tag>
            <span class="dt1-job-url" :title="item.url">{{ item.url }}</span>
            <span v-if="item.filename" class="dt1-job-filename" :title="item.filename">
              → {{ item.filename }}
            </span>
          </div>
          <div v-if="item.status === 'downloading' || (item.status === 'done' && item.bytes_downloaded > 0)"
               class="dt1-job-line2">
            <el-progress
              :percentage="item.progress_percent"
              :status="item.status === 'done' ? 'success' : undefined"
              :stroke-width="6"
              class="dt1-job-bar" />
            <span class="dt1-job-metric">
              {{ fmtBytes(item.bytes_downloaded) }}
              <template v-if="item.bytes_total > 0"> / {{ fmtBytes(item.bytes_total) }}</template>
            </span>
            <span v-if="item.status === 'downloading' && item.speed_bps > 0" class="dt1-job-metric">
              {{ fmtSpeed(item.speed_bps) }}
            </span>
          </div>
          <div v-if="item.message" class="dt1-job-msg" :title="item.message">{{ item.message }}</div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script lang="ts" src="@/browser_agent/views/DownloadSSMHView.ts"></script>

<style scoped>
.dt1-root { padding: 24px 32px; box-sizing: border-box; max-width: 1200px; margin: 0 auto; }
.dt1-header { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.dt1-title { margin: 0; font-size: 22px; font-weight: 600; flex: 1; }
.dt1-header-actions { display: flex; gap: 8px; }
.dt1-card { margin-bottom: 20px; }
.dt1-card-head {
  display: flex; align-items: center; justify-content: space-between;
  font-weight: 600;
}
.dt1-card-head-actions { display: flex; gap: 8px; }

.dt1-config-missing { margin-bottom: 20px; }

.dt1-hint { color: #64748b; font-size: 13px; }
.dt1-hint code {
  background: #f1f5f9; padding: 1px 6px; border-radius: 3px; font-size: 12px;
}

.dt1-cand-list { display: flex; flex-direction: column; }
.dt1-cand-head {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 12px; border-bottom: 1px solid #e2e8f0;
  background: #f8fafc; font-size: 13px;
}
.dt1-cand-actions { margin-left: auto; }
.dt1-cand-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-bottom: 1px solid #f1f5f9;
  cursor: pointer; user-select: none;
}
.dt1-cand-row:last-child { border-bottom: none; }
.dt1-cand-row:hover { background: #fafcfe; }
.dt1-selected { background: #eff6ff; }
.dt1-selected:hover { background: #dbeafe; }
.dt1-cand-aid {
  font-family: monospace; font-size: 12px; color: #64748b;
  padding: 2px 6px; background: #f1f5f9; border-radius: 4px;
}
.dt1-cand-url {
  flex: 1; font-family: monospace; font-size: 12px; color: #334155;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.dt1-progress-summary {
  font-weight: 400; font-size: 13px; color: #64748b;
  display: flex; align-items: center; gap: 8px;
}
.dt1-job-list { display: flex; flex-direction: column; gap: 8px; }
.dt1-job-row {
  display: flex; flex-direction: column; gap: 4px;
  padding: 8px 10px; font-size: 12px;
  border-bottom: 1px solid #f1f5f9;
}
.dt1-job-row:last-child { border-bottom: none; }
.dt1-job-line1, .dt1-job-line2 {
  display: flex; align-items: center; gap: 10px;
}
.dt1-job-status { flex: none; }
.dt1-job-url {
  flex: 1; min-width: 0; font-family: monospace; color: #334155;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dt1-job-filename { color: #16a34a; font-family: monospace; font-size: 11px; }
.dt1-job-msg { color: #64748b; font-size: 11px; padding-left: 6px; }
.dt1-job-bar { flex: 1; margin-right: 8px; }
.dt1-job-metric {
  flex: none; font-family: monospace; font-size: 11px; color: #475569;
  min-width: 90px; text-align: right;
}
</style>
