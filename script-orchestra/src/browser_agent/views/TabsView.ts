import { defineComponent, ref, reactive, computed, onMounted, watch, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Setting } from '@element-plus/icons-vue'
import MockLiveView from '@/browser_agent/views/MockLiveView.vue'
import { vPdndDrag, vPdndDrop, vPdndGroupHdr, vPdndLiveRow, useDndMonitor } from './dnd'
import type { DragPayload, DropPayload, MonitorDropEvent, MonitorDragEvent } from './dnd'
import { getSettings, updateSettings } from '@/browser_agent/service/BrowserAgentService'
import type { TabArchiveSettings } from '@/browser_agent/service/Model'
import {
  closeTabs,
  groupTabsByDomain,
  mergeTabs,
  tabArchiveCreateLabel,
  tabArchiveDeleteRecord,
  tabArchiveListLabels,
  tabArchiveRestore,
  tabArchiveSelected,
  tabArchiveSetRecordLabels,
  tabArchiveSnapshot,
  tabArchiveUpdateRecord,
  tabArchiveReplaceUrl,
  tabArchiveCreateGroup,
  tabArchiveDeleteGroup,
  tabArchiveRenameGroup,
  tabArchiveSetRecordGroup,
  tabArchiveSetLiveTabsGroup,
  tabArchiveSetLiveTabOrder,
  tabArchiveBatchSetLiveTabOrders,
  tabArchiveGroupAsWindow,
  tabArchiveSetLiveTabCustomHeader,
  tabArchiveSortByGroup,
  tabArchiveSplitByGroups,
  tabArchiveReorderRecord,
  tabArchiveMoveGroup,
  tabArchiveGetShelf,
  tabArchiveCreateShelfItem,
  tabArchiveDeleteShelfItem,
  tabArchiveSetShelfItemOrder,
  tabArchiveOpenShelfItem,
  tabArchiveSyncShelfFromBrowserBookmarks,
  tabArchiveExportShelfToBrowserBookmarks,
  tabArchiveSetShelfItemGroup,
} from '@/browser_agent/service/BrowserAgentService'
import type { GroupScope } from '@/browser_agent/service/BrowserAgentService'
import type {
  HeatLevel,
  TabArchiveGroup,
  TabArchiveLabel,
  TabArchiveLiveCard,
  TabArchiveRecord,
  TabArchiveRestoreResultRow,
  TabArchiveReplaceUrlPreviewRow,
  ShelfItem,
} from '@/browser_agent/service/Model'

type Pane = 'live' | 'archive' | 'shelf' | 'mock'
type RestoreDestination = 'new_window' | 'current_window'

type EternalFilter = 'all' | 'eternal' | 'not_eternal'

type TreeNode =
  | { type: 'group'; group: TabArchiveGroup; children: TreeNode[] }
  | { type: 'tab'; card: TabArchiveLiveCard }

type ArchiveTreeNode =
  | { type: 'group'; group: TabArchiveGroup; children: ArchiveTreeNode[] }
  | { type: 'record'; record: TabArchiveRecord }

type LiveRenderItem =
  | { kind: 'window'; windowId: number; tabCount: number; dragKey: string }
  | { kind: 'group'; group: TabArchiveGroup; depth: number; tabCount: number; ancestorIds: number[]; dragKey: string }
  | { kind: 'tab'; card: TabArchiveLiveCard; depth: number; ancestorIds: number[]; dragKey: string }

type ArchiveRenderItem =
  | { kind: 'group'; group: TabArchiveGroup; depth: number; recordCount: number; ancestorIds: number[]; dragKey: string }
  | { kind: 'record'; record: TabArchiveRecord; depth: number; ancestorIds: number[]; dragKey: string }

type ShelfRenderItem =
  | { kind: 'group'; group: TabArchiveGroup; depth: number; itemCount: number; ancestorIds: number[]; dragKey: string }
  | { kind: 'item'; item: ShelfItem; depth: number; ancestorIds: number[]; dragKey: string }

type ShelfTreeNode =
  | { type: 'group'; group: TabArchiveGroup; children: ShelfTreeNode[] }
  | { type: 'item'; item: ShelfItem }

const TAB_ARCHIVE_LOG_PREFIX = '[tab-archive-ui]'

function uiDebug(event: string, payload?: unknown) {
  if (!import.meta.env.DEV) {
    return
  }
  if (payload === undefined) {
    console.debug(`${TAB_ARCHIVE_LOG_PREFIX} ${event}`)
    return
  }
  console.debug(`${TAB_ARCHIVE_LOG_PREFIX} ${event}`, payload)
}

function uiWarn(event: string, payload?: unknown) {
  if (!import.meta.env.DEV) {
    return
  }
  if (payload === undefined) {
    console.warn(`${TAB_ARCHIVE_LOG_PREFIX} ${event}`)
    return
  }
  console.warn(`${TAB_ARCHIVE_LOG_PREFIX} ${event}`, payload)
}

function uiError(event: string, payload?: unknown) {
  if (!import.meta.env.DEV) {
    return
  }
  if (payload === undefined) {
    console.error(`${TAB_ARCHIVE_LOG_PREFIX} ${event}`)
    return
  }
  console.error(`${TAB_ARCHIVE_LOG_PREFIX} ${event}`, payload)
}

function errorMessage(error: unknown, fallback: string): string {
  const e = error as { response?: { data?: { error?: string } }; message?: string }
  return e?.response?.data?.error || e?.message || fallback
}

function uniqueNumbers(values: number[]): number[] {
  return Array.from(new Set(values.filter(v => Number.isInteger(v) && v > 0)))
}

function restoreFailureReason(error: string): string {
  const text = (error || '').toLowerCase()
  if (text.includes('extension_outdated') || text.includes('unknown command type')) return 'extension-outdated'
  if (text.includes('record_not_found')) return 'record-not-found'
  if (text.includes('focus_failed')) return 'focus-failed'
  if (text.includes('open_failed')) return 'open-failed'
  if (text.includes('missing_result')) return 'missing-extension-result'
  return 'other'
}

function buildRestoreFailureSummary(rows: TabArchiveRestoreResultRow[]): {
  headline: string
  details: string
} {
  const failed = rows.filter(row => !row.ok)
  if (failed.length === 0) {
    return {
      headline: '',
      details: '',
    }
  }

  const reasonCounts = new Map<string, number>()
  failed.forEach(row => {
    const reason = restoreFailureReason(row.error)
    reasonCounts.set(reason, (reasonCounts.get(reason) || 0) + 1)
  })

  const reasonLine = Array.from(reasonCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([reason, count]) => `${reason}=${count}`)
    .join(', ')

  const exampleLines = failed.slice(0, 5).map(row => {
    const name = (row.title || '').trim() || row.url || `record#${row.record_id}`
    return `- ${name}: ${row.error || 'unknown_error'}`
  })

  const details = [
    `Failure reasons: ${reasonLine}`,
    '',
    'Examples:',
    ...exampleLines,
  ].join('\n')

  return {
    headline: reasonLine,
    details,
  }
}

export default defineComponent({
  name: 'TabsView',
  components: { Setting, MockLiveView },
  directives: {
    pdndDrag: vPdndDrag, pdndDrop: vPdndDrop, pdndGroupHdr: vPdndGroupHdr, pdndLiveRow: vPdndLiveRow,
    focus: { mounted: (el: HTMLElement) => el.focus() },
  },
  setup() {
    const router = useRouter()
    const route = useRoute()

    // Settings drawer (tabArchive config)
    const TAB_ARCHIVE_DEFAULTS: TabArchiveSettings = {
      heatThresholds: { high: 4, medium: 2, low: 0.8 },
      expireDays: 365,
    }
    const settingsOpen = ref(false)
    const settingsCfg = reactive<TabArchiveSettings>(JSON.parse(JSON.stringify(TAB_ARCHIVE_DEFAULTS)))
    const settingsSaving = ref(false)


    async function openSettings() {
      const s = await getSettings()
      const c = s.tabArchive || TAB_ARCHIVE_DEFAULTS
      Object.assign(settingsCfg, JSON.parse(JSON.stringify(c)))
      settingsOpen.value = true
    }
    async function saveSettings() {
      settingsSaving.value = true
      try {
        await updateSettings({ tabArchive: JSON.parse(JSON.stringify(settingsCfg)) })
        settingsOpen.value = false
        ElMessage.success('Settings saved')
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.error || e?.message || 'Failed to save')
      } finally {
        settingsSaving.value = false
      }
    }

    const loading = ref(false)
    const busy = ref(false)
    const activePane = computed<Pane>({
      get() {
        const q = route.query.tab
        return (q === 'archive' || q === 'live' || q === 'shelf' || q === 'mock') ? q : 'live'
      },
      set(val: Pane) {
        router.replace({ query: { ...route.query, tab: val } })
      },
    })
    const search = ref('')

    const liveRows = ref<TabArchiveLiveCard[]>([])
    const archiveRows = ref<TabArchiveRecord[]>([])
    const extensionAvailable = ref(true)
    const liveError = ref('')

    const selectedLiveTabIds = ref<Set<number>>(new Set())
    const selectedArchiveIds = ref<Set<number>>(new Set())
    const archiveCache = ref<Record<number, TabArchiveRecord>>({})

    const labels = ref<TabArchiveLabel[]>([])
    const liveGroupTree = ref<TabArchiveGroup[]>([])
    const archiveGroupTree = ref<TabArchiveGroup[]>([])
    const shelfGroupTree = ref<TabArchiveGroup[]>([])
    // Flat ordered list of dragKeys per windowId for the Live pane.
    // 'grp-{id}' for groups, 'tab-{tabId}' for tabs. Groups and tabs interleave freely.
    const liveOrderByWindow = ref<Map<number, string[]>>(new Map())
    const collapsedLiveGroups = ref<Set<number>>(new Set())
    const collapsedArchiveGroups = ref<Set<number>>(new Set())

    // Inline custom_header editing state
    const editingHeaderTabId = ref<number | null>(null)
    const editingHeaderValue = ref('')

    function startEditHeader(card: TabArchiveLiveCard) {
      editingHeaderTabId.value = card.tab_id
      editingHeaderValue.value = card.custom_header ?? ''
    }

    function cancelEditHeader() {
      editingHeaderTabId.value = null
      editingHeaderValue.value = ''
    }

    async function saveCustomHeader(card: TabArchiveLiveCard) {
      const tabId = card.tab_id
      const value = editingHeaderValue.value.trim() || null
      editingHeaderTabId.value = null
      // Optimistic update
      const idx = liveRows.value.findIndex(t => t.tab_id === tabId)
      if (idx >= 0) liveRows.value[idx] = { ...liveRows.value[idx], custom_header: value }
      tabArchiveSetLiveTabCustomHeader(tabId, value).catch(err => {
        uiWarn('save-custom-header.failed', err)
        // Revert on error
        if (idx >= 0) liveRows.value[idx] = { ...liveRows.value[idx], custom_header: card.custom_header }
      })
    }


    const liveGroupEditVisible = ref(false)
    const liveGroupEditId = ref<number | null>(null)
    const liveGroupEditName = ref('')

    // Create group dialog (replaces ElMessageBox.prompt to handle IME correctly)
    const createGroupDialogVisible = ref(false)
    const createGroupDialogName = ref('')
    const createGroupDialogParentId = ref<number | null>(null)
    let createGroupDialogResolve: ((group: TabArchiveGroup | null) => void) | null = null
    let createGroupDialogClosedAt = 0  // timestamp to debounce IME Enter bleed-through

    function openCreateGroupDialog(parentId?: number | null): Promise<TabArchiveGroup | null> {
      // Guard: ignore if already open or dialog just closed within 400ms (IME Enter bleed-through)
      if (createGroupDialogVisible.value || Date.now() - createGroupDialogClosedAt < 400) {
        return Promise.resolve(null)
      }
      createGroupDialogName.value = ''
      createGroupDialogParentId.value = parentId ?? null
      createGroupDialogVisible.value = true
      return new Promise(resolve => { createGroupDialogResolve = resolve })
    }

    async function confirmCreateGroupDialog() {
      const name = createGroupDialogName.value.trim()
      if (!name) return
      createGroupDialogVisible.value = false
      createGroupDialogClosedAt = Date.now()
      busy.value = true
      try {
        const group = await tabArchiveCreateGroup(name, createGroupDialogParentId.value, activeScope())
        createGroupDialogResolve?.({ ...group, children: [] })
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to create group'))
        createGroupDialogResolve?.(null)
      } finally {
        busy.value = false
        createGroupDialogResolve = null
      }
    }

    function cancelCreateGroupDialog() {
      createGroupDialogVisible.value = false
      createGroupDialogClosedAt = Date.now()
      // Only resolve if still pending (not already resolved by confirmCreateGroupDialog)
      if (createGroupDialogResolve) {
        createGroupDialogResolve(null)
        createGroupDialogResolve = null
      }
    }

    function openLiveGroupEdit(group: TabArchiveGroup) {
      liveGroupEditId.value = group.id
      liveGroupEditName.value = group.name
      liveGroupEditVisible.value = true
    }

    async function saveLiveGroupEdit() {
      const id = liveGroupEditId.value
      const name = liveGroupEditName.value.trim()
      if (!id || !name) return
      try {
        await tabArchiveRenameGroup(id, name, 'live')
        liveGroupEditVisible.value = false
        silentRefreshSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to rename group'))
      }
    }

    const liveDndIndicator = ref<{ key: string; edge: 'top' | 'bottom' | 'into' } | null>(null)

    const collectVisible = ref(false)
    const collectGroupId = ref<number | null>(null)
    const collectGroupName = ref('')
    const collectQuery = ref('')
    const collectWindowId = ref<number | null>(null)
    const collectSaving = ref(false)

    const collectMatches = computed(() => {
      const q = collectQuery.value.trim().toLowerCase()
      if (!q || collectWindowId.value === null) return []
      return liveRows.value.filter(t =>
        t.window_id === collectWindowId.value &&
        (t.group_id ?? null) === null &&
        (t.url.toLowerCase().includes(q) || t.title.toLowerCase().includes(q))
      )
    })

    function openCollect(group: TabArchiveGroup, windowId: number) {
      collectGroupId.value = group.id
      collectGroupName.value = group.name
      collectWindowId.value = windowId
      collectQuery.value = ''
      collectVisible.value = true
    }

    async function runCollect() {
      const matches = collectMatches.value
      const ids = matches.map(t => t.tab_id)
      const gid = collectGroupId.value
      if (!ids.length || gid === null) return
      collectSaving.value = true

      // Optimistic update: move matched tabs into the group immediately
      const idSet = new Set(ids)
      liveRows.value = liveRows.value.map(t =>
        idSet.has(t.tab_id) ? { ...t, group_id: gid } : t
      )

      // Move their keys in liveOrderByWindow: remove from wherever they are, insert after group header
      const tabKeys = ids.map(id => 'tab-' + id)
      const tabKeySet = new Set(tabKeys)
      const groupKey = 'grp-' + gid
      const newMap = new Map(liveOrderByWindow.value)
      newMap.forEach((order, wid) => {
        // Remove matched tab keys from this window's order
        const filtered = order.filter(k => !tabKeySet.has(k))
        newMap.set(wid, filtered)
      })
      // Insert the tab keys after the group header in whichever window contains it
      let inserted = false
      newMap.forEach((order, wid) => {
        const gIdx = order.indexOf(groupKey)
        if (gIdx < 0 || inserted) return
        // Find insertion point: after last existing member of this group
        let insertAt = gIdx + 1
        for (let i = gIdx + 1; i < order.length; i++) {
          const k = order[i]
          if (k.startsWith('grp-')) break
          if (k.startsWith('tab-')) {
            const tid = parseInt(k.slice(4))
            const card = liveRows.value.find(t => t.tab_id === tid)
            if (card?.group_id === gid) insertAt = i + 1
            else break
          }
        }
        order.splice(insertAt, 0, ...tabKeys)
        newMap.set(wid, order)
        inserted = true
      })
      liveOrderByWindow.value = newMap

      // Close dialog immediately
      collectVisible.value = false

      try {
        await tabArchiveSetLiveTabsGroup(ids, gid)
        silentRefreshSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to collect tabs'))
        // Revert on error
        liveRows.value = liveRows.value.map(t =>
          idSet.has(t.tab_id) ? { ...t, group_id: null } : t
        )
        await loadSnapshot()
      } finally {
        collectSaving.value = false
      }
    }

    function toggleLiveGroupCollapse(groupId: number) {
      const next = new Set(collapsedLiveGroups.value)
      next.has(groupId) ? next.delete(groupId) : next.add(groupId)
      collapsedLiveGroups.value = next
    }

    function toggleArchiveGroupCollapse(groupId: number) {
      const next = new Set(collapsedArchiveGroups.value)
      next.has(groupId) ? next.delete(groupId) : next.add(groupId)
      collapsedArchiveGroups.value = next
    }

    // Organize mode (bulk assign tabs/records to groups)
    const liveOrganizeMode = ref(false)
    const archiveOrganizeMode = ref(false)
    const organizeSelectedIds = ref<Set<number>>(new Set())
    const organizeBulkGroupId = ref<number | null>(null)
    const organizeSaving = ref(false)

    const restoreDestination = ref<RestoreDestination>('new_window')

    const archiveEternalFilter = ref<EternalFilter>('all')
    const archiveLabelFilter = ref<string[]>([])
    const expiringCount = ref(0)
    const expireDays = ref(365)
    const showStale = ref(false)
    const expiringDismissed = ref(false)


    const editVisible = ref(false)
    const editingRecordId = ref<number | null>(null)
    const editTitle = ref('')
    const editComment = ref('')
    const editEternal = ref(false)
    const editLabelIds = ref<number[]>([])

    // --- Archive replace URL ---
    const replaceUrlVisible = ref(false)
    const replaceUrlFind = ref('')
    const replaceUrlReplace = ref('')
    const replaceUrlPreviewRows = ref<TabArchiveReplaceUrlPreviewRow[]>([])
    const replaceUrlPreviewed = ref(false)

    let searchTimer: number | undefined

    const labelNameById = computed<Record<number, string>>(() => {
      const out: Record<number, string> = {}
      labels.value.forEach(label => {
        out[label.id] = label.name
      })
      return out
    })

    const labelIdByName = computed<Record<string, number>>(() => {
      const out: Record<string, number> = {}
      labels.value.forEach(label => {
        out[label.name] = label.id
      })
      return out
    })

    const groupNameById = computed<Record<number, string>>(() => {
      const out: Record<number, string> = {}
      function walk(nodes: TabArchiveGroup[]) {
        nodes.forEach(g => {
          out[g.id] = g.name
          if (g.children?.length) walk(g.children)
        })
      }
      walk(liveGroupTree.value)
      walk(archiveGroupTree.value)
      walk(shelfGroupTree.value)
      return out
    })

    // Group tree for the currently active pane (drives the Organize dropdown
    // and the settings-drawer group manager, which are pane-scoped).
    const activeGroupTree = computed<TabArchiveGroup[]>(() => {
      if (activePane.value === 'live') return liveGroupTree.value
      if (activePane.value === 'shelf') return shelfGroupTree.value
      return archiveGroupTree.value
    })

    function activeScope(): GroupScope {
      if (activePane.value === 'live') return 'live'
      if (activePane.value === 'shelf') return 'shelf'
      return 'archive'
    }

    const flatGroups = computed<TabArchiveGroup[]>(() => {
      const result: TabArchiveGroup[] = []
      function walk(nodes: TabArchiveGroup[]) {
        nodes.forEach(g => {
          result.push(g)
          if (g.children?.length) walk(g.children)
        })
      }
      walk(activeGroupTree.value)
      return result
    })

    // Return ancestor group ids from root down to (not including) the given group.
    function getGroupAncestors(tree: TabArchiveGroup[], groupId: number): number[] {
      function search(nodes: TabArchiveGroup[], path: number[]): number[] | null {
        for (const g of nodes) {
          if (g.id === groupId) return path
          const found = search(g.children || [], [...path, g.id])
          if (found) return found
        }
        return null
      }
      return search(tree, []) ?? []
    }

    // Count tabs directly belonging to a group (not nested).
    function countTabsInGroup(groupId: number, tabs: TabArchiveLiveCard[]): number {
      return tabs.filter(t => t.group_id === groupId).length
    }

    // Build initial flat order for the Live pane from snapshot data.
    // Produces: groups depth-first (with their member tabs interleaved), then ungrouped tabs.
    function buildInitialLiveOrder(
      tabs: TabArchiveLiveCard[],
      groups: TabArchiveGroup[],
    ): Map<number, string[]> {
      const winMap = new Map<number, TabArchiveLiveCard[]>()
      tabs.forEach(t => {
        const arr = winMap.get(t.window_id) ?? []
        arr.push(t)
        winMap.set(t.window_id, arr)
      })

      // Collect all group keys once (groups are window-agnostic)
      const allGroupKeys: string[] = []
      function collectAllGroupKeys(nodes: TabArchiveGroup[]) {
        nodes.forEach(g => {
          allGroupKeys.push('grp-' + g.id)
          collectAllGroupKeys(g.children || [])
        })
      }
      collectAllGroupKeys(groups)

      const result = new Map<number, string[]>()
      let isFirstWindow = true
      winMap.forEach((winTabs, windowId) => {
        const tabsByGroupId = new Map<number | null, TabArchiveLiveCard[]>()
        winTabs.forEach(t => {
          const gid = t.group_id ?? null
          const arr = tabsByGroupId.get(gid) ?? []
          arr.push(t)
          tabsByGroupId.set(gid, arr)
        })

        const keys: string[] = []

        if (isFirstWindow) {
          // Groups appear only in the first window, interleaved with their member tabs
          const walkGroups = (nodes: TabArchiveGroup[]) => {
            nodes.forEach(g => {
              keys.push('grp-' + g.id)
              const memberTabs = (tabsByGroupId.get(g.id) ?? [])
                .slice().sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0))
              memberTabs.forEach(t => keys.push('tab-' + t.tab_id))
              walkGroups(g.children || [])
            })
          }
          walkGroups(groups)
          isFirstWindow = false
        }

        const ungrouped = tabsByGroupId.get(null) ?? []
        ungrouped.forEach(t => keys.push('tab-' + t.tab_id))

        result.set(windowId, keys)
      })

      // If there are no windows with tabs but groups exist, put them in a virtual entry
      if (result.size === 0 && allGroupKeys.length > 0) {
        result.set(-1, allGroupKeys)
      }

      return result
    }

    // Merge updated snapshot into liveOrderByWindow without losing user's custom order.
    // Removes keys for gone tabs/groups, appends keys for new tabs/groups.
    function mergeLiveOrderAfterRefresh(
      newTabs: TabArchiveLiveCard[],
      newGroups: TabArchiveGroup[],
    ) {
      const allGroupKeys = new Set<string>()
      function collectGroupKeys(nodes: TabArchiveGroup[]) {
        nodes.forEach(g => { allGroupKeys.add('grp-' + g.id); collectGroupKeys(g.children || []) })
      }
      collectGroupKeys(newGroups)

      const winMap = new Map<number, TabArchiveLiveCard[]>()
      newTabs.forEach(t => {
        const arr = winMap.get(t.window_id) ?? []
        arr.push(t)
        winMap.set(t.window_id, arr)
      })

      const newMap = new Map<number, string[]>()
      const windowIds = [...winMap.keys()]
      const firstWinId = windowIds[0]

      winMap.forEach((winTabs, windowId) => {
        const validTabKeys = new Set(winTabs.map(t => 'tab-' + t.tab_id))
        const isFirst = windowId === firstWinId
        const existing = liveOrderByWindow.value.get(windowId) ?? []

        // For non-first windows: strip out any group keys (they don't belong here)
        const kept = existing.filter(k => {
          if (allGroupKeys.has(k)) return isFirst
          return validTabKeys.has(k)
        })
        const keptSet = new Set(kept)
        // Append new tabs not yet in the order
        winTabs.forEach(t => {
          const k = 'tab-' + t.tab_id
          if (!keptSet.has(k)) kept.push(k)
        })
        newMap.set(windowId, kept)
      })

      // Ensure all group keys appear exactly once in the first window
      if (newMap.size > 0) {
        const firstOrder = newMap.get(firstWinId)!
        const firstSet = new Set(firstOrder)
        const missingGroups: string[] = []
        allGroupKeys.forEach(k => { if (!firstSet.has(k)) missingGroups.push(k) })
        firstOrder.unshift(...missingGroups)
        // Also remove any group keys from non-first windows (cleanup from old data)
        windowIds.slice(1).forEach(wid => {
          const order = newMap.get(wid)!
          newMap.set(wid, order.filter(k => !allGroupKeys.has(k)))
        })
      }

      liveOrderByWindow.value = newMap
    }

    function buildLiveTree(tabs: TabArchiveLiveCard[], tree: TabArchiveGroup[]): TreeNode[] {
      const tabsByGroupId = new Map<number | null, TabArchiveLiveCard[]>()
      tabs.forEach(t => {
        const gid = t.group_id ?? null
        const arr = tabsByGroupId.get(gid) ?? []
        arr.push(t)
        tabsByGroupId.set(gid, arr)
      })

      function sortedTabs(list: TabArchiveLiveCard[]): TabArchiveLiveCard[] {
        // If all tabs in this group have display_order, sort by it.
        // If any are null (not yet ordered by user), keep browser order as-is.
        const allHaveOrder = list.every(t => t.display_order !== null)
        if (!allHaveOrder) return list
        return [...list].sort((a, b) => (a.display_order as number) - (b.display_order as number))
      }

      function buildNodes(nodes: TabArchiveGroup[]): TreeNode[] {
        const result: TreeNode[] = []
        nodes.forEach(g => {
          const children: TreeNode[] = buildNodes(g.children || [])
          const directTabs = sortedTabs(tabsByGroupId.get(g.id) || [])
          directTabs.forEach(t => children.push({ type: 'tab', card: t }))
          result.push({ type: 'group', group: g, children })
        })
        return result
      }

      const rootNodes = buildNodes(tree)
      const ungrouped = sortedTabs(tabsByGroupId.get(null) || [])
      ungrouped.forEach(t => rootNodes.push({ type: 'tab', card: t }))
      return rootNodes
    }

    const liveRowsByWindow = computed<Array<{
      windowId: number
      tree: TreeNode[]
    }>>(() => {
      const winMap = new Map<number, TabArchiveLiveCard[]>()
      liveRows.value.forEach(r => {
        const arr = winMap.get(r.window_id) ?? []
        arr.push(r)
        winMap.set(r.window_id, arr)
      })
      return Array.from(winMap.entries()).map(([windowId, tabs]) => ({
        windowId,
        tree: buildLiveTree(tabs, liveGroupTree.value),
      }))
    })

    // Set of tab_ids whose group-siblings are non-contiguous in browser order.
    // A group is non-contiguous if its member tabs in a window are not all
    // adjacent (i.e. there is at least one tab from a different group between
    // two members of the same group).
    const liveOutOfOrderTabIds = computed<Set<number>>(() => {
      const result = new Set<number>()
      // Process each window independently.
      const winMap = new Map<number, TabArchiveLiveCard[]>()
      liveRows.value.forEach(r => {
        const arr = winMap.get(r.window_id) ?? []
        arr.push(r)
        winMap.set(r.window_id, arr)
      })
      winMap.forEach(tabs => {
        // Gather group ids that appear in this window (skip ungrouped).
        const groupIds = new Set(tabs.filter(t => t.group_id !== null).map(t => t.group_id as number))
        groupIds.forEach(gid => {
          const members = tabs.filter(t => t.group_id === gid)
          if (members.length < 2) return
          // Find min/max position index in the window tab list.
          const indices = members.map(t => tabs.indexOf(t))
          const minIdx = Math.min(...indices)
          const maxIdx = Math.max(...indices)
          // Non-contiguous if span is wider than member count - 1.
          if (maxIdx - minIdx >= members.length) {
            members.forEach(t => result.add(t.tab_id))
          }
        })
      })
      return result
    })

    // --- Drag handlers: nested draggable approach ---
    // Each group is its own <draggable> container; ungrouped items are in a
    // root-level <draggable>. SortableJS group name is shared so items can
    // cross containers. @change events carry:
    //   moved  → reorder within the same container (groupId stays the same)
    //   added  → item moved FROM another container (new groupId = target)
    //   removed → item moved TO another container (handled on the target side)
    //
    // Handler signature: (evt, groupId) where groupId is the container's group
    // id (null = ungrouped / root).

    // Compute midpoint display_order for an item dropped at `newIndex` inside
    // a list of items (before mutation). The item itself is NOT in the list.
    function midpointOrder(siblings: { display_order: number }[], newIndex: number): number {
      const prev = siblings[newIndex - 1]
      const next = siblings[newIndex]
      const prevOrder = prev ? prev.display_order : 0
      const nextOrder = next ? next.display_order : (prevOrder || 0) + 2000
      return (prevOrder + nextOrder) / 2
    }

    // --- Pragmatic drag-and-drop: compute insertion index from Y position ----
    // Given a drop zone element and the cursor Y coordinate, return the index
    // (0-based) where the dropped item should be inserted. Scans child rows
    // with [data-item-id] and finds the split point.
    function computeInsertIndex(zoneEl: HTMLElement, cursorY: number): number {
      const rows = Array.from(zoneEl.querySelectorAll<HTMLElement>(':scope > [data-item-id]'))
      for (let i = 0; i < rows.length; i++) {
        const rect = rows[i].getBoundingClientRect()
        if (cursorY < rect.top + rect.height / 2) return i
      }
      return rows.length
    }

    // --- Archive drag ---
    // archiveItemsByGroup: for each group id (or null), the list of visible records.
    const archiveItemsByGroup = computed<Map<number | null, TabArchiveRecord[]>>(() => {
      const map = new Map<number | null, TabArchiveRecord[]>()
      visibleArchiveRows.value.forEach(r => {
        const gid = r.group_id ?? null
        const arr = map.get(gid) ?? []
        arr.push(r)
        map.set(gid, arr)
      })
      return map
    })

    async function onArchiveGroupChange(
      evt: { added?: { element: TabArchiveRecord; newIndex: number }; moved?: { element: TabArchiveRecord; oldIndex: number; newIndex: number } },
      groupId: number | null,
    ) {
      if (evt.added) {
        const record = evt.added.element
        const siblings = archiveItemsByGroup.value.get(groupId) ?? []
        const newOrder = midpointOrder(siblings, evt.added.newIndex)
        // Optimistic: update local state immediately
        const idx = archiveRows.value.findIndex(r => r.id === record.id)
        if (idx >= 0) {
          archiveRows.value[idx] = { ...archiveRows.value[idx], group_id: groupId, display_order: newOrder }
        }
        try {
          await tabArchiveSetRecordGroup(record.id, groupId)
          await tabArchiveReorderRecord(record.id, newOrder)
          silentRefreshSnapshot()
        } catch (error) {
          ElMessage.error(errorMessage(error, 'Failed to move record'))
          await loadSnapshot()
        }
      } else if (evt.moved) {
        const record = evt.moved.element
        const siblings = (archiveItemsByGroup.value.get(groupId) ?? []).filter(r => r.id !== record.id)
        const newOrder = midpointOrder(siblings, evt.moved.newIndex)
        // Optimistic: update display_order locally
        const idx = archiveRows.value.findIndex(r => r.id === record.id)
        if (idx >= 0) {
          archiveRows.value[idx] = { ...archiveRows.value[idx], display_order: newOrder }
        }
        try {
          await tabArchiveReorderRecord(record.id, newOrder)
          silentRefreshSnapshot()
        } catch (error) {
          ElMessage.error(errorMessage(error, 'Failed to reorder'))
          await loadSnapshot()
        }
      }
    }

    // --- Live drag ---
    const liveItemsByGroup = computed<Map<number | null, TabArchiveLiveCard[]>>(() => {
      const map = new Map<number | null, TabArchiveLiveCard[]>()
      liveRows.value.forEach(t => {
        const gid = t.group_id ?? null
        const arr = map.get(gid) ?? []
        arr.push(t)
        map.set(gid, arr)
      })
      return map
    })

    // Find a group node anywhere in a tree by id (recursive).
    function findGroupInTree(nodes: TabArchiveGroup[], id: number): TabArchiveGroup | null {
      for (const g of nodes) {
        if (g.id === id) return g
        const found = findGroupInTree(g.children || [], id)
        if (found) return found
      }
      return null
    }

    // Return the sibling list (groups only) at the same parent level as `groupId`.
    function getSiblingGroups(tree: TabArchiveGroup[], groupId: number): TabArchiveGroup[] {
      function findSiblings(nodes: TabArchiveGroup[]): TabArchiveGroup[] | null {
        if (nodes.some(g => g.id === groupId)) return nodes
        for (const g of nodes) {
          const found = findSiblings(g.children || [])
          if (found) return found
        }
        return null
      }
      return findSiblings(tree) ?? []
    }

    // Return all groups that share the given parent_id (direct children of that parent).
    function getSiblingGroupsAtParent(tree: TabArchiveGroup[], parentId: number | null): TabArchiveGroup[] {
      if (parentId === null) return tree
      const parent = findGroupInTree(tree, parentId)
      return parent?.children || []
    }

    // Remove a group from the tree (returns a new tree without that node).
    function removeGroupFromTree(nodes: TabArchiveGroup[], id: number): TabArchiveGroup[] {
      return nodes
        .filter(g => g.id !== id)
        .map(g => ({ ...g, children: removeGroupFromTree(g.children || [], id) }))
    }

    // Insert a group into the children of `parentId` at the correct display_order position
    // (or at root level if parentId is null).
    function insertGroupInTree(
      nodes: TabArchiveGroup[],
      group: TabArchiveGroup,
      parentId: number | null,
    ): TabArchiveGroup[] {
      if (parentId === null) {
        const list = [...nodes, group].sort((a, b) => a.display_order - b.display_order)
        return list
      }
      return nodes.map(g => {
        if (g.id === parentId) {
          const children = [...(g.children || []), group].sort((a, b) => a.display_order - b.display_order)
          return { ...g, children }
        }
        return { ...g, children: insertGroupInTree(g.children || [], group, parentId) }
      })
    }

    function handleLiveDrop(
      source: Extract<DragPayload, { type: 'live-tab' } | { type: 'live-group' }>,
      targetDragKey: string,
      liveZone: 'top' | 'bottom' | 'into',
      windowId: number,
    ) {
      const sourceKey = source.type === 'live-tab'
        ? 'tab-' + (source as Extract<DragPayload, { type: 'live-tab' }>).tabId
        : 'grp-' + (source as Extract<DragPayload, { type: 'live-group' }>).id

      // Prevent group dropping into itself
      if (sourceKey === targetDragKey) return

      // Find which window order contains the source key
      // (groups are always in the first window; tabs may be in any window)
      let sourceWindowId = windowId
      let sourceOrder = [...(liveOrderByWindow.value.get(windowId) ?? [])]
      if (!sourceOrder.includes(sourceKey)) {
        // Search all windows for the source key
        let found = false
        for (const [wid, ord] of liveOrderByWindow.value.entries()) {
          if (ord.includes(sourceKey)) {
            sourceWindowId = wid
            sourceOrder = [...ord]
            found = true
            break
          }
        }
        if (!found) { uiDebug('live-drop.source-not-found', { sourceKey }); return }
      }

      // Find which window order contains the target key
      let targetWindowId = windowId
      let targetOrder = [...(liveOrderByWindow.value.get(windowId) ?? [])]
      if (!targetOrder.includes(targetDragKey)) {
        let found = false
        for (const [wid, ord] of liveOrderByWindow.value.entries()) {
          if (ord.includes(targetDragKey)) {
            targetWindowId = wid
            targetOrder = [...ord]
            found = true
            break
          }
        }
        if (!found) { uiDebug('live-drop.target-not-found', { targetDragKey }); return }
      }

      uiDebug('live-drop.start', { sourceKey, targetDragKey, liveZone, sourceWindowId, targetWindowId })

      // For group drags, collect the group key + all its direct member tab keys as one block
      let blockKeys: string[]
      if (sourceKey.startsWith('grp-')) {
        const gid = parseInt(sourceKey.slice(4))
        blockKeys = [sourceKey]
        const fromIdx = sourceOrder.indexOf(sourceKey)
        for (let i = fromIdx + 1; i < sourceOrder.length; i++) {
          const k = sourceOrder[i]
          if (k.startsWith('grp-')) break
          if (k.startsWith('tab-')) {
            const tabId = parseInt(k.slice(4))
            const card = liveRows.value.find(t => t.tab_id === tabId)
            if (card?.group_id === gid) blockKeys.push(k)
            else break
          }
        }
      } else {
        blockKeys = [sourceKey]
      }

      const newMap = new Map(liveOrderByWindow.value)

      if (sourceWindowId === targetWindowId) {
        // Same-window move: standard splice
        const order = sourceWindowId === windowId ? [...(liveOrderByWindow.value.get(sourceWindowId) ?? [])] : sourceOrder
        const fromIdx = order.indexOf(sourceKey)
        if (fromIdx < 0) { uiDebug('live-drop.source-not-found-same', { sourceKey }); return }
        order.splice(fromIdx, blockKeys.length)

        if (liveZone === 'into' && targetDragKey.startsWith('grp-')) {
          const gid = parseInt(targetDragKey.slice(4))
          const newToIdx = order.indexOf(targetDragKey)
          if (newToIdx < 0) { uiDebug('live-drop.target-lost', { targetDragKey }); return }
          let insertAt = newToIdx + 1
          for (let i = newToIdx + 1; i < order.length; i++) {
            const k = order[i]
            if (k.startsWith('grp-')) break
            if (k.startsWith('tab-')) {
              const tabId = parseInt(k.slice(4))
              const card = liveRows.value.find(t => t.tab_id === tabId)
              if (card?.group_id === gid) insertAt = i + 1
              else break
            }
          }
          order.splice(insertAt, 0, ...blockKeys)
        } else {
          const newToIdx = order.indexOf(targetDragKey)
          if (newToIdx < 0) { uiDebug('live-drop.target-lost', { targetDragKey }); return }
          const insertAt = liveZone === 'top' ? newToIdx : newToIdx + 1
          order.splice(insertAt, 0, ...blockKeys)
        }

        newMap.set(sourceWindowId, order)
      } else {
        // Cross-window move: remove from source window, insert into target window
        const fromIdx = sourceOrder.indexOf(sourceKey)
        if (fromIdx < 0) return
        sourceOrder.splice(fromIdx, blockKeys.length)
        newMap.set(sourceWindowId, sourceOrder)

        if (liveZone === 'into' && targetDragKey.startsWith('grp-')) {
          const gid = parseInt(targetDragKey.slice(4))
          const toIdx = targetOrder.indexOf(targetDragKey)
          if (toIdx < 0) { uiDebug('live-drop.target-not-found-cross', { targetDragKey }); return }
          let insertAt = toIdx + 1
          for (let i = toIdx + 1; i < targetOrder.length; i++) {
            const k = targetOrder[i]
            if (k.startsWith('grp-')) break
            if (k.startsWith('tab-')) {
              const tabId = parseInt(k.slice(4))
              const card = liveRows.value.find(t => t.tab_id === tabId)
              if (card?.group_id === gid) insertAt = i + 1
              else break
            }
          }
          targetOrder.splice(insertAt, 0, ...blockKeys)
        } else {
          const toIdx = targetOrder.indexOf(targetDragKey)
          if (toIdx < 0) { uiDebug('live-drop.target-not-found-cross', { targetDragKey }); return }
          const insertAt = liveZone === 'top' ? toIdx : toIdx + 1
          targetOrder.splice(insertAt, 0, ...blockKeys)
        }

        newMap.set(targetWindowId, targetOrder)
      }

      liveOrderByWindow.value = newMap

      // The effective order for persistence is the one containing the source key after move
      const effectiveOrder = [...(newMap.get(targetWindowId) ?? [])]
      uiDebug('live-drop.done', { sourceKey, newPos: effectiveOrder.indexOf(sourceKey) })

      // Infer new group/parent for DB persistence
      if (source.type === 'live-tab') {
        const tabId = (source as Extract<DragPayload, { type: 'live-tab' }>).tabId
        const newGroupId = inferTabGroupFromOrder(effectiveOrder, sourceKey, liveRows.value)
        // Optimistic update of group_id on the card
        const idx = liveRows.value.findIndex(t => t.tab_id === tabId)
        if (idx >= 0 && liveRows.value[idx].group_id !== newGroupId) {
          liveRows.value[idx] = { ...liveRows.value[idx], group_id: newGroupId }
        }
        persistTabOrder(effectiveOrder, liveRows.value)
      } else {
        const groupId = (source as Extract<DragPayload, { type: 'live-group' }>).id
        const newParentId = inferGroupParentFromOrder(effectiveOrder, sourceKey, liveGroupTree.value)
        persistGroupMove(groupId, newParentId, effectiveOrder)
      }
    }

    // Infer the group_id a tab should belong to based on its position in the flat order.
    // Scan backwards: if we hit a group key, the tab belongs to that group.
    // If we hit an ungrouped tab or the start, the tab is ungrouped.
    function inferTabGroupFromOrder(
      order: string[],
      tabKey: string,
      tabs: TabArchiveLiveCard[],
    ): number | null {
      const pos = order.indexOf(tabKey)
      for (let i = pos - 1; i >= 0; i--) {
        const k = order[i]
        if (k.startsWith('grp-')) return parseInt(k.slice(4))
        if (k.startsWith('tab-')) {
          const tid = parseInt(k.slice(4))
          const card = tabs.find(t => t.tab_id === tid)
          if (card?.group_id != null) return card.group_id
          return null  // hit an ungrouped tab → ungrouped
        }
      }
      return null
    }

    // Infer the parent_id for a group based on its position in the flat order.
    // If it's directly after another group key, it may be a child of that group.
    // Simplified: scan backwards for the nearest group key; if that group's depth
    // is shallower, it's the parent. If none found, parent is null (root).
    function inferGroupParentFromOrder(
      order: string[],
      groupKey: string,
      tree: TabArchiveGroup[],
    ): number | null {
      const pos = order.indexOf(groupKey)
      // Scan backwards for the nearest group key
      for (let i = pos - 1; i >= 0; i--) {
        const k = order[i]
        if (k.startsWith('grp-')) {
          // Only treat as parent if this drop was 'into' (but we already handled that above).
          // For top/bottom drops, the group stays at the same nesting level as target.
          // The target is the key at pos+1 or pos-1 — use the item right after sourceKey.
          break
        }
        if (k.startsWith('tab-')) break
      }
      // For simplicity: check what's immediately after the group in the order.
      // If nothing before it is a group header, it's a root group (parent=null).
      // Check the group's current parent and only change if the surrounding context differs.
      const gid = parseInt(groupKey.slice(4))
      const group = findGroupInTree(tree, gid)
      return group?.parent_id ?? null
    }

    // Persist tab order to DB (fire-and-forget)
    function persistTabOrder(order: string[], tabs: TabArchiveLiveCard[]) {
      const items: Array<{ tab_id: number; group_id: number | null; display_order: number }> = []
      let idx = 0
      order.forEach(key => {
        if (!key.startsWith('tab-')) return
        const tabId = parseInt(key.slice(4))
        const card = tabs.find(t => t.tab_id === tabId)
        if (!card) return
        items.push({ tab_id: tabId, group_id: card.group_id ?? null, display_order: (idx + 1) * 1000 })
        idx++
      })
      tabArchiveBatchSetLiveTabOrders(items).catch(err => uiWarn('persist-tab-order.failed', err))
    }

    // Persist group move to DB (fire-and-forget)
    function persistGroupMove(groupId: number, newParentId: number | null, order: string[]) {
      const groupKeys = order.filter(k => k.startsWith('grp-'))
      const pos = groupKeys.indexOf('grp-' + groupId)
      const newOrder = (pos + 1) * 1000

      // Update liveGroupTree optimistically
      const group = findGroupInTree(liveGroupTree.value, groupId)
      if (group) {
        const updatedGroup = { ...group, parent_id: newParentId, display_order: newOrder }
        let newTree = removeGroupFromTree(liveGroupTree.value, groupId)
        newTree = insertGroupInTree(newTree, updatedGroup, newParentId)
        liveGroupTree.value = newTree
      }

      tabArchiveMoveGroup(groupId, newParentId, newOrder, 'live')
        .catch(err => uiWarn('persist-group-move.failed', err))
    }

    async function onLiveGroupChange(
      evt: { added?: { element: TabArchiveLiveCard; newIndex: number }; moved?: { element: TabArchiveLiveCard; oldIndex: number; newIndex: number } },
      windowId: number,
      groupId: number | null,
    ) {
      if (evt.added) {
        const card = evt.added.element
        // Optimistic: update group_id locally
        const idx = liveRows.value.findIndex(r => r.tab_id === card.tab_id)
        if (idx >= 0) {
          liveRows.value[idx] = { ...liveRows.value[idx], group_id: groupId }
        }
        try {
          await tabArchiveSetLiveTabsGroup([card.tab_id], groupId)
          silentRefreshSnapshot()
        } catch (error) {
          ElMessage.error(errorMessage(error, 'Failed to move tab'))
          await loadSnapshot()
        }
      } else if (evt.moved) {
        try {
          silentRefreshSnapshot()
        } catch (error) {
          ElMessage.error(errorMessage(error, 'Failed to reorder tab'))
          await loadSnapshot()
        }
      }
    }

    // --- Shelf drag ---
    const shelfItemsByGroup = computed<Map<number | null, ShelfItem[]>>(() => {
      const map = new Map<number | null, ShelfItem[]>()
      shelfItems.value.forEach(it => {
        const gid = it.group_id ?? null
        const arr = map.get(gid) ?? []
        arr.push(it)
        map.set(gid, arr)
      })
      return map
    })

    async function onShelfGroupChange(
      evt: { added?: { element: ShelfItem; newIndex: number }; moved?: { element: ShelfItem; oldIndex: number; newIndex: number } },
      groupId: number | null,
    ) {
      if (evt.added) {
        const item = evt.added.element
        const siblings = shelfItemsByGroup.value.get(groupId) ?? []
        const newOrder = midpointOrder(siblings, evt.added.newIndex)
        // Optimistic: update locally
        const idx = shelfItems.value.findIndex(it => it.id === item.id)
        if (idx >= 0) {
          shelfItems.value[idx] = { ...shelfItems.value[idx], group_id: groupId, display_order: newOrder }
        }
        try {
          await tabArchiveSetShelfItemGroup(item.id, groupId)
          await tabArchiveSetShelfItemOrder(item.id, newOrder)
          silentRefreshShelf()
        } catch (error) {
          ElMessage.error(errorMessage(error, 'Failed to move item'))
          await loadShelf()
        }
      } else if (evt.moved) {
        const item = evt.moved.element
        const siblings = (shelfItemsByGroup.value.get(groupId) ?? []).filter(it => it.id !== item.id)
        const newOrder = midpointOrder(siblings, evt.moved.newIndex)
        // Optimistic: update display_order locally
        const idx = shelfItems.value.findIndex(it => it.id === item.id)
        if (idx >= 0) {
          shelfItems.value[idx] = { ...shelfItems.value[idx], display_order: newOrder }
        }
        try {
          await tabArchiveSetShelfItemOrder(item.id, newOrder)
          silentRefreshShelf()
        } catch (error) {
          ElMessage.error(errorMessage(error, 'Failed to reorder'))
          await loadShelf()
        }
      }
    }

    // --- Unified drop handler (pragmatic-drag-and-drop monitor) ---
    function handleDrop(evt: MonitorDropEvent) {
      const { source, target, dropElement, inputY, closestEdge } = evt

      // --- archive record drops ---
      if (source.type === 'archive-record') {
        if (target.zone === 'archive-group-content') {
          const record = archiveRows.value.find(r => r.id === source.id)
          if (!record) return
          const newIndex = computeInsertIndex(dropElement, inputY)
          const newGroupId = (target as { groupId: number | null }).groupId
          if (source.groupId === newGroupId) {
            void onArchiveGroupChange({ moved: { element: record, oldIndex: 0, newIndex } }, newGroupId)
          } else {
            void onArchiveGroupChange({ added: { element: record, newIndex } }, newGroupId)
          }
          return
        }
        if (target.zone === 'archive-group-header') {
          const record = archiveRows.value.find(r => r.id === source.id)
          if (!record) return
          // top edge: place before this group → ungrouped; bottom edge: into this group
          const newGroupId = closestEdge === 'top' ? null : (target as { groupId: number }).groupId
          const newIndex = computeInsertIndex(dropElement, inputY)
          if (source.groupId === newGroupId) {
            void onArchiveGroupChange({ moved: { element: record, oldIndex: 0, newIndex } }, newGroupId)
          } else {
            void onArchiveGroupChange({ added: { element: record, newIndex: 0 } }, newGroupId)
          }
          return
        }
        return
      }

      // --- archive group reorder ---
      if (source.type === 'archive-group') {
        if (target.zone === 'archive-group-header') {
          const group = archiveGroupTree.value.find(g => g.id === source.id)
          if (!group) return
          const siblings = archiveGroupTree.value.filter(g => g.id !== source.id)
          const targetIdx = siblings.findIndex(g => g.id === (target as { groupId: number }).groupId)
          const newIndex = targetIdx >= 0 ? targetIdx : siblings.length
          void onGroupReorder({ moved: { element: group, oldIndex: 0, newIndex } }, 'archive')
        }
        return
      }

      // --- live tab drops ---
      if (source.type === 'live-tab') {
        const dragKey = dropElement.dataset.dragKey
        if (!dragKey) { uiDebug('handle-drop.live-tab.no-drag-key', { el: dropElement.className }); return }
        const edge: 'top' | 'bottom' | 'into' = evt.liveZone ?? 'bottom'
        const windowId = source.windowId
        uiDebug('handle-drop.live-tab', { tabId: source.tabId, dragKey, edge, windowId })
        handleLiveDrop(source, dragKey, edge, windowId)
        liveDndIndicator.value = null
        return
      }

      // --- live group reorder/reparent ---
      if (source.type === 'live-group') {
        const dragKey = dropElement.dataset.dragKey
        if (!dragKey) { uiDebug('handle-drop.live-group.no-drag-key', { el: dropElement.className }); return }
        const edge: 'top' | 'bottom' | 'into' = evt.liveZone ?? 'bottom'
        // Groups are window-agnostic; use first window that has an order
        const windowId = liveOrderByWindow.value.keys().next().value ?? 0
        uiDebug('handle-drop.live-group', { groupId: source.id, dragKey, edge, windowId })
        handleLiveDrop(source, dragKey, edge, windowId as number)
        liveDndIndicator.value = null
        return
      }

      // --- shelf item drops ---
      if (source.type === 'shelf-item') {
        if (target.zone === 'shelf-group-content') {
          const newGroupId = (target as { groupId: number | null }).groupId
          const item = shelfItems.value.find(it => it.id === source.id)
          if (!item) return
          const newIndex = computeInsertIndex(dropElement, inputY)
          if (source.groupId === newGroupId) {
            void onShelfGroupChange({ moved: { element: item, oldIndex: 0, newIndex } }, newGroupId)
          } else {
            void onShelfGroupChange({ added: { element: item, newIndex } }, newGroupId)
          }
          return
        }
        if (target.zone === 'shelf-group-header') {
          const item = shelfItems.value.find(it => it.id === source.id)
          if (!item) return
          const newGroupId = closestEdge === 'top' ? null : (target as { groupId: number }).groupId
          if (source.groupId === newGroupId) {
            void onShelfGroupChange({ moved: { element: item, oldIndex: 0, newIndex: 0 } }, newGroupId)
          } else {
            void onShelfGroupChange({ added: { element: item, newIndex: 0 } }, newGroupId)
          }
          return
        }
        return
      }

      // --- shelf group reorder ---
      if (source.type === 'shelf-group') {
        if (target.zone === 'shelf-group-header') {
          const group = shelfGroupTree.value.find(g => g.id === source.id)
          if (!group) return
          const siblings = shelfGroupTree.value.filter(g => g.id !== source.id)
          const targetIdx = siblings.findIndex(g => g.id === (target as { groupId: number }).groupId)
          const newIndex = targetIdx >= 0 ? targetIdx : siblings.length
          void onGroupReorder({ moved: { element: group, oldIndex: 0, newIndex } }, 'shelf')
        }
        return
      }
    }

    // Register the global monitor (auto-cleaned on unmount by useDndMonitor)
    useDndMonitor(handleDrop, (evt) => {
      // Update live drag indicator for Live pane rows only
      if (evt.source.type !== 'live-tab' && evt.source.type !== 'live-group') return
      if (!evt.dropElement) {
        liveDndIndicator.value = null
        return
      }
      const dragKey = evt.dropElement.dataset.dragKey
      if (!dragKey) {
        liveDndIndicator.value = null
        return
      }
      const overAttr = evt.dropElement.dataset.dropOver
      const edgeAttr = evt.dropElement.dataset.edge
      const edge: 'top' | 'bottom' | 'into' = overAttr ? 'into' : (edgeAttr === 'top' ? 'top' : 'bottom')
      liveDndIndicator.value = { key: dragKey, edge }
    })

    // --- Reorder groups within a pane by dragging their headers.
    // The outer <draggable> emits @change with moved.{element, newIndex}.
    // We persist the new order via tabArchiveMoveGroup and update the tree optimistically.
    async function onGroupReorder(
      evt: { moved?: { element: TabArchiveGroup; oldIndex: number; newIndex: number } },
      scope: GroupScope,
    ) {
      if (!evt.moved) return
      const { element: group, newIndex } = evt.moved
      // Determine which tree to update
      const treeRef = scope === 'live' ? liveGroupTree : scope === 'shelf' ? shelfGroupTree : archiveGroupTree
      // Compute new display_order using midpoint between neighbors
      const siblings = treeRef.value.filter(g => g.id !== group.id)
      const prev = siblings[newIndex - 1]
      const next = siblings[newIndex]
      const prevOrder = prev ? prev.display_order : 0
      const nextOrder = next ? next.display_order : (prevOrder || 0) + 2000
      const newOrder = (prevOrder + nextOrder) / 2
      // Optimistic: reorder in the local tree
      const reordered = [...treeRef.value]
      const oldIdx = reordered.findIndex(g => g.id === group.id)
      if (oldIdx >= 0) {
        reordered.splice(oldIdx, 1)
        reordered.splice(newIndex, 0, { ...group, display_order: newOrder })
        treeRef.value = reordered
      }
      try {
        await tabArchiveMoveGroup(group.id, group.parent_id, newOrder, scope)
        if (scope === 'shelf') silentRefreshShelf()
        else silentRefreshSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to reorder group'))
        if (scope === 'shelf') await loadShelf()
        else await loadSnapshot()
      }
    }

    const visibleArchiveRows = computed(() => {
      return archiveRows.value.filter(record => {
        if (archiveEternalFilter.value === 'eternal' && !record.eternal) {
          return false
        }
        if (archiveEternalFilter.value === 'not_eternal' && record.eternal) {
          return false
        }

        if (archiveLabelFilter.value.length > 0) {
          const names = new Set(record.labels || [])
          if (!archiveLabelFilter.value.every(labelName => names.has(labelName))) {
            return false
          }
        }

        if (showStale.value) {
          if (record.eternal) return false
          const cutoffMs = Date.now() - expireDays.value * 86400 * 1000
          const lastActivity = record.last_opened_at || record.last_archived_at || record.created_at || ''
          if (!lastActivity || new Date(lastActivity).getTime() >= cutoffMs) return false
        }

        return true
      })
    })

    // Flattened render lists for Live and Archive (avoids recursive templates)
    function countTabs(nodes: TreeNode[]): number {
      let count = 0
      nodes.forEach(n => {
        if (n.type === 'tab') count++
        else count += countTabs(n.children)
      })
      return count
    }

    function flattenLiveTree(nodes: TreeNode[], depth: number, out: LiveRenderItem[], ancestors: number[] = []) {
      nodes.forEach(n => {
        if (n.type === 'group') {
          out.push({ kind: 'group', group: n.group, depth, tabCount: countTabs(n.children), ancestorIds: ancestors, dragKey: 'grp-' + n.group.id })
          flattenLiveTree(n.children, depth + 1, out, [...ancestors, n.group.id])
        } else {
          out.push({ kind: 'tab', card: n.card, depth, ancestorIds: ancestors, dragKey: 'tab-' + n.card.tab_id })
        }
      })
    }

    const liveRenderList = computed<Array<{
      windowId: number
      items: LiveRenderItem[]
      tabCount: number
    }>>(() => {
      const tabMap = new Map<number, TabArchiveLiveCard>()
      liveRows.value.forEach(t => tabMap.set(t.tab_id, t))
      const groupMap = new Map<number, TabArchiveGroup>()
      function indexGroups(nodes: TabArchiveGroup[]) {
        nodes.forEach(g => { groupMap.set(g.id, g); indexGroups(g.children || []) })
      }
      indexGroups(liveGroupTree.value)

      return Array.from(liveOrderByWindow.value.entries()).map(([windowId, keys]) => {
        const items: LiveRenderItem[] = []
        keys.forEach(key => {
          if (key.startsWith('grp-')) {
            const gid = parseInt(key.slice(4))
            const group = groupMap.get(gid)
            if (!group) return
            const ancestors = getGroupAncestors(liveGroupTree.value, gid)
            // Skip groups whose top-level ancestor is collapsed
            const topAncestor = ancestors[0]
            if (topAncestor !== undefined && collapsedLiveGroups.value.has(topAncestor)) return
            const depth = ancestors.length
            const tabCount = countTabsInGroup(gid, liveRows.value)
            items.push({ kind: 'group', group, depth, tabCount, ancestorIds: ancestors, dragKey: key })
          } else if (key.startsWith('tab-')) {
            const tabId = parseInt(key.slice(4))
            const card = tabMap.get(tabId)
            if (!card) return
            const ancestors = card.group_id != null ? getGroupAncestors(liveGroupTree.value, card.group_id) : []
            // Skip if inside a collapsed group
            const isCollapsed = (card.group_id != null && collapsedLiveGroups.value.has(card.group_id)) ||
              ancestors.some(aid => collapsedLiveGroups.value.has(aid))
            if (isCollapsed) return
            const depth = card.group_id != null ? ancestors.length + 1 : 0
            const ancestorIds = card.group_id != null ? [...ancestors, card.group_id] : []
            items.push({ kind: 'tab', card, depth, ancestorIds, dragKey: key })
          }
        })
        const tabCount = items.filter(i => i.kind === 'tab').length
        return { windowId, items, tabCount }
      })
    })

    function countRecords(nodes: ArchiveTreeNode[]): number {
      let count = 0
      nodes.forEach(n => {
        if (n.type === 'record') count++
        else count += countRecords(n.children)
      })
      return count
    }

    function flattenArchiveTree(nodes: ArchiveTreeNode[], depth: number, out: ArchiveRenderItem[], ancestors: number[] = []) {
      nodes.forEach(n => {
        if (n.type === 'group') {
          out.push({ kind: 'group', group: n.group, depth, recordCount: countRecords(n.children), ancestorIds: ancestors, dragKey: 'grp-' + n.group.id })
          flattenArchiveTree(n.children, depth + 1, out, [...ancestors, n.group.id])
        } else {
          out.push({ kind: 'record', record: n.record, depth, ancestorIds: ancestors, dragKey: 'rec-' + n.record.id })
        }
      })
    }

    const archiveRenderList = computed<ArchiveRenderItem[]>(() => {
      const items: ArchiveRenderItem[] = []
      flattenArchiveTree(visibleArchiveTree.value, 0, items)
      return items
    })
    const visibleArchiveTree = computed<ArchiveTreeNode[]>(() => {
      const recordsByGroupId = new Map<number | null, TabArchiveRecord[]>()
      visibleArchiveRows.value.forEach(r => {
        const gid = r.group_id ?? null
        const arr = recordsByGroupId.get(gid) ?? []
        arr.push(r)
        recordsByGroupId.set(gid, arr)
      })

      function buildNodes(nodes: TabArchiveGroup[]): ArchiveTreeNode[] {
        const result: ArchiveTreeNode[] = []
        nodes.forEach(g => {
          const children: ArchiveTreeNode[] = buildNodes(g.children || [])
          const direct = recordsByGroupId.get(g.id) || []
          direct.forEach(r => children.push({ type: 'record', record: r }))
          result.push({ type: 'group', group: g, children })
        })
        return result
      }

      const rootNodes = buildNodes(archiveGroupTree.value)
      const ungrouped = recordsByGroupId.get(null) || []
      ungrouped.forEach(r => rootNodes.push({ type: 'record', record: r }))
      return rootNodes
    })

    const visibleArchiveByGroup = computed<Array<{ groupName: string | null; rows: typeof visibleArchiveRows.value }>>(() => {
      const grpMap = new Map<string, typeof visibleArchiveRows.value>()
      visibleArchiveRows.value.forEach(r => {
        const key = r.group_name ?? '￿'
        const arr = grpMap.get(key) ?? []
        arr.push(r)
        grpMap.set(key, arr)
      })
      return Array.from(grpMap.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, rows]) => ({ groupName: key === '￿' ? null : key, rows }))
    })

const allVisibleLiveSelected = computed(() => {
      const rows = liveRows.value
      if (rows.length === 0) {
        return false
      }
      return rows.every(row => selectedLiveTabIds.value.has(row.tab_id))
    })

    const someVisibleLiveSelected = computed(() => {
      if (allVisibleLiveSelected.value) {
        return false
      }
      return liveRows.value.some(row => selectedLiveTabIds.value.has(row.tab_id))
    })

    const allVisibleArchiveSelected = computed(() => {
      const rows = visibleArchiveRows.value
      if (rows.length === 0) {
        return false
      }
      return rows.every(row => selectedArchiveIds.value.has(row.id))
    })

    const someVisibleArchiveSelected = computed(() => {
      if (allVisibleArchiveSelected.value) {
        return false
      }
      return visibleArchiveRows.value.some(row => selectedArchiveIds.value.has(row.id))
    })

    const heatTagType = (heat: HeatLevel): 'danger' | 'warning' | 'success' | 'info' => {
      if (heat === 'high') return 'danger'
      if (heat === 'medium') return 'warning'
      if (heat === 'low') return 'success'
      return 'info'
    }

    async function loadLabels() {
      labels.value = await tabArchiveListLabels()
    }

    // Silent refresh: reload data from server without showing the loading spinner.
    // Used after optimistic updates so the UI stays fast but eventually consistent.
    function silentRefreshSnapshot() {
      tabArchiveSnapshot({ q: search.value.trim(), scope: 'all', include_live_urls: true })
        .then(data => {
          extensionAvailable.value = data.extension_available
          liveError.value = data.live_error || ''
          liveRows.value = data.live || []
          archiveRows.value = data.archive || []
          liveGroupTree.value = data.live_group_tree || []
          archiveGroupTree.value = data.archive_group_tree || []
          expiringCount.value = (data as any).expiring_count ?? 0
          expireDays.value = (data as any).expire_days ?? 365
          const cache = { ...archiveCache.value }
          archiveRows.value.forEach(row => { cache[row.id] = row })
          archiveCache.value = cache
          mergeLiveOrderAfterRefresh(data.live || [], data.live_group_tree || [])
          uiDebug('silent-refresh.done', { liveCount: liveRows.value.length })
        })
        .catch(err => uiWarn('silent-refresh-snapshot.failed', err))
    }

    function silentRefreshShelf() {
      tabArchiveGetShelf()
        .then(resp => {
          shelfItems.value = resp.items || []
          shelfGroupTree.value = resp.group_tree || []
        })
        .catch(err => uiWarn('silent-refresh-shelf.failed', err))
    }

    async function loadSnapshot() {
      loading.value = true
      uiDebug('snapshot.start', { queryLen: search.value.trim().length })
      try {
        const data = await tabArchiveSnapshot({
          q: search.value.trim(),
          scope: 'all',
          include_live_urls: true,
        })

        extensionAvailable.value = data.extension_available
        liveError.value = data.live_error || ''
        liveRows.value = data.live || []
        archiveRows.value = data.archive || []
        liveGroupTree.value = data.live_group_tree || []
        archiveGroupTree.value = data.archive_group_tree || []
        expiringCount.value = (data as any).expiring_count ?? 0
        expireDays.value = (data as any).expire_days ?? 365

        const cache = { ...archiveCache.value }
        archiveRows.value.forEach(row => {
          cache[row.id] = row
        })
        archiveCache.value = cache

        // Build initial flat order for Live pane
        liveOrderByWindow.value = buildInitialLiveOrder(liveRows.value, liveGroupTree.value)

        // Live selections should only keep currently existing tabs.
        const existingLiveIds = new Set(liveRows.value.map(row => row.tab_id))
        const nextLiveSelected = new Set<number>()
        selectedLiveTabIds.value.forEach(id => {
          if (existingLiveIds.has(id)) {
            nextLiveSelected.add(id)
          }
        })
        selectedLiveTabIds.value = nextLiveSelected
        uiDebug('snapshot.done', {
          live: liveRows.value.length,
          archive: archiveRows.value.length,
          extensionAvailable: extensionAvailable.value,
        })
      } catch (error) {
        uiError('snapshot.failed', error)
        ElMessage.error(errorMessage(error, 'Failed to load tab snapshot'))
      } finally {
        loading.value = false
      }
    }

    function scheduleSearchReload() {
      if (searchTimer !== undefined) {
        window.clearTimeout(searchTimer)
      }
      searchTimer = window.setTimeout(() => {
        void loadSnapshot()
      }, 250)
    }

    function toggleLiveSelection(tabId: number) {
      const next = new Set(selectedLiveTabIds.value)
      if (next.has(tabId)) next.delete(tabId)
      else next.add(tabId)
      selectedLiveTabIds.value = next
    }

    function toggleVisibleLiveSelection() {
      const next = new Set(selectedLiveTabIds.value)
      if (allVisibleLiveSelected.value) {
        liveRows.value.forEach(row => next.delete(row.tab_id))
      } else {
        liveRows.value.forEach(row => next.add(row.tab_id))
      }
      selectedLiveTabIds.value = next
    }

    function toggleArchiveSelection(recordId: number) {
      const next = new Set(selectedArchiveIds.value)
      if (next.has(recordId)) next.delete(recordId)
      else next.add(recordId)
      selectedArchiveIds.value = next
    }

    function toggleVisibleArchiveSelection() {
      const next = new Set(selectedArchiveIds.value)
      if (allVisibleArchiveSelected.value) {
        visibleArchiveRows.value.forEach(row => next.delete(row.id))
      } else {
        visibleArchiveRows.value.forEach(row => next.add(row.id))
      }
      selectedArchiveIds.value = next
    }

async function archiveSelectedLive() {
      const ids = uniqueNumbers(Array.from(selectedLiveTabIds.value))
      if (ids.length === 0) {
        ElMessage.info('No live tabs selected')
        return
      }
      uiDebug('archiveSelected.start', { count: ids.length })

      try {
        await ElMessageBox.confirm(
          `Archive and close ${ids.length} selected tab(s)?`,
          'Confirm archive',
          {
            type: 'warning',
            confirmButtonText: 'Archive selected',
            cancelButtonText: 'Cancel',
          },
        )
      } catch {
        return
      }

      busy.value = true
      try {
        const result = await tabArchiveSelected(ids)
        uiDebug('archiveSelected.done', {
          requested: result.requested,
          closed: result.closed_count,
          failed: result.failed_count,
        })
        if (result.failed_count > 0) {
          uiWarn('archiveSelected.partial', {
            failed: result.failed_count,
            failures: result.failures?.slice(0, 5) || [],
          })
          ElMessage.warning(
            `Archived ${result.closed_count}/${result.requested}. ${result.failed_count} failed.`,
          )
        } else {
          ElMessage.success(`Archived ${result.closed_count} tab(s)`)
        }
        selectedLiveTabIds.value = new Set()
        await loadSnapshot()
      } catch (error) {
        uiError('archiveSelected.failed', error)
        ElMessage.error(errorMessage(error, 'Archive selected failed'))
      } finally {
        busy.value = false
      }
    }

    async function restoreSelectedArchive() {
      const ids = uniqueNumbers(Array.from(selectedArchiveIds.value))
      if (ids.length === 0) {
        ElMessage.info('No archived records selected')
        return
      }
      uiDebug('restore.start', {
        count: ids.length,
        destination: restoreDestination.value,
      })

      busy.value = true
      try {
        const result = await tabArchiveRestore(ids, restoreDestination.value)
        uiDebug('restore.done', {
          requested: result.requested,
          opened: result.opened_count,
          alreadyLive: result.already_live_count,
          failed: result.failed_count,
        })

        const failedIds = new Set(
          result.results
            .filter(row => !row.ok)
            .map(row => row.record_id),
        )

        if (failedIds.size === 0) {
          selectedArchiveIds.value = new Set()
          ElMessage.success(`Restore completed: ${result.opened_count} opened, ${result.already_live_count} already live`)
        } else {
          selectedArchiveIds.value = new Set(Array.from(failedIds))
          const summary = buildRestoreFailureSummary(result.results)
          const headline = summary.headline ? ` (${summary.headline})` : ''
          uiWarn('restore.partial', {
            failedIds: Array.from(failedIds),
            reasonSummary: summary.headline,
            sampleFailures: result.results.filter(row => !row.ok).slice(0, 5),
          })
          ElMessage.warning(`Restore partial: ${result.failed_count} failed${headline}`)
          if (summary.details) {
            await ElMessageBox.alert(summary.details, 'Restore failure details', {
              type: 'warning',
              confirmButtonText: 'OK',
            })
          }
        }

        await loadSnapshot()
      } catch (error) {
        uiError('restore.failed', error)
        ElMessage.error(errorMessage(error, 'Restore failed'))
      } finally {
        busy.value = false
      }
    }

    async function closeSingleLive(tabId: number) {
      busy.value = true
      try {
        const result = await closeTabs([tabId])
        if ((result.closed || 0) > 0) {
          ElMessage.success('Tab closed')
        } else {
          ElMessage.warning('Close request returned no closed tabs')
        }
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to close tab'))
      } finally {
        busy.value = false
      }
    }

    async function closeSelectedLiveOnly() {
      const ids = uniqueNumbers(Array.from(selectedLiveTabIds.value))
      if (ids.length === 0) {
        ElMessage.info('No live tabs selected')
        return
      }

      try {
        await ElMessageBox.confirm(`Close ${ids.length} selected live tab(s)?`, 'Confirm', {
          type: 'warning',
          confirmButtonText: 'Close selected',
          cancelButtonText: 'Cancel',
        })
      } catch {
        return
      }

      busy.value = true
      try {
        const result = await closeTabs(ids)
        const failed = result.failed?.length || 0
        if (failed > 0) {
          ElMessage.warning(`Closed ${result.closed}; ${failed} failed`)
        } else {
          ElMessage.success(`Closed ${result.closed} tab(s)`)
        }
        selectedLiveTabIds.value = new Set()
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to close selected tabs'))
      } finally {
        busy.value = false
      }
    }

    async function mergeAll() {
      busy.value = true
      try {
        const result = await mergeTabs()
        ElMessage.success(`Merged ${result.moved} tab(s) into one window`)
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to merge windows'))
      } finally {
        busy.value = false
      }
    }

    async function groupByDomain() {
      busy.value = true
      try {
        const result = await groupTabsByDomain()
        ElMessage.success(`Grouped ${result.grouped} tab(s) by domain`)
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to group tabs'))
      } finally {
        busy.value = false
      }
    }

    function startEditRecord(record: TabArchiveRecord) {
      editingRecordId.value = record.id
      editTitle.value = record.title || ''
      editComment.value = record.comment || ''
      editEternal.value = !!record.eternal
      editLabelIds.value = uniqueNumbers((record.labels || []).map(name => labelIdByName.value[name] || 0))
      editVisible.value = true
    }

    async function createLabelInEditor() {
      const promptResult = await ElMessageBox.prompt('Label name', 'Create Label', {
        inputPlaceholder: 'e.g. reference, learning, work',
      }).catch(() => null)

      const value = promptResult?.value?.trim()
      if (!value) {
        return
      }

      busy.value = true
      try {
        const label = await tabArchiveCreateLabel(value)
        labels.value = [...labels.value, label].sort((a, b) => a.name.localeCompare(b.name))
        editLabelIds.value = uniqueNumbers([...editLabelIds.value, label.id])
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to create label'))
      } finally {
        busy.value = false
      }
    }

    async function saveRecordEdit() {
      const id = editingRecordId.value
      if (!id) {
        return
      }

      busy.value = true
      try {
        let record = await tabArchiveUpdateRecord(id, {
          title: editTitle.value,
          comment: editComment.value,
          eternal: editEternal.value,
        })
        record = await tabArchiveSetRecordLabels(id, uniqueNumbers(editLabelIds.value))

        const cache = { ...archiveCache.value }
        cache[id] = record
        archiveCache.value = cache

        editVisible.value = false
        ElMessage.success('Record updated')
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to update record'))
      } finally {
        busy.value = false
      }
    }

    async function deleteRecord(record: TabArchiveRecord) {
      try {
        await ElMessageBox.confirm(
          `Delete archived record "${record.title || record.domain || record.url}"?`,
          'Delete record',
          {
            type: 'warning',
            confirmButtonText: 'Delete',
            cancelButtonText: 'Cancel',
          },
        )
      } catch {
        return
      }

      busy.value = true
      try {
        await tabArchiveDeleteRecord(record.id)
        const selected = new Set(selectedArchiveIds.value)
        selected.delete(record.id)
        selectedArchiveIds.value = selected

        const cache = { ...archiveCache.value }
        delete cache[record.id]
        archiveCache.value = cache

        ElMessage.success('Record deleted')
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to delete record'))
      } finally {
        busy.value = false
      }
    }

    function hideFavicon(event: Event) {
      const img = event.target as HTMLImageElement | null
      if (img) {
        img.style.display = 'none'
      }
    }

    // --- Live: select by keyword ---

    // --- Archive: replace URL ---

    function openReplaceUrlDialog() {
      replaceUrlFind.value = ''
      replaceUrlReplace.value = ''
      replaceUrlPreviewRows.value = []
      replaceUrlPreviewed.value = false
      replaceUrlVisible.value = true
    }

    async function previewReplaceUrl() {
      if (!replaceUrlFind.value.trim()) {
        ElMessage.warning('Find text must not be empty')
        return
      }
      busy.value = true
      try {
        const result = await tabArchiveReplaceUrl({
          find: replaceUrlFind.value,
          replace: replaceUrlReplace.value,
          preview: true,
        })
        replaceUrlPreviewRows.value = result.preview || []
        replaceUrlPreviewed.value = true
        if (replaceUrlPreviewRows.value.length === 0) {
          ElMessage.info('No records match the find text')
        }
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Preview failed'))
      } finally {
        busy.value = false
      }
    }

    async function applyReplaceUrl() {
      if (!replaceUrlFind.value.trim()) {
        ElMessage.warning('Find text must not be empty')
        return
      }
      const count = replaceUrlPreviewRows.value.length
      if (count === 0) {
        ElMessage.info('Nothing to replace')
        return
      }
      try {
        await ElMessageBox.confirm(
          `Replace URL in ${count} record(s)?`,
          'Confirm replace',
          {
            type: 'warning',
            confirmButtonText: 'Replace',
            cancelButtonText: 'Cancel',
          },
        )
      } catch {
        return
      }

      busy.value = true
      try {
        const result = await tabArchiveReplaceUrl({
          find: replaceUrlFind.value,
          replace: replaceUrlReplace.value,
          preview: false,
        })
        ElMessage.success(`Replaced URL in ${result.updated} record(s)`)
        replaceUrlVisible.value = false
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Replace failed'))
      } finally {
        busy.value = false
      }
    }

    // --- Group management ---

    async function createGroupPrompt(parentId?: number | null): Promise<TabArchiveGroup | null> {
      const group = await openCreateGroupDialog(parentId)
      if (!group) return null
      // Optimistic: insert into the correct tree immediately
      const newGroup: TabArchiveGroup = { ...group, children: [] }
      if (activePane.value === 'shelf') {
        if (parentId) {
          const parent = flatGroups.value.find(g => g.id === parentId)
          if (parent) parent.children = [...(parent.children || []), newGroup]
        } else {
          shelfGroupTree.value = [...shelfGroupTree.value, newGroup]
        }
        silentRefreshShelf()
      } else if (activePane.value === 'live') {
        if (parentId) {
          const parent = flatGroups.value.find(g => g.id === parentId)
          if (parent) parent.children = [...(parent.children || []), newGroup]
        } else {
          liveGroupTree.value = [...liveGroupTree.value, newGroup]
        }
        silentRefreshSnapshot()
      } else {
        if (parentId) {
          const parent = flatGroups.value.find(g => g.id === parentId)
          if (parent) parent.children = [...(parent.children || []), newGroup]
        } else {
          archiveGroupTree.value = [...archiveGroupTree.value, newGroup]
        }
        silentRefreshSnapshot()
      }
      return group
    }

    async function confirmDeleteGroup(group: TabArchiveGroup) {
      try {
        await ElMessageBox.confirm(
          `Delete group "${group.name}"? All tabs will be unassigned.`,
          'Delete group',
          { type: 'warning', confirmButtonText: 'Delete', cancelButtonText: 'Cancel' },
        )
      } catch {
        return
      }
      busy.value = true
      try {
        await tabArchiveDeleteGroup(group.id, activePane.value as GroupScope)
        ElMessage.success(`Group "${group.name}" deleted`)
        // Optimistic: remove from tree and un-assign items locally
        function removeFromTree(nodes: TabArchiveGroup[]): TabArchiveGroup[] {
          return nodes.filter(g => g.id !== group.id).map(g => ({ ...g, children: removeFromTree(g.children || []) }))
        }
        if (activePane.value === 'shelf') {
          shelfGroupTree.value = removeFromTree(shelfGroupTree.value)
          shelfItems.value = shelfItems.value.map(it => it.group_id === group.id ? { ...it, group_id: null } : it)
          silentRefreshShelf()
        } else if (activePane.value === 'live') {
          liveGroupTree.value = removeFromTree(liveGroupTree.value)
          liveRows.value = liveRows.value.map(r => r.group_id === group.id ? { ...r, group_id: null, group_name: null } : r)
          silentRefreshSnapshot()
        } else {
          archiveGroupTree.value = removeFromTree(archiveGroupTree.value)
          archiveRows.value = archiveRows.value.map(r => r.group_id === group.id ? { ...r, group_id: null, group_name: null } : r)
          silentRefreshSnapshot()
        }
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to delete group'))
        if (activePane.value === 'shelf') await loadShelf()
        else await loadSnapshot()
      } finally {
        busy.value = false
      }
    }

    async function groupAsWindow(windowId: number) {
      const promptResult = await ElMessageBox.prompt('Group name for this window', 'Group as window', {
        inputPlaceholder: 'e.g. work, research',
      }).catch(() => null)
      const value = promptResult?.value?.trim()
      if (!value) return
      busy.value = true
      try {
        const result = await tabArchiveGroupAsWindow(windowId, value)
        ElMessage.success(`Grouped ${result.count} tab(s) as "${result.group.name}"`)
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to group window'))
      } finally {
        busy.value = false
      }
    }

    async function sortByGroup(windowId?: number) {
      busy.value = true
      try {
        const result = await tabArchiveSortByGroup(windowId)
        ElMessage.success(`Sorted ${result.sorted ?? 0} tab(s) by group`)
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Sort by group failed'))
      } finally {
        busy.value = false
      }
    }

    async function splitByGroups() {
      busy.value = true
      try {
        const result = await tabArchiveSplitByGroups()
        ElMessage.success(`Split into ${result.windows_created} window(s) by group`)
        await loadSnapshot()
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Split by groups failed'))
      } finally {
        busy.value = false
      }
    }

    // --- Archive drag (vuedraggable): reorder + drop-into-group ---
    // Handled by onArchiveGroupChange above.

    // --- Organize mode ---

    function enterLiveOrganizeMode() {
      organizeSelectedIds.value = new Set()
      organizeBulkGroupId.value = null
      liveOrganizeMode.value = true
    }

    function enterArchiveOrganizeMode() {
      organizeSelectedIds.value = new Set()
      organizeBulkGroupId.value = null
      archiveOrganizeMode.value = true
    }

    function toggleOrganizeSelection(id: number) {
      const next = new Set(organizeSelectedIds.value)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      organizeSelectedIds.value = next
    }

    async function organizeBulkMoveSelected(forLive: boolean) {
      const ids = Array.from(organizeSelectedIds.value)
      if (ids.length === 0) {
        ElMessage.info('No items selected')
        return
      }
      organizeSaving.value = true
      try {
        if (forLive) {
          await tabArchiveSetLiveTabsGroup(ids, organizeBulkGroupId.value)
        } else {
          await Promise.all(ids.map(id => tabArchiveSetRecordGroup(id, organizeBulkGroupId.value)))
        }
        organizeSelectedIds.value = new Set()
        organizeBulkGroupId.value = null
        await loadSnapshot()
        ElMessage.success('Group assignment updated')
      } catch (error) {
        ElMessage.error(errorMessage(error, 'Failed to assign group'))
      } finally {
        organizeSaving.value = false
      }
    }

    async function createGroupInOrganize() {
      const group = await createGroupPrompt()
      if (group) {
        organizeBulkGroupId.value = group.id
      }
    }

    function formatTime(text: string | null): string {
      if (!text) {
        return '-'
      }
      return text
    }

    function formatDate(text: string | null): string {
      if (!text) return '-'
      return text.slice(0, 10)
    }

    watch(search, () => {
      scheduleSearchReload()
    })

    onMounted(async () => {
      await Promise.all([loadLabels(), loadSnapshot()])
    })

    onUnmounted(() => {
      if (searchTimer !== undefined) {
        window.clearTimeout(searchTimer)
      }
    })

    // --- Shelf ---
    const shelfItems = ref<ShelfItem[]>([])
    const collapsedShelfGroups = ref<Set<number>>(new Set())
    const shelfLoading = ref(false)

    async function loadShelf() {
      shelfLoading.value = true
      try {
        const resp = await tabArchiveGetShelf()
        shelfItems.value = resp.items || []
        shelfGroupTree.value = resp.group_tree || []
      } catch (e) {
        ElMessage.error(errorMessage(e, 'Failed to load shelf'))
      } finally {
        shelfLoading.value = false
      }
    }

    function toggleShelfGroupCollapse(groupId: number) {
      const next = new Set(collapsedShelfGroups.value)
      next.has(groupId) ? next.delete(groupId) : next.add(groupId)
      collapsedShelfGroups.value = next
    }

    function buildShelfTree(items: ShelfItem[], tree: TabArchiveGroup[]): ShelfTreeNode[] {
      const byGroupId = new Map<number | null, ShelfItem[]>()
      items.forEach(it => {
        const gid = it.group_id ?? null
        const arr = byGroupId.get(gid) ?? []
        arr.push(it)
        byGroupId.set(gid, arr)
      })

      function buildNodes(nodes: TabArchiveGroup[]): ShelfTreeNode[] {
        const result: ShelfTreeNode[] = []
        nodes.forEach(g => {
          const children: ShelfTreeNode[] = buildNodes(g.children || [])
          const directItems = byGroupId.get(g.id) || []
          directItems.forEach(it => children.push({ type: 'item', item: it }))
          result.push({ type: 'group', group: g, children })
        })
        return result
      }

      const rootNodes = buildNodes(tree)
      const ungroupedItems = byGroupId.get(null) || []
      ungroupedItems.forEach(it => rootNodes.push({ type: 'item', item: it }))
      return rootNodes
    }

    function countShelfItems(nodes: ShelfTreeNode[]): number {
      let count = 0
      nodes.forEach(n => {
        if (n.type === 'item') count++
        else count += countShelfItems(n.children)
      })
      return count
    }

    function flattenShelfTree(nodes: ShelfTreeNode[], depth: number, out: ShelfRenderItem[], ancestors: number[] = []) {
      nodes.forEach(n => {
        if (n.type === 'group') {
          out.push({ kind: 'group', group: n.group, depth, itemCount: countShelfItems(n.children), ancestorIds: ancestors, dragKey: 'grp-' + n.group.id })
          flattenShelfTree(n.children, depth + 1, out, [...ancestors, n.group.id])
        } else {
          out.push({ kind: 'item', item: n.item, depth, ancestorIds: ancestors, dragKey: 'item-' + n.item.id })
        }
      })
    }

    const shelfRenderList = computed<ShelfRenderItem[]>(() => {
      const tree = buildShelfTree(shelfItems.value, shelfGroupTree.value)
      const out: ShelfRenderItem[] = []
      flattenShelfTree(tree, 0, out)
      return out
    })

    async function addShelfItemPrompt() {
      try {
        const { value: url } = await ElMessageBox.prompt('Enter URL to add to Shelf', 'Add to Shelf', {
          confirmButtonText: 'Add',
          cancelButtonText: 'Cancel',
          inputPlaceholder: 'https://...',
          inputValidator: (v: string) => !!v.trim() || 'URL is required',
        })
        if (!url?.trim()) return
        await tabArchiveCreateShelfItem({ url: url.trim() })
        await loadShelf()
        ElMessage.success('Added to shelf')
      } catch (e: any) {
        if (e === 'cancel') return
        ElMessage.error(errorMessage(e, 'Failed to add item'))
      }
    }

    async function deleteShelfItem(itemId: number) {
      try {
        await ElMessageBox.confirm('Remove this item from the shelf?', 'Remove', {
          type: 'warning',
          confirmButtonText: 'Remove',
          cancelButtonText: 'Cancel',
        })
        await tabArchiveDeleteShelfItem(itemId)
        await loadShelf()
        ElMessage.success('Removed from shelf')
      } catch (e: any) {
        if (e === 'cancel') return
        ElMessage.error(errorMessage(e, 'Failed to remove item'))
      }
    }

    async function openShelfItem(itemId: number) {
      try {
        const result = await tabArchiveOpenShelfItem(itemId, 'current_window')
        if (!result.ok) {
          ElMessage.error(result.error || 'Failed to open')
        }
      } catch (e) {
        ElMessage.error(errorMessage(e, 'Failed to open item'))
      }
    }

    async function syncShelfFromBookmarks() {
      shelfLoading.value = true
      try {
        const result = await tabArchiveSyncShelfFromBrowserBookmarks()
        if ((result as any).error) {
          ElMessage.error((result as any).error)
        } else {
          ElMessage.success(`Synced ${(result as any).upserted ?? 0} bookmark(s) to shelf`)
          await loadShelf()
        }
      } catch (e) {
        ElMessage.error(errorMessage(e, 'Failed to sync bookmarks'))
      } finally {
        shelfLoading.value = false
      }
    }

    async function exportShelfToBookmarks() {
      shelfLoading.value = true
      try {
        const result = await tabArchiveExportShelfToBrowserBookmarks()
        if ((result as any).error) {
          ElMessage.error((result as any).error)
        } else {
          ElMessage.success('Shelf exported to browser bookmarks')
        }
      } catch (e) {
        ElMessage.error(errorMessage(e, 'Failed to export bookmarks'))
      } finally {
        shelfLoading.value = false
      }
    }

    // --- Shelf drag (vuedraggable): reorder + drop-into-group ---
    // Handled by onShelfGroupChange above.

    watch(activePane, (pane) => {
      if (pane === 'shelf') loadShelf()
    })

    return {
      activePane,
      loading,
      busy,
      search,
      extensionAvailable,
      liveError,
      liveRows,
      archiveRows,
      labels,
      liveGroupTree,
      archiveGroupTree,
      flatGroups,

      selectedLiveTabIds,
      selectedArchiveIds,
      allVisibleLiveSelected,
      someVisibleLiveSelected,
      allVisibleArchiveSelected,
      someVisibleArchiveSelected,

      restoreDestination,

      archiveEternalFilter,
      archiveLabelFilter,
      visibleArchiveRows,
      visibleArchiveByGroup,
      visibleArchiveTree,
      expiringCount,
      expireDays,
      showStale,
      expiringDismissed,

      editVisible,
      editTitle,
      editComment,
      editEternal,
      editLabelIds,

      labelNameById,
      groupNameById,
      collapsedLiveGroups,
      collapsedArchiveGroups,
      toggleLiveGroupCollapse,
      toggleArchiveGroupCollapse,
      editingHeaderTabId,
      editingHeaderValue,
      startEditHeader,
      cancelEditHeader,
      saveCustomHeader,
      liveGroupEditVisible,
      liveGroupEditId,
      liveGroupEditName,
      openLiveGroupEdit,
      saveLiveGroupEdit,
      createGroupDialogVisible,
      createGroupDialogName,
      confirmCreateGroupDialog,
      cancelCreateGroupDialog,
      collectVisible,
      collectGroupName,
      collectQuery,
      collectMatches,
      collectSaving,
      openCollect,
      runCollect,
      liveDndIndicator,
      liveRowsByWindow,
      liveRenderList,
      archiveRenderList,
      liveOutOfOrderTabIds,

      // organize mode
      liveOrganizeMode,
      archiveOrganizeMode,
      organizeSelectedIds,
      organizeBulkGroupId,
      organizeSaving,

      loadSnapshot,
      toggleLiveSelection,
      toggleVisibleLiveSelection,
      toggleArchiveSelection,
      toggleVisibleArchiveSelection,
      archiveSelectedLive,
      restoreSelectedArchive,
      closeSingleLive,
      closeSelectedLiveOnly,
      mergeAll,
      groupByDomain,
      startEditRecord,
      createLabelInEditor,
      saveRecordEdit,
      deleteRecord,
      hideFavicon,
      heatTagType,
      formatTime,
      formatDate,
      goBack: () => router.push('/browser-agent'),

      // group functions
      groupAsWindow,
      sortByGroup,
      splitByGroups,
      enterLiveOrganizeMode,
      enterArchiveOrganizeMode,
      toggleOrganizeSelection,
      organizeBulkMoveSelected,
      createGroupInOrganize,
      confirmDeleteGroup,
      createGroupPrompt,

      // drag handlers (pragmatic-drag-and-drop — directives + monitor)
      // These payload builders are used by v-pdnd-drag in the template.
      archiveItemsByGroup,
      liveItemsByGroup,

      replaceUrlVisible,
      replaceUrlFind,
      replaceUrlReplace,
      replaceUrlPreviewRows,
      replaceUrlPreviewed,
      openReplaceUrlDialog,
      previewReplaceUrl,
      applyReplaceUrl,

      settingsOpen, settingsCfg, settingsSaving,
      openSettings, saveSettings,
      Setting,

      // shelf
      shelfItems,
      shelfGroupTree,
      shelfRenderList,
      collapsedShelfGroups,
      shelfLoading,
      shelfItemsByGroup,
      toggleShelfGroupCollapse,
      loadShelf,
      addShelfItemPrompt,
      deleteShelfItem,
      openShelfItem,
      syncShelfFromBookmarks,
      exportShelfToBookmarks,
    }
  },
})
