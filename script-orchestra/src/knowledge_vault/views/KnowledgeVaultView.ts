import { defineComponent, ref } from 'vue'
import { useRouter } from 'vue-router'
import { marked } from 'marked'
import * as api from '../service/KnowledgeVaultService'
import type { RawFragment, Label } from '../service/Model'
import { fragmentSummary } from '../service/Model'

export default defineComponent({
  name: 'KnowledgeVaultView',
  setup() {
    const router = useRouter()
    function goBack() { router.push('/') }
    function goCapture() { router.push({ name: 'knowledge-vault-capture' }) }

    const labels = ref<Label[]>([])
    const labelMap = ref<Record<number, Label>>({})

    async function loadLabels() {
      labels.value = await api.getLabels()
      labelMap.value = Object.fromEntries(labels.value.map(l => [l.id, l]))
    }

    // ---- search state ----
    const queryText = ref('')
    const results = ref<RawFragment[]>([])
    const searched = ref(false)
    const searching = ref(false)
    const searchDetail = ref<RawFragment | null>(null)

    async function runSearch() {
      if (!queryText.value.trim()) return
      searching.value = true
      try {
        results.value = await api.search(queryText.value, 10)
        searched.value = true
        searchDetail.value = null
      } catch (e: any) {
        // ElMessage not imported here — errors are silent on search page
      } finally {
        searching.value = false
      }
    }

    function fmtDate(iso: string): string {
      if (!iso) return '—'
      const d = new Date(iso)
      return isNaN(d.getTime()) ? '—' : d.toLocaleDateString()
    }

    function renderMd(text: string): string {
      return marked.parse(text || '', { async: false }) as string
    }

    // Load labels for tag display in results
    loadLabels()

    return {
      goBack, goCapture,
      labelMap, labels,
      queryText, results, searched, searching, searchDetail,
      runSearch, fmtDate, fragmentSummary, renderMd,
    }
  },
})
