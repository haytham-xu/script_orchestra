
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
    const titleInput = ref<any>(null)

    // Inline edit state
    const editingTaskId = ref<string | null>(null)

    // Form data
    const taskForm = ref({
      title: '',
      description: '',
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
        title: '',
        description: '',
        priority: TaskPriority.MEDIUM,
        status: status
      }
      // Focus input after DOM update
      nextTick(() => {
        titleInput.value?.focus()
      })
    }

    // Cancel create
    function cancelCreate() {
      createFormColumn.value = null
      taskForm.value = {
        title: '',
        description: '',
        priority: TaskPriority.MEDIUM,
        status: TaskStatus.TODO
      }
    }

    // Open inline edit
    function openEditForm(task: Task) {
      editingTaskId.value = task.id
      taskForm.value = {
        title: task.title,
        description: task.description,
        priority: task.priority as TaskPriority,
        status: task.status
      }
    }

    // Cancel edit
    function cancelEdit() {
      editingTaskId.value = null
      taskForm.value = {
        title: '',
        description: '',
        priority: TaskPriority.MEDIUM,
        status: TaskStatus.TODO
      }
    }

    // Save task
    async function saveTask() {
      if (!taskForm.value.title.trim()) {
        ElMessage.warning('Please enter task title')
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

      console.log('[Drag] Moving task:', task.title, 'from', fromColumnId, 'to', toColumnId)

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
      titleInput,
      taskForm,
      TaskPriority,
      openCreateForm,
      cancelCreate,
      openEditForm,
      cancelEdit,
      saveTask,
      deleteTask,
      handleDragEnd
    }
  }
})
