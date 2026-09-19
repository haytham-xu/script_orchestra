import { defineComponent, ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { marked } from 'marked'
import * as api from '../service/KnowledgeVaultService'
import type { RawFragment, Label, FragmentGroup, ContentBlock } from '../service/Model'
import { fragmentSummary } from '../service/Model'
import GroupTreeNode from './GroupTreeNode.vue'

export default defineComponent({
  name: 'KnowledgeVaultCaptureView',
  components: { GroupTreeNode },
  setup() {
    const router = useRouter()
    const route = useRoute()
    function goBack() { router.push({ name: 'knowledge-vault' }) }
    function goSearch() { router.push({ name: 'knowledge-vault' }) }
    function goSettings() { router.push({ name: 'knowledge-vault-settings' }) }

    // ---- labels ----
    const labels = ref<Label[]>([])
    const labelMap = computed<Record<number, Label>>(() =>
      Object.fromEntries(labels.value.map(l => [l.id, l])))

    // ---- data ----
    const fragments = ref<RawFragment[]>([])
    const allFragments = ref<RawFragment[]>([])
    const groups = ref<FragmentGroup[]>([])

    const viewMode = ref<'all' | 'ungrouped' | 'normal'>('all')
    const currentGroupId = ref<number | null>(null)

    const ROOT_GROUP_ID = 1

    const treeGroups = computed<FragmentGroup[]>(() => {
      const byId = new Map(groups.value
        .filter(g => g.id !== ROOT_GROUP_ID)
        .map(g => ({ ...g, children: [] as FragmentGroup[], fragments: [] as RawFragment[] }))
        .map(g => [g.id, g]))
      byId.forEach(g => {
        if (g.parent_id != null && g.parent_id !== ROOT_GROUP_ID) {
          const p = byId.get(g.parent_id); if (p) p.children!.push(g)
        }
      })
      for (const f of allFragments.value) {
        if (f.group_id != null && f.group_id !== ROOT_GROUP_ID) {
          const g = byId.get(f.group_id); if (g) g.fragments!.push(f)
        }
      }
      // top-level in the tree = groups whose parent is null or root
      return [...byId.values()].filter(g => g.parent_id == null || g.parent_id === ROOT_GROUP_ID)
    })

    const currentFragments = computed<RawFragment[]>(() => {
      if (currentGroupId.value == null) return fragments.value
      return allFragments.value.filter(f => f.group_id === currentGroupId.value)
    })
    const currentGroup = computed(() =>
      currentGroupId.value == null ? null : groups.value.find(g => g.id === currentGroupId.value) ?? null)
    const currentSubGroups = computed<FragmentGroup[]>(() => {
      if (currentGroupId.value == null) return treeGroups.value
      return groups.value.filter(g => g.parent_id === currentGroupId.value)
    })

    const filterLabelIds = ref<number[]>([])
    const baseFragments = computed<RawFragment[]>(() => {
      if (viewMode.value === 'all') return allFragments.value
      if (viewMode.value === 'ungrouped') return fragments.value
      // normal at root: show fragments in the root group (All fragments, id=1)
      if (currentGroupId.value == null)
        return allFragments.value.filter(f => f.group_id === ROOT_GROUP_ID)
      return currentFragments.value
    })
    const filteredFragments = computed(() => {
      if (!filterLabelIds.value.length) return baseFragments.value
      return baseFragments.value.filter(f =>
        filterLabelIds.value.every(lid => f.label_ids?.includes(lid)))
    })

    const flatGroupOptions = computed<{ id: number; label: string }[]>(() => {
      const result: { id: number; label: string }[] = []
      function walk(nodes: FragmentGroup[], depth: number) {
        for (const g of nodes) {
          const prefix = '　'.repeat(depth) + '↳ '
          const suffix = g.note && g.note !== 'root group' ? ` — ${g.note}` : ''
          result.push({ id: g.id, label: prefix + g.name + suffix })
          if (g.children?.length) walk(g.children, depth + 1)
        }
      }
      walk(treeGroups.value, 1)
      return result
    })

    function groupFragmentCount(gid: number): number {
      return allFragments.value.filter(f => f.group_id === gid).length
    }

    const showArchived = ref(false)

    async function loadAll() {
      const [frags, allFrags, grps, lbls] = await Promise.all([
        api.getFragments(true, showArchived.value), api.getAllFragments(showArchived.value), api.getGroups(), api.getLabels(),
      ])
      fragments.value = frags
      allFragments.value = allFrags
      groups.value = grps
      labels.value = lbls
    }

    async function toggleArchived() {
      showArchived.value = !showArchived.value
      closeDetail()
      await loadAll()
    }

    // ---- detail panel ----
    const detailOpen = ref(false)
    const selectedFrag = ref<RawFragment | null>(null)
    const detailEditing = ref(false)

    function openDetail(frag: RawFragment) { selectedFrag.value = frag; detailEditing.value = false; detailOpen.value = true }
    function closeDetail() { detailOpen.value = false; selectedFrag.value = null; detailEditing.value = false }

    const editingBlocks = ref<ContentBlock[]>([])
    const editingNote = ref('')
    const editingHeader = ref('')
    const editingLabelIds = ref<number[]>([])

    function startEdit() {
      if (!selectedFrag.value) return
      editingBlocks.value = selectedFrag.value.blocks.map(b => ({
        type: b.type, body: b.body, lang: b.lang ?? '', subtitle: b.subtitle ?? '',
      }))
      editingNote.value = selectedFrag.value.note
      editingHeader.value = selectedFrag.value.header || ''
      editingLabelIds.value = [...(selectedFrag.value.label_ids || [])]
      detailEditing.value = true
    }
    function cancelEdit() { detailEditing.value = false }

    function addBlock(type: ContentBlock['type'] = 'text') {
      editingBlocks.value.push({ type, body: '', subtitle: '', ...(type === 'code' ? { lang: '' } : {}) })
    }
    function removeBlock(idx: number) { if (editingBlocks.value.length > 1) editingBlocks.value.splice(idx, 1) }
    function moveBlock(idx: number, dir: -1 | 1) {
      const t = idx + dir
      if (t < 0 || t >= editingBlocks.value.length) return
      const tmp = editingBlocks.value[idx]; editingBlocks.value[idx] = editingBlocks.value[t]; editingBlocks.value[t] = tmp
    }

    async function saveEdit() {
      if (!selectedFrag.value) return
      if (!editingHeader.value.trim()) { ElMessage.warning('Header is required'); return }
      try {
        const updated = await api.updateFragment(selectedFrag.value.id, {
          blocks: editingBlocks.value, note: editingNote.value,
          header: editingHeader.value, label_ids: editingLabelIds.value,
        })
        selectedFrag.value = updated; detailEditing.value = false
        await loadAll(); ElMessage.success('Saved')
      } catch (e: any) { ElMessage.error(e.message || 'Failed') }
    }

    async function deleteSelected() {
      if (!selectedFrag.value) return
      try {
        await ElMessageBox.confirm('Permanently delete this fragment?', 'Confirm', { type: 'warning' })
        await api.deleteFragment(selectedFrag.value.id); closeDetail(); await loadAll(); ElMessage.success('Deleted')
      } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || 'Failed') }
    }

    async function archiveSelected() {
      if (!selectedFrag.value) return
      try {
        await api.archiveFragment(selectedFrag.value.id); closeDetail(); await loadAll(); ElMessage.success('Archived')
      } catch (e: any) { ElMessage.error(e.message || 'Failed') }
    }

    async function unarchiveSelected() {
      if (!selectedFrag.value) return
      try {
        await api.unarchiveFragment(selectedFrag.value.id); closeDetail(); await loadAll(); ElMessage.success('Restored')
      } catch (e: any) { ElMessage.error(e.message || 'Failed') }
    }

    // ---- add fragment ----
    const addDialog = ref(false)
    const draftBlocks = ref<ContentBlock[]>([{ type: 'text', body: '', subtitle: '' }])
    const draftNote = ref('')
    const draftHeader = ref('')
    const draftLabelIds = ref<number[]>([])
    const draftGroupId = ref<number | null>(null)
    const saving = ref(false)
    const draftHeaderTouched = ref(false)

    function openAdd() {
      draftBlocks.value = [{ type: 'text', body: '', subtitle: '' }]
      draftNote.value = ''; draftHeader.value = ''; draftLabelIds.value = []
      draftGroupId.value = currentGroupId.value
      draftHeaderTouched.value = false; addDialog.value = true
    }
    function addDraftBlock(type: ContentBlock['type'] = 'text') {
      draftBlocks.value.push({ type, body: '', subtitle: '', ...(type === 'code' ? { lang: '' } : {}) })
    }
    function removeDraftBlock(idx: number) { if (draftBlocks.value.length > 1) draftBlocks.value.splice(idx, 1) }
    async function addFragment() {
      if (!draftHeader.value.trim()) { ElMessage.warning('Header is required'); return }
      if (!draftBlocks.value.some(b => b.body.trim())) { ElMessage.warning('At least one block must have content'); return }
      if (saving.value) return
      saving.value = true
      try {
        const created = await api.addFragment(draftBlocks.value, draftNote.value, draftLabelIds.value, draftHeader.value)
        if (draftGroupId.value != null) {
          const existing = await api.getGroupMembers(draftGroupId.value)
          await api.setGroupMembers(draftGroupId.value, [...new Set([...existing, created.id])])
        }
        addDialog.value = false; await loadAll(); ElMessage.success('Saved')
      } catch (e: any) { ElMessage.error(e.message || 'Failed') } finally { saving.value = false }
    }

    // ---- groups ----
    const groupDialog = ref(false)
    const editingGroup = ref<{ id: number | null; name: string; note: string; parent_id: number | null }>(
      { id: null, name: '', note: '', parent_id: null })
    const savingGroup = ref(false)

    function openCreateGroup(parentId?: number) {
      editingGroup.value = { id: null, name: '', note: '', parent_id: parentId ?? null }; groupDialog.value = true
    }
    function openEditGroup(g: FragmentGroup) {
      editingGroup.value = { id: g.id, name: g.name, note: g.note || '', parent_id: g.parent_id }; groupDialog.value = true
    }
    async function saveGroup() {
      const name = editingGroup.value.name.trim()
      if (!name) { ElMessage.warning('Group name is required'); return }
      savingGroup.value = true
      try {
        if (editingGroup.value.id == null) await api.createGroup(name, editingGroup.value.note, editingGroup.value.parent_id)
        else await api.updateGroup(editingGroup.value.id, { name, note: editingGroup.value.note, parent_id: editingGroup.value.parent_id })
        groupDialog.value = false; await loadAll()
      } catch (e: any) { ElMessage.error(e.response?.data?.error || e.message || 'Failed')
      } finally { savingGroup.value = false }
    }
    async function confirmDeleteGroup(g: FragmentGroup) {
      try {
        await ElMessageBox.confirm(`Delete group "${g.name}"? It must be empty.`, 'Confirm', { type: 'warning' })
        await api.deleteGroup(g.id)
        if (currentGroupId.value === g.id) currentGroupId.value = null
        await loadAll(); ElMessage.success('Deleted')
      } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.response?.data?.error || e.message || 'Failed') }
    }

    const groupMemberDialog = ref(false)
    const fragmentToGroup = ref<RawFragment | null>(null)
    const targetGroupId = ref<number | null>(null)

    function openMoveToGroup(frag: RawFragment) {
      fragmentToGroup.value = frag; targetGroupId.value = frag.group_id ?? null; groupMemberDialog.value = true
    }
    async function confirmMoveToGroup() {
      if (!fragmentToGroup.value) return
      try {
        const frag = fragmentToGroup.value
        if (targetGroupId.value == null) {
          if (frag.group_id != null) {
            const ex = await api.getGroupMembers(frag.group_id)
            await api.setGroupMembers(frag.group_id, ex.filter(id => id !== frag.id))
          }
        } else {
          if (frag.group_id != null && frag.group_id !== targetGroupId.value) {
            const ex = await api.getGroupMembers(frag.group_id)
            await api.setGroupMembers(frag.group_id, ex.filter(id => id !== frag.id))
          }
          const ex = await api.getGroupMembers(targetGroupId.value)
          await api.setGroupMembers(targetGroupId.value, [...new Set([...ex, frag.id])])
        }
        groupMemberDialog.value = false; await loadAll()
        if (selectedFrag.value?.id === frag.id)
          selectedFrag.value = allFragments.value.find(f => f.id === frag.id) ?? null
        ElMessage.success('Moved')
      } catch (e: any) { ElMessage.error(e.message || 'Failed') }
    }

    // ---- organize mode ----
    const captureMode = ref<'fragments' | 'organize'>('fragments')
    const organizeFragments = ref<RawFragment[]>([])
    const organizeSelected = ref<Set<number>>(new Set())
    const organizeBulkGroupId = ref<number | null>(null)
    const organizeSaving = ref(false)
    const organizeSelectedFrag = ref<RawFragment | null>(null)

    async function loadOrganize() {
      organizeFragments.value = await api.getAllFragments()
      if (organizeSelectedFrag.value) {
        organizeSelectedFrag.value = organizeFragments.value.find(f => f.id === organizeSelectedFrag.value!.id) ?? null
      }
    }

    function organizeToggle(id: number) {
      const s = new Set(organizeSelected.value); s.has(id) ? s.delete(id) : s.add(id); organizeSelected.value = s
    }
    function organizeToggleAll() {
      organizeSelected.value = organizeSelected.value.size === organizeFragments.value.length
        ? new Set() : new Set(organizeFragments.value.map(f => f.id))
    }
    async function organizeBulkMove() {
      if (!organizeSelected.value.size) { ElMessage.warning('Select at least one fragment'); return }
      organizeSaving.value = true
      try {
        const ids = [...organizeSelected.value]; const tgid = organizeBulkGroupId.value
        for (const frag of organizeFragments.value.filter(f => ids.includes(f.id))) {
          if (frag.group_id != null && frag.group_id !== tgid) {
            const ex = await api.getGroupMembers(frag.group_id)
            await api.setGroupMembers(frag.group_id, ex.filter(id => id !== frag.id))
          }
          if (tgid != null) {
            const ex = await api.getGroupMembers(tgid)
            await api.setGroupMembers(tgid, [...new Set([...ex, frag.id])])
          }
        }
        organizeSelected.value = new Set(); await Promise.all([loadOrganize(), loadAll()])
        ElMessage.success(`Moved ${ids.length} fragment(s)`)
      } catch (e: any) { ElMessage.error(e.message || 'Failed')
      } finally { organizeSaving.value = false }
    }
    async function organizeQuickMove(frag: RawFragment, newGroupId: number | null) {
      try {
        if (frag.group_id != null && frag.group_id !== newGroupId) {
          const ex = await api.getGroupMembers(frag.group_id)
          await api.setGroupMembers(frag.group_id, ex.filter(id => id !== frag.id))
        }
        if (newGroupId != null) {
          const ex = await api.getGroupMembers(newGroupId)
          await api.setGroupMembers(newGroupId, [...new Set([...ex, frag.id])])
        }
        await Promise.all([loadOrganize(), loadAll()])
      } catch (e: any) { ElMessage.error(e.message || 'Failed') }
    }
    async function organizeDeleteOne(frag: RawFragment) {
      try {
        await ElMessageBox.confirm(`Delete "${fragmentSummary(frag)}"?`, 'Confirm', { type: 'warning' })
        await api.deleteFragment(frag.id)
        const s = new Set(organizeSelected.value); s.delete(frag.id); organizeSelected.value = s
        if (organizeSelectedFrag.value?.id === frag.id) organizeSelectedFrag.value = null
        await Promise.all([loadOrganize(), loadAll()])
      } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || 'Failed') }
    }
    async function organizeDeleteSelected() {
      const ids = [...organizeSelected.value]; if (!ids.length) return
      try {
        await ElMessageBox.confirm(`Delete ${ids.length} fragment(s)?`, 'Confirm', { type: 'warning' })
        organizeSaving.value = true
        await Promise.all(ids.map(id => api.deleteFragment(id)))
        organizeSelected.value = new Set(); await Promise.all([loadOrganize(), loadAll()])
      } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.message || 'Failed')
      } finally { organizeSaving.value = false }
    }

    watch(captureMode, (mode) => { if (mode === 'organize') loadOrganize() })

    // ---- helpers ----
    function fmtDate(iso: string): string {
      if (!iso) return '—'; const d = new Date(iso)
      return isNaN(d.getTime()) ? '—' : d.toLocaleDateString()
    }
    function renderMd(text: string): string {
      return marked.parse(text || '', { async: false }) as string
    }
    function setBlockType(blocks: ContentBlock[], idx: number, type: string) {
      blocks[idx] = { ...blocks[idx], type: type as ContentBlock['type'] }
    }
    async function copyBlock(text: string) {
      try { await navigator.clipboard.writeText(text); ElMessage.success('Copied') }
      catch { ElMessage.error('Copy failed') }
    }

    // ---- reindex ----
    const reindexStatus = ref({ running: false, total: 0, indexed: 0 })
    let reindexPoll: ReturnType<typeof setInterval> | null = null

    function startReindexPolling() {
      if (reindexPoll) return
      reindexPoll = setInterval(async () => {
        try {
          reindexStatus.value = await api.getReindexStatus()
          if (!reindexStatus.value.running) {
            clearInterval(reindexPoll!); reindexPoll = null
            ElMessage.success('Rebuild complete')
          }
        } catch { clearInterval(reindexPoll!); reindexPoll = null }
      }, 1000)
    }

    async function triggerReindex() {
      try {
        await api.reindexAll()
        reindexStatus.value = { running: true, total: 0, indexed: 0 }
        startReindexPolling()
      } catch (e: any) { ElMessage.error(e.message || 'Reindex failed') }
    }

    onMounted(async () => {
      await loadAll()
      try {
        reindexStatus.value = await api.getReindexStatus()
        if (reindexStatus.value.running) startReindexPolling()
      } catch { /* ignore */ }
      // open fragment if navigated here from search with ?open=id
      const openId = route.query.open
      if (openId) {
        const frag = allFragments.value.find(f => f.id === Number(openId))
        if (frag) openDetail(frag)
      }
    })

    onUnmounted(() => { if (reindexPoll) { clearInterval(reindexPoll); reindexPoll = null } })

    const expandedLongs = ref(new Set<ContentBlock>())
    function toggleLong(blk: ContentBlock) {
      if (expandedLongs.value.has(blk)) expandedLongs.value.delete(blk)
      else expandedLongs.value.add(blk)
      expandedLongs.value = new Set(expandedLongs.value)
    }

    return {
      goBack, goSearch, goSettings,
      ROOT_GROUP_ID,
      labels, labelMap,
      fragments, allFragments, groups, treeGroups, flatGroupOptions,
      currentGroupId, currentGroup, currentSubGroups,
      viewMode, filterLabelIds, filteredFragments, groupFragmentCount,
      showArchived, toggleArchived,
      detailOpen, selectedFrag, detailEditing,
      openDetail, closeDetail, startEdit, cancelEdit, saveEdit, deleteSelected,
      archiveSelected, unarchiveSelected,
      editingBlocks, editingNote, editingHeader, editingLabelIds,
      addBlock, removeBlock, moveBlock,
      addDialog, draftBlocks, draftNote, draftHeader, draftLabelIds, draftGroupId, saving, draftHeaderTouched,
      openAdd, addDraftBlock, removeDraftBlock, addFragment,
      groupDialog, editingGroup, savingGroup,
      openCreateGroup, openEditGroup, saveGroup, confirmDeleteGroup,
      groupMemberDialog, fragmentToGroup, targetGroupId,
      openMoveToGroup, confirmMoveToGroup,
      captureMode,
      organizeFragments, organizeSelected, organizeBulkGroupId, organizeSaving, organizeSelectedFrag,
      organizeToggle, organizeToggleAll, organizeBulkMove, organizeQuickMove,
      organizeDeleteOne, organizeDeleteSelected,
      reindexStatus, triggerReindex,
      fmtDate, fragmentSummary, copyBlock, setBlockType, renderMd,
      expandedLongs, toggleLong,
    }
  },
})
