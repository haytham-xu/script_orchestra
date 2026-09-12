import { defineComponent, ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '../service/KnowledgeVaultService'
import type {
  RawFragment, KnowledgeVaultSettings, Label, AnalyzedFragment, ChatMessage,
} from '../service/Model'

export default defineComponent({
  name: 'KnowledgeVaultView',
  setup() {
    const router = useRouter()
    function goBack() { router.push('/') }

    const activeTab = ref<'capture' | 'search' | 'duplicates' | 'settings'>('capture')
    const settings = ref<KnowledgeVaultSettings>({
      ai_model: '',
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

    // ---- fragment highlight (from search result navigation) ----
    const highlightFragId = ref<number | null>(null)

    // ---- settings ----
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

    return {
      goBack,
      activeTab, settings,
      labels, labelMap, loadLabels, newLabel, addLabel, removeLabel,
      draft, fragments, saving, addFragment, removeFragment, loadFragments,
      addDialog, openAdd,
      fmtDate,
      editDialog, editing, openEdit, saveEdit,
      batchDialog, chatInput, chatLoading, batchCommitting, batchLabelIds,
      messages, analyzed, openBatch, sendChat, commitBatch,
      suggestedLabels, applySuggestedLabel,
      queryText, results, aiAnswer, aiLoading, runSearch, runAiQuery,
      dupConfident, dupFuzzy, dupLoading, dupChecked, aiChecking, aiDupKeys, dupActing,
      pairKey, loadDuplicates, aiCheckFuzzy, resolvePair,
      highlightFragId,
      saveAiModel,
    }
  },
})
