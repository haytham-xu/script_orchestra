import { defineComponent, ref, onMounted, nextTick, onBeforeUnmount, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Network } from 'vis-network/standalone'
import * as api from '../service/KnowledgeVaultService'
import type {
  RawFragment, KnowledgeNode, KnowledgeVaultSettings, BuildStatus, Label, AnalyzedFragment, ChatMessage,
} from '../service/Model'

export default defineComponent({
  name: 'KnowledgeVaultView',
  setup() {
    const activeTab = ref<'capture' | 'search' | 'network' | 'settings'>('capture')
    const settings = ref<KnowledgeVaultSettings>({
      auto_build: false, embed_model: '<embed-model>', relate_top_k: 5, stale_days: 90,
    })

    // ---- labels (user-managed tags, shared across tabs) ----
    const labels = ref<Label[]>([])
    const labelMap = computed<Record<number, Label>>(() =>
      Object.fromEntries(labels.value.map((l) => [l.id, l])))
    async function loadLabels() { labels.value = await api.getLabels() }
    const newLabel = ref({ name: '', color: '#0a84ff' })
    async function addLabel() {
      const name = newLabel.value.name.trim()
      if (!name) { ElMessage.warning('Label name is required'); return }
      try {
        await api.createLabel(name, newLabel.value.color)
        newLabel.value = { name: '', color: '#0a84ff' }
        await loadLabels()
      } catch (e: any) { ElMessage.error(e.message || 'Failed') }
    }
    async function removeLabel(l: Label) {
      try {
        await ElMessageBox.confirm(`Delete label “${l.name}”? It will be removed from all fragments.`, 'Confirm', { type: 'warning' })
        await api.deleteLabel(l.id)
        await loadLabels()
        await loadFragments()
      } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || 'Failed') }
    }

    // ---- capture ----
    // kind is no longer entered by the user — the AI infers it at build time.
    const draft = ref<{ content: string; note: string; label_ids: number[] }>({ content: '', note: '', label_ids: [] })
    const fragments = ref<RawFragment[]>([])
    const saving = ref(false)

    // date/status display helpers (freshness is computed server-side)
    function fmtDate(iso: string): string {
      if (!iso) return '—'
      const d = new Date(iso)
      return isNaN(d.getTime()) ? '—' : d.toLocaleDateString()
    }
    const FRESH_LABEL: Record<string, string> = { fresh: 'Fresh', aging: 'Aging', stale: 'May be outdated' }
    const FRESH_TYPE: Record<string, string> = { fresh: 'success', aging: 'warning', stale: 'danger' }

    async function loadFragments() { fragments.value = await api.getFragments() }
    async function addFragment() {
      if (!draft.value.content.trim()) { ElMessage.warning('Content is required'); return }
      if (saving.value) return   // guard against double-submit
      saving.value = true
      try {
        await api.addFragment(draft.value.content, draft.value.note, draft.value.label_ids)
        draft.value = { content: '', note: '', label_ids: [] }
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

    // ---- edit fragment ----
    const editDialog = ref(false)
    const editing = ref<{ id: number; content: string; note: string; label_ids: number[] }>(
      { id: 0, content: '', note: '', label_ids: [] })
    function openEdit(f: RawFragment) {
      editing.value = { id: f.id, content: f.content, note: f.note, label_ids: [...(f.label_ids || [])] }
      editDialog.value = true
    }
    async function saveEdit() {
      try {
        await api.updateFragment(editing.value.id, {
          content: editing.value.content, note: editing.value.note, label_ids: editing.value.label_ids,
        })
        editDialog.value = false
        ElMessage.success('Updated')
        await loadFragments()
      } catch (e: any) { ElMessage.error(e.response?.data?.error || e.message || 'Update failed') }
    }

    // ---- batch import (conversational: chat with AI, it regenerates the draft) ----
    const batchDialog = ref(false)
    const chatInput = ref('')
    const chatLoading = ref(false)
    const batchCommitting = ref(false)
    const batchLabelIds = ref<number[]>([])
    const messages = ref<ChatMessage[]>([])       // full conversation (sent every turn)
    const analyzed = ref<AnalyzedFragment[]>([])   // current draft, kept in sync with AI
    function openBatch() {
      chatInput.value = ''; messages.value = []; analyzed.value = []; batchLabelIds.value = []
      batchDialog.value = true
    }
    async function sendChat() {
      const text = chatInput.value.trim()
      if (!text) return
      if (chatLoading.value) return
      messages.value.push({ role: 'user', content: text })
      chatInput.value = ''
      chatLoading.value = true
      try {
        const r = await api.batchChat(messages.value, analyzed.value)
        messages.value.push({ role: 'assistant', content: r.reply || '(updated draft)' })
        // AI returns the FULL regenerated draft; keep prior selection where possible.
        analyzed.value = r.fragments.map((f) => ({ ...f, _keep: true }))
      } catch (e: any) {
        messages.value.push({ role: 'assistant', content: 'Error: ' + (e.response?.data?.error || e.message || 'chat failed') })
      } finally { chatLoading.value = false }
    }
    async function commitBatch() {
      const keep = analyzed.value.filter((f) => f._keep)
      if (!keep.length) { ElMessage.warning('Nothing selected'); return }
      batchCommitting.value = true
      try {
        const n = await api.batchCommit(keep, batchLabelIds.value)
        ElMessage.success(`Imported ${n} fragment(s)`)
        batchDialog.value = false
        await loadFragments()
      } catch (e: any) {
        ElMessage.error(e.response?.data?.error || e.message || 'Import failed')
      } finally { batchCommitting.value = false }
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
      await loadLabels()
      await loadFragments()
    })

    onBeforeUnmount(() => { if (network) { network.destroy(); network = null } })

    return {
      activeTab, settings,
      labels, labelMap, loadLabels, newLabel, addLabel, removeLabel,
      draft, fragments, saving, addFragment, removeFragment, loadFragments,
      fmtDate, FRESH_LABEL, FRESH_TYPE,
      editDialog, editing, openEdit, saveEdit,
      batchDialog, chatInput, chatLoading, batchCommitting, batchLabelIds,
      messages, analyzed, openBatch, sendChat, commitBatch,
      queryText, results, aiAnswer, aiLoading, runSearch, runAiQuery,
      nodes, edges, stale, buildStatus, building, loadNetwork, rebuild,
      selected, graphEl, KIND_COLOR,
      toggleAutoBuild,
    }
  },
})
