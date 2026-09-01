<template>
  <div class="dt2-root">
    <div class="dt2-header">
      <el-button type="default" size="small" @click="goBack">← Browser Agent</el-button>
      <h2 class="dt2-title">Download JM</h2>
      <div class="dt2-header-actions">
        <el-button size="small" @click="$router.push('/browser-agent/settings')">Settings</el-button>
      </div>
    </div>

    <div v-if="!configReady" class="dt2-config-missing">
      <el-alert type="warning" show-icon :closable="false">
        <template #title>Download JM is not configured yet</template>
        Go to
        <el-button link @click="$router.push('/browser-agent/settings')">Settings</el-button>
        and fill in source domain + download path. This tool requires you to be
        <strong>already logged in to the site in your browser</strong>.
      </el-alert>
    </div>

    <template v-else>
      <el-card class="dt2-card">
        <template #header>
          <div class="dt2-card-head">
            <span>Auth check</span>
            <el-button size="small" @click="doCheckAuth">Recheck</el-button>
          </div>
        </template>
        <el-tag :type="authStatus === 'ok' ? 'success' : authStatus === 'needs_login' ? 'warning' : authStatus === 'error' ? 'danger' : 'info'"
                size="small">{{ authStatus }}</el-tag>
        <span class="dt2-auth-msg">{{ authMsg }}</span>
        <p v-if="authStatus === 'needs_login'" class="dt2-hint">
          Open the site in your browser, sign in manually (including any
          Cloudflare challenge), then click Recheck.
        </p>
      </el-card>

      <el-card class="dt2-card">
        <template #header>
          <div class="dt2-card-head">
            <span>Scan open tabs</span>
            <div class="dt2-card-head-actions">
              <el-button type="primary" :loading="scanning" @click="doScan">Scan now</el-button>
            </div>
          </div>
        </template>

        <div v-if="candidates.length === 0 && !scanning" class="dt2-hint">
          <template v-if="totalTabsScanned > 0">
            Scanned {{ totalTabsScanned }} tabs — none matched the source domain.
          </template>
          <template v-else>
            Click <em>Scan now</em> to filter open browser tabs whose host matches
            the configured source domain and whose path is
            <code>/album/&lt;id&gt;/...</code>.
          </template>
        </div>

        <div v-else class="dt2-cand-list">
          <div class="dt2-cand-head">
            <el-checkbox :model-value="allSelected" @change="toggleSelectAll" />
            <span>{{ selectedUrls.size }} / {{ candidates.length }} selected  (from {{ totalTabsScanned }} tabs)</span>
            <div class="dt2-cand-actions">
              <el-button type="danger" :disabled="selectedUrls.size === 0 || jobRunning"
                         @click="execute">Download selected</el-button>
            </div>
          </div>
          <label v-for="c in candidates" :key="c.url" class="dt2-cand-row"
                 :class="{ 'dt2-selected': selectedUrls.has(c.url) }">
            <el-checkbox
              :model-value="selectedUrls.has(c.url)"
              @change="toggleSelected(c.url)" />
            <span class="dt2-cand-aid">id {{ c.album_id || '—' }}</span>
            <span class="dt2-cand-url" :title="c.url">{{ c.url }}</span>
          </label>
        </div>
      </el-card>

      <!-- Captcha handoff — appears when the worker is blocked on user input. -->
      <el-card v-if="captchaPending" class="dt2-card dt2-captcha-card">
        <template #header>
          <div class="dt2-card-head">
            <span>Captcha needed</span>
            <span class="dt2-attempts">attempts left: {{ captchaPending.attempts_left }}</span>
          </div>
        </template>
        <div class="dt2-captcha-body">
          <img :src="'data:image/png;base64,' + captchaPending.image_base64"
               class="dt2-captcha-img" />
          <el-input v-model="captchaAnswer"
                    placeholder="type the result (numbers only)"
                    style="width: 240px"
                    @keyup.enter="submitCaptcha" />
          <el-button type="primary" :loading="captchaSubmitting"
                     :disabled="!captchaAnswer.trim()" @click="submitCaptcha">
            Submit
          </el-button>
        </div>
      </el-card>

      <el-card v-if="jobItems.length > 0" class="dt2-card">
        <template #header>
          <div class="dt2-card-head">
            <span>Progress</span>
            <span class="dt2-progress-summary">
              {{ jobDone }} / {{ jobTotal }}
              <el-tag v-if="jobRunning" type="warning" size="small">running</el-tag>
              <el-tag v-else type="success" size="small">done</el-tag>
            </span>
          </div>
        </template>
        <div class="dt2-job-list">
          <div v-for="item in jobItems" :key="item.url" class="dt2-job-row">
            <div class="dt2-job-line1">
              <el-tag :type="statusTagType(item.status)" size="small" class="dt2-job-status">
                {{ item.status }}
              </el-tag>
              <span class="dt2-job-url" :title="item.url">{{ item.url }}</span>
              <span v-if="item.chapter_label" class="dt2-job-chapter">{{ item.chapter_label }}</span>
              <span v-if="item.filename" class="dt2-job-filename" :title="item.filename">
                → {{ item.filename }}
              </span>
            </div>
            <div v-if="item.status === 'downloading' || (item.status === 'done' && item.bytes_downloaded > 0)"
                 class="dt2-job-line2">
              <el-progress
                :percentage="item.progress_percent"
                :status="item.status === 'done' ? 'success' : undefined"
                :stroke-width="6"
                class="dt2-job-bar" />
              <span class="dt2-job-metric">
                {{ fmtBytes(item.bytes_downloaded) }}
                <template v-if="item.bytes_total > 0"> / {{ fmtBytes(item.bytes_total) }}</template>
              </span>
              <span v-if="item.status === 'downloading' && item.speed_bps > 0" class="dt2-job-metric">
                {{ fmtSpeed(item.speed_bps) }}
              </span>
            </div>
            <div v-if="item.message" class="dt2-job-msg" :title="item.message">{{ item.message }}</div>
          </div>
        </div>
      </el-card>
    </template>
  </div>
</template>

<script lang="ts" src="@/browser_agent/views/DownloadJMView.ts"></script>

<style scoped>
.dt2-root { padding: 24px 32px; box-sizing: border-box; max-width: 1200px; margin: 0 auto; }
.dt2-header { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.dt2-title { margin: 0; font-size: 22px; font-weight: 600; flex: 1; }
.dt2-header-actions { display: flex; gap: 8px; }
.dt2-card { margin-bottom: 20px; }
.dt2-card-head {
  display: flex; align-items: center; justify-content: space-between;
  font-weight: 600;
}
.dt2-card-head-actions { display: flex; gap: 8px; }
.dt2-config-missing { margin-bottom: 20px; }
.dt2-auth-msg { margin-left: 10px; color: #475569; font-size: 13px; }
.dt2-attempts { color: #b45309; font-size: 12px; font-weight: 400; }

.dt2-hint { color: #64748b; font-size: 13px; }
.dt2-hint code {
  background: #f1f5f9; padding: 1px 6px; border-radius: 3px; font-size: 12px;
}

.dt2-captcha-card { background: #fefce8; border-left: 4px solid #eab308; }
.dt2-captcha-body {
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
}
.dt2-captcha-img {
  border: 1px solid #d4d4d8; background: #fff; padding: 4px;
  border-radius: 4px; image-rendering: pixelated; min-width: 150px;
}

.dt2-cand-list { display: flex; flex-direction: column; }
.dt2-cand-head {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 12px; border-bottom: 1px solid #e2e8f0;
  background: #f8fafc; font-size: 13px;
}
.dt2-cand-actions { margin-left: auto; }
.dt2-cand-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-bottom: 1px solid #f1f5f9;
  cursor: pointer; user-select: none;
}
.dt2-cand-row:last-child { border-bottom: none; }
.dt2-cand-row:hover { background: #fafcfe; }
.dt2-selected { background: #eff6ff; }
.dt2-selected:hover { background: #dbeafe; }
.dt2-cand-aid {
  font-family: monospace; font-size: 12px; color: #64748b;
  padding: 2px 6px; background: #f1f5f9; border-radius: 4px;
}
.dt2-cand-url {
  flex: 1; font-family: monospace; font-size: 12px; color: #334155;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.dt2-progress-summary {
  font-weight: 400; font-size: 13px; color: #64748b;
  display: flex; align-items: center; gap: 8px;
}
.dt2-job-list { display: flex; flex-direction: column; gap: 8px; }
.dt2-job-row {
  display: flex; flex-direction: column; gap: 4px;
  padding: 8px 10px; font-size: 12px;
  border-bottom: 1px solid #f1f5f9;
}
.dt2-job-row:last-child { border-bottom: none; }
.dt2-job-line1, .dt2-job-line2 {
  display: flex; align-items: center; gap: 10px;
}
.dt2-job-status { flex: none; }
.dt2-job-url {
  flex: 1; min-width: 0; font-family: monospace; color: #334155;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dt2-job-filename { color: #16a34a; font-family: monospace; font-size: 11px; }
.dt2-job-chapter {
  flex: none; font-size: 11px; color: #7c3aed; background: #ede9fe;
  padding: 2px 6px; border-radius: 4px; font-weight: 600;
}
.dt2-job-msg { color: #64748b; font-size: 11px; padding-left: 6px; }
.dt2-job-bar { flex: 1; margin-right: 8px; }
.dt2-job-metric {
  flex: none; font-family: monospace; font-size: 11px; color: #475569;
  min-width: 90px; text-align: right;
}
</style>
