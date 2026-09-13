import { getRequest, postRequest, putRequest, deleteRequest } from '@/basic/RequestService'
import { APPRENTICE_ENDPOINT } from '@/basic/Constants'
import type {
  Task, MemoryShortEntry, HumanMessage, RedLine, ApprenticeSettings
} from './Model'

const BASE = APPRENTICE_ENDPOINT

export const ApprenticeService = {
  // Tasks
  listTasks: () => getRequest<{ tasks: Task[] }>(`${BASE}/tasks`),
  getTask: (id: number) => getRequest<Task>(`${BASE}/tasks/${id}`),
  createTask: (data: { title: string; description: string; repo_path: string }) =>
    postRequest<Task>(`${BASE}/tasks`, data),
  startTask: (id: number) => postRequest<Task>(`${BASE}/tasks/${id}/start`, {}),
  stopTask: (id: number) => postRequest<{ status: string }>(`${BASE}/tasks/${id}/stop`, {}),

  // Human channel
  listMessages: (taskId: number) =>
    getRequest<{ messages: HumanMessage[] }>(`${BASE}/tasks/${taskId}/messages`),
  sendMessage: (taskId: number, content: string) =>
    postRequest<HumanMessage>(`${BASE}/tasks/${taskId}/messages`, { content }),

  // Memory
  listShortMemory: () => getRequest<{ entries: MemoryShortEntry[] }>(`${BASE}/memory/short`),
  getLongMemory: () => getRequest<{ content: string }>(`${BASE}/memory/long`),
  distill: () => postRequest<{ content: string }>(`${BASE}/memory/distill`, {}),
  submitFeedback: (entryId: number, score: number | null, note: string) =>
    postRequest(`${BASE}/memory/short/${entryId}/feedback`, { score, note }),

  // Red lines
  listRedLines: () => getRequest<{ red_lines: RedLine[] }>(`${BASE}/red-lines`),
  addRedLine: (rule: string) => postRequest<RedLine>(`${BASE}/red-lines`, { rule }),
  deleteRedLine: (id: number) => deleteRequest(`${BASE}/red-lines/${id}`),

  // Settings
  getSettings: () => getRequest<ApprenticeSettings>(`${BASE}/settings`),
  saveSettings: (data: Partial<ApprenticeSettings>) =>
    putRequest<ApprenticeSettings>(`${BASE}/settings`, data),
}
