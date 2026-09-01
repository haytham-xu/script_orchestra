import { defineComponent, ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listTabs, closeTabs, type TabInfo } from '@/browser_agent/service/BrowserAgentService'

// Two tabs "duplicate" iff their URLs match after we strip #fragment and any
// utm_/gclid tracking params — same-content URLs that only differ by tracking
// noise still count as dupes to the user.
function normalizeUrl(u: string): string {
  try {
    const url = new URL(u)
    url.hash = ''
    const drop: string[] = []
    url.searchParams.forEach((_, k) => {
      if (k.startsWith('utm_') || k === 'gclid' || k === 'fbclid' || k === 'yclid') drop.push(k)
    })
    drop.forEach(k => url.searchParams.delete(k))
    return url.toString()
  } catch {
    return u
  }
}

interface DupeGroup {
  normalizedUrl: string
  tabs: TabInfo[]     // all tabs sharing this URL (>= 2)
}

export default defineComponent({
  name: 'TabDedupView',
  setup() {
    const router = useRouter()
    const tabs = ref<TabInfo[]>([])
    const loading = ref(false)
    const busy = ref(false)
    const selectedTabIds = ref<Set<number>>(new Set())

    async function loadTabs() {
      loading.value = true
      try {
        const list = await listTabs()
        tabs.value = list
        preselectDupes()
      } catch (e: any) {
        const msg = e?.response?.data?.error || e.message || 'Failed to list tabs'
        ElMessage.error(msg)
      } finally {
        loading.value = false
      }
    }

    const dupeGroups = computed<DupeGroup[]>(() => {
      const byUrl = new Map<string, TabInfo[]>()
      for (const t of tabs.value) {
        const key = normalizeUrl(t.url)
        const arr = byUrl.get(key)
        if (arr) arr.push(t)
        else byUrl.set(key, [t])
      }
      const out: DupeGroup[] = []
      for (const [normalizedUrl, group] of byUrl) {
        if (group.length >= 2) out.push({ normalizedUrl, tabs: group })
      }
      // Larger groups first so the user tackles the worst dupes.
      out.sort((a, b) => b.tabs.length - a.tabs.length)
      return out
    })

    const totalDupeTabs = computed(() =>
      dupeGroups.value.reduce((sum, g) => sum + g.tabs.length, 0))
    const closableCount = computed(() =>
      dupeGroups.value.reduce((sum, g) => sum + Math.max(0, g.tabs.length - 1), 0))

    // Default selection: within each group, keep the FIRST tab, mark the rest
    // for closing. Users can uncheck individually.
    function preselectDupes() {
      const s = new Set<number>()
      for (const g of dupeGroups.value) {
        for (let i = 1; i < g.tabs.length; i++) s.add(g.tabs[i].id)
      }
      selectedTabIds.value = s
    }

    function toggleTab(id: number) {
      const s = new Set(selectedTabIds.value)
      if (s.has(id)) s.delete(id); else s.add(id)
      selectedTabIds.value = s
    }

    function selectAllInGroup(g: DupeGroup, keepFirst = true) {
      const s = new Set(selectedTabIds.value)
      g.tabs.forEach((t, i) => {
        if (keepFirst && i === 0) s.delete(t.id)
        else s.add(t.id)
      })
      selectedTabIds.value = s
    }

    function clearGroupSelection(g: DupeGroup) {
      const s = new Set(selectedTabIds.value)
      g.tabs.forEach(t => s.delete(t.id))
      selectedTabIds.value = s
    }

    async function closeSelected() {
      const ids = Array.from(selectedTabIds.value)
      if (!ids.length) {
        ElMessage.info('No tabs selected')
        return
      }
      try {
        await ElMessageBox.confirm(
          `Close ${ids.length} tab(s)?`, 'Confirm', {
            confirmButtonText: 'Close them',
            cancelButtonText: 'Cancel',
            type: 'warning',
          })
      } catch { return }
      busy.value = true
      try {
        const res = await closeTabs(ids)
        ElMessage.success(`Closed ${res.closed} tab(s)`)
        selectedTabIds.value = new Set()
        await loadTabs()
      } catch (e: any) {
        const msg = e?.response?.data?.error || e.message || 'Failed to close tabs'
        ElMessage.error(msg)
      } finally {
        busy.value = false
      }
    }

    onMounted(() => { loadTabs() })

    function hideFavicon(e: Event) {
      const img = e.target as HTMLImageElement | null
      if (img) img.style.display = 'none'
    }

    return {
      tabs, loading, busy,
      dupeGroups, totalDupeTabs, closableCount,
      selectedTabIds, toggleTab,
      selectAllInGroup, clearGroupSelection,
      loadTabs, closeSelected,
      hideFavicon,
      goBack: () => router.push('/browser-agent'),
    }
  }
})
