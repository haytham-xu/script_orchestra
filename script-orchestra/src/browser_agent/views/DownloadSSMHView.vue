<template>
  <div class="dt1-root">
    <div class="dt1-header">
      <el-button type="default" size="small" @click="goBack">← Browser Agent</el-button>
      <h2 class="dt1-title">Download SSMH</h2>
      <div class="dt1-header-actions">
        <el-button :icon="Setting" size="small" @click="openSettings">Settings</el-button>
      </div>
    </div>

    <div v-if="!configReady" class="dt1-config-missing">
      <el-alert type="warning" show-icon :closable="false">
        <template #title>Download SSMH is not configured yet</template>
        Click <el-button link @click="openSettings">Settings</el-button>
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

      <!-- Scan progress bar -->
      <div v-if="scanning && scanTotal > 0" class="dt1-scan-progress">
        <el-progress
          :percentage="Math.round(scanDone * 100 / scanTotal)"
          :stroke-width="6"
          class="dt1-scan-bar" />
        <span class="dt1-scan-label">Classifying {{ scanDone }} / {{ scanTotal }} tabs…</span>
      </div>
      <div v-else-if="scanning" class="dt1-scan-progress">
        <span class="dt1-scan-label">Fetching tab list…</span>
      </div>

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
          <div class="dt1-cand-type-btns">
            <el-button v-if="type1Count > 0" size="small" @click="selectByType('type1')">
              T1 ({{ type1Count }})
            </el-button>
            <el-button v-if="type2Count > 0" size="small" @click="selectByType('type2')">
              T2 ({{ type2Count }})
            </el-button>
          </div>
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
          <el-tag :type="c.dl_type === 'type1' ? 'success' : c.dl_type === 'type2' ? 'warning' : 'info'"
                  size="small" class="dt1-cand-type">
            {{ c.dl_type === 'type1' ? 'T1' : c.dl_type === 'type2' ? 'T2' : '?' }}
          </el-tag>
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
            <el-tag v-if="item.dl_type === 'type1' || item.dl_type === 'type2'"
                    :type="item.dl_type === 'type1' ? 'success' : 'warning'"
                    size="small" class="dt1-job-dtype">
              {{ item.dl_type === 'type1' ? 'T1' : 'T2' }}
            </el-tag>
            <span class="dt1-job-url" :title="item.url">{{ item.url }}</span>
            <span v-if="item.filename" class="dt1-job-filename" :title="item.filename">
              → {{ item.filename }}
            </span>
          </div>
          <div v-if="(!item.sub_items || !item.sub_items.length) && (item.status === 'skipped' || item.status === 'downloading' || (item.status === 'done' && item.bytes_downloaded > 0))"
               class="dt1-job-line2">
            <el-progress
              :percentage="item.progress_percent"
              :status="(item.status === 'done' || item.status === 'skipped') ? 'success' : undefined"
              :stroke-width="6"
              class="dt1-job-bar" />
            <span v-if="item.status !== 'skipped'" class="dt1-job-metric">
              {{ fmtBytes(item.bytes_downloaded) }}
              <template v-if="item.bytes_total > 0"> / {{ fmtBytes(item.bytes_total) }}</template>
            </span>
            <span v-if="item.status === 'downloading' && item.speed_bps > 0" class="dt1-job-metric">
              {{ fmtSpeed(item.speed_bps) }}
            </span>
          </div>
          <div v-if="item.message" class="dt1-job-msg" :title="item.message">{{ item.message }}</div>

          <!-- Per-file sub-items (Type 2 multi-chapter) -->
          <div v-if="item.sub_items && item.sub_items.length > 0" class="dt1-subitem-list">
            <div v-for="(sub, si) in item.sub_items" :key="si" class="dt1-subitem-row">
              <el-tag :type="statusTagType(sub.status)" size="small" class="dt1-sub-status">
                {{ sub.status }}
              </el-tag>
              <span class="dt1-sub-name" :title="sub.filename">{{ sub.filename }}</span>
              <el-progress
                v-if="sub.status !== 'pending'"
                :percentage="sub.progress_percent"
                :status="sub.status === 'done' ? 'success' : (sub.status === 'error' ? 'exception' : undefined)"
                :stroke-width="4"
                class="dt1-sub-bar" />
              <span v-if="sub.bytes_downloaded > 0 || sub.bytes_total > 0" class="dt1-job-metric">
                {{ fmtBytes(sub.bytes_downloaded) }}
                <template v-if="sub.bytes_total > 0"> / {{ fmtBytes(sub.bytes_total) }}</template>
              </span>
              <span v-if="sub.status === 'downloading' && sub.speed_bps > 0" class="dt1-job-metric">
                {{ fmtSpeed(sub.speed_bps) }}
              </span>
              <span v-if="sub.message" class="dt1-sub-msg">{{ sub.message }}</span>
            </div>
          </div>
        </div>
      </div>
    </el-card>
  </div>

  <!-- Settings drawer -->
  <el-drawer v-model="settingsOpen" title="Download SSMH Settings" size="480px" direction="rtl">
    <div class="dt1-settings">
      <div class="dt1-set-row">
        <label>Source domains</label>
        <el-input type="textarea" :rows="3"
          :model-value="ssmhSourcesText()"
          @update:model-value="setSsmhSourcesText"
          placeholder="one per line, e.g. foo.com" spellcheck="false" />
      </div>
      <div class="dt1-set-row">
        <label>Download domains</label>
        <el-input type="textarea" :rows="3"
          :model-value="ssmhDownloadsText()"
          @update:model-value="setSsmhDownloadsText"
          placeholder="one per line, e.g. cdn.foo.com" spellcheck="false" />
      </div>
      <div class="dt1-set-row">
        <label>Link label <span class="dt1-type1-note">(Type 1 only)</span></label>
        <el-input v-model="settingsCfg.linkLabel"
          placeholder="visible text of the anchor to pick" spellcheck="false" />
      </div>
      <div class="dt1-set-row">
        <label>Download path</label>
        <el-input v-model="settingsCfg.downloadPath"
          placeholder="/absolute/path/to/output" spellcheck="false" />
      </div>
      <div class="dt1-set-row">
        <label>Parallel segments <span class="dt1-type1-note">(1 = single stream; raise with care, CDN rate-limits easily)</span></label>
        <el-input-number v-model="settingsCfg.downloadParts" :min="1" :max="16" :step="1" style="width:120px" />
      </div>
      <el-button type="primary" :loading="settingsSaving" @click="saveSettings" style="margin-top:8px">Save</el-button>
    </div>
  </el-drawer>
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
.dt1-type1-note { font-size: 11px; font-weight: 400; color: #94a3b8; }
.dt1-settings { display: flex; flex-direction: column; gap: 16px; padding: 4px 0; }
.dt1-set-row { display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
.dt1-set-row label { font-weight: 500; color: #1d1d1f; }

.dt1-subitem-list {
  margin-top: 4px; margin-left: 12px;
  border-left: 2px solid #e2e8f0; padding-left: 10px;
  display: flex; flex-direction: column; gap: 4px;
}
.dt1-subitem-row {
  display: flex; align-items: center; gap: 8px;
  font-size: 11px; padding: 2px 0;
}
.dt1-sub-status { flex: none; }
.dt1-sub-name {
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-family: monospace; color: #475569;
}
.dt1-sub-bar { flex: none; width: 120px; }
.dt1-scan-progress {
  display: flex; align-items: center; gap: 12px;
  padding: 6px 0 8px;
}
.dt1-scan-bar { flex: 1; }
.dt1-scan-label { flex: none; font-size: 12px; color: #64748b; }
.dt1-cand-type-btns { display: flex; gap: 6px; }
.dt1-cand-type { flex: none; }
.dt1-job-dtype { flex: none; }
</style>
