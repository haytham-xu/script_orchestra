import { defineComponent, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
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
    const draft = ref({ content: '', note: '', kind: '' })
    const fragments = ref<RawFragment[]>([])
    async function loadFragments() { fragments.value = await api.getFragments() }
    async function addFragment() {
      if (!draft.value.content.trim()) { ElMessage.warning('Content is required'); return }
      try {
        await api.addFragment(draft.value.content, draft.value.note, draft.value.kind)
        draft.value = { content: '', note: '', kind: '' }
        ElMessage.success('Saved')
        await loadFragments()
      } catch (e: any) { ElMessage.error(e.message || 'Save failed') }
    }
    async function archive(f: RawFragment) {
      try { await api.archiveFragment(f.id); await loadFragments() }
      catch (e: any) { ElMessage.error(e.message || 'Archive failed') }
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
      draft, fragments, addFragment, archive, loadFragments,
      queryText, results, aiAnswer, aiLoading, runSearch, runAiQuery,
      nodes, stale, buildStatus, building, loadNetwork, rebuild,
      toggleAutoBuild,
    }
  },
})
