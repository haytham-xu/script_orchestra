<template>
  <div class="ck-root">
    <!-- Header -->
    <div class="ck-header">
      <el-button size="small" @click="$router.push('/manga-viewer/batch')">← Back</el-button>
      <h2 class="ck-title">Clean Keyword</h2>
      <span class="ck-subtitle">Strip noise keywords from folder names</span>
    </div>

    <div class="ck-body">
      <!-- Left: keyword list -->
      <div class="ck-sidebar">
        <div class="ck-section-title">
          Keywords
          <span class="ck-count">({{ keywords.length }})</span>
        </div>

        <div class="ck-add-row">
          <el-input v-model="newKw" placeholder="Add keyword..." size="small"
            @keyup.enter="addKw" />
          <el-button type="primary" size="small" @click="addKw">Add</el-button>
        </div>

        <el-button size="small" style="margin-bottom:10px;width:100%"
          @click="importDialogVisible = true">Import bulk...</el-button>

        <div class="ck-kw-list">
          <div v-if="!keywords.length" class="ck-empty">No keywords yet.</div>
          <div v-for="kw in keywords" :key="kw" class="ck-kw-item">
            <span class="ck-kw-text" :title="kw">{{ kw }}</span>
            <el-button link type="danger" size="small" @click="removeKw(kw)">×</el-button>
          </div>
        </div>
      </div>

      <!-- Right: preview + apply -->
      <div class="ck-main">
        <div class="ck-section-title">Preview</div>

        <div class="ck-path-row">
          <span class="ck-path-label">Root path:</span>
          <span class="ck-path-value" :title="rootPath">{{ rootPath || '(not configured — set in Manga Viewer Settings)' }}</span>
          <el-button size="small" @click="runPreview" :loading="previewing" :disabled="!rootPath">
            Preview
          </el-button>
          <el-button type="primary" size="small" @click="runApply" :loading="applying"
            :disabled="!rootPath || !previewItems.length">
            Apply ({{ previewItems.length }})
          </el-button>
        </div>

        <div v-if="previewItems.length" class="ck-summary">
          {{ previewItems.length }} folders will be renamed
          <template v-if="conflictCount"> · <span class="ck-conflict-badge">{{ conflictCount }} conflicts auto-resolved</span></template>
        </div>

        <div v-if="previewItems.length" class="ck-table-wrap">
          <table class="ck-table">
            <thead>
              <tr>
                <th>Original name</th>
                <th>New name</th>
                <th>Conflict</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in previewItems" :key="item.old_name"
                :class="{ 'ck-row-conflict': item.conflict }">
                <td class="ck-cell-old">{{ item.old_name }}</td>
                <td class="ck-cell-new">{{ item.resolved }}</td>
                <td class="ck-cell-conflict">
                  <span v-if="item.conflict" class="ck-conflict-tag">resolved → _N</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="previewDone" class="ck-empty-preview">
          No folders need renaming.
        </div>
      </div>
    </div>

    <!-- Import dialog -->
    <el-dialog v-model="importDialogVisible" title="Import keywords" width="480px">
      <div class="ck-import-hint">One keyword per line. Duplicates are skipped.</div>
      <el-input type="textarea" v-model="importText" :rows="12"
        placeholder="keyword1&#10;keyword2&#10;..." />
      <template #footer>
        <el-button @click="importDialogVisible = false">Cancel</el-button>
        <el-button type="primary" @click="doImport" :loading="importing">Import</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import * as svc from '@/clean_keyword/service/CleanKeywordService'
import type { PreviewItem } from '@/clean_keyword/service/CleanKeywordService'
import { getRequest } from '@/basic/RequestService'
import { BACKEND_BASE_URL, MANGA_VIEWER_SETTINGS_ENDPOINT } from '@/basic/Constants'

const keywords = ref<string[]>([])
const newKw = ref('')

const rootPath = ref('')
const previewItems = ref<PreviewItem[]>([])
const previewDone = ref(false)
const previewing = ref(false)
const applying = ref(false)

const importDialogVisible = ref(false)
const importText = ref('')
const importing = ref(false)

const conflictCount = computed(() => previewItems.value.filter(i => i.conflict).length)

onMounted(async () => {
  await loadKeywords()
  await loadRootPath()
})

async function loadKeywords() {
  keywords.value = await svc.fetchKeywords()
}

async function loadRootPath() {
  try {
    const res = await getRequest(`${BACKEND_BASE_URL}${MANGA_VIEWER_SETTINGS_ENDPOINT}`) as any
    rootPath.value = res?.root_path ?? res?.rootPath ?? ''
  } catch {}
}

async function addKw() {
  const kw = newKw.value.trim()
  if (!kw) return
  try {
    keywords.value = await svc.addKeyword(kw)
    newKw.value = ''
  } catch (e: any) {
    if (e?.response?.status === 409) ElMessage.warning('Keyword already exists')
  }
}

async function removeKw(kw: string) {
  await svc.deleteKeyword(kw)
  keywords.value = keywords.value.filter(k => k !== kw)
}

async function doImport() {
  if (!importText.value.trim()) return
  importing.value = true
  try {
    const res = await svc.importKeywords(importText.value)
    keywords.value = res.keywords
    ElMessage.success(`Imported ${res.added} keywords`)
    importDialogVisible.value = false
    importText.value = ''
  } finally {
    importing.value = false
  }
}

async function runPreview() {
  if (!rootPath.value) return
  previewing.value = true
  previewDone.value = false
  try {
    const res = await svc.previewClean(rootPath.value)
    previewItems.value = res.items
    previewDone.value = true
  } finally {
    previewing.value = false
  }
}

async function runApply() {
  if (!rootPath.value) return
  applying.value = true
  try {
    const res = await svc.applyClean(rootPath.value)
    const msg = `Renamed ${res.renamed} folders`
    if (res.errors.length) {
      ElMessage.warning(`${msg}, ${res.errors.length} errors`)
    } else {
      ElMessage.success(msg)
    }
    // Refresh preview after apply
    await runPreview()
  } finally {
    applying.value = false
  }
}
</script>

<style scoped>
.ck-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  padding: 20px;
  box-sizing: border-box;
  gap: 16px;
}

.ck-header {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-shrink: 0;
}
.ck-title { margin: 0; font-size: 20px; font-weight: 600; }
.ck-subtitle { font-size: 13px; color: #909399; }

.ck-body {
  display: flex;
  gap: 20px;
  flex: 1;
  min-height: 0;
}

/* Sidebar */
.ck-sidebar {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px solid #e4e7ed;
  border-radius: 12px;
  padding: 14px;
  background: #fff;
  overflow: hidden;
}
.ck-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 2px;
}
.ck-count { font-weight: 400; color: #909399; }
.ck-add-row { display: flex; gap: 6px; }
.ck-kw-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  scrollbar-width: thin;
}
.ck-kw-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 6px;
  border-radius: 6px;
  font-size: 12px;
  background: #f5f7fa;
}
.ck-kw-item:hover { background: #eef0f4; }
.ck-kw-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #303133;
}
.ck-empty { font-size: 12px; color: #c0c4cc; padding: 8px 0; text-align: center; }

/* Main area */
.ck-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 12px;
  padding: 14px;
  background: #fff;
  overflow: hidden;
}
.ck-path-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.ck-path-label { font-size: 12px; font-weight: 600; color: #606266; flex-shrink: 0; }
.ck-path-value {
  flex: 1; min-width: 0;
  font-size: 12px; color: #303133;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.ck-summary {
  font-size: 13px;
  color: #606266;
  flex-shrink: 0;
}
.ck-conflict-badge {
  color: #e6a23c;
  font-weight: 600;
}

.ck-table-wrap {
  flex: 1;
  overflow-y: auto;
  scrollbar-width: thin;
}
.ck-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.ck-table th {
  text-align: left;
  padding: 6px 10px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
  font-weight: 600;
  color: #606266;
  position: sticky;
  top: 0;
}
.ck-table td {
  padding: 5px 10px;
  border-bottom: 1px solid #f0f2f5;
  vertical-align: middle;
}
.ck-row-conflict { background: #fdf6ec; }
.ck-cell-old { color: #909399; }
.ck-cell-new { color: #303133; font-weight: 500; }
.ck-conflict-tag {
  font-size: 11px;
  background: #fdf6ec;
  color: #e6a23c;
  border: 1px solid #f5dab1;
  border-radius: 4px;
  padding: 1px 5px;
}

.ck-empty-preview {
  font-size: 13px;
  color: #c0c4cc;
  text-align: center;
  padding: 40px 0;
}

.ck-import-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}
</style>
