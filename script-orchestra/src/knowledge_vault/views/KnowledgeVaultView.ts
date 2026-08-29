import { defineComponent, ref, onMounted, nextTick, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Network } from 'vis-network/standalone'
import * as api from '../service/KnowledgeVaultService'
import type { RawFragment, KnowledgeNode, KnowledgeVaultSettings, BuildStatus } from '../service/Model'

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
    const nodes = ref<KnowledgeNode[]>([])
    const edges = ref<any[]>([])
    const stale = ref<any[]>([])
    const buildStatus = ref<BuildStatus | null>(null)
    const building = ref(false)
    const selected = ref<KnowledgeNode | null>(null)   // clicked node detail
    const graphEl = ref<HTMLElement | null>(null)
    let network: Network | null = null

    // kind → node colour (semantic, so the graph is scannable at a glance).
    const KIND_COLOR: Record<string, string> = {
      url: '#0a84ff', command: '#30d158', script: '#ff9f0a', note: '#bf5af2',
    }
    // freshness → border colour (aging/stale visually flagged).
    const FRESH_BORDER: Record<string, string> = {
      fresh: '#34c759', aging: '#ff9f0a', stale: '#ff3b30',
    }

    async function loadNetwork() {
      nodes.value = await api.getNodes()
      edges.value = await api.getEdges()
      stale.value = await api.getStale()
      await nextTick()
      renderGraph()
    }

    function renderGraph() {
      if (!graphEl.value) return
      const visNodes = nodes.value.map((n) => ({
        id: n.id,
        label: n.title,
        title: n.summary || n.title,          // native tooltip
        color: {
          background: KIND_COLOR[n.kind] || '#8e8e93',
          border: FRESH_BORDER[n.freshness] || '#c7c7cc',
          highlight: { background: KIND_COLOR[n.kind] || '#8e8e93', border: '#1d1d1f' },
        },
        borderWidth: 3,
        font: { color: '#1d1d1f', size: 13 },
        shape: 'dot',
        size: 14 + (n.fragment_ids?.length || 1) * 2,   // bigger = more source fragments
      }))
      const visEdges = edges.value.map((e) => ({
        from: e.source_id, to: e.target_id,
        label: e.relation, width: 1 + (e.weight || 0.5) * 3,
        font: { size: 10, color: '#86868b', strokeWidth: 0 },
        color: { color: '#c7c7cc', highlight: '#0a84ff' },
        smooth: { enabled: true, type: 'continuous', roundness: 0.3 },
      }))
      const data = { nodes: visNodes, edges: visEdges }
      const options = {
        physics: { stabilization: true, barnesHut: { springLength: 140 } },
        interaction: { hover: true, tooltipDelay: 120 },
        nodes: { shadow: false },
        edges: { arrows: { to: { enabled: true, scaleFactor: 0.5 } } },
      }
      if (network) { network.setData(data as any) }
      else {
        network = new Network(graphEl.value, data as any, options as any)
        network.on('click', (params: any) => {
          const id = params.nodes?.[0]
          selected.value = id != null ? nodes.value.find((n) => n.id === id) || null : null
        })
      }
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

    onBeforeUnmount(() => { if (network) { network.destroy(); network = null } })

    return {
      activeTab, settings,
      draft, fragments, saving, addFragment, removeFragment, loadFragments,
      queryText, results, aiAnswer, aiLoading, runSearch, runAiQuery,
      nodes, edges, stale, buildStatus, building, loadNetwork, rebuild,
      selected, graphEl, KIND_COLOR,
      toggleAutoBuild,
    }
  },
})
