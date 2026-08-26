<template>
  <div class="ba">
    <header class="ba-topbar">
      <div class="ba-topbar-left">
        <h1>Browser Agent</h1>
        <p class="ba-sub">Download queue from browser tabs</p>
      </div>
      <div class="ba-topbar-right">
        <el-button :icon="Refresh" @click="load" :loading="loading">Refresh</el-button>
        <el-button :icon="Setting" @click="goToSettings">Settings</el-button>
      </div>
    </header>

    <main class="ba-content" v-loading="loading">
      <el-empty v-if="tasks.length === 0 && !loading" description="No download tasks yet">
        <p class="ba-hint">
          Open some target pages in your browser, then click
          <b>Send all tabs to download queue</b> in the Browser Agent extension.
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
</style>
