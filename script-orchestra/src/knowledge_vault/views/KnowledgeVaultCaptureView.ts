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
    function goBack() { router.push('/') }
    function goSearch() { router.push({ name: 'knowledge-vault-search' }) }
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
        type: b.type, body: b.body, lang: b.lang ?? '', subtitle: b.subtitle ?? '', arg_names: b.arg_names,
      }))
      editingNote.value = selectedFrag.value.note
      editingHeader.value = selectedFrag.value.header || ''
      editingLabelIds.value = [...(selectedFrag.value.label_ids || [])]
      detailEditing.value = true
    }
    function cancelEdit() { detailEditing.value = false }

    function createBlock(type: ContentBlock['type'] = 'text'): ContentBlock {
      return {
        type,
        body: '',
        subtitle: '',
        ...(type === 'code' ? { lang: '' } : {}),
        ...(type === 'template' ? { arg_names: ['arg1'] } : {}),
      }
    }

    type TableData = { headers: string[]; rows: string[][] }
    type TableWidthStore = Record<string, Record<string, number>>
    const TABLE_WIDTHS_KEY = 'knowledge_vault.table_widths.v1'

    const tableWidths = ref<TableWidthStore>({})

    function loadTableWidthsFromLocal() {
      try {
        const raw = localStorage.getItem(TABLE_WIDTHS_KEY)
        if (!raw) return
        const parsed = JSON.parse(raw)
        if (parsed && typeof parsed === 'object') tableWidths.value = parsed
      } catch {
        tableWidths.value = {}
      }
    }

    function saveTableWidthsToLocal() {
      try { localStorage.setItem(TABLE_WIDTHS_KEY, JSON.stringify(tableWidths.value))
      } catch { /* ignore localStorage failures */ }
    }

    async function loadTableWidths() {
      loadTableWidthsFromLocal()
      try {
        const remote = await api.getTableWidths()
        if (remote && typeof remote === 'object') {
          tableWidths.value = remote
          saveTableWidthsToLocal()
        }
      } catch {
        // Keep local fallback when backend fetch fails
      }
    }

    async function syncTableWidthsToServer() {
      try {
        await api.saveTableWidths(tableWidths.value)
      } catch {
        // Keep local copy even if sync fails
      }
    }

    function tableColProp(colIdx: number): string {
      return `c${colIdx}`
    }

    function tableRowsForView(body: string): Array<Record<string, string | number>> {
      const table = tableForView(body)
      return table.rows.map((cells, rowIdx) => {
        const row: Record<string, string | number> = { __idx: rowIdx }
        table.headers.forEach((_, colIdx) => {
          row[tableColProp(colIdx)] = cells[colIdx] ?? ''
        })
        return row
      })
    }

    function getTablePersistKey(scope: 'capture' | 'organize', fragId: number, blockIdx: number, colCount: number): string {
      return `${scope}:${fragId}:${blockIdx}:${colCount}`
    }

    function getTableColWidth(tableKey: string, colIdx: number): number | undefined {
      return tableWidths.value[tableKey]?.[tableColProp(colIdx)]
    }

    function onTableHeaderDragEnd(tableKey: string, newWidth: number, columnProperty?: string) {
      if (!columnProperty) return
      const width = Math.max(80, Math.round(newWidth || 0))
      if (!tableWidths.value[tableKey]) tableWidths.value[tableKey] = {}
      tableWidths.value[tableKey][columnProperty] = width
      tableWidths.value = { ...tableWidths.value }
      saveTableWidthsToLocal()
      void syncTableWidthsToServer()
    }

    function defaultTableData(): TableData {
      return { headers: ['', ''], rows: [['', '']] }
    }

    function toTableBody(data: TableData): string {
      return JSON.stringify(data)
    }

    function parseMarkdownTable(body: string): TableData | null {
      const lines = body.split('\n').map(l => l.trim()).filter(Boolean)
      if (lines.length < 2 || !lines[0].includes('|')) return null
      const parseRow = (line: string): string[] => line
        .replace(/^\|/, '')
        .replace(/\|$/, '')
        .split('|')
        .map(c => c.trim())
      const headers = parseRow(lines[0])
      if (!headers.length) return null
      const dataLines = lines.slice(2)
      const rows = dataLines
        .filter(line => line.includes('|'))
        .map(parseRow)
        .map(r => headers.map((_, idx) => r[idx] ?? ''))
      return { headers, rows: rows.length ? rows : [['', ...headers.slice(1).map(() => '')]] }
    }

    function parseTableBody(body: string): TableData {
      const fallback = defaultTableData()
      if (!body?.trim()) return fallback
      try {
        const parsed = JSON.parse(body)
        if (parsed && Array.isArray(parsed.headers) && Array.isArray(parsed.rows)) {
          const headers = parsed.headers.map((h: unknown) => String(h ?? '').trim())
          const rows = parsed.rows
            .filter((r: unknown) => Array.isArray(r))
            .map((r: unknown) => (r as unknown[]).map(c => String(c ?? '')))
            .map((r: string[]) => headers.map((_, idx) => r[idx] ?? ''))
          return { headers, rows: rows.length ? rows : [headers.map(() => '')] }
        }
      } catch {
        const md = parseMarkdownTable(body)
        if (md) return md
      }
      return fallback
    }

    function ensureTableBody(block: ContentBlock) {
      if (block.type !== 'table') return
      const parsed = parseTableBody(block.body)
      block.body = toTableBody(parsed)
    }

    function tableDataOf(block: ContentBlock): TableData {
      ensureTableBody(block)
      return parseTableBody(block.body)
    }

    function updateTableData(block: ContentBlock, next: TableData) {
      block.body = toTableBody(next)
    }

    function getTableHeaders(block: ContentBlock): string[] {
      return tableDataOf(block).headers
    }

    function getTableRows(block: ContentBlock): string[][] {
      return tableDataOf(block).rows
    }

    function updateTableHeader(block: ContentBlock, colIdx: number, value: string) {
      const data = tableDataOf(block)
      data.headers[colIdx] = value
      updateTableData(block, data)
    }

    function updateTableCell(block: ContentBlock, rowIdx: number, colIdx: number, value: string) {
      const data = tableDataOf(block)
      data.rows[rowIdx][colIdx] = value
      updateTableData(block, data)
    }

    function addTableRow(block: ContentBlock) {
      const data = tableDataOf(block)
      data.rows.push(data.headers.map(() => ''))
      updateTableData(block, data)
    }

    function removeTableRow(block: ContentBlock, rowIdx: number) {
      const data = tableDataOf(block)
      if (data.rows.length <= 1) return
      data.rows.splice(rowIdx, 1)
      updateTableData(block, data)
    }

    function addTableColumn(block: ContentBlock) {
      const data = tableDataOf(block)
      data.headers.push('')
      data.rows = data.rows.map(r => [...r, ''])
      updateTableData(block, data)
    }

    function removeTableColumn(block: ContentBlock, colIdx: number) {
      const data = tableDataOf(block)
      if (data.headers.length <= 1) return
      data.headers.splice(colIdx, 1)
      data.rows = data.rows.map(r => r.filter((_, idx) => idx !== colIdx))
      updateTableData(block, data)
    }

    function tableForView(body: string): TableData {
      return parseTableBody(body)
    }

    function insertEditingBlockAt(index: number, type: ContentBlock['type'] = 'text') {
      const insertAt = Math.max(0, Math.min(index, editingBlocks.value.length))
      const next = createBlock(type)
      if (next.type === 'table') next.body = toTableBody(defaultTableData())
      editingBlocks.value.splice(insertAt, 0, next)
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
    function insertDraftBlockAt(index: number, type: ContentBlock['type'] = 'text') {
      const insertAt = Math.max(0, Math.min(index, draftBlocks.value.length))
      const next = createBlock(type)
      if (next.type === 'table') next.body = toTableBody(defaultTableData())
      draftBlocks.value.splice(insertAt, 0, next)
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
      if (blocks[idx].type === 'table') ensureTableBody(blocks[idx])
      if (blocks[idx].type === 'template') {
        ensureTemplateArgNames(blocks[idx])
      }
    }
    async function copyBlock(text: string) {
      try { await navigator.clipboard.writeText(text); ElMessage.success('Copied') }
      catch { ElMessage.error('Copy failed') }
    }

    const templateArgs = ref<Record<string, string[]>>({})
    const templateGenerated = ref<Record<string, string>>({})

    function detectTemplateVarNames(body: string): string[] {
      const names: string[] = []
      const seen = new Set<string>()
      const re = /\$\{?([a-zA-Z_][a-zA-Z0-9_]*)\}?/g
      let m: RegExpExecArray | null
      while ((m = re.exec(body || '')) !== null) {
        const name = m[1]
        if (!seen.has(name)) {
          seen.add(name)
          names.push(name)
        }
      }
      return names
    }

    function ensureTemplateArgNames(blk: ContentBlock): string[] {
      if (Array.isArray(blk.arg_names) && blk.arg_names.length > 0) {
        blk.arg_names = blk.arg_names.map(v => String(v ?? ''))
        return blk.arg_names
      }
      const detected = detectTemplateVarNames(blk.body || '')
      if (detected.length > 0) {
        blk.arg_names = detected
        return blk.arg_names
      }
      const count = Math.max(1, Number((blk as any).arg_count || 1))
      blk.arg_names = Array.from({ length: count }, (_, i) => `arg${i + 1}`)
      return blk.arg_names
    }

    function getTemplateArgNames(blk: ContentBlock): string[] {
      return ensureTemplateArgNames(blk)
    }

    function setTemplateArgName(blk: ContentBlock, argIdx: number, value: string) {
      const names = [...getTemplateArgNames(blk)]
      names[argIdx] = value
      blk.arg_names = names
    }

    function addTemplateVar(blk: ContentBlock) {
      const names = [...getTemplateArgNames(blk)]
      names.push(`arg${names.length + 1}`)
      blk.arg_names = names
    }

    function removeTemplateVar(blk: ContentBlock, argIdx: number) {
      const names = [...getTemplateArgNames(blk)]
      if (names.length <= 1) return
      names.splice(argIdx, 1)
      blk.arg_names = names
    }

    const draggingTemplateVar = ref<{ blk: ContentBlock | null; index: number }>({ blk: null, index: -1 })

    function moveTemplateVar(blk: ContentBlock, argIdx: number, direction: -1 | 1) {
      const names = [...getTemplateArgNames(blk)]
      const targetIdx = argIdx + direction
      if (targetIdx < 0 || targetIdx >= names.length) return
      const [picked] = names.splice(argIdx, 1)
      names.splice(targetIdx, 0, picked)
      blk.arg_names = names
    }

    function startTemplateVarDrag(blk: ContentBlock, argIdx: number) {
      draggingTemplateVar.value = { blk, index: argIdx }
    }

    function dropTemplateVar(blk: ContentBlock, targetIdx: number) {
      const { blk: sourceBlk, index: fromIdx } = draggingTemplateVar.value
      draggingTemplateVar.value = { blk: null, index: -1 }
      if (!sourceBlk || sourceBlk !== blk || fromIdx < 0 || fromIdx === targetIdx) return
      const names = [...getTemplateArgNames(blk)]
      if (fromIdx >= names.length || targetIdx < 0 || targetIdx >= names.length) return
      const [picked] = names.splice(fromIdx, 1)
      names.splice(targetIdx, 0, picked)
      blk.arg_names = names
    }

    function templateKey(scope: 'capture' | 'organize', fragId: number | null | undefined, blockIdx: number): string {
      return `${scope}:${fragId ?? 0}:${blockIdx}`
    }

    function ensureTemplateArgs(key: string, blk: ContentBlock): string[] {
      const expected = getTemplateArgNames(blk).length
      const existing = templateArgs.value[key] || []
      const next = Array.from({ length: Math.max(expected, existing.length, 1) }, (_, i) => existing[i] ?? '')
      templateArgs.value[key] = next
      return next
    }

    function getTemplateArgs(key: string, blk: ContentBlock): string[] {
      return ensureTemplateArgs(key, blk)
    }

    function setTemplateArg(key: string, blk: ContentBlock, argIdx: number, value: string) {
      const args = [...ensureTemplateArgs(key, blk)]
      args[argIdx] = value
      templateArgs.value[key] = args
    }

    function addTemplateArg(key: string, blk: ContentBlock) {
      const args = [...ensureTemplateArgs(key, blk), '']
      templateArgs.value[key] = args
    }

    function removeTemplateArg(key: string, blk: ContentBlock, argIdx: number) {
      const args = [...ensureTemplateArgs(key, blk)]
      if (args.length <= 1) return
      args.splice(argIdx, 1)
      templateArgs.value[key] = args
    }

    function getTemplateGenerated(key: string): string {
      return templateGenerated.value[key] || ''
    }

    function hasTemplateGenerated(key: string): boolean {
      return !!templateGenerated.value[key]
    }

    function templateAllArgsFilled(key: string, blk: ContentBlock): boolean {
      const names = getTemplateArgNames(blk)
      const args = ensureTemplateArgs(key, blk)
      return names.every((name, idx) => name.trim().length > 0 && (args[idx] || '').trim().length > 0)
    }

    function fillTemplateBody(body: string, args: string[]): string {
      return (body || '').replace(/\$\{?([a-zA-Z_][a-zA-Z0-9_]*)\}?/g, (_, token) => {
        return `$${token}`
      })
    }

    function blurCopyTrigger(evt?: Event) {
      const target = evt?.currentTarget as HTMLElement | null | undefined
      target?.blur?.()
      if (typeof document !== 'undefined') {
        const active = document.activeElement as HTMLElement | null
        active?.blur?.()
      }
    }

    function copyBlockFilled(blk: ContentBlock, key?: string, evt?: Event) {
      if (blk.type !== 'template') {
        copyBlock(blk.body)
        blurCopyTrigger(evt)
        return
      }
      if (key && !templateAllArgsFilled(key, blk)) {
        ElMessage.warning('Fill all template variable values before copy')
        blurCopyTrigger(evt)
        return
      }
      const args = key ? ensureTemplateArgs(key, blk) : Array.from({ length: getTemplateArgNames(blk).length }, () => '')
      let rendered = fillTemplateBody(blk.body, args)
      const names = getTemplateArgNames(blk)
      names.forEach((name, idx) => {
        if (!name.trim()) return
        const val = args[idx] ?? ''
        const esc = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
        rendered = rendered
          .replace(new RegExp(`\\$\\{${esc}\\}`, 'g'), val)
          .replace(new RegExp(`\\$${esc}\\b`, 'g'), val)
      })
      if (key) templateGenerated.value[key] = rendered
      copyBlock(rendered)
      blurCopyTrigger(evt)
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
      await loadTableWidths()
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
      insertEditingBlockAt, removeBlock, moveBlock,
      addDialog, draftBlocks, draftNote, draftHeader, draftLabelIds, draftGroupId, saving, draftHeaderTouched,
      openAdd, insertDraftBlockAt, removeDraftBlock, addFragment,
      groupDialog, editingGroup, savingGroup,
      openCreateGroup, openEditGroup, saveGroup, confirmDeleteGroup,
      groupMemberDialog, fragmentToGroup, targetGroupId,
      openMoveToGroup, confirmMoveToGroup,
      captureMode,
      organizeFragments, organizeSelected, organizeBulkGroupId, organizeSaving, organizeSelectedFrag,
      organizeToggle, organizeToggleAll, organizeBulkMove, organizeQuickMove,
      organizeDeleteOne, organizeDeleteSelected,
      reindexStatus, triggerReindex,
      fmtDate, fragmentSummary, copyBlock, copyBlockFilled, setBlockType, renderMd,
      templateKey, getTemplateArgs, setTemplateArg, addTemplateArg, removeTemplateArg,
      templateAllArgsFilled,
      getTemplateGenerated, hasTemplateGenerated,
      getTemplateArgNames, setTemplateArgName, addTemplateVar, removeTemplateVar, moveTemplateVar,
      startTemplateVarDrag, dropTemplateVar,
      tableForView,
      tableRowsForView, tableColProp,
      getTablePersistKey, getTableColWidth, onTableHeaderDragEnd,
      getTableHeaders, getTableRows,
      updateTableHeader, updateTableCell,
      addTableRow, removeTableRow, addTableColumn, removeTableColumn,
      expandedLongs, toggleLong,
    }
  },
})
