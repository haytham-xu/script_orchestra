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

    function templateKey(scope: 'search', fragId: number | null | undefined, blockIdx: number): string {
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

    async function copyBlockFilled(blk: ContentBlock, key?: string, evt?: Event) {
      if (blk.type === 'template' && key && !templateAllArgsFilled(key, blk)) {
        blurCopyTrigger(evt)
        return
      }
      const text = blk.type === 'template'
        ? (() => {
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
          return rendered
        })()
        : blk.body
      try { await navigator.clipboard.writeText(text)
      } catch {
        // silently ignore in search view
      }
      blurCopyTrigger(evt)
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
      templateKey, getTemplateArgNames, getTemplateArgs, setTemplateArg, addTemplateArg, removeTemplateArg,
      getTemplateGenerated, hasTemplateGenerated,
      templateAllArgsFilled, copyBlockFilled,
      expandedLongs, toggleLong,
    }
  },
})
