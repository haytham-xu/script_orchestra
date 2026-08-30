<template>
  <div class="kv">
    <header class="kv-topbar">
      <div class="kv-topbar-inner">
        <h1>Knowledge Vault</h1>
        <div class="kv-auto">
          <span>Auto-build</span>
          <el-switch :model-value="settings.auto_build" @change="(v: any) => toggleAutoBuild(v)" />
          <el-button size="small" :loading="building" @click="rebuild">
            {{ building ? (buildPhase ? 'Building — ' + buildPhase : 'Building…') : 'Rebuild network' }}
          </el-button>
        </div>
      </div>
    </header>

    <el-tabs v-model="activeTab" class="kv-tabs" @tab-change="activeTab === 'network' && loadNetwork()">
      <!-- Capture -->
      <el-tab-pane label="Capture" name="capture">
        <div class="kv-capture">
          <div class="kv-cap-head">
            <span class="kv-cap-title">Fragments</span>
            <div style="display:flex; gap:8px;">
              <el-button type="primary" @click="openAdd">Add fragment</el-button>
              <el-button @click="openBatch">Batch import (AI)</el-button>
            </div>
          </div>

          <div class="kv-list">
            <el-empty v-if="!fragments.length" description="No fragments yet" :image-size="70" />
            <div v-for="row in fragments" :key="row.id" class="kv-frag"
              :class="{ 'kv-frag-hl': highlightFragId === row.id }" :data-frag-id="row.id">
              <div class="kv-frag-main">
                <div class="kv-frag-content" :title="row.content">{{ row.content }}</div>
                <div v-if="row.note" class="kv-frag-note">{{ row.note }}</div>
                <div class="kv-frag-meta">
                  <el-tag v-if="row.kind" size="small" effect="plain" class="kv-kind">{{ row.kind }}</el-tag>
                  <el-tag v-for="lid in row.label_ids" :key="lid" size="small"
                    :color="labelMap[lid]?.color" class="kv-lbl">{{ labelMap[lid]?.name }}</el-tag>
                  <span class="kv-dot">·</span>
                  <span class="kv-added">{{ fmtDate(row.created_at) }}</span>
                  <span class="kv-dot">·</span>
                  <el-tag size="small" :type="FRESH_TYPE[row.freshness]" effect="light">
                    {{ FRESH_LABEL[row.freshness] || row.freshness }}
                  </el-tag>
                </div>
              </div>
              <div class="kv-frag-actions">
                <el-button size="small" text @click="openEdit(row)">Edit</el-button>
                <el-button size="small" text type="danger" @click="removeFragment(row)">Delete</el-button>
              </div>
            </div>
          </div>
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
          <div class="kv-list" style="margin-top:12px;">
            <el-empty v-if="!results.length" description="No results" :image-size="60" />
            <div v-for="row in results" :key="row.id" class="kv-frag">
              <div class="kv-frag-main">
                <div class="kv-frag-content" :title="row.content">{{ row.content }}</div>
                <div v-if="row.note" class="kv-frag-note">{{ row.note }}</div>
                <div class="kv-frag-meta">
                  <el-tag v-if="row.kind" size="small" effect="plain" class="kv-kind">{{ row.kind }}</el-tag>
                  <span v-if="row.score != null" class="kv-score">match {{ Number(row.score).toFixed(2) }}</span>
                </div>
              </div>
            </div>
          </div>
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

          <!-- Filter by kind + search-to-focus a node (C2). -->
          <div v-if="nodes.length" class="kv-net-tools">
            <div class="kv-kind-filter">
              <span class="kv-hint">Show:</span>
              <el-check-tag v-for="k in graphKinds" :key="k" :checked="kindFilter.has(k)"
                @change="toggleKind(k)">{{ k }}</el-check-tag>
              <template v-if="graphLabels.length">
                <span class="kv-hint" style="margin-left:8px">Labels:</span>
                <el-check-tag v-for="l in graphLabels" :key="l.id" :checked="labelFilter.has(l.id)"
                  @change="toggleLabelFilter(l.id)">{{ l.name }}</el-check-tag>
              </template>
              <span v-if="kindFilter.size || labelFilter.size" class="kv-hint">({{ visibleNodes.length }}/{{ nodes.length }})</span>
            </div>
            <el-input v-model="nodeSearch" placeholder="Find a node…" clearable size="small"
              style="max-width:240px" @keyup.enter="focusSearch">
              <template #append><el-button @click="focusSearch">Locate</el-button></template>
            </el-input>
            <el-button v-if="settings.link_check_enabled" size="small" :loading="checkingLinks"
              @click="checkLinks">Check links</el-button>
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
              <div v-if="selectedFragments.length" class="kv-detail-frags">
                <div v-for="f in selectedFragments" :key="f.id" class="kv-detail-frag"
                  :title="f.content" @click="goToFragment(f)">
                  <span class="kv-detail-frag-text">{{ f.note || f.content }}</span>
                  <el-icon class="kv-detail-frag-go"><Right /></el-icon>
                </div>
              </div>
            </el-card>
          </div>

          <!-- Needs review: nodes that have gone stale. Each: keep (still valid) or archive. -->
          <div v-if="stale.length" class="kv-stale">
            <div class="kv-stale-head">
              <h4>Needs review <el-tag type="danger" size="small" round>{{ stale.length }}</el-tag></h4>
              <span class="kv-hint">Untouched a long while — likely outdated. Keep it (marks as still valid) or archive it.</span>
            </div>
            <div v-for="s in stale" :key="s.id" class="kv-stale-row">
              <div class="kv-stale-main">
                <div class="kv-stale-title" :title="s.summary || s.title">{{ s.title }}</div>
                <div class="kv-stale-meta">
                  <el-tag v-if="s.kind" size="small" effect="plain">{{ s.kind }}</el-tag>
                  <span>{{ s.fragment_ids?.length || 0 }} source fragment(s)</span>
                </div>
              </div>
              <div class="kv-stale-actions">
                <el-button size="small" :loading="staleActing === s.id" @click="markReviewed(s)">Still valid</el-button>
                <el-button size="small" type="danger" plain :loading="staleActing === s.id" @click="archiveStale(s)">Archive</el-button>
              </div>
            </div>
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

          <h3 style="margin-top:24px">Link checking</h3>
          <p class="kv-hint">
            Probe your saved URLs over HTTP so dead links get flagged for review sooner.
            <strong>This sends requests to those URLs' servers</strong> (they can see the request in their logs),
            so it's off by default. When on, use “Check links” on the Network tab.
          </p>
          <div class="kv-link-toggle">
            <el-switch :model-value="settings.link_check_enabled" @change="(v: any) => toggleLinkCheck(v)" />
            <span>{{ settings.link_check_enabled ? 'Enabled' : 'Disabled' }}</span>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- Add fragment dialog -->
    <el-dialog v-model="addDialog" title="Add a fragment" width="520px">
      <el-input v-model="draft.content" type="textarea" :rows="3"
        placeholder="Paste a URL / command / snippet…" />
      <el-input v-model="draft.note" placeholder="Note — what is this?" style="margin-top:8px" />
      <el-select v-model="draft.label_ids" multiple collapse-tags placeholder="Labels (optional)"
        style="width:100%; margin-top:8px">
        <el-option v-for="l in labels" :key="l.id" :label="l.name" :value="l.id" />
      </el-select>
      <template #footer>
        <el-button @click="addDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="saving" @click="addFragment">Save</el-button>
      </template>
    </el-dialog>

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

    <!-- Batch import dialog — conversational: chat with AI, it regenerates the draft -->
    <el-dialog v-model="batchDialog" title="Batch import — talk to AI to shape your fragments" width="960px" top="5vh">
      <div class="kv-batch">
        <!-- left: chat -->
        <div class="kv-chat">
          <div class="kv-chat-log">
            <el-empty v-if="!messages.length"
              description="Paste a messy pile of knowledge, then ask AI to split it — and keep refining by chatting."
              :image-size="70" />
            <div v-for="(m, i) in messages" :key="i" class="kv-msg" :class="m.role">
              <div class="kv-bubble">{{ m.content }}</div>
            </div>
            <div v-if="chatLoading" class="kv-msg assistant"><div class="kv-bubble kv-typing">…</div></div>
          </div>
          <div class="kv-chat-input">
            <el-input v-model="chatInput" type="textarea" :rows="2" resize="none"
              placeholder="e.g. paste your notes, or “merge the last two”, “change note of the azure url”…"
              @keyup.enter.exact.prevent="sendChat" />
            <el-button type="primary" :loading="chatLoading" @click="sendChat">Send</el-button>
          </div>
        </div>

        <!-- right: live draft -->
        <div class="kv-draft">
          <p class="kv-hint">
            {{ analyzed.filter(a => a._keep).length }} of {{ analyzed.length }} selected — the draft updates as you chat.
          </p>
          <el-empty v-if="!analyzed.length" description="No draft yet" :image-size="60" />
          <div v-else class="kv-draft-list">
            <div v-for="(row, i) in analyzed" :key="i" class="kv-draft-item" :class="{ off: !row._keep }">
              <el-checkbox v-model="row._keep" class="kv-draft-check" />
              <div class="kv-draft-fields">
                <el-input v-model="row.content" size="small" placeholder="Content" />
                <div class="kv-draft-sub">
                  <el-input v-model="row.note" size="small" placeholder="Note" />
                  <el-tag v-if="row.kind" size="small" effect="plain" class="kv-kind">{{ row.kind }}</el-tag>
                </div>
              </div>
            </div>
          </div>
          <div v-if="suggestedLabels.length" class="kv-suggested">
            <span class="kv-hint">Suggested labels:</span>
            <el-tag v-for="name in suggestedLabels" :key="name" size="small" type="info"
              effect="plain" class="kv-suggest-tag" @click="applySuggestedLabel(name)">
              + {{ name }}
            </el-tag>
          </div>
          <el-select v-model="batchLabelIds" multiple collapse-tags placeholder="Apply labels to all (optional)"
            style="width:100%; margin-top:8px">
            <el-option v-for="l in labels" :key="l.id" :label="l.name" :value="l.id" />
          </el-select>
        </div>
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
.kv { min-height: 100vh; width: 100%; box-sizing: border-box; background: #f5f5f7; color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; }
.kv-topbar { display: flex; padding: 16px 24px; border-bottom: 1px solid rgba(0,0,0,0.06); background: #fff; }
.kv-topbar-inner { display: flex; align-items: center; justify-content: space-between;
  width: 100%; max-width: 1240px; margin: 0 auto; }
.kv-topbar h1 { margin: 0; font-size: 20px; font-weight: 600; }
.kv-auto { display: flex; align-items: center; gap: 10px; font-size: 13px; color: #86868b; }
.kv-tabs { padding: 0 24px; max-width: 1240px; margin: 0 auto; }
.kv-capture, .kv-search { max-width: 1100px; margin: 16px auto; }
.kv-settings { max-width: 1100px; margin: 16px auto; }
.kv-network { max-width: 1200px; margin: 16px auto; }
.kv-hint { font-size: 12px; color: #86868b; margin: 0; }

.kv-cap-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.kv-cap-title { font-size: 14px; font-weight: 600; }
.kv-cap-row { display: flex; gap: 8px; align-items: center; margin-top: 8px; }

.kv-label-add { display: flex; gap: 8px; align-items: center; margin: 12px 0; }
.kv-label-list { display: flex; flex-wrap: wrap; align-items: center; }
.kv-analyzed { margin-top: 12px; }
.kv-added { font-size: 12px; color: #86868b; }

/* fragment cards (Capture + Search lists) */
.kv-list { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
.kv-frag { display: flex; align-items: flex-start; gap: 12px; background: #fff;
  border: 1px solid rgba(0,0,0,0.06); border-radius: 10px; padding: 12px 14px;
  transition: box-shadow .15s, border-color .15s; }
.kv-frag:hover { border-color: rgba(10,132,255,0.35); box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
.kv-frag-main { flex: 1; min-width: 0; }
.kv-frag-content { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px; color: #1d1d1f; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.kv-frag-note { font-size: 13px; color: #3a3a3c; margin-top: 3px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kv-frag-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.kv-frag-meta .kv-added { font-size: 12px; }
.kv-kind { text-transform: capitalize; }
.kv-lbl { color: #fff !important; border: none !important; }
.kv-dot { color: #d2d2d7; }
.kv-score { font-size: 12px; color: #86868b; }
.kv-frag-actions { flex-shrink: 0; opacity: 0; transition: opacity .15s; }
.kv-frag:hover .kv-frag-actions { opacity: 1; }

/* batch draft cards */
.kv-draft-list { display: flex; flex-direction: column; gap: 8px; }
.kv-draft-item { display: flex; gap: 10px; align-items: flex-start; padding: 10px;
  background: #fff; border: 1px solid rgba(0,0,0,0.06); border-radius: 8px; }
.kv-draft-item.off { opacity: 0.45; }
.kv-draft-check { margin-top: 4px; }
.kv-draft-fields { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.kv-draft-sub { display: flex; gap: 6px; align-items: center; }

/* conversational batch import */
.kv-batch { display: flex; gap: 16px; height: 62vh; }
.kv-chat { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.kv-chat-log { flex: 1; overflow-y: auto; padding: 8px; background: #f5f5f7;
  border-radius: 10px; }
.kv-msg { display: flex; margin: 6px 0; }
.kv-msg.user { justify-content: flex-end; }
.kv-bubble { max-width: 82%; padding: 8px 12px; border-radius: 12px; font-size: 13px;
  white-space: pre-wrap; word-break: break-word; }
.kv-msg.user .kv-bubble { background: #0a84ff; color: #fff; }
.kv-msg.assistant .kv-bubble { background: #fff; color: #1d1d1f; border: 1px solid rgba(0,0,0,0.06); }
.kv-typing { letter-spacing: 2px; color: #86868b; }
.kv-chat-input { display: flex; gap: 8px; align-items: flex-end; margin-top: 8px; }
.kv-draft { width: 460px; display: flex; flex-direction: column; overflow-y: auto; }
.kv-suggested { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.kv-suggest-tag { cursor: pointer; }

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

.kv-stale { margin-top: 16px; background: #fff; border-radius: 12px;
  border: 1px solid rgba(255,59,48,0.18); overflow: hidden; }
.kv-stale-head { padding: 12px 16px; border-bottom: 1px solid rgba(0,0,0,0.05);
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.kv-stale-head h4 { margin: 0; font-size: 15px; }
.kv-stale-row { display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 10px 16px; border-bottom: 1px solid rgba(0,0,0,0.04); }
.kv-stale-row:last-child { border-bottom: none; }
.kv-stale-main { min-width: 0; }
.kv-stale-title { font-size: 14px; color: #1d1d1f; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.kv-stale-meta { display: flex; align-items: center; gap: 8px; margin-top: 4px;
  font-size: 12px; color: #86868b; }
.kv-stale-actions { flex-shrink: 0; }

.kv-net-tools { display: flex; align-items: center; justify-content: space-between;
  gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.kv-kind-filter { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.kv-link-toggle { display: flex; align-items: center; gap: 10px; font-size: 13px; color: #3a3a3c; }
.kv-detail-frags { margin-top: 10px; border-top: 1px solid rgba(0,0,0,0.06); padding-top: 8px; }
.kv-detail-frag { display: flex; align-items: center; gap: 6px; padding: 5px 6px;
  border-radius: 6px; cursor: pointer; font-size: 12px; color: #3a3a3c; }
.kv-detail-frag:hover { background: rgba(10,132,255,0.08); color: #0a84ff; }
.kv-detail-frag-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kv-detail-frag-go { flex-shrink: 0; opacity: 0.6; }
.kv-frag-hl { animation: kv-flash 2.4s ease-out; }
@keyframes kv-flash {
  0%, 30% { background: rgba(10,132,255,0.16); box-shadow: 0 0 0 2px rgba(10,132,255,0.4); }
  100% { background: transparent; box-shadow: none; }
}
</style>
