import { defineComponent, ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listTabs, closeTabs, type TabInfo } from '@/browser_agent/service/BrowserAgentService'

type SortKey = 'window' | 'title' | 'url'

export default defineComponent({
  name: 'TabsView',
  setup() {
    const router = useRouter()
    const tabs = ref<TabInfo[]>([])
    const loading = ref(false)
    const busy = ref(false)
    const search = ref('')
    const sortKey = ref<SortKey>('window')
    const selectedTabIds = ref<Set<number>>(new Set())

    async function loadTabs() {
      loading.value = true
      try {
        const list = await listTabs()
        tabs.value = list
        // Drop selections that no longer exist (closed elsewhere).
        const live = new Set(list.map(t => t.id))
        const kept = new Set<number>()
        selectedTabIds.value.forEach(id => { if (live.has(id)) kept.add(id) })
        selectedTabIds.value = kept
      } catch (e: any) {
        const msg = e?.response?.data?.error || e.message || 'Failed to list tabs'
        ElMessage.error(msg)
      } finally {
        loading.value = false
      }
    }

    // Filtered + sorted view over the raw tab list.
    const visibleTabs = computed<TabInfo[]>(() => {
      const q = search.value.trim().toLowerCase()
      let out = tabs.value
      if (q) {
        out = out.filter(t =>
          (t.title || '').toLowerCase().includes(q) ||
          (t.url || '').toLowerCase().includes(q))
      }
      const sorted = [...out]
      if (sortKey.value === 'title') {
        sorted.sort((a, b) => (a.title || '').localeCompare(b.title || ''))
      } else if (sortKey.value === 'url') {
        sorted.sort((a, b) => (a.url || '').localeCompare(b.url || ''))
      } else {
        // window: group by windowId, then by original array order
        sorted.sort((a, b) => a.windowId - b.windowId)
      }
      return sorted
    })

    const allVisibleSelected = computed(() => {
      const vis = visibleTabs.value
      if (vis.length === 0) return false
      return vis.every(t => selectedTabIds.value.has(t.id))
    })
    const someVisibleSelected = computed(() =>
      visibleTabs.value.some(t => selectedTabIds.value.has(t.id)) && !allVisibleSelected.value)

    function toggleTab(id: number) {
      const s = new Set(selectedTabIds.value)
      if (s.has(id)) s.delete(id); else s.add(id)
      selectedTabIds.value = s
    }
    function toggleAllVisible() {
      const s = new Set(selectedTabIds.value)
      if (allVisibleSelected.value) {
        visibleTabs.value.forEach(t => s.delete(t.id))
      } else {
        visibleTabs.value.forEach(t => s.add(t.id))
      }
      selectedTabIds.value = s
    }
    function clearSelection() {
      selectedTabIds.value = new Set()
    }

    async function closeSelected() {
      const ids = Array.from(selectedTabIds.value)
      if (!ids.length) { ElMessage.info('No tabs selected'); return }
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
        await loadTabs()
      } catch (e: any) {
        const msg = e?.response?.data?.error || e.message || 'Failed to close tabs'
        ElMessage.error(msg)
      } finally {
        busy.value = false
      }
    }

    async function closeSingle(id: number) {
      busy.value = true
      try {
        await closeTabs([id])
        await loadTabs()
      } catch (e: any) {
        const msg = e?.response?.data?.error || e.message || 'Failed to close tab'
        ElMessage.error(msg)
      } finally {
        busy.value = false
      }
    }

    function hideFavicon(e: Event) {
      const img = e.target as HTMLImageElement | null
      if (img) img.style.display = 'none'
    }

    onMounted(() => { loadTabs() })

    return {
      tabs, loading, busy,
      search, sortKey,
      visibleTabs, selectedTabIds,
      allVisibleSelected, someVisibleSelected,
      toggleTab, toggleAllVisible, clearSelection,
      loadTabs, closeSelected, closeSingle, hideFavicon,
      goBack: () => router.push('/browser-agent'),
    }
  }
})
