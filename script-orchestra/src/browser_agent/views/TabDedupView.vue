<template>
  <div class="td-root" v-loading="busy" element-loading-text="Working…">
    <div class="td-header">
      <el-button type="default" size="small" @click="goBack">← Browser Agent</el-button>
      <h2 class="td-title">Tab Dedup</h2>
      <div class="td-header-actions">
        <el-button :icon="undefined" @click="loadTabs" :loading="loading">Refresh</el-button>
        <el-button type="danger" :disabled="selectedTabIds.size === 0" @click="closeSelected">
          Close selected ({{ selectedTabIds.size }})
        </el-button>
      </div>
    </div>

    <div class="td-summary">
      <div class="td-stat">
        <div class="td-stat-label">All tabs</div>
        <div class="td-stat-value">{{ tabs.length }}</div>
      </div>
      <div class="td-stat">
        <div class="td-stat-label">Duplicate groups</div>
        <div class="td-stat-value">{{ dupeGroups.length }}</div>
      </div>
      <div class="td-stat">
        <div class="td-stat-label">Duplicate tabs</div>
        <div class="td-stat-value">{{ totalDupeTabs }}</div>
      </div>
      <div class="td-stat">
        <div class="td-stat-label">Closable if you keep 1 of each</div>
        <div class="td-stat-value">{{ closableCount }}</div>
      </div>
    </div>

    <el-empty v-if="!loading && dupeGroups.length === 0" description="No duplicate tabs found 🎉">
      <p class="td-hint" v-if="tabs.length === 0">
        The list is empty. Please check if the browser extension is installed and enabled (chrome://extensions/).
      </p>
      <p class="td-hint" v-else>Scanned {{ tabs.length }} tabs, all URLs are unique.</p>
    </el-empty>

    <div v-else class="td-groups">
      <div v-for="g in dupeGroups" :key="g.normalizedUrl" class="td-group">
        <div class="td-group-head">
          <span class="td-group-count">{{ g.tabs.length }} tabs</span>
          <span class="td-group-url" :title="g.normalizedUrl">{{ g.normalizedUrl }}</span>
          <div class="td-group-actions">
            <el-button size="small" text @click="selectAllInGroup(g, true)">Mark all but 1st</el-button>
            <el-button size="small" text @click="clearGroupSelection(g)">Clear</el-button>
          </div>
        </div>
        <div class="td-group-body">
          <label
            v-for="(t, i) in g.tabs"
            :key="t.id"
            class="td-tab-row"
            :class="{ 'td-tab-keep': !selectedTabIds.has(t.id) && i === 0 }">
            <el-checkbox
              :model-value="selectedTabIds.has(t.id)"
              @change="toggleTab(t.id)" />
            <img v-if="t.favIconUrl" :src="t.favIconUrl" class="td-fav" @error="hideFavicon" />
            <span v-else class="td-fav td-fav-placeholder"></span>
            <span class="td-tab-title" :title="t.title">{{ t.title || '(no title)' }}</span>
            <span class="td-tab-meta" v-if="t.pinned">📌</span>
            <span class="td-tab-meta">win {{ t.windowId }}</span>
          </label>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" src="@/browser_agent/views/TabDedupView.ts"></script>

<style scoped>
.td-root { padding: 24px 32px; box-sizing: border-box; }
.td-header {
  display: flex; align-items: center; gap: 16px; margin-bottom: 20px;
}
.td-title { margin: 0; font-size: 22px; font-weight: 600; flex: 1; }
.td-header-actions { display: flex; gap: 8px; }
.td-summary {
  display: flex; gap: 32px; padding: 16px 20px; background: #f8fafc;
  border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 20px;
}
.td-stat-label { font-size: 12px; color: #64748b; }
.td-stat-value { font-size: 22px; font-weight: 600; color: #0f172a; }
.td-hint { color: #64748b; }

.td-groups { display: flex; flex-direction: column; gap: 14px; }
.td-group {
  border: 1px solid #e2e8f0; border-radius: 8px; background: #fff;
  overflow: hidden;
}
.td-group-head {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px; background: #f1f5f9; border-bottom: 1px solid #e2e8f0;
  font-size: 13px;
}
.td-group-count {
  background: #0891b2; color: #fff; padding: 2px 8px; border-radius: 10px;
  font-weight: 600; font-size: 12px;
}
.td-group-url {
  flex: 1; color: #334155; font-family: monospace; font-size: 12px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.td-group-actions { display: flex; gap: 4px; }

.td-group-body { display: flex; flex-direction: column; }
.td-tab-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 14px; border-top: 1px solid #f1f5f9;
  cursor: pointer; user-select: none;
}
.td-tab-row:first-child { border-top: none; }
.td-tab-row:hover { background: #fafcfe; }
.td-tab-keep { background: #f0fdf4; }
.td-tab-keep:hover { background: #dcfce7; }
.td-fav {
  width: 16px; height: 16px; flex: none; border-radius: 3px;
}
.td-fav-placeholder { background: #e2e8f0; }
.td-tab-title {
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 13px; color: #1e293b;
}
.td-tab-meta {
  font-size: 11px; color: #64748b; padding: 2px 6px; background: #f1f5f9; border-radius: 4px;
}
</style>
