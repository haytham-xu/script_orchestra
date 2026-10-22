<template>
  <div class="wt-root">
    <!-- Top bar: back button + tabs -->
    <div class="wt-tabbar">
      <router-link to="/" class="wt-back" title="Back to dashboard">
        <el-icon><ArrowLeft /></el-icon>
      </router-link>
      <div class="wt-tabbar-divider" />
      <div
        v-for="win in windows"
        :key="win.window_id"
        class="wt-tab"
        :class="{ active: win.window_id === activeId }"
        @click="selectWindow(win.window_id)"
      >
        <span class="wt-tab-title">{{ win.title }}</span>
        <el-icon
          class="wt-tab-close"
          @click.stop="confirmDelete(win.window_id)"
        ><Close /></el-icon>
      </div>

      <!-- New tab button -->
      <el-popover
        v-model:visible="newPopoverVisible"
        placement="bottom-start"
        :width="320"
        trigger="click"
      >
        <template #reference>
          <div class="wt-tab wt-tab-new" title="New terminal">+</div>
        </template>
        <div class="wt-new-form">
          <div class="wt-new-row">
            <label>Title</label>
            <el-input v-model="newTitle" placeholder="Terminal" size="small" />
          </div>
          <div class="wt-new-row">
            <label>Working directory</label>
            <el-input v-model="newCwd" placeholder="~" size="small" />
          </div>
          <el-button
            type="primary"
            size="small"
            style="width:100%;margin-top:8px"
            :loading="creating"
            @click="createWindow"
          >Open</el-button>
        </div>
      </el-popover>
    </div>

    <!-- Terminal area -->
    <div class="wt-body">
      <div v-if="windows.length === 0" class="wt-empty">
        <p>No terminals open. Click <strong>+</strong> to create one.</p>
      </div>

      <template v-for="win in windows" :key="win.window_id">
        <div
          v-show="win.window_id === activeId"
          class="wt-pane-wrapper"
        >
          <TerminalPane
            v-if="mountedIds.has(win.window_id)"
            :window-id="win.window_id"
            :ws-service="ws"
            :initial-scrollback="scrollbacks[win.window_id] ?? ''"
            @ready="(cols, rows) => onPaneReady(win.window_id, cols, rows)"
          />
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import TerminalPane from '../components/TerminalPane.vue'
import { WebTerminalWsService } from '../service/WebTerminalWsService'
import {
  listWindows,
  createWindow as apiCreateWindow,
  deleteWindow as apiDeleteWindow,
  getScrollback,
  attachPty,
} from '../service/WebTerminalApiService'
import type { TerminalWindow } from '../service/Model'

const ws = new WebTerminalWsService()
const windows = ref<TerminalWindow[]>([])
const activeId = ref('')
const mountedIds = ref<Set<string>>(new Set())
const scrollbacks = ref<Record<string, string>>({})
// Tracks which windows already have a PTY attached this session
const attachedIds = ref<Set<string>>(new Set())
const newPopoverVisible = ref(false)
const newTitle = ref('')
const newCwd = ref('~')
const creating = ref(false)

// ---- lifecycle ----

onMounted(async () => {
  ws.connect()
  await loadWindows()
  if (windows.value.length > 0) {
    await selectWindow(windows.value[0].window_id)
  }
})

onBeforeUnmount(() => {
  ws.disconnect()
})

// ---- window management ----

async function loadWindows() {
  try {
    windows.value = await listWindows()
  } catch (e) {
    ElMessage.error('Failed to load terminals')
  }
}

async function selectWindow(id: string) {
  activeId.value = id
  localStorage.setItem('wt_active', id)

  if (!mountedIds.value.has(id)) {
    const sb = await getScrollback(id).catch(() => '')
    scrollbacks.value[id] = sb
    // Mount the pane — PTY will be attached once TerminalPane emits @ready
    mountedIds.value = new Set([...mountedIds.value, id])
  }
}

// Called by TerminalPane after it has fitted to its real dimensions.
// Only attach a fresh PTY on first mount; re-selecting an already-attached
// window just re-uses the running shell.
async function onPaneReady(id: string, _cols: number, _rows: number) {
  if (attachedIds.value.has(id)) return
  attachedIds.value = new Set([...attachedIds.value, id])
  try {
    await attachPty(id)
  } catch {
    ElMessage.warning('Could not attach PTY')
  }
}

async function createWindow() {
  creating.value = true
  try {
    const title = newTitle.value.trim() || 'Terminal'
    const cwd = newCwd.value.trim() || '~'
    const win = await apiCreateWindow(title, cwd)
    windows.value.unshift(win)
    newPopoverVisible.value = false
    newTitle.value = ''
    newCwd.value = '~'
    await selectWindow(win.window_id)
  } catch (e: any) {
    ElMessage.error(e.message || 'Failed to create terminal')
  } finally {
    creating.value = false
  }
}

async function confirmDelete(id: string) {
  const win = windows.value.find((w) => w.window_id === id)
  try {
    await ElMessageBox.confirm(
      `Delete terminal "${win?.title ?? id}"? History will be lost.`,
      'Confirm',
      { confirmButtonText: 'Delete', cancelButtonText: 'Cancel', type: 'warning' },
    )
  } catch {
    return
  }
  await deleteWindow(id)
}

async function deleteWindow(id: string) {
  try {
    await apiDeleteWindow(id)
    windows.value = windows.value.filter((w) => w.window_id !== id)
    mountedIds.value.delete(id)
    attachedIds.value.delete(id)
    delete scrollbacks.value[id]

    if (activeId.value === id) {
      activeId.value = windows.value[0]?.window_id ?? ''
      if (activeId.value && !mountedIds.value.has(activeId.value)) {
        await selectWindow(activeId.value)
      }
    }
  } catch (e) {
    ElMessage.error('Failed to delete terminal')
  }
}
</script>

<style scoped>
.wt-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #1e1e1e;
  font-family: sans-serif;
}

/* ---- tab bar ---- */
.wt-tabbar {
  display: flex;
  align-items: center;
  background: #2d2d2d;
  border-bottom: 1px solid #444;
  overflow-x: auto;
  flex-shrink: 0;
  gap: 1px;
  padding: 4px 4px 0;
  scrollbar-width: none;
}
.wt-tabbar::-webkit-scrollbar { display: none; }

.wt-back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 28px;
  color: #888;
  flex-shrink: 0;
  border-radius: 4px;
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
  margin-bottom: 4px;
}
.wt-back:hover { background: #3c3c3c; color: #fff; }
.wt-back .el-icon { font-size: 14px; }

.wt-tabbar-divider {
  width: 1px;
  height: 18px;
  background: #444;
  flex-shrink: 0;
  margin: 0 4px 4px;
}

.wt-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  font-size: 12px;
  color: #aaa;
  cursor: pointer;
  border-radius: 4px 4px 0 0;
  background: #333;
  white-space: nowrap;
  user-select: none;
  transition: background 0.15s, color 0.15s;
  min-width: 80px;
  max-width: 160px;
}
.wt-tab:hover { background: #3c3c3c; color: #ccc; }
.wt-tab.active { background: #1e1e1e; color: #fff; border-top: 2px solid #4da6ff; }
.wt-tab-title { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.wt-tab-close {
  opacity: 0;
  font-size: 11px;
  border-radius: 2px;
  padding: 1px;
  flex-shrink: 0;
  transition: opacity 0.15s;
}
.wt-tab:hover .wt-tab-close,
.wt-tab.active .wt-tab-close { opacity: 0.7; }
.wt-tab-close:hover { opacity: 1 !important; color: #ff6b6b; }

.wt-tab-new {
  font-size: 18px;
  font-weight: 300;
  min-width: 32px;
  max-width: 32px;
  padding: 2px 8px;
  justify-content: center;
  color: #888;
  background: transparent;
}
.wt-tab-new:hover { background: #3c3c3c; color: #fff; }

/* ---- new terminal form ---- */
.wt-new-form { padding: 4px 0; }
.wt-new-row { margin-bottom: 8px; }
.wt-new-row label {
  display: block;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}

/* ---- terminal body ---- */
.wt-body {
  flex: 1;
  min-height: 0;
  position: relative;
  padding-bottom: 8px;
}
.wt-pane-wrapper {
  position: absolute;
  inset: 0;
}
.wt-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #666;
  font-size: 14px;
}
</style>
