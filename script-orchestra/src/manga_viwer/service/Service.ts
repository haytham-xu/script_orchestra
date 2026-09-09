import {getRequest, putRequest, postRequest, deleteRequest} from '@/basic/RequestService'
import {MANGA_VIEWER_INDEX_ENDPOINT, MANGA_VIEWER_FOLDER_SCAN_ENDPINT, MANGA_VIEWER_UPDATE_ENDPOINT, MANGA_VIEWER_SETTINGS_ENDPOINT} from '@/basic/Constants.ts'
import type { MangaIndex, FolderModel, MangaViewerSettings } from '@/manga_viwer/service/Model'

export async function fetchIndex(): Promise<MangaIndex> {
  return await getRequest<MangaIndex>(MANGA_VIEWER_INDEX_ENDPOINT)
}

export async function fetchRandomIndex(count?: number): Promise<MangaIndex> {
  const url = count
    ? `${MANGA_VIEWER_INDEX_ENDPOINT}/random?count=${count}`
    : `${MANGA_VIEWER_INDEX_ENDPOINT}/random`
  return await getRequest<MangaIndex>(url)
}

export async function fetchFileList(folderId:string): Promise<string[]> {
  return await getRequest<string[]>(MANGA_VIEWER_FOLDER_SCAN_ENDPINT, { folderId: folderId })
}

export async function updateFolderModels(folderModels:Record<string, FolderModel>, classifierMode: boolean): Promise<void> {
  await putRequest<FolderModel>(MANGA_VIEWER_UPDATE_ENDPOINT + "/" + classifierMode, {}, folderModels)
}

export async function deleteFolders(folderIds: string[]): Promise<void> {
  await postRequest('/manga-viewer/delete', {}, { folderIds })
}

export async function fetchSettings(): Promise<MangaViewerSettings> {
  return await getRequest<MangaViewerSettings>(MANGA_VIEWER_SETTINGS_ENDPOINT)
}

export async function updateSettings(settings: Partial<MangaViewerSettings>): Promise<MangaViewerSettings> {
  return await putRequest<MangaViewerSettings>(MANGA_VIEWER_SETTINGS_ENDPOINT, {}, settings)
}

export async function openFolder(folderId: string): Promise<void> {
  await postRequest('/manga-viewer/open-folder', {}, { folderId })
}

export async function refreshIndex(): Promise<void> {
  await postRequest('/manga-viewer/refresh-index', {}, {})
}

export interface RefreshStatus {
  running: boolean
  phase: string
  total: number
  done: number
}

export async function fetchRefreshStatus(): Promise<RefreshStatus> {
  return await getRequest<RefreshStatus>('/manga-viewer/refresh-status')
}

export interface MangaStats {
  total_folders: number
  total_files: number
  total_size: number
}

export async function fetchStats(): Promise<MangaStats> {
  return await getRequest<MangaStats>('/manga-viewer/stats')
}

export async function incReadCount(folderId: string): Promise<{ id: string; read_count: number }> {
  return await postRequest<{ id: string; read_count: number }>(`/manga-viewer/folder/${encodeURIComponent(folderId)}/read-inc`, {}, {})
}

export async function resetReadCount(folderId: string): Promise<{ id: string; read_count: number }> {
  return await postRequest<{ id: string; read_count: number }>(`/manga-viewer/folder/${encodeURIComponent(folderId)}/read-reset`, {}, {})
}

export async function cleanEmptyFolders(): Promise<void> {
  await postRequest('/manga-viewer/clean-empty-folders', {}, {})
}

// ── Queue types ────────────────────────────────────────────────────────────

export interface ReadQueueEntry {
  folder_id: string
  added_at: number
}

export interface SnoozeQueueEntry {
  folder_id: string
  added_at: number
  expires_at: number
}

export interface QueueResponse<T> {
  entries: T[]
  folders: Record<string, any>
}

// ── Read Queue ─────────────────────────────────────────────────────────────

export async function fetchReadQueue(): Promise<QueueResponse<ReadQueueEntry>> {
  return await getRequest<QueueResponse<ReadQueueEntry>>('/manga-viewer/read-queue')
}

export async function addToReadQueue(folderId: string): Promise<{ entry: ReadQueueEntry }> {
  return await postRequest<{ entry: ReadQueueEntry }>('/manga-viewer/read-queue', {}, { folder_id: folderId })
}

export async function removeFromReadQueue(folderId: string): Promise<void> {
  await deleteRequest(`/manga-viewer/read-queue/${encodeURIComponent(folderId)}`)
}

// ── Snooze Queue ───────────────────────────────────────────────────────────

export async function fetchSnoozeQueue(): Promise<QueueResponse<SnoozeQueueEntry>> {
  return await getRequest<QueueResponse<SnoozeQueueEntry>>('/manga-viewer/snooze-queue')
}

export async function addToSnoozeQueue(folderId: string, days = 7): Promise<{ entry: SnoozeQueueEntry }> {
  return await postRequest<{ entry: SnoozeQueueEntry }>('/manga-viewer/snooze-queue', {}, { folder_id: folderId, days })
}

export async function removeFromSnoozeQueue(folderId: string): Promise<void> {
  await deleteRequest(`/manga-viewer/snooze-queue/${encodeURIComponent(folderId)}`)
}

export async function cleanupSnoozeQueue(): Promise<{ deleted: number }> {
  return await postRequest<{ deleted: number }>('/manga-viewer/snooze-queue/cleanup', {}, {})
}
