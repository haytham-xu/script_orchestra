

import {defineComponent, ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { usePhotoClassifierStore } from '../store/PhotoClassifierStore';
import { useRouter } from 'vue-router'
import type { GroupList, DefaultGroup, FileModel, Group} from '@/photo_classifier/model/Model.ts'
import { FileCategory, FileStatus, FileType, GroupStatus } from '@/photo_classifier/model/Model.ts'
import MediaComponment from '@/photo_classifier/components/MediaComponment.vue'

export default defineComponent({
  name: 'PCDefaultGroupView',
  components: {MediaComponment},
  setup() {
    const router = useRouter()
    const photoClassifierStore = usePhotoClassifierStore()

    const currentIndex = ref(0)
    const currentLastGroupIndex = ref(-1)
    const showFiltered = ref(false)
    const drawerVisible = ref(false)

    const displayFileList = computed<FileModel[]>(() => {
    const files = photoClassifierStore.defaultGroup.files;
      if (!showFiltered.value) {
        return files;
      }
      return files.filter(f => f.fileStatus !== FileStatus.IN_GROUP);
    });

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
      if (!currentDisplayFile) return
      photoClassifierStore.addFileToGroup(file, index)
      nextFile()
    }

    const applyGroup = async () => {
      await photoClassifierStore.applyFiles(displayFileList.value)
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (!currentDisplayFile.value) {
          return;
      }

      switch (event.code) {
        case 'ArrowLeft':
          prevFile()
          break
        case 'ArrowRight':
          nextFile()
          break
        case 'Space':
          photoClassifierStore.addFileToGroup(currentDisplayFile.value, currentLastGroupIndex.value)
          nextFile()
          break
        case 'Enter':
          currentLastGroupIndex.value = photoClassifierStore.createNewGroupWithFile(currentDisplayFile.value)
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
        default:
          if (/^Digit[0-9]$/.test(event.code)) {
            console.log("hi", event.code)
          }
      }
    }

    function updateDisplayFiles() {
      currentIndex.value = 0
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
      applyGroup
    }
  }
})

