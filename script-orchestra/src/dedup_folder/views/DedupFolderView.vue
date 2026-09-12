<template>
  <div class="df-root">
    <div class="df-header">
      <el-button type="default" size="small" @click="$router.back()">← Back</el-button>
      <h2 class="df-title">Dedup Folder</h2>
    </div>

    <el-tabs v-model="activeTab" class="df-tabs">

      <!-- ===== Tab 1: Cross-Dir ===== -->
      <el-tab-pane label="Cross-Dir Dedup" name="cross">
        <div class="df-body">
          <el-card class="df-params" shadow="never">
            <template #header><span class="panel-title">Cross-Dir Dedup</span></template>
            <el-form label-position="top" size="small">
              <el-form-item label="Source path (keep these)">
                <el-input v-model="cross.source_path" placeholder="/path/source" clearable />
              </el-form-item>
              <el-form-item label="Duplicate path (scan here)">
                <el-input v-model="cross.duplicate_path" placeholder="/path/duplicates" clearable />
              </el-form-item>
              <el-form-item label="Trash path (move duplicates here)">
                <el-input v-model="cross.trash_path" placeholder="/path/trash" clearable />
              </el-form-item>
              <div style="display:flex;gap:8px;margin-top:8px">
                <el-button type="default" @click="crossPreview" :loading="cross.loading" style="flex:1">Preview</el-button>
                <el-button type="danger" @click="crossApply" :loading="cross.applyLoading" :disabled="!cross.preview" style="flex:1">Apply</el-button>
              </div>
            </el-form>
          </el-card>
          <div class="df-results">
            <template v-if="cross.preview && !cross.result">
              <div class="df-summary">
                <div class="sum-chip">Common folders: <b>{{ cross.preview.total }}</b></div>
                <div class="sum-chip orange">Identical (will move): <b>{{ cross.preview.eligible }}</b></div>
              </div>
              <el-table :data="cross.preview.items" size="small" height="500" stripe>
                <el-table-column prop="name" label="Folder" show-overflow-tooltip />
                <el-table-column label="Status" width="150">
                  <template #default="{ row }">
                    <el-tag :type="row.identical ? 'danger' : 'success'" size="small">
                      {{ row.identical ? 'Identical — will move' : 'Different — keep' }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </template>
            <template v-if="cross.result">
              <div class="df-summary">
                <div class="sum-chip green">Moved: <b>{{ cross.result.moved }}</b></div>
                <div class="sum-chip" :class="{ red: cross.result.errors > 0 }">Errors: <b>{{ cross.result.errors }}</b></div>
              </div>
              <el-table :data="cross.result.items" size="small" height="500" stripe>
                <el-table-column prop="name" label="Folder" show-overflow-tooltip />
                <el-table-column prop="dest" label="Moved to" show-overflow-tooltip />
                <el-table-column prop="error" label="Error" show-overflow-tooltip />
              </el-table>
            </template>
            <div v-if="!cross.preview && !cross.result" class="df-empty">Enter paths and click Preview.</div>
          </div>
        </div>
      </el-tab-pane>

      <!-- ===== Tab 2: Name Pattern ===== -->
      <el-tab-pane label="Name Pattern Dedup" name="name">
        <div class="df-body">
          <el-card class="df-params" shadow="never">
            <template #header><span class="panel-title">Name Pattern Dedup</span></template>
            <el-form label-position="top" size="small">
              <el-form-item label="Source path">
                <el-input v-model="name_.source_path" placeholder="/path/source" clearable />
              </el-form-item>
              <el-form-item label="Trash path">
                <el-input v-model="name_.trash_path" placeholder="/path/trash" clearable />
              </el-form-item>
              <div style="display:flex;gap:8px;margin-top:8px">
                <el-button type="default" @click="namePreview" :loading="name_.loading" style="flex:1">Preview</el-button>
                <el-button type="danger" @click="nameApply" :loading="name_.applyLoading" :disabled="!name_.preview" style="flex:1">Apply</el-button>
              </div>
            </el-form>
            <div style="margin-top:12px;font-size:12px;color:#909399;line-height:1.6">
              Detects copies named: <code>XXX 2</code>, <code>XXX_2</code>, <code>XXX copy</code>, <code>XXX (2)</code> etc.
            </div>
          </el-card>
          <div class="df-results">
            <template v-if="name_.preview && !name_.result">
              <div class="df-summary">
                <div class="sum-chip orange">Suspected copies: <b>{{ name_.preview.total }}</b></div>
              </div>
              <el-table :data="name_.preview.items" size="small" height="500" stripe>
                <el-table-column prop="name" label="Copy folder" show-overflow-tooltip />
                <el-table-column prop="original" label="Original" show-overflow-tooltip />
              </el-table>
            </template>
            <template v-if="name_.result">
              <div class="df-summary">
                <div class="sum-chip green">Moved: <b>{{ name_.result.moved }}</b></div>
                <div class="sum-chip" :class="{ red: name_.result.errors > 0 }">Errors: <b>{{ name_.result.errors }}</b></div>
              </div>
              <el-table :data="name_.result.items" size="small" height="500" stripe>
                <el-table-column prop="name" label="Folder" show-overflow-tooltip />
                <el-table-column prop="original" label="Original" show-overflow-tooltip />
                <el-table-column prop="dest" label="Moved to" show-overflow-tooltip />
                <el-table-column prop="error" label="Error" show-overflow-tooltip />
              </el-table>
            </template>
            <div v-if="!name_.preview && !name_.result" class="df-empty">Enter paths and click Preview.</div>
          </div>
        </div>
      </el-tab-pane>

      <!-- ===== Tab 3: macOS File Dedup ===== -->
      <el-tab-pane label="macOS File Dedup" name="macos">
        <div class="df-body">
          <el-card class="df-params" shadow="never">
            <template #header><span class="panel-title">macOS File Dedup</span></template>
            <el-form label-position="top" size="small">
              <el-form-item label="Source path">
                <el-input v-model="macos.source_path" placeholder="/path/source" clearable />
              </el-form-item>
              <el-form-item label="Action">
                <el-radio-group v-model="macos.deleteDirectly">
                  <el-radio :value="false">Move to trash folder</el-radio>
                  <el-radio :value="true">Delete directly</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item v-if="!macos.deleteDirectly" label="Trash path">
                <el-input v-model="macos.trash_path" placeholder="/path/trash" clearable />
              </el-form-item>
              <div style="display:flex;gap:8px;margin-top:8px">
                <el-button type="default" @click="macosPreview" :loading="macos.loading" style="flex:1">Preview</el-button>
                <el-button type="danger" @click="macosApply" :loading="macos.applyLoading" :disabled="!macos.preview" style="flex:1">Apply</el-button>
              </div>
            </el-form>
            <div style="margin-top:12px;font-size:12px;color:#909399;line-height:1.6">
              Detects macOS copies: <code>file (1).jpg</code>, <code>file copy.jpg</code>, <code>file 2.jpg</code> etc.
            </div>
          </el-card>
          <div class="df-results">
            <template v-if="macos.preview && !macos.result">
              <div class="df-summary">
                <div class="sum-chip orange">Duplicate files: <b>{{ macos.preview.total }}</b></div>
              </div>
              <el-table :data="macos.preview.items" size="small" height="500" stripe>
                <el-table-column prop="name" label="Duplicate file" show-overflow-tooltip />
                <el-table-column prop="original" label="Original" show-overflow-tooltip />
                <el-table-column prop="size_kb" label="Size (KB)" width="100" />
                <el-table-column label="Same size" width="100">
                  <template #default="{ row }">
                    <el-tag :type="row.same_size ? 'warning' : 'info'" size="small">{{ row.same_size ? 'Yes' : 'No' }}</el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </template>
            <template v-if="macos.result">
              <div class="df-summary">
                <div class="sum-chip green">Removed: <b>{{ macos.result.removed }}</b></div>
                <div class="sum-chip" :class="{ red: macos.result.errors > 0 }">Errors: <b>{{ macos.result.errors }}</b></div>
              </div>
              <el-table :data="macos.result.items" size="small" height="500" stripe>
                <el-table-column prop="name" label="File" show-overflow-tooltip />
                <el-table-column prop="action" label="Action" width="80" />
                <el-table-column prop="dest" label="Dest" show-overflow-tooltip />
                <el-table-column prop="error" label="Error" show-overflow-tooltip />
              </el-table>
            </template>
            <div v-if="!macos.preview && !macos.result" class="df-empty">Enter a path and click Preview.</div>
          </div>
        </div>
      </el-tab-pane>

    </el-tabs>
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  crossDirPreview, crossDirApply,
  namePatternPreview, namePatternApply,
  macosFilePreview, macosFileApply,
} from '../service/DedupFolderService'

const activeTab = ref('cross')

const cross = ref({ source_path: '', duplicate_path: '', trash_path: '', loading: false, applyLoading: false, preview: null as any, result: null as any })
const name_ = ref({ source_path: '', trash_path: '', loading: false, applyLoading: false, preview: null as any, result: null as any })
const macos = ref({ source_path: '', trash_path: '', deleteDirectly: false, loading: false, applyLoading: false, preview: null as any, result: null as any })

async function crossPreview() {
  if (!cross.value.source_path || !cross.value.duplicate_path) { ElMessage.warning('Enter source and duplicate paths'); return }
  cross.value.loading = true; cross.value.result = null
  try { cross.value.preview = await crossDirPreview(cross.value.source_path, cross.value.duplicate_path) }
  finally { cross.value.loading = false }
}
async function crossApply() {
  if (!cross.value.trash_path) { ElMessage.warning('Enter trash path'); return }
  cross.value.applyLoading = true
  try {
    cross.value.result = await crossDirApply(cross.value.source_path, cross.value.duplicate_path, cross.value.trash_path)
    cross.value.preview = null
    ElMessage.success(`Moved ${cross.value.result.moved} folders`)
  } finally { cross.value.applyLoading = false }
}

async function namePreview() {
  if (!name_.value.source_path) { ElMessage.warning('Enter source path'); return }
  name_.value.loading = true; name_.value.result = null
  try { name_.value.preview = await namePatternPreview(name_.value.source_path) }
  finally { name_.value.loading = false }
}
async function nameApply() {
  if (!name_.value.trash_path) { ElMessage.warning('Enter trash path'); return }
  name_.value.applyLoading = true
  try {
    name_.value.result = await namePatternApply(name_.value.source_path, name_.value.trash_path)
    name_.value.preview = null
    ElMessage.success(`Moved ${name_.value.result.moved} folders`)
  } finally { name_.value.applyLoading = false }
}

async function macosPreview() {
  if (!macos.value.source_path) { ElMessage.warning('Enter source path'); return }
  macos.value.loading = true; macos.value.result = null
  try { macos.value.preview = await macosFilePreview(macos.value.source_path) }
  finally { macos.value.loading = false }
}
async function macosApply() {
  if (!macos.value.deleteDirectly && !macos.value.trash_path) { ElMessage.warning('Enter trash path or choose delete directly'); return }
  macos.value.applyLoading = true
  try {
    macos.value.result = await macosFileApply(macos.value.source_path, macos.value.trash_path, macos.value.deleteDirectly)
    macos.value.preview = null
    ElMessage.success(`Removed ${macos.value.result.removed} files`)
  } finally { macos.value.applyLoading = false }
}
</script>

<style scoped>
.df-root { min-height: 100vh; padding: 24px; box-sizing: border-box; }
.df-header { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.df-title { margin: 0; font-size: 22px; font-weight: 600; }
.df-body { display: flex; gap: 24px; align-items: flex-start; margin-top: 16px; }
.df-params { width: 320px; flex-shrink: 0; }
.df-results { flex: 1; min-width: 0; }
.df-empty { display: flex; align-items: center; justify-content: center; padding: 60px; color: #909399; }
.panel-title { font-weight: 600; font-size: 15px; }
.df-summary { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.sum-chip { padding: 6px 14px; border-radius: 20px; font-size: 13px; background: #f4f4f5; border: 1px solid #e9e9eb; }
.sum-chip.orange { background: #fdf6ec; border-color: #fde5c0; color: #b7791f; }
.sum-chip.green { background: #f0fdf4; border-color: #bbf7d0; color: #16a34a; }
.sum-chip.red { background: #fff2f0; border-color: #ffd4d4; color: #e74c3c; }
</style>
