import { defineComponent, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchSettings, updateSettings } from '@/manga_viwer/service/Service'
import type { MangaViewerSettings, CategoryOption } from '../service/Model'
import { ElMessage, ElMessageBox, ElLoading } from 'element-plus'

export default defineComponent({
  name: 'SettingsView',
  setup() {
    const router = useRouter()
    const settings = ref<MangaViewerSettings | null>(null)

    function goBack() {
      router.push('/manga-viewer')
    }

    async function loadSettings() {
      const loading = ElLoading.service({ lock: true, text: 'Loading settings...', background: 'rgba(0,0,0,0.4)' })
      try {
        settings.value = await fetchSettings()
      } catch (e) {
        console.error('Failed to load settings:', e)
        ElMessage.error('Failed to load settings')
      } finally {
        loading.close()
      }
    }

    async function handleSave() {
      if (!settings.value) return

      const loading = ElLoading.service({ lock: true, text: 'Saving...', background: 'rgba(0,0,0,0.4)' })
      try {
        await updateSettings(settings.value)
        ElMessage.success('Settings saved successfully')
      } catch (e) {
        console.error('Failed to save settings:', e)
        ElMessage.error('Failed to save settings')
      } finally {
        loading.close()
      }
    }

    function addMainCategory() {
      if (!settings.value) return
      settings.value.categories.main.push({
        id: '',
        label: '',
        target_folder: ''
      })
    }

    function removeMainCategory(index: number) {
      if (!settings.value) return
      settings.value.categories.main.splice(index, 1)
    }

    function addSubCategory() {
      if (!settings.value) return
      settings.value.categories.sub.push({
        id: '',
        label: ''
      })
    }

    function removeSubCategory(index: number) {
      if (!settings.value) return
      settings.value.categories.sub.splice(index, 1)
    }

    function addScanFolder() {
      if (!settings.value) return
      settings.value.paths.scan_folders.push('')
    }

    function removeScanFolder(index: number) {
      if (!settings.value) return
      settings.value.paths.scan_folders.splice(index, 1)
    }

    function addIgnoreScanFolder() {
      if (!settings.value) return
      settings.value.paths.ignore_scan_folders.push('')
    }

    function removeIgnoreScanFolder(index: number) {
      if (!settings.value) return
      settings.value.paths.ignore_scan_folders.splice(index, 1)
    }

    onMounted(() => {
      loadSettings()
    })

    return {
      settings,
      goBack,
      handleSave,
      addMainCategory,
      removeMainCategory,
      addSubCategory,
      removeSubCategory,
      addScanFolder,
      removeScanFolder,
      addIgnoreScanFolder,
      removeIgnoreScanFolder,
    }
  }
})
