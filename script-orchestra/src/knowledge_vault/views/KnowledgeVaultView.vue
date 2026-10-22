<template>
  <div class="kv">
    <!-- top bar -->
    <header class="kv-topbar">
      <el-button @click="goBack" circle size="small"><el-icon><ArrowLeft /></el-icon></el-button>
      <h1>Knowledge Vault</h1>
      <div style="flex:1" />
      <el-button type="primary" @click="goCapture">Capture</el-button>
    </header>

    <!-- ===== HERO (before first search) ===== -->
    <div v-if="!searched" class="kv-hero">
      <div class="kv-hero-logo">Knowledge Vault</div>
      <div class="kv-hero-bar">
        <el-input
          v-model="queryText"
          placeholder="Search by meaning…"
          size="large"
          class="kv-hero-input"
          @keyup.enter="runSearch"
        />
        <el-button type="primary" size="large" :loading="searching" @click="runSearch">
          {{ searching ? 'Searching…' : 'Search' }}
        </el-button>
      </div>
    </div>

    <!-- ===== RESULTS (after first search) ===== -->
    <div v-else class="kv-results-page">
      <!-- compact search bar -->
      <div class="kv-compact-bar">
        <el-input
          v-model="queryText"
          placeholder="Search by meaning…"
          class="kv-compact-input"
          @keyup.enter="runSearch"
        />
        <el-button type="primary" :loading="searching" @click="runSearch">
          {{ searching ? 'Searching…' : 'Search' }}
        </el-button>
      </div>

      <!-- split: results list + detail panel -->
      <div class="kv-split">
        <!-- left: result list -->
        <div class="kv-split-left">
          <div class="kv-result-count" v-if="!searching">
            {{ results.length ? `${results.length} result${results.length !== 1 ? 's' : ''}` : 'No results found' }}
          </div>
          <div v-for="row in results" :key="row.id"
            class="kv-result-row"
            :class="{ 'kv-result-row--active': searchDetail?.id === row.id }"
            @click="searchDetail = row">
            <div class="kv-result-title">{{ row.header || fragmentSummary(row) }}</div>
            <div v-if="row.note" class="kv-result-note">{{ row.note }}</div>
            <div class="kv-result-meta">
              <span v-if="row.score != null" class="kv-score">{{ Number(row.score).toFixed(2) }}</span>
              <span class="kv-date">{{ fmtDate(row.created_at) }}</span>
              <el-tag v-for="lid in row.label_ids" :key="lid" size="small"
                :color="labelMap[lid]?.color" class="kv-lbl">{{ labelMap[lid]?.name }}</el-tag>
            </div>
          </div>
        </div>

        <!-- right: detail panel -->
        <aside v-if="searchDetail" class="kv-split-detail">
          <div class="kv-det-head">
            <div class="kv-det-title-wrap">
              <div class="kv-det-title">{{ searchDetail.header || fragmentSummary(searchDetail) }}</div>
            </div>
            <div class="kv-det-acts">
              <el-button text size="small" @click="$router.push({ name: 'knowledge-vault', query: { open: String(searchDetail.id) } })">Edit</el-button>
              <el-button text size="small" @click="searchDetail = null">✕</el-button>
            </div>
          </div>
          <div class="kv-det-body">
            <div v-if="searchDetail.note" class="kv-det-note">{{ searchDetail.note }}</div>
            <div class="kv-det-meta">
              <el-tag size="small" effect="light"
                :type="searchDetail.freshness === 'fresh' ? 'success' : searchDetail.freshness === 'aging' ? 'warning' : 'danger'">
                {{ searchDetail.freshness === 'fresh' ? 'Fresh' : searchDetail.freshness === 'aging' ? 'Aging' : 'Outdated' }}
              </el-tag>
              <span class="kv-date">{{ fmtDate(searchDetail.created_at) }}</span>
              <el-tag v-for="lid in searchDetail.label_ids" :key="lid" size="small"
                :color="labelMap[lid]?.color" class="kv-lbl">{{ labelMap[lid]?.name }}</el-tag>
            </div>
            <div class="kv-blocks">
              <div v-for="(blk, i) in searchDetail.blocks" :key="i" class="kv-block">
                <div class="kv-blk-bar" :class="blk.type === 'code' ? 'kv-blk-bar--code' : blk.type === 'url' ? 'kv-blk-bar--url' : blk.type === 'long' ? 'kv-blk-bar--long' : blk.type === 'table' ? 'kv-blk-bar--table' : blk.type === 'template' ? 'kv-blk-bar--template' : blk.type === 'execute' ? 'kv-blk-bar--execute' : 'kv-blk-bar--text'"
                  @click="blk.type === 'long' ? toggleLong(blk) : undefined" :style="blk.type === 'long' ? 'cursor:pointer' : ''">
                  <span class="kv-blk-subtitle" v-if="blk.subtitle">{{ blk.subtitle }}</span>
                  <span v-else-if="blk.type === 'long'" class="kv-blk-subtitle kv-blk-subtitle--long">Long text — click to expand</span>
                  <span v-else style="flex:1" />
                  <el-button
                    v-if="blk.type === 'execute'"
                    text
                    size="small"
                    :loading="isExecuteRunning(templateKey('search', searchDetail?.id, i))"
                    :disabled="!templateAllArgsFilled(templateKey('search', searchDetail?.id, i), blk)"
                    @click.stop="runExecuteBlock(blk, templateKey('search', searchDetail?.id, i), $event)"
                  >Execute</el-button>
                  <el-button
                    text
                    size="small"
                    :disabled="blk.type === 'execute'
                      ? (!templateAllArgsFilled(templateKey('search', searchDetail?.id, i), blk) || !hasExecuteResult(templateKey('search', searchDetail?.id, i)))
                      : (blk.type === 'template' && !templateAllArgsFilled(templateKey('search', searchDetail?.id, i), blk))"
                    @click.stop="copyBlockFilled(blk, templateKey('search', searchDetail?.id, i), $event)"
                  >Copy</el-button>
                  <span v-if="blk.type === 'long'" class="kv-long-chevron" :class="{ expanded: expandedLongs.has(blk) }">›</span>
                </div>
                <div v-if="blk.type === 'text'" class="kv-blk-text-body kv-md" v-html="renderMd(blk.body)" />
                <pre v-else-if="blk.type === 'code'" class="kv-pre">{{ blk.body }}</pre>
                <div v-else-if="blk.type === 'url'" class="kv-url-body">
                  <a :href="blk.body" target="_blank" rel="noopener" class="kv-url-link">{{ blk.body }}</a>
                </div>
                <div v-else-if="blk.type === 'template' || blk.type === 'execute'" class="kv-template-body">
                  <div class="kv-template-args kv-template-args--compact">
                    <div v-for="(arg, argIdx) in getTemplateArgs(templateKey('search', searchDetail?.id, i), blk)" :key="argIdx" class="kv-template-arg-row">
                      <span class="kv-template-arg-label">{{ getTemplateArgNames(blk)[argIdx] }}</span>
                      <el-input
                        :model-value="arg"
                        size="small"
                        :placeholder="`value for ${getTemplateArgNames(blk)[argIdx]}`"
                        @update:model-value="(v) => setTemplateArg(templateKey('search', searchDetail?.id, i), blk, argIdx, v)"
                      />
                    </div>
                  </div>
                  <pre class="kv-pre kv-pre-template">{{ blk.body }}</pre>
                  <div
                    v-if="blk.type === 'template' && hasTemplateGenerated(templateKey('search', searchDetail?.id, i))"
                    class="kv-template-result kv-template-result--compact"
                  >
                    <div class="kv-template-result-head">
                      <div class="kv-template-result-label">Generated</div>
                      <el-button text size="small" @click="toggleResultViewMode(templateKey('search', searchDetail?.id, i))">
                        {{ getResultViewMode(templateKey('search', searchDetail?.id, i)) === 'tail' ? 'Show full' : 'Show tail' }}
                      </el-button>
                    </div>
                    <pre class="kv-pre kv-pre-template-result">{{ getTemplateGeneratedDisplay(templateKey('search', searchDetail?.id, i)) }}</pre>
                  </div>
                  <div
                    v-if="blk.type === 'execute' && hasExecuteResult(templateKey('search', searchDetail?.id, i))"
                    class="kv-template-result kv-template-result--compact"
                  >
                    <div class="kv-template-result-head">
                      <div class="kv-template-result-label">Execution Result</div>
                      <el-button text size="small" @click="toggleResultViewMode(templateKey('search', searchDetail?.id, i))">
                        {{ getResultViewMode(templateKey('search', searchDetail?.id, i)) === 'tail' ? 'Show full' : 'Show tail' }}
                      </el-button>
                    </div>
                    <pre class="kv-pre kv-pre-template-result">{{ getExecuteResultDisplay(templateKey('search', searchDetail?.id, i)) }}</pre>
                  </div>
                </div>
                <div v-else-if="blk.type === 'table'" class="kv-table-view-wrap">
                  <el-table
                    :data="tableRowsForView(blk.body)"
                    size="small"
                    border
                    class="kv-table-view"
                    @header-dragend="(newWidth, _oldWidth, column) => onTableHeaderDragEnd(getTablePersistKey('search', searchDetail?.id || 0, i, tableForView(blk.body).headers.length), newWidth, column?.property)"
                  >
                    <el-table-column
                      v-for="(header, colIdx) in tableForView(blk.body).headers"
                      :key="colIdx"
                      :prop="tableColProp(colIdx)"
                      :label="header || `Column ${colIdx + 1}`"
                      :min-width="120"
                      :width="getTableColWidth(getTablePersistKey('search', searchDetail?.id || 0, i, tableForView(blk.body).headers.length), colIdx)"
                    >
                      <template #default="{ row }">
                        <span class="kv-table-cell">{{ row[tableColProp(colIdx)] }}</span>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
                <div v-else-if="blk.type === 'long' && expandedLongs.has(blk)" class="kv-blk-text-body kv-md" v-html="renderMd(blk.body)" />
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  </div>
</template>

<script lang="ts" src="@/knowledge_vault/views/KnowledgeVaultView.ts"></script>

<style scoped>
.kv {
  height: 100vh; display: flex; flex-direction: column; overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  background: #f5f5f7; color: #1d1d1f;
}

/* topbar */
.kv-topbar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 20px; background: #fff;
  border-bottom: 1px solid rgba(0,0,0,0.07); flex-shrink: 0;
}
.kv-topbar h1 { margin: 0; font-size: 17px; font-weight: 600; white-space: nowrap; }

/* ===== HERO ===== */
.kv-hero {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  justify-content: flex-start; padding-top: 22vh; gap: 24px; padding-left: 20px; padding-right: 20px;
}
.kv-hero-logo {
  font-size: 36px; font-weight: 700; color: #1d1d1f; letter-spacing: -1px;
}
.kv-hero-bar {
  display: flex; gap: 10px; width: 100%; max-width: 580px;
}
.kv-hero-input { flex: 1; }
:deep(.kv-hero-input .el-input__wrapper) { border-radius: 24px; }

/* ===== RESULTS PAGE ===== */
.kv-results-page {
  flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0;
}
.kv-compact-bar {
  display: flex; gap: 10px; align-items: center;
  padding: 10px 20px; background: #fff;
  border-bottom: 1px solid rgba(0,0,0,0.07); flex-shrink: 0;
}
.kv-compact-input { flex: 1; max-width: 560px; }

/* split layout */
.kv-split {
  flex: 1; display: flex; overflow: hidden; min-height: 0;
}
.kv-split-left {
  flex: 1; min-width: 0; overflow-y: auto; padding: 16px 20px;
}
.kv-result-count { font-size: 13px; color: #86868b; margin-bottom: 12px; }

.kv-result-row {
  padding: 12px 16px; margin-bottom: 6px;
  background: #fff; border: 1px solid rgba(0,0,0,0.07); border-radius: 10px;
  cursor: pointer; transition: border-color .1s, box-shadow .1s;
}
.kv-result-row:hover { border-color: rgba(10,132,255,0.3); box-shadow: 0 1px 6px rgba(10,132,255,0.08); }
.kv-result-row--active { border-color: rgba(10,132,255,0.5) !important; box-shadow: 0 1px 8px rgba(10,132,255,0.15) !important; background: #f0f7ff; }
.kv-result-title { font-size: 14px; font-weight: 600; color: #1d1d1f; margin-bottom: 3px; }
.kv-result-note { font-size: 12px; color: #555; margin-bottom: 5px; line-height: 1.4; }
.kv-result-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }

/* detail panel */
.kv-split-detail {
  width: 420px; flex-shrink: 0;
  background: #fff; border-left: 1px solid rgba(0,0,0,0.07);
  display: flex; flex-direction: column; overflow: hidden;
}
.kv-det-head {
  display: flex; align-items: flex-start; gap: 6px;
  padding: 12px 14px; border-bottom: 1px solid rgba(0,0,0,0.06); flex-shrink: 0;
}
.kv-det-title-wrap { flex: 1; min-width: 0; }
.kv-det-title { font-size: 13px; font-weight: 600; word-break: break-word; line-height: 1.4; }
.kv-det-acts { display: flex; gap: 2px; flex-shrink: 0; }
.kv-det-body { flex: 1; overflow-y: auto; padding: 12px 14px; }
.kv-det-note { font-size: 13px; color: #3a3a3c; margin-bottom: 8px; line-height: 1.5; }
.kv-det-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; margin-bottom: 14px; }

/* blocks */
.kv-blocks { display: flex; flex-direction: column; gap: 8px; }
.kv-block { border-radius: 7px; overflow: hidden; border: 1px solid rgba(0,0,0,0.07); }
.kv-blk-bar {
  display: flex; align-items: center; justify-content: space-between; padding: 4px 10px;
}
.kv-blk-bar--text { background: #f5f5f7; }
.kv-blk-bar--code { background: #2d2d2d; }
.kv-blk-bar--url { background: #f0f7ff; }
.kv-blk-bar--long { background: #f5f0ff; }
.kv-blk-bar--table { background: #ecfdf5; }
.kv-blk-bar--template { background: #fff6e8; }
.kv-blk-bar--execute { background: #eef7ff; }
.kv-block:has(.kv-blk-bar--code) { background: #1e1e1e; }
.kv-blk-subtitle {
  flex: 1; font-size: 12px; color: #555; font-style: italic;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.kv-blk-subtitle--long { color: #7c4dbd; }
.kv-blk-bar--code .kv-blk-subtitle { color: #bbb; }
.kv-long-chevron {
  font-size: 16px; color: #7c4dbd; font-style: normal; margin-left: 4px;
  display: inline-block; transform: rotate(0deg); transition: transform .2s;
}
.kv-long-chevron.expanded { transform: rotate(90deg); }
.kv-blk-text-body {
  padding: 8px 12px; font-size: 13px; color: #1d1d1f;
  white-space: pre-wrap; word-break: break-word; line-height: 1.6;
}
.kv-md { white-space: normal; }
.kv-md :deep(p) { margin: 0 0 6px; }
.kv-md :deep(p:last-child) { margin-bottom: 0; }
.kv-md :deep(ul), .kv-md :deep(ol) { margin: 4px 0 6px; padding-left: 20px; }
.kv-md :deep(li) { margin: 2px 0; }
.kv-md :deep(h1), .kv-md :deep(h2), .kv-md :deep(h3) { margin: 8px 0 4px; font-size: 14px; font-weight: 600; }
.kv-md :deep(code) { background: #f0f2f5; border-radius: 3px; padding: 1px 4px; font-size: 12px; font-family: ui-monospace, monospace; }
.kv-md :deep(pre) { background: #1e1e1e; color: #d4d4d4; border-radius: 6px; padding: 10px 12px; overflow-x: auto; margin: 6px 0; }
.kv-md :deep(pre code) { background: none; padding: 0; color: inherit; }
.kv-md :deep(blockquote) { border-left: 3px solid #d0d0d0; margin: 6px 0; padding: 2px 10px; color: #555; }
.kv-md :deep(a) { color: #0a84ff; text-decoration: none; }
.kv-md :deep(a:hover) { text-decoration: underline; }
.kv-md :deep(hr) { border: none; border-top: 1px solid #e0e0e0; margin: 8px 0; }
.kv-md :deep(table) { border-collapse: collapse; font-size: 12px; }
.kv-md :deep(th), .kv-md :deep(td) { border: 1px solid #ddd; padding: 4px 8px; }
.kv-pre {
  margin: 0; padding: 10px 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px; color: #d4d4d4; overflow-x: auto; white-space: pre;
}
.kv-url-body { padding: 6px 12px 10px; }
.kv-url-link { font-size: 12px; color: #0a84ff; word-break: break-all; text-decoration: none; }
.kv-url-link:hover { text-decoration: underline; }
.kv-template-body { padding: 8px 10px; background: #fff; }
.kv-pre-template { background: #2b2112; margin-bottom: 8px; }
.kv-template-args { display: flex; flex-direction: column; gap: 6px; }
.kv-template-arg-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 2px 6px;
  border-radius: 6px;
  background: #fffaf0;
  border: 1px solid rgba(122, 90, 30, 0.15);
}
.kv-template-arg-label {
  width: auto;
  min-width: 20px;
  max-width: 180px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: #7a5a1e;
  text-align: left;
  flex-shrink: 0;
}
.kv-template-actions { display: flex; justify-content: flex-start; padding-top: 4px; }
.kv-template-args--compact {
  flex-direction: row;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 0;
  opacity: 0;
  overflow: hidden;
  pointer-events: none;
  transition: max-height .15s ease, opacity .15s ease, margin .15s ease;
  margin-top: 0;
}
.kv-block:hover .kv-template-body .kv-template-args--compact,
.kv-block:focus-within .kv-template-body .kv-template-args--compact,
.kv-template-body:hover .kv-template-args--compact,
.kv-template-body:focus-within .kv-template-args--compact {
  max-height: 220px;
  opacity: 1;
  pointer-events: auto;
  margin-top: 6px;
}
.kv-template-result {
  margin-top: 8px;
}
.kv-template-result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.kv-template-result-label {
  font-size: 11px;
  color: #9a7a3a;
  margin-bottom: 4px;
}
.kv-pre-template-result {
  background: #102015;
  color: #defbe6;
  max-height: 320px;
  overflow: auto;
  white-space: pre;
}
.kv-template-result--compact {
  max-height: 0;
  opacity: 0;
  overflow: hidden;
  pointer-events: none;
  transition: max-height .15s ease, opacity .15s ease, margin .15s ease;
  margin-top: 0;
}
.kv-block:hover .kv-template-body .kv-template-result--compact,
.kv-block:focus-within .kv-template-body .kv-template-result--compact,
.kv-template-body:hover .kv-template-result--compact,
.kv-template-body:focus-within .kv-template-result--compact {
  max-height: 240px;
  opacity: 1;
  pointer-events: auto;
  margin-top: 8px;
}
@media (hover: none) {
  .kv-template-args--compact {
    max-height: 220px;
    opacity: 1;
    pointer-events: auto;
    margin-top: 6px;
  }
  .kv-template-result--compact {
    max-height: 240px;
    opacity: 1;
    pointer-events: auto;
    margin-top: 8px;
  }
}
.kv-table-view-wrap { padding: 8px 12px 10px; overflow-x: auto; background: #fff; }
.kv-table-view { min-width: 320px; }
.kv-table-cell { white-space: pre-wrap; word-break: break-word; font-size: 12px; color: #1d1d1f; }
.kv-table-body { overflow-x: auto; }

/* shared micro */
.kv-date { font-size: 11px; color: #86868b; white-space: nowrap; }
.kv-score { font-size: 11px; color: #86868b; }
.kv-lbl { color: #fff !important; border: none !important; }
</style>
