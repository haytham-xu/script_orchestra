import { defineComponent, ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getSettings,
  jmCheckAuth, jmScan, jmExecute, jmStatus, jmSubmitCaptcha,
  type DownloadJMConfig, type JMCandidate, type JMItem, type JMCaptchaPending,
} from '@/browser_agent/service/BrowserAgentService'

export default defineComponent({
  name: 'DownloadJMView',
  setup() {
    const router = useRouter()

    const cfg = ref<DownloadJMConfig | null>(null)
    const configReady = computed(() => {
      const c = cfg.value
      return !!(c && c.sourceDomain?.trim() && c.downloadPath.trim())
    })

    const authStatus = ref<string>('unknown')   // 'unknown' | 'ok' | 'needs_login' | 'error'
    const authMsg = ref<string>('')

    const candidates = ref<JMCandidate[]>([])
    const selectedUrls = ref<Set<string>>(new Set())
    const scanning = ref(false)
    const totalTabsScanned = ref(0)

    const jobRunning = ref(false)
    const jobItems = ref<JMItem[]>([])
    const jobDone = ref(0)
    const jobTotal = ref(0)
    const captchaPending = ref<JMCaptchaPending | null>(null)
    const captchaAnswer = ref('')
    const captchaSubmitting = ref(false)
    let pollTimer: number | null = null

    async function loadCfg() {
      try {
        const s = await getSettings()
        cfg.value = s.downloadJM || { sourceDomain: '', downloadPath: '' }
      } catch (e: any) {
        ElMessage.error(e?.message || 'Failed to load config')
      }
    }

    async function doCheckAuth() {
      authStatus.value = 'unknown'
      authMsg.value = 'checking…'
      try {
        const res = await jmCheckAuth()
        if (res.error) {
          authStatus.value = 'error'
          authMsg.value = res.error
          return
        }
        // Positive marker (logout link present) is the strongest "you're
        // logged in" signal. Fall back to the older heuristic only when the
        // marker is absent.
        if (res.has_logout_marker) {
          authStatus.value = 'ok'
          authMsg.value = `authenticated  (cookies: ${res.cookie_count}, status: ${res.status}, logout link detected)`
          return
        }
        if (res.still_looks_like_login) {
          authStatus.value = 'needs_login'
          authMsg.value = `${res.cookie_count} cookies received but the site still shows a login page — please log in in your browser.`
          return
        }
        // Ambiguous — cookies flowed, no explicit signal either way. Assume
        // OK but tell the user what we saw.
        authStatus.value = 'ok'
        authMsg.value = `cookies: ${res.cookie_count}, status: ${res.status} (no logout marker found — try a download to confirm)`
      } catch (e: any) {
        authStatus.value = 'error'
        authMsg.value = e?.response?.data?.error || e?.message || 'auth check failed'
      }
    }

    async function doScan() {
      if (!configReady.value) {
        ElMessage.warning('Configure source domain + download path in Settings first.')
        return
      }
      scanning.value = true
      try {
        const res = await jmScan()
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
          `Download ${urls.length} album(s) to ${cfg.value?.downloadPath}? ` +
          `You'll be asked to solve a captcha per download.`,
          'Confirm', {
            confirmButtonText: 'Start',
            cancelButtonText: 'Cancel',
            type: 'warning',
          })
      } catch { return }
      try {
        await jmExecute(urls)
        startPolling()
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.error || e?.message || 'Execute failed')
      }
    }

    function stopPolling() {
      if (pollTimer !== null) { clearInterval(pollTimer); pollTimer = null }
    }
    async function pollOnce() {
      try {
        const s = await jmStatus()
        jobRunning.value = s.running
        jobItems.value = s.items
        jobDone.value = s.done
        jobTotal.value = s.total
        captchaPending.value = s.captcha_pending
        if (s.captcha_pending && !captchaAnswer.value) {
          // Clear the answer input when a new captcha shows up.
        }
        if (!s.running) stopPolling()
      } catch { /* keep polling */ }
    }
    function startPolling() {
      stopPolling()
      pollOnce()
      pollTimer = window.setInterval(pollOnce, 500)
    }

    async function submitCaptcha() {
      const ans = captchaAnswer.value.trim()
      if (!ans) { ElMessage.info('Please enter your answer'); return }
      captchaSubmitting.value = true
      try {
        await jmSubmitCaptcha(ans)
        captchaAnswer.value = ''
        // Immediately poll to reflect state change.
        pollOnce()
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.error || e?.message || 'Submit failed')
      } finally {
        captchaSubmitting.value = false
      }
    }

    // Reset the answer input whenever a new captcha shows up.
    watch(() => captchaPending.value?.image_base64, () => {
      captchaAnswer.value = ''
    })

    function statusTagType(status: string): '' | 'success' | 'warning' | 'danger' | 'info' {
      if (status === 'done') return 'success'
      if (status === 'error') return 'danger'
      if (status === 'captcha_needed') return 'warning'
      if (status === 'downloading' || status.startsWith('fetching_') || status === 'submitting_captcha') return 'info'
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
      await loadCfg()
      if (configReady.value) doCheckAuth()
      const s = await jmStatus()
      if (s.running || s.items.length) {
        jobRunning.value = s.running
        jobItems.value = s.items
        jobDone.value = s.done
        jobTotal.value = s.total
        captchaPending.value = s.captcha_pending
        if (s.running) startPolling()
      }
    })
    onBeforeUnmount(() => stopPolling())

    return {
      cfg, configReady,
      authStatus, authMsg, doCheckAuth,
      candidates, selectedUrls, scanning, totalTabsScanned,
      allSelected, toggleSelected, toggleSelectAll,
      jobRunning, jobItems, jobDone, jobTotal,
      captchaPending, captchaAnswer, captchaSubmitting, submitCaptcha,
      doScan, execute, statusTagType, fmtBytes, fmtSpeed,
      goBack: () => router.push('/browser-agent'),
    }
  }
})
