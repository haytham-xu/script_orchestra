<template>
  <div class="fg-detail" v-loading="isLoading">
    <header class="fg-topbar">
      <div class="fg-topbar-left">
        <el-button link @click="goToDetail">
          <el-icon><ArrowLeft /></el-icon>
          <span>{{ repo?.name ?? 'Repository' }}</span>
        </el-button>
        <h1>Manual Transfer</h1>
      </div>
      <div class="fg-topbar-right">
        <el-button :icon="Refresh" size="small" @click="loadAll">Refresh</el-button>
      </div>
    </header>

    <main class="fg-content">

      <section class="fg-card fg-card-info">
        <p class="fg-info-text">
          Use when automated push/pull is too slow or you want to move individual files.
          You drag files yourself via the cloud app; this tool handles encryption, index tracking, and lock management.
          See <strong>Doc</strong> in the repo header for full details.
        </p>
      </section>

      <section class="fg-card">
        <h2>Manual Upload</h2>
        <el-form label-position="top" style="margin-bottom: 8px;">
          <el-form-item label="Subpath (relative, empty = whole repo)">
            <el-input
              v-model="manualSubpath"
              placeholder="e.g. photos/2024"
              :disabled="isLocked" />
          </el-form-item>
        </el-form>
        <div class="fg-action-row">
          <el-button :icon="Upload" :disabled="!canManualUploadPrepare" @click="manualUpload">Prepare</el-button>
          <el-button :icon="Check" :disabled="!canPostManualUpload" @click="postManualUpload">Confirm</el-button>
        </div>
      </section>

      <section class="fg-card">
        <h2>Manual Download</h2>
        <div class="fg-action-row">
          <el-button :icon="Download" :disabled="!canPreManualDownload" @click="preManualDownload">Acquire Lock</el-button>
          <el-button :icon="Check" :disabled="!canPostManualDownload" @click="postManualDownload">Decrypt &amp; Reconcile</el-button>
        </div>
      </section>

    </main>
  </div>
</template>

<script lang="ts" setup>
import { useRouter, useRoute } from 'vue-router'
import { useFileGitRepoDetail } from './FileGitRepoDetailView'
import { ArrowLeft, Refresh, Upload, Download, Check } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

const view = useFileGitRepoDetail()
const {
  repo, isLoading, isBusy,
  isLocked, isEncrypted,
  canManualUploadPrepare, canPostManualUpload,
  canPreManualDownload, canPostManualDownload,
  manualSubpath,
  loadAll,
  manualUpload, postManualUpload,
  preManualDownload, postManualDownload,
} = view

function goToDetail() {
  router.push(`/file-git/${route.params.id}`)
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
.fg-card-info {
  background: #f0f7ff;
  border: 1px solid #c8e0ff;
}
.fg-info-text {
  font-size: 13px;
  color: #2c5282;
  margin: 0;
  line-height: 1.6;
}
.fg-card h2 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 12px;
}
.fg-hint {
  font-size: 12px;
  color: #86868b;
  margin: 0 0 12px;
}
.fg-action-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
