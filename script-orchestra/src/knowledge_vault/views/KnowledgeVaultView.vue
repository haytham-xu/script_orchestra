<template>
  <div class="kv">
    <header class="kv-topbar">
      <h1>Knowledge Vault</h1>
      <div class="kv-auto">
        <span>Auto-build</span>
        <el-switch :model-value="settings.auto_build" @change="(v: any) => toggleAutoBuild(v)" />
        <el-button size="small" :loading="building" @click="rebuild">Rebuild network</el-button>
      </div>
    </header>

    <el-tabs v-model="activeTab" class="kv-tabs" @tab-change="activeTab === 'network' && loadNetwork()">
      <!-- Capture -->
      <el-tab-pane label="Capture" name="capture">
        <div class="kv-capture">
          <div class="kv-cap-head">
            <span class="kv-cap-title">Add a fragment</span>
            <el-button size="small" @click="openBatch">Batch import (AI)</el-button>
          </div>
          <el-input v-model="draft.content" type="textarea" :rows="2"
            placeholder="Paste a URL / command / snippet…" />
          <el-input v-model="draft.note" placeholder="Note — what is this?" style="margin-top:8px" />
          <div class="kv-cap-row">
            <el-select v-model="draft.label_ids" multiple collapse-tags placeholder="Labels (optional)"
              style="flex:1" size="default">
              <el-option v-for="l in labels" :key="l.id" :label="l.name" :value="l.id" />
            </el-select>
            <el-button type="primary" :loading="saving" @click="addFragment">Save</el-button>
          </div>

          <el-table :data="fragments" size="small" style="width:100%; margin-top:16px;">
            <el-table-column prop="content" label="Content" show-overflow-tooltip />
            <el-table-column prop="note" label="Note" show-overflow-tooltip />
            <el-table-column label="Labels" width="180">
              <template #default="{ row }">
                <el-tag v-for="lid in row.label_ids" :key="lid" size="small"
                  :color="labelMap[lid]?.color" style="margin-right:4px; color:#fff; border:none;">
                  {{ labelMap[lid]?.name }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="Added" width="110">
              <template #default="{ row }">
                <span class="kv-added">{{ fmtDate(row.created_at) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="Status" width="140">
              <template #default="{ row }">
                <el-tag size="small" :type="FRESH_TYPE[row.freshness]">
                  {{ FRESH_LABEL[row.freshness] || row.freshness }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="" width="150">
              <template #default="{ row }">
                <el-button size="small" @click="openEdit(row)">Edit</el-button>
                <el-button size="small" type="danger" @click="removeFragment(row)">Delete</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Search -->
      <el-tab-pane label="Search" name="search">
        <div class="kv-search">
          <div style="display:flex; gap:8px;">
            <el-input v-model="queryText" placeholder="Search by meaning…"
              @keyup.enter="runSearch" />
            <el-button type="primary" @click="runSearch">Search</el-button>
            <el-button :loading="aiLoading" @click="runAiQuery">AI deep answer</el-button>
          </div>
          <el-card v-if="aiAnswer" class="kv-ai" style="margin-top:12px;">
            <div style="white-space:pre-wrap">{{ aiAnswer }}</div>
          </el-card>
          <el-table :data="results" size="small" style="width:100%; margin-top:12px;">
            <el-table-column prop="content" label="Content" show-overflow-tooltip />
            <el-table-column prop="note" label="Note" show-overflow-tooltip />
            <el-table-column prop="score" label="Score" width="90" />
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Network -->
      <el-tab-pane label="Network" name="network">
        <div class="kv-network">
          <div class="kv-net-head">
            <p v-if="buildStatus" class="kv-hint">
              Last build: {{ buildStatus.nodes }} nodes, {{ buildStatus.edges }} edges
            </p>
            <div class="kv-legend">
              <span><i class="dot" style="background:#0a84ff"></i>url</span>
              <span><i class="dot" style="background:#30d158"></i>command</span>
              <span><i class="dot" style="background:#ff9f0a"></i>script</span>
              <span><i class="dot" style="background:#bf5af2"></i>note</span>
              <span class="sep">|</span>
              <span><i class="ring" style="border-color:#34c759"></i>fresh</span>
              <span><i class="ring" style="border-color:#ff9f0a"></i>aging</span>
              <span><i class="ring" style="border-color:#ff3b30"></i>stale</span>
            </div>
          </div>

          <el-empty v-if="!nodes.length"
            description="No knowledge network yet — capture some fragments, then click “Rebuild network”."
            :image-size="80" />

          <div v-show="nodes.length" class="kv-graph-wrap">
            <div ref="graphEl" class="kv-graph"></div>
            <el-card v-if="selected" class="kv-detail" shadow="never">
              <h4>{{ selected.title }}</h4>
              <el-tag size="small">{{ selected.kind }}</el-tag>
              <el-tag size="small" style="margin-left:6px"
                :type="selected.freshness === 'stale' ? 'danger' : selected.freshness === 'aging' ? 'warning' : 'success'">
                {{ selected.freshness }}
              </el-tag>
              <p class="kv-detail-summary">{{ selected.summary || '—' }}</p>
              <p class="kv-detail-meta">{{ selected.fragment_ids?.length || 0 }} source fragment(s)</p>
            </el-card>
          </div>
        </div>
      </el-tab-pane>

      <!-- Settings: label management -->
      <el-tab-pane label="Settings" name="settings">
        <div class="kv-settings">
          <h3>Labels</h3>
          <p class="kv-hint">User-managed tags. A fragment can carry several. Deleting a label removes it from all fragments.</p>
          <div class="kv-label-add">
            <el-color-picker v-model="newLabel.color" />
            <el-input v-model="newLabel.name" placeholder="New label name" style="max-width:240px"
              @keyup.enter="addLabel" />
            <el-button type="primary" @click="addLabel">Add label</el-button>
          </div>
          <div class="kv-label-list">
            <el-tag v-for="l in labels" :key="l.id" closable :color="l.color"
              style="color:#fff; border:none; margin:4px;" @close="removeLabel(l)">
              {{ l.name }}
            </el-tag>
            <el-empty v-if="!labels.length" description="No labels yet" :image-size="50" />
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- Edit fragment dialog -->
    <el-dialog v-model="editDialog" title="Edit fragment" width="520px">
      <el-input v-model="editing.content" type="textarea" :rows="3" placeholder="Content" />
      <el-input v-model="editing.note" placeholder="Note" style="margin-top:8px" />
      <el-select v-model="editing.label_ids" multiple collapse-tags placeholder="Labels"
        style="width:100%; margin-top:8px">
        <el-option v-for="l in labels" :key="l.id" :label="l.name" :value="l.id" />
      </el-select>
      <template #footer>
        <el-button @click="editDialog = false">Cancel</el-button>
        <el-button type="primary" @click="saveEdit">Save</el-button>
      </template>
    </el-dialog>

    <!-- Batch import dialog -->
    <el-dialog v-model="batchDialog" title="Batch import (AI splits into fragments)" width="720px">
      <el-input v-model="batchText" type="textarea" :rows="6"
        placeholder="Paste a messy pile of knowledge — URLs, commands, notes, anything. AI will split it into individual fragments." />
      <div class="kv-cap-row">
        <el-select v-model="batchLabelIds" multiple collapse-tags placeholder="Apply labels to all (optional)"
          style="flex:1">
          <el-option v-for="l in labels" :key="l.id" :label="l.name" :value="l.id" />
        </el-select>
        <el-button type="primary" :loading="batchAnalyzing" @click="runAnalyze">Analyze</el-button>
      </div>

      <div v-if="analyzed.length" class="kv-analyzed">
        <p class="kv-hint">{{ analyzed.filter(a => a._keep).length }} of {{ analyzed.length }} selected. Uncheck any you don't want.</p>
        <el-table :data="analyzed" size="small" max-height="320">
          <el-table-column width="46">
            <template #default="{ row }"><el-checkbox v-model="row._keep" /></template>
          </el-table-column>
          <el-table-column label="Content">
            <template #default="{ row }"><el-input v-model="row.content" size="small" /></template>
          </el-table-column>
          <el-table-column label="Note" width="200">
            <template #default="{ row }"><el-input v-model="row.note" size="small" /></template>
          </el-table-column>
          <el-table-column prop="kind" label="Kind" width="90" />
        </el-table>
      </div>

      <template #footer>
        <el-button @click="batchDialog = false">Cancel</el-button>
        <el-button type="primary" :disabled="!analyzed.length" :loading="batchCommitting"
          @click="commitBatch">Import selected</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts" src="@/knowledge_vault/views/KnowledgeVaultView.ts"></script>

<style scoped>
.kv { min-height: 100vh; background: #f5f5f7; color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; }
.kv-topbar { display: flex; align-items: center; justify-content: space-between;
  padding: 16px 24px; border-bottom: 1px solid rgba(0,0,0,0.06); background: #fff; }
.kv-topbar h1 { margin: 0; font-size: 20px; font-weight: 600; }
.kv-auto { display: flex; align-items: center; gap: 10px; font-size: 13px; color: #86868b; }
.kv-tabs { padding: 0 24px; }
.kv-capture, .kv-search { max-width: 900px; margin: 16px auto; }
.kv-settings { max-width: 900px; margin: 16px auto; }
.kv-network { max-width: 1200px; margin: 16px auto; }
.kv-hint { font-size: 12px; color: #86868b; margin: 0; }

.kv-cap-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.kv-cap-title { font-size: 14px; font-weight: 600; }
.kv-cap-row { display: flex; gap: 8px; align-items: center; margin-top: 8px; }

.kv-label-add { display: flex; gap: 8px; align-items: center; margin: 12px 0; }
.kv-label-list { display: flex; flex-wrap: wrap; align-items: center; }
.kv-analyzed { margin-top: 12px; }
.kv-added { font-size: 12px; color: #86868b; }

.kv-net-head { display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.kv-legend { display: flex; align-items: center; gap: 12px; font-size: 12px; color: #86868b; }
.kv-legend .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  margin-right: 4px; vertical-align: middle; }
.kv-legend .ring { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  border: 2px solid; margin-right: 4px; vertical-align: middle; }
.kv-legend .sep { color: #d2d2d7; }

.kv-graph-wrap { position: relative; }
.kv-graph { width: 100%; height: 560px; background: #fff; border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.06); }
.kv-detail { position: absolute; top: 12px; right: 12px; width: 260px;
  background: rgba(255,255,255,0.96); backdrop-filter: blur(6px); }
.kv-detail h4 { margin: 0 0 8px; font-size: 15px; }
.kv-detail-summary { font-size: 13px; color: #3a3a3c; margin: 10px 0 4px; white-space: pre-wrap; }
.kv-detail-meta { font-size: 12px; color: #86868b; margin: 0; }
</style>
