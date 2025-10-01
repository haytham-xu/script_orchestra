

import {defineComponent, ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { usePhotoClassifierStore } from '../store/PhotoClassifierStore';
import { useRouter } from 'vue-router'
import { FileCategory, FileStatus, FileType, GroupStatus } from '@/photo_classifier/model/Model.ts'
import type { FileModel } from '@/photo_classifier/model/Model.ts'
import MediaComponment from '@/photo_classifier/components/MediaComponment.vue'

export default defineComponent({
  name: 'PCGroupView',
  components: {MediaComponment},
  props: {
    groupId: {
      type: Number,
      required: true
    }
  },
  setup(props) {
    const router = useRouter()
    const photoClassifierStore = usePhotoClassifierStore()

    const currentIndex = ref(0)

    const displayFileList = computed(() => {
      const group = photoClassifierStore.groupList.groupList[props.groupId]
      return group ? group.files : []
    })

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
      if (props.groupId >= 0 && props.groupId < photoClassifierStore.groupList.groupList.length - 1) {
        router.push(`/photo-classifier/group/${Number(props.groupId) + 1}`)
      } else {
        ElMessage.info("Already the last group.")
      }
      
    }

    const goPrevGroup = () => {
      if (props.groupId > 0) {
        router.push(`/photo-classifier/group/${Number(props.groupId) - 1}`)
      } else {
        ElMessage.info("Already the first group.")
      }
    }

    const setCategory = (category: FileCategory) => {
      if (currentFile.value) {
        currentFile.value.categoryTag = category
        // goNextImage()
      }
    }

    const applyGroup = async () => {
      await photoClassifierStore.applyFiles(displayFileList.value)
      goNextGroup()
    }

    function handleKeydowna(e: KeyboardEvent) {
      switch (e.code) {
        case 'ArrowRight':
          goNextImage()
          break
        case 'ArrowLeft':
          goPrevImage()
          break
        case 'KeyZ':
          setCategory(FileCategory.BEST)
          break
        case 'KeyX':
          setCategory(FileCategory.BETTER)
          break
        case 'KeyC':
          setCategory(FileCategory.NORMAL)
          break
        case 'Backspace':
          setCategory(FileCategory.DEL)
          break
      }
    }

    onMounted(() => {
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
      applyGroup,
      // setCategory
    }
  }
})
