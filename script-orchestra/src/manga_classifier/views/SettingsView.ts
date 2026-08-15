import { defineComponent, ref, computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  Plus,
  Delete,
  Refresh,
} from '@element-plus/icons-vue'
import { getSettings, updateSettings } from '@/manga_classifier/service/SettingsService'
import type {
  MangaClassifierSettings,
  CategoryButton,
} from '@/manga_classifier/service/Model'

const DEFAULT_SETTINGS: MangaClassifierSettings = {
  rootPath: '',
  targetPath: '',
  deletePath: '',
  imageExts: ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'],
  videoExts: ['.mp4', '.webm', '.mov', '.avi', '.mkv'],
  categoty: {
    left:  { name: 'Left',  mainButtons: [], subButtons: [] },
    right: { name: 'Right', mainButtons: [], subButtons: [] },
  },
}

function cloneSettings(s: MangaClassifierSettings): MangaClassifierSettings {
  return JSON.parse(JSON.stringify(s))
}

export default defineComponent({
  name: 'MangaClassifierSettingsView',
  components: { ArrowLeft, Plus, Delete, Refresh },
  setup() {
    const router = useRouter()
    const state = reactive<MangaClassifierSettings>(cloneSettings(DEFAULT_SETTINGS))
    const originalJson = ref<string>(JSON.stringify(DEFAULT_SETTINGS))
    const loading = ref(false)
    const saving = ref(false)

    const newImageExt = ref('')
    const newVideoExt = ref('')

    const isDirty = computed(() => JSON.stringify(state) !== originalJson.value)

    async function load() {
      loading.value = true
      try {
        const s = await getSettings()
        Object.assign(state, s)
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
        const msg = e?.response?.data?.error || e.message || 'Failed to save settings'
        ElMessage.error(msg)
      } finally {
        saving.value = false
      }
    }

    function resetToDefaults() {
      Object.assign(state, cloneSettings(DEFAULT_SETTINGS))
    }

    function addExt(kind: 'image' | 'video') {
      const raw = kind === 'image' ? newImageExt.value : newVideoExt.value
      const trimmed = raw.trim()
      if (!trimmed) return
      const list = kind === 'image' ? state.imageExts : state.videoExts
      let normalized = trimmed.toLowerCase()
      if (!normalized.startsWith('.')) normalized = '.' + normalized
      if (!list.includes(normalized)) list.push(normalized)
      if (kind === 'image') newImageExt.value = ''
      else newVideoExt.value = ''
    }

    function removeExt(kind: 'image' | 'video', ext: string) {
      const list = kind === 'image' ? state.imageExts : state.videoExts
      const i = list.indexOf(ext)
      if (i !== -1) list.splice(i, 1)
    }

    function addButton(side: 'left' | 'right', group: 'mainButtons' | 'subButtons') {
      state.categoty[side][group].push({ label: '', folderPath: '' })
    }

    function removeButton(
      side: 'left' | 'right',
      group: 'mainButtons' | 'subButtons',
      idx: number,
    ) {
      state.categoty[side][group].splice(idx, 1)
    }

    function goBack() {
      router.push('/manga-classifier')
    }

    function resolveTargetPath(folderPath: string): string {
      const target = state.targetPath.trim()
      // Sub is user-entered relative path; strip leading separators of either flavor.
      const sub = (folderPath || '').replace(/^[\\/]+/, '')
      if (!target && !sub) return ''
      if (!target) return sub
      if (!sub) return target
      // Detect the separator style already used in target so preview matches
      // the user's platform / typing. Fall back to '/' when target has no separator.
      const sep = target.includes('\\') && !target.includes('/') ? '\\' : '/'
      return target.replace(/[\\/]+$/, '') + sep + sub.replace(/\//g, sep)
    }

    onMounted(load)

    return {
      state,
      loading,
      saving,
      isDirty,
      newImageExt,
      newVideoExt,
      load,
      save,
      resetToDefaults,
      addExt,
      removeExt,
      addButton,
      removeButton,
      goBack,
      resolveTargetPath,
      // typed helpers for template
      leftMain: computed<CategoryButton[]>(() => state.categoty.left.mainButtons),
      leftSub:  computed<CategoryButton[]>(() => state.categoty.left.subButtons),
      rightMain: computed<CategoryButton[]>(() => state.categoty.right.mainButtons),
      rightSub:  computed<CategoryButton[]>(() => state.categoty.right.subButtons),
    }
  },
})
