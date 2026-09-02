<template>
  <div class="tv-root" v-loading="busy" element-loading-text="Working…">
    <div class="tv-header">
      <el-button type="default" size="small" @click="goBack">← Browser Agent</el-button>
      <h2 class="tv-title">All Tabs</h2>
      <div class="tv-header-actions">
        <el-button @click="loadTabs" :loading="loading">Refresh</el-button>
        <el-button @click="mergeAll">Merge windows</el-button>
        <el-button @click="groupByDomain">Group by domain</el-button>
        <el-button type="danger" :disabled="selectedTabIds.size === 0" @click="closeSelected">
          Close selected ({{ selectedTabIds.size }})
        </el-button>
      </div>
    </div>

    <div class="tv-toolbar">
      <el-input
        v-model="search"
        placeholder="Filter by title or URL…"
        clearable
        class="tv-search"
      />
      <el-select v-model="sortKey" class="tv-sort">
        <el-option label="Group by window" value="window" />
        <el-option label="Sort by title"   value="title" />
        <el-option label="Sort by URL"     value="url" />
      </el-select>
      <span class="tv-summary">
        Showing {{ visibleTabs.length }} / {{ tabs.length }} tabs
      </span>
    </div>

    <el-empty v-if="!loading && tabs.length === 0" description="No tabs found">
      <p class="tv-hint">
        The list is empty. Check that the browser extension is installed and
        enabled at chrome://extensions/.
      </p>
    </el-empty>

    <div v-else class="tv-table">
      <div class="tv-row tv-row-head">
        <el-checkbox
          :model-value="allVisibleSelected"
          :indeterminate="someVisibleSelected"
          @change="toggleAllVisible"
        />
        <span class="tv-col-fav"></span>
        <span class="tv-col-title">Title</span>
        <span class="tv-col-url">URL</span>
        <span class="tv-col-win">Win</span>
        <span class="tv-col-actions"></span>
      </div>
      <label
        v-for="t in visibleTabs"
        :key="t.id"
        class="tv-row"
        :class="{ 'tv-selected': selectedTabIds.has(t.id) }">
        <el-checkbox
          :model-value="selectedTabIds.has(t.id)"
          @change="toggleTab(t.id)"
        />
        <img v-if="t.favIconUrl" :src="t.favIconUrl" class="tv-fav" @error="hideFavicon" />
        <span v-else class="tv-fav tv-fav-placeholder"></span>
        <span class="tv-col-title" :title="t.title">
          {{ t.title || '(no title)' }}
          <span v-if="t.pinned" class="tv-pin">📌</span>
        </span>
        <span class="tv-col-url" :title="t.url">{{ t.url }}</span>
        <span class="tv-col-win">{{ t.windowId }}</span>
        <span class="tv-col-actions">
          <el-button
            size="small"
            type="danger"
            text
            @click.stop.prevent="closeSingle(t.id)"
          >✕</el-button>
        </span>
      </label>
    </div>
  </div>
</template>

<script lang="ts" src="@/browser_agent/views/TabsView.ts"></script>

<style scoped>
.tv-root { padding: 24px 32px; box-sizing: border-box; }
.tv-header {
  display: flex; align-items: center; gap: 16px; margin-bottom: 20px;
}
.tv-title { margin: 0; font-size: 22px; font-weight: 600; flex: 1; }
.tv-header-actions { display: flex; gap: 8px; }

.tv-toolbar {
  display: flex; align-items: center; gap: 12px; margin-bottom: 12px;
}
.tv-search { max-width: 320px; }
.tv-sort { width: 200px; }
.tv-summary { color: #64748b; font-size: 13px; margin-left: auto; }

.tv-hint { color: #64748b; }

.tv-table {
  border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; background: #fff;
}
.tv-row {
  display: grid;
  grid-template-columns: 30px 24px minmax(180px, 1fr) minmax(200px, 2fr) 44px 44px;
  gap: 10px; align-items: center;
  padding: 8px 12px; border-top: 1px solid #f1f5f9;
  cursor: pointer; user-select: none; font-size: 13px;
}
.tv-row:first-child { border-top: none; }
.tv-row:hover:not(.tv-row-head) { background: #fafcfe; }
.tv-selected { background: #eff6ff; }
.tv-selected:hover { background: #dbeafe !important; }

.tv-row-head {
  background: #f1f5f9; font-weight: 600; color: #475569; font-size: 12px;
  cursor: default;
}
.tv-row-head:hover { background: #f1f5f9; }

.tv-fav, .tv-col-fav {
  width: 16px; height: 16px; flex: none; border-radius: 3px;
}
.tv-fav-placeholder { background: #e2e8f0; }

.tv-col-title, .tv-col-url {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tv-col-title { color: #1e293b; }
.tv-col-url { color: #64748b; font-family: monospace; font-size: 12px; }
.tv-col-win { color: #64748b; text-align: center; font-family: monospace; }
.tv-col-actions { text-align: right; }

.tv-pin { margin-left: 6px; font-size: 11px; }
</style>
