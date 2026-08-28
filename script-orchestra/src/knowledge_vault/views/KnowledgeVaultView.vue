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
          <el-input v-model="draft.content" type="textarea" :rows="2"
            placeholder="Paste a URL / command / snippet…" />
          <el-input v-model="draft.note" placeholder="Note — what is this?" style="margin-top:8px" />
          <div style="margin-top:8px; display:flex; gap:8px; justify-content:flex-end;">
            <el-button type="primary" :loading="saving" @click="addFragment">Save</el-button>
          </div>

          <el-table :data="fragments" size="small" style="width:100%; margin-top:16px;">
            <el-table-column prop="content" label="Content" show-overflow-tooltip />
            <el-table-column prop="note" label="Note" show-overflow-tooltip />
            <el-table-column label="" width="90">
              <template #default="{ row }">
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
          <p v-if="buildStatus" class="kv-hint">
            Last build: {{ buildStatus.nodes }} nodes, {{ buildStatus.edges }} edges
          </p>
          <h3>Nodes</h3>
          <el-table :data="nodes" size="small" style="width:100%;">
            <el-table-column prop="title" label="Title" show-overflow-tooltip />
            <el-table-column prop="kind" label="Kind" width="100" />
            <el-table-column prop="freshness" label="Freshness" width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="row.freshness === 'stale' ? 'danger' : row.freshness === 'aging' ? 'warning' : 'success'">
                  {{ row.freshness }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <h3 style="margin-top:16px;">Needs review (stale)</h3>
          <el-empty v-if="!stale.length" description="Nothing stale" :image-size="60" />
          <el-table v-else :data="stale" size="small" style="width:100%;">
            <el-table-column prop="title" label="Title" show-overflow-tooltip />
            <el-table-column prop="kind" label="Kind" width="100" />
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>
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
.kv-capture, .kv-search, .kv-network { max-width: 900px; margin: 16px auto; }
.kv-hint { font-size: 12px; color: #86868b; }
</style>
