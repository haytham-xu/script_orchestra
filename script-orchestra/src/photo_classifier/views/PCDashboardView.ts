import { defineComponent, onMounted, ref } from 'vue'
import { usePhotoClassifierStore } from '@/photo_classifier/service/PhotoClassifierStore'
import { getFileList } from '@/photo_classifier/service/PhotoClassifierService.ts'
import { loadRootPathFromBackend } from '@/photo_classifier/config/settings'
import { useRouter } from 'vue-router'
import { Setting } from '@element-plus/icons-vue'
import PCSettingsDrawer from '@/photo_classifier/components/PCSettingsDrawer.vue'

export default defineComponent({
  name: 'PCDashboardView',
  components: {
    PCSettingsDrawer,
  },
  setup() {
    const router = useRouter()
    const photoClassifierStore = usePhotoClassifierStore()
    const settingsDrawerVisible = ref(false)

    async function initStore() {
      // Load settings from backend first
      await loadRootPathFromBackend()

      // Then load files
      const defaultFiles = await getFileList()
      photoClassifierStore.initDefaultGroup(defaultFiles)
    }

    function goToDefaultGroup() {
      router.push({ name: 'photo-classifier-default' })
    }

    function goToBatchSelect() {
      router.push({ name: 'photo-classifier-batch-select' })
    }

    function goToGroup(group: any, index: number) {
      router.push({ name: 'photo-classifier-group', params: { groupId: index } })
    }

    function handlePathChanged() {
      // Reload files after path is changed
      initStore()
    }

    onMounted(() => {
      initStore()
    })

    return {
      photoClassifierStore,
      goToDefaultGroup,
      goToBatchSelect,
      goToGroup,
      settingsDrawerVisible,
      handlePathChanged,
      Setting,
    }
  },
})
