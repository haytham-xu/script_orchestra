<template>
  <div class="k8s-root">
    <!-- Top bar -->
    <div class="k8s-topbar">
      <router-link to="/" class="k8s-back" title="Back to dashboard">
        <el-icon><ArrowLeft /></el-icon>
      </router-link>
      <span class="k8s-title">K8s Console</span>
      <div class="k8s-topbar-spacer" />
      <el-button size="small" :loading="refreshing" @click="refreshStatus">
        <el-icon><Refresh /></el-icon> Refresh Status
      </el-button>
    </div>

    <!-- Status panel -->
    <div class="k8s-status-panel">
      <div class="k8s-status-item">
        <span class="k8s-status-label">Public IP</span>
        <span class="k8s-status-value" :class="{ loading: refreshing }">
          {{ ipDisplay }}
        </span>
      </div>
      <div class="k8s-status-divider" />
      <div class="k8s-status-item">
        <span class="k8s-status-label">Azure Account</span>
        <span class="k8s-status-value" :class="azStatusClass">
          {{ azDisplay }}
        </span>
      </div>
      <div v-if="azStatus?.logged_in" class="k8s-status-item">
        <span class="k8s-status-label">Subscription</span>
        <span class="k8s-status-value">{{ azStatus.subscription_name }}</span>
      </div>
      <div v-if="statusUpdatedAt" class="k8s-status-item k8s-status-ts">
        <span class="k8s-status-label">Last refresh</span>
        <span class="k8s-status-value muted">{{ statusUpdatedAt }}</span>
      </div>
    </div>

    <!-- Instance list -->
    <div class="k8s-instances-header">
      <span class="k8s-instances-title">Clusters</span>
      <el-button type="primary" size="small" @click="showCreateDialog = true">
        + New Cluster
      </el-button>
    </div>

    <div v-if="instances.length === 0" class="k8s-empty">
      No clusters yet. Click <strong>+ New Cluster</strong> to add one.
    </div>

    <div class="k8s-instance-grid">
      <div
        v-for="inst in instances"
        :key="inst.instance_id"
        class="k8s-card"
        @click="openInstance(inst)"
      >
        <div class="k8s-card-header">
          <el-tag :type="typeTag(inst.cluster_type)" size="small" class="k8s-type-tag">
            {{ inst.cluster_type.toUpperCase() }}
          </el-tag>
          <span class="k8s-card-name">{{ inst.name }}</span>
          <div class="k8s-card-actions" @click.stop>
            <el-icon class="k8s-card-action-btn" title="Settings" @click="openSettings(inst)">
              <Setting />
            </el-icon>
            <el-icon class="k8s-card-action-btn danger" title="Delete" @click="confirmDelete(inst)">
              <Delete />
            </el-icon>
          </div>
        </div>

        <div v-if="inst.note" class="k8s-card-note">{{ inst.note }}</div>

        <div class="k8s-card-meta">
          <span v-if="!inst.has_kubeconfig" class="k8s-no-kubeconfig">No kubeconfig</span>
          <span v-if="inst.cluster_type === 'aks' && inst.subscription_id" class="k8s-meta-chip">
            {{ inst.subscription_id.slice(0, 8) }}…
          </span>
          <span v-if="inst.cluster_type === 'kyma' && inst.kyma_environment_name" class="k8s-meta-chip">
            {{ inst.kyma_environment_name }}
          </span>
        </div>

        <div class="k8s-card-links" @click.stop>
          <a
            v-if="inst.cluster_type === 'aks' && inst.azure_portal_link"
            :href="inst.azure_portal_link"
            target="_blank"
            class="k8s-ext-link"
          >Azure Portal ↗</a>
          <a
            v-if="inst.cluster_type === 'kyma' && inst.kyma_dashboard_url"
            :href="inst.kyma_dashboard_url"
            target="_blank"
            class="k8s-ext-link"
          >Kyma Dashboard ↗</a>
        </div>
      </div>
    </div>

    <!-- Create dialog -->
    <el-dialog v-model="showCreateDialog" title="New Cluster" width="480px" :close-on-click-modal="false">
      <el-form :model="createForm" label-width="140px" size="small">
        <el-form-item label="Name" required>
          <el-input v-model="createForm.name" placeholder="e.g. Production AKS" />
        </el-form-item>
        <el-form-item label="Type" required>
          <el-select v-model="createForm.cluster_type" style="width:100%">
            <el-option label="AKS (Azure)" value="aks" />
            <el-option label="Kyma (SAP BTP)" value="kyma" />
            <el-option label="Generic K8s" value="generic" />
          </el-select>
        </el-form-item>
        <el-form-item label="Note">
          <el-input v-model="createForm.note" type="textarea" :rows="2" />
        </el-form-item>

        <!-- AKS fields -->
        <template v-if="createForm.cluster_type === 'aks'">
          <el-divider content-position="left"><small>AKS Details</small></el-divider>
          <el-form-item label="Subscription ID">
            <el-input v-model="createForm.subscription_id" placeholder="xxxxxxxx-xxxx-..." />
          </el-form-item>
          <el-form-item label="Resource Group">
            <el-input v-model="createForm.resource_group" />
          </el-form-item>
          <el-form-item label="Cluster Name">
            <el-input v-model="createForm.cluster_name" />
          </el-form-item>
          <el-form-item label="Azure Portal Link">
            <el-input v-model="createForm.azure_portal_link" placeholder="https://portal.azure.com/..." />
          </el-form-item>
        </template>

        <!-- Kyma fields -->
        <template v-if="createForm.cluster_type === 'kyma'">
          <el-divider content-position="left"><small>Kyma / BTP Details</small></el-divider>
          <el-form-item label="Kyma Dashboard">
            <el-input v-model="createForm.kyma_dashboard_url" placeholder="https://dashboard.kyma.cloud.sap/..." />
          </el-form-item>
          <el-form-item label="Global Account">
            <el-input v-model="createForm.btp_global_account" />
          </el-form-item>
          <el-form-item label="Subaccount">
            <el-input v-model="createForm.btp_subaccount" />
          </el-form-item>
          <el-form-item label="Environment Name">
            <el-input v-model="createForm.kyma_environment_name" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="creating" @click="doCreate">Create</el-button>
      </template>
    </el-dialog>

    <!-- Settings drawer -->
    <el-drawer
      v-model="showSettings"
      :title="settingsInst?.name ?? 'Settings'"
      direction="rtl"
      size="480px"
      :destroy-on-close="true"
    >
      <K8sInstanceSettings
        v-if="settingsInst"
        :instance="settingsInst"
        @saved="onSettingsSaved"
      />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Refresh, Setting, Delete } from '@element-plus/icons-vue'
import K8sInstanceSettings from '../components/K8sInstanceSettings.vue'
import {
  listInstances,
  createInstance,
  deleteInstance,
  getAzStatus,
  getPublicIp,
} from '../service/K8sConsoleService'
import type { K8sInstance, AzStatus, CreateInstancePayload } from '../service/Model'

const router = useRouter()

const instances = ref<K8sInstance[]>([])
const azStatus = ref<AzStatus | null>(null)
const publicIp = ref<string | null>(null)
const refreshing = ref(false)
const statusUpdatedAt = ref('')
const showCreateDialog = ref(false)
const creating = ref(false)
const showSettings = ref(false)
const settingsInst = ref<K8sInstance | null>(null)

const emptyCreateForm = (): CreateInstancePayload => ({
  name: '',
  cluster_type: 'aks',
  note: '',
  subscription_id: '',
  resource_group: '',
  cluster_name: '',
  azure_portal_link: '',
  kyma_dashboard_url: '',
  btp_global_account: '',
  btp_subaccount: '',
  kyma_environment_name: '',
})
const createForm = ref<CreateInstancePayload>(emptyCreateForm())

const ipDisplay = computed(() => {
  if (refreshing.value) return '…'
  return publicIp.value ?? 'unavailable'
})

const azDisplay = computed(() => {
  if (refreshing.value) return '…'
  if (!azStatus.value) return '—'
  if (!azStatus.value.logged_in) return 'Not logged in'
  return azStatus.value.user ?? 'Logged in'
})

const azStatusClass = computed(() => {
  if (!azStatus.value) return ''
  return azStatus.value.logged_in ? 'ok' : 'warn'
})

function typeTag(t: string) {
  if (t === 'aks') return 'primary'
  if (t === 'kyma') return 'success'
  return 'info'
}

onMounted(async () => {
  await Promise.all([loadInstances(), refreshStatus()])
})

async function loadInstances() {
  try {
    instances.value = await listInstances()
  } catch {
    ElMessage.error('Failed to load clusters')
  }
}

async function refreshStatus() {
  refreshing.value = true
  try {
    const [az, ip] = await Promise.all([getAzStatus(), getPublicIp()])
    azStatus.value = az
    publicIp.value = ip.ip
    statusUpdatedAt.value = new Date().toLocaleTimeString()
  } catch {
    ElMessage.error('Status refresh failed')
  } finally {
    refreshing.value = false
  }
}

async function doCreate() {
  if (!createForm.value.name.trim()) {
    ElMessage.warning('Name is required')
    return
  }
  creating.value = true
  try {
    const inst = await createInstance(createForm.value)
    instances.value.unshift(inst)
    showCreateDialog.value = false
    createForm.value = emptyCreateForm()
    ElMessage.success('Cluster created')
  } catch (e: any) {
    ElMessage.error(e.message || 'Failed to create cluster')
  } finally {
    creating.value = false
  }
}

function openInstance(inst: K8sInstance) {
  router.push({ name: 'k8s-instance', params: { id: inst.instance_id } })
}

function openSettings(inst: K8sInstance) {
  settingsInst.value = inst
  showSettings.value = true
}

function onSettingsSaved(updated: K8sInstance) {
  const idx = instances.value.findIndex((i) => i.instance_id === updated.instance_id)
  if (idx >= 0) instances.value[idx] = updated
  showSettings.value = false
}

async function confirmDelete(inst: K8sInstance) {
  try {
    await ElMessageBox.confirm(
      `Delete cluster "${inst.name}"? This cannot be undone.`,
      'Confirm',
      { confirmButtonText: 'Delete', cancelButtonText: 'Cancel', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await deleteInstance(inst.instance_id)
    instances.value = instances.value.filter((i) => i.instance_id !== inst.instance_id)
    ElMessage.success('Cluster deleted')
  } catch {
    ElMessage.error('Failed to delete cluster')
  }
}
</script>

<style scoped>
.k8s-root {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--el-bg-color-page);
  font-family: var(--el-font-family);
}

/* ── top bar ── */
.k8s-topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-light);
  flex-shrink: 0;
}
.k8s-back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: var(--el-text-color-secondary);
  border-radius: 6px;
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
}
.k8s-back:hover { background: var(--el-fill-color); color: var(--el-text-color-primary); }
.k8s-title { font-size: 15px; font-weight: 600; color: var(--el-text-color-primary); }
.k8s-topbar-spacer { flex: 1; }

/* ── status panel ── */
.k8s-status-panel {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 10px 20px;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-wrap: wrap;
  gap: 16px;
}
.k8s-status-divider {
  width: 1px;
  height: 20px;
  background: var(--el-border-color-light);
}
.k8s-status-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.k8s-status-ts { margin-left: auto; }
.k8s-status-label {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.k8s-status-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  font-family: 'Menlo', 'Monaco', monospace;
}
.k8s-status-value.ok { color: var(--el-color-success); }
.k8s-status-value.warn { color: var(--el-color-warning); }
.k8s-status-value.loading { opacity: 0.4; }
.k8s-status-value.muted { color: var(--el-text-color-placeholder); font-size: 12px; font-family: inherit; font-weight: 400; }

/* ── instance grid ── */
.k8s-instances-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 8px;
}
.k8s-instances-title { font-size: 13px; font-weight: 600; color: var(--el-text-color-secondary); text-transform: uppercase; letter-spacing: 0.06em; }

.k8s-empty {
  padding: 40px 20px;
  text-align: center;
  color: var(--el-text-color-placeholder);
  font-size: 14px;
}

.k8s-instance-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  padding: 0 20px 24px;
}

.k8s-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  padding: 14px 16px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.k8s-card:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 12px rgba(0,0,0,0.08);
}

.k8s-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.k8s-type-tag { flex-shrink: 0; }
.k8s-card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.k8s-card-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}
.k8s-card:hover .k8s-card-actions { opacity: 1; }
.k8s-card-action-btn {
  padding: 4px;
  border-radius: 4px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.k8s-card-action-btn:hover { background: var(--el-fill-color); color: var(--el-text-color-primary); }
.k8s-card-action-btn.danger:hover { background: var(--el-color-danger-light-9); color: var(--el-color-danger); }

.k8s-card-note {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.k8s-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
}
.k8s-meta-chip {
  font-size: 11px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  padding: 1px 6px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
}
.k8s-no-kubeconfig {
  font-size: 11px;
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
  border-radius: 4px;
  padding: 1px 6px;
}

.k8s-card-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}
.k8s-ext-link {
  font-size: 11px;
  color: var(--el-color-primary);
  text-decoration: none;
}
.k8s-ext-link:hover { text-decoration: underline; }
</style>
