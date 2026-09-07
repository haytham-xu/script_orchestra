<template>
  <div class="ba">
    <header class="ba-topbar">
      <div class="ba-topbar-left">
        <h1>Browser Agent</h1>
        <p class="ba-sub">Download queue from browser tabs</p>
      </div>
      <div class="ba-topbar-right">
        <el-button type="primary" @click="onSendCurrentTabs" :loading="sending">
          Send current tabs
        </el-button>
        <el-button :icon="Refresh" @click="load" :loading="loading">Refresh</el-button>
        <el-button :icon="Setting" @click="openSettings">Settings</el-button>
      </div>
    </header>

    <main class="ba-content" v-loading="loading">
      <el-empty v-if="tasks.length === 0 && !loading" description="No download tasks yet">
        <p class="ba-hint">
          Open some target pages in your browser, then click
          <b>Send current tabs</b> in the top-right to queue downloads.
        </p>
      </el-empty>

      <el-table v-else :data="tasks" style="width: 100%" size="small">
        <el-table-column prop="file_name" label="File" min-width="220" show-overflow-tooltip />
        <el-table-column prop="size" label="Size" width="90">
          <template #default="{ row }">{{ row.size }} MB</template>
        </el-table-column>
        <el-table-column label="Status" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Progress" min-width="160">
          <template #default="{ row }">
            <el-progress
              v-if="row.status === BrowserTaskStatus.InProgress"
              :percentage="liveProgress[row.id] || 0" />
            <span v-else-if="row.status === BrowserTaskStatus.Completed">100%</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="retry_times" label="Retries" width="80" />
        <el-table-column label="Actions" width="120">
          <template #default="{ row }">
            <el-button
              :icon="RefreshLeft" circle size="small"
              title="Retry"
              :disabled="row.status === BrowserTaskStatus.InProgress"
              @click="onRetry(row)" />
            <el-button
              :icon="Delete" circle size="small" type="danger"
              title="Delete"
              @click="onDelete(row)" />
          </template>
        </el-table-column>
      </el-table>
    </main>
  </div>

  <!-- Global settings drawer -->
  <el-drawer v-model="settingsOpen" title="Download Queue Settings" size="520px" direction="rtl">
    <div class="ba-settings">
      <div class="ba-set-row">
        <label>Download directory</label>
        <el-input v-model="settingsCfg.downloadDir" placeholder="/absolute/path/to/downloads" spellcheck="false" />
      </div>
      <div class="ba-set-row">
        <label>Max retries</label>
        <el-input-number v-model="settingsCfg.maxRetries" :min="0" :max="20" />
      </div>
      <div class="ba-set-row">
        <label>Poll interval (sec)</label>
        <el-input-number v-model="settingsCfg.pollIntervalSec" :min="5" :max="3600" :step="5" />
      </div>
      <div class="ba-set-row">
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
          <label>Site rules</label>
          <el-button size="small" :icon="Plus" @click="addRule">Add rule</el-button>
        </div>
        <div v-for="(rule, i) in settingsCfg.siteRules" :key="i" class="ba-rule-block">
          <div class="ba-rule-row">
            <span class="ba-rule-label">Domains</span>
            <el-input size="small" :model-value="domainsText(rule)"
              @update:model-value="v => setDomainsText(rule, v)"
              placeholder="foo.com, bar.com" spellcheck="false" />
            <el-button size="small" type="danger" :icon="Delete" @click="removeRule(i)" />
          </div>
          <div class="ba-rule-row">
            <span class="ba-rule-label">Overview URI</span>
            <el-input size="small" v-model="rule.overviewUriFormat" spellcheck="false" />
          </div>
          <div class="ba-rule-row">
            <span class="ba-rule-label">Download URI</span>
            <el-input size="small" v-model="rule.downloadUriFormat" spellcheck="false" />
          </div>
          <div class="ba-rule-row">
            <span class="ba-rule-label">Link regex</span>
            <el-input size="small" v-model="rule.downloadLinkRegex" spellcheck="false" />
          </div>
        </div>
      </div>
      <el-button type="primary" :loading="settingsSaving" @click="saveSettings" style="margin-top:8px">Save</el-button>
    </div>
  </el-drawer>
</template>

<script lang="ts" src="@/browser_agent/views/BrowserAgentView.ts"></script>

<style scoped>
.ba {
  min-height: 100vh;
  background: #f5f5f7;
  color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}
.ba-topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(245, 245, 247, 0.85);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  padding: 16px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.ba-topbar-left h1 { margin: 0; font-size: 20px; font-weight: 600; }
.ba-sub { margin: 2px 0 0; font-size: 12px; color: #86868b; }
.ba-topbar-right { display: flex; gap: 8px; }
.ba-content { max-width: 1100px; margin: 0 auto; padding: 24px; }
.ba-hint { font-size: 13px; color: #86868b; max-width: 420px; text-align: center; }
.ba-settings { display: flex; flex-direction: column; gap: 16px; padding: 4px 0; }
.ba-set-row { display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
.ba-set-row label { font-weight: 500; color: #1d1d1f; }
.ba-rule-block { border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; margin-bottom: 8px; background: #f8fafc; }
.ba-rule-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.ba-rule-row:last-child { margin-bottom: 0; }
.ba-rule-label { flex: none; width: 90px; font-size: 12px; color: #475569; font-weight: 500; }
</style>
