<template>
  <div class="unzip-container">
    <el-card class="main-card">
      <template #header>
        <div class="card-header">
          <div style="display:flex;align-items:center;gap:10px;">
            <el-button @click="goBack" circle size="small"><el-icon><ArrowLeft /></el-icon></el-button>
            <h2>Unzip Tool</h2>
          </div>
          <span class="subtitle">Extract archives locally</span>
        </div>
      </template>

      <!-- Single Path Input -->
      <div class="input-section">
        <el-input
          v-model="inputPath"
          placeholder="/path/to/archive.zip or /path/to/folder/"
          clearable
          :disabled="isProcessing"
          @keyup.enter="extract"
        >
          <template #prepend>Path</template>
        </el-input>
        <p class="hint">
          Enter file path or folder path (scans current level only)
        </p>
      </div>

      <el-button
        type="primary"
        :loading="isProcessing"
        :disabled="!inputPath"
        @click="extract"
        class="extract-button"
      >
        {{ isProcessing ? 'Extracting...' : 'Extract' }}
      </el-button>

      <!-- Tips -->
      <el-alert
        type="info"
        :closable="false"
        style="margin-top: 20px"
      >
        <template #title>
          <strong>Tips:</strong>
        </template>
        <ul class="tips-list">
          <li><strong>File:</strong> Extract single archive to same directory</li>
          <li><strong>Folder:</strong> Extract all archives in folder (not recursive)</li>
          <li>Supports: .zip, .rar (requires UnRAR), .7z</li>
          <li>Get path: Right-click file in Finder → Hold Option → Copy Pathname</li>
        </ul>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useUnzipView } from './UnzipView'

const router = useRouter()
function goBack() { router.push('/') }

const {
  inputPath,
  isProcessing,
  extract
} = useUnzipView()
</script>

<style scoped>
.unzip-container {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
}

.main-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.card-header h2 {
  margin: 0;
  font-size: 24px;
}

.subtitle {
  color: #909399;
  font-size: 14px;
}

/* Input Section */
.input-section {
  margin-bottom: 20px;
}

.hint {
  margin-top: 8px;
  font-size: 13px;
  color: #909399;
}

.extract-button {
  width: 100%;
  height: 48px;
  font-size: 16px;
}

/* Tips */
.tips-list {
  margin: 8px 0 0 0;
  padding-left: 20px;
  font-size: 14px;
  line-height: 1.8;
}

.tips-list code {
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 13px;
}
</style>
