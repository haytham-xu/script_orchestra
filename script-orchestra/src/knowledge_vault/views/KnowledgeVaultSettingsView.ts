import { defineComponent, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '../service/KnowledgeVaultService'
import type { Label, KnowledgeVaultSettings } from '../service/Model'

export default defineComponent({
  name: 'KnowledgeVaultSettingsView',
  setup() {
    const router = useRouter()
    function goBack() { router.push({ name: 'knowledge-vault-capture' }) }

    const settings = ref<KnowledgeVaultSettings>({ ai_model: '', embed_model: '' })
    const labels = ref<Label[]>([])
    const newLabel = ref({ name: '', color: '#0a84ff' })

    const labelPresetColors = [
      '#0a84ff', '#34c759', '#ff9f0a', '#ff3b30',
      '#af52de', '#5ac8fa', '#ff6b35', '#30b0c7',
      '#8e8e93', '#1d1d1f',
    ]

    async function loadAll() {
      const [lbls, cfg] = await Promise.all([api.getLabels(), api.getSettings()])
      labels.value = lbls
      settings.value = cfg
    }

    async function addLabel() {
      const name = newLabel.value.name.trim()
      if (!name) { ElMessage.warning('Label name is required'); return }
      try {
        await api.createLabel(name, newLabel.value.color)
        newLabel.value = { name: '', color: '#0a84ff' }
        await loadAll()
      } catch (e: any) {
        ElMessage.warning(e?.response?.data?.error || e.message || 'Failed')
      }
    }
    async function removeLabel(l: Label) {
      try {
        await ElMessageBox.confirm(`Delete label "${l.name}"?`, 'Confirm', { type: 'warning' })
        await api.deleteLabel(l.id)
        await loadAll()
      } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || 'Failed') }
    }

    const editingLabelId = ref<number | null>(null)
    const editingLabelName = ref('')
    const editingLabelColor = ref('')

    function startEditLabel(l: Label) {
      editingLabelId.value = l.id; editingLabelName.value = l.name; editingLabelColor.value = l.color
    }
    function cancelEditLabel() { editingLabelId.value = null }
    async function saveEditLabel() {
      if (!editingLabelId.value) return
      const name = editingLabelName.value.trim()
      if (!name) { ElMessage.warning('Label name is required'); return }
      try {
        await api.updateLabel(editingLabelId.value, name, editingLabelColor.value)
        editingLabelId.value = null; await loadAll()
      } catch (e: any) { ElMessage.error(e?.response?.data?.error || e.message || 'Failed') }
    }

    async function saveAiModel() {
      const m = (settings.value.ai_model || '').trim()
      if (!m) { ElMessage.warning('Model cannot be empty'); return }
      try {
        settings.value = await api.updateSettings({ ai_model: m }); ElMessage.success('Saved')
      } catch (e: any) { ElMessage.error(e.message || 'Failed') }
    }

    async function saveEmbedModel() {
      const m = (settings.value.embed_model || '').trim()
      if (!m) { ElMessage.warning('Model cannot be empty'); return }
      try {
        settings.value = await api.updateSettings({ embed_model: m })
        ElMessage.success('Saved — rebuild the search index to apply')
      } catch (e: any) { ElMessage.error(e.message || 'Failed') }
    }

    onMounted(async () => { await loadAll() })

    return {
      goBack,
      settings, labels, newLabel, labelPresetColors,
      addLabel, removeLabel,
      editingLabelId, editingLabelName, editingLabelColor,
      startEditLabel, cancelEditLabel, saveEditLabel,
      saveAiModel, saveEmbedModel,
    }
  },
})
