import { defineComponent, ref, onMounted, onUnmounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Loading, Picture } from '@element-plus/icons-vue'
import { usePhotoClassifierStore } from '../service/PhotoClassifierStore'
import { useRouter } from 'vue-router'
import type { FileModel } from '@/photo_classifier/service/Model.ts'
import { FileStatus } from '@/photo_classifier/service/Model.ts'

export default defineComponent({
  name: 'PCBatchSelectView',
  setup() {
    const router = useRouter()
    const photoClassifierStore = usePhotoClassifierStore()

    const selectedFiles = ref<FileModel[]>([])
    const showUnGroupedOnly = ref(false)
    const showGroupSelectDrawer = ref(false)
    const lastSelectedIndex = ref<number | null>(null)

    // Infinite scroll
    const pageSize = 100 // 每次加载100张
    const loadedCount = ref(pageSize) // 已加载数量

    const allFiles = computed<FileModel[]>(() => {
      const files = photoClassifierStore.defaultGroup.files
      if (!showUnGroupedOnly.value) {
        return files
      }
      return files.filter((f) => f.fileStatus !== FileStatus.IN_GROUP)
    })

    const displayFileList = computed<FileModel[]>(() => {
      return allFiles.value.slice(0, loadedCount.value)
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

    function createNewGroupWithSelected() {
      if (selectedFiles.value.length === 0) {
        ElMessage.warning('请先选择图片')
        return
      }

      const newGroupId = photoClassifierStore.batchCreateNewGroup(selectedFiles.value)
      ElMessage.success(`已创建新分组 ${newGroupId}，包含 ${selectedFiles.value.length} 张图片`)
      clearSelection()
    }

    function addSelectedToGroup(groupIndex: number) {
      if (selectedFiles.value.length === 0) {
        ElMessage.warning('请先选择图片')
        return
      }

      photoClassifierStore.batchAddFilesToGroup(selectedFiles.value, groupIndex)
      ElMessage.success(`已将 ${selectedFiles.value.length} 张图片添加到分组 ${groupIndex}`)
      clearSelection()
      showGroupSelectDrawer.value = false
    }

    function handleFilterChange() {
      // Clear selection when switching filter mode
      clearSelection()
      // Reset loaded count
      loadedCount.value = pageSize
    }

    function loadMore() {
      if (hasMore.value) {
        loadedCount.value = Math.min(loadedCount.value + pageSize, allFiles.value.length)
      }
    }

    // Infinite scroll handler
    function handleScroll(event: Event) {
      const target = event.target as HTMLElement
      const scrollBottom = target.scrollTop + target.clientHeight
      const threshold = target.scrollHeight - 200 // 提前200px触发加载

      if (scrollBottom >= threshold && hasMore.value) {
        loadMore()
      }
    }

    onMounted(() => {
      // 找到滚动容器并添加监听器
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
      showUnGroupedOnly,
      showGroupSelectDrawer,
      displayFileList,
      allFiles,
      hasMore,
      goBack,
      isSelected,
      handleImageClick,
      clearSelection,
      createNewGroupWithSelected,
      addSelectedToGroup,
      handleFilterChange,
      loadMore,
      Check,
      Loading,
      Picture,
    }
  },
})
