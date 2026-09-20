import { defineComponent, ref, computed } from 'vue'
import { vPdndDrag, vPdndLiveRow, useDndMonitor } from './dnd'
import type { DragPayload, MonitorDropEvent } from './dnd'
import type { TabArchiveGroup, TabArchiveLiveCard } from '@/browser_agent/service/Model'

// ---------------------------------------------------------------------------
// Mock data — all IDs are negative so they never collide with real backend IDs
// ---------------------------------------------------------------------------

let _nextId = -1
function nextId() { return _nextId-- }

function makeTab(overrides: Partial<TabArchiveLiveCard>): TabArchiveLiveCard {
  const id = nextId()
  return {
    tab_id: id,
    window_id: -1,
    url: 'https://example.com/page' + id,
    title: 'Mock Tab ' + Math.abs(id),
    domain: 'example.com',
    favicon_url: '',
    pinned: false,
    heat_level: 'cold',
    first_seen_at: '2026-01-01',
    group_id: null,
    group_name: null,
    comment: null,
    labels: [],
    display_order: null,
    custom_header: null,
    ...overrides,
  }
}

function makeGroup(name: string, parentId: number | null = null): TabArchiveGroup {
  return {
    id: nextId(),
    name,
    parent_id: parentId,
    scope: 'live',
    display_order: 1000,
    children: [],
  }
}

// Build initial mock dataset: 2 windows, 3 groups, ~20 tabs
function buildMockData(): {
  groups: TabArchiveGroup[]
  tabs: TabArchiveLiveCard[]
} {
  const gWork = makeGroup('Work')
  const gPersonal = makeGroup('Personal')
  const gResearch = makeGroup('Research')
  gWork.display_order = 1000
  gPersonal.display_order = 2000
  gResearch.display_order = 3000

  const tabs: TabArchiveLiveCard[] = [
    // Window 1 — grouped tabs
    makeTab({ window_id: -1, group_id: gWork.id, group_name: gWork.name, title: 'PR #42 Review', domain: 'github.com', url: 'https://github.com/org/repo/pull/42', favicon_url: 'https://github.com/favicon.ico', heat_level: 'high' }),
    makeTab({ window_id: -1, group_id: gWork.id, group_name: gWork.name, title: 'CI Pipeline Logs', domain: 'ci.example.com', url: 'https://ci.example.com/build/123', heat_level: 'medium' }),
    makeTab({ window_id: -1, group_id: gWork.id, group_name: gWork.name, title: 'Jira Board', domain: 'jira.example.com', url: 'https://jira.example.com/board', heat_level: 'medium' }),
    makeTab({ window_id: -1, group_id: gPersonal.id, group_name: gPersonal.name, title: 'Gmail Inbox', domain: 'mail.google.com', url: 'https://mail.google.com', favicon_url: 'https://www.google.com/favicon.ico', heat_level: 'high' }),
    makeTab({ window_id: -1, group_id: gPersonal.id, group_name: gPersonal.name, title: 'Calendar', domain: 'calendar.google.com', url: 'https://calendar.google.com', favicon_url: 'https://www.google.com/favicon.ico', heat_level: 'medium' }),
    makeTab({ window_id: -1, group_id: gResearch.id, group_name: gResearch.name, title: 'Vue 3 Docs — Composition API', domain: 'vuejs.org', url: 'https://vuejs.org/guide/extras/composition-api-faq.html', heat_level: 'low' }),
    makeTab({ window_id: -1, group_id: gResearch.id, group_name: gResearch.name, title: 'pragmatic-drag-and-drop', domain: 'npmjs.com', url: 'https://www.npmjs.com/package/@atlaskit/pragmatic-drag-and-drop', heat_level: 'low' }),
    // Window 1 — ungrouped tabs
    makeTab({ window_id: -1, title: 'Google', domain: 'google.com', url: 'https://google.com', favicon_url: 'https://www.google.com/favicon.ico', heat_level: 'cold' }),
    makeTab({ window_id: -1, title: 'New Tab', domain: '', url: 'chrome://newtab', heat_level: 'cold' }),
    makeTab({ window_id: -1, title: 'Stack Overflow — Array methods', domain: 'stackoverflow.com', url: 'https://stackoverflow.com/q/12345', heat_level: 'cold' }),
    // Window 2 — ungrouped tabs
    makeTab({ window_id: -2, title: 'Figma — Design System', domain: 'figma.com', url: 'https://figma.com/file/abc', heat_level: 'high' }),
    makeTab({ window_id: -2, title: 'Notion — Project Notes', domain: 'notion.so', url: 'https://notion.so/project', heat_level: 'medium' }),
    makeTab({ window_id: -2, title: 'YouTube — Demo Video', domain: 'youtube.com', url: 'https://youtube.com/watch?v=demo', heat_level: 'low' }),
    makeTab({ window_id: -2, title: 'Twitter / X', domain: 'x.com', url: 'https://x.com', heat_level: 'cold' }),
    makeTab({ window_id: -2, title: 'Hacker News', domain: 'news.ycombinator.com', url: 'https://news.ycombinator.com', heat_level: 'cold' }),
  ]

  return {
    groups: [gWork, gPersonal, gResearch],
    tabs,
  }
}

// ---------------------------------------------------------------------------
// Types reused from TabsView.ts (copied so MockLiveView is self-contained)
// ---------------------------------------------------------------------------

type LiveRenderItem =
  | { kind: 'group'; group: TabArchiveGroup; depth: number; tabCount: number; ancestorIds: number[]; dragKey: string }
  | { kind: 'tab'; card: TabArchiveLiveCard; depth: number; ancestorIds: number[]; dragKey: string }

type HeatTagType = 'danger' | 'warning' | 'success' | 'info'

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default defineComponent({
  name: 'MockLiveView',
  directives: {
    pdndDrag: vPdndDrag,
    pdndLiveRow: vPdndLiveRow,
    focus: { mounted: (el: HTMLElement) => el.focus() },
  },
  setup() {
    const { groups: initialGroups, tabs: initialTabs } = buildMockData()

    const mockGroups = ref<TabArchiveGroup[]>(initialGroups)
    const mockTabs = ref<TabArchiveLiveCard[]>(initialTabs)

    // Flat ordered list of dragKeys per windowId (same pattern as live TabsView)
    const orderByWindow = ref<Map<number, string[]>>(new Map())

    // Collapsed groups
    const collapsedGroups = ref<Set<number>>(new Set())

    // DnD indicator
    const dndIndicator = ref<{ key: string; edge: 'top' | 'bottom' | 'into' } | null>(null)

    // Inline custom_header editing
    const editingHeaderTabId = ref<number | null>(null)
    const editingHeaderValue = ref('')

    // Collect dialog
    const collectVisible = ref(false)
    const collectGroupId = ref<number | null>(null)
    const collectGroupName = ref('')
    const collectWindowId = ref<number | null>(null)
    const collectQuery = ref('')

    // Create group dialog
    const createGroupVisible = ref(false)
    const createGroupName = ref('')
    const createGroupParentId = ref<number | null>(null)
    let createGroupClosedAt = 0

    // Edit group dialog
    const editGroupVisible = ref(false)
    const editGroupId = ref<number | null>(null)
    const editGroupName = ref('')

    // Log of mock actions for UX debugging
    const actionLog = ref<string[]>([])
    function log(msg: string) {
      actionLog.value = [new Date().toLocaleTimeString() + '  ' + msg, ...actionLog.value.slice(0, 29)]
    }

    // Build initial order
    function buildOrder(): Map<number, string[]> {
      const winMap = new Map<number, TabArchiveLiveCard[]>()
      mockTabs.value.forEach(t => {
        const arr = winMap.get(t.window_id) ?? []
        arr.push(t)
        winMap.set(t.window_id, arr)
      })

      const result = new Map<number, string[]>()
      let first = true
      winMap.forEach((winTabs, windowId) => {
        const byGroup = new Map<number | null, TabArchiveLiveCard[]>()
        winTabs.forEach(t => {
          const gid = t.group_id ?? null
          const arr = byGroup.get(gid) ?? []
          arr.push(t)
          byGroup.set(gid, arr)
        })

        const keys: string[] = []
        if (first) {
          mockGroups.value.forEach(g => {
            keys.push('grp-' + g.id)
            ;(byGroup.get(g.id) ?? []).forEach(t => keys.push('tab-' + t.tab_id))
          })
          first = false
        }
        ;(byGroup.get(null) ?? []).forEach(t => keys.push('tab-' + t.tab_id))
        result.set(windowId, keys)
      })
      return result
    }

    orderByWindow.value = buildOrder()

    // ---------------------------------------------------------------------------
    // Computed render list (mirrors liveRenderList in TabsView.ts)
    // ---------------------------------------------------------------------------

    function getGroupAncestors(groupId: number): number[] {
      function search(nodes: TabArchiveGroup[], path: number[]): number[] | null {
        for (const g of nodes) {
          if (g.id === groupId) return path
          const found = search(g.children || [], [...path, g.id])
          if (found) return found
        }
        return null
      }
      return search(mockGroups.value, []) ?? []
    }

    function countTabsInGroup(groupId: number): number {
      return mockTabs.value.filter(t => t.group_id === groupId).length
    }

    const renderList = computed<Array<{
      windowId: number
      items: LiveRenderItem[]
      tabCount: number
    }>>(() => {
      const tabMap = new Map<number, TabArchiveLiveCard>()
      mockTabs.value.forEach(t => tabMap.set(t.tab_id, t))
      const groupMap = new Map<number, TabArchiveGroup>()
      function indexGroups(nodes: TabArchiveGroup[]) {
        nodes.forEach(g => { groupMap.set(g.id, g); indexGroups(g.children || []) })
      }
      indexGroups(mockGroups.value)

      return Array.from(orderByWindow.value.entries()).map(([windowId, keys]) => {
        const items: LiveRenderItem[] = []
        keys.forEach(key => {
          if (key.startsWith('grp-')) {
            const gid = parseInt(key.slice(4))
            const group = groupMap.get(gid)
            if (!group) return
            const ancestors = getGroupAncestors(gid)
            const topAncestor = ancestors[0]
            if (topAncestor !== undefined && collapsedGroups.value.has(topAncestor)) return
            const depth = ancestors.length
            items.push({ kind: 'group', group, depth, tabCount: countTabsInGroup(gid), ancestorIds: ancestors, dragKey: key })
          } else if (key.startsWith('tab-')) {
            const tabId = parseInt(key.slice(4))
            const card = tabMap.get(tabId)
            if (!card) return
            const ancestors = card.group_id != null ? getGroupAncestors(card.group_id) : []
            const isCollapsed = (card.group_id != null && collapsedGroups.value.has(card.group_id)) ||
              ancestors.some(aid => collapsedGroups.value.has(aid))
            if (isCollapsed) return
            const depth = card.group_id != null ? ancestors.length + 1 : 0
            const ancestorIds = card.group_id != null ? [...ancestors, card.group_id] : []
            items.push({ kind: 'tab', card, depth, ancestorIds, dragKey: key })
          }
        })
        return { windowId, items, tabCount: items.filter(i => i.kind === 'tab').length }
      })
    })

    // ---------------------------------------------------------------------------
    // Drop handling (mirrors handleLiveDrop in TabsView.ts)
    // ---------------------------------------------------------------------------

    function inferTabGroup(order: string[], tabKey: string): number | null {
      const pos = order.indexOf(tabKey)
      for (let i = pos - 1; i >= 0; i--) {
        const k = order[i]
        if (k.startsWith('grp-')) return parseInt(k.slice(4))
        if (k.startsWith('tab-')) {
          const tid = parseInt(k.slice(4))
          const card = mockTabs.value.find(t => t.tab_id === tid)
          if (card?.group_id != null) return card.group_id
          return null
        }
      }
      return null
    }

    function handleDrop(evt: MonitorDropEvent) {
      const { source, dropElement } = evt
      if (source.type !== 'live-tab' && source.type !== 'live-group') return

      const dragKey = dropElement.dataset.dragKey
      if (!dragKey) return
      const edge: 'top' | 'bottom' | 'into' = evt.liveZone ?? 'bottom'

      const sourceKey = source.type === 'live-tab'
        ? 'tab-' + (source as Extract<DragPayload, { type: 'live-tab' }>).tabId
        : 'grp-' + (source as Extract<DragPayload, { type: 'live-group' }>).id

      if (sourceKey === dragKey) { dndIndicator.value = null; return }

      // Find source window
      let srcWinId = -1
      let srcOrder: string[] = []
      for (const [wid, ord] of orderByWindow.value.entries()) {
        if (ord.includes(sourceKey)) { srcWinId = wid; srcOrder = [...ord]; break }
      }
      if (srcWinId === -1) { dndIndicator.value = null; return }

      // Find target window
      let tgtWinId = -1
      let tgtOrder: string[] = []
      for (const [wid, ord] of orderByWindow.value.entries()) {
        if (ord.includes(dragKey)) { tgtWinId = wid; tgtOrder = [...ord]; break }
      }
      if (tgtWinId === -1) { dndIndicator.value = null; return }

      // Build block (group moves with its member tabs)
      let blockKeys: string[] = [sourceKey]
      if (sourceKey.startsWith('grp-')) {
        const gid = parseInt(sourceKey.slice(4))
        const fromIdx = srcOrder.indexOf(sourceKey)
        for (let i = fromIdx + 1; i < srcOrder.length; i++) {
          const k = srcOrder[i]
          if (k.startsWith('grp-')) break
          if (k.startsWith('tab-')) {
            const card = mockTabs.value.find(t => t.tab_id === parseInt(k.slice(4)))
            if (card?.group_id === gid) blockKeys.push(k)
            else break
          }
        }
      }

      const newMap = new Map(orderByWindow.value)

      if (srcWinId === tgtWinId) {
        const order = [...srcOrder]
        const fromIdx = order.indexOf(sourceKey)
        order.splice(fromIdx, blockKeys.length)

        if (edge === 'into' && dragKey.startsWith('grp-')) {
          const gid = parseInt(dragKey.slice(4))
          const toIdx = order.indexOf(dragKey)
          let insertAt = toIdx + 1
          for (let i = toIdx + 1; i < order.length; i++) {
            const k = order[i]
            if (k.startsWith('grp-')) break
            if (k.startsWith('tab-')) {
              const card = mockTabs.value.find(t => t.tab_id === parseInt(k.slice(4)))
              if (card?.group_id === gid) insertAt = i + 1
              else break
            }
          }
          order.splice(insertAt, 0, ...blockKeys)
        } else {
          const toIdx = order.indexOf(dragKey)
          if (toIdx < 0) { dndIndicator.value = null; return }
          order.splice(edge === 'top' ? toIdx : toIdx + 1, 0, ...blockKeys)
        }
        newMap.set(srcWinId, order)
      } else {
        // Cross-window
        const fromIdx = srcOrder.indexOf(sourceKey)
        srcOrder.splice(fromIdx, blockKeys.length)
        newMap.set(srcWinId, srcOrder)

        if (edge === 'into' && dragKey.startsWith('grp-')) {
          const gid = parseInt(dragKey.slice(4))
          const toIdx = tgtOrder.indexOf(dragKey)
          let insertAt = toIdx + 1
          for (let i = toIdx + 1; i < tgtOrder.length; i++) {
            const k = tgtOrder[i]
            if (k.startsWith('grp-')) break
            if (k.startsWith('tab-')) {
              const card = mockTabs.value.find(t => t.tab_id === parseInt(k.slice(4)))
              if (card?.group_id === gid) insertAt = i + 1
              else break
            }
          }
          tgtOrder.splice(insertAt, 0, ...blockKeys)
        } else {
          const toIdx = tgtOrder.indexOf(dragKey)
          if (toIdx < 0) { dndIndicator.value = null; return }
          tgtOrder.splice(edge === 'top' ? toIdx : toIdx + 1, 0, ...blockKeys)
        }
        newMap.set(tgtWinId, tgtOrder)
      }

      orderByWindow.value = newMap

      // Update group_id on tab cards after drop
      if (source.type === 'live-tab') {
        const tabId = (source as Extract<DragPayload, { type: 'live-tab' }>).tabId
        const effectiveOrder = [...(newMap.get(tgtWinId) ?? [])]
        const newGroupId = inferTabGroup(effectiveOrder, sourceKey)
        const idx = mockTabs.value.findIndex(t => t.tab_id === tabId)
        if (idx >= 0) {
          mockTabs.value[idx] = { ...mockTabs.value[idx], group_id: newGroupId }
          const g = mockGroups.value.find(g => g.id === newGroupId)
          log(`Move tab "${mockTabs.value[idx].title}" → ${g ? '"' + g.name + '"' : 'ungrouped'}`)
        }
      } else {
        const gid = (source as Extract<DragPayload, { type: 'live-group' }>).id
        const g = mockGroups.value.find(g => g.id === gid)
        log(`Reorder group "${g?.name ?? gid}"`)
      }

      dndIndicator.value = null
    }

    useDndMonitor(handleDrop, (evt) => {
      if (evt.source.type !== 'live-tab' && evt.source.type !== 'live-group') return
      if (!evt.dropElement) { dndIndicator.value = null; return }
      const dragKey = evt.dropElement.dataset.dragKey
      if (!dragKey) { dndIndicator.value = null; return }
      const overAttr = evt.dropElement.dataset.dropOver
      const edgeAttr = evt.dropElement.dataset.edge
      const edge: 'top' | 'bottom' | 'into' = overAttr ? 'into' : (edgeAttr === 'top' ? 'top' : 'bottom')
      dndIndicator.value = { key: dragKey, edge }
    })

    // ---------------------------------------------------------------------------
    // Group actions (pure frontend mutations)
    // ---------------------------------------------------------------------------

    function toggleGroupCollapse(groupId: number) {
      const next = new Set(collapsedGroups.value)
      next.has(groupId) ? next.delete(groupId) : next.add(groupId)
      collapsedGroups.value = next
    }

    function openCollect(group: TabArchiveGroup, windowId: number) {
      collectGroupId.value = group.id
      collectGroupName.value = group.name
      collectWindowId.value = windowId
      collectQuery.value = ''
      collectVisible.value = true
    }

    const collectMatches = computed(() => {
      const q = collectQuery.value.trim().toLowerCase()
      if (!q || collectWindowId.value === null) return []
      return mockTabs.value.filter(t =>
        t.window_id === collectWindowId.value &&
        (t.group_id ?? null) === null &&
        (t.url.toLowerCase().includes(q) || t.title.toLowerCase().includes(q))
      )
    })

    function runCollect() {
      const matches = collectMatches.value
      const ids = new Set(matches.map(t => t.tab_id))
      const gid = collectGroupId.value
      if (!ids.size || gid === null) return

      mockTabs.value = mockTabs.value.map(t => ids.has(t.tab_id) ? { ...t, group_id: gid } : t)

      // Update order: remove from wherever, insert after group header
      const tabKeys = [...ids].map(id => 'tab-' + id)
      const tabKeySet = new Set(tabKeys)
      const groupKey = 'grp-' + gid
      const newMap = new Map(orderByWindow.value)
      newMap.forEach((order, wid) => { newMap.set(wid, order.filter(k => !tabKeySet.has(k))) })
      let inserted = false
      newMap.forEach((order, wid) => {
        const gIdx = order.indexOf(groupKey)
        if (gIdx < 0 || inserted) return
        let insertAt = gIdx + 1
        for (let i = gIdx + 1; i < order.length; i++) {
          const k = order[i]
          if (k.startsWith('grp-')) break
          if (k.startsWith('tab-')) {
            const card = mockTabs.value.find(t => t.tab_id === parseInt(k.slice(4)))
            if (card?.group_id === gid) insertAt = i + 1
            else break
          }
        }
        order.splice(insertAt, 0, ...tabKeys)
        newMap.set(wid, order)
        inserted = true
      })
      orderByWindow.value = newMap
      collectVisible.value = false
      log(`Collected ${matches.length} tab(s) into "${collectGroupName.value}"`)
    }

    function openCreateGroup(parentId?: number | null) {
      if (createGroupVisible.value || Date.now() - createGroupClosedAt < 400) return
      createGroupName.value = ''
      createGroupParentId.value = parentId ?? null
      createGroupVisible.value = true
    }

    function confirmCreateGroup() {
      const name = createGroupName.value.trim()
      if (!name) return
      createGroupVisible.value = false
      createGroupClosedAt = Date.now()

      const newGroup: TabArchiveGroup = {
        id: nextId(),
        name,
        parent_id: createGroupParentId.value,
        scope: 'live',
        display_order: (mockGroups.value.length + 1) * 1000,
        children: [],
      }
      mockGroups.value = [...mockGroups.value, newGroup]

      // Add group key to first window's order
      const firstWinId = orderByWindow.value.keys().next().value
      if (firstWinId !== undefined) {
        const order = [...(orderByWindow.value.get(firstWinId) ?? []), 'grp-' + newGroup.id]
        const newMap = new Map(orderByWindow.value)
        newMap.set(firstWinId, order)
        orderByWindow.value = newMap
      }
      log(`Created group "${name}"`)
    }

    function cancelCreateGroup() {
      createGroupVisible.value = false
      createGroupClosedAt = Date.now()
    }

    function openEditGroup(group: TabArchiveGroup) {
      editGroupId.value = group.id
      editGroupName.value = group.name
      editGroupVisible.value = true
    }

    function confirmEditGroup() {
      const name = editGroupName.value.trim()
      const id = editGroupId.value
      if (!name || !id) return
      mockGroups.value = mockGroups.value.map(g => g.id === id ? { ...g, name } : g)
      editGroupVisible.value = false
      log(`Renamed group → "${name}"`)
    }

    function deleteGroup(group: TabArchiveGroup) {
      mockGroups.value = mockGroups.value.filter(g => g.id !== group.id)
      mockTabs.value = mockTabs.value.map(t => t.group_id === group.id ? { ...t, group_id: null } : t)
      // Remove group key from all orders
      const groupKey = 'grp-' + group.id
      const newMap = new Map(orderByWindow.value)
      newMap.forEach((order, wid) => newMap.set(wid, order.filter(k => k !== groupKey)))
      orderByWindow.value = newMap
      log(`Deleted group "${group.name}"`)
    }

    function addTab(windowId: number) {
      const tab = makeTab({ window_id: windowId, title: 'New Tab ' + Math.abs(nextId() + 1) })
      // nextId() was called inside makeTab already; adjust
      mockTabs.value = [...mockTabs.value, tab]
      // Append to that window's order
      const newMap = new Map(orderByWindow.value)
      const order = [...(newMap.get(windowId) ?? []), 'tab-' + tab.tab_id]
      newMap.set(windowId, order)
      orderByWindow.value = newMap
      log(`Added tab "${tab.title}" to window ${windowId}`)
    }

    function closeTab(tabId: number) {
      const tab = mockTabs.value.find(t => t.tab_id === tabId)
      mockTabs.value = mockTabs.value.filter(t => t.tab_id !== tabId)
      const tabKey = 'tab-' + tabId
      const newMap = new Map(orderByWindow.value)
      newMap.forEach((order, wid) => newMap.set(wid, order.filter(k => k !== tabKey)))
      orderByWindow.value = newMap
      log(`Closed tab "${tab?.title ?? tabId}"`)
    }

    // custom_header inline editing
    function startEditHeader(card: TabArchiveLiveCard) {
      editingHeaderTabId.value = card.tab_id
      editingHeaderValue.value = card.custom_header ?? ''
    }

    function cancelEditHeader() {
      editingHeaderTabId.value = null
      editingHeaderValue.value = ''
    }

    function saveCustomHeader(card: TabArchiveLiveCard) {
      const tabId = card.tab_id
      const value = editingHeaderValue.value.trim() || null
      editingHeaderTabId.value = null
      const idx = mockTabs.value.findIndex(t => t.tab_id === tabId)
      if (idx >= 0) mockTabs.value[idx] = { ...mockTabs.value[idx], custom_header: value }
      log(`Set custom header on tab "${card.title}" → ${value ? '"' + value + '"' : 'cleared'}`)
    }

    function resetAll() {
      const { groups, tabs } = buildMockData()
      mockGroups.value = groups
      mockTabs.value = tabs
      orderByWindow.value = buildOrder()
      collapsedGroups.value = new Set()
      actionLog.value = ['Reset to initial mock data']
    }

    const heatTagType = (heat: string): 'danger' | 'warning' | 'success' | 'info' => {
      if (heat === 'high') return 'danger'
      if (heat === 'medium') return 'warning'
      if (heat === 'low') return 'success'
      return 'info'
    }

    function hideFavicon(event: Event) {
      const img = event.target as HTMLImageElement | null
      if (img) img.style.display = 'none'
    }

    const flatGroups = computed<TabArchiveGroup[]>(() => {
      const result: TabArchiveGroup[] = []
      function walk(nodes: TabArchiveGroup[]) {
        nodes.forEach(g => { result.push(g); walk(g.children || []) })
      }
      walk(mockGroups.value)
      return result
    })

    return {
      renderList,
      mockGroups,
      flatGroups,
      collapsedGroups,
      dndIndicator,
      actionLog,

      editingHeaderTabId,
      editingHeaderValue,
      startEditHeader,
      cancelEditHeader,
      saveCustomHeader,

      collectVisible,
      collectGroupName,
      collectQuery,
      collectMatches,
      openCollect,
      runCollect,

      createGroupVisible,
      createGroupName,
      openCreateGroup,
      confirmCreateGroup,
      cancelCreateGroup,

      editGroupVisible,
      editGroupName,
      openEditGroup,
      confirmEditGroup,

      toggleGroupCollapse,
      deleteGroup,
      addTab,
      closeTab,
      heatTagType,
      hideFavicon,
      resetAll,
    }
  },
})
