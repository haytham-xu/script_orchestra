

import {defineComponent, ref, onMounted, onUnmounted, computed, watch, reactive, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import {getButtonConfigJSON, getFolderList, getFileList, postMoveFolder, postDeleteFolder, postUndo, postOpenFolder} from "@/manga_classifier/service/MangaClassifierService"
import type {ButtonConfigJSON, FolderObject, FolderObjectList, FileList} from '@/manga_classifier/service/Model'
import {FolderStatus} from '@/manga_classifier/service/Model'
import {getSettings} from '@/manga_classifier/service/SettingsService'
import CategoryButtonCardComponment from "@/manga_classifier/components/CategoryButtonCardComponment.vue"
import { ElMessage } from 'element-plus'
import { Setting, RefreshLeft, FolderOpened } from '@element-plus/icons-vue'

export default defineComponent({
  name: 'ParentView',
  components: { CategoryButtonCardComponment, Setting, RefreshLeft, FolderOpened },
  setup() {
    const router = useRouter()
    const currentFolderName = ref<string>('')
    const categoryButtonCardJSON = ref<ButtonConfigJSON | null>(null);
    const currentFileList = ref<FileList| null>(null);
    const folderObjectList = ref<FolderObjectList | null>(null);
    const currentFolderObject = ref<FolderObject | null>(null);
    const currentIndex = ref<number>(0);
    let maxFolderindex = 0;

    // Reading UI preferences loaded from settings (with sensible defaults).
    const imageWidthPx = ref<number>(520)
    const scrollPageRatio = ref<number>(0.85)
    const pinSidebars = ref<boolean>(false)

    // Dynamically shrink the header title font for long folder names so it
    // doesn't crowd the progress indicator / action buttons.
    const titleFontSize = computed(() => {
      const len = currentFolderName.value?.length ?? 0
      if (len <= 20) return '20px'
      if (len <= 35) return '16px'
      return '13px'
    })

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

    const isLoadingFiles = ref(false)

    // Debounced file loader — cancels any in-flight request when the folder
    // changes again within the debounce window, and only actually calls
    // getFileList after the user has settled on a folder for LOAD_DEBOUNCE_MS.
    const LOAD_DEBOUNCE_MS = 500
    let debounceTimer: ReturnType<typeof setTimeout> | null = null
    let activeAbort: AbortController | null = null

    function scheduleLoadFiles(folderName: string) {
      // Cancel any pending debounce.
      if (debounceTimer) {
        clearTimeout(debounceTimer)
        debounceTimer = null
      }
      // Abort any in-flight request from a previous folder.
      if (activeAbort) {
        activeAbort.abort()
        activeAbort = null
      }
      // Clear the currently-displayed files immediately so the user doesn't
      // see stale content while paging through.
      currentFileList.value = null
      if (!folderName || folderName === 'EOL') {
        isLoadingFiles.value = false
        return
      }
      isLoadingFiles.value = true
      debounceTimer = setTimeout(async () => {
        debounceTimer = null
        const abort = new AbortController()
        activeAbort = abort
        try {
          const result = await getFileList(folderName, abort.signal)
          if (abort.signal.aborted) return
          currentFileList.value = result
        } catch (e: any) {
          if (abort.signal.aborted || e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED') return
          console.error('Failed to load files:', e)
        } finally {
          if (activeAbort === abort) {
            activeAbort = null
            isLoadingFiles.value = false
          }
        }
      }, LOAD_DEBOUNCE_MS)
    }

    function jumpToIndex(oneBasedIndex: number) {
      if (folderObjectList.value === null) {
        ElMessage.warning("folderObjectList is not ready, please wait.");
        return;
      }
      const total = folderObjectList.value.folderList.length;
      if (!total) return;
      // Clamp to valid range.
      const clamped = Math.max(1, Math.min(oneBasedIndex, total));
      const zeroBased = clamped - 1;
      if (zeroBased === currentIndex.value && currentFolderObject.value?.folderName !== 'EOL') return;
      currentIndex.value = zeroBased;
      currentFolderObject.value = folderObjectList.value.folderList[zeroBased];
      currentFolderName.value = currentFolderObject.value.folderName;
      scheduleLoadFiles(currentFolderName.value);
      window.scrollTo(0, 0);
    }

    // Inline editing of the current index in the header.
    const editingIndex = ref(false)
    const indexInputValue = ref<number | string>('')
    const indexInputRef = ref<HTMLInputElement | null>(null)

    async function startIndexEdit() {
      indexInputValue.value = currentDisplayIndex.value
      editingIndex.value = true
      await nextTick()
      indexInputRef.value?.focus()
      indexInputRef.value?.select()
    }

    function commitIndexEdit() {
      if (!editingIndex.value) return
      const raw = indexInputValue.value
      const parsed = typeof raw === 'number' ? raw : parseInt(String(raw), 10)
      editingIndex.value = false
      if (!Number.isFinite(parsed)) return
      jumpToIndex(parsed)
    }

    function cancelIndexEdit() {
      editingIndex.value = false
    }

    async function loadReadingSettings() {
      try {
        const s = await getSettings()
        if (typeof s.imageWidthPx === 'number') imageWidthPx.value = s.imageWidthPx
        if (typeof s.scrollPageRatio === 'number') scrollPageRatio.value = s.scrollPageRatio
        if (typeof s.pinSidebars === 'boolean') pinSidebars.value = s.pinSidebars
      } catch (e) {
        console.error('Failed to load reading settings:', e)
      }
      // Inject the fixed reader width as a CSS variable consumed by the view.
      document.documentElement.style.setProperty('--mc-img-width', `${imageWidthPx.value}px`)
    }

    // ArrowUp / ArrowDown scroll the page by a fraction of the viewport so the
    // user keeps their reading position (a small overlap, like PageDown).
    function scrollByPage(dir: number) {
      const amount = dir * window.innerHeight * scrollPageRatio.value
      window.scrollBy({ top: amount, behavior: 'smooth' })
    }

    async function openCurrentFolder() {
      const name = currentFolderName.value
      if (!name || name === 'EOL') return
      try {
        await postOpenFolder(name)
      } catch (e: any) {
        const msg = e?.response?.data?.error || e.message || 'Failed to open folder'
        ElMessage.error(msg)
      }
    }

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
      maxFolderindex = folderObjectList.value!.folderList.length - 1;
      scheduleLoadFiles(currentFolderName.value)
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
        scheduleLoadFiles(currentFolderName.value)
        window.scrollTo(0, 0);
      } else if(currentIndex.value == maxFolderindex) {
          currentIndex.value += 1;
          currentFolderName.value = "EOL";
          scheduleLoadFiles('EOL');
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
        scheduleLoadFiles(currentFolderName.value)
        window.scrollTo(0, 0);
      } else if(currentIndex.value == 0) {
          currentIndex.value -= 1;
          currentFolderName.value = "EOL";
          scheduleLoadFiles('EOL');
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
        // Reload file list immediately (user explicit action, no debounce).
        // Cancel any pending debounce/inflight first.
        if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; }
        if (activeAbort) { activeAbort.abort(); activeAbort = null; }
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
      // Don't hijack keys while user is typing in an input (index editor,
      // future search box, etc.).
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        return;
      }
      // ArrowUp ArrowDown ArrowLeft ArrowRight Delete
      switch (event.code) {
        case 'ArrowLeft':
          previousFolder()
          break
        case 'ArrowRight':
          nextFolder()
          break
        case 'ArrowDown':
          scrollByPage(1)
          event.preventDefault()
          break
        case 'ArrowUp':
          scrollByPage(-1)
          event.preventDefault()
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
      loadReadingSettings()
      processRootFolder()
      window.addEventListener('keydown', handleKeyDown)
    })

    onUnmounted(() => {
      window.removeEventListener('keydown', handleKeyDown);
      if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; }
      if (activeAbort) { activeAbort.abort(); activeAbort = null; }
    })

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
      isLoadingFiles,
      jumpToIndex,
      editingIndex,
      indexInputValue,
      indexInputRef,
      startIndexEdit,
      commitIndexEdit,
      cancelIndexEdit,
      titleFontSize,
      pinSidebars,
      openCurrentFolder,
    };
  },
});
