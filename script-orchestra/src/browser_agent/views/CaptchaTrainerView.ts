import { defineComponent, ref, computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  fetchTrainingList, saveTrainingLabel, deleteTrainingSample,
  type TrainingSample,
} from '@/browser_agent/service/BrowserAgentService'

export default defineComponent({
  name: 'CaptchaTrainerView',
  setup() {
    const router = useRouter()
    const samples = ref<TrainingSample[]>([])
    const templates = ref<Record<string, number>>({})
    const loading = ref(false)
    const busyByFile = reactive<Record<string, boolean>>({})
    const inputByFile = reactive<Record<string, string>>({})

    async function loadList() {
      loading.value = true
      try {
        const res = await fetchTrainingList()
        samples.value = res.samples
        templates.value = res.template_counts
        for (const s of res.samples) {
          if (!(s.filename in inputByFile)) {
            // Prefill with the answer hint stored in filename — the user
            // typed the RESULT (e.g. "21"), which is not the expression, but
            // seeing it helps them remember.
            inputByFile[s.filename] = ''
          }
        }
      } catch (e: any) {
        ElMessage.error(e?.message || 'Failed to load training samples')
      } finally {
        loading.value = false
      }
    }

    async function saveLabel(s: TrainingSample) {
      const expr = (inputByFile[s.filename] || '').trim()
      if (!expr) { ElMessage.info('Enter the expression, e.g. 16+5='); return }
      busyByFile[s.filename] = true
      try {
        const res = await saveTrainingLabel(s.filename, expr)
        if (res.error) {
          ElMessage.error(res.error)
          return
        }
        ElMessage.success(`Saved ${res.saved} template(s)`)
        await loadList()
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.error || e?.message || 'Save failed')
      } finally {
        busyByFile[s.filename] = false
      }
    }

    async function skipSample(s: TrainingSample) {
      busyByFile[s.filename] = true
      try {
        await deleteTrainingSample(s.filename)
        await loadList()
      } catch (e: any) {
        ElMessage.error(e?.message || 'Delete failed')
      } finally {
        busyByFile[s.filename] = false
      }
    }

    const templateBadges = computed(() => {
      const chars = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '+', '-', '=']
      return chars.map(c => ({
        char: c,
        count: templates.value[c] || 0,
        have: (templates.value[c] || 0) > 0,
      }))
    })

    onMounted(loadList)

    return {
      samples, loading, busyByFile, inputByFile,
      templateBadges, loadList,
      saveLabel, skipSample,
      goBack: () => router.push('/browser-agent'),
    }
  }
})
