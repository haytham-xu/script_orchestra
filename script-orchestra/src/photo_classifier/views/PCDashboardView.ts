import { defineComponent, onMounted } from 'vue'
import { usePhotoClassifierStore } from '@/photo_classifier/service/PhotoClassifierStore'
import { getFileList } from '@/photo_classifier/service/PhotoClassifierService.ts'
import { useRouter } from 'vue-router'

export default defineComponent({
  name: 'PCDashboardView',
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

    return {
      photoClassifierStore,
      goToDefaultGroup,
      goToGroup,
    }
  },
})
