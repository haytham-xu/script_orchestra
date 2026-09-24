/**
 * Pragmatic drag-and-drop directives for the Tabs Workspace.
 *
 * v-pdnd-drag      — makes an element draggable; binding value = DragPayload
 * v-pdnd-drop      — drop target (group-content zone); binding value = DropPayload
 * v-pdnd-group-hdr — group header: handles both group-reorder drags AND
 *                    item drags with closest-edge (top = before group / bottom = into group)
 * v-pdnd-live-row  — Live pane unified row: draggable + drop target by edge/into.
 *                    Sets data-drag-key, data-edge, data-drop-over on the element.
 *
 * useDndMonitor(onDrop, onDragUpdate?) — installs a monitor and auto-cleans on component unmount.
 */
import { onUnmounted } from 'vue'
import {
  draggable,
  dropTargetForElements,
  monitorForElements,
} from '@atlaskit/pragmatic-drag-and-drop/element/adapter'
import { attachClosestEdge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge/attach-closest-edge'
import { extractClosestEdge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge/extract-closest-edge'
import type { Edge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/dist/types/types'

export type { Edge }

// ---- payload types ---------------------------------------------------------

export type DragPayload =
  | { type: 'archive-record'; id: number; groupId: number | null }
  | { type: 'live-tab'; tabId: number; groupId: number | null; windowId: number }
  | { type: 'shelf-item'; id: number; groupId: number | null }
  | { type: 'archive-group'; id: number }
  | { type: 'live-group'; id: number }
  | { type: 'shelf-group'; id: number }

export type DropPayload =
  | { zone: 'archive-group-content'; groupId: number | null }
  | { zone: 'archive-group-header'; groupId: number }
  | { zone: 'live-group-content'; groupId: number | null; windowId: number }
  | { zone: 'live-group-header'; groupId: number }
  | { zone: 'shelf-group-content'; groupId: number | null }
  | { zone: 'shelf-group-header'; groupId: number }
  | { zone: 'live-row'; dragKey: string; isGroup: boolean }

// ---- cleanup registry ------------------------------------------------------

const registry = new WeakMap<Element, () => void>()

function register(el: Element, cleanup: () => void) {
  const prev = registry.get(el)
  if (prev) prev()
  registry.set(el, cleanup)
}

function unregister(el: Element) {
  const fn = registry.get(el)
  if (fn) {
    fn()
    registry.delete(el)
  }
}

// ---- helper builders -------------------------------------------------------

function makeDraggable(el: HTMLElement, payload: DragPayload) {
  return draggable({
    element: el,
    getInitialData: () => payload as unknown as Record<string, unknown>,
    onDragStart: () => el.setAttribute('data-dragging', '1'),
    onDrop: () => el.removeAttribute('data-dragging'),
  })
}

function makeDropTarget(el: HTMLElement, payload: DropPayload) {
  return dropTargetForElements({
    element: el,
    getData: () => payload as unknown as Record<string, unknown>,
    canDrop({ source }) {
      const d = source.data as DragPayload
      if (payload.zone === 'archive-group-content') return d.type === 'archive-record'
      if (payload.zone === 'live-group-content') return d.type === 'live-tab'
      if (payload.zone === 'shelf-group-content') return d.type === 'shelf-item'
      return false
    },
    onDragEnter: () => el.setAttribute('data-drop-over', '1'),
    onDragLeave: () => el.removeAttribute('data-drop-over'),
    onDrop: () => el.removeAttribute('data-drop-over'),
  })
}

// makeGroupHeader: dual-purpose drop target on the group header row.
//   - group drags (archive-group / live-group / shelf-group): reorder groups.
//     Edge is ignored — position is determined by which header you drop on.
//   - item drags (archive-record / live-tab / shelf-item):
//     top half  → "before this group" (place item as ungrouped above the group)
//     bottom half → "into this group"  (add item to this group)
function makeGroupHeader(el: HTMLElement, payload: DropPayload) {
  if (!payload.zone.endsWith('-group-header')) {
    throw new Error('makeGroupHeader requires a -group-header zone payload')
  }
  const pane = payload.zone.replace('-group-header', '') as 'archive' | 'live' | 'shelf'
  return dropTargetForElements({
    element: el,
    getData({ input }) {
      return attachClosestEdge(payload as unknown as Record<string, unknown>, {
        element: el,
        input,
        allowedEdges: ['top', 'bottom'],
      })
    },
    canDrop({ source }) {
      const d = source.data as DragPayload
      // allow group-drag for reorder
      if (pane === 'archive') return d.type === 'archive-group' || d.type === 'archive-record'
      if (pane === 'live') return d.type === 'live-group' || d.type === 'live-tab'
      if (pane === 'shelf') return d.type === 'shelf-group' || d.type === 'shelf-item'
      return false
    },
    onDrag({ self, source }) {
      const d = source.data as DragPayload
      const isGroupDrag = d.type === 'archive-group' || d.type === 'live-group' || d.type === 'shelf-group'
      if (isGroupDrag) {
        // group reorder: highlight header, no edge indicator
        el.setAttribute('data-drop-over', '1')
        el.removeAttribute('data-edge')
      } else {
        // item drag: show edge indicator
        el.removeAttribute('data-drop-over')
        const edge = extractClosestEdge(self.data)
        if (edge) el.setAttribute('data-edge', edge)
        else el.removeAttribute('data-edge')
      }
    },
    onDragLeave: () => {
      el.removeAttribute('data-drop-over')
      el.removeAttribute('data-edge')
    },
    onDrop: () => {
      el.removeAttribute('data-drop-over')
      el.removeAttribute('data-edge')
    },
  })
}

// makeLiveRow: Live pane unified row — draggable + drop target.
// - Tab rows and group rows each get this applied.
// - For group rows, isGroup=true enables "drop into" (data-drop-over) when a
//   tab or group is dragged over it without an edge; edge detection is top/bottom.
// - Sets data-drag-key (for the monitor to identify), data-edge, data-drop-over.
// Compute drop zone for a group row: top 25% → 'top', bottom 25% → 'bottom', middle → 'into'
export function groupDropZone(el: HTMLElement, inputY: number): 'top' | 'bottom' | 'into' {
  const rect = el.getBoundingClientRect()
  const relY = inputY - rect.top
  if (relY < rect.height * 0.25) return 'top'
  if (relY > rect.height * 0.75) return 'bottom'
  return 'into'
}

function makeLiveRow(el: HTMLElement, drag: DragPayload, dropKey: string, isGroup: boolean) {
  const cleanup1 = makeDraggable(el, drag)
  const cleanup2 = dropTargetForElements({
    element: el,
    getData({ input }) {
      const base: Record<string, unknown> = {
        zone: 'live-row',
        dragKey: dropKey,
        isGroup,
      }
      // For group rows with tab drags, we handle edge ourselves; still attach for tab-tab drops
      return attachClosestEdge(base, {
        element: el,
        input,
        allowedEdges: ['top', 'bottom'],
      })
    },
    canDrop({ source }) {
      const d = source.data as DragPayload
      return d.type === 'live-tab' || d.type === 'live-group'
    },
    onDrag({ self, location }) {
      if (isGroup) {
        // Both tab-on-group and group-on-group: use 25/50/25 split
        const zone = groupDropZone(el, location.current.input.clientY)
        if (zone === 'into') {
          el.setAttribute('data-drop-over', '1')
          el.removeAttribute('data-edge')
        } else {
          el.removeAttribute('data-drop-over')
          el.setAttribute('data-edge', zone)
        }
      } else {
        el.removeAttribute('data-drop-over')
        const edge = extractClosestEdge(self.data)
        if (edge) el.setAttribute('data-edge', edge)
        else el.removeAttribute('data-edge')
      }
    },
    onDragLeave: () => {
      el.removeAttribute('data-drop-over')
      el.removeAttribute('data-edge')
    },
    onDrop: () => {
      el.removeAttribute('data-drop-over')
      el.removeAttribute('data-edge')
    },
  })
  return () => { cleanup1(); cleanup2() }
}

// ---- v-pdnd-drag directive --------------------------------------------------

export const vPdndDrag = {
  mounted(el: HTMLElement, binding: { value: DragPayload }) {
    register(el, makeDraggable(el, binding.value))
  },
  updated(el: HTMLElement, binding: { value: DragPayload }) {
    unregister(el)
    register(el, makeDraggable(el, binding.value))
  },
  unmounted(el: HTMLElement) {
    unregister(el)
  },
}

// ---- v-pdnd-drop directive (content zones only) ----------------------------

export const vPdndDrop = {
  mounted(el: HTMLElement, binding: { value: DropPayload }) {
    register(el, makeDropTarget(el, binding.value))
  },
  updated(el: HTMLElement, binding: { value: DropPayload }) {
    unregister(el)
    register(el, makeDropTarget(el, binding.value))
  },
  unmounted(el: HTMLElement) {
    unregister(el)
  },
}

// ---- v-pdnd-group-hdr directive (group header: reorder + edge) -------------

export const vPdndGroupHdr = {
  mounted(el: HTMLElement, binding: { value: DropPayload }) {
    register(el, makeGroupHeader(el, binding.value))
  },
  updated(el: HTMLElement, binding: { value: DropPayload }) {
    unregister(el)
    register(el, makeGroupHeader(el, binding.value))
  },
  unmounted(el: HTMLElement) {
    unregister(el)
  },
}

// ---- v-pdnd-live-row directive (Live pane unified row) ----------------------

export type LiveRowBinding = { drag: DragPayload; dropKey: string; isGroup: boolean }

export const vPdndLiveRow = {
  mounted(el: HTMLElement, binding: { value: LiveRowBinding }) {
    const { drag, dropKey, isGroup } = binding.value
    el.setAttribute('data-drag-key', dropKey)
    register(el, makeLiveRow(el, drag, dropKey, isGroup))
  },
  updated(el: HTMLElement, binding: { value: LiveRowBinding }) {
    const { drag, dropKey, isGroup } = binding.value
    el.setAttribute('data-drag-key', dropKey)
    unregister(el)
    register(el, makeLiveRow(el, drag, dropKey, isGroup))
  },
  unmounted(el: HTMLElement) {
    unregister(el)
  },
}

// ---- useDndMonitor composable -----------------------------------------------

export type MonitorDropEvent = {
  source: DragPayload
  target: DropPayload
  dropElement: HTMLElement
  inputY: number
  // set when target is a group-header and source is an item (not a group)
  closestEdge: Edge | null
  // for live-row targets: the resolved zone ('top' | 'bottom' | 'into'), computed in monitor before DOM is cleared
  liveZone: 'top' | 'bottom' | 'into' | null
}

export type MonitorDragEvent = {
  source: DragPayload
  dropElement: HTMLElement | null
  edge: Edge | null
  isOver: boolean
}

export function useDndMonitor(
  onDrop: (evt: MonitorDropEvent) => void,
  onDragUpdate?: (evt: MonitorDragEvent) => void,
) {
  const cleanup = monitorForElements({
    onDrag({ source, location }) {
      if (!onDragUpdate) return
      const targets = location.current.dropTargets
      if (targets.length === 0) {
        onDragUpdate({ source: source.data as DragPayload, dropElement: null, edge: null, isOver: false })
        return
      }
      const target = targets[0]
      const src = source.data as DragPayload
      const isGroupDrag = src.type === 'archive-group' || src.type === 'live-group' || src.type === 'shelf-group'
      const edge = !isGroupDrag ? extractClosestEdge(target.data) : null
      onDragUpdate({
        source: src,
        dropElement: target.element as HTMLElement,
        edge,
        isOver: !!(target.element as HTMLElement).dataset.dropOver,
      })
    },
    onDrop({ source, location }) {
      const targets = location.current.dropTargets
      if (targets.length === 0) return
      const target = targets[0]
      const src = source.data as DragPayload
      const isGroupDrag = src.type === 'archive-group' || src.type === 'live-group' || src.type === 'shelf-group'
      const edge = !isGroupDrag ? extractClosestEdge(target.data) : null
      const tgt = target.data as DropPayload
      const el = target.element as HTMLElement
      let liveZone: 'top' | 'bottom' | 'into' | null = null
      if (tgt.zone === 'live-row') {
        const isTargetGroup = (tgt as { isGroup: boolean }).isGroup
        const inputY = location.current.input.clientY
        if (isTargetGroup) {
          // Both tab-on-group and group-on-group: use 25/50/25 split for "into"
          liveZone = groupDropZone(el, inputY)
        } else {
          // tab-on-tab or group-on-tab: use closest edge
          const e = extractClosestEdge(target.data)
          liveZone = e === 'top' ? 'top' : 'bottom'
        }
      }
      onDrop({
        source: src,
        target: tgt,
        dropElement: el,
        inputY: location.current.input.clientY,
        closestEdge: edge,
        liveZone,
      })
    },
  })
  onUnmounted(cleanup)
  return cleanup
}
