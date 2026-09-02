<template>
  <div class="proxy-view">
    <div class="proxy-header">
      <div class="proxy-header-left">
        <el-button @click="goBack" circle>
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h1>Proxy Forward</h1>
        <el-tag :type="status.running ? 'success' : 'info'">
          {{ status.running ? 'Running' : 'Stopped' }}
        </el-tag>
      </div>
      <el-button @click="refreshAll" :loading="loading" plain>
        <el-icon><Refresh /></el-icon>
        Refresh
      </el-button>
    </div>

    <el-card class="proxy-card">
      <template #header>
        <div class="card-header">LAN Network</div>
      </template>
      <div class="network-grid">
        <div>
          <div class="label">Current LAN IP</div>
          <div class="value value-ip">{{ lanIpDisplay }}</div>
        </div>
        <div>
          <div class="label">LAN Access Address</div>
          <div class="value">{{ lanAccessDisplay }}</div>
        </div>
      </div>
      <div class="ip-list" v-if="status.lan_ips.length">
        <el-tag v-for="ip in status.lan_ips" :key="ip" size="small" effect="plain">{{ ip }}</el-tag>
      </div>
      <el-alert
        v-if="!status.lan_ips.length"
        title="No LAN IPv4 detected. Please check Wi-Fi/Ethernet connectivity."
        type="warning"
        :closable="false"
      />
    </el-card>

    <el-card class="proxy-card">
      <template #header>
        <div class="card-header">Forward Configuration</div>
      </template>
      <div class="form-grid">
        <div class="form-item">
          <label>Listen Host</label>
          <el-input v-model="form.listen_host" :disabled="status.running" />
        </div>
        <div class="form-item">
          <label>Listen Port</label>
          <el-input-number v-model="form.listen_port" :min="1" :max="65535" :disabled="status.running" />
        </div>
        <div class="form-item">
          <label>Target Host</label>
          <el-input v-model="form.target_host" :disabled="status.running" />
        </div>
        <div class="form-item">
          <label>Target Port</label>
          <el-input-number v-model="form.target_port" :min="1" :max="65535" :disabled="status.running" />
        </div>
      </div>

      <div class="runtime-grid">
        <div><span class="label">Started At</span><span class="value">{{ status.started_at || '-' }}</span></div>
        <div><span class="label">Active Connections</span><span class="value">{{ status.active_connections }}</span></div>
        <div><span class="label">Total Connections</span><span class="value">{{ status.total_connections }}</span></div>
      </div>

      <el-alert
        v-if="status.last_error"
        class="error-alert"
        :title="status.last_error"
        type="error"
        :closable="false"
      />

      <div class="actions">
        <el-button
          v-if="!status.running"
          type="primary"
          size="large"
          :loading="starting"
          @click="handleStart"
        >
          Start Forwarding
        </el-button>
        <el-button
          v-else
          type="danger"
          size="large"
          :loading="stopping"
          @click="handleStop"
        >
          Stop Forwarding
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Refresh } from '@element-plus/icons-vue'
import {
  getNetwork,
  getStatus,
  startProxy,
  stopProxy,
} from '../service/ProxyForwardService'
import type { ProxyForwardStatus } from '../service/Model'

const router = useRouter()

const status = ref<ProxyForwardStatus>({
  running: false,
  listen_host: '',
  listen_port: null,
  target_host: '',
  target_port: null,
  started_at: null,
  active_connections: 0,
  total_connections: 0,
  lan_ip: null,
  lan_ips: [],
  last_error: null,
})

const form = reactive<{
  listen_host: string
  listen_port: number | null
  target_host: string
  target_port: number | null
}>({
  listen_host: '',
  listen_port: null,
  target_host: '',
  target_port: null,
})

const loading = ref(false)
const starting = ref(false)
const stopping = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | null = null

const lanIpDisplay = computed(() => status.value.lan_ip || status.value.lan_ips[0] || 'Not detected')
const lanAccessDisplay = computed(() => {
  const ip = status.value.lan_ip || status.value.lan_ips[0]
  return ip && status.value.listen_port ? `${ip}:${status.value.listen_port}` : '-'
})

function goBack() {
  router.push('/')
}

function syncFormFromStatus() {
  form.listen_host = status.value.listen_host
  form.listen_port = status.value.listen_port
  form.target_host = status.value.target_host
  form.target_port = status.value.target_port
}

async function refreshStatus() {
  status.value = await getStatus()
  if (!status.value.running) {
    syncFormFromStatus()
  }
}

async function refreshNetworkOnly() {
  const network = await getNetwork()
  status.value.lan_ip = network.lan_ip
  status.value.lan_ips = network.lan_ips || []
}

async function refreshAll() {
  loading.value = true
  try {
    await Promise.all([refreshStatus(), refreshNetworkOnly()])
  } catch (error: any) {
    ElMessage.error(error.message || 'Refresh failed')
  } finally {
    loading.value = false
  }
}

async function handleStart() {
  const listenHost = form.listen_host.trim()
  const targetHost = form.target_host.trim()
  if (!listenHost || !targetHost || form.listen_port == null || form.target_port == null) {
    ElMessage.error('Please configure listen/target host and port first')
    return
  }

  starting.value = true
  try {
    status.value = await startProxy({
      listen_host: listenHost,
      listen_port: form.listen_port,
      target_host: targetHost,
      target_port: form.target_port,
    })
    ElMessage.success('Forwarding started')
  } catch (error: any) {
    ElMessage.error(error.message || 'Start failed')
  } finally {
    starting.value = false
  }
}

async function handleStop() {
  stopping.value = true
  try {
    status.value = await stopProxy()
    syncFormFromStatus()
    ElMessage.success('Forwarding stopped')
  } catch (error: any) {
    ElMessage.error(error.message || 'Stop failed')
  } finally {
    stopping.value = false
  }
}

onMounted(async () => {
  await refreshAll()
  refreshTimer = setInterval(() => {
    refreshAll().catch(() => {})
  }, 5000)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})
</script>

<style scoped>
.proxy-view {
  max-width: 980px;
  margin: 0 auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.proxy-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.proxy-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.proxy-header-left h1 {
  margin: 0;
  font-size: 24px;
}

.proxy-card {
  border-radius: 12px;
}

.card-header {
  font-size: 16px;
  font-weight: 600;
}

.network-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 12px;
}

.label {
  display: block;
  color: #909399;
  font-size: 12px;
  margin-bottom: 6px;
}

.value {
  color: #303133;
  font-weight: 600;
  word-break: break-all;
}

.value-ip {
  font-size: 28px;
  letter-spacing: 0.4px;
}

.ip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.runtime-grid {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.error-alert {
  margin-top: 14px;
}

.actions {
  margin-top: 18px;
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 760px) {
  .network-grid,
  .form-grid,
  .runtime-grid {
    grid-template-columns: 1fr;
  }

  .proxy-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
}
</style>
