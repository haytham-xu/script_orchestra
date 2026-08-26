import { getRequest, postRequest, putRequest, deleteRequest } from '@/basic/RequestService'
import { BROWSER_AGENT_ENDPOINT } from '@/basic/Constants'
import type { BrowserTask, BrowserAgentSettings } from './Model'

export async function getTasks(): Promise<BrowserTask[]> {
  const res = await getRequest<{ tasks: BrowserTask[] }>(`${BROWSER_AGENT_ENDPOINT}/tasks`)
  return res.tasks
}

export async function retryTask(id: number) {
  return postRequest(`${BROWSER_AGENT_ENDPOINT}/tasks/${id}/retry`, {}, {})
}

export async function deleteTask(id: number) {
  return deleteRequest(`${BROWSER_AGENT_ENDPOINT}/tasks/${id}`)
}

export async function getSettings(): Promise<BrowserAgentSettings> {
  const res = await getRequest<{ settings: BrowserAgentSettings }>(
    `${BROWSER_AGENT_ENDPOINT}/settings`)
  return res.settings
}

export async function updateSettings(
  patch: Partial<BrowserAgentSettings>,
): Promise<BrowserAgentSettings> {
  const res = await putRequest<{ settings: BrowserAgentSettings }>(
    `${BROWSER_AGENT_ENDPOINT}/settings`, {}, patch)
  return res.settings
}
