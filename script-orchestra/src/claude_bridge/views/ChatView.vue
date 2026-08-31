<template>
  <div class="cb-view">
    <div class="cb-header">
      <el-button @click="goBack" circle size="small">
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <h2>Claude Bridge</h2>
      <el-tag v-if="connected" type="success" size="small">Live</el-tag>
      <el-tag v-else type="info" size="small">Offline</el-tag>
      <span class="cb-spacer" />
      <el-button size="small" plain @click="goTerminal">Terminal</el-button>
      <el-button
        v-if="sessionId"
        type="warning" size="small" plain
        @click="interrupt">Interrupt</el-button>
    </div>

    <!-- Token gate: shown when the backend requires a token we don't have -->
    <el-card v-if="needToken" class="cb-setup">
      <div class="cb-setup-row">
        <label>Access token</label>
        <el-input
          v-model="tokenInput" type="password" show-password
          placeholder="Enter bridge token" @keydown.enter="saveToken" />
      </div>
      <p class="cb-hint">This bridge is protected. Enter the token to continue.</p>
      <el-button
        type="primary" :disabled="!tokenInput.trim()"
        style="width: 100%" @click="saveToken">Unlock</el-button>
    </el-card>

    <!-- Setup: choose cwd + model, start a session -->
    <el-card v-else-if="!sessionId" class="cb-setup">
      <div class="cb-setup-row">
        <label>Working directory</label>
        <el-input v-model="cwd" placeholder="/path/to/project" />
      </div>
      <div class="cb-setup-row">
        <label>Model</label>
        <el-select v-model="model" style="width: 100%">
          <el-option
            v-for="m in models" :key="m.id" :label="m.label" :value="m.id" />
        </el-select>
      </div>
      <p v-if="cwdRoots.length" class="cb-hint">
        Allowed roots: {{ cwdRoots.join(', ') }}
      </p>
      <el-button
        type="primary" :loading="starting"
        style="width: 100%" @click="startSession">Start session</el-button>
    </el-card>

    <!-- Conversation -->
    <div v-else ref="scrollBox" class="cb-messages">
      <div
        v-for="(item, idx) in timeline" :key="idx"
        class="cb-item" :class="'cb-' + item.kind">
        <!-- user -->
        <div v-if="item.kind === 'user'" class="cb-bubble cb-user">{{ item.text }}</div>
        <!-- assistant text -->
        <div v-else-if="item.kind === 'assistant'" class="cb-bubble cb-assistant">{{ item.text }}</div>
        <!-- thinking -->
        <el-collapse v-else-if="item.kind === 'thinking'" class="cb-thinking">
          <el-collapse-item title="🤔 Thinking">
            <pre>{{ item.text }}</pre>
          </el-collapse-item>
        </el-collapse>
        <!-- tool use -->
        <div v-else-if="item.kind === 'tool_use'" class="cb-tool">
          <div class="cb-tool-head">🔧 {{ item.name }}</div>
          <pre class="cb-tool-body">{{ item.text }}</pre>
        </div>
        <!-- tool result -->
        <div
          v-else-if="item.kind === 'tool_result'"
          class="cb-tool" :class="{ 'cb-tool-error': item.isError }">
          <div class="cb-tool-head">{{ item.isError ? '❌ result' : '✅ result' }}</div>
          <pre class="cb-tool-body">{{ item.text }}</pre>
        </div>
        <!-- result summary -->
        <div v-else-if="item.kind === 'result'" class="cb-result">
          {{ item.text }}
        </div>
        <!-- error -->
        <div v-else-if="item.kind === 'error'" class="cb-error">⚠️ {{ item.text }}</div>
      </div>

      <!-- permission prompt -->
      <div v-if="pendingPerm" class="cb-perm" :class="{ 'cb-perm-high': pendingPerm.risk === 'high' }">
        <div class="cb-perm-title">
          <el-tag :type="pendingPerm.risk === 'high' ? 'danger' : 'warning'" size="small">
            {{ pendingPerm.risk === 'high' ? 'Risky' : 'Tool' }}
          </el-tag>
          Allow <b>{{ pendingPerm.tool }}</b>?
        </div>
        <div v-if="pendingPerm.summary" class="cb-perm-summary">{{ pendingPerm.summary }}</div>
        <el-collapse class="cb-thinking">
          <el-collapse-item title="Details">
            <pre class="cb-tool-body">{{ prettyInput(pendingPerm.input) }}</pre>
          </el-collapse-item>
        </el-collapse>
        <div class="cb-perm-actions">
          <el-button type="success" size="small" @click="respond('allow')">Allow</el-button>
          <el-button type="danger" size="small" @click="respond('deny')">Deny</el-button>
        </div>
      </div>
    </div>

    <!-- composer -->
    <div v-if="sessionId" class="cb-composer">
      <el-input
        v-model="draft" type="textarea" :autosize="{ minRows: 1, maxRows: 5 }"
        placeholder="Message Claude…" @keydown.enter.exact.prevent="send" />
      <el-button type="primary" :disabled="!draft.trim()" @click="send">Send</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ClaudeBridgeWebSocket, type CbEvent } from '../service/websocket'
import { getConfig, createSession, closeSession, checkAuth, type ModelAlias } from '../service/api'

interface TimelineItem {
  kind: 'user' | 'assistant' | 'thinking' | 'tool_use' | 'tool_result' | 'result' | 'error'
  text: string
  name?: string
  isError?: boolean
}

const router = useRouter()
const ws = new ClaudeBridgeWebSocket()

const connected = ref(false)
const starting = ref(false)
const sessionId = ref('')
const cwd = ref('')
const model = ref('')
const models = ref<ModelAlias[]>([])
const cwdRoots = ref<string[]>([])
const draft = ref('')
const timeline = reactive<TimelineItem[]>([])
const pendingPerm = ref<{ tool: string; input: Record<string, unknown>; requestId: string; risk?: string; summary?: string } | null>(null)
const scrollBox = ref<HTMLElement | null>(null)

// Auth: token stored client-side; the token gate shows when the backend
// requires one but we don't have a (valid) token yet.
const token = ref(localStorage.getItem('cb_token') || '')
const needToken = ref(false)
const tokenInput = ref('')

function goBack() { router.push('/') }
function goTerminal() { router.push('/claude-bridge/terminal') }

function prettyInput(input: unknown): string {
  try { return JSON.stringify(input, null, 2) } catch { return String(input) }
}

async function scrollDown() {
  await nextTick()
  if (scrollBox.value) scrollBox.value.scrollTop = scrollBox.value.scrollHeight
}

function pushItem(item: TimelineItem) {
  timeline.push(item)
  scrollDown()
}

function tokenArg(): string | undefined {
  return token.value || undefined
}

async function init() {
  try {
    const cfg = await getConfig(tokenArg())
    models.value = cfg.models
    model.value = cfg.default_model
    cwd.value = cfg.default_cwd
    cwdRoots.value = cfg.cwd_roots
  } catch (e) {
    // 401 => bad/absent token; re-prompt.
    if (String((e as Error).message).includes('401') || String(e).includes('unauthorized')) {
      needToken.value = true
      return
    }
    ElMessage.error('Failed to load config (is the backend running?)')
    return
  }
  ws.connect(tokenArg())
  ws.onEvent(onEvent)
  setTimeout(() => { connected.value = true }, 300)
}

function saveToken() {
  const t = tokenInput.value.trim()
  if (!t) return
  token.value = t
  localStorage.setItem('cb_token', t)
  needToken.value = false
  tokenInput.value = ''
  init()
}

onMounted(async () => {
  try {
    const { auth_required } = await checkAuth()
    if (auth_required && !token.value) {
      needToken.value = true
      return
    }
  } catch {
    ElMessage.error('Failed to reach backend')
    return
  }
  init()
})

onBeforeUnmount(() => {
  if (sessionId.value) closeSession(sessionId.value, tokenArg()).catch(() => {})
  ws.disconnect()
})

async function startSession() {
  starting.value = true
  try {
    const s = await createSession(cwd.value, model.value, tokenArg())
    sessionId.value = s.session_id
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    starting.value = false
  }
}

function send() {
  const text = draft.value.trim()
  if (!text || !sessionId.value) return
  pushItem({ kind: 'user', text })
  ws.sendMessage(sessionId.value, text)
  draft.value = ''
}

function interrupt() {
  if (sessionId.value) ws.interrupt(sessionId.value)
}

function respond(decision: 'allow' | 'deny') {
  if (!pendingPerm.value || !sessionId.value) return
  ws.respondPermission(sessionId.value, pendingPerm.value.requestId, decision)
  pendingPerm.value = null
}

function onEvent(e: CbEvent) {
  if (e.session_id && sessionId.value && e.session_id !== sessionId.value) return
  switch (e.type) {
    case 'assistant_text': {
      // merge consecutive assistant text into the last assistant bubble
      const last = timeline[timeline.length - 1]
      if (last && last.kind === 'assistant') last.text += e.text || ''
      else pushItem({ kind: 'assistant', text: e.text || '' })
      scrollDown()
      break
    }
    case 'thinking':
      pushItem({ kind: 'thinking', text: e.thinking || '' })
      break
    case 'tool_use':
      pushItem({ kind: 'tool_use', text: prettyInput(e.input), name: e.name })
      break
    case 'tool_result':
      pushItem({ kind: 'tool_result', text: (e.content || '').slice(0, 4000), isError: e.is_error })
      break
    case 'result': {
      const cost = e.total_cost_usd != null ? ` · $${e.total_cost_usd.toFixed(4)}` : ''
      pushItem({ kind: 'result', text: `— done (${e.num_turns ?? '?'} turns${cost}) —` })
      break
    }
    case 'permission_request':
      pendingPerm.value = {
        tool: e.tool || '?',
        input: (e.input as Record<string, unknown>) || {},
        requestId: e.request_id || '',
        risk: e.risk,
        summary: e.summary,
      }
      scrollDown()
      break
    case 'error':
      pushItem({ kind: 'error', text: e.message || 'unknown error' })
      break
    case 'session_status':
      if (e.status === 'ready') connected.value = true
      break
  }
}
</script>

<style scoped>
.cb-view { display: flex; flex-direction: column; height: 100vh; max-width: 900px; margin: 0 auto; }
.cb-header { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--el-border-color); }
.cb-header h2 { margin: 0; font-size: 16px; }
.cb-spacer { flex: 1; }
.cb-setup { margin: 16px 12px; }
.cb-setup-row { margin-bottom: 12px; }
.cb-setup-row label { display: block; font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.cb-hint { font-size: 12px; color: var(--el-text-color-secondary); margin: 4px 0 12px; }
.cb-messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.cb-item { display: flex; }
.cb-user { margin-left: auto; }
.cb-bubble { max-width: 85%; padding: 8px 12px; border-radius: 12px; white-space: pre-wrap; word-break: break-word; }
.cb-user { background: var(--el-color-primary); color: #fff; }
.cb-assistant { background: var(--el-fill-color-light); }
.cb-thinking { width: 100%; }
.cb-thinking pre { white-space: pre-wrap; font-size: 12px; color: var(--el-text-color-secondary); }
.cb-tool { width: 100%; border: 1px solid var(--el-border-color); border-radius: 8px; overflow: hidden; font-size: 12px; }
.cb-tool-error { border-color: var(--el-color-danger); }
.cb-tool-head { padding: 4px 8px; background: var(--el-fill-color); font-weight: 600; }
.cb-tool-body { margin: 0; padding: 8px; white-space: pre-wrap; word-break: break-word; max-height: 240px; overflow: auto; }
.cb-result { width: 100%; text-align: center; font-size: 12px; color: var(--el-text-color-secondary); }
.cb-error { width: 100%; color: var(--el-color-danger); }
.cb-perm { width: 100%; border: 1px solid var(--el-color-warning); border-radius: 8px; padding: 8px; }
.cb-perm-high { border-color: var(--el-color-danger); }
.cb-perm-title { margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
.cb-perm-summary { font-family: monospace; font-size: 12px; background: var(--el-fill-color); padding: 6px 8px; border-radius: 6px; white-space: pre-wrap; word-break: break-word; margin-bottom: 6px; }
.cb-perm-actions { display: flex; gap: 8px; margin-top: 6px; }
.cb-composer { display: flex; gap: 8px; padding: 10px 12px; border-top: 1px solid var(--el-border-color); }
.cb-composer .el-textarea { flex: 1; }
</style>
