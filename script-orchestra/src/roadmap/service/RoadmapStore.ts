/**
 * Roadmap Kanban Store
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Task, Column } from '../models/Task'
import { TaskStatus } from '../models/Task'
import * as RoadmapService from './RoadmapService'

export const useRoadmapStore = defineStore('roadmap', () => {
  // State
  const tasks = ref<Task[]>([])
  const loading = ref(false)

  // Mutable columns for draggable
  const columns = computed<Column[]>(() => {
    const todoTasks = tasks.value.filter(t => t.status === TaskStatus.TODO).sort((a, b) => a.order - b.order)
    const inProgressTasks = tasks.value.filter(t => t.status === TaskStatus.IN_PROGRESS).sort((a, b) => a.order - b.order)
    const blockTasks = tasks.value.filter(t => t.status === TaskStatus.BLOCK).sort((a, b) => a.order - b.order)
    const doneTasks = tasks.value.filter(t => t.status === TaskStatus.DONE).sort((a, b) => a.order - b.order)

    return [
      {
        id: TaskStatus.TODO,
        name: 'Todo',
        tasks: todoTasks
      },
      {
        id: TaskStatus.IN_PROGRESS,
        name: 'In Progress',
        tasks: inProgressTasks
      },
      {
        id: TaskStatus.BLOCK,
        name: 'Block',
        tasks: blockTasks
      },
      {
        id: TaskStatus.DONE,
        name: 'Done',
        tasks: doneTasks
      }
    ]
  })

  // Actions
  async function loadTasks() {
    loading.value = true
    try {
      const response = await RoadmapService.getTasks()
      tasks.value = response.tasks
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
      const updatedTask = await RoadmapService.updateTask(taskId, payload)
      const index = tasks.value.findIndex(t => t.id === taskId)
      if (index !== -1) {
        tasks.value[index] = updatedTask
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
    loadTasks,
    createTask,
    updateTask,
    deleteTask,
    reorderTasks,
    updateTaskLocal
  }
})
