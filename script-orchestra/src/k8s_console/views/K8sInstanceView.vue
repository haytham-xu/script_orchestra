<template>
  <div class="ki-root">
    <!-- Top header bar -->
    <div class="ki-header">
      <router-link to="/k8s-console" class="ki-back" title="Back to K8s Console">
        <el-icon><ArrowLeft /></el-icon>
      </router-link>
      <el-tag :type="typeTag" size="small" class="ki-type-tag">{{ typeLabel }}</el-tag>
      <span class="ki-name">{{ instance?.name ?? '…' }}</span>
      <div class="ki-header-spacer" />
      <el-tooltip :content="drawerOpen ? 'Hide info panel' : 'Show info panel'" placement="bottom">
        <el-icon class="ki-drawer-toggle" @click="drawerOpen = !drawerOpen">
          <component :is="drawerOpen ? ArrowRight : Menu" />
        </el-icon>
      </el-tooltip>
    </div>

    <!-- Body: terminal + optional drawer -->
    <div class="ki-body">
      <!-- Info drawer -->
      <transition name="ki-drawer">
        <div v-show="drawerOpen" class="ki-drawer">
          <div class="ki-drawer-section">
            <div class="ki-drawer-label">Note</div>
            <div class="ki-drawer-note">{{ instance?.note || '—' }}</div>
          </div>

          <!-- AKS links -->
          <template v-if="instance?.cluster_type === 'aks'">
            <div class="ki-drawer-section">
              <div class="ki-drawer-label">AKS Details</div>
              <div class="ki-meta-row"><span>Subscription</span><span>{{ instance.subscription_id || '—' }}</span></div>
              <div class="ki-meta-row"><span>Resource Group</span><span>{{ instance.resource_group || '—' }}</span></div>
              <div class="ki-meta-row"><span>Cluster</span><span>{{ instance.cluster_name || '—' }}</span></div>
            </div>
            <div v-if="instance.azure_portal_link" class="ki-drawer-section">
              <a :href="instance.azure_portal_link" target="_blank" class="ki-ext-link">Azure Portal ↗</a>
            </div>
            <div class="ki-drawer-section ki-tip">
              <code>kubelogin convert-kubeconfig -l azurecli</code>
              <span> if kubectl auth fails</span>
            </div>
          </template>

          <!-- Kyma links -->
          <template v-if="instance?.cluster_type === 'kyma'">
            <div class="ki-drawer-section">
              <div class="ki-drawer-label">Kyma / BTP Details</div>
              <div class="ki-meta-row"><span>Global Account</span><span>{{ instance.btp_global_account || '—' }}</span></div>
              <div class="ki-meta-row"><span>Subaccount</span><span>{{ instance.btp_subaccount || '—' }}</span></div>
              <div class="ki-meta-row"><span>Environment</span><span>{{ instance.kyma_environment_name || '—' }}</span></div>
            </div>
            <div v-if="instance.kyma_dashboard_url" class="ki-drawer-section">
              <a :href="instance.kyma_dashboard_url" target="_blank" class="ki-ext-link">Kyma Dashboard ↗</a>
            </div>
          </template>

          <div class="ki-drawer-section">
            <div class="ki-drawer-label">Kubeconfig</div>
            <el-tag :type="instance?.has_kubeconfig ? 'success' : 'warning'" size="small">
              {{ instance?.has_kubeconfig ? 'Configured' : 'Not set' }}
            </el-tag>
          </div>

          <div class="ki-drawer-footer">
            <el-button size="small" @click="goSettings">
              <el-icon><Setting /></el-icon> Settings
            </el-button>
          </div>
        </div>
      </transition>

      <!-- Terminal area -->
      <div class="ki-terminal-area">
        <div v-if="loading" class="ki-loading">
          <el-icon class="ki-loading-icon is-loading"><Loading /></el-icon>
          <span>Connecting…</span>
        </div>
        <div v-else-if="errorMsg" class="ki-error">
          <el-icon><Warning /></el-icon>
          {{ errorMsg }}
          <el-button size="small" style="margin-left:8px" @click="provision">Retry</el-button>
        </div>
        <TerminalPane
          v-else-if="windowId"
          :key="windowId"
          :window-id="windowId"
          :ws-service="ws"
          :initial-scrollback="scrollback"
          @ready="onPaneReady"
        />
      </div>
    </div>

    <!-- Settings drawer -->
    <el-drawer
      v-model="showSettings"
      :title="instance?.name ?? 'Settings'"
      direction="rtl"
      size="480px"
      :destroy-on-close="true"
    >
      <K8sInstanceSettings
        v-if="instance"
        :instance="instance"
        @saved="onSettingsSaved"
      />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Menu, Setting, Loading, Warning } from '@element-plus/icons-vue'
import TerminalPane from '../../web_terminal/components/TerminalPane.vue'
import { WebTerminalWsService } from '../../web_terminal/service/WebTerminalWsService'
import { getScrollback, attachPty } from '../../web_terminal/service/WebTerminalApiService'
import K8sInstanceSettings from '../components/K8sInstanceSettings.vue'
import { listInstances, provisionTerminal } from '../service/K8sConsoleService'
import type { K8sInstance } from '../service/Model'

const route = useRoute()
const router = useRouter()
const instanceId = route.params.id as string

const instance = ref<K8sInstance | null>(null)
const windowId = ref('')
const scrollback = ref('')
const loading = ref(true)
const errorMsg = ref('')
const drawerOpen = ref(true)
const showSettings = ref(false)
const attached = ref(false)

const ws = new WebTerminalWsService()

const typeTag = computed(() => {
  if (instance.value?.cluster_type === 'aks') return 'primary'
  if (instance.value?.cluster_type === 'kyma') return 'success'
  return 'info'
})
const typeLabel = computed(() => (instance.value?.cluster_type ?? '').toUpperCase())

onMounted(async () => {
  ws.connect()
  try {
    const all = await listInstances()
    instance.value = all.find((i) => i.instance_id === instanceId) ?? null
    if (!instance.value) {
      errorMsg.value = 'Cluster not found'
      loading.value = false
      return
    }
    await provision()
  } catch (e: any) {
    errorMsg.value = e.message || 'Failed to load cluster'
    loading.value = false
  }
})

onBeforeUnmount(() => {
  ws.disconnect()
})

async function provision() {
  loading.value = true
  errorMsg.value = ''
  try {
    const result = await provisionTerminal(instanceId)
    windowId.value = result.window_id
    scrollback.value = await getScrollback(result.window_id).catch(() => '')
  } catch (e: any) {
    errorMsg.value = e.message || 'Failed to connect terminal'
  } finally {
    loading.value = false
  }
}

async function onPaneReady(_cols: number, _rows: number) {
  if (attached.value) return
  attached.value = true
  try {
    await attachPty(windowId.value)
  } catch {
    ElMessage.warning('Could not attach PTY')
  }
}

function goSettings() {
  showSettings.value = true
}

function onSettingsSaved(updated: K8sInstance) {
  instance.value = updated
  showSettings.value = false
}
</script>

<style scoped>
.ki-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #1e1e1e;
  overflow: hidden;
}

/* ── header ── */
.ki-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 14px;
  background: #2d2d2d;
  border-bottom: 1px solid #444;
  flex-shrink: 0;
}
.ki-back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: #888;
  border-radius: 4px;
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
}
.ki-back:hover { background: #3c3c3c; color: #fff; }
.ki-type-tag { flex-shrink: 0; }
.ki-name { font-size: 14px; font-weight: 600; color: #e0e0e0; }
.ki-header-spacer { flex: 1; }
.ki-drawer-toggle {
  font-size: 16px;
  color: #888;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: background 0.15s, color 0.15s;
}
.ki-drawer-toggle:hover { background: #3c3c3c; color: #fff; }

/* ── body ── */
.ki-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* ── info drawer ── */
.ki-drawer {
  width: 260px;
  flex-shrink: 0;
  background: #252525;
  border-right: 1px solid #3a3a3a;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 0;
}
.ki-drawer-transition-enter-active,
.ki-drawer-transition-leave-active { transition: width 0.2s ease, opacity 0.2s ease; }
.ki-drawer-transition-enter-from,
.ki-drawer-transition-leave-to { width: 0; opacity: 0; overflow: hidden; }

.ki-drawer-section {
  padding: 10px 0;
  border-bottom: 1px solid #333;
}
.ki-drawer-section:last-child { border-bottom: none; }
.ki-drawer-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #666;
  margin-bottom: 6px;
}
.ki-drawer-note { font-size: 12px; color: #bbb; line-height: 1.5; }
.ki-meta-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  margin-bottom: 3px;
  color: #aaa;
}
.ki-meta-row span:first-child { color: #666; flex-shrink: 0; }
.ki-meta-row span:last-child { text-align: right; font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ki-ext-link { font-size: 12px; color: #4da6ff; text-decoration: none; }
.ki-ext-link:hover { text-decoration: underline; }
.ki-tip { font-size: 11px; color: #888; }
.ki-tip code { background: #333; padding: 1px 4px; border-radius: 3px; font-size: 10px; color: #ddd; }
.ki-drawer-footer { margin-top: auto; padding-top: 12px; }

/* ── terminal ── */
.ki-terminal-area {
  flex: 1;
  min-width: 0;
  min-height: 0;
  position: relative;
  padding-bottom: 8px;
}
.ki-loading, .ki-error {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #666;
  font-size: 14px;
  gap: 8px;
}
.ki-loading-icon { font-size: 20px; }
</style>
