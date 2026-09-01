<template>
  <div class="tr">
    <header class="tr-topbar">
      <div class="tr-topbar-inner">
        <h1>Translator</h1>
        <span class="tr-sub">Copilot-backed · zh ↔ en</span>
      </div>
    </header>

    <el-tabs v-model="activeTab" class="tr-tabs">
      <!-- ============ Scene 1: zh → en ============ -->
      <el-tab-pane label="ZH → EN (Slack + learning points)" name="zh2en">
        <div class="tr-scene">
          <div class="tr-card">
            <div class="tr-card-title">Chinese / mixed source</div>
            <el-input v-model="zhExtra" class="tr-extra" size="small"
              placeholder="(optional) one-off extra instruction for this translation, e.g. more formal / American casual" />
            <el-input v-model="zhInput" type="textarea" :rows="5"
              placeholder="Write what you want to say, in Chinese or mixed Chinese/English…" />
            <div class="tr-actions">
              <div class="tr-model-pick">
                <span class="tr-model-label">Model</span>
                <el-select v-model="zhModel" size="small" class="tr-model-select">
                  <el-option v-for="m in modelOptions" :key="m.id" :label="m.name" :value="m.id" />
                </el-select>
              </div>
              <el-button type="primary" :loading="zhLoading" @click="runZh2En">
                {{ zhLoading ? 'Translating…' : 'Translate' }}
              </el-button>
            </div>
          </div>

          <!-- live streaming (while translating) -->
          <div v-if="zhLoading" class="tr-card tr-stream-card">
            <div class="tr-card-title">Translating…</div>
            <div class="tr-stream">{{ zhStreaming }}<span class="tr-cursor">▋</span></div>
            <div v-if="zhPhase" class="tr-phase">{{ zhPhase }}</div>
          </div>

          <!-- per-call usage -->
          <div v-if="!zhLoading && zhUsage && fmtUsage(zhUsage)" class="tr-usage-line">
            This call: {{ fmtUsage(zhUsage) }}
          </div>

          <!-- English + back-translation side by side -->
          <div v-if="!zhLoading && zhEnglish" class="tr-two-col">
            <div class="tr-card">
              <div class="tr-card-head">
                <span class="tr-card-title">Slack-style English</span>
                <el-button size="small" text @click="copyText(zhEnglish)">Copy</el-button>
              </div>
              <div class="tr-output tr-md" v-html="renderMarkdown(zhEnglish)"></div>
            </div>
            <div class="tr-card">
              <div class="tr-card-head">
                <span class="tr-card-title">Chinese back-translation (for review)</span>
                <el-button size="small" text @click="copyText(zhBack)">Copy</el-button>
              </div>
              <div v-if="zhBack" class="tr-output tr-output-muted tr-md" v-html="renderMarkdown(zhBack)"></div>
              <div v-else class="tr-output tr-output-muted">—</div>
            </div>
          </div>

          <!-- English learning points -->
          <div v-if="!zhLoading && zhEnglish" class="tr-card">
            <div class="tr-card-head">
              <span class="tr-card-title">English learning points</span>
              <el-button v-if="zhPoints.length" size="small" @click="copyAllPoints">Copy all</el-button>
            </div>
            <el-empty v-if="!zhPoints.length" description="Nothing obvious to improve here 👍" :image-size="60" />
            <div v-else class="tr-points">
              <div v-for="(p, i) in zhPoints" :key="p.id || i" class="tr-point">
                <div class="tr-point-main">
                  <div class="tr-point-orig">{{ p.original }}</div>
                  <div v-if="p.suggestion" class="tr-point-sug">→ {{ p.suggestion }}</div>
                  <div v-if="p.explanation" class="tr-point-exp">{{ p.explanation }}</div>
                </div>
                <el-button size="small" text @click="copyPoint(p)">Copy</el-button>
              </div>
            </div>
          </div>

          <!-- Scene 1 history -->
          <div class="tr-card">
            <div class="tr-card-title">History</div>
            <el-empty v-if="!zhHistory.length" description="No records yet" :image-size="60" />
            <el-collapse v-else class="tr-hist">
              <el-collapse-item v-for="h in zhHistory" :key="h.id" :name="h.id">
                <template #title>
                  <span class="tr-hist-title">{{ h.source_text }}</span>
                  <span class="tr-hist-date">{{ fmtDate(h.created_at) }}</span>
                </template>
                <div class="tr-hist-body">
                  <div class="tr-hist-row"><b>English:</b> {{ h.result_text }}</div>
                  <div v-if="h.back_translation" class="tr-hist-row tr-output-muted">
                    <b>Back-translation:</b> {{ h.back_translation }}
                  </div>
                  <div v-if="fmtUsage(h.usage)" class="tr-hist-usage">Usage: {{ fmtUsage(h.usage) }}</div>
                  <div v-if="h.learning_points.length" class="tr-hist-points">
                    <div v-for="p in h.learning_points" :key="p.id" class="tr-hist-point">
                      · {{ p.original }}<template v-if="p.suggestion"> → {{ p.suggestion }}</template>
                      <template v-if="p.explanation"> ({{ p.explanation }})</template>
                    </div>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
      </el-tab-pane>

      <!-- ============ Scene 2: en → zh ============ -->
      <el-tab-pane label="EN → ZH (faithful translation)" name="en2zh">
        <div class="tr-scene">
          <div class="tr-card">
            <div class="tr-card-title">English source / Slack chat log</div>
            <el-input v-model="enExtra" class="tr-extra" size="small"
              placeholder="(optional) one-off extra instruction for this translation, e.g. keep proper nouns / more casual" />
            <el-input v-model="enInput" type="textarea" :rows="6"
              placeholder="Paste English or a Slack chat log…" />
            <div class="tr-actions">
              <div class="tr-model-pick">
                <span class="tr-model-label">Model</span>
                <el-select v-model="enModel" size="small" class="tr-model-select">
                  <el-option v-for="m in modelOptions" :key="m.id" :label="m.name" :value="m.id" />
                </el-select>
              </div>
              <el-button type="primary" :loading="enLoading" @click="runEn2Zh">
                {{ enLoading ? 'Translating…' : 'Translate' }}
              </el-button>
            </div>
          </div>

          <!-- live streaming (while translating) -->
          <div v-if="enLoading" class="tr-card tr-stream-card">
            <div class="tr-card-title">Translating…</div>
            <div class="tr-stream">{{ enStreaming }}<span class="tr-cursor">▋</span></div>
          </div>

          <div v-if="!enLoading && enUsage && fmtUsage(enUsage)" class="tr-usage-line">
            This call: {{ fmtUsage(enUsage) }}
          </div>

          <div v-if="!enLoading && enChinese" class="tr-card">
            <div class="tr-card-head">
              <span class="tr-card-title">Chinese translation</span>
              <el-button size="small" text @click="copyText(enChinese)">Copy</el-button>
            </div>
            <div class="tr-output tr-md" v-html="renderMarkdown(enChinese)"></div>
          </div>

          <!-- Scene 2 history -->
          <div class="tr-card">
            <div class="tr-card-title">History</div>
            <el-empty v-if="!enHistory.length" description="No records yet" :image-size="60" />
            <el-collapse v-else class="tr-hist">
              <el-collapse-item v-for="h in enHistory" :key="h.id" :name="h.id">
                <template #title>
                  <span class="tr-hist-title">{{ h.source_text }}</span>
                  <span class="tr-hist-date">{{ fmtDate(h.created_at) }}</span>
                </template>
                <div class="tr-hist-body">
                  <div class="tr-hist-row"><b>Chinese:</b> {{ h.result_text }}</div>
                  <div v-if="fmtUsage(h.usage)" class="tr-hist-usage">Usage: {{ fmtUsage(h.usage) }}</div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
      </el-tab-pane>

      <!-- ============ Settings ============ -->
      <el-tab-pane label="Settings" name="settings">
        <div class="tr-scene">
          <div class="tr-card">
            <div class="tr-card-title">Scene 1 · ZH → EN</div>
            <label class="tr-label">System prompt (translation style, write your own)</label>
            <el-input v-model="settings.zh2en.system_prompt" type="textarea" :rows="4"
              placeholder="e.g. Translate into concise, friendly Slack-style English…" />
            <label class="tr-label">Learning-point preference (optional)</label>
            <el-input v-model="settings.zh2en.learning_prompt" type="textarea" :rows="3"
              placeholder="Steer what the learning points focus on, e.g. emphasize preposition collocations and business tone. (Appended to the built-in learning-point instruction; does not change the JSON format.)" />
            <label class="tr-label">Model</label>
            <el-select v-model="settings.zh2en.model" class="tr-select">
              <el-option v-for="m in modelOptions" :key="m.id" :label="m.name" :value="m.id" />
            </el-select>
          </div>

          <div class="tr-card">
            <div class="tr-card-title">Scene 2 · EN → ZH</div>
            <label class="tr-label">System prompt (translation style, write your own)</label>
            <el-input v-model="settings.en2zh.system_prompt" type="textarea" :rows="4"
              placeholder="e.g. Translate into faithful, objective Chinese…" />
            <label class="tr-label">Model</label>
            <el-select v-model="settings.en2zh.model" class="tr-select">
              <el-option v-for="m in modelOptions" :key="m.id" :label="m.name" :value="m.id" />
            </el-select>
          </div>

          <div class="tr-card">
            <div class="tr-card-title">Cumulative usage</div>
            <el-empty v-if="!usageSummary || !usageSummary.count" description="No usage yet" :image-size="60" />
            <div v-else class="tr-usage-grid">
              <div class="tr-usage-cell">
                <div class="tr-usage-num">{{ usageSummary.total_credits }}</div>
                <div class="tr-usage-cap">Total AI Credits</div>
              </div>
              <div class="tr-usage-cell">
                <div class="tr-usage-num">{{ usageSummary.count }}</div>
                <div class="tr-usage-cap">Translations</div>
              </div>
              <div class="tr-usage-cell">
                <div class="tr-usage-num">↑{{ usageSummary.total_input_tokens }} ↓{{ usageSummary.total_output_tokens }}</div>
                <div class="tr-usage-cap">Total tokens</div>
              </div>
            </div>
            <div v-if="usageSummary && usageSummary.count" class="tr-usage-byscene">
              <span>ZH→EN: {{ usageSummary.by_scene.zh2en.total_credits }} credits / {{ usageSummary.by_scene.zh2en.count }} calls</span>
              <span>EN→ZH: {{ usageSummary.by_scene.en2zh.total_credits }} credits / {{ usageSummary.by_scene.en2zh.count }} calls</span>
            </div>
          </div>

          <div class="tr-card">
            <div class="tr-card-title">Data cleanup</div>
            <div class="tr-cleanup">
              <span>Delete history older than</span>
              <el-input-number v-model="cleanupDays" :min="1" :max="3650" :step="1" size="small" />
              <span>days (both scenes)</span>
              <el-button type="danger" plain size="small" :loading="cleaning" @click="runCleanup">
                Clean up
              </el-button>
            </div>
            <div class="tr-hint">Default days ({{ settings.cleanup_days }}) can be changed when you save settings:</div>
            <div class="tr-cleanup">
              <span>Default cleanup days</span>
              <el-input-number v-model="settings.cleanup_days" :min="1" :max="3650" size="small" />
            </div>
          </div>

          <div class="tr-actions">
            <el-button type="primary" :loading="savingSettings" @click="saveSettings">Save settings</el-button>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script lang="ts" src="@/translator/views/TranslatorView.ts"></script>

<style scoped>
.tr { max-width: 900px; margin: 0 auto; padding: 0 16px 48px; }
.tr-topbar { padding: 20px 0 8px; }
.tr-topbar-inner { display: flex; align-items: baseline; gap: 12px; }
.tr-topbar h1 { font-size: 24px; font-weight: 600; color: #1d1d1f; margin: 0; }
.tr-sub { font-size: 13px; color: #86868b; }
.tr-tabs { margin-top: 8px; }
.tr-scene { display: flex; flex-direction: column; gap: 16px; padding-top: 8px; }
.tr-card { background: #fff; border: 1px solid rgba(0,0,0,0.06); border-radius: 12px;
  padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.03); }
.tr-card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.tr-card-title { font-size: 15px; font-weight: 600; color: #1d1d1f; margin-bottom: 8px; display: block; }
.tr-card-head .tr-card-title { margin-bottom: 0; }
.tr-actions { margin-top: 12px; display: flex; justify-content: flex-end; align-items: center; gap: 12px; }
.tr-model-pick { display: flex; align-items: center; gap: 6px; margin-right: auto; }
.tr-model-label { font-size: 13px; color: #6e6e73; }
.tr-model-select { width: 180px; }
.tr-usage-line { font-size: 12px; color: #86868b; padding: 0 4px; margin-top: -6px; }
.tr-hist-usage { font-size: 12px; color: #86868b; margin-top: 4px; }
.tr-usage-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.tr-usage-cell { text-align: center; padding: 12px; border: 1px solid rgba(0,0,0,0.05);
  border-radius: 8px; background: #fafafa; }
.tr-usage-num { font-size: 20px; font-weight: 600; color: #1d1d1f; }
.tr-usage-cap { font-size: 12px; color: #86868b; margin-top: 4px; }
.tr-usage-byscene { display: flex; gap: 20px; flex-wrap: wrap; margin-top: 12px;
  font-size: 13px; color: #6e6e73; }
.tr-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 720px) { .tr-two-col { grid-template-columns: 1fr; } }
.tr-output { white-space: pre-wrap; line-height: 1.6; color: #1d1d1f; font-size: 14px; }
.tr-extra { margin-bottom: 8px; }
/* markdown-rendered output (v-html): keep links/emphasis/code readable */
.tr-md { white-space: normal; }
.tr-md :deep(p) { margin: 0 0 8px; line-height: 1.6; }
.tr-md :deep(p:last-child) { margin-bottom: 0; }
.tr-md :deep(a) { color: #0a84ff; text-decoration: none; }
.tr-md :deep(a:hover) { text-decoration: underline; }
.tr-md :deep(code) { background: rgba(0,0,0,0.05); padding: 1px 5px; border-radius: 4px;
  font-size: 13px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.tr-md :deep(pre) { background: rgba(0,0,0,0.05); padding: 10px; border-radius: 8px; overflow-x: auto; }
.tr-md :deep(pre code) { background: none; padding: 0; }
.tr-md :deep(ul), .tr-md :deep(ol) { margin: 4px 0 8px; padding-left: 22px; }
.tr-md :deep(strong) { font-weight: 600; }
.tr-stream-card { border-color: rgba(10,132,255,0.3); }
.tr-stream { white-space: pre-wrap; line-height: 1.6; color: #1d1d1f; font-size: 14px; min-height: 22px; }
.tr-cursor { display: inline-block; color: #0a84ff; animation: tr-blink 1s step-end infinite; }
@keyframes tr-blink { 50% { opacity: 0; } }
.tr-phase { margin-top: 8px; font-size: 12px; color: #0a84ff; }
.tr-output-muted { color: #6e6e73; }
.tr-points { display: flex; flex-direction: column; gap: 8px; }
.tr-point { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px;
  padding: 10px 12px; border: 1px solid rgba(0,0,0,0.05); border-radius: 8px; background: #fafafa; }
.tr-point-main { min-width: 0; }
.tr-point-orig { font-size: 14px; color: #1d1d1f; }
.tr-point-sug { font-size: 14px; color: #0a84ff; margin-top: 2px; }
.tr-point-exp { font-size: 12px; color: #86868b; margin-top: 4px; }
.tr-hist { border: none; }
/* let long source_text wrap onto multiple lines inside the collapse header */
.tr-hist :deep(.el-collapse-item__header) { height: auto; min-height: 48px;
  align-items: flex-start; padding: 10px 0; line-height: 1.5; }
.tr-hist-title { flex: 1; min-width: 0; white-space: normal; word-break: break-word;
  line-height: 1.5; color: #1d1d1f; font-size: 14px; }
.tr-hist-date { flex-shrink: 0; margin-left: 12px; font-size: 12px; color: #86868b; }
.tr-hist-body { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: #3a3a3c; }
.tr-hist-row { line-height: 1.5; }
.tr-hist-points { margin-top: 4px; border-top: 1px dashed rgba(0,0,0,0.08); padding-top: 6px; }
.tr-hist-point { font-size: 12px; color: #6e6e73; line-height: 1.6; }
.tr-label { display: block; font-size: 13px; color: #6e6e73; margin: 10px 0 4px; }
.tr-select { width: 240px; }
.tr-cleanup { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; color: #3a3a3c; }
.tr-hint { font-size: 12px; color: #86868b; margin: 10px 0 6px; }
</style>
