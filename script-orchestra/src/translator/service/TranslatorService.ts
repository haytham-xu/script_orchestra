import { getRequest, postRequest, putRequest, deleteRequest } from '@/basic/RequestService'
import { TRANSLATOR_ENDPOINT } from '@/basic/Constants'
import type {
  Zh2EnResult, En2ZhResult, TranslationHistory, TranslatorSettings, ModelInfo, UsageSummary,
} from './Model'

const B = TRANSLATOR_ENDPOINT

// Scene 1: zh→en (Slack-style + back-translation + English learning points).
// `model` optionally overrides the scene's saved default for this request.
// `jobId` correlates the request with streaming progress events over Socket.IO.
// `extraPrompt` is a one-off instruction appended to the system prompt for this request only.
export async function zh2en(text: string, model?: string, jobId?: string, extraPrompt?: string): Promise<Zh2EnResult> {
  return await postRequest(`${B}/zh2en`, {}, {
    text,
    ...(model ? { model } : {}),
    ...(jobId ? { job_id: jobId } : {}),
    ...(extraPrompt ? { extra_prompt: extraPrompt } : {}),
  }) as Zh2EnResult
}

// Scene 2: en→zh (faithful objective translation).
export async function en2zh(text: string, model?: string, jobId?: string, extraPrompt?: string): Promise<En2ZhResult> {
  return await postRequest(`${B}/en2zh`, {}, {
    text,
    ...(model ? { model } : {}),
    ...(jobId ? { job_id: jobId } : {}),
    ...(extraPrompt ? { extra_prompt: extraPrompt } : {}),
  }) as En2ZhResult
}

// History, optionally filtered by scene (newest first).
export async function getHistory(scene?: 'zh2en' | 'en2zh'): Promise<TranslationHistory[]> {
  const params = scene ? { scene } : {}
  return (await getRequest<{ history: TranslationHistory[] }>(`${B}/history`, params)).history
}

// One-click cleanup: delete ALL history older than `days` (both scenes).
export async function cleanup(days?: number): Promise<{ deleted: number; days: number }> {
  const params = days != null ? { days } : {}
  return await deleteRequest<{ deleted: number; days: number }>(`${B}/history`, params)
}

export async function getModels(): Promise<ModelInfo[]> {
  return (await getRequest<{ models: ModelInfo[] }>(`${B}/models`)).models
}

// Cumulative usage across history, optionally scoped to one scene.
export async function getUsageSummary(scene?: 'zh2en' | 'en2zh'): Promise<UsageSummary> {
  const params = scene ? { scene } : {}
  return await getRequest<UsageSummary>(`${B}/usage/summary`, params)
}

export async function getSettings(): Promise<TranslatorSettings> {
  return await getRequest<TranslatorSettings>(`${B}/settings`)
}

export async function updateSettings(patch: Partial<TranslatorSettings>): Promise<TranslatorSettings> {
  return await putRequest<TranslatorSettings>(`${B}/settings`, {}, patch)
}
