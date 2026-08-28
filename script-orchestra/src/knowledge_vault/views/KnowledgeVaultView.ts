import { defineComponent, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '../service/KnowledgeVaultService'
import type { RawFragment, KnowledgeVaultSettings, BuildStatus } from '../service/Model'

export default defineComponent({
  name: 'KnowledgeVaultView',
  setup() {
    const activeTab = ref<'capture' | 'search' | 'network'>('capture')
    const settings = ref<KnowledgeVaultSettings>({
      auto_build: false, embed_model: '<embed-model>', relate_top_k: 5, stale_days: 90,
    })

    // ---- capture ----
    // kind is no longer entered by the user — the AI infers it at build time.
    const draft = ref({ content: '', note: '' })
    const fragments = ref<RawFragment[]>([])
    const saving = ref(false)
    async function loadFragments() { fragments.value = await api.getFragments() }
    async function addFragment() {
      if (!draft.value.content.trim()) { ElMessage.warning('Content is required'); return }
      if (saving.value) return   // guard against double-submit
      saving.value = true
      try {
        await api.addFragment(draft.value.content, draft.value.note)
        draft.value = { content: '', note: '' }
        ElMessage.success('Saved')
        await loadFragments()
      } catch (e: any) {
        ElMessage.error(e.response?.data?.error || e.message || 'Save failed')
      } finally { saving.value = false }
    }
    async function removeFragment(f: RawFragment) {
      try {
        await ElMessageBox.confirm('Permanently delete this fragment?', 'Confirm', { type: 'warning' })
        await api.deleteFragment(f.id)  // hard delete (user-initiated)
        ElMessage.success('Deleted')
        await loadFragments()
      } catch (e: any) {
        if (e !== 'cancel') ElMessage.error(e.message || 'Delete failed')
      }
    }

    // ---- search ----
    const queryText = ref('')
    const results = ref<RawFragment[]>([])
    const aiAnswer = ref('')
    const aiLoading = ref(false)
    async function runSearch() {
      results.value = await api.search(queryText.value, 10)
      aiAnswer.value = ''
    }
    async function runAiQuery() {
      if (!queryText.value.trim()) return
      aiLoading.value = true
      try {
        const r = await api.aiQuery(queryText.value)
        aiAnswer.value = r.answer
        results.value = r.used
      } catch (e: any) {
        ElMessage.error(e.response?.data?.error || e.message || 'AI query failed')
      } finally { aiLoading.value = false }
    }

    // ---- network / build ----
    const nodes = ref<any[]>([])
    const stale = ref<any[]>([])
    const buildStatus = ref<BuildStatus | null>(null)
    const building = ref(false)
    async function loadNetwork() {
      nodes.value = await api.getNodes()
      stale.value = await api.getStale()
    }
    async function rebuild() {
      building.value = true
      try {
        buildStatus.value = await api.build(true)
        ElMessage.success(`Built ${buildStatus.value.nodes} nodes, ${buildStatus.value.edges} edges`)
        await loadNetwork()
      } catch (e: any) {
        ElMessage.error(e.response?.data?.error || e.message || 'Build failed')
      } finally { building.value = false }
    }

    // ---- settings ----
    async function toggleAutoBuild(v: boolean) {
      try { settings.value = await api.updateSettings({ auto_build: v }) }
      catch (e: any) { ElMessage.error(e.message || 'Failed') }
    }

    onMounted(async () => {
      try { settings.value = await api.getSettings() } catch { /* defaults */ }
      await loadFragments()
    })

    return {
      activeTab, settings,
      draft, fragments, saving, addFragment, removeFragment, loadFragments,
      queryText, results, aiAnswer, aiLoading, runSearch, runAiQuery,
      nodes, stale, buildStatus, building, loadNetwork, rebuild,
      toggleAutoBuild,
    }
  },
})
