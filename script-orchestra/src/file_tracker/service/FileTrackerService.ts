import { getRequest, postRequest, putRequest, patchRequest, deleteRequest } from '@/basic/RequestService'
import { FILE_TRACKER_ENDPOINT } from '@/basic/Constants'
import type { TrackedFile, ScanStatus, FileTrackerSettings, FilesPage, FileStats } from './Model'

const B = FILE_TRACKER_ENDPOINT

export async function startScan(): Promise<{ message: string }> {
  return postRequest(`${B}/scan`)
}

export async function getScanStatus(): Promise<ScanStatus> {
  return getRequest<ScanStatus>(`${B}/scan/status`)
}

export interface FilesQuery {
  status?: string
  min_age_days?: number
  max_age_days?: number
  sort?: string
  order?: string
  page?: number
  per_page?: number
  q?: string
}

export async function getFiles(q: FilesQuery = {}): Promise<FilesPage> {
  const params: Record<string, any> = {}
  if (q.status) params.status = q.status
  if (q.min_age_days != null) params.min_age_days = q.min_age_days
  if (q.max_age_days != null) params.max_age_days = q.max_age_days
  if (q.sort) params.sort = q.sort
  if (q.order) params.order = q.order
  if (q.page) params.page = q.page
  if (q.per_page) params.per_page = q.per_page
  if (q.q) params.q = q.q
  return getRequest<FilesPage>(`${B}/files`, params)
}

export async function getStats(): Promise<FileStats> {
  return getRequest<FileStats>(`${B}/files/stats`)
}

export async function patchFile(id: number, patch: { status?: string; note?: string }): Promise<TrackedFile | null> {
  const r = await patchRequest<{ file: TrackedFile | null }>(`${B}/files/${id}`, {}, patch)
  return r.file
}

export async function trashFile(id: number): Promise<void> {
  await deleteRequest(`${B}/files/${id}`)
}

export async function bulkStatus(ids: number[], status: string): Promise<void> {
  await postRequest(`${B}/files/bulk-status`, {}, { ids, status })
}

export async function bulkDelete(ids: number[]): Promise<{ deleted: number; errors: any[] }> {
  return postRequest(`${B}/files/bulk-delete`, {}, { ids })
}

export async function revealFile(id: number): Promise<void> {
  await postRequest(`${B}/files/${id}/reveal`)
}

export async function pruneDeleted(): Promise<number> {
  const r = await postRequest<{ removed: number }>(`${B}/files/prune`)
  return r.removed
}

export async function getSettings(): Promise<FileTrackerSettings> {
  const r = await getRequest<{ settings: FileTrackerSettings }>(`${B}/settings`)
  return r.settings
}

export async function saveSettings(s: FileTrackerSettings): Promise<FileTrackerSettings> {
  const r = await putRequest<{ settings: FileTrackerSettings }>(`${B}/settings`, {}, s)
  return r.settings
}
