import { defineComponent, ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { marked } from 'marked'
import * as api from '../service/TranslatorService'
import { getTranslatorWebSocketService, type TranslatorProgress } from '../service/websocket'
import type {
  TranslationHistory, TranslatorSettings, ModelInfo, LearningPoint, Usage, UsageSummary,
} from '../service/Model'

// GitHub-flavored markdown, soft line breaks (matches assistant/roadmap usage).
marked.setOptions({ gfm: true, breaks: true })
function renderMarkdown(text?: string): string {
  if (!text) return ''
  try { return marked.parse(text) as string } catch { return text || '' }
}

export default defineComponent({
  name: 'TranslatorView',
  setup() {
    const router = useRouter()
    function goBack() { router.push('/') }

    const activeTab = ref<'zh2en' | 'en2zh' | 'settings'>('zh2en')

    // ---- streaming (Socket.IO) ----
    const ws = getTranslatorWebSocketService()
    let currentJobId = ''                 // the in-flight translation's job id
    const zhStreaming = ref('')           // live-accumulated main translation text
    const zhPhase = ref('')               // phase hint: 'Back-translating…' / 'Analyzing learning points…'
    const enStreaming = ref('')
    const PHASE_TEXT: Record<string, string> = {
      back_translating: 'Back-translating…',
      learning_points: 'Analyzing learning points…',
    }
    function newJobId(): string {
      // no crypto needed; uniqueness within a session is enough to correlate
      return `${activeTab.value}-${performance.now()}-${Math.floor(Math.random() * 1e6)}`
    }
    function handleProgress(p: TranslatorProgress) {
      if (p.job_id !== currentJobId) return   // ignore stale / other jobs
      if (p.phase === 'translating' && p.delta) {
        if (p.scene === 'zh2en') zhStreaming.value += p.delta
        else enStreaming.value += p.delta
      } else if (p.phase === 'back_translating' || p.phase === 'learning_points') {
        if (p.scene === 'zh2en') zhPhase.value = PHASE_TEXT[p.phase] || ''
      }
    }

    // ---- shared: settings + models ----
    const settings = ref<TranslatorSettings>({
      zh2en: { system_prompt: '', model: 'auto', learning_prompt: '' },
      en2zh: { system_prompt: '', model: 'auto' },
      cleanup_days: 30,
    })
    const models = ref<ModelInfo[]>([])
    // model dropdown always offers "auto" plus whatever the runtime lists.
    const modelOptions = computed<ModelInfo[]>(() => {
      const base: ModelInfo[] = [{ id: 'auto', name: 'auto' }]
      const extra = models.value.filter((m) => m.id !== 'auto')
      return [...base, ...extra]
    })

    async function loadSettings() {
      try { settings.value = await api.getSettings() } catch { /* toast handled upstream */ }
    }
    async function loadModels() {
      try { models.value = await api.getModels() } catch { models.value = [] }
    }

    // ---- cumulative usage summary (Settings tab) ----
    const usageSummary = ref<UsageSummary | null>(null)
    async function loadUsageSummary() {
      try { usageSummary.value = await api.getUsageSummary() } catch { /* toast upstream */ }
    }

    // Format a usage dict as a compact one-liner for the result/history rows.
    function fmtUsage(u?: Usage | Record<string, never>): string {
      if (!u || !(u as Usage).model) return ''
      const usage = u as Usage
      const parts = [usage.model, `${usage.credits} credits`]
      if (usage.input_tokens || usage.output_tokens) {
        parts.push(`↑${usage.input_tokens} ↓${usage.output_tokens} tokens`)
      }
      return parts.join(' · ')
    }
    const savingSettings = ref(false)
    async function saveSettings() {
      savingSettings.value = true
      try {
        settings.value = await api.updateSettings(settings.value)
        ElMessage.success('Settings saved')
      } finally { savingSettings.value = false }
    }

    // ---- cleanup ----
    const cleanupDays = ref<number>(30)
    const cleaning = ref(false)
    async function runCleanup() {
      try {
        await ElMessageBox.confirm(
          `Delete ALL translation history older than ${cleanupDays.value} days (both scenes)? This cannot be undone.`,
          'Confirm cleanup', { type: 'warning', confirmButtonText: 'Delete', cancelButtonText: 'Cancel' },
        )
      } catch { return }
      cleaning.value = true
      try {
        const res = await api.cleanup(cleanupDays.value)
        ElMessage.success(`Deleted ${res.deleted} record(s) older than ${res.days} days`)
        await Promise.all([loadZhHistory(), loadEnHistory()])
      } finally { cleaning.value = false }
    }

    // ---- scene 1: zh → en ----
    const zhInput = ref('')
    const zhExtra = ref('')           // one-off extra prompt for this translation
    const zhModel = ref('auto')       // per-request model override (defaults to scene default)
    const zhLoading = ref(false)
    const zhEnglish = ref('')
    const zhBack = ref('')
    const zhPoints = ref<LearningPoint[]>([])
    const zhUsage = ref<Usage | null>(null)
    const zhHistory = ref<TranslationHistory[]>([])

    async function loadZhHistory() {
      try { zhHistory.value = await api.getHistory('zh2en') } catch { /* toast upstream */ }
    }
    async function runZh2En() {
      const text = zhInput.value.trim()
      if (!text) { ElMessage.warning('Please enter some text'); return }
      zhLoading.value = true
      currentJobId = newJobId()
      zhStreaming.value = ''
      zhPhase.value = ''
      try {
        const res = await api.zh2en(text, zhModel.value, currentJobId, zhExtra.value.trim() || undefined)
        zhEnglish.value = res.english
        zhBack.value = res.back_translation
        zhPoints.value = res.learning_points
        zhUsage.value = res.usage
        await Promise.all([loadZhHistory(), loadUsageSummary()])
      } finally {
        zhLoading.value = false
        zhStreaming.value = ''
        zhPhase.value = ''
        currentJobId = ''
      }
    }

    // ---- scene 2: en → zh ----
    const enInput = ref('')
    const enExtra = ref('')           // one-off extra prompt for this translation
    const enModel = ref('auto')
    const enLoading = ref(false)
    const enChinese = ref('')
    const enUsage = ref<Usage | null>(null)
    const enHistory = ref<TranslationHistory[]>([])

    async function loadEnHistory() {
      try { enHistory.value = await api.getHistory('en2zh') } catch { /* toast upstream */ }
    }
    async function runEn2Zh() {
      const text = enInput.value.trim()
      if (!text) { ElMessage.warning('Please enter some text'); return }
      enLoading.value = true
      currentJobId = newJobId()
      enStreaming.value = ''
      try {
        const res = await api.en2zh(text, enModel.value, currentJobId, enExtra.value.trim() || undefined)
        enChinese.value = res.chinese
        enUsage.value = res.usage
        await Promise.all([loadEnHistory(), loadUsageSummary()])
      } finally {
        enLoading.value = false
        enStreaming.value = ''
        currentJobId = ''
      }
    }

    // ---- copy helpers ----
    async function copyText(text: string) {
      if (!text) return
      try {
        await navigator.clipboard.writeText(text)
        ElMessage.success('Copied')
      } catch {
        ElMessage.error('Copy failed')
      }
    }
    // one learning point as a compact card-friendly line
    function pointToText(p: LearningPoint): string {
      const parts = [p.original]
      if (p.suggestion) parts.push(`→ ${p.suggestion}`)
      if (p.explanation) parts.push(`(${p.explanation})`)
      return parts.join(' ')
    }
    function copyPoint(p: LearningPoint) { copyText(pointToText(p)) }
    function copyAllPoints() {
      if (!zhPoints.value.length) return
      const all = zhPoints.value.map((p, i) => `${i + 1}. ${pointToText(p)}`).join('\n')
      copyText(all)
    }

    function fmtDate(iso?: string): string {
      if (!iso) return ''
      try { return new Date(iso).toLocaleString() } catch { return iso }
    }

    onMounted(async () => {
      // Connect the streaming socket; failure is non-fatal (HTTP result still works).
      try {
        ws.connect()
        ws.onProgress(handleProgress)
      } catch { /* streaming unavailable — degrade to plain HTTP */ }
      await Promise.all([loadSettings(), loadZhHistory(), loadEnHistory(), loadUsageSummary()])
      cleanupDays.value = settings.value.cleanup_days
      // seed per-scene model pickers from the saved scene defaults
      zhModel.value = settings.value.zh2en.model || 'auto'
      enModel.value = settings.value.en2zh.model || 'auto'
      // models come from the Copilot runtime; load lazily, don't block the view.
      loadModels()
    })

    onBeforeUnmount(() => {
      ws.offProgress()
      ws.disconnect()
    })

    return {
      goBack,
      activeTab, settings, modelOptions, savingSettings, saveSettings,
      cleanupDays, cleaning, runCleanup,
      usageSummary, fmtUsage, renderMarkdown,
      zhStreaming, zhPhase, enStreaming,
      zhInput, zhExtra, zhModel, zhLoading, zhEnglish, zhBack, zhPoints, zhUsage, zhHistory, runZh2En,
      enInput, enExtra, enModel, enLoading, enChinese, enUsage, enHistory, runEn2Zh,
      copyText, copyPoint, copyAllPoints, fmtDate,
    }
  },
})
