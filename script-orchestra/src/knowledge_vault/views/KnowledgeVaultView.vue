<template>
  <div class="kv">
    <header class="kv-topbar">
      <div class="kv-topbar-inner">
        <h1>Knowledge Vault</h1>
        <!-- Network build controls hidden (the Network tab is retired for now). Kept for easy restore.
        <div class="kv-auto">
          <span>Auto-build</span>
          <el-switch :model-value="settings.auto_build" @change="(v: any) => toggleAutoBuild(v)" />
          <el-button size="small" :loading="building" @click="rebuild">
            {{ building ? (buildPhase ? 'Building — ' + buildPhase : 'Building…') : 'Rebuild network' }}
          </el-button>
        </div>
        -->
      </div>
    </header>

    <el-tabs v-model="activeTab" class="kv-tabs" @tab-change="activeTab === 'duplicates' && loadDuplicates()">
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

      <!-- Duplicates (Network tab hidden; its code is retained in the .ts/service) -->
      <el-tab-pane label="Duplicates" name="duplicates">
        <div class="kv-dup">
          <div class="kv-dup-head">
            <el-button type="primary" :loading="dupLoading" @click="loadDuplicates">Find duplicates</el-button>
            <el-button v-if="dupFuzzy.length" :loading="aiChecking" @click="aiCheckFuzzy">
              Let AI judge {{ dupFuzzy.length }} fuzzy pair(s) · costs tokens
            </el-button>
            <span class="kv-hint">Compares your fragments by meaning (free, offline). AI check is optional and only for the fuzzy ones.</span>
          </div>

          <el-empty v-if="dupChecked && !dupConfident.length && !dupFuzzy.length"
            description="No duplicates found." :image-size="70" />
          <el-empty v-else-if="!dupChecked"
            description="Click “Find duplicates” to scan for near-identical fragments." :image-size="70" />

          <!-- Confident duplicates -->
          <template v-if="dupConfident.length">
            <h4 class="kv-dup-section">Likely duplicates <el-tag type="danger" size="small" round>{{ dupConfident.length }}</el-tag></h4>
            <div v-for="p in dupConfident" :key="pairKey(p)" class="kv-dup-pair">
              <div class="kv-dup-side">
                <div class="kv-dup-content" :title="p.a.content">{{ p.a.note || p.a.content }}</div>
                <div class="kv-dup-sub">{{ p.a.content }}</div>
                <el-button size="small" :loading="dupActing === pairKey(p)" @click="resolvePair(p, p.a, p.b)">Keep this</el-button>
              </div>
              <div class="kv-dup-mid"><span class="kv-dup-sim">{{ (p.sim * 100).toFixed(0) }}%</span></div>
              <div class="kv-dup-side">
                <div class="kv-dup-content" :title="p.b.content">{{ p.b.note || p.b.content }}</div>
                <div class="kv-dup-sub">{{ p.b.content }}</div>
                <el-button size="small" :loading="dupActing === pairKey(p)" @click="resolvePair(p, p.b, p.a)">Keep this</el-button>
              </div>
            </div>
          </template>

          <!-- Fuzzy candidates -->
          <template v-if="dupFuzzy.length">
            <h4 class="kv-dup-section">Possible duplicates <el-tag type="warning" size="small" round>{{ dupFuzzy.length }}</el-tag>
              <span class="kv-hint">worded differently — run the AI check if unsure</span></h4>
            <div v-for="p in dupFuzzy" :key="pairKey(p)" class="kv-dup-pair"
              :class="{ 'kv-dup-ai': aiDupKeys.has(pairKey(p)) }">
              <div class="kv-dup-side">
                <div class="kv-dup-content" :title="p.a.content">{{ p.a.note || p.a.content }}</div>
                <div class="kv-dup-sub">{{ p.a.content }}</div>
                <el-button size="small" :loading="dupActing === pairKey(p)" @click="resolvePair(p, p.a, p.b)">Keep this</el-button>
              </div>
              <div class="kv-dup-mid">
                <span class="kv-dup-sim">{{ (p.sim * 100).toFixed(0) }}%</span>
                <el-tag v-if="aiDupKeys.has(pairKey(p))" type="danger" size="small">AI: dup</el-tag>
              </div>
              <div class="kv-dup-side">
                <div class="kv-dup-content" :title="p.b.content">{{ p.b.note || p.b.content }}</div>
                <div class="kv-dup-sub">{{ p.b.content }}</div>
                <el-button size="small" :loading="dupActing === pairKey(p)" @click="resolvePair(p, p.b, p.a)">Keep this</el-button>
              </div>
            </div>
          </template>
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

.kv-dup-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
.kv-dup-section { margin: 18px 0 8px; font-size: 15px; display: flex; align-items: center; gap: 8px; }
.kv-dup-pair { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 12px;
  background: #fff; border: 1px solid rgba(0,0,0,0.07); border-radius: 12px; padding: 12px 14px; margin-bottom: 8px; }
.kv-dup-ai { border-color: rgba(255,59,48,0.4); box-shadow: 0 0 0 1px rgba(255,59,48,0.15); }
.kv-dup-side { min-width: 0; display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
.kv-dup-content { font-size: 14px; color: #1d1d1f; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.kv-dup-sub { font-size: 12px; color: #86868b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.kv-dup-mid { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.kv-dup-sim { font-size: 12px; font-weight: 600; color: #86868b; }
</style>
