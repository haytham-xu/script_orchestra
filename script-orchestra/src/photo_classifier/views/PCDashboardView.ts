import { defineComponent, onMounted, ref } from 'vue'
import { usePhotoClassifierStore } from '@/photo_classifier/service/PhotoClassifierStore'
import { getFileList } from '@/photo_classifier/service/PhotoClassifierService.ts'
import { loadRootPathFromBackend } from '@/photo_classifier/config/settings'
import { useRouter } from 'vue-router'
import { Setting } from '@element-plus/icons-vue'
import PCSettingsDrawer from '@/photo_classifier/components/PCSettingsDrawer.vue'
import { ElMessageBox } from 'element-plus'

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

      // Try to load working state first
      const hasWorkingState = await photoClassifierStore.loadWorkingStateFromBackend()

      // If no working state, load files from backend
      if (!hasWorkingState) {
        const defaultFiles = await getFileList()
        photoClassifierStore.initDefaultGroup(defaultFiles)
      }
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

    function isVideoUrl(url: string): boolean {
      // Check if URL contains video file extension or video MIME type in query params
      return url.includes('type=video') || /\.(mp4|webm|ogg|mov|avi|mkv)(\?|$)/i.test(url)
    }

    async function handleReset() {
      try {
        await ElMessageBox.confirm(
          '确定要重置所有分组和标记吗？此操作不可撤销。',
          '确认重置',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning',
          }
        )

        // Reset store state
        await photoClassifierStore.resetAllState()

        // Clear working state from backend
        await photoClassifierStore.clearWorkingStateFromBackend()

        // Reload data
        await initStore()
      } catch {
        // User cancelled
      }
    }

    onMounted(() => {
      initStore()
    })

    return {
      goBack: () => router.push('/'),
      photoClassifierStore,
      goToDefaultGroup,
      goToBatchSelect,
      goToGroup,
      settingsDrawerVisible,
      handlePathChanged,
      handleReset,
      isVideoUrl,
      Setting,
    }
  },
})
