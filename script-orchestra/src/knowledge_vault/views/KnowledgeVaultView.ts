import { defineComponent, ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { marked } from 'marked'
import * as api from '../service/KnowledgeVaultService'
import type { RawFragment, Label, ContentBlock } from '../service/Model'
import { fragmentSummary } from '../service/Model'

export default defineComponent({
  name: 'KnowledgeVaultView',
  setup() {
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
    const router = useRouter()
    function goBack() { router.push('/') }
    function goCapture() { router.push({ name: 'knowledge-vault' }) }

    const labels = ref<Label[]>([])
    const labelMap = ref<Record<number, Label>>({})

    async function loadLabels() {
      labels.value = await api.getLabels()
      labelMap.value = Object.fromEntries(labels.value.map(l => [l.id, l]))
    }

    // ---- search state ----
    const queryText = ref('')
    const results = ref<RawFragment[]>([])
    const searched = ref(false)
    const searching = ref(false)
    const searchDetail = ref<RawFragment | null>(null)

    async function runSearch() {
      if (!queryText.value.trim()) return
      searching.value = true
      try {
        results.value = await api.search(queryText.value, 10)
        searched.value = true
        searchDetail.value = null
      } catch (e: any) {
        // ElMessage not imported here — errors are silent on search page
      } finally {
        searching.value = false
      }
    }

    function fmtDate(iso: string): string {
      if (!iso) return '—'
      const d = new Date(iso)
      return isNaN(d.getTime()) ? '—' : d.toLocaleDateString()
    }

    function renderMd(text: string): string {
      return marked.parse(text || '', { async: false }) as string
    }

    type TableData = { headers: string[]; rows: string[][] }
    function tableForView(body: string): TableData {
      const fallback: TableData = { headers: ['', ''], rows: [['', '']] }
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
        // Ignore: non-JSON table payloads fall back to default shape
      }
      return fallback
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

    function getTablePersistKey(scope: 'search', fragId: number, blockIdx: number, colCount: number): string {
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

    const expandedLongs = ref(new Set<ContentBlock>())
    function toggleLong(blk: ContentBlock) {
      if (expandedLongs.value.has(blk)) expandedLongs.value.delete(blk)
      else expandedLongs.value.add(blk)
      expandedLongs.value = new Set(expandedLongs.value)
    }

    // Load labels for tag display in results
    void loadTableWidths()
    loadLabels()

    return {
      goBack, goCapture,
      labelMap, labels,
      queryText, results, searched, searching, searchDetail,
      runSearch, fmtDate, fragmentSummary, renderMd, tableForView,
      tableRowsForView, tableColProp,
      getTablePersistKey, getTableColWidth, onTableHeaderDragEnd,
      expandedLongs, toggleLong,
    }
  },
})
