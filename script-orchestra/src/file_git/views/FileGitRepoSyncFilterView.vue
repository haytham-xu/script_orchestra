<template>
  <div class="fg-detail" v-loading="isLoading">
    <header class="fg-topbar">
      <div class="fg-topbar-left">
        <el-button link @click="goToDetail">
          <el-icon><ArrowLeft /></el-icon>
          <span>{{ repo?.name ?? 'Repository' }}</span>
        </el-button>
        <h1>Sync Filter</h1>
      </div>
      <div class="fg-topbar-right">
        <el-button type="primary" :icon="Check" size="small" :loading="isBusy" @click="applyFilter">Apply</el-button>
      </div>
    </header>

    <main class="fg-content">

      <section class="fg-card">
        <el-tree
          ref="syncTreeRef"
          :key="syncTreeKey"
          lazy
          :load="loadSyncChildren"
          :props="{ label: 'label', isLeaf: 'isLeaf' }"
          node-key="path">
          <template #default="{ data }">
            <span class="fg-sync-node">
              <span class="fg-sync-name">{{ data.label }}</span>
              <template v-if="data.can_set && data.can_set.length > 0">
                <el-select
                  :model-value="data.mode"
                  size="small"
                  class="fg-sync-select"
                  @change="(val: string) => setSyncNodeMode(data.path, val as any)"
                  @click.stop>
                  <el-option
                    v-for="m in data.can_set"
                    :key="m"
                    :label="modeLabel(m)"
                    :value="m" />
                </el-select>
              </template>
              <el-tag v-else size="small" type="info" class="fg-sync-inherited">inherited</el-tag>
              <el-tag size="small" :type="statusTagType(data.status)" class="fg-sync-status">
                {{ data.status }}
              </el-tag>
            </span>
          </template>
        </el-tree>

      </section>

    </main>
  </div>
</template>

<script lang="ts" setup>
import { useRouter, useRoute } from 'vue-router'
import { useFileGitRepoDetail } from './FileGitRepoDetailView'
import { ArrowLeft, Check } from '@element-plus/icons-vue'
import type { SyncMode } from '../service/FileGitService'

const router = useRouter()
const route = useRoute()

const view = useFileGitRepoDetail()
const {
  repo, isLoading, isBusy,
  syncTreeRef, syncTreeKey, loadSyncChildren, setSyncNodeMode,
  applyFilter,
} = view

function goToDetail() {
  router.push(`/file-git/${route.params.id}`)
}

function statusTagType(status: string) {
  if (status === 'synced') return 'success'
  if (status?.startsWith('pending')) return 'warning'
  if (status?.startsWith('conflict')) return 'danger'
  return 'info'
}

function modeLabel(mode: SyncMode) {
  if (mode === 'synced') return 'Synced'
  if (mode === 'remote-only') return 'Remote Only'
  if (mode === 'local-only') return 'Local Only'
  return mode
}
</script>

<style scoped>
.fg-detail {
  min-height: 100vh;
  background: #f5f5f7;
  color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}
.fg-topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(245, 245, 247, 0.85);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  padding: 12px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.fg-topbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.fg-topbar-left h1 {
  font-size: 17px;
  margin: 0;
  font-weight: 600;
}
.fg-topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.fg-content {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.fg-card {
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  padding: 16px 20px;
}
.fg-sync-node {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.fg-sync-name { font-size: 13px; }
.fg-sync-select { width: 130px; flex-shrink: 0; }
.fg-sync-status { flex-shrink: 0; }
.fg-sync-inherited { opacity: 0.55; }
</style>
