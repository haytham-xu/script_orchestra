<template>
  <div class="ct-root" v-loading="loading">
    <div class="ct-header">
      <el-button type="default" size="small" @click="goBack">← Browser Agent</el-button>
      <h2 class="ct-title">Captcha Template Trainer</h2>
      <div class="ct-header-actions">
        <el-button size="small" @click="loadList">Refresh</el-button>
      </div>
    </div>

    <el-card class="ct-card">
      <template #header>
        <div class="ct-card-head">
          <span>Template coverage</span>
          <span class="ct-hint-small">
            Auto-solve kicks in only when EVERY glyph in a captcha has a template.
          </span>
        </div>
      </template>
      <div class="ct-coverage">
        <span v-for="b in templateBadges" :key="b.char"
              class="ct-badge" :class="{ 'ct-badge-empty': !b.have }">
          {{ b.char }} <span class="ct-badge-count">×{{ b.count }}</span>
        </span>
      </div>
    </el-card>

    <el-empty v-if="!loading && samples.length === 0"
              description="No pending training samples 🎉">
      <p class="ct-hint">
        Whenever you manually type a captcha answer in Download JM, the raw
        image is stashed under
        <code>~/.script_orchestra/browser_agent/captcha_training/</code>. Come
        back here to label it.
      </p>
    </el-empty>

    <el-card v-for="s in samples" :key="s.filename" class="ct-card ct-sample">
      <div class="ct-sample-body">
        <img :src="'data:image/jpeg;base64,' + s.image_base64" class="ct-sample-img" />
        <div class="ct-sample-info">
          <div class="ct-sample-meta">
            <span class="ct-mono">{{ s.filename }}</span>
            <span class="ct-hint-small">Previous answer hint: {{ s.answer_hint || '—' }}</span>
            <span class="ct-hint-small">Detected {{ s.glyph_count }} glyph(s)</span>
          </div>
          <div class="ct-sample-input">
            <el-input
              v-model="inputByFile[s.filename]"
              :placeholder="`Full expression, e.g. 16+5=  (needs ${s.glyph_count} chars)`"
              @keyup.enter="saveLabel(s)"
              style="width: 320px"
            />
            <el-button type="primary" :loading="busyByFile[s.filename]" @click="saveLabel(s)">
              Save templates
            </el-button>
            <el-button :loading="busyByFile[s.filename]" @click="skipSample(s)">
              Skip / delete
            </el-button>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script lang="ts" src="@/browser_agent/views/CaptchaTrainerView.ts"></script>

<style scoped>
.ct-root { padding: 24px 32px; box-sizing: border-box; max-width: 1200px; margin: 0 auto; }
.ct-header { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.ct-title { margin: 0; font-size: 22px; font-weight: 600; flex: 1; }
.ct-header-actions { display: flex; gap: 8px; }
.ct-card { margin-bottom: 20px; }
.ct-card-head { display: flex; align-items: center; justify-content: space-between; font-weight: 600; }
.ct-hint { color: #64748b; font-size: 13px; }
.ct-hint code { background: #f1f5f9; padding: 1px 6px; border-radius: 3px; font-size: 12px; }
.ct-hint-small { color: #64748b; font-size: 12px; }

.ct-coverage { display: flex; flex-wrap: wrap; gap: 8px; }
.ct-badge {
  padding: 4px 10px; border-radius: 4px; background: #dcfce7; color: #166534;
  font-family: monospace; font-size: 13px; font-weight: 600;
}
.ct-badge-empty { background: #fee2e2; color: #991b1b; }
.ct-badge-count { color: #6b7280; font-weight: 400; margin-left: 4px; }

.ct-sample-body { display: flex; gap: 16px; align-items: flex-start; }
.ct-sample-img {
  flex: none; border: 1px solid #d4d4d8; background: #fff; padding: 4px;
  border-radius: 4px; image-rendering: pixelated;
}
.ct-sample-info { flex: 1; display: flex; flex-direction: column; gap: 12px; }
.ct-sample-meta { display: flex; flex-direction: column; gap: 4px; }
.ct-sample-input { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.ct-mono { font-family: monospace; font-size: 12px; color: #334155; }
</style>
