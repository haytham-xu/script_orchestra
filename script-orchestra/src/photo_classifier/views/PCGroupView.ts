import { defineComponent, ref, onMounted, onUnmounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { usePhotoClassifierStore } from '../service/PhotoClassifierStore'
import { useRouter } from 'vue-router'
import { FileCategory } from '@/photo_classifier/service/Model.ts'
import type { FileModel } from '@/photo_classifier/service/Model.ts'
import MediaComponment from '@/photo_classifier/components/MediaComponment.vue'
import { getFileList } from '@/photo_classifier/service/PhotoClassifierService.ts'
import { loadRootPathFromBackend } from '@/photo_classifier/config/settings'

export default defineComponent({
  name: 'PCGroupView',
  components: { MediaComponment },
  props: {
    groupId: {
      type: Number,
      required: true,
    },
  },
  setup(props) {
    const router = useRouter()
    const photoClassifierStore = usePhotoClassifierStore()

    const currentIndex = ref(0)

    const displayFileList = computed(() => {
      const group = photoClassifierStore.groupList.groupList[props.groupId]
      return group ? group.files : []
    })

    const markAllNormal = () => {
      console.log('[GroupView] markAllNormal - Before:', displayFileList.value.map(f => ({
        file: f.filePath,
        categoryTag: f.categoryTag
      })))
      for (const a_file of displayFileList.value) {
        a_file.categoryTag = FileCategory.NORMAL
      }
      console.log('[GroupView] markAllNormal - After:', displayFileList.value.map(f => ({
        file: f.filePath,
        categoryTag: f.categoryTag
      })))
      photoClassifierStore.autoSaveWorkingState()
    }

    const currentFile = computed<FileModel | null>(() => {
      return displayFileList.value[currentIndex.value] || null
    })

    const goNextImage = () => {
      if (currentIndex.value < displayFileList.value.length - 1) {
        currentIndex.value++
      }
    }

    const goPrevImage = () => {
      if (currentIndex.value > 0) {
        currentIndex.value--
      }
    }

    const goNextGroup = () => {
      if (
        props.groupId >= 0 &&
        props.groupId < photoClassifierStore.groupList.groupList.length - 1
      ) {
        currentIndex.value = 0
        router.push(`/photo-classifier/group/${Number(props.groupId) + 1}`)
      } else {
        ElMessage.info('Already the last group.')
      }
    }

    const goPrevGroup = () => {
      if (props.groupId > 0) {
        currentIndex.value = 0
        router.push(`/photo-classifier/group/${Number(props.groupId) - 1}`)
      } else {
        ElMessage.info('Already the first group.')
      }
    }

    const goToBatchMode = () => {
      router.push(`/photo-classifier/group/${props.groupId}/batch`)
    }

    const applyGroup = async () => {
      await photoClassifierStore.applyFiles(displayFileList.value)

      // Clear working state after successful apply
      await photoClassifierStore.clearWorkingStateFromBackend()

      goNextGroup()
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

    function handleKeydowna(e: KeyboardEvent) {
      // Cache currentFile to avoid multiple computed recalculations
      const file = currentFile.value
      if (!file) return

      switch (e.code) {
        case 'ArrowRight':
          goNextImage()
          break
        case 'ArrowLeft':
          goPrevImage()
          break
        case 'KeyZ':
          console.log(`[GroupView] KeyZ - Setting ${file.filePath} to BEST`)
          file.categoryTag = FileCategory.BEST
          console.log(`[GroupView] KeyZ - New categoryTag: ${file.categoryTag}`)
          photoClassifierStore.autoSaveWorkingState()
          break
        case 'KeyX':
          console.log(`[GroupView] KeyX - Setting ${file.filePath} to BETTER`)
          file.categoryTag = FileCategory.BETTER
          console.log(`[GroupView] KeyX - New categoryTag: ${file.categoryTag}`)
          photoClassifierStore.autoSaveWorkingState()
          break
        case 'KeyC':
          console.log(`[GroupView] KeyC - Setting ${file.filePath} to NORMAL`)
          file.categoryTag = FileCategory.NORMAL
          console.log(`[GroupView] KeyC - New categoryTag: ${file.categoryTag}`)
          photoClassifierStore.autoSaveWorkingState()
          break
        case 'Backspace':
          console.log(`[GroupView] Backspace - Setting ${file.filePath} to DEL`)
          file.categoryTag = FileCategory.DEL
          console.log(`[GroupView] Backspace - New categoryTag: ${file.categoryTag}`)
          photoClassifierStore.autoSaveWorkingState()
          break
        case 'Enter':
          applyGroup()
          break
      }
    }

    onMounted(() => {
      // Initialize store if not already loaded
      if (!photoClassifierStore.initialized) {
        initStore()
      }
      window.addEventListener('keydown', handleKeydowna)
    })

    onUnmounted(() => {
      window.removeEventListener('keydown', handleKeydowna)
    })

    return {
      currentIndex,
      displayFileList,
      currentFile,
      goNextImage,
      goPrevImage,
      goNextGroup,
      goPrevGroup,
      goToBatchMode,
      applyGroup,
      markAllNormal,
    }
  },
})
