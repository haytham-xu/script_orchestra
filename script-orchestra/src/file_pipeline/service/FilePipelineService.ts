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

export async function runPipeline(pipeline_id: number, folder_path: string): Promise<RunResult[]> {
  const r = await postRequest(`${B}/run`, {}, { pipeline_id, folder_path }) as any
  return r.results
}
