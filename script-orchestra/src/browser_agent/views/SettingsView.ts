import { defineComponent, reactive, ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Plus, Delete, Refresh } from '@element-plus/icons-vue'
import { getSettings, updateSettings } from '../service/BrowserAgentService'
import type { BrowserAgentSettings, SiteRule } from '../service/Model'

const DEFAULTS: BrowserAgentSettings = {
  downloadDir: '',
  maxRetries: 3,
  pollIntervalSec: 60,
  siteRules: [],
  downloadSSMH: { sourceDomains: [], downloadDomains: [], downloadPath: '', linkLabel: '' },
  downloadJM: { sourceDomain: '', downloadPath: '' },
  tabArchive: {
    safeExcludeDomains: [],
    safeExcludeKeywords: [],
    embedModel: '',
    semanticTopK: 120,
    heatThresholds: { high: 4, medium: 2, low: 0.8 },
    healthCheckTimeoutSec: 4,
  },
}

export default defineComponent({
  name: 'BrowserAgentSettingsView',
  components: { ArrowLeft, Plus, Delete, Refresh },
  setup() {
    const router = useRouter()
    const state = reactive<BrowserAgentSettings>(JSON.parse(JSON.stringify(DEFAULTS)))
    const originalJson = ref(JSON.stringify(DEFAULTS))
    const loading = ref(false)
    const saving = ref(false)

    const isDirty = computed(() => JSON.stringify(state) !== originalJson.value)

    async function load() {
      loading.value = true
      try {
        const s = await getSettings()
        Object.assign(state, s)
        if (!state.downloadSSMH) {
          state.downloadSSMH = { sourceDomains: [], downloadDomains: [], downloadPath: '', linkLabel: '' }
        }
        if (!state.downloadJM) {
          state.downloadJM = { sourceDomain: '', downloadPath: '' }
        }
        if (!state.tabArchive) {
          state.tabArchive = {
            safeExcludeDomains: [],
            safeExcludeKeywords: [],
            embedModel: '',
            semanticTopK: 120,
            heatThresholds: { high: 4, medium: 2, low: 0.8 },
            healthCheckTimeoutSec: 4,
          }
        }
        if (!state.tabArchive.heatThresholds) {
          state.tabArchive.heatThresholds = { high: 4, medium: 2, low: 0.8 }
        }
        if (typeof state.tabArchive.embedModel !== 'string') {
          state.tabArchive.embedModel = ''
        }
        if (!Number.isFinite(state.tabArchive.semanticTopK)) {
          state.tabArchive.semanticTopK = 120
        }
        originalJson.value = JSON.stringify(state)
      } catch (e: any) {
        ElMessage.error(e.message || 'Failed to load settings')
      } finally {
        loading.value = false
      }
    }

    async function save() {
      saving.value = true
      try {
        const updated = await updateSettings(state)
        Object.assign(state, updated)
        originalJson.value = JSON.stringify(state)
        ElMessage.success('Settings saved')
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.error || e.message || 'Failed to save')
      } finally {
        saving.value = false
      }
    }

    function addRule() {
      state.siteRules.push({
        coverDomains: [],
        overviewUriFormat: '',
        downloadUriFormat: '',
        downloadLinkRegex: '',
      } as SiteRule)
    }

    function removeRule(i: number) {
      state.siteRules.splice(i, 1)
    }

    // el-input works on a string; domains are stored as an array.
    function domainsText(rule: SiteRule): string {
      return rule.coverDomains.join(', ')
    }
    function setDomainsText(rule: SiteRule, text: string) {
      rule.coverDomains = text.split(',').map(s => s.trim()).filter(Boolean)
    }

    // downloadSSMH lists — one domain per line (more forgiving than commas
    // when host names get long).
    function ssmhSourcesText(): string {
      return (state.downloadSSMH?.sourceDomains || []).join('\n')
    }
    function setSsmhSourcesText(text: string) {
      if (!state.downloadSSMH) state.downloadSSMH = { sourceDomains: [], downloadDomains: [], downloadPath: '', linkLabel: '' }
      state.downloadSSMH.sourceDomains = text.split('\n').map(s => s.trim()).filter(Boolean)
    }
    function ssmhDownloadsText(): string {
      return (state.downloadSSMH?.downloadDomains || []).join('\n')
    }
    function setSsmhDownloadsText(text: string) {
      if (!state.downloadSSMH) state.downloadSSMH = { sourceDomains: [], downloadDomains: [], downloadPath: '', linkLabel: '' }
      state.downloadSSMH.downloadDomains = text.split('\n').map(s => s.trim()).filter(Boolean)
    }

    function archiveExcludeDomainsText(): string {
      return (state.tabArchive?.safeExcludeDomains || []).join('\n')
    }

    function setArchiveExcludeDomainsText(text: string) {
      if (!state.tabArchive) {
        state.tabArchive = {
          safeExcludeDomains: [],
          safeExcludeKeywords: [],
          embedModel: '',
          semanticTopK: 120,
          heatThresholds: { high: 4, medium: 2, low: 0.8 },
          healthCheckTimeoutSec: 4,
        }
      }
      state.tabArchive.safeExcludeDomains = text
        .split('\n')
        .map(s => s.trim().toLowerCase())
        .filter(Boolean)
    }

    function archiveExcludeKeywordsText(): string {
      return (state.tabArchive?.safeExcludeKeywords || []).join('\n')
    }

    function setArchiveExcludeKeywordsText(text: string) {
      if (!state.tabArchive) {
        state.tabArchive = {
          safeExcludeDomains: [],
          safeExcludeKeywords: [],
          embedModel: '',
          semanticTopK: 120,
          heatThresholds: { high: 4, medium: 2, low: 0.8 },
          healthCheckTimeoutSec: 4,
        }
      }
      state.tabArchive.safeExcludeKeywords = text
        .split('\n')
        .map(s => s.trim().toLowerCase())
        .filter(Boolean)
    }

    onMounted(load)

    return {
      state, loading, saving, isDirty,
      load, save, addRule, removeRule, domainsText, setDomainsText,
      ssmhSourcesText, setSsmhSourcesText,
      ssmhDownloadsText, setSsmhDownloadsText,
      archiveExcludeDomainsText, setArchiveExcludeDomainsText,
      archiveExcludeKeywordsText, setArchiveExcludeKeywordsText,
      Refresh,
      Plus,
      Delete,
      goBack: () => router.push('/browser-agent'),
    }
  },
})
