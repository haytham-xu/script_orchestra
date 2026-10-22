<template>
  <el-form :model="form" label-width="140px" size="small" class="ks-form">
    <el-form-item label="Name">
      <el-input v-model="form.name" />
    </el-form-item>
    <el-form-item label="Type">
      <el-select v-model="form.cluster_type" style="width:100%">
        <el-option label="AKS (Azure)" value="aks" />
        <el-option label="Kyma (SAP BTP)" value="kyma" />
        <el-option label="Generic K8s" value="generic" />
      </el-select>
    </el-form-item>
    <el-form-item label="Note">
      <el-input v-model="form.note" type="textarea" :rows="3" />
    </el-form-item>

    <!-- AKS fields -->
    <template v-if="form.cluster_type === 'aks'">
      <el-divider content-position="left"><small>AKS Details</small></el-divider>
      <el-form-item label="Subscription ID">
        <el-input v-model="form.subscription_id" />
      </el-form-item>
      <el-form-item label="Resource Group">
        <el-input v-model="form.resource_group" />
      </el-form-item>
      <el-form-item label="Cluster Name">
        <el-input v-model="form.cluster_name" />
      </el-form-item>
      <el-form-item label="Azure Portal Link">
        <el-input v-model="form.azure_portal_link" placeholder="https://portal.azure.com/..." />
      </el-form-item>
    </template>

    <!-- Kyma fields -->
    <template v-if="form.cluster_type === 'kyma'">
      <el-divider content-position="left"><small>Kyma / BTP Details</small></el-divider>
      <el-form-item label="Kyma Dashboard">
        <el-input v-model="form.kyma_dashboard_url" />
      </el-form-item>
      <el-form-item label="Global Account">
        <el-input v-model="form.btp_global_account" />
      </el-form-item>
      <el-form-item label="Subaccount">
        <el-input v-model="form.btp_subaccount" />
      </el-form-item>
      <el-form-item label="Environment Name">
        <el-input v-model="form.kyma_environment_name" />
      </el-form-item>
    </template>

    <!-- Kubeconfig section -->
    <el-divider content-position="left"><small>Kubeconfig</small></el-divider>
    <el-form-item label="Status">
      <el-tag :type="instance.has_kubeconfig ? 'success' : 'warning'" size="small">
        {{ instance.has_kubeconfig ? 'Configured' : 'Not set' }}
      </el-tag>
      <el-button
        v-if="instance.has_kubeconfig"
        size="small"
        type="danger"
        text
        style="margin-left:8px"
        :loading="removingKc"
        @click="removeKubeconfig"
      >Remove</el-button>
    </el-form-item>
    <el-form-item label="Paste kubeconfig">
      <el-input
        v-model="kubeconfigText"
        type="textarea"
        :rows="6"
        placeholder="Paste kubeconfig YAML here…"
        style="font-family:monospace;font-size:11px"
      />
    </el-form-item>
    <el-form-item label=" " label-width="140px">
      <el-button
        size="small"
        type="primary"
        :disabled="!kubeconfigText.trim()"
        :loading="savingKc"
        @click="saveKubeconfig"
      >Save Kubeconfig</el-button>
    </el-form-item>

    <div class="ks-form-actions">
      <el-button type="primary" :loading="saving" @click="save">Save Settings</el-button>
    </div>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { updateInstance, uploadKubeconfig, removeKubeconfig as apiRemoveKubeconfig } from '../service/K8sConsoleService'
import type { K8sInstance } from '../service/Model'

const props = defineProps<{ instance: K8sInstance }>()
const emit = defineEmits<{ saved: [inst: K8sInstance] }>()

const form = reactive({
  name: props.instance.name,
  cluster_type: props.instance.cluster_type,
  note: props.instance.note,
  subscription_id: props.instance.subscription_id,
  resource_group: props.instance.resource_group,
  cluster_name: props.instance.cluster_name,
  azure_portal_link: props.instance.azure_portal_link,
  kyma_dashboard_url: props.instance.kyma_dashboard_url,
  btp_global_account: props.instance.btp_global_account,
  btp_subaccount: props.instance.btp_subaccount,
  kyma_environment_name: props.instance.kyma_environment_name,
})

const saving = ref(false)
const kubeconfigText = ref('')
const savingKc = ref(false)
const removingKc = ref(false)

async function save() {
  saving.value = true
  try {
    const updated = await updateInstance(props.instance.instance_id, { ...form })
    ElMessage.success('Settings saved')
    emit('saved', updated)
  } catch {
    ElMessage.error('Failed to save settings')
  } finally {
    saving.value = false
  }
}

async function saveKubeconfig() {
  const kc = kubeconfigText.value.trim()
  if (!kc) return
  savingKc.value = true
  try {
    await uploadKubeconfig(props.instance.instance_id, kc)
    kubeconfigText.value = ''
    ElMessage.success('Kubeconfig saved (encrypted)')
    // Signal parent to refresh so has_kubeconfig reflects truth
    const updated = await updateInstance(props.instance.instance_id, {})
    emit('saved', { ...updated, has_kubeconfig: true })
  } catch {
    ElMessage.error('Failed to save kubeconfig')
  } finally {
    savingKc.value = false
  }
}

async function removeKubeconfig() {
  removingKc.value = true
  try {
    await apiRemoveKubeconfig(props.instance.instance_id)
    ElMessage.success('Kubeconfig removed')
    emit('saved', { ...props.instance, has_kubeconfig: false })
  } catch {
    ElMessage.error('Failed to remove kubeconfig')
  } finally {
    removingKc.value = false
  }
}
</script>

<style scoped>
.ks-form { padding: 4px 0; }
.ks-form-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}
</style>
