<template>
  <div class="cb-term-view">
    <div class="cb-term-header">
      <el-button @click="goBack" circle size="small">
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <h2>Claude Terminal</h2>
      <el-tag v-if="ptyId" type="success" size="small">running</el-tag>
      <span class="cb-spacer" />
      <el-button size="small" @click="goChat">Chat mode</el-button>
    </div>

    <el-card v-if="!ptyId" class="cb-term-setup">
      <div class="cb-setup-row">
        <label>Working directory</label>
        <el-input v-model="cwd" placeholder="/path/to/project" />
      </div>
      <el-button
        type="primary" :loading="starting"
        style="width: 100%" @click="start">Open terminal</el-button>
    </el-card>

    <div v-show="ptyId" ref="termEl" class="cb-term"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { ClaudeBridgeWebSocket, type CbEvent } from '../service/websocket'
import { getConfig, createPty, closePty } from '../service/api'

const router = useRouter()
const ws = new ClaudeBridgeWebSocket()
const token = localStorage.getItem('cb_token') || undefined

const cwd = ref('')
const ptyId = ref('')
const starting = ref(false)
const termEl = ref<HTMLElement | null>(null)

let term: Terminal | null = null
let fit: FitAddon | null = null
let resizeObserver: ResizeObserver | null = null

function goBack() { router.push('/') }
function goChat() { router.push('/claude-bridge') }

onMounted(async () => {
  try {
    const cfg = await getConfig(token)
    cwd.value = cfg.default_cwd
  } catch {
    ElMessage.error('Failed to load config (is the backend running?)')
  }
  ws.connect(token)
  ws.onEvent(onEvent)
})

onBeforeUnmount(() => {
  if (ptyId.value) closePty(ptyId.value, token).catch(() => {})
  resizeObserver?.disconnect()
  term?.dispose()
  ws.disconnect()
})

function onEvent(e: CbEvent) {
  if (e.pty_id && ptyId.value && e.pty_id !== ptyId.value) return
  if (e.type === 'cb_pty_output') {
    term?.write(e.data || '')
  } else if (e.type === 'cb_pty_exit') {
    term?.write('\r\n\x1b[31m[process exited]\x1b[0m\r\n')
  }
}

async function start() {
  starting.value = true
  try {
    const p = await createPty(cwd.value, token)
    ptyId.value = p.pty_id
    await nextTick()
    initTerminal()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    starting.value = false
  }
}

function initTerminal() {
  if (!termEl.value) return
  term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: 'Menlo, Monaco, "Courier New", monospace',
    theme: { background: '#1e1e1e' },
  })
  fit = new FitAddon()
  term.loadAddon(fit)
  term.open(termEl.value)
  fit.fit()

  // pipe keystrokes to the PTY
  term.onData((d) => {
    if (ptyId.value) ws.sendPtyInput(ptyId.value, d)
  })

  // send an initial resize so claude paints at the right size, then track changes
  sendResize()
  resizeObserver = new ResizeObserver(() => {
    fit?.fit()
    sendResize()
  })
  resizeObserver.observe(termEl.value)
  term.focus()
}

function sendResize() {
  if (term && ptyId.value) {
    ws.sendPtyResize(ptyId.value, term.cols, term.rows)
  }
}
</script>

<style scoped>
.cb-term-view { display: flex; flex-direction: column; height: 100vh; }
.cb-term-header { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--el-border-color); }
.cb-term-header h2 { margin: 0; font-size: 16px; }
.cb-spacer { flex: 1; }
.cb-term-setup { margin: 16px 12px; }
.cb-setup-row { margin-bottom: 12px; }
.cb-setup-row label { display: block; font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.cb-term { flex: 1; min-height: 0; padding: 6px; background: #1e1e1e; }
</style>
