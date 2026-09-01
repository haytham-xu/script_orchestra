import { defineComponent, ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getSettings,
  ssmhScan, ssmhExecute, ssmhStatus,
  type SSMHCandidate, type SSMHItem, type DownloadSSMHConfig,
} from '@/browser_agent/service/BrowserAgentService'

export default defineComponent({
  name: 'DownloadSSMHView',
  setup() {
    const router = useRouter()

    // Live config read from settings. `null` while loading; a non-null but
    // partially-empty object means the user hasn't finished configuring yet.
    const cfg = ref<DownloadSSMHConfig | null>(null)
    const configReady = computed(() => {
      const c = cfg.value
      return !!(c && c.sourceDomains?.length && c.downloadDomains?.length && c.downloadPath.trim())
    })

    const candidates = ref<SSMHCandidate[]>([])
    const selectedUrls = ref<Set<string>>(new Set())
    const scanning = ref(false)
    const totalTabsScanned = ref(0)

    const jobRunning = ref(false)
    const jobItems = ref<SSMHItem[]>([])
    const jobDone = ref(0)
    const jobTotal = ref(0)
    let pollTimer: number | null = null

    async function loadConfig() {
      try {
        const s = await getSettings()
        cfg.value = s.downloadSSMH || { sourceDomains: [], downloadDomains: [], downloadPath: '' }
      } catch (e: any) {
        ElMessage.error(e?.message || 'Failed to load config')
      }
    }

    async function doScan() {
      if (!configReady.value) {
        ElMessage.warning('Please finish configuring Download SSMH in Settings first.')
        return
      }
      scanning.value = true
      try {
        const res = await ssmhScan()
        candidates.value = res.candidates
        totalTabsScanned.value = res.total_tabs
        selectedUrls.value = new Set(res.candidates.map(c => c.url))
        if (res.candidates.length === 0) {
          ElMessage.info(`Scanned ${res.total_tabs} tabs — no source-domain match`)
        }
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.error || e?.message || 'Scan failed')
      } finally {
        scanning.value = false
      }
    }

    function toggleSelected(url: string) {
      const s = new Set(selectedUrls.value)
      if (s.has(url)) s.delete(url); else s.add(url)
      selectedUrls.value = s
    }
    const allSelected = computed(() =>
      candidates.value.length > 0 && candidates.value.every(c => selectedUrls.value.has(c.url)))
    function toggleSelectAll() {
      if (allSelected.value) selectedUrls.value = new Set()
      else selectedUrls.value = new Set(candidates.value.map(c => c.url))
    }

    async function execute() {
      const urls = Array.from(selectedUrls.value)
      if (!urls.length) { ElMessage.info('No tabs selected'); return }
      try {
        await ElMessageBox.confirm(
          `Download ${urls.length} tab(s) to ${cfg.value?.downloadPath}?`, 'Confirm', {
            confirmButtonText: 'Start',
            cancelButtonText: 'Cancel',
            type: 'warning',
          })
      } catch { return }
      try {
        await ssmhExecute(urls)
        startPolling()
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.error || e?.message || 'Execute failed')
      }
    }

    function stopPolling() {
      if (pollTimer !== null) { clearInterval(pollTimer); pollTimer = null }
    }
    const unmatchedShown = ref(false)
    async function pollOnce() {
      try {
        const s = await ssmhStatus()
        jobRunning.value = s.running
        jobItems.value = s.items
        jobDone.value = s.done
        jobTotal.value = s.total
        const unmatched = s.items.find(i => i.status === 'unmatched_download_domain')
        if (unmatched && !unmatchedShown.value) {
          unmatchedShown.value = true
          ElMessage.warning(
            `Download host not in allowlist: ${unmatched.download_url}. Update Download Domains in Settings, then rerun those items.`,
            { duration: 6000 } as any,
          )
        }
        if (!s.running) stopPolling()
      } catch { /* keep polling */ }
    }
    function startPolling() {
      unmatchedShown.value = false
      stopPolling()
      pollOnce()
      pollTimer = window.setInterval(pollOnce, 500)
    }

    function statusTagType(status: string): '' | 'success' | 'warning' | 'danger' | 'info' {
      if (status === 'done') return 'success'
      if (status === 'error') return 'danger'
      if (status === 'unmatched_download_domain') return 'warning'
      if (status === 'downloading' || status === 'fetching_source' || status === 'fetching_download_page') return 'info'
      return ''
    }

    function fmtBytes(n: number): string {
      if (!n || n < 0) return '0 B'
      const u = ['B', 'KB', 'MB', 'GB', 'TB']
      let v = n, i = 0
      while (v >= 1024 && i < u.length - 1) { v /= 1024; i++ }
      return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${u[i]}`
    }
    function fmtSpeed(bps: number): string {
      return `${fmtBytes(bps)}/s`
    }

    onMounted(async () => {
      await loadConfig()
      // Resume progress polling if a job is still running from a prior nav.
      const s = await ssmhStatus()
      if (s.running || s.items.length) {
        jobRunning.value = s.running
        jobItems.value = s.items
        jobDone.value = s.done
        jobTotal.value = s.total
        if (s.running) startPolling()
      }
    })
    onBeforeUnmount(() => stopPolling())

    return {
      cfg, configReady,
      candidates, selectedUrls, scanning, totalTabsScanned,
      allSelected, toggleSelected, toggleSelectAll,
      jobRunning, jobItems, jobDone, jobTotal,
      doScan, execute, statusTagType,
      fmtBytes, fmtSpeed,
      goBack: () => router.push('/browser-agent'),
    }
  }
})
