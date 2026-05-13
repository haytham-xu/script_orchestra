
import { defineComponent, ref, onMounted, nextTick } from 'vue'
import { useRoadmapStore } from '../service/RoadmapStore'
import { TaskStatus, TaskPriority } from '../models/Task'
import type { Task } from '../models/Task'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import TaskCard from '../components/TaskCard.vue'
import draggable from 'vuedraggable'

export default defineComponent({
  name: 'RoadmapView',
  components: {
    TaskCard,
    draggable,
    Plus
  },
  setup() {
    const store = useRoadmapStore()

    // Inline create form state
    const createFormColumn = ref<TaskStatus | null>(null)
    const contentInput = ref<any>(null)

    // Inline edit state
    const editingTaskId = ref<string | null>(null)
    const editContentInput = ref<any>(null)

    // Form data
    const taskForm = ref({
      content: '',
      priority: TaskPriority.MEDIUM,
      status: TaskStatus.TODO
    })

    // Load tasks on mount
    onMounted(() => {
      store.loadTasks()
    })

    // Open inline create form
    function openCreateForm(status: TaskStatus) {
      createFormColumn.value = status
      taskForm.value = {
        content: '',
        priority: TaskPriority.MEDIUM,
        status: status
      }
      // Focus input after DOM update
      nextTick(() => {
        contentInput.value?.focus()
      })
    }

    // Cancel create
    function cancelCreate() {
      createFormColumn.value = null
      taskForm.value = {
        content: '',
        priority: TaskPriority.MEDIUM,
        status: TaskStatus.TODO
      }
    }

    // Open inline edit
    function openEditForm(task: Task) {
      editingTaskId.value = task.id
      taskForm.value = {
        content: task.content,
        priority: task.priority as TaskPriority,
        status: task.status
      }
      // Focus textarea after DOM update
      nextTick(() => {
        const textarea = editContentInput.value?.$el?.querySelector('textarea')
        if (textarea) {
          textarea.focus()
          // Set cursor to end
          textarea.setSelectionRange(textarea.value.length, textarea.value.length)
        }
      })
    }

    // Cancel edit
    function cancelEdit() {
      editingTaskId.value = null
      taskForm.value = {
        content: '',
        priority: TaskPriority.MEDIUM,
        status: TaskStatus.TODO
      }
    }

    // Save task
    async function saveTask() {
      if (!taskForm.value.content.trim()) {
        ElMessage.warning('Please enter task content')
        return
      }

      try {
        // If createFormColumn is set, we're creating
        if (createFormColumn.value !== null) {
          await store.createTask(taskForm.value)
          ElMessage.success('Task created successfully')
          cancelCreate()
        } else if (editingTaskId.value !== null) {
          // We're editing
          await store.updateTask(editingTaskId.value, taskForm.value)
          ElMessage.success('Task updated successfully')
          cancelEdit()
        }
      } catch (error) {
        ElMessage.error('Operation failed')
      }
    }

    // Handle clicking outside edit/create form
    function handleClickOutside(event: MouseEvent) {
      // Check if we're in edit or create mode
      const isEditMode = editingTaskId.value !== null
      const isCreateMode = createFormColumn.value !== null

      if (!isEditMode && !isCreateMode) {
        return
      }

      // Check if click target is inside forms
      const target = event.target as HTMLElement
      const editForm = target.closest('.inline-edit-form')
      const createForm = target.closest('.inline-create-form')
      const taskContent = target.closest('.task-content')

      // Don't trigger if clicking inside forms or on task content
      if (editForm || createForm || taskContent) {
        return
      }

      // Clicked outside - auto save
      saveTask()
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
      } catch (error) {
        if (error !== 'cancel') {
          ElMessage.error('Delete failed')
        }
      }
    }

    // Handle drag end - use event data to determine what moved
    async function handleDragEnd(evt: any) {
      console.log('[Drag] handleDragEnd called with event:', evt)

      // Get drag details from event
      const { to, from, oldIndex, newIndex, item } = evt
      console.log('[Drag] Old index:', oldIndex, 'New index:', newIndex)

      // Get the task ID from the dragged element
      const taskId = item?.getAttribute('data-task-id')
      console.log('[Drag] Task ID:', taskId)

      // Get column IDs from the container elements
      const fromColumnId = from?.getAttribute('data-column-id')
      const toColumnId = to?.getAttribute('data-column-id')
      console.log('[Drag] From column:', fromColumnId, 'To column:', toColumnId)

      if (!taskId || !toColumnId) {
        console.error('[Drag] Missing required data:', { taskId, toColumnId })
        return
      }

      // Find the task
      const task = store.tasks.find(t => t.id === taskId)
      if (!task) {
        console.error('[Drag] Could not find task with ID:', taskId)
        return
      }

      console.log('[Drag] Moving task:', task.content, 'from', fromColumnId, 'to', toColumnId)

      try {
        // Update task status
        await store.updateTask(taskId, {
          status: toColumnId,
          order: newIndex
        })

        console.log('[Drag] Task moved successfully')
      } catch (error) {
        console.error('[Drag] Failed to move task:', error)
        ElMessage.error('Failed to update task position')
        // Reload to restore correct state
        await store.loadTasks()
      }
    }

    return {
      store,
      createFormColumn,
      editingTaskId,
      contentInput,
      editContentInput,
      taskForm,
      TaskPriority,
      openCreateForm,
      cancelCreate,
      openEditForm,
      cancelEdit,
      saveTask,
      deleteTask,
      handleDragEnd,
      handleClickOutside
    }
  }
})
