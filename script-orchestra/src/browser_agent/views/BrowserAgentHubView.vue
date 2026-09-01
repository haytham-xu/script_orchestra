<template>
  <div class="ba-hub">
    <div class="ba-header">
      <el-button type="default" size="small" @click="$router.push('/')">← Home</el-button>
      <h2 class="ba-title">Browser Agent</h2>
    </div>
    <div class="ba-grid">
      <div
        v-for="t in tools"
        :key="t.key"
        class="ba-cell"
        @click="goTo(t.path)">
        <div class="ba-icon" v-html="t.icon"></div>
        <div class="ba-name">{{ t.name }}</div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" src="@/browser_agent/views/BrowserAgentHubView.ts"></script>

<style scoped>
.ba-hub { min-height: 100vh; padding: 32px; box-sizing: border-box; }
.ba-header {
  display: flex; align-items: center; gap: 16px; margin-bottom: 24px;
}
.ba-title { margin: 0; font-size: 22px; font-weight: 600; }
.ba-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 32px 28px;
}
.ba-cell {
  width: 190px; height: 190px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 14px; cursor: pointer; border-radius: 24px;
  transition: transform 0.15s, background 0.15s;
}
.ba-cell:hover { transform: translateY(-2px); background: rgba(0,0,0,0.03); }
.ba-icon { width: 112px; height: 112px; pointer-events: none; }
.ba-icon :deep(svg) { width: 100%; height: 100%; display: block; }
.ba-name {
  font-size: 15px; font-weight: 600; color: #303133; text-align: center;
  max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  pointer-events: none;
}
</style>
