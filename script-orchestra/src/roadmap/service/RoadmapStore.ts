/**
 * Roadmap Kanban Store
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Task, Column } from '../models/Task'
import { TaskStatus, TaskCategory } from '../models/Task'
import * as RoadmapService from './RoadmapService'
import * as SettingsService from './SettingsService'

// Cache for settings
let settingsCache: { inProgressTimeoutHours: number; doneAutoRemoveDays: number | null } | null = null

// Load settings from API (with caching)
async function loadSettings() {
  if (!settingsCache) {
    try {
      settingsCache = await SettingsService.getSettings()
    } catch (e) {
      console.error('Failed to load settings:', e)
      settingsCache = { inProgressTimeoutHours: 4, doneAutoRemoveDays: null }
    }
  }
  return settingsCache
}

// Invalidate cache when settings change
export function invalidateSettingsCache() {
  settingsCache = null
}

function getInProgressTimeout(): number {
  if (settingsCache) {
    return settingsCache.inProgressTimeoutHours * 60 * 60 * 1000
  }
  return 4 * 60 * 60 * 1000 // Default: 4 hours
}

function getDoneAutoRemoveDays(): number | null {
  if (settingsCache) {
    return settingsCache.doneAutoRemoveDays
  }
  return null // Default: never remove
}

export const useRoadmapStore = defineStore('roadmap', () => {
  // State
  const tasks = ref<Task[]>([])
  const loading = ref(false)
  const inProgressTimers = ref<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  // Today tasks - tasks with ETA today or overdue
  const todayTasks = computed<Task[]>(() => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const tomorrow = new Date(today)
    tomorrow.setDate(tomorrow.getDate() + 1)

    return tasks.value.filter(task => {
      if (!task.eta) return false
      const eta = new Date(task.eta)
      // Include tasks with ETA today or in the past
      return eta < tomorrow
    }).sort((a, b) => a.order - b.order)
  })

  // Category-based columns
  const categoryColumns = computed(() => {
    const categories = [
      TaskCategory.A,
      TaskCategory.B,
      TaskCategory.C,
      TaskCategory.D
    ]

    return categories.map(category => {
      const categoryTasks = tasks.value.filter(t => t.category === category)

      return {
        category,
        todoTasks: categoryTasks.filter(t => t.status === TaskStatus.TODO).sort((a, b) => a.order - b.order),
        blockTasks: categoryTasks.filter(t => t.status === TaskStatus.BLOCK).sort((a, b) => a.order - b.order)
      }
    })
  })

  // In Progress tasks (all categories)
  const inProgressTasks = computed<Task[]>(() => {
    return tasks.value.filter(t => t.status === TaskStatus.IN_PROGRESS).sort((a, b) => a.order - b.order)
  })

  // Done tasks (with auto-remove filter)
  const doneTasks = computed<Task[]>(() => {
    let filtered = tasks.value.filter(t => t.status === TaskStatus.DONE)

    // Apply auto-remove filter if configured
    const autoRemoveDays = getDoneAutoRemoveDays()
    if (autoRemoveDays !== null && autoRemoveDays > 0) {
      const cutoffTime = Date.now() - (autoRemoveDays * 24 * 60 * 60 * 1000)
      filtered = filtered.filter(task => {
        if (!task.doneAt) return true // Keep tasks without doneAt timestamp
        const doneTime = new Date(task.doneAt).getTime()
        return doneTime > cutoffTime
      })
    }

    return filtered.sort((a, b) => a.order - b.order)
  })

  // Legacy columns for backward compatibility
  const columns = computed<Column[]>(() => {
    const todoTasks = tasks.value.filter(t => t.status === TaskStatus.TODO).sort((a, b) => a.order - b.order)
    const inProgressTasksList = tasks.value.filter(t => t.status === TaskStatus.IN_PROGRESS).sort((a, b) => a.order - b.order)
    const blockTasks = tasks.value.filter(t => t.status === TaskStatus.BLOCK).sort((a, b) => a.order - b.order)
    const doneTasksList = tasks.value.filter(t => t.status === TaskStatus.DONE).sort((a, b) => a.order - b.order)

    return [
      {
        id: TaskStatus.TODO,
        name: 'Todo',
        tasks: todoTasks
      },
      {
        id: TaskStatus.IN_PROGRESS,
        name: 'In Progress',
        tasks: inProgressTasksList
      },
      {
        id: TaskStatus.BLOCK,
        name: 'Block',
        tasks: blockTasks
      },
      {
        id: TaskStatus.DONE,
        name: 'Done',
        tasks: doneTasksList
      }
    ]
  })

  function getBlockTasks(category: TaskCategory): Task[] {
    return tasks.value
      .filter((t) => t.status === TaskStatus.BLOCK && t.category === category)
      .sort((a, b) => a.order - b.order)
  }

  // Start timer for task in In Progress
  function startInProgressTimer(taskId: string) {
    // Clear existing timer if any
    if (inProgressTimers.value.has(taskId)) {
      clearTimeout(inProgressTimers.value.get(taskId)!)
    }

    // Set new timer
    const timeout = getInProgressTimeout()
    const timer = setTimeout(async () => {
      console.log(`[InProgressTimer] Task ${taskId} timeout - moving back to TODO`)
      try {
        await updateTask(taskId, {
          status: TaskStatus.TODO,
          returnedFromInProgress: true
        })
        inProgressTimers.value.delete(taskId)
      } catch (error) {
        console.error('[InProgressTimer] Failed to move task back to TODO:', error)
      }
    }, timeout)

    inProgressTimers.value.set(taskId, timer)
  }

  // Clear timer for task
  function clearInProgressTimer(taskId: string) {
    if (inProgressTimers.value.has(taskId)) {
      clearTimeout(inProgressTimers.value.get(taskId)!)
      inProgressTimers.value.delete(taskId)
    }
  }

  // Actions
  async function loadTasks() {
    loading.value = true
    try {
      // Load settings first
      await loadSettings()

      const response = await RoadmapService.getTasks()
      tasks.value = response.tasks

      // Restart timers for tasks in In Progress
      const timeout = getInProgressTimeout()
      for (const task of tasks.value) {
        if (task.status === TaskStatus.IN_PROGRESS && task.inProgressAt) {
          const inProgressAt = new Date(task.inProgressAt)
          const elapsed = Date.now() - inProgressAt.getTime()

          if (elapsed < timeout) {
            // Start timer with remaining time
            const remainingTime = timeout - elapsed
            const timer = setTimeout(async () => {
              console.log(`[InProgressTimer] Task ${task.id} timeout - moving back to TODO`)
              try {
                await updateTask(task.id, {
                  status: TaskStatus.TODO,
                  returnedFromInProgress: true
                })
                inProgressTimers.value.delete(task.id)
              } catch (error) {
                console.error('[InProgressTimer] Failed to move task back to TODO:', error)
              }
            }, remainingTime)

            inProgressTimers.value.set(task.id, timer)
          } else {
            // Already timed out, move back to TODO
            await updateTask(task.id, {
              status: TaskStatus.TODO,
              returnedFromInProgress: true
            })
          }
        }
      }
    } catch (error) {
      console.error('Failed to load tasks:', error)
    } finally {
      loading.value = false
    }
  }

  async function createTask(payload: RoadmapService.TaskCreatePayload) {
    loading.value = true
    try {
      const newTask = await RoadmapService.createTask(payload)
      tasks.value.push(newTask)
      return newTask
    } catch (error) {
      console.error('Failed to create task:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function updateTask(taskId: string, payload: RoadmapService.TaskUpdatePayload) {
    loading.value = true
    try {
      const task = tasks.value.find(t => t.id === taskId)
      const oldStatus = task?.status

      const updatedTask = await RoadmapService.updateTask(taskId, payload)
      const index = tasks.value.findIndex(t => t.id === taskId)
      if (index !== -1) {
        tasks.value[index] = updatedTask
      }

      // Handle In Progress timer
      if (payload.status === TaskStatus.IN_PROGRESS && oldStatus !== TaskStatus.IN_PROGRESS) {
        startInProgressTimer(taskId)
      } else if (payload.status && payload.status !== TaskStatus.IN_PROGRESS) {
        clearInProgressTimer(taskId)
      }

      return updatedTask
    } catch (error) {
      console.error('Failed to update task:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function deleteTask(taskId: string) {
    loading.value = true
    try {
      await RoadmapService.deleteTask(taskId)
      tasks.value = tasks.value.filter(t => t.id !== taskId)
      clearInProgressTimer(taskId)
    } catch (error) {
      console.error('Failed to delete task:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function reorderTasks(updates: Array<{ id: string; status: string; order: number }>) {
    console.log('[Store] reorderTasks called with', updates.length, 'updates')
    try {
      const response = await RoadmapService.reorderTasks({ updates })
      console.log('[Store] Backend response:', response)

      // Handle In Progress timers for status changes
      updates.forEach(update => {
        const task = tasks.value.find(t => t.id === update.id)
        const oldStatus = task?.status

        if (update.status === TaskStatus.IN_PROGRESS && oldStatus !== TaskStatus.IN_PROGRESS) {
          startInProgressTimer(update.id)
        } else if (update.status !== TaskStatus.IN_PROGRESS && oldStatus === TaskStatus.IN_PROGRESS) {
          clearInProgressTimer(update.id)
        }
      })

      tasks.value = response.tasks
      console.log('[Store] Tasks updated, new count:', tasks.value.length)
    } catch (error) {
      console.error('[Store] Failed to reorder tasks:', error)
      // Reload tasks on error to restore correct state
      await loadTasks()
      throw error
    }
  }

  // Update task status and order locally (optimistic update)
  function updateTaskLocal(taskId: string, status: TaskStatus, order: number) {
    const task = tasks.value.find(t => t.id === taskId)
    if (task) {
      task.status = status
      task.order = order
    }
  }

  return {
    tasks,
    loading,
    columns,
    todayTasks,
    categoryColumns,
    inProgressTasks,
    doneTasks,
    getBlockTasks,
    loadTasks,
    createTask,
    updateTask,
    deleteTask,
    reorderTasks,
    updateTaskLocal
  }
})
