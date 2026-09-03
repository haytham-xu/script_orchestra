<template>
  <div class="relay-view">
    <div class="relay-header">
      <div class="relay-header-left">
        <el-button @click="goBack" circle>
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1>Relay Proxy</h1>
        <el-tag :type="status.running ? 'success' : 'info'">{{ status.running ? 'Running' : 'Stopped' }}</el-tag>
      </div>
      <div class="relay-header-actions">
        <el-button :loading="probing" plain @click="handleProbe">
          Probe
        </el-button>
        <el-button :loading="loading" plain @click="refreshAll">
          <el-icon><Refresh /></el-icon>
          Refresh
        </el-button>
      </div>
    </div>

    <el-card class="relay-card">
      <template #header>
        <div class="card-title">LAN Network</div>
      </template>
      <div class="network-grid">
        <div>
          <span class="label">Current LAN IP</span>
          <div class="value value-ip">{{ status.lan_ip || status.lan_ips[0] || '-' }}</div>
        </div>
        <div>
          <span class="label">Mode</span>
          <div class="value">{{ settings.mode }}</div>
        </div>
      </div>
      <div v-if="status.lan_ips.length" class="ip-list">
        <el-tag v-for="item in status.lan_ips" :key="item" size="small" effect="plain">{{ item }}</el-tag>
      </div>
    </el-card>

    <el-card class="relay-card">
      <template #header>
        <div class="card-title">Listeners</div>
      </template>

      <div class="section-title">HTTP Proxy Listener</div>
      <div class="form-grid">
        <div class="form-item">
          <label>Enabled</label>
          <el-switch v-model="settings.listeners.http.enabled" :disabled="status.running" />
        </div>
        <div class="form-item">
          <label>Bind Host</label>
          <el-input v-model="settings.listeners.http.bind_host" :disabled="status.running" />
        </div>
        <div class="form-item">
          <label>Bind Port</label>
          <el-input-number v-model="settings.listeners.http.bind_port" :min="1" :max="65535" :disabled="status.running" />
        </div>
      </div>

      <div class="section-title">SOCKS5 Listener</div>
      <div class="form-grid">
        <div class="form-item">
          <label>Enabled</label>
          <el-switch v-model="settings.listeners.socks5.enabled" :disabled="status.running" />
        </div>
        <div class="form-item">
          <label>Bind Host</label>
          <el-input v-model="settings.listeners.socks5.bind_host" :disabled="status.running" />
        </div>
        <div class="form-item">
          <label>Bind Port</label>
          <el-input-number v-model="settings.listeners.socks5.bind_port" :min="1" :max="65535" :disabled="status.running" />
        </div>
      </div>

      <div class="section-title">Upstream Route</div>
      <div class="form-grid">
        <div class="form-item">
          <label>Mode</label>
          <el-select v-model="settings.mode" :disabled="status.running">
            <el-option label="upstream_proxy" value="upstream_proxy" />
            <el-option label="direct" value="direct" />
          </el-select>
        </div>
        <div class="form-item">
          <label>Upstream Protocol</label>
          <el-select v-model="settings.upstream.protocol" :disabled="status.running || settings.mode !== 'upstream_proxy'">
            <el-option label="http" value="http" />
            <el-option label="socks5" value="socks5" />
          </el-select>
        </div>
        <div class="form-item">
          <label>Upstream Host</label>
          <el-input v-model="settings.upstream.host" :disabled="status.running || settings.mode !== 'upstream_proxy'" />
        </div>
        <div class="form-item">
          <label>Upstream Port</label>
          <el-input-number v-model="settings.upstream.port" :min="1" :max="65535" :disabled="status.running || settings.mode !== 'upstream_proxy'" />
        </div>
      </div>

      <div class="section-title">Access Policy</div>
      <div class="form-item">
        <label>Allowed Client CIDRs (comma separated, empty means allow all)</label>
        <el-input
          v-model="allowedCidrsInput"
          type="textarea"
          :rows="2"
          :disabled="status.running"
          placeholder="comma-separated CIDR values"
        />
      </div>

      <div class="section-title">Limits</div>
      <div class="form-grid">
        <div class="form-item">
          <label>Max Connections</label>
          <el-input-number v-model="settings.limits.max_connections" :min="1" :disabled="status.running" />
        </div>
        <div class="form-item">
          <label>Connect Timeout (s)</label>
          <el-input-number v-model="settings.limits.connect_timeout_seconds" :min="1" :disabled="status.running" />
        </div>
        <div class="form-item">
          <label>Idle Timeout (s)</label>
          <el-input-number v-model="settings.limits.idle_timeout_seconds" :min="1" :disabled="status.running" />
        </div>
        <div class="form-item">
          <label>Max Header Bytes</label>
          <el-input-number v-model="settings.limits.max_header_bytes" :min="1024" :step="1024" :disabled="status.running" />
        </div>
        <div class="form-item">
          <label>History Limit</label>
          <el-input-number v-model="settings.limits.history_limit" :min="100" :disabled="status.running" />
        </div>
      </div>

      <div class="actions">
        <el-button :disabled="status.running" @click="handleSaveSettings" :loading="saving">Save Settings</el-button>
        <el-button type="primary" v-if="!status.running" @click="handleStart" :loading="starting">Start Relay</el-button>
        <el-button type="danger" v-else @click="handleStop" :loading="stopping">Stop Relay</el-button>
      </div>
    </el-card>

    <el-card class="relay-card">
      <template #header>
        <div class="card-title">Runtime</div>
      </template>
      <div class="runtime-grid">
        <div><span class="label">Started At</span><span class="value">{{ status.started_at || '-' }}</span></div>
        <div><span class="label">Active Connections</span><span class="value">{{ status.active_connections }}</span></div>
        <div><span class="label">Total Connections</span><span class="value">{{ status.total_connections }}</span></div>
      </div>
      <div class="runtime-grid">
        <div><span class="label">History Count</span><span class="value">{{ status.history_count }}</span></div>
        <div><span class="label">HTTP Listener</span><span class="value">{{ formatRuntimeListener('http') }}</span></div>
        <div><span class="label">SOCKS5 Listener</span><span class="value">{{ formatRuntimeListener('socks5') }}</span></div>
      </div>
      <el-alert v-if="status.last_error" :title="status.last_error" type="error" :closable="false" class="runtime-error" />
    </el-card>

    <el-card class="relay-card">
      <template #header>
        <div class="diagnostics-header">
          <span class="card-title">Diagnostics Probe</span>
          <el-tag v-if="probeResult" :type="probeResult.ok ? 'success' : 'danger'" size="small">
            {{ probeResult.ok ? 'Pass' : 'Fail' }}
          </el-tag>
        </div>
      </template>

      <div class="diagnostics-summary">
        <div><span class="label">Last Probe</span><span class="value">{{ probeResult?.timestamp || '-' }}</span></div>
        <div><span class="label">Effective Mode</span><span class="value">{{ probeResult?.mode || '-' }}</span></div>
      </div>

      <div v-if="!probeResult || !probeResult.checks.length" class="history-empty">
        Run Probe to validate listener binding and upstream connectivity.
      </div>

      <div v-else class="probe-list">
        <div v-for="check in probeResult.checks" :key="check.name" class="probe-item">
          <div class="probe-title-row">
            <span class="probe-name">{{ check.name }}</span>
            <el-tag size="small" :type="check.skipped ? 'info' : check.ok ? 'success' : 'danger'">
              {{ check.skipped ? 'Skipped' : check.ok ? 'OK' : 'Failed' }}
            </el-tag>
          </div>
          <div class="probe-detail">{{ check.detail }}</div>
        </div>
      </div>
    </el-card>

    <el-card class="relay-card">
      <template #header>
        <div class="history-header">
          <span class="card-title">History ({{ historyEntries.length }})</span>
          <el-button plain size="small" :disabled="!historyEntries.length" @click="handleClearHistory">Clear</el-button>
        </div>
      </template>
      <div v-if="!historyEntries.length" class="history-empty">No history entries.</div>
      <div v-else class="history-list">
        <div v-for="entry in historyEntries" :key="entry.id" class="history-item">
          <span class="history-time">{{ entry.timestamp }}</span>
          <el-tag size="small" :type="entry.level === 'error' ? 'danger' : entry.level === 'warning' ? 'warning' : 'info'">{{ entry.event }}</el-tag>
          <span class="history-message" :class="{ 'history-message-error': entry.level === 'error' }">{{ entry.message }}</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  clearHistory,
  getHistory,
  runDiagnosticsProbe,
  getSettings,
  getStatus,
  startRelay,
  stopRelay,
  updateSettings,
} from '../service/RelayProxyService'
import type {
  RelayProxyHistoryEntry,
  RelayProxyProbeResult,
  RelayProxySettings,
  RelayProxyStatus,
} from '../service/Model'

const router = useRouter()

const status = ref<RelayProxyStatus>({
  running: false,
  mode: 'upstream_proxy',
  listeners_runtime: {},
  active_connections: 0,
  total_connections: 0,
  started_at: null,
  last_error: null,
  history_count: 0,
  lan_ip: null,
  lan_ips: [],
})

const settings = reactive<RelayProxySettings>({
  mode: 'upstream_proxy',
  listeners: {
    http: { enabled: false, bind_host: '', bind_port: null },
    socks5: { enabled: false, bind_host: '', bind_port: null },
  },
  upstream: {
    protocol: 'http',
    host: '',
    port: null,
  },
  access: {
    allowed_client_cidrs: [],
  },
  limits: {
    max_connections: 256,
    connect_timeout_seconds: 15,
    idle_timeout_seconds: 300,
    max_header_bytes: 65536,
    history_limit: 2000,
  },
})

const allowedCidrsInput = ref('')
const historyEntries = ref<RelayProxyHistoryEntry[]>([])
const probeResult = ref<RelayProxyProbeResult | null>(null)

const loading = ref(false)
const saving = ref(false)
const starting = ref(false)
const stopping = ref(false)
const probing = ref(false)

function getErrorMessage(error: any, fallback: string): string {
  return error?.response?.data?.error || error?.response?.data?.message || error?.message || fallback
}

function syncSettings(incoming: RelayProxySettings): void {
  settings.mode = incoming.mode

  settings.listeners.http.enabled = incoming.listeners.http.enabled
  settings.listeners.http.bind_host = incoming.listeners.http.bind_host
  settings.listeners.http.bind_port = incoming.listeners.http.bind_port

  settings.listeners.socks5.enabled = incoming.listeners.socks5.enabled
  settings.listeners.socks5.bind_host = incoming.listeners.socks5.bind_host
  settings.listeners.socks5.bind_port = incoming.listeners.socks5.bind_port

  settings.upstream.protocol = incoming.upstream.protocol
  settings.upstream.host = incoming.upstream.host
  settings.upstream.port = incoming.upstream.port

  settings.access.allowed_client_cidrs = [...incoming.access.allowed_client_cidrs]
  allowedCidrsInput.value = incoming.access.allowed_client_cidrs.join(', ')

  settings.limits.max_connections = incoming.limits.max_connections
  settings.limits.connect_timeout_seconds = incoming.limits.connect_timeout_seconds
  settings.limits.idle_timeout_seconds = incoming.limits.idle_timeout_seconds
  settings.limits.max_header_bytes = incoming.limits.max_header_bytes
  settings.limits.history_limit = incoming.limits.history_limit
}

function buildSettingsPayload(): RelayProxySettings {
  const cidrs = allowedCidrsInput.value
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)

  return {
    mode: settings.mode,
    listeners: {
      http: {
        enabled: settings.listeners.http.enabled,
        bind_host: settings.listeners.http.bind_host.trim(),
        bind_port: settings.listeners.http.bind_port,
      },
      socks5: {
        enabled: settings.listeners.socks5.enabled,
        bind_host: settings.listeners.socks5.bind_host.trim(),
        bind_port: settings.listeners.socks5.bind_port,
      },
    },
    upstream: {
      protocol: settings.upstream.protocol,
      host: settings.upstream.host.trim(),
      port: settings.upstream.port,
    },
    access: {
      allowed_client_cidrs: cidrs,
    },
    limits: {
      max_connections: settings.limits.max_connections,
      connect_timeout_seconds: settings.limits.connect_timeout_seconds,
      idle_timeout_seconds: settings.limits.idle_timeout_seconds,
      max_header_bytes: settings.limits.max_header_bytes,
      history_limit: settings.limits.history_limit,
    },
  }
}

function formatRuntimeListener(key: string): string {
  const item = status.value.listeners_runtime[key]
  if (!item) {
    return 'not running'
  }
  if (!item.bind_host || item.bind_port == null) {
    return 'running'
  }
  return `${item.bind_host}:${item.bind_port}`
}

async function refreshAll(): Promise<void> {
  loading.value = true
  try {
    const [s, cfg, hist] = await Promise.all([getStatus(), getSettings(), getHistory(300)])
    status.value = s
    syncSettings(cfg)
    historyEntries.value = hist
  } catch (error: any) {
    ElMessage.error(getErrorMessage(error, 'Failed to refresh relay state'))
  } finally {
    loading.value = false
  }
}

async function handleSaveSettings(): Promise<void> {
  saving.value = true
  try {
    const saved = await updateSettings(buildSettingsPayload())
    syncSettings(saved)
    ElMessage.success('Settings saved')
  } catch (error: any) {
    ElMessage.error(getErrorMessage(error, 'Failed to save settings'))
  } finally {
    saving.value = false
  }
}

async function handleStart(): Promise<void> {
  starting.value = true
  try {
    await updateSettings(buildSettingsPayload())
    status.value = await startRelay()
    historyEntries.value = await getHistory(300)
    ElMessage.success('Relay started')
  } catch (error: any) {
    ElMessage.error(getErrorMessage(error, 'Failed to start relay'))
  } finally {
    starting.value = false
  }
}

async function handleStop(): Promise<void> {
  stopping.value = true
  try {
    status.value = await stopRelay()
    historyEntries.value = await getHistory(300)
    ElMessage.success('Relay stopped')
  } catch (error: any) {
    ElMessage.error(getErrorMessage(error, 'Failed to stop relay'))
  } finally {
    stopping.value = false
  }
}

async function handleClearHistory(): Promise<void> {
  try {
    await clearHistory()
    historyEntries.value = await getHistory(300)
    status.value.history_count = historyEntries.value.length
    ElMessage.success('History cleared')
  } catch (error: any) {
    ElMessage.error(getErrorMessage(error, 'Failed to clear history'))
  }
}

async function handleProbe(): Promise<void> {
  probing.value = true
  try {
    const payload = buildSettingsPayload()
    probeResult.value = await runDiagnosticsProbe(payload)
    if (probeResult.value.ok) {
      ElMessage.success('Probe passed')
    } else {
      ElMessage.warning('Probe found issues')
    }
  } catch (error: any) {
    ElMessage.error(getErrorMessage(error, 'Probe failed'))
  } finally {
    probing.value = false
  }
}

function goBack(): void {
  router.push('/')
}

onMounted(async () => {
  await refreshAll()
})
</script>

<style scoped>
.relay-view {
  max-width: 1080px;
  margin: 0 auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.relay-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.relay-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.relay-header-left h1 {
  margin: 0;
  font-size: 24px;
}

.relay-header-actions {
  display: flex;
  gap: 8px;
}

.relay-card {
  border-radius: 12px;
}

.card-title {
  font-weight: 600;
  font-size: 16px;
}

.section-title {
  margin-top: 8px;
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 600;
  color: #606266;
}

.network-grid,
.runtime-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 10px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-item > label,
.label {
  color: #909399;
  font-size: 12px;
}

.value {
  color: #303133;
  font-size: 14px;
  font-weight: 600;
  word-break: break-all;
}

.value-ip {
  font-size: 26px;
}

.actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.ip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.runtime-error {
  margin-top: 12px;
}

.diagnostics-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.diagnostics-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 10px;
}

.probe-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.probe-item {
  padding: 10px;
  border-radius: 8px;
  background: #f8fafc;
}

.probe-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.probe-name {
  font-family: Menlo, Monaco, Consolas, 'Courier New', monospace;
  font-size: 12px;
  color: #475467;
}

.probe-detail {
  margin-top: 6px;
  font-size: 13px;
  color: #344054;
  word-break: break-word;
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.history-empty {
  color: #909399;
}

.history-list {
  max-height: 320px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.history-item {
  display: grid;
  grid-template-columns: 190px 100px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  background: #f8fafc;
  padding: 8px 10px;
  border-radius: 8px;
}

.history-time {
  font-size: 12px;
  color: #606266;
  font-family: Menlo, Monaco, Consolas, 'Courier New', monospace;
}

.history-message {
  font-size: 13px;
  color: #303133;
  word-break: break-word;
}

.history-message-error {
  color: #b42318;
}

@media (max-width: 900px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .network-grid,
  .runtime-grid,
  .diagnostics-summary {
    grid-template-columns: 1fr;
  }

  .history-item {
    grid-template-columns: 1fr;
  }

  .relay-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
}
</style>
