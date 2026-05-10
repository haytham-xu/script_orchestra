import {getRequest, putRequest, postRequest} from '@/basic/RequestService'
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
