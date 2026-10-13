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
        <ProgressPopover v-model:visible="progressVisible" :items="progressItems" :count="progressActiveCount" />
        <el-button type="primary" :icon="Check" size="small" :loading="isBusy" @click="applyFilter">Apply</el-button>
      </div>
    </header>

    <main class="fg-content">

      <section class="fg-card" v-loading="syncLoading" element-loading-text="Loading…">
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
              <!-- Encrypted cloud path hint — only for ENCRYPTED repos -->
              <el-tooltip
                v-if="isEncrypted"
                placement="top"
                :hide-after="0"
                effect="dark">
                <template #content>
                  <div class="fg-enc-tooltip">
                    <div class="fg-enc-tooltip-label">Cloud path (encoded)</div>
                    <div class="fg-enc-tooltip-path">{{ encodeCache[data.path] ?? 'Loading…' }}</div>
                  </div>
                </template>
                <el-icon
                  class="fg-sync-enc-icon"
                  @mouseenter.stop="fetchEncoded(data.path)"
                  @click.stop>
                  <InfoFilled />
                </el-icon>
              </el-tooltip>
            </span>
          </template>
        </el-tree>

      </section>

    </main>
  </div>
</template>

<script lang="ts" setup>
import { reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useFileGitRepoDetail } from './FileGitRepoDetailView'
import { ArrowLeft, Check, InfoFilled } from '@element-plus/icons-vue'
import type { SyncMode } from '../service/FileGitService'
import { FileGitService } from '../service/FileGitService'
import ProgressPopover from '../components/ProgressPopover.vue'

const router = useRouter()
const route = useRoute()

const view = useFileGitRepoDetail()
const {
  repo, isLoading, isBusy, isEncrypted, repoId,
  finalRemotePath,
  syncTreeRef, syncTreeKey, syncLoading, loadSyncChildren, setSyncNodeMode,
  applyFilter,
  progressItems, progressVisible, progressActiveCount,
} = view

// Cache: path → full cloud path (encoded)
const encodeCache = reactive<Record<string, string>>({})

async function fetchEncoded(path: string) {
  if (encodeCache[path] !== undefined) return
  encodeCache[path] = 'Loading…'
  try {
    const res = await FileGitService.encodePath(repoId.value, path)
    if (res.success && res.encoded) {
      const base = finalRemotePath.value
      encodeCache[path] = base ? `${base}/${res.encoded}` : res.encoded
    } else {
      encodeCache[path] = '(error)'
    }
  } catch {
    encodeCache[path] = '(error)'
  }
}

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
.fg-sync-enc-icon {
  font-size: 13px;
  color: #c0c4cc;
  cursor: default;
  flex-shrink: 0;
  vertical-align: middle;
}
.fg-sync-enc-icon:hover { color: #409eff; }
.fg-enc-tooltip { line-height: 1.5; }
.fg-enc-tooltip-label {
  font-size: 11px;
  opacity: 0.65;
  margin-bottom: 2px;
}
.fg-enc-tooltip-path {
  font-family: monospace;
  font-size: 12px;
  word-break: break-all;
  max-width: 480px;
}
</style>
