import { postRequest } from '@/basic/RequestService'
import { DEDUP_FOLDER_ENDPOINT } from '@/basic/Constants'

const BASE = DEDUP_FOLDER_ENDPOINT

// Cross-Dir
export interface CrossItem { name: string; identical: boolean }
export interface CrossPreview { total: number; eligible: number; items: CrossItem[] }
export interface CrossApplyResult { moved: number; errors: number; items: any[] }

export async function crossDirPreview(source_path: string, duplicate_path: string): Promise<CrossPreview> {
  return await postRequest(`${BASE}/cross-dir/preview`, {}, { source_path, duplicate_path }) as any
}
export async function crossDirApply(source_path: string, duplicate_path: string, trash_path: string): Promise<CrossApplyResult> {
  return await postRequest(`${BASE}/cross-dir/apply`, {}, { source_path, duplicate_path, trash_path }) as any
}

// Name Pattern
export interface NameItem { name: string; original: string }
export interface NamePreview { total: number; items: NameItem[] }
export interface NameApplyResult { moved: number; errors: number; items: any[] }

export async function namePatternPreview(source_path: string): Promise<NamePreview> {
  return await postRequest(`${BASE}/name-pattern/preview`, {}, { source_path }) as any
}
export async function namePatternApply(source_path: string, trash_path: string): Promise<NameApplyResult> {
  return await postRequest(`${BASE}/name-pattern/apply`, {}, { source_path, trash_path }) as any
}

// macOS File Dedup
export interface MacosItem { name: string; original: string; same_size: boolean; size_kb: number }
export interface MacosPreview { total: number; items: MacosItem[] }
export interface MacosApplyResult { removed: number; errors: number; items: any[] }

export async function macosFilePreview(source_path: string): Promise<MacosPreview> {
  return await postRequest(`${BASE}/macos-file/preview`, {}, { source_path }) as any
}
export async function macosFileApply(source_path: string, trash_path: string, delete_directly: boolean): Promise<MacosApplyResult> {
  return await postRequest(`${BASE}/macos-file/apply`, {}, { source_path, trash_path, delete_directly }) as any
}
