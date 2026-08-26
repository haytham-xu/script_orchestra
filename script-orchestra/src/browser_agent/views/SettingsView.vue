<template>
  <div class="ba-settings">
    <header class="ba-topbar">
      <div class="ba-topbar-left">
        <el-button link @click="goBack" class="ba-back">
          <el-icon><ArrowLeft /></el-icon>
          <span>Browser Agent</span>
        </el-button>
        <h1>Settings</h1>
      </div>
      <div class="ba-topbar-right">
        <el-button :icon="Refresh" @click="load" :loading="loading" text />
        <el-button type="primary" @click="save" :disabled="!isDirty || saving" :loading="saving">
          Save
        </el-button>
      </div>
    </header>

    <main class="ba-content" v-loading="loading">
      <!-- Download -->
      <section class="ba-card">
        <div class="ba-card-header">
          <h2>Download</h2>
          <p class="ba-hint">Where files are saved and how the queue behaves.</p>
        </div>
        <div class="ba-card-body">
          <div class="ba-row">
            <label class="ba-label">Download directory</label>
            <el-input v-model="state.downloadDir" placeholder="/absolute/path/to/downloads" spellcheck="false" />
          </div>
          <div class="ba-row">
            <label class="ba-label">Max retries</label>
            <el-input-number v-model="state.maxRetries" :min="0" :max="20" controls-position="right" />
          </div>
          <div class="ba-row">
            <label class="ba-label">Poll interval (sec)</label>
            <el-input-number v-model="state.pollIntervalSec" :min="5" :max="3600" :step="5" controls-position="right" />
          </div>
        </div>
      </section>

      <!-- Site rules -->
      <section class="ba-card">
        <div class="ba-card-header">
          <h2>Site rules</h2>
          <p class="ba-hint">How to recognize target pages and extract the real download link.</p>
        </div>
        <div class="ba-card-body">
          <div v-if="state.siteRules.length === 0" class="ba-empty">No rules yet</div>
          <div v-for="(rule, i) in state.siteRules" :key="i" class="ba-rule">
            <div class="ba-rule-head">
              <span>Rule {{ i + 1 }}</span>
              <el-button :icon="Delete" size="small" text type="danger" @click="removeRule(i)" />
            </div>
            <div class="ba-row">
              <label class="ba-label">Domains</label>
              <el-input
                :model-value="domainsText(rule)"
                @update:model-value="(v: string) => setDomainsText(rule, v)"
                placeholder="www.a.com, www.b.com" spellcheck="false" />
            </div>
            <div class="ba-row">
              <label class="ba-label">Overview URI</label>
              <el-input v-model="rule.overviewUriFormat" placeholder="photos-slide-aid-{aid}.html" spellcheck="false" />
            </div>
            <div class="ba-row">
              <label class="ba-label">Download URI</label>
              <el-input v-model="rule.downloadUriFormat" placeholder="download-index-aid-{aid}.html" spellcheck="false" />
            </div>
            <div class="ba-row">
              <label class="ba-label">Link regex</label>
              <el-input v-model="rule.downloadLinkRegex" placeholder="href=&quot;(//...\.zip\?n=[^&quot;]+)&quot;" spellcheck="false" />
            </div>
          </div>
          <el-button :icon="Plus" size="small" @click="addRule" text>Add rule</el-button>
        </div>
      </section>
    </main>
  </div>
</template>

<script lang="ts" src="@/browser_agent/views/SettingsView.ts"></script>

<style scoped>
.ba-settings {
  min-height: 100vh;
  background: #f5f5f7;
  color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}
.ba-topbar {
  position: sticky; top: 0; z-index: 10;
  background: rgba(245, 245, 247, 0.85);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  padding: 12px 24px;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
}
.ba-topbar-left { display: flex; align-items: baseline; gap: 16px; }
.ba-back { color: #0071e3; }
.ba-topbar h1 { font-size: 17px; font-weight: 600; margin: 0; }
.ba-topbar-right { display: flex; align-items: center; gap: 8px; }
.ba-content { max-width: 820px; margin: 0 auto; padding: 24px; display: flex; flex-direction: column; gap: 20px; }
.ba-card { background: #fff; border-radius: 12px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); overflow: hidden; }
.ba-card-header { padding: 16px 20px 8px; }
.ba-card-header h2 { font-size: 15px; font-weight: 600; margin: 0 0 4px; }
.ba-hint { font-size: 12px; color: #86868b; margin: 0; }
.ba-card-body { padding: 8px 20px 16px; display: flex; flex-direction: column; gap: 12px; }
.ba-row { display: grid; grid-template-columns: 130px 1fr; align-items: center; gap: 12px; }
.ba-label { font-size: 13px; color: #1d1d1f; }
.ba-rule { background: #fbfbfd; border-radius: 10px; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.ba-rule-head { display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 600; color: #86868b; }
.ba-empty { font-size: 12px; color: #b0b0b6; font-style: italic; }
@media (max-width: 720px) {
  .ba-row { grid-template-columns: 1fr; align-items: stretch; }
}
</style>
