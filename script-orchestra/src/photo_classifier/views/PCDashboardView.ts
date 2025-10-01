

import {defineComponent, ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { usePhotoClassifierStore } from '@/photo_classifier/store/PhotoClassifierStore';
import {getFileList} from '@/photo_classifier/service/PhotoClassifierService.ts'
import { useRouter } from 'vue-router'

export default defineComponent({
  name: 'PCDashboardView',
  components: {},
  setup() {
    const router = useRouter()
    const photoClassifierStore = usePhotoClassifierStore()

    async function initStore() {
      const defaultFiles = await getFileList()
      photoClassifierStore.initDefaultGroup(defaultFiles)
    }

    function goToDefaultGroup() {
      router.push({ name: 'photo-classifier-default' })
    }

    function goToGroup(group: any, index: number) {
      router.push({ name: 'photo-classifier-group', params: { groupId: index } })
    }

    onMounted(() => {
      initStore()
    })

    onUnmounted(() => {
      
    })

    return {
      photoClassifierStore,
      goToDefaultGroup,
      goToGroup
    }
  },
})
