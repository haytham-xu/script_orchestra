import { defineComponent, ref, onMounted, nextTick, onBeforeUnmount, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Network } from 'vis-network/standalone'
import * as api from '../service/KnowledgeVaultService'
import type {
  RawFragment, KnowledgeNode, KnowledgeVaultSettings, BuildStatus, Label, AnalyzedFragment, ChatMessage,
} from '../service/Model'

export default defineComponent({
  name: 'KnowledgeVaultView',
  setup() {
    const router = useRouter()
    function goBack() { router.push('/') }

    const activeTab = ref<'capture' | 'search' | 'duplicates' | 'settings'>('capture')
    const settings = ref<KnowledgeVaultSettings>({
      auto_build: false, embed_model: '', ai_model: '', relate_top_k: 5, stale_days: 90,
      link_check_enabled: false,
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
    const addDialog = ref(false)
    function openAdd() {
      draft.value = { content: '', note: '', label_ids: [] }
      addDialog.value = true
    }
    async function addFragment() {
      if (!draft.value.content.trim()) { ElMessage.warning('Content is required'); return }
      if (saving.value) return   // guard against double-submit
      saving.value = true
      try {
        await api.addFragment(draft.value.content, draft.value.note, draft.value.label_ids)
        draft.value = { content: '', note: '', label_ids: [] }
        addDialog.value = false
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
    const suggestedLabels = ref<string[]>([])      // AI-suggested label names for this batch
    function openBatch() {
      chatInput.value = ''; messages.value = []; analyzed.value = []
      batchLabelIds.value = []; suggestedLabels.value = []
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
        // Only surface suggestions that aren't already an existing label.
        const existing = new Set(labels.value.map((l) => l.name.toLowerCase()))
        suggestedLabels.value = (r.suggested_labels || []).filter((n) => !existing.has(n.toLowerCase()))
      } catch (e: any) {
        messages.value.push({ role: 'assistant', content: 'Error: ' + (e.response?.data?.error || e.message || 'chat failed') })
      } finally { chatLoading.value = false }
    }
    // Click a suggested label → create it (if new) and apply to the batch.
    async function applySuggestedLabel(name: string) {
      try {
        const created = await api.createLabel(name)
        await loadLabels()
        if (!batchLabelIds.value.includes(created.id)) batchLabelIds.value.push(created.id)
        suggestedLabels.value = suggestedLabels.value.filter((n) => n !== name)
      } catch (e: any) { ElMessage.error(e.message || 'Failed to add label') }
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

    // ---- stale review (acts on the node's source fragments; nodes are rebuildable) ----
    const staleActing = ref<number | null>(null)   // node id currently being acted on
    async function markReviewed(node: KnowledgeNode) {
      staleActing.value = node.id
      try {
        stale.value = await api.markStaleReviewed(node.id)
        await api.getNodes().then((n) => { nodes.value = n; renderGraph() })
        ElMessage.success('Marked as still valid')
      } catch (e: any) {
        ElMessage.error(e.response?.data?.error || e.message || 'Failed')
      } finally { staleActing.value = null }
    }
    async function archiveStale(node: KnowledgeNode) {
      try {
        await ElMessageBox.confirm(
          `Archive “${node.title}”? Its ${node.fragment_ids?.length || 0} source fragment(s) will be hidden (not deleted). Rebuild to fully drop it from the graph.`,
          'Confirm', { type: 'warning' })
      } catch { return }   // cancelled
      staleActing.value = node.id
      try {
        stale.value = await api.archiveStale(node.id)
        await api.getNodes().then((n) => { nodes.value = n; renderGraph() })
        await loadFragments()   // archived fragments drop from the capture list
        ElMessage.success('Archived')
      } catch (e: any) {
        ElMessage.error(e.response?.data?.error || e.message || 'Failed')
      } finally { staleActing.value = null }
    }

    // ---- URL liveness check (C1; opt-in, user-triggered — makes outbound requests) ----
    const checkingLinks = ref(false)
    async function checkLinks() {
      checkingLinks.value = true
      try {
        const r = await api.checkLinks()
        stale.value = r.stale
        await api.getNodes().then((n) => { nodes.value = n; renderGraph() })
        if (r.dead > 0) {
          ElMessage.warning(`Checked ${r.checked} link(s): ${r.dead} dead → ${r.flagged_nodes} node(s) flagged for review`)
        } else {
          ElMessage.success(`Checked ${r.checked} link(s): all reachable`)
        }
      } catch (e: any) {
        ElMessage.error(e.response?.data?.error || e.message || 'Link check failed')
      } finally { checkingLinks.value = false }
    }

    // ---- duplicates (on-demand; vector pairs are zero-cost, ai-check spends tokens) ----
    const dupConfident = ref<api.DupPair[]>([])
    const dupFuzzy = ref<api.DupPair[]>([])
    const dupLoading = ref(false)
    const dupChecked = ref(false)          // has the user run a scan yet?
    const aiChecking = ref(false)
    const aiDupKeys = ref<Set<string>>(new Set())   // fuzzy pairs AI judged duplicate
    const dupActing = ref<string | null>(null)      // pair key currently being resolved
    const pairKey = (p: api.DupPair) => `${Math.min(p.a.id, p.b.id)}-${Math.max(p.a.id, p.b.id)}`

    async function loadDuplicates() {
      dupLoading.value = true
      try {
        const r = await api.findDuplicates()
        dupConfident.value = r.confident
        dupFuzzy.value = r.fuzzy
        aiDupKeys.value = new Set()
        dupChecked.value = true
      } catch (e: any) {
        ElMessage.error(e.response?.data?.error || e.message || 'Failed to find duplicates')
      } finally { dupLoading.value = false }
    }
    async function aiCheckFuzzy() {
      if (!dupFuzzy.value.length) return
      aiChecking.value = true
      try {
        const pairs = dupFuzzy.value.map((p) => [p.a.id, p.b.id] as [number, number])
        const dups = await api.aiCheckDuplicates(pairs)
        aiDupKeys.value = new Set(dups.map(([a, b]) => `${Math.min(a, b)}-${Math.max(a, b)}`))
        ElMessage.success(`AI judged ${dups.length} of ${pairs.length} fuzzy pair(s) as duplicates`)
      } catch (e: any) {
        ElMessage.error(e.response?.data?.error || e.message || 'AI check failed')
      } finally { aiChecking.value = false }
    }
    // Resolve a pair: keep one fragment, archive (soft-delete) the other.
    async function resolvePair(p: api.DupPair, keep: api.DupFrag, drop: api.DupFrag) {
      try {
        await ElMessageBox.confirm(
          `Keep “${(keep.note || keep.content).slice(0, 60)}” and archive the other? The archived fragment is hidden, not deleted (recoverable).`,
          'Confirm', { type: 'warning' })
      } catch { return }
      dupActing.value = pairKey(p)
      try {
        const r = await api.resolveDuplicate(keep.id, drop.id)
        dupConfident.value = r.confident
        dupFuzzy.value = r.fuzzy
        await loadFragments()   // archived fragment drops from the capture list
        ElMessage.success('Resolved')
      } catch (e: any) {
        ElMessage.error(e.response?.data?.error || e.message || 'Failed')
      } finally { dupActing.value = null }
    }

    // ---- graph filter / search / navigation (C2) ----
    const graphKinds = computed<string[]>(() =>
      Array.from(new Set(nodes.value.map((n) => n.kind || 'note'))).sort())
    const kindFilter = ref<Set<string>>(new Set())   // empty = show all kinds
    const labelFilter = ref<Set<number>>(new Set())   // empty = show all labels
    const nodeSearch = ref('')
    function toggleKind(kind: string) {
      const s = new Set(kindFilter.value)
      s.has(kind) ? s.delete(kind) : s.add(kind)
      kindFilter.value = s
      renderGraph()
    }
    function toggleLabelFilter(id: number) {
      const s = new Set(labelFilter.value)
      s.has(id) ? s.delete(id) : s.add(id)
      labelFilter.value = s
      renderGraph()
    }
    // Labels actually present on the current network (for the filter chips).
    const graphLabels = computed<Label[]>(() => {
      const present = new Set<number>()
      nodes.value.forEach((n) => (n.label_ids || []).forEach((id) => present.add(id)))
      return labels.value.filter((l) => present.has(l.id))
    })
    // Nodes to draw: kind filter ∩ label filter ∩ search match (empty set = no constraint).
    const visibleNodes = computed<KnowledgeNode[]>(() => {
      const q = nodeSearch.value.trim().toLowerCase()
      return nodes.value.filter((n) => {
        if (kindFilter.value.size && !kindFilter.value.has(n.kind || 'note')) return false
        if (labelFilter.value.size && !(n.label_ids || []).some((id) => labelFilter.value.has(id))) return false
        if (q && !(`${n.title} ${n.summary}`.toLowerCase().includes(q))) return false
        return true
      })
    })
    // Jump the viewport to the first search match and select it.
    function focusSearch() {
      const first = visibleNodes.value[0]
      if (!first || !network) { ElMessage.info('No matching node'); return }
      selected.value = first
      network.selectNodes([first.id])
      network.focus(first.id, { scale: 1.1, animation: { duration: 400, easingFunction: 'easeInOutQuad' } })
    }
    // Source fragments of the selected node (resolved from the in-memory list).
    const selectedFragments = computed<RawFragment[]>(() => {
      if (!selected.value) return []
      const byId = new Map(fragments.value.map((f) => [f.id, f]))
      return (selected.value.fragment_ids || []).map((id) => byId.get(id)).filter(Boolean) as RawFragment[]
    })
    // Jump to the Capture tab and briefly highlight a fragment.
    const highlightFragId = ref<number | null>(null)
    function goToFragment(f: RawFragment) {
      activeTab.value = 'capture'
      highlightFragId.value = f.id
      nextTick(() => {
        document.querySelector(`[data-frag-id="${f.id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      })
      setTimeout(() => { if (highlightFragId.value === f.id) highlightFragId.value = null }, 2400)
    }

    function renderGraph() {
      if (!graphEl.value) return
      const shown = visibleNodes.value
      const shownIds = new Set(shown.map((n) => n.id))
      const visNodes = shown.map((n) => ({
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
      const visEdges = edges.value
        .filter((e) => shownIds.has(e.source_id) && shownIds.has(e.target_id))
        .map((e) => ({
        from: e.source_id, to: e.target_id,
        label: e.relation, width: 1 + (e.weight || 0.5) * 3,
        title: e.weight != null ? `similarity ${Number(e.weight).toFixed(2)}` : undefined,
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

    const buildPhase = ref('')
    async function rebuild() {
      building.value = true
      buildPhase.value = 'starting'
      try {
        await api.build(true)   // returns immediately (202); build runs in background
        // Poll status until the build finishes.
        for (;;) {
          await new Promise((r) => setTimeout(r, 1500))
          const s = await api.getBuildStatus()
          buildStatus.value = s
          buildPhase.value = s.phase
          if (!s.running) break
        }
        if (buildStatus.value?.phase?.startsWith('error')) {
          ElMessage.error('Build failed: ' + buildStatus.value.phase)
        } else {
          ElMessage.success(`Built ${buildStatus.value?.nodes ?? 0} nodes, ${buildStatus.value?.edges ?? 0} edges`)
        }
        await loadNetwork()
      } catch (e: any) {
        ElMessage.error(e.response?.data?.error || e.message || 'Build failed')
      } finally { building.value = false; buildPhase.value = '' }
    }

    // ---- settings ----
    async function toggleAutoBuild(v: boolean) {
      try { settings.value = await api.updateSettings({ auto_build: v }) }
      catch (e: any) { ElMessage.error(e.message || 'Failed') }
    }
    async function toggleLinkCheck(v: boolean) {
      try { settings.value = await api.updateSettings({ link_check_enabled: v }) }
      catch (e: any) { ElMessage.error(e.message || 'Failed') }
    }
    async function saveAiModel() {
      const m = (settings.value.ai_model || '').trim()
      if (!m) { ElMessage.warning('Model cannot be empty'); return }
      try {
        settings.value = await api.updateSettings({ ai_model: m })
        ElMessage.success('Model saved')
      } catch (e: any) { ElMessage.error(e.response?.data?.error || e.message || 'Failed') }
    }

    onMounted(async () => {
      try { settings.value = await api.getSettings() } catch { /* defaults */ }
      await loadLabels()
      await loadFragments()
    })

    onBeforeUnmount(() => { if (network) { network.destroy(); network = null } })

    return {
      goBack,
      activeTab, settings,
      labels, labelMap, loadLabels, newLabel, addLabel, removeLabel,
      draft, fragments, saving, addFragment, removeFragment, loadFragments,
      addDialog, openAdd,
      fmtDate, FRESH_LABEL, FRESH_TYPE,
      editDialog, editing, openEdit, saveEdit,
      batchDialog, chatInput, chatLoading, batchCommitting, batchLabelIds,
      messages, analyzed, openBatch, sendChat, commitBatch,
      suggestedLabels, applySuggestedLabel,
      queryText, results, aiAnswer, aiLoading, runSearch, runAiQuery,
      nodes, edges, stale, buildStatus, building, buildPhase, loadNetwork, rebuild,
      staleActing, markReviewed, archiveStale,
      checkingLinks, checkLinks,
      dupConfident, dupFuzzy, dupLoading, dupChecked, aiChecking, aiDupKeys, dupActing,
      pairKey, loadDuplicates, aiCheckFuzzy, resolvePair,
      selected, graphEl, KIND_COLOR,
      graphKinds, kindFilter, toggleKind, nodeSearch, focusSearch,
      graphLabels, labelFilter, toggleLabelFilter,
      visibleNodes, selectedFragments, goToFragment, highlightFragId,
      toggleAutoBuild, toggleLinkCheck, saveAiModel,
    }
  },
})
