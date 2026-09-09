<template>
  <div class="ci-root">
    <div class="ci-header">
      <el-button type="default" size="small" @click="$router.back()">← Back</el-button>
      <h2 class="ci-title">Compress Image</h2>
    </div>

    <div class="ci-body">
      <!-- Params -->
      <el-card class="ci-params" shadow="never">
        <template #header><span class="panel-title">Parameters</span></template>
        <el-form label-position="top" size="small">
          <el-form-item label="Image path (file or folder)">
            <el-input v-model="form.root_path" placeholder="/path/to/images" clearable />
          </el-form-item>
          <el-form-item label="Target size (KB)">
            <el-input-number v-model="form.target_kb" :min="10" :step="100" :precision="0" style="width:100%" />
          </el-form-item>
          <el-form-item label="Output mode">
            <el-radio-group v-model="outputMode">
              <el-radio value="overwrite">Overwrite original</el-radio>
              <el-radio value="suffix">Add _compressed suffix (same folder)</el-radio>
              <el-radio value="dir">Output to specific folder</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="outputMode === 'dir'" label="Output folder">
            <el-input v-model="form.output_dir" placeholder="/path/to/output" clearable />
          </el-form-item>

          <div style="display:flex;gap:8px;margin-top:8px">
            <el-button type="default" @click="doPreview" :loading="previewLoading" style="flex:1">Preview</el-button>
            <el-button type="primary" @click="doApply" :loading="applyLoading" :disabled="!previewResult" style="flex:1">Apply</el-button>
          </div>
        </el-form>
      </el-card>

      <!-- Results -->
      <div class="ci-results">
        <!-- Preview mode -->
        <template v-if="previewResult && !applyResult">
          <div class="ci-summary">
            <div class="sum-chip">Total: <b>{{ previewResult.total }}</b></div>
            <div class="sum-chip orange">To compress: <b>{{ previewResult.eligible }}</b></div>
            <div class="sum-chip">Total size: <b>{{ fmtKb(previewResult.total_size_kb) }}</b></div>
          </div>
          <el-table :data="previewResult.items" size="small" height="500" stripe>
            <el-table-column prop="name" label="File" show-overflow-tooltip />
            <el-table-column prop="size_kb" label="Size" width="100">
              <template #default="{ row }">{{ fmtKb(row.size_kb) }}</template>
            </el-table-column>
            <el-table-column label="Status" width="130">
              <template #default="{ row }">
                <el-tag :type="row.needs_compress ? 'warning' : 'success'" size="small">
                  {{ row.needs_compress ? 'Will compress' : 'Already small' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </template>

        <!-- Apply result -->
        <template v-if="applyResult">
          <div class="ci-summary">
            <div class="sum-chip green">Compressed: <b>{{ applyResult.compressed }}</b></div>
            <div class="sum-chip">Skipped: <b>{{ applyResult.skipped }}</b></div>
            <div class="sum-chip" :class="{ red: applyResult.errors > 0 }">Errors: <b>{{ applyResult.errors }}</b></div>
            <div class="sum-chip green">Saved: <b>{{ fmtKb(applyResult.total_saved_kb) }}</b></div>
          </div>
          <el-table :data="applyResult.results" size="small" height="500" stripe>
            <el-table-column prop="name" label="File" show-overflow-tooltip />
            <el-table-column label="Before" width="100">
              <template #default="{ row }">{{ fmtKb(row.before_kb) }}</template>
            </el-table-column>
            <el-table-column label="After" width="100">
              <template #default="{ row }">
                <span v-if="row.after_kb !== null">{{ fmtKb(row.after_kb) }}</span>
                <span v-else class="red">—</span>
              </template>
            </el-table-column>
            <el-table-column label="Saved" width="90">
              <template #default="{ row }">
                <span v-if="row.after_kb !== null" class="green">{{ fmtKb(row.before_kb - row.after_kb) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="Status" width="130">
              <template #default="{ row }">
                <el-tag v-if="row.error" type="danger" size="small">Error</el-tag>
                <el-tag v-else-if="row.skipped" type="info" size="small">Skipped</el-tag>
                <el-tag v-else type="success" size="small">Done</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="error" label="Error" show-overflow-tooltip />
          </el-table>
        </template>

        <div v-if="!previewResult && !applyResult" class="ci-empty">
          <p>Enter a path and click <b>Preview</b> to see which files will be compressed.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed } from 'vue'
import { previewCompress, applyCompress, type PreviewResult, type ApplyResult } from '../service/CompressImageService'
import { ElMessage } from 'element-plus'

const form = ref({ root_path: '', target_kb: 500, output_dir: '' })
const outputMode = ref<'overwrite' | 'suffix' | 'dir'>('suffix')

const previewLoading = ref(false)
const applyLoading = ref(false)
const previewResult = ref<PreviewResult | null>(null)
const applyResult = ref<ApplyResult | null>(null)

async function doPreview() {
  if (!form.value.root_path.trim()) { ElMessage.warning('Please enter a path'); return }
  previewLoading.value = true
  applyResult.value = null
  try {
    previewResult.value = await previewCompress(form.value.root_path, form.value.target_kb)
  } finally {
    previewLoading.value = false
  }
}

async function doApply() {
  if (!form.value.root_path.trim()) return
  applyLoading.value = true
  try {
    applyResult.value = await applyCompress({
      root_path: form.value.root_path,
      target_kb: form.value.target_kb,
      overwrite: outputMode.value === 'overwrite',
      output_dir: outputMode.value === 'dir' ? form.value.output_dir : '',
    })
    previewResult.value = null
    ElMessage.success(`Compressed ${applyResult.value.compressed} files, saved ${fmtKb(applyResult.value.total_saved_kb)}`)
  } finally {
    applyLoading.value = false
  }
}

function fmtKb(kb: number) {
  if (kb >= 1024) return (kb / 1024).toFixed(1) + ' MB'
  return kb.toFixed(1) + ' KB'
}
</script>

<style scoped>
.ci-root { min-height: 100vh; padding: 24px; box-sizing: border-box; }
.ci-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.ci-title { margin: 0; font-size: 22px; font-weight: 600; }
.ci-body { display: flex; gap: 24px; align-items: flex-start; }
.ci-params { width: 320px; flex-shrink: 0; }
.ci-results { flex: 1; min-width: 0; }
.ci-empty { display: flex; align-items: center; justify-content: center; padding: 60px; color: #909399; }
.panel-title { font-weight: 600; font-size: 15px; }
.ci-summary { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.sum-chip {
  padding: 6px 14px; border-radius: 20px; font-size: 13px;
  background: #f4f4f5; border: 1px solid #e9e9eb;
}
.sum-chip.orange { background: #fdf6ec; border-color: #fde5c0; color: #b7791f; }
.sum-chip.green { background: #f0fdf4; border-color: #bbf7d0; color: #16a34a; }
.sum-chip.red { background: #fff2f0; border-color: #ffd4d4; color: #e74c3c; }
.green { color: #16a34a; font-weight: 600; }
.red { color: #e74c3c; }
</style>
