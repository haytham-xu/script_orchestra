

import {defineComponent, ref, onMounted, onUnmounted, computed, watch, reactive } from 'vue'
import { useRouter } from 'vue-router'
import {getButtonConfigJSON, getFolderList, getFileList, postMoveFolder, postDeleteFolder, postUndo} from "@/manga_classifier/service/MangaClassifierService"
import type {ButtonConfigJSON, FolderObject, FolderObjectList, FileList} from '@/manga_classifier/service/Model'
import {FolderStatus} from '@/manga_classifier/service/Model'
import CategoryButtonCardComponment from "@/manga_classifier/components/CategoryButtonCardComponment.vue"
import { ElMessage } from 'element-plus'
import { Setting, RefreshLeft } from '@element-plus/icons-vue'

export default defineComponent({
  name: 'ParentView',
  components: { CategoryButtonCardComponment, Setting, RefreshLeft },
  setup() {
    const router = useRouter()
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
    // 1-based index of the current focus; 0 when empty; totalCount+1 when past EOL.
    const currentDisplayIndex = computed(() => {
      if (!folderObjectList.value?.folderList.length) return 0
      return Math.min(currentIndex.value + 1, totalCount.value)
    })
    const progressPercent = computed(() => {
      if (!totalCount.value) return 0
      return Math.round((currentDisplayIndex.value / totalCount.value) * 100)
    })
    const pageTitle = computed(() => `Manage Classifier - ${pendingCount.value}/${totalCount.value}`)
    const isEmpty = computed(() =>
      folderObjectList.value !== null && folderObjectList.value.folderList.length === 0
    )

    // Set of folder names that can currently be undone in this session.
    // Mirrors the backend stack; entries are removed on successful undo.
    const undoableNames = reactive(new Set<string>())

    // The current folder was moved/deleted and is still undoable → show
    // inline restore UI in the content area instead of files.
    const canRestoreCurrent = computed(() =>
      currentFolderObject.value?.status === FolderStatus.Done &&
      currentFolderName.value !== 'EOL' &&
      undoableNames.has(currentFolderName.value)
    )

    // The current folder was already handled but its undo record is gone
    // (e.g., stack cleared, backend restarted) → show a lightweight "processed" hint.
    const isProcessedNoUndo = computed(() =>
      currentFolderObject.value?.status === FolderStatus.Done &&
      currentFolderName.value !== 'EOL' &&
      !undoableNames.has(currentFolderName.value)
    )

    watch(pageTitle, (newTitle) => {
      document.title = newTitle
    }, { immediate: true })

    async function processRootFolder() {
      categoryButtonCardJSON.value = await getButtonConfigJSON();
      folderObjectList.value = await getFolderList();
      if (!folderObjectList.value.folderList.length) {
        currentFolderObject.value = null;
        currentFolderName.value = '';
        currentFileList.value = null;
        maxFolderindex = -1;
        return;
      }
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
      const movedName = sourceFolderPath;
      try {
        await postMoveFolder(sourceFolderPath, targetFolderPath);
        currentFolderObject.value.status = FolderStatus.Done
        undoableNames.add(movedName);
        ElMessage.success(`Moved: ${sourceFolderPath} → ${targetFolderPath}`);
        nextFolder();
      } catch (e: any) {
        const msg = e?.response?.data?.error || e.message || 'Failed to move'
        ElMessage.error(msg);
      }
    }

    async function deleteFolder() {
      if (folderObjectList.value === null || currentFolderObject.value === null) {
        ElMessage.warning("folderObjectList is not ready, please wait.")
        return;
      }
      if (currentFolderObject.value.folderName == "EOL") {
        ElMessage.warning("This is the EOL, cannot delete.");
        return;
      }
      if (currentFolderObject.value.status == FolderStatus.Done) {
        ElMessage.info("The Folder already moved.");
        return;
      }
      const movedName = currentFolderName.value;
      try {
        await postDeleteFolder(movedName);
        currentFolderObject.value.status = FolderStatus.Done;
        undoableNames.add(movedName);
        ElMessage.success(`Deleted: ${movedName}`);
        nextFolder();
      } catch (e: any) {
        const msg = e?.response?.data?.error || e.message || 'Failed to delete'
        ElMessage.error(msg);
      }
    }

    async function handleUndoCurrent() {
      const folderObj = currentFolderObject.value;
      const name = currentFolderName.value;
      if (!folderObj || !name || !undoableNames.has(name)) return;
      try {
        await postUndo(name);
        folderObj.status = FolderStatus.Pending;
        undoableNames.delete(name);
        // Reload file list for this folder now that it's back in place.
        currentFileList.value = await getFileList(name);
        ElMessage.success(`Restored: ${name}`);
      } catch (e: any) {
        const msg = e?.response?.data?.error || e.message || 'Failed to undo'
        ElMessage.error(msg);
        // Backend rejected — the stale entry is no longer valid, drop it.
        undoableNames.delete(name);
      }
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
          deleteFolder()
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
      goToSettings: () => router.push('/manga-classifier/settings'),
      isEmpty,
      canRestoreCurrent,
      isProcessedNoUndo,
      handleUndoCurrent,
      currentDisplayIndex,
      totalCount,
      progressPercent,
    };
  },
});
