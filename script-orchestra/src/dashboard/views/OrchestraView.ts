import { defineComponent, ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { toolIcons } from '../icons/toolIcons'
import * as api from '../service/DashboardService'
import type { LayoutItem, FolderItem } from '../service/DashboardService'

// Code-defined tool registry — the source of truth for what tools exist.
// key matches the slug used in toolIcons. Layout only references these keys.
export interface Tool { key: string; name: string; path: string; testid?: string }
const TOOLS: Tool[] = [
  { key: 'manga-classifier',       name: 'Manga Classifier',       path: '/manga-classifier' },
  { key: 'photo-classifier',       name: 'Photo Classifier',       path: '/photo-classifier' },
  { key: 'manga-viewer',           name: 'Manga Viewer',           path: '/manga-viewer' },
  { key: 'roadmap',                name: 'Roadmap',                path: '/roadmap' },
  { key: 'pdf-converter',          name: 'PDF Converter',          path: '/pdf-converter' },
  { key: 'unzip',                  name: 'Unzip',                  path: '/unzip' },
  { key: 'duplicate-finder',       name: 'Duplicate Finder',       path: '/duplicate-finder', testid: 'duplicate-finder' },
  { key: 'video-duplicate-finder', name: 'Video Duplicate Finder', path: '/video-duplicate-finder', testid: 'video-duplicate-finder' },
  { key: 'clipboard-share',        name: 'Clipboard Share',        path: '/clipboard-share' },
  { key: 'caffeinate',             name: 'Caffeinate',             path: '/caffeinate' },
  { key: 'browser-agent',          name: 'Browser Agent',          path: '/browser-agent' },
  { key: 'assistant',              name: 'Assistant',              path: '/assistant' },
  { key: 'file-git',               name: 'File-Git',               path: '/file-git' },
  { key: 'memory-curve',           name: 'Memory Curve',           path: '/memory-curve' },
  { key: 'knowledge-vault',        name: 'Knowledge Vault',        path: '/knowledge-vault' },
  { key: 'translator',             name: 'Translator',             path: '/translator' },
  { key: 'claude-bridge',          name: 'Claude Bridge',          path: '/claude-bridge' },
  { key: 'proxy-forward',          name: 'Proxy Forward',          path: '/proxy-forward' },
]

const TOOL_BY_KEY: Record<string, Tool> = Object.fromEntries(TOOLS.map((t) => [t.key, t]))

// Client-side grid model: each cell is a single tool or a folder of tools.
export type Cell =
  | { type: 'tool'; key: string }
  | { type: 'folder'; id: string; name: string; keys: string[] }

/**
 * Reconcile a backend layout against the code-defined tool list:
 * keep valid refs in order, drop removed keys, append never-mentioned tools
 * (so tools added by another session never silently disappear).
 */
export function mergeLayout(items: LayoutItem[]): Cell[] {
  const seen = new Set<string>()
  const cells: Cell[] = []
  for (const it of items || []) {
    if (it.type === 'tool') {
      if (TOOL_BY_KEY[it.key] && !seen.has(it.key)) { seen.add(it.key); cells.push({ type: 'tool', key: it.key }) }
    } else if (it.type === 'folder') {
      const keys = (it.keys || []).filter((k) => TOOL_BY_KEY[k] && !seen.has(k))
      keys.forEach((k) => seen.add(k))
      if (keys.length) cells.push({ type: 'folder', id: it.id, name: it.name || 'Folder', keys })
    }
  }
  for (const t of TOOLS) {
    if (!seen.has(t.key)) { seen.add(t.key); cells.push({ type: 'tool', key: t.key }) }
  }
  return cells
}

function cellsToLayout(cells: Cell[]): LayoutItem[] {
  return cells.map((c) =>
    c.type === 'tool'
      ? { type: 'tool', key: c.key }
      : { type: 'folder', id: c.id, name: c.name, keys: c.keys } as FolderItem,
  )
}

let _folderSeq = 0
function newFolderId(): string {
  _folderSeq += 1
  return `folder-${_folderSeq}-${Math.floor(performance.now()).toString(36)}`
}

export default defineComponent({
  name: 'OrchestraView',
  setup() {
    const router = useRouter()
    const cells = ref<Cell[]>([])
    const openFolderId = ref<string | null>(null)
    const dragKey = ref<string | null>(null)      // key of tool being dragged (grid)
    const overCell = ref<number | null>(null)      // index currently hovered as drop target
    let saveTimer: any = null
    let loaded = false

    function toolOf(key: string): Tool | undefined { return TOOL_BY_KEY[key] }

    const openFolder = computed<Cell | null>(() =>
      cells.value.find((c) => c.type === 'folder' && c.id === openFolderId.value) || null)

    async function load() {
      try {
        cells.value = mergeLayout((await api.getLayout()).items)
      } catch {
        cells.value = mergeLayout([])
      }
      loaded = true
    }

    function persist() {
      if (!loaded) return
      if (saveTimer) clearTimeout(saveTimer)
      saveTimer = setTimeout(() => {
        api.saveLayout(cellsToLayout(cells.value)).catch(() => { /* best-effort */ })
      }, 500)
    }
    watch(cells, persist, { deep: true })

    function goTo(path?: string) {
      if (dragKey.value) return          // don't navigate on drag release
      if (path) router.push(path)
    }

    // ---- grid drag (native HTML5): reorder, or stack onto a card to group ----
    function onDragStart(e: DragEvent, index: number) {
      const c = cells.value[index]
      if (!c || c.type !== 'tool') { e.preventDefault(); return }  // only tools initiate stack/drag
      dragKey.value = c.key
      e.dataTransfer?.setData('text/plain', c.key)
      if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
    }
    function onDragOver(e: DragEvent, index: number) {
      e.preventDefault()
      overCell.value = index
    }
    function onDragLeave(index: number) {
      if (overCell.value === index) overCell.value = null
    }
    function onDrop(e: DragEvent, targetIndex: number) {
      e.preventDefault()
      overCell.value = null
      const key = dragKey.value
      dragKey.value = null
      if (!key) return
      const from = cells.value.findIndex((c) => c.type === 'tool' && c.key === key)
      const target = cells.value[targetIndex]
      if (from === -1 || !target || from === targetIndex) return

      if (target.type === 'folder') {
        // drop into an existing folder
        if (!target.keys.includes(key)) target.keys.push(key)
        cells.value.splice(from, 1)
      } else if (target.type === 'tool') {
        // stack two tools → new folder in the target's slot
        const folder: Cell = { type: 'folder', id: newFolderId(), name: 'Folder', keys: [target.key, key] }
        // remove dragged first, then replace target
        cells.value.splice(from, 1)
        const ti = cells.value.findIndex((c) => c.type === 'tool' && c.key === target.key)
        cells.value.splice(ti, 1, folder)
      }
    }
    function onDragEnd() { dragKey.value = null; overCell.value = null }

    // Reorder: dropping on empty grid area moves the dragged tool to the end.
    function onGridDrop(e: DragEvent) {
      e.preventDefault()
      const key = dragKey.value
      dragKey.value = null; overCell.value = null
      if (!key) return
      const from = cells.value.findIndex((c) => c.type === 'tool' && c.key === key)
      if (from === -1) return
      const [moved] = cells.value.splice(from, 1)
      cells.value.push(moved)
    }

    // ---- folder interactions ----
    function openFolderView(id: string) { if (!dragKey.value) openFolderId.value = id }
    function closeFolder() { openFolderId.value = null }

    async function renameFolder(folder: Cell) {
      if (folder.type !== 'folder') return
      try {
        const { value } = await ElMessageBox.prompt('Folder name', 'Rename', {
          inputValue: folder.name, confirmButtonText: 'Save', cancelButtonText: 'Cancel',
        })
        folder.name = (value || 'Folder').trim() || 'Folder'
      } catch { /* cancelled */ }
    }

    function removeFromFolder(folder: Cell, key: string) {
      if (folder.type !== 'folder') return
      folder.keys = folder.keys.filter((k) => k !== key)
      const fi = cells.value.findIndex((c) => c.type === 'folder' && c.id === folder.id)
      cells.value.splice(fi + 1, 0, { type: 'tool', key })
      // folder with <=1 member dissolves (macOS behavior)
      if (folder.keys.length <= 1) {
        const leftover = folder.keys[0]
        const idx = cells.value.findIndex((c) => c.type === 'folder' && c.id === folder.id)
        if (leftover) cells.value.splice(idx, 1, { type: 'tool', key: leftover })
        else cells.value.splice(idx, 1)
        closeFolder()
      }
    }

    onMounted(load)

    return {
      cells, toolIcons, toolOf, goTo, dragKey, overCell,
      onDragStart, onDragOver, onDragLeave, onDrop, onDragEnd, onGridDrop,
      openFolderId, openFolder, openFolderView, closeFolder,
      renameFolder, removeFromFolder,
    }
  },
})
