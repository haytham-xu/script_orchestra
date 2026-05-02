import { defineComponent, ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { usePhotoClassifierStore } from '../service/PhotoClassifierStore'
import { useRouter } from 'vue-router'
import type { FileModel } from '@/photo_classifier/service/Model.ts'
import { FileCategory, FileStatus } from '@/photo_classifier/service/Model.ts'
import MediaComponment from '@/photo_classifier/components/MediaComponment.vue'

export default defineComponent({
  name: 'PCDefaultGroupView',
  components: { MediaComponment },
  setup() {
    const currentIndex = ref(0)
    const isEditing = ref(false)
    const editValue = ref(1)

    function startEditing() {
      isEditing.value = true
      editValue.value = currentIndex!.value + 1
    }

    function applyEdit() {
      let newIndex = editValue.value - 1
      if (newIndex < 0) newIndex = 0
      if (newIndex >= displayFileList!.value.length) {
        newIndex = displayFileList!.value.length - 1
      }
      isEditing.value = false
    }

    const router = useRouter()
    const photoClassifierStore = usePhotoClassifierStore()

    const showFiltered = ref(false)
    const drawerVisible = ref(false)

    const displayFileList = computed<FileModel[]>(() => {
      const files = photoClassifierStore.defaultGroup.files
      if (!showFiltered.value) {
        return files
      }
      return files.filter((f) => f.fileStatus !== FileStatus.IN_GROUP)
    })

    const currentDisplayFile = computed<FileModel | null>(() => {
      return displayFileList.value[currentIndex.value] || null
    })

    function goBack() {
      router.push('/photo-classifier')
    }

    function nextFile() {
      if (currentIndex.value < displayFileList.value.length - 1) {
        currentIndex.value++
      }
    }

    function prevFile() {
      if (currentIndex.value > 0) {
        currentIndex.value--
      }
    }

    function addToGroup(file: FileModel, index: number) {
      if (!file) return
      photoClassifierStore.addFileToGroup(file, index)
      nextFile()
    }

    const applyGroup = async () => {
      await photoClassifierStore.applyFiles(displayFileList.value)

      // 处理完成后，调整 currentIndex
      if (currentIndex.value >= displayFileList.value.length) {
        currentIndex.value = Math.max(0, displayFileList.value.length - 1)
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      // Ignore repeated key events to prevent duplicate operations
      if (event.repeat) {
        return
      }
      if (!currentDisplayFile.value) {
        return
      }

      switch (event.code) {
        case 'ArrowLeft':
          prevFile()
          break
        case 'ArrowRight':
          nextFile()
          break
        case 'KeyW':
          // W: Add to current group index
          if (photoClassifierStore.currentGroupIndex >= 0) {
            photoClassifierStore.addFileToGroup(currentDisplayFile.value, photoClassifierStore.currentGroupIndex)
            nextFile()
          } else {
            ElMessage.warning('No group selected. Press Q to create a new group first.')
          }
          break
        case 'KeyQ':
          // Q: Always create a new group
          photoClassifierStore.createNewGroupWithFile(currentDisplayFile.value)
          nextFile()
          break
        case 'Backspace':
          currentDisplayFile.value.categoryTag = FileCategory.DEL
          break
        case 'KeyZ':
          currentDisplayFile.value.categoryTag = FileCategory.BEST
          break
        case 'KeyX':
          currentDisplayFile.value.categoryTag = FileCategory.BETTER
          break
        case 'KeyC':
          currentDisplayFile.value.categoryTag = FileCategory.NORMAL
          break
      }
    }

    function updateDisplayFiles() {
      // Try to maintain the current file when switching filter modes
      const currentFilePath = currentDisplayFile.value?.filePath

      // Reset to beginning if there's no current file
      if (!currentFilePath) {
        currentIndex.value = 0
        return
      }

      // Find the current file in the new filtered list
      const newIndex = displayFileList.value.findIndex(f => f.filePath === currentFilePath)

      if (newIndex >= 0) {
        // Keep the same file if it's still in the filtered list
        currentIndex.value = newIndex
      } else {
        // Otherwise, try to stay at a similar position or reset to 0
        currentIndex.value = Math.min(currentIndex.value, displayFileList.value.length - 1)
        if (currentIndex.value < 0) currentIndex.value = 0
      }
    }

    function goToGroup(index: number) {
      router.push(`/photo-classifier/group/${index}`)
    }

    onMounted(() => {
      window.addEventListener('keydown', handleKeyDown)
    })

    onUnmounted(() => {
      window.removeEventListener('keydown', handleKeyDown)
    })

    return {
      photoClassifierStore,
      currentIndex,
      showFiltered,
      drawerVisible,
      displayFileList,
      currentFile: currentDisplayFile,
      goBack,
      goToGroup,
      addToGroup,
      updateDisplayFiles,
      applyGroup,
      isEditing,
      editValue,
      applyEdit,
      startEditing,
    }
  },
})
