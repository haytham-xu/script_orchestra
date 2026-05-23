import { defineComponent, ref, onMounted, onUnmounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { usePhotoClassifierStore } from '../service/PhotoClassifierStore'
import { useRouter } from 'vue-router'
import type { FileModel } from '@/photo_classifier/service/Model.ts'
import { FileCategory, FileStatus } from '@/photo_classifier/service/Model.ts'
import MediaComponment from '@/photo_classifier/components/MediaComponment.vue'
import { getFileList } from '@/photo_classifier/service/PhotoClassifierService.ts'
import { loadRootPathFromBackend } from '@/photo_classifier/config/settings'

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

    function goToBatchSelect() {
      router.push('/photo-classifier/batch-select')
    }

    function nextFile() {
      console.log('[nextFile] Before - currentIndex:', currentIndex.value, 'displayFileList.length:', displayFileList.value.length)
      if (currentIndex.value < displayFileList.value.length - 1) {
        currentIndex.value++
        console.log('[nextFile] After - currentIndex:', currentIndex.value, 'currentFile:', displayFileList.value[currentIndex.value]?.filePath)

        // Debug: Log all files after switching
        console.log('[DefaultGroup] nextFile - After switching to index', currentIndex.value)
        displayFileList.value.forEach((file, index) => {
          console.log(`  [${index}] ${file.filePath} - categoryTag: ${file.categoryTag}, fileStatus: ${file.fileStatus}`)
        })
      } else {
        console.log('[nextFile] Already at last file')
      }
    }

    function prevFile() {
      console.log('[prevFile] Before - currentIndex:', currentIndex.value)
      if (currentIndex.value > 0) {
        currentIndex.value--
        console.log('[prevFile] After - currentIndex:', currentIndex.value, 'currentFile:', displayFileList.value[currentIndex.value]?.filePath)

        // Debug: Log all files after switching
        console.log('[DefaultGroup] prevFile - After switching to index', currentIndex.value)
        displayFileList.value.forEach((file, index) => {
          console.log(`  [${index}] ${file.filePath} - categoryTag: ${file.categoryTag}, fileStatus: ${file.fileStatus}`)
        })
      } else {
        console.log('[prevFile] Already at first file')
      }
    }

    function addToGroup(file: FileModel, index: number) {
      if (!file) return
      photoClassifierStore.addFileToGroup(file, index)
      nextFile()
    }

    const applyGroup = async () => {
      // Collect all files to apply: files from defaultGroup AND all groups
      const allFilesToApply: FileModel[] = []
      const filePathSet = new Set<string>()

      // First, add files from all groups (these have priority as they contain the latest marks)
      photoClassifierStore.groupList.groupList.forEach((group, groupIndex) => {
        group.files.forEach(file => {
          allFilesToApply.push(file)
          filePathSet.add(file.filePath)
        })
      })

      // Then add files from default group that are NOT already in groups
      displayFileList.value.forEach(file => {
        if (!filePathSet.has(file.filePath)) {
          allFilesToApply.push(file)
        }
      })

      // Debug: Log all files and their categoryTags before applying
      console.log('[DefaultGroup] Apply - Files to process:')
      allFilesToApply.forEach((file, index) => {
        console.log(`  [${index}] ${file.filePath} - categoryTag: ${file.categoryTag}`)
      })

      await photoClassifierStore.applyFiles(allFilesToApply)

      // Clear working state after successful apply
      await photoClassifierStore.clearWorkingStateFromBackend()

      // 处理完成后，调整 currentIndex
      if (currentIndex.value >= displayFileList.value.length) {
        currentIndex.value = Math.max(0, displayFileList.value.length - 1)
      }
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

    function handleKeyDown(event: KeyboardEvent) {
      // Ignore repeated key events to prevent duplicate operations
      if (event.repeat) {
        return
      }

      // Cache currentDisplayFile to avoid multiple computed recalculations
      const currentFile = currentDisplayFile.value
      if (!currentFile) {
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
          console.log('[KeyW] Before add - currentFile:', currentFile.filePath, 'currentIndex:', currentIndex.value)
          if (photoClassifierStore.currentGroupIndex >= 0) {
            photoClassifierStore.addFileToGroup(currentFile, photoClassifierStore.currentGroupIndex)
            console.log('[KeyW] After add - fileStatus:', currentFile.fileStatus, 'groupId:', currentFile.groupId)
            nextFile()
            console.log('[KeyW] After nextFile - currentIndex:', currentIndex.value)
          } else {
            ElMessage.warning('No group selected. Press Q to create a new group first.')
          }
          break
        case 'KeyQ':
          // Q: Always create a new group
          console.log('[KeyQ] Before create - currentFile:', currentFile.filePath, 'currentIndex:', currentIndex.value)
          photoClassifierStore.createNewGroupWithFile(currentFile)
          console.log('[KeyQ] After create - fileStatus:', currentFile.fileStatus, 'groupId:', currentFile.groupId)
          nextFile()
          console.log('[KeyQ] After nextFile - currentIndex:', currentIndex.value)
          break
        case 'Backspace':
          currentFile.categoryTag = FileCategory.DEL
          photoClassifierStore.autoSaveWorkingState()
          break
        case 'KeyZ':
          console.log('[DefaultGroup] KeyZ - Setting to BEST:', currentFile.filePath)
          currentFile.categoryTag = FileCategory.BEST
          console.log('[DefaultGroup] KeyZ - New categoryTag:', currentFile.categoryTag)
          photoClassifierStore.autoSaveWorkingState()
          break
        case 'KeyX':
          console.log('[DefaultGroup] KeyX - Setting to BETTER:', currentFile.filePath)
          currentFile.categoryTag = FileCategory.BETTER
          console.log('[DefaultGroup] KeyX - New categoryTag:', currentFile.categoryTag)
          photoClassifierStore.autoSaveWorkingState()
          break
        case 'KeyC':
          console.log('[DefaultGroup] KeyC - Setting to NORMAL:', currentFile.filePath)
          currentFile.categoryTag = FileCategory.NORMAL
          console.log('[DefaultGroup] KeyC - New categoryTag:', currentFile.categoryTag)
          photoClassifierStore.autoSaveWorkingState()
          break
        case 'Enter':
          applyGroup()
          break
      }
    }

    function updateDisplayFiles() {
      console.log('[updateDisplayFiles] START')
      console.log('  showFiltered:', showFiltered.value)
      console.log('  currentIndex before:', currentIndex.value)
      console.log('  defaultGroup.files.length:', photoClassifierStore.defaultGroup.files.length)

      // Try to maintain the current file when switching filter modes
      // IMPORTANT: Must get the file from the ORIGINAL list before displayFileList changes
      // because currentDisplayFile is a computed property based on the new displayFileList
      const currentFile = photoClassifierStore.defaultGroup.files[currentIndex.value]
      const currentFilePath = currentFile?.filePath
      console.log('  currentFile from original list:', currentFilePath)
      console.log('  currentFile.fileStatus:', currentFile?.fileStatus)

      // Reset to beginning if there's no current file
      if (!currentFilePath) {
        console.log('  No current file, reset to 0')
        currentIndex.value = 0
        return
      }

      // Log the new filtered list
      console.log('  displayFileList.length:', displayFileList.value.length)
      displayFileList.value.forEach((f, idx) => {
        console.log(`    [${idx}] ${f.filePath} (status: ${f.fileStatus})`)
      })

      // Find the current file in the new filtered list
      const newIndex = displayFileList.value.findIndex(f => f.filePath === currentFilePath)
      console.log('  newIndex in filtered list:', newIndex)

      if (newIndex >= 0) {
        // Keep the same file if it's still in the filtered list
        console.log('  File found in filtered list, set currentIndex to:', newIndex)
        currentIndex.value = newIndex
      } else {
        // Otherwise, try to stay at a similar position or reset to 0
        const adjustedIndex = Math.min(currentIndex.value, displayFileList.value.length - 1)
        console.log('  File NOT in filtered list, adjust currentIndex from', currentIndex.value, 'to:', adjustedIndex)
        currentIndex.value = adjustedIndex
        if (currentIndex.value < 0) currentIndex.value = 0
      }

      console.log('  currentIndex after:', currentIndex.value)
      console.log('[updateDisplayFiles] END\n')
    }

    function goToGroup(index: number) {
      router.push(`/photo-classifier/group/${index}`)
    }

    function markAllNormal() {
      // Cache displayFileList to avoid multiple computed recalculations
      const fileList = displayFileList.value

      console.log('[DefaultGroup] markAllNormal - Before:')
      fileList.forEach((file, index) => {
        console.log(`  [${index}] ${file.filePath} - categoryTag: ${file.categoryTag}`)
      })

      for (const file of fileList) {
        file.categoryTag = FileCategory.NORMAL
      }

      console.log('[DefaultGroup] markAllNormal - After:')
      fileList.forEach((file, index) => {
        console.log(`  [${index}] ${file.filePath} - categoryTag: ${file.categoryTag}`)
      })

      ElMessage.success('All files marked as Normal')
    }

    onMounted(async () => {
      // Initialize store if not already loaded
      // This ensures the page works even when accessed directly (not from dashboard)
      if (!photoClassifierStore.initialized) {
        await initStore()
      }

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
      goToBatchSelect,
      goToGroup,
      addToGroup,
      updateDisplayFiles,
      applyGroup,
      markAllNormal,
      isEditing,
      editValue,
      applyEdit,
      startEditing,
    }
  },
})
