import { defineComponent, ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Setting } from '@element-plus/icons-vue'
import {
  getSettings, updateSettings,
  ssmhScan, ssmhScanStatus, ssmhExecute, ssmhStatus,
  type SSMHCandidate, type SSMHItem, type SSMHSubItem,
} from '@/browser_agent/service/BrowserAgentService'
import type { DownloadSSMHConfig } from '@/browser_agent/service/Model'

export default defineComponent({
  name: 'DownloadSSMHView',
  components: { Setting },
  setup() {
    const router = useRouter()

    // Live config read from settings.
    const cfg = ref<DownloadSSMHConfig | null>(null)
    const configReady = computed(() => {
      const c = cfg.value
      return !!(c && c.sourceDomains?.length && c.downloadPath.trim())
    })

    // Settings drawer
    const settingsOpen = ref(false)
    const settingsCfg = reactive<DownloadSSMHConfig>({ sourceDomains: [], downloadDomains: [], downloadPath: '', linkLabel: '', downloadParts: 1 })
    const settingsSaving = ref(false)

    function ssmhSourcesText() { return settingsCfg.sourceDomains.join('\n') }
    function setSsmhSourcesText(text: string) {
      settingsCfg.sourceDomains = text.split('\n').map(s => s.trim()).filter(Boolean)
    }
    function ssmhDownloadsText() { return settingsCfg.downloadDomains.join('\n') }
    function setSsmhDownloadsText(text: string) {
      settingsCfg.downloadDomains = text.split('\n').map(s => s.trim()).filter(Boolean)
    }

    async function openSettings() {
      const s = await getSettings()
      const c = s.downloadSSMH || { sourceDomains: [], downloadDomains: [], downloadPath: '', linkLabel: '', downloadParts: 1 }
      Object.assign(settingsCfg, c)
      settingsOpen.value = true
    }
    async function saveSettings() {
      settingsSaving.value = true
      try {
        await updateSettings({ downloadSSMH: { ...settingsCfg } })
        cfg.value = { ...settingsCfg }
        settingsOpen.value = false
        ElMessage.success('Settings saved')
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.error || e?.message || 'Failed to save')
      } finally {
        settingsSaving.value = false
      }
    }

    const candidates = ref<SSMHCandidate[]>([])
    const selectedUrls = ref<Set<string>>(new Set())
    const scanning = ref(false)
    const scanDone = ref(0)
    const scanTotal = ref(0)
    const totalTabsScanned = ref(0)
    let scanPollTimer: number | null = null

    const type1Count = computed(() => candidates.value.filter(c => c.dl_type === 'type1').length)
    const type2Count = computed(() => candidates.value.filter(c => c.dl_type === 'type2').length)

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
      scanDone.value = 0
      scanTotal.value = 0
      candidates.value = []
      selectedUrls.value = new Set()
      try {
        const res = await ssmhScan()
        totalTabsScanned.value = res.total_tabs
        // Start polling scan status for progress.
        if (scanPollTimer !== null) clearInterval(scanPollTimer)
        scanPollTimer = window.setInterval(async () => {
          try {
            const s = await ssmhScanStatus()
            scanDone.value = s.done
            scanTotal.value = s.total
            candidates.value = s.candidates
            selectedUrls.value = new Set(s.candidates.map(c => c.url))
            if (!s.running) {
              clearInterval(scanPollTimer!)
              scanPollTimer = null
              scanning.value = false
              if (s.candidates.length === 0) {
                ElMessage.info(`Scanned ${s.total_tabs} tabs — no source-domain match`)
              }
            }
          } catch { /* keep polling */ }
        }, 400)
      } catch (e: any) {
        scanning.value = false
        ElMessage.error(e?.response?.data?.error || e?.message || 'Scan failed')
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
    function selectByType(t: string) {
      selectedUrls.value = new Set(candidates.value.filter(c => c.dl_type === t).map(c => c.url))
    }

    async function execute() {
      const items = candidates.value
        .filter(c => selectedUrls.value.has(c.url))
        .map(c => ({ url: c.url, dl_type: c.dl_type }))
      if (!items.length) { ElMessage.info('No tabs selected'); return }
      try {
        await ElMessageBox.confirm(
          `Download ${items.length} tab(s) to ${cfg.value?.downloadPath}?`, 'Confirm', {
            confirmButtonText: 'Start',
            cancelButtonText: 'Cancel',
            type: 'warning',
          })
      } catch { return }
      try {
        await ssmhExecute(items)
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
      if (status === 'done' || status === 'skipped') return 'success'
      if (status === 'error' || status === 'quota_exceeded') return 'danger'
      if (status === 'manual_required' || status === 'unmatched_download_domain') return 'warning'
      if (['downloading', 'fetching_source', 'fetching_download_page',
           'calling_worker_api', 'fetching_chapters',
           'fetching_slide', 'downloading_images'].includes(status)) return 'info'
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
    onBeforeUnmount(() => {
      stopPolling()
      if (scanPollTimer !== null) { clearInterval(scanPollTimer); scanPollTimer = null }
    })

    return {
      cfg, configReady,
      candidates, selectedUrls, scanning, scanDone, scanTotal, totalTabsScanned,
      type1Count, type2Count,
      allSelected, toggleSelected, toggleSelectAll, selectByType,
      jobRunning, jobItems, jobDone, jobTotal,
      doScan, execute, statusTagType,
      fmtBytes, fmtSpeed,
      settingsOpen, settingsCfg, settingsSaving,
      openSettings, saveSettings,
      ssmhSourcesText, setSsmhSourcesText, ssmhDownloadsText, setSsmhDownloadsText,
      Setting,
      goBack: () => router.push('/browser-agent'),
    }
  }
})
