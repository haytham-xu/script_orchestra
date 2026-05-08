/**
 * Roadmap HTTP Service
 */
import { getRequest, postRequest, putRequest, deleteRequest } from '@/basic/RequestService'
import type { Task } from '../models/Task'

const BASE_PATH = '/roadmap'

export interface TaskCreatePayload {
  title: string
  description?: string
  priority?: string
  status?: string
}

export interface TaskUpdatePayload {
  title?: string
  description?: string
  priority?: string
  status?: string
  order?: number
}

export interface TaskReorderPayload {
  updates: Array<{
    id: string
    status: string
    order: number
  }>
}

export async function getTasks(): Promise<{ tasks: Task[] }> {
  return getRequest<{ tasks: Task[] }>(`${BASE_PATH}/tasks`)
}

export async function createTask(payload: TaskCreatePayload): Promise<Task> {
  return postRequest(`${BASE_PATH}/tasks`, {}, payload)
}

export async function updateTask(taskId: string, payload: TaskUpdatePayload): Promise<Task> {
  return putRequest<Task>(`${BASE_PATH}/tasks/${taskId}`, {}, payload)
}

export async function deleteTask(taskId: string): Promise<{ message: string }> {
  return deleteRequest<{ message: string }>(`${BASE_PATH}/tasks/${taskId}`)
}

export async function reorderTasks(payload: TaskReorderPayload): Promise<{ tasks: Task[] }> {
  return putRequest<{ tasks: Task[] }>(`${BASE_PATH}/tasks/reorder`, {}, payload)
}
