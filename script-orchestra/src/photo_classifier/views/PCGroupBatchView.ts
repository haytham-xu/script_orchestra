import { defineComponent, ref, onMounted, onUnmounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, Loading, Picture } from '@element-plus/icons-vue'
import { usePhotoClassifierStore } from '../service/PhotoClassifierStore'
import { useRouter } from 'vue-router'
import type { FileModel } from '@/photo_classifier/service/Model.ts'
import { getFileList } from '@/photo_classifier/service/PhotoClassifierService.ts'
import { loadRootPathFromBackend } from '@/photo_classifier/config/settings'

export default defineComponent({
  name: 'PCGroupBatchView',
  props: {
    groupId: {
      type: Number,
      required: true,
    },
  },
  setup(props) {
    const router = useRouter()
    const photoClassifierStore = usePhotoClassifierStore()

    const selectedFiles = ref<FileModel[]>([])
    const lastSelectedIndex = ref<number | null>(null)

    // Infinite scroll
    const pageSize = 100
    const loadedCount = ref(pageSize)

    const allFiles = computed(() => {
      const group = photoClassifierStore.groupList.groupList[props.groupId]
      console.log(`[GroupBatch] Getting files for group ${props.groupId}:`, {
        groupExists: !!group,
        filesCount: group?.files?.length || 0,
        totalGroups: photoClassifierStore.groupList.groupList.length
      })
      return group ? group.files : []
    })

    const displayFileList = computed(() => {
      const list = allFiles.value.slice(0, loadedCount.value)
      console.log(`[GroupBatch] displayFileList:`, {
        loadedCount: loadedCount.value,
        totalFiles: allFiles.value.length,
        displayCount: list.length
      })
      return list
    })

    const hasMore = computed(() => {
      return loadedCount.value < allFiles.value.length
    })

    function goBack() {
      router.push('/photo-classifier')
    }

    function isSelected(file: FileModel): boolean {
      return selectedFiles.value.some(f => f.filePath === file.filePath)
    }

    function handleImageClick(file: FileModel, index: number, event: MouseEvent) {
      // Shift + Click for range selection
      if (event.shiftKey && lastSelectedIndex.value !== null) {
        const start = Math.min(lastSelectedIndex.value, index)
        const end = Math.max(lastSelectedIndex.value, index)

        // Select all files in range
        for (let i = start; i <= end; i++) {
          const fileToSelect = displayFileList.value[i]
          if (fileToSelect && !isSelected(fileToSelect)) {
            selectedFiles.value.push(fileToSelect)
          }
        }
      } else {
        // Toggle selection for single file
        if (isSelected(file)) {
          selectedFiles.value = selectedFiles.value.filter(f => f.filePath !== file.filePath)
        } else {
          selectedFiles.value.push(file)
        }
        lastSelectedIndex.value = index
      }
    }

    function clearSelection() {
      selectedFiles.value = []
      lastSelectedIndex.value = null
    }

    async function removeSelectedFromGroup() {
      if (selectedFiles.value.length === 0) {
        ElMessage.warning({ message: '请先选择要移除的图片', offset: 20, duration: 1500, customClass: 'message-bottom' })
        return
      }

      try {
        await ElMessageBox.confirm(
          `确定要从分组中移除 ${selectedFiles.value.length} 张图片吗？`,
          '确认移除',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning',
          }
        )

        photoClassifierStore.removeFilesFromGroup(selectedFiles.value, props.groupId)
        clearSelection()
      } catch {
        // User cancelled
      }
    }

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

    function loadMore() {
      if (hasMore.value) {
        loadedCount.value = Math.min(loadedCount.value + pageSize, allFiles.value.length)
      }
    }

    function handleScroll(event: Event) {
      const target = event.target as HTMLElement
      const scrollBottom = target.scrollTop + target.clientHeight
      const threshold = target.scrollHeight - 200

      if (scrollBottom >= threshold && hasMore.value) {
        loadMore()
      }
    }

    onMounted(async () => {
      // Initialize store with working state or fresh data
      await initStore()

      console.log(`[GroupBatch] onMounted - groupId: ${props.groupId}`)
      console.log(`[GroupBatch] Store state:`, {
        totalGroups: photoClassifierStore.groupList.groupList.length,
        groupFiles: photoClassifierStore.groupList.groupList[props.groupId]?.files?.length || 0
      })

      const gridElement = document.querySelector('.image-grid')
      if (gridElement) {
        gridElement.addEventListener('scroll', handleScroll)
      }
    })

    onUnmounted(() => {
      const gridElement = document.querySelector('.image-grid')
      if (gridElement) {
        gridElement.removeEventListener('scroll', handleScroll)
      }
    })

    return {
      photoClassifierStore,
      selectedFiles,
      displayFileList,
      allFiles,
      hasMore,
      goBack,
      isSelected,
      handleImageClick,
      clearSelection,
      removeSelectedFromGroup,
      loadMore,
      Check,
      Loading,
      Picture,
    }
  },
})
