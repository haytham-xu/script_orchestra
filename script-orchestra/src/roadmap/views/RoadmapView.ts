
import { defineComponent, ref, onMounted, nextTick, watch, computed, onUnmounted } from 'vue'
import { useRoadmapStore, invalidateSettingsCache } from '../service/RoadmapStore'
import { TaskStatus, TaskPriority, TaskSize, TaskCategory } from '../models/Task'
import type { Task } from '../models/Task'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Setting } from '@element-plus/icons-vue'
import TaskCard from '../components/TaskCard.vue'
import draggable from 'vuedraggable'
import { marked } from 'marked'
import * as SettingsService from '../service/SettingsService'
import type { Settings } from '../service/SettingsService'

export default defineComponent({
  name: 'RoadmapView',
  components: {
    TaskCard,
    draggable,
    Plus,
    Setting
  },
  setup() {
    const store = useRoadmapStore()

    // Form state
    const showCreateDialog = ref(false)
    const showEditDialog = ref(false)
    const showDetailDialog = ref(false)
    const showSettingsDrawer = ref(false)
    const detailTask = ref<Task | null>(null)
    const editingTaskId = ref<string | null>(null)
    const shouldSaveOnClose = ref(true)
    const editingCategoryKey = ref<TaskCategory | null>(null)
    const editingCategoryName = ref('')
    const isComposingEdit = ref(false)
    const isSavingCheckbox = ref(false) // Flag to prevent duplicate saves

    // Markdown tab state
    const activeTab = ref('preview')

    // Settings state
    const defaultSettings: Settings = {
      inProgressTimeoutHours: 4,
      doneAutoRemoveDays: null // null means never remove
    }

    const settings = ref<Settings>({ ...defaultSettings })

    // Default category display names (can be customized by user)
    const defaultCategoryNames: Record<TaskCategory, string> = {
      [TaskCategory.A]: '日常工作',
      [TaskCategory.B]: '个人事物',
      [TaskCategory.C]: '高价值',
      [TaskCategory.D]: '支线/弯道'
    }

    // Category names (customizable, stored in localStorage)
    const categoryNames = ref<Record<TaskCategory, string>>({ ...defaultCategoryNames })

    // Load category names from localStorage
    onMounted(async () => {
      store.loadTasks()

      // Load category names
      const savedNames = localStorage.getItem('roadmap_category_names')
      if (savedNames) {
        try {
          const parsed = JSON.parse(savedNames)
          // Merge with defaults to ensure all categories exist
          categoryNames.value = {
            ...defaultCategoryNames,
            ...parsed
          }
        } catch (e) {
          console.error('Failed to load category names:', e)
          categoryNames.value = { ...defaultCategoryNames }
        }
      }

      // Load settings from API
      try {
        const loadedSettings = await SettingsService.getSettings()
        settings.value = loadedSettings
      } catch (e) {
        console.error('Failed to load settings:', e)
        ElMessage.warning('Failed to load settings, using defaults')
        settings.value = { ...defaultSettings }
      }
    })

    // Form data
    const taskForm = ref({
      header: '',
      content: '',
      priority: TaskPriority.MEDIUM,
      status: TaskStatus.TODO,
      size: TaskSize.MEDIUM,
      category: TaskCategory.A
    })
    const taskFormEta = ref<Date | null>(null)
    const taskFormTime = ref<string>('09:00')
    const etaPreset = ref<string>('custom')

    // Handle ETA preset selection
    function handleEtaPresetChange(value: string) {
      etaPreset.value = value  // Update the preset value to reflect UI state
      const now = new Date()

      switch (value) {
        case 'today':
          // Today at 23:59
          taskFormEta.value = new Date(now.getFullYear(), now.getMonth(), now.getDate())
          taskFormTime.value = '23:59'
          break

        case 'tomorrow':
          // Tomorrow at 23:59
          taskFormEta.value = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
          taskFormTime.value = '23:59'
          break

        case 'dayafter':
          // Day after tomorrow at 23:59
          taskFormEta.value = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 2)
          taskFormTime.value = '23:59'
          break

        case 'thisweek':
          // End of this week (Sunday) at 23:59
          const daysUntilSunday = 7 - now.getDay()
          taskFormEta.value = new Date(now.getFullYear(), now.getMonth(), now.getDate() + daysUntilSunday)
          taskFormTime.value = '23:59'
          break

        case 'none':
          // No ETA
          taskFormEta.value = null
          taskFormTime.value = '09:00'
          break

        case 'custom':
          // Keep current values or set defaults
          if (!taskFormEta.value) {
            taskFormEta.value = null
            taskFormTime.value = '09:00'
          }
          break
      }
    }

    // Start editing category name
    function startEditCategory(category: TaskCategory) {
      editingCategoryKey.value = category
      editingCategoryName.value = categoryNames.value[category]
      // Focus input on next tick
      nextTick(() => {
        const inputs = document.querySelectorAll('.category-header-cell input')
        inputs.forEach((input: any) => {
          if (input && input.value === editingCategoryName.value) {
            input.focus()
            input.select()
          }
        })
      })
    }

    // Save category name
    function saveCategoryName() {
      if (editingCategoryKey.value && editingCategoryName.value.trim()) {
        categoryNames.value[editingCategoryKey.value] = editingCategoryName.value.trim()
        localStorage.setItem('roadmap_category_names', JSON.stringify(categoryNames.value))
        ElMessage.success('Category name updated')
      }
      editingCategoryKey.value = null
      editingCategoryName.value = ''
    }

    // Cancel editing category name
    function cancelEditCategory() {
      editingCategoryKey.value = null
      editingCategoryName.value = ''
    }

    // Settings functions
    function openSettings() {
      showSettingsDrawer.value = true
    }

    function closeSettings() {
      showSettingsDrawer.value = false
    }

    async function saveSettings() {
      // Validate settings
      if (settings.value.inProgressTimeoutHours < 0.5) {
        ElMessage.warning('In Progress timeout must be at least 0.5 hours')
        return
      }
      if (settings.value.doneAutoRemoveDays !== null && settings.value.doneAutoRemoveDays < 1) {
        ElMessage.warning('Done auto-remove must be at least 1 day or disabled')
        return
      }

      // Save to database via API
      try {
        await SettingsService.updateSettings(settings.value)
        invalidateSettingsCache() // Invalidate cache so store reloads settings
        ElMessage.success('Settings saved successfully')

        // Reload tasks to apply new filters (especially for done auto-remove)
        await store.loadTasks()

        closeSettings()
      } catch (error) {
        console.error('Failed to save settings:', error)
        ElMessage.error('Failed to save settings')
      }
    }

    async function resetSettings() {
      try {
        settings.value = { ...defaultSettings }
        await SettingsService.updateSettings(settings.value)
        invalidateSettingsCache() // Invalidate cache so store reloads settings
        ElMessage.success('Settings reset to defaults')

        // Reload tasks to apply new filters
        await store.loadTasks()
      } catch (error) {
        console.error('Failed to reset settings:', error)
        ElMessage.error('Failed to reset settings')
      }
    }

    // Open create form
    function openCreateForm(status: TaskStatus, category: TaskCategory) {
      showCreateDialog.value = true
      activeTab.value = 'preview'  // Default to preview tab
      taskForm.value = {
        header: '',
        content: '',
        priority: TaskPriority.MEDIUM,
        status: status,
        size: TaskSize.MEDIUM,
        category: category
      }

      // Default to "今天" (today at 23:59) for new tasks
      const now = new Date()
      taskFormEta.value = new Date(now.getFullYear(), now.getMonth(), now.getDate())
      taskFormTime.value = '23:59'
      etaPreset.value = 'today'
    }

    // Open create form with default values
    function openCreateFormDefault() {
      openCreateForm(TaskStatus.TODO, TaskCategory.A)
    }

    // Cancel create
    function cancelCreate() {
      showCreateDialog.value = false
      taskForm.value = {
        header: '',
        content: '',
        priority: TaskPriority.MEDIUM,
        status: TaskStatus.TODO,
        size: TaskSize.MEDIUM,
        category: TaskCategory.A
      }
      taskFormEta.value = null
      taskFormTime.value = '09:00'
    }

    // Open edit dialog (from Edit button - starts in edit mode)
    function openEditForm(task: Task) {
      console.log('[OpenEdit] Task content (first 100 chars):', task.content.substring(0, 100))

      editingTaskId.value = task.id
      showEditDialog.value = true
      shouldSaveOnClose.value = true
      activeTab.value = 'edit'  // Start in edit tab for Edit button
      taskForm.value = {
        header: task.header,
        content: task.content,
        priority: task.priority as TaskPriority,
        status: task.status,
        size: task.size as TaskSize,
        category: task.category as TaskCategory
      }
      if (task.eta) {
        const etaDate = new Date(task.eta)
        taskFormEta.value = etaDate
        const hours = etaDate.getHours().toString().padStart(2, '0')
        const minutes = etaDate.getMinutes().toString().padStart(2, '0')
        taskFormTime.value = `${hours}:${minutes}`

        // Determine which preset matches (if any)
        etaPreset.value = determineEtaPreset(etaDate, `${hours}:${minutes}`)
      } else {
        taskFormEta.value = null
        taskFormTime.value = '09:00'
        etaPreset.value = 'none'
      }
    }

    // Open preview dialog (from Card click - starts in preview mode)
    function openPreviewForm(task: Task) {
      console.log('[OpenPreview] Task content (first 100 chars):', task.content.substring(0, 100))

      editingTaskId.value = task.id
      showEditDialog.value = true
      shouldSaveOnClose.value = true
      activeTab.value = 'preview'  // Start in preview tab for Card click
      taskForm.value = {
        header: task.header,
        content: task.content,
        priority: task.priority as TaskPriority,
        status: task.status,
        size: task.size as TaskSize,
        category: task.category as TaskCategory
      }
      if (task.eta) {
        const etaDate = new Date(task.eta)
        taskFormEta.value = etaDate
        const hours = etaDate.getHours().toString().padStart(2, '0')
        const minutes = etaDate.getMinutes().toString().padStart(2, '0')
        taskFormTime.value = `${hours}:${minutes}`

        // Determine which preset matches (if any)
        etaPreset.value = determineEtaPreset(etaDate, `${hours}:${minutes}`)
      } else {
        taskFormEta.value = null
        taskFormTime.value = '09:00'
        etaPreset.value = 'none'
      }
    }

    // Determine which ETA preset matches the given date/time
    function determineEtaPreset(date: Date, time: string): string {
      if (time !== '23:59') {
        return 'custom'
      }

      const now = new Date()
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
      const targetDate = new Date(date.getFullYear(), date.getMonth(), date.getDate())
      const diffDays = Math.round((targetDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))

      if (diffDays === 0) return 'today'
      if (diffDays === 1) return 'tomorrow'
      if (diffDays === 2) return 'dayafter'

      // Check if it's end of this week (Sunday)
      const daysUntilSunday = 7 - now.getDay()
      if (diffDays === daysUntilSunday) return 'thisweek'

      return 'custom'
    }

    // Cancel edit
    function cancelEdit() {
      shouldSaveOnClose.value = false
      showEditDialog.value = false
      editingTaskId.value = null
      taskForm.value = {
        header: '',
        content: '',
        priority: TaskPriority.MEDIUM,
        status: TaskStatus.TODO,
        size: TaskSize.MEDIUM,
        category: TaskCategory.A
      }
      taskFormEta.value = null
      taskFormTime.value = '09:00'
    }

    // Save task
    async function saveTask() {
      if (!taskForm.value.header.trim()) {
        ElMessage.warning('Please enter task header')
        return
      }

      try {
        // Combine date and time
        let etaISO = null
        if (taskFormEta.value && taskFormTime.value) {
          const date = new Date(taskFormEta.value)
          const [hours, minutes] = taskFormTime.value.split(':')
          date.setHours(parseInt(hours), parseInt(minutes), 0, 0)
          etaISO = date.toISOString()
        }

        const payload: any = {
          header: taskForm.value.header,
          content: taskForm.value.content,
          priority: taskForm.value.priority,
          size: taskForm.value.size,
          category: taskForm.value.category,
          eta: etaISO
        }

        // If showCreateDialog is true, we're creating
        if (showCreateDialog.value) {
          payload.status = taskForm.value.status
          await store.createTask(payload)
          ElMessage.success('Task created successfully')
          cancelCreate()
        } else if (showEditDialog.value) {
          // We're editing
          shouldSaveOnClose.value = false
          await store.updateTask(editingTaskId.value!, payload)
          ElMessage.success('Task updated successfully')
          cancelEdit()
        }
      } catch (error) {
        ElMessage.error('Operation failed')
      }
    }

    // Handle composition events for IME (Input Method Editor)
    function handleCompositionStart(isCreate: boolean) {
      if (!isCreate) {
        isComposingEdit.value = true
      }
    }

    function handleCompositionEnd(isCreate: boolean) {
      if (!isCreate) {
        isComposingEdit.value = false
      }
    }

    // Handle Enter key press
    function handleEnterKey(event: KeyboardEvent, isCreate: boolean) {
      const isComposing = !isCreate ? isComposingEdit.value : false

      // If IME is composing OR event.isComposing is true, don't save
      if (isComposing || event.isComposing) {
        return // Let the IME handle it
      }

      // Not composing - treat Enter as save
      event.preventDefault()
      saveTask()
    }

    // Handle clicking outside edit/create form
    function handleClickOutside(event: MouseEvent) {
      // No longer needed for inline editing
      return
    }

    // Delete task
    async function deleteTask(taskId: string) {
      try {
        await ElMessageBox.confirm('Are you sure to delete this task?', 'Warning', {
          confirmButtonText: 'OK',
          cancelButtonText: 'Cancel',
          type: 'warning'
        })

        await store.deleteTask(taskId)
        ElMessage.success('Task deleted successfully')

        // Close edit dialog if it's open
        if (showEditDialog.value) {
          cancelEdit()
        }
      } catch (error) {
        if (error !== 'cancel') {
          ElMessage.error('Delete failed')
        }
      }
    }

    // Handle delete from edit dialog
    function handleDeleteInEdit() {
      if (editingTaskId.value) {
        deleteTask(editingTaskId.value)
      }
    }

    // Extend In Progress time by 30 minutes
    async function extendInProgressTime(taskId: string) {
      const task = store.tasks.find(t => t.id === taskId)
      if (!task || !task.inProgressAt) {
        console.error('[ExtendTime] Task not found or not in progress:', taskId)
        return
      }

      try {
        // Move inProgressAt forward by 30 minutes (which increases the remaining time)
        const currentInProgressAt = new Date(task.inProgressAt)
        const newInProgressAt = new Date(currentInProgressAt.getTime() + 30 * 60 * 1000)

        await store.updateTask(taskId, {
          inProgressAt: newInProgressAt.toISOString()
        })

        await store.loadTasks()
        ElMessage.success('已增加30分钟')
      } catch (error) {
        console.error('[ExtendTime] Failed to extend time:', error)
        ElMessage.error('延长时间失败')
      }
    }

    // Handle drag change
    async function handleDragChange(evt: any, targetStatus: TaskStatus, targetCategory: TaskCategory | null) {
      const moved = evt.moved
      const added = evt.added
      const removed = evt.removed

      if (!moved && !added && !removed) {
        return
      }

      try {
        // Case 1: Task moved within the same list (e.g., reordering in In Progress)
        if (moved) {
          const task = moved.element
          const newIndex = moved.newIndex
          const oldIndex = moved.oldIndex

          // Determine which list we're in based on task status
          let tasksInList: Task[] = []
          if (task.status === TaskStatus.IN_PROGRESS) {
            tasksInList = [...store.inProgressTasks]
          } else if (task.status === TaskStatus.DONE) {
            tasksInList = [...store.doneTasks]
          } else {
            tasksInList = [...store.getBlockTasks(task.category)]
          }

          // Manually simulate the move to get the new order
          const movedTask = tasksInList[oldIndex]
          tasksInList.splice(oldIndex, 1)
          tasksInList.splice(newIndex, 0, movedTask)

          // For In Progress, use the list order directly
          if (task.status === TaskStatus.IN_PROGRESS) {
            const updates = tasksInList.map((t, index) => ({
              id: t.id,
              status: TaskStatus.IN_PROGRESS,
              order: index
            }))

            await store.reorderTasks(updates)
            await store.loadTasks()
          } else {
            // For blocks and done, restore original order for now
            await store.loadTasks()
          }
        }

        // Case 2: Task added from another list (cross-list drag)
        else if (added) {
          const task = added.element

          // Update task with new status/category
          const updates: any = {}
          if (targetStatus !== task.status) {
            updates.status = targetStatus
          }
          if (targetCategory && targetCategory !== task.category) {
            updates.category = targetCategory
          }

          if (Object.keys(updates).length > 0) {
            await store.updateTask(task.id, updates)
          }
          await store.loadTasks()
        }
      } catch (error) {
        console.error('[Drag] Error:', error)
        ElMessage.error('Failed to update task position')
        await store.loadTasks()
      }
    }

    // Show task detail in dialog
    function showTaskDetail(task: Task) {
      detailTask.value = task
      showDetailDialog.value = true
    }

    // Close detail dialog
    function closeDetail() {
      showDetailDialog.value = false
      detailTask.value = null
    }

    // Edit from detail dialog
    function editFromDetail() {
      if (detailTask.value) {
        openEditForm(detailTask.value)
        closeDetail()
      }
    }

    // Get priority tag type
    function getPriorityTagType(priority: string) {
      switch (priority) {
        case TaskPriority.HIGH:
          return 'danger'
        case TaskPriority.MEDIUM:
          return 'warning'
        case TaskPriority.LOW:
          return 'info'
        default:
          return ''
      }
    }

    // Format ETA for detail dialog
    function formatDetailETA(dateStr: string): string {
      const date = new Date(dateStr)
      return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      })
    }

    // Render markdown for detail dialog
    function renderMarkdown(content: string): string {
      if (!content) return ''

      try {
        // Parse markdown with support for task lists (checkboxes)
        let html = marked.parse(content) as string

        // Convert GitHub-style checkboxes to HTML checkboxes
        html = html.replace(/\[ \]/g, '<input type="checkbox" disabled>')
        html = html.replace(/\[x\]/gi, '<input type="checkbox" checked disabled>')

        return html
      } catch (error) {
        console.error('Markdown parsing error:', error)
        return content
      }
    }

    // Handle edit dialog close
    async function handleEditDialogClose() {
      console.log('[DialogClose] shouldSaveOnClose:', shouldSaveOnClose.value, 'hasHeader:', !!taskForm.value.header.trim())

      if (shouldSaveOnClose.value && taskForm.value.header.trim()) {
        // Auto save when closing by clicking outside
        console.log('[DialogClose] 💾 Saving task...')
        try {
          // Combine date and time
          let etaISO = null
          if (taskFormEta.value && taskFormTime.value) {
            const date = new Date(taskFormEta.value)
            const [hours, minutes] = taskFormTime.value.split(':')
            date.setHours(parseInt(hours), parseInt(minutes), 0, 0)
            etaISO = date.toISOString()
          }

          const payload: any = {
            header: taskForm.value.header,
            content: taskForm.value.content,
            priority: taskForm.value.priority,
            size: taskForm.value.size,
            category: taskForm.value.category,
            eta: etaISO
          }

          console.log('[DialogClose] Payload content (first 100 chars):', payload.content.substring(0, 100))

          await store.updateTask(editingTaskId.value!, payload)
          console.log('[DialogClose] ✅ Save successful')
          ElMessage.success('Task saved successfully')
        } catch (error) {
          console.error('[DialogClose] ❌ Save failed:', error)
          ElMessage.error('Save failed')
        }
      } else {
        console.log('[DialogClose] Skipping save')
      }
      // Reset form
      editingTaskId.value = null
      taskForm.value = {
        header: '',
        content: '',
        priority: TaskPriority.MEDIUM,
        status: TaskStatus.TODO,
        size: TaskSize.MEDIUM,
        category: TaskCategory.A
      }
      taskFormEta.value = null
      taskFormTime.value = '09:00'
      shouldSaveOnClose.value = true
    }

    // Configure marked options for GitHub-flavored markdown with checkboxes
    marked.setOptions({
      gfm: true,
      breaks: true
    })

    // Handle checkbox click in preview
    async function handleCheckboxClick(event: Event) {
      const target = event.target as HTMLInputElement

      if (target.type !== 'checkbox') {
        return
      }

      // Don't prevent default - let the checkbox toggle naturally
      event.stopPropagation() // But stop propagation to prevent other handlers

      // The checkbox has already been toggled by the browser's default behavior
      const isNowChecked = target.checked

      // Find the checkbox index
      const previewDiv = target.closest('.markdown-preview')
      if (!previewDiv) {
        return
      }

      const allCheckboxes = Array.from(previewDiv.querySelectorAll('input[type="checkbox"]'))
      const checkboxIndex = allCheckboxes.indexOf(target)

      if (checkboxIndex === -1) return

      // Update the markdown content to match the new checkbox state
      const content = taskForm.value.content
      const lines = content.split('\n')
      let currentCheckboxIndex = 0

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i]
        // Match checkbox patterns:
        // 1. With list markers: - [ ] or - [x] or - [X]
        // 2. Without list markers: [ ] or [x] or [X] at start of line
        const uncheckedWithMarker = line.match(/^(\s*[-*+]\s+)\[ \](.*)$/)
        const checkedWithMarker = line.match(/^(\s*[-*+]\s+)\[x\](.*)$/i)
        const uncheckedNoMarker = line.match(/^(\s*)\[ \](.*)$/)
        const checkedNoMarker = line.match(/^(\s*)\[x\](.*)$/i)

        // Try matching with marker first, then without marker
        const uncheckedMatch = uncheckedWithMarker || uncheckedNoMarker
        const checkedMatch = checkedWithMarker || checkedNoMarker

        if (uncheckedMatch || checkedMatch) {
          if (currentCheckboxIndex === checkboxIndex) {
            console.log('[Checkbox] Found matching line at index', i, ':', line)
            // Update to match the checkbox's current state
            if (isNowChecked) {
              // Make it checked in markdown
              if (uncheckedMatch) {
                lines[i] = uncheckedMatch[1] + '[x]' + uncheckedMatch[2]
                console.log('[Checkbox] Changed to:', lines[i])
              } else if (checkedMatch) {
                // Already checked, keep it
                lines[i] = checkedMatch[1] + '[x]' + checkedMatch[2]
              }
            } else {
              // Make it unchecked in markdown
              if (checkedMatch) {
                lines[i] = checkedMatch[1] + '[ ]' + checkedMatch[2]
                console.log('[Checkbox] Changed to:', lines[i])
              } else if (uncheckedMatch) {
                // Already unchecked, keep it
                lines[i] = uncheckedMatch[1] + '[ ]' + uncheckedMatch[2]
              }
            }
            break
          }
          currentCheckboxIndex++
        }
      }

      taskForm.value.content = lines.join('\n')
      console.log('[Checkbox] ✅ Updated content (first 100 chars):', taskForm.value.content.substring(0, 100))
    }

    // Setup event listeners for dynamically generated checkboxes
    function setupCheckboxListeners() {
      // Use setTimeout to ensure DOM is fully rendered
      setTimeout(() => {
        const previewDivs = document.querySelectorAll('.markdown-preview')

        previewDivs.forEach((div) => {
          // Find all checkboxes within this preview div
          const checkboxes = div.querySelectorAll('input[type="checkbox"]')

          checkboxes.forEach((checkbox) => {
            // Remove existing listener if any
            checkbox.removeEventListener('click', handleCheckboxClick as EventListener)

            // Add click listener (use capture phase to ensure we catch it first)
            checkbox.addEventListener('click', handleCheckboxClick as EventListener, true)
          })
        })
      }, 100)
    }

    // Watch for tab changes and dialog state to setup listeners
    watch([activeTab, showEditDialog, showCreateDialog], () => {
      if ((showEditDialog.value || showCreateDialog.value) && activeTab.value === 'preview') {
        setupCheckboxListeners()
      }
    })

    // Cleanup on unmount
    onUnmounted(() => {
      const previewDivs = document.querySelectorAll('.markdown-preview')
      previewDivs.forEach((div) => {
        const checkboxes = div.querySelectorAll('input[type="checkbox"]')
        checkboxes.forEach((checkbox) => {
          checkbox.removeEventListener('click', handleCheckboxClick as EventListener)
          checkbox.removeEventListener('change', handleCheckboxClick as EventListener)
        })
      })
    })

    // Markdown rendering
    const renderedMarkdown = computed(() => {
      if (!taskForm.value.content) return '<p class="empty-preview">No content to preview</p>'

      try {
        // Parse markdown with support for task lists (checkboxes)
        let html = marked.parse(taskForm.value.content) as string

        // Remove disabled attribute from checkboxes (marked adds it by default with GFM)
        html = html.replace(/<input([^>]*?)disabled([^>]*?)>/gi, '<input$1$2>')

        // Convert GitHub-style checkboxes to HTML checkboxes (clickable, with data-index)
        let checkboxIndex = 0
        html = html.replace(/\[ \]/g, () => {
          return `<input type="checkbox" data-index="${checkboxIndex++}" class="markdown-checkbox">`
        })
        html = html.replace(/\[x\]/gi, () => {
          return `<input type="checkbox" checked data-index="${checkboxIndex++}" class="markdown-checkbox">`
        })

        // Setup listeners after render
        nextTick(() => {
          setupCheckboxListeners()
        })

        return html
      } catch (error) {
        console.error('Markdown parsing error:', error)
        return '<p class="error-preview">Error parsing markdown</p>'
      }
    })

    return {
      store,
      showCreateDialog,
      showEditDialog,
      showDetailDialog,
      detailTask,
      editingTaskId,
      taskForm,
      taskFormEta,
      taskFormTime,
      etaPreset,
      handleEtaPresetChange,
      TaskPriority,
      TaskSize,
      TaskStatus,
      TaskCategory,
      Plus,
      Setting,
      openCreateForm,
      openCreateFormDefault,
      cancelCreate,
      openEditForm,
      openPreviewForm,
      cancelEdit,
      saveTask,
      deleteTask,
      handleDeleteInEdit,
      extendInProgressTime,
      handleDragChange,
      handleClickOutside,
      handleCompositionStart,
      handleCompositionEnd,
      handleEnterKey,
      showTaskDetail,
      closeDetail,
      editFromDetail,
      getPriorityTagType,
      formatDetailETA,
      handleEditDialogClose,
      categoryNames,
      editingCategoryKey,
      editingCategoryName,
      startEditCategory,
      saveCategoryName,
      cancelEditCategory,
      activeTab,
      renderedMarkdown,
      renderMarkdown,
      handleCheckboxClick,
      showSettingsDrawer,
      settings,
      openSettings,
      closeSettings,
      saveSettings,
      resetSettings
    }
  }
})
