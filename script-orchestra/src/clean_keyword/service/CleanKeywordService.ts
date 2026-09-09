import { getRequest, postRequest, deleteRequest } from '@/basic/RequestService'
import { CLEAN_KEYWORD_ENDPOINT } from '@/basic/Constants'

const BASE = CLEAN_KEYWORD_ENDPOINT

export interface PreviewItem {
  old_name: string
  new_name: string
  conflict: boolean
  resolved: string
}

export interface ApplyResult {
  renamed: number
  skipped: number
  errors: { folder: string; error: string }[]
}

export async function fetchKeywords(): Promise<string[]> {
  const res = await getRequest(`${BASE}/keywords`) as any
  return res.keywords ?? []
}

export async function addKeyword(keyword: string): Promise<string[]> {
  const res = await postRequest(`${BASE}/keywords`, { keyword }) as any
  return res.keywords ?? []
}

export async function deleteKeyword(kw: string): Promise<void> {
  await deleteRequest(`${BASE}/keywords/${encodeURIComponent(kw)}`)
}

export async function importKeywords(text: string): Promise<{ added: number; keywords: string[] }> {
  return await postRequest(`${BASE}/keywords/import`, { text }) as any
}

export async function previewClean(rootPath: string): Promise<{ items: PreviewItem[]; total: number }> {
  return await getRequest(`${BASE}/preview?root_path=${encodeURIComponent(rootPath)}`) as any
}

export async function applyClean(rootPath: string): Promise<ApplyResult> {
  return await postRequest(`${BASE}/apply`, { root_path: rootPath }) as any
}
