import { getRequest, postRequest, putRequest, deleteRequest } from '@/basic/RequestService'
import { FILE_PIPELINE_ENDPOINT } from '@/basic/Constants'

const B = FILE_PIPELINE_ENDPOINT

export interface Tool {
  id: number
  name: string
  exe_path: string
  args_template: string
}

export interface Pipeline {
  id: number
  name: string
  steps?: string
}

export interface RunConfig {
  folder_path?: string
  output_path?: string
  [key: string]: string | undefined
}

export interface ProgressEvent {
  run_id: string
  pipeline_id: number
  phase: 'start' | 'file_start' | 'file_done' | 'done' | 'error'
  done: number
  total: number
  file: string
  results: RunResult[]
}

export interface RunResult {
  file: string
  steps_taken: string[]
  status: string
  error: string
}

export async function getTools(): Promise<Tool[]> {
  const r = await getRequest(`${B}/tools`) as any
  return r.tools
}

export async function addTool(t: Omit<Tool, 'id'>): Promise<number> {
  const r = await postRequest(`${B}/tools`, {}, t) as any
  return r.id
}

export async function updateTool(id: number, t: Omit<Tool, 'id'>): Promise<void> {
  await putRequest(`${B}/tools/${id}`, {}, t)
}

export async function deleteTool(id: number): Promise<void> {
  await deleteRequest(`${B}/tools/${id}`)
}

export async function getPipelines(): Promise<Pipeline[]> {
  const r = await getRequest(`${B}/pipelines`) as any
  return r.pipelines
}

export async function getPipeline(id: number): Promise<Pipeline> {
  return await getRequest(`${B}/pipelines/${id}`) as any
}

export async function addPipeline(name: string, steps: object): Promise<number> {
  const r = await postRequest(`${B}/pipelines`, {}, { name, steps }) as any
  return r.id
}

export async function updatePipeline(id: number, name: string, steps: object): Promise<void> {
  await putRequest(`${B}/pipelines/${id}`, {}, { name, steps })
}

export async function deletePipeline(id: number): Promise<void> {
  await deleteRequest(`${B}/pipelines/${id}`)
}

export async function getPipelineConfig(id: number): Promise<RunConfig> {
  return await getRequest(`${B}/pipelines/${id}/config`) as any
}

export async function savePipelineConfig(id: number, config: RunConfig): Promise<void> {
  await putRequest(`${B}/pipelines/${id}/config`, {}, config)
}

export interface Password {
  id: number
  value: string
  note: string
}

export async function getPasswords(): Promise<Password[]> {
  const r = await getRequest(`${B}/passwords`) as any
  return r.passwords
}

export async function addPassword(value: string, note: string): Promise<number> {
  const r = await postRequest(`${B}/passwords`, {}, { value, note }) as any
  return r.id
}

export async function updatePassword(id: number, value: string, note: string): Promise<void> {
  await putRequest(`${B}/passwords/${id}`, {}, { value, note })
}

export async function deletePassword(id: number): Promise<void> {
  await deleteRequest(`${B}/passwords/${id}`)
}

export async function reorderPasswords(ids: number[]): Promise<void> {
  await postRequest(`${B}/passwords/reorder`, {}, { ids })
}

export async function runPipeline(
  pipeline_id: number,
  folder_path: string,
  run_vars?: Record<string, string>
): Promise<string> {
  const r = await postRequest(`${B}/run`, {}, { pipeline_id, folder_path, run_vars: run_vars ?? {} }) as any
  return r.run_id
}
