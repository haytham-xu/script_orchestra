

import {defineComponent, ref, onMounted, onUnmounted, computed, watch } from 'vue'
import {getButtonConfigJSON, getFolderList, getFileList, postMoveFolder} from "@/manga_classifier/service/MangaClassifierService.ts"
import type {ButtonConfigJSON, FolderObject, FolderObjectList, FileList} from '@/manga_classifier/model/Model'
import {FolderStatus} from '@/manga_classifier/model/Model'
import CategoryButtonCardComponment from "@/manga_classifier/components/CategoryButtonCardComponment.vue"
import { ElMessage } from 'element-plus'

export default defineComponent({
  name: 'ParentView',
  components: { CategoryButtonCardComponment },
  setup() {
    const currentFolderName = ref<string>('')
    const categoryButtonCardJSON = ref<ButtonConfigJSON | null>(null);
    const currentFileList = ref<FileList| null>(null);
    const folderObjectList = ref<FolderObjectList | null>(null);
    const currentFolderObject = ref<FolderObject | null>(null);
    const currentIndex = ref<number>(0);
    let maxFolderindex = 0;

    const pendingCount = computed(() => {
      if (!folderObjectList.value) return 0
        return folderObjectList.value.folderList.filter(f => f.status === FolderStatus.Pending).length
    })
    const totalCount = computed(() => folderObjectList.value?.folderList.length ?? 0)
    const pageTitle = computed(() => `Manage Classifier - ${pendingCount.value}/${totalCount.value}`)

    watch(pageTitle, (newTitle) => {
      document.title = newTitle
    }, { immediate: true })

    async function processRootFolder() {
      categoryButtonCardJSON.value = await getButtonConfigJSON();
      folderObjectList.value = await getFolderList();
      currentFolderObject.value = folderObjectList.value.folderList[currentIndex.value];
      currentFolderName.value = currentFolderObject.value.folderName
      currentFileList.value = await getFileList(currentFolderName.value);
      maxFolderindex = folderObjectList.value!.folderList.length - 1;
    }

    async function nextFolder() {
      if (folderObjectList.value === null || currentFolderObject.value === null) {
        ElMessage.warning("folderObjectList is not ready, please wait.");
        return;
      }
      if(currentIndex.value < maxFolderindex) {
        currentIndex.value += 1;
        currentFolderObject.value = folderObjectList.value.folderList[currentIndex.value];
        currentFolderName.value = currentFolderObject.value.folderName
        currentFileList.value = await getFileList(currentFolderName.value);
        window.scrollTo(0, 0);
      } else if(currentIndex.value == maxFolderindex) {
          currentIndex.value += 1;
          currentFolderName.value = "EOL";
          currentFileList.value = null;
          ElMessage.info('This is the Lates Folder.');
      } else {
          ElMessage.info('This is the Lates Folder.');
      }
    }

    async function previousFolder() {
      if (folderObjectList.value === null || currentFolderObject.value === null) {
        ElMessage.warning("folderObjectList is not ready, please wait.");
        return;
      }
      if(currentIndex.value > 0) {
        currentIndex.value -= 1;
        currentFolderObject.value = folderObjectList.value.folderList[currentIndex.value];
        currentFolderName.value = currentFolderObject.value.folderName
        currentFileList.value = await getFileList(currentFolderName.value);
        window.scrollTo(0, 0);
      } else if(currentIndex.value == 0) {
          currentIndex.value -= 1;
          currentFolderName.value = "EOL";
          currentFileList.value = null;
          ElMessage.info('This is the First Folder.');
      } else {
          ElMessage.info('This is the First Folder.');
      }
    }

    async function moveFolder(sourceFolderPath:string, targetFolderPath:string) {
      if (folderObjectList.value === null || currentFolderObject.value === null) {
        ElMessage.warning("folderObjectList is not ready, please wait.")
        return;
      }
      if (currentFolderObject.value.folderName == "EOL") {
        ElMessage.warning("This is the EOL, cannot move.");
        return;
      }
      if (currentFolderObject.value.status == FolderStatus.Done) {
        ElMessage.info("The Folder already moved.");
        return;
      }
      console.log('moveFolder', sourceFolderPath, targetFolderPath);
      postMoveFolder(sourceFolderPath, targetFolderPath);
      currentFolderObject.value.status = FolderStatus.Done
      nextFolder();
    }

    function handleKeyDown(event: KeyboardEvent) {
      // ArrowUp ArrowDown ArrowLeft ArrowRight Delete
      switch (event.code) {
        case 'ArrowLeft':
          previousFolder()
          break
        case 'ArrowRight':
          nextFolder()
          break
        case 'Space':
          nextFolder()
          break
        case 'Backspace':
          moveFolder(currentFolderName.value, "to_del")
          break
      }
    }

    onMounted(() => {
      processRootFolder()
      window.addEventListener('keydown', handleKeyDown)
    })

    onUnmounted(() => {window.removeEventListener('keydown', handleKeyDown) })

    return {
      categoryButtonCardJSON,
      currentFolderName,
      currentFileList,
      moveFolder,
    };
  },
});
